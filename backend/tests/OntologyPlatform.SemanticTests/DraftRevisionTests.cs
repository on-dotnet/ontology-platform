using System.Data.Common;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using Npgsql;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SemanticTests;

/// <summary>真实PG迁移、真实Jena和Governance事务写入器共同证明草稿一致性。</summary>
[TestClass]
public sealed class DraftRevisionTests
{
    /// <summary>重命名与源修订同事务提交，重放和结构编辑保留名称及源历史。</summary>
    [TestMethod]
    public async Task RenamePersistsThroughReopenListReplayAndStructuralEdit()
    {
        // 独立真实PG上下文承载本次草稿。
        await using var database = Database();
        // 可信双厂操作者不来自客户端输入。
        var actor = Actor();
        // 生产服务执行真实Jena解析与事务审计。
        var service = Service(database);
        // 原始四份源码作为字节保真基线。
        var created = await service.CreateAsync(actor, Request(), CancellationToken.None);
        // 仅名称变化仍必须提交可重放的新修订。
        var request = new SaveDraftRequest { Name = "重命名后的资产😀", Sources = created.Sources, Command = Command(1) };
        // 返回值必须包含事务内持久化的新名称。
        var saved = await service.SaveAsync(actor, created.DraftId, request, CancellationToken.None);
        Assert.AreEqual(request.Name, saved.Name);
        Assert.AreEqual(2L, saved.Revision);
        Assert.AreEqual(created.Sources, saved.Sources);
        Assert.AreEqual(created.Hashes, saved.Hashes);
        Assert.AreEqual(JsonSerializer.Serialize(saved), JsonSerializer.Serialize(await service.SaveAsync(actor, created.DraftId, request, CancellationToken.None)));
        // 独立上下文排除EF跟踪缓存导致的虚假持久化。
        await using var reopened = Database();
        // 新服务的读回和目录均必须显示同一名称。
        var reader = Service(reopened);
        Assert.AreEqual(request.Name, (await reader.ReadAsync(actor, created.DraftId, CancellationToken.None)).Name);
        Assert.AreEqual(request.Name, (await reader.ListAsync(actor, CancellationToken.None)).Single(row => row.DraftId == created.DraftId).Name);
        Assert.AreEqual(2, await reopened.Revisions.CountAsync(row => row.DraftId == created.DraftId));
        // 结构编辑只修改三元组，不能重置资产名称。
        var label = saved.Projection.Triples.First(triple => triple.Predicate == "http://www.w3.org/2000/01/rdf-schema#label");
        // 使用真实投影中的完整旧客体，避免猜测词法。
        var edited = await reader.EditAsync(actor, saved.DraftId, new EditDraftRequest { Edit = new SemanticEdit { SubjectIri = label.Subject.Value, PredicateIri = label.Predicate, OldObject = label.Object, NewObject = label.Object with { Value = "重命名后结构编辑" } }, Command = Command(2) }, CancellationToken.None);
        Assert.AreEqual(request.Name, edited.Name);
        // 历史原文仍逐字保存，不因重命名重新导出源码。
        var original = await reopened.Revisions.SingleAsync(row => row.DraftId == created.DraftId && row.Revision == 1);
        Assert.AreEqual(created.Sources, JsonSerializer.Deserialize<SourceBundle>(original.SourcesJson));
    }

    /// <summary>旧修订、审计失败及非法名称不能留下重命名或新源历史。</summary>
    [TestMethod]
    public async Task RenameFailureAndNameBoundsLeaveCommittedNameUnchanged()
    {
        // 真实临时PG中的独立草稿用于观察失败后的状态。
        await using var database = Database();
        // 当前可信双厂主体。
        var actor = Actor();
        // 生产服务先提交有效基线。
        var service = Service(database);
        // 初始草稿名称必须在全部失败后保持不变。
        var created = await service.CreateAsync(actor, Request(), CancellationToken.None);
        Assert.AreEqual(409, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.SaveAsync(actor, created.DraftId, new SaveDraftRequest { Name = "旧修订不能覆盖", Sources = created.Sources, Command = Command(0) }, CancellationToken.None))).Status);
        // 故障发生在真实审计写入后，名称也必须随同事务回滚。
        var failing = new OntologyService(database, SemanticFixture.Runtime(), new FailAfterAudit(Writer()), TimeProvider.System);
        Assert.AreEqual(503, (await Assert.ThrowsAsync<SemanticOperationException>(() => failing.SaveAsync(actor, created.DraftId, new SaveDraftRequest { Name = "审计失败不能覆盖", Sources = created.Sources, Command = Command(1) }, CancellationToken.None))).Status);
        // 空白及超长名称与创建采用相同限制，不能被默认空串掩盖。
        foreach (var name in new[] { "", "  ", new string('名', 201) })
        {
            Assert.AreEqual(422, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.SaveAsync(actor, created.DraftId, new SaveDraftRequest { Name = name, Sources = created.Sources, Command = Command(1) }, CancellationToken.None))).Status);
        }
        // 新上下文验证失败没有污染已提交头或历史。
        await using var reopened = Database();
        Assert.AreEqual(created.Name, (await Service(reopened).ReadAsync(actor, created.DraftId, CancellationToken.None)).Name);
        Assert.AreEqual(1, await reopened.Revisions.CountAsync(row => row.DraftId == created.DraftId));
        Assert.AreEqual(1, await reopened.Commands.CountAsync(row => row.SubjectId == actor.SubjectId));
        // 独立治理读回证明失败没有留下额外审计事实。
        await using var governance = Governance();
        Assert.AreEqual(1, await governance.AuditRecords.CountAsync(row => row.Actor == actor.SubjectId));
        // 与创建一致的200字符上界可成功提交。
        var maximum = await service.SaveAsync(actor, created.DraftId, new SaveDraftRequest { Name = new string('名', 200), Sources = created.Sources, Command = Command(1) }, CancellationToken.None);
        Assert.AreEqual(new string('名', 200), maximum.Name);
    }

    /// <summary>保存历史、真实校验、无损读回和旧发布校验绑定必须同时成立。</summary>
    [TestMethod]
    public async Task SourceHistoryValidationAndPublicationBindingAreReal()
    {
        // 独立真实模块上下文由临时PG连接构建。
        await using var database = Database();
        // 固定可信主体拥有两个厂区和完整平台角色。
        var actor = Actor();
        // 生产服务使用真正Jena和真正Governance writer。
        var service = Service(database);
        // 请求含完整有来源Synthetic源码。
        var request = Request();
        // 初始revision1和源码原字节一起提交。
        var draft = await service.CreateAsync(actor, request, CancellationToken.None);
        Assert.AreEqual(1L, draft.Revision);
        Assert.AreEqual(request.Sources, (await service.ReadAsync(actor, draft.DraftId, CancellationToken.None)).Sources);
        CollectionAssert.AreEqual(new[] { "site-a", "site-b" }, draft.Scope.SiteIds);
        // 报告真正绑定当前草稿revision和源hash。
        var report = await service.ValidateAsync(actor, draft.DraftId, new ValidateDraftRequest { Revision = draft.Revision, Hashes = draft.Hashes, Command = Command(1) }, CancellationToken.None);
        Assert.IsTrue(report.Conforms);
        // 调用方拥有物理事务，Ontology只执行自己的读取锁。
        await using var connection = new NpgsqlConnection(Connection());
        await connection.OpenAsync();
        // 发布前读取不自行提交调用方事务。
        await using (var transaction = await connection.BeginTransactionAsync())
        {
            // 当前成功报告与精确hash在同物理连接锁定核验。
            var locked = await service.LockForPublicationAsync(actor, draft.DraftId, 1, draft.Hashes, report.ReportId, connection, transaction, CancellationToken.None);
            Assert.AreEqual(request.Sources, locked.Draft.Sources);
            await transaction.RollbackAsync();
        }
        // 只新增源码注释仍保存独立原文历史，语义图保持相同。
        var changed = request.Sources with { OntologyTurtle = request.Sources.OntologyTurtle + "\n# 修订二完整原文\n" };
        // 期望修订来自先前返回值，不覆盖其他写入。
        var saved = await service.SaveAsync(actor, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = changed, Command = Command(1) }, CancellationToken.None);
        Assert.AreEqual(2L, saved.Revision);
        Assert.AreEqual(draft.AssetId, saved.AssetId);
        Assert.AreEqual(draft.Scope.OrganizationId, saved.Scope.OrganizationId);
        CollectionAssert.AreEqual(draft.Scope.SiteIds, saved.Scope.SiteIds);
        Assert.AreEqual(2, await database.Revisions.CountAsync(row => row.DraftId == draft.DraftId));
        // 真实原文有差异但三元组无虚假变化。
        var difference = await service.DiffAsync(actor, draft.DraftId, 1, CancellationToken.None);
        Assert.IsNotEmpty(difference.SourceDiff);
        Assert.IsEmpty(difference.AddedTriples);
        Assert.IsEmpty(difference.RemovedTriples);
        // 当前草稿已经变更，旧成功报告不能再次作为发布依据。
        await using (var transaction = await connection.BeginTransactionAsync())
        {
            // 这是跨模块锁定边界的真实失效检查，完整Publishing状态机另由PUB测试。
            var error = await Assert.ThrowsAsync<SemanticOperationException>(() => service.LockForPublicationAsync(actor, draft.DraftId, 1, draft.Hashes, report.ReportId, connection, transaction, CancellationToken.None));
            Assert.AreEqual(409, error.Status);
            await transaction.RollbackAsync();
        }
        // 单独新上下文证明不是EF跟踪缓存形成的读回。
        await using var reopened = Database();
        Assert.AreEqual(changed, (await Service(reopened).ReadAsync(actor, draft.DraftId, CancellationToken.None)).Sources);
        // Governance真实审计表分别含create/validate/save的已提交事实。
        await using var governance = Governance();
        // 真实审计完整scope不退化成首厂。
        var audits = await governance.AuditRecords.Where(row => row.Resource == draft.DraftId).ToArrayAsync();
        Assert.HasCount(3, audits);
        Assert.IsTrue(audits.All(row => row.Outcome == "allowed" && row.ScopeSiteIds!.SequenceEqual(draft.Scope.SiteIds) && row.SiteId is null));
    }

    /// <summary>非BMP结构编辑写入真实PG修订，旧源码字节保持不变且Diff如实包含导出格式变化。</summary>
    [TestMethod]
    public async Task UnicodeEditPersistsExactHistoryAndHonestSourceDiff()
    {
        // 使用交付迁移创建的真实独立PG上下文。
        await using var database = Database();
        // 可信操作者拥有请求的完整scope。
        var actor = Actor();
        // 生产服务使用实际RIOT和真实事务审计写入器。
        var service = Service(database);
        // 原文注释用于证明历史没有被新导出格式覆盖。
        var request = Request();
        request = request with { Sources = request.Sources with { OntologyTurtle = "# 保留原文😀𠀀\n" + request.Sources.OntologyTurtle } };
        // 首次保存保留原文的UTF8散列。
        var draft = await service.CreateAsync(actor, request, CancellationToken.None);
        Assert.AreEqual(OntologyPlatform.Modules.Ontology.Domain.OntologyRules.Hash(request.Sources.OntologyTurtle), draft.Hashes.OntologyHash);
        // 从完整真实投影选取一个已有语言标签，不猜IRI或词法。
        var label = draft.Projection.Triples.First(triple => triple.Predicate == "http://www.w3.org/2000/01/rdf-schema#label");
        // Unicode仅作为新业务词法，语言/datatype保持旧项。
        var replacement = label.Object with { Value = "修改后😀𠀀" };
        // 编辑必须真正提交新修订且保持旧版本源历史。
        var edited = await service.EditAsync(actor, draft.DraftId, new EditDraftRequest { Edit = new SemanticEdit { SubjectIri = label.Subject.Value, PredicateIri = label.Predicate, OldObject = label.Object, NewObject = replacement }, Command = Command(1) }, CancellationToken.None);
        Assert.AreEqual(2L, edited.Revision);
        Assert.AreNotEqual(draft.Hashes.OntologyHash, edited.Hashes.OntologyHash);
        // Diff的源字段保留完整before/after，不能把导出格式变化隐藏为原文未变。
        var difference = await service.DiffAsync(actor, draft.DraftId, 1, CancellationToken.None);
        // 解码真实源差异载荷以核对两个完整SourceBundle，而非只检查文本含emoji。
        using var rawDiff = JsonDocument.Parse(difference.SourceDiff);
        Assert.AreEqual(request.Sources, rawDiff.RootElement.GetProperty("before").Deserialize<SourceBundle>());
        Assert.AreEqual(edited.Sources, rawDiff.RootElement.GetProperty("after").Deserialize<SourceBundle>());
        Assert.AreEqual(1, difference.AddedTriples.Length);
        Assert.AreEqual("修改后😀𠀀", difference.AddedTriples[0].Object.Value);
        Assert.AreEqual(1, difference.RemovedTriples.Length);
        // 新上下文读回证明真实持久化，而非本次服务对象缓存。
        await using var reopened = Database();
        Assert.AreEqual(edited.Sources, (await Service(reopened).ReadAsync(actor, draft.DraftId, CancellationToken.None)).Sources);
        // 原修订仍保存用户提供的全部注释和Unicode源字节。
        var original = await reopened.Revisions.SingleAsync(row => row.DraftId == draft.DraftId && row.Revision == 1);
        Assert.AreEqual(request.Sources, JsonSerializer.Deserialize<SourceBundle>(original.SourcesJson));
    }

    /// <summary>真实PG创建和保存相同含BOM源码后，各修订原文/hash不被临时解析视图覆盖。</summary>
    [TestMethod]
    public async Task LeadingBomCreateSaveAndNoOpKeepExactSourceHistory()
    {
        // 真实交付迁移后的PG上下文，与其他用例草稿隔离。
        await using var database = Database();
        // 原请求含完整Synthetic四源，不访问历史runtime或私有数据。
        var request = Request();
        request = request with
        {
            Sources = request.Sources with
            {
                OntologyTurtle = "\uFEFF" + request.Sources.OntologyTurtle,
                ShapesTurtle = "\uFEFF" + request.Sources.ShapesTurtle,
                VocabularyTurtle = "\uFEFF" + request.Sources.VocabularyTurtle,
                DataTurtle = "\uFEFF" + request.Sources.DataTurtle.Replace("炉次heat-1", "炉\uFEFF次heat-1", StringComparison.Ordinal)
            }
        };
        // 服务使用实际RIOT及真实Governance事务writer。
        var service = Service(database);
        // 操作者拥有全部请求scope。
        var actor = Actor();
        // 初次持久化必须使用完整原文的四个源hash。
        var created = await service.CreateAsync(actor, request, CancellationToken.None);
        Assert.AreEqual(request.Sources, created.Sources);
        Assert.AreEqual(OntologyPlatform.Modules.Ontology.Domain.OntologyRules.Hash(request.Sources.OntologyTurtle), created.Hashes.OntologyHash);
        Assert.AreEqual(OntologyPlatform.Modules.Ontology.Domain.OntologyRules.Hash(request.Sources.ShapesTurtle), created.Hashes.ShapesHash);
        Assert.AreEqual(OntologyPlatform.Modules.Ontology.Domain.OntologyRules.Hash(request.Sources.VocabularyTurtle!), created.Hashes.VocabularyHash);
        Assert.AreEqual(OntologyPlatform.Modules.Ontology.Domain.OntologyRules.Hash(request.Sources.DataTurtle), created.Hashes.DataHash);
        // 相同源保存仍产生受控修订，但不因BOM规范化改变原文/hash。
        var saved = await service.SaveAsync(actor, created.DraftId, new SaveDraftRequest { Name = created.Name, Sources = request.Sources, Command = Command(1) }, CancellationToken.None);
        Assert.AreEqual(2L, saved.Revision);
        Assert.AreEqual(created.Hashes, saved.Hashes);
        Assert.AreEqual(request.Sources, saved.Sources);
        // 从真实投影取精确对象做no-op，不能通过重新导出丢掉BOM。
        var label = saved.Projection.Triples.First(triple => triple.Predicate == "http://www.w3.org/2000/01/rdf-schema#label");
        // no-op生产服务结果仍应引用含BOM的相同完整源。
        var unchanged = await service.EditAsync(actor, saved.DraftId, new EditDraftRequest { Edit = new SemanticEdit { SubjectIri = label.Subject.Value, PredicateIri = label.Predicate, OldObject = label.Object, NewObject = label.Object }, Command = Command(2) }, CancellationToken.None);
        Assert.AreEqual(created.Hashes, unchanged.Hashes);
        Assert.AreEqual(request.Sources, unchanged.Sources);
        // 全部实际历史修订都应保留用户源，不假定no-op一定新建修订。
        var history = await database.Revisions.Where(row => row.DraftId == created.DraftId).ToArrayAsync();
        Assert.IsTrue(history.Length >= 2);
        Assert.IsTrue(history.All(row => JsonSerializer.Deserialize<SourceBundle>(row.SourcesJson) == request.Sources));
        // 新上下文重新加载，排除仅返回内存对象未实际保存的假阳性。
        await using var reopened = Database();
        // 实际数据库读回的DTO用于核验持久原文与hash。
        var loaded = await Service(reopened).ReadAsync(actor, created.DraftId, CancellationToken.None);
        Assert.AreEqual(request.Sources, loaded.Sources);
        Assert.AreEqual(created.Hashes, loaded.Hashes);
        // 相同语义且相同源的Diff必须为空，不把临时BOM去除误报为业务编辑。
        var difference = await service.DiffAsync(actor, created.DraftId, 1, CancellationToken.None);
        Assert.AreEqual("", difference.SourceDiff);
        Assert.AreEqual(0, difference.AddedTriples.Length);
        Assert.AreEqual(0, difference.RemovedTriples.Length);
    }

    /// <summary>真实并发不同载荷只有一个revision CAS胜出，失败方不留审计或源修订。</summary>
    [TestMethod]
    public async Task ConcurrentSaveHasOneWinnerAndNoLostUpdate()
    {
        // 建立两个后续操作共同竞争的持久revision1。
        await using var seed = Database();
        // 测试主体与其他用例隔离。
        var actor = Actor();
        // 真实初始草稿。
        var draft = await Service(seed).CreateAsync(actor, Request(), CancellationToken.None);
        // 两个写入各使用自己的DbContext/物理连接。
        await using var firstDb = Database();
        // 第二上下文防止把EF线程限制误当成并发控制。
        await using var secondDb = Database();
        // 不同命令与源内容但相同期望修订。
        var first = SaveStatus(Service(firstDb), actor, draft, "first");
        // 并发发起第二次真实Jena解析及PG事务。
        var second = SaveStatus(Service(secondDb), actor, draft, "second");
        // 唯一获胜者提交revision2，另一方明确409。
        var outcomes = await Task.WhenAll(first, second);
        CollectionAssert.AreEquivalent(new[] { 200, 409 }, outcomes);
        Assert.AreEqual(2L, (await Service(seed).ReadAsync(actor, draft.DraftId, CancellationToken.None)).Revision);
        Assert.AreEqual(2, await seed.Revisions.CountAsync(row => row.DraftId == draft.DraftId));
        // 失败CAS不能留下success审计。
        await using var governance = Governance();
        Assert.AreEqual(2, await governance.AuditRecords.CountAsync(row => row.Resource == draft.DraftId));
    }

    /// <summary>响应丢失后Jena不可用，同命令仍返回已提交回执且审计/修订不重复。</summary>
    [TestMethod]
    public async Task CommittedCreateAndSaveReplayWithoutJena()
    {
        // 首次操作真正访问Jena与PG。
        await using var database = Database();
        // 固定同一可信主体才能重放其回执。
        var actor = Actor();
        // 保留原命令ID和完整载荷模拟响应丢失。
        var request = Request();
        // 实际首次创建已提交。
        var created = await Service(database).CreateAsync(actor, request, CancellationToken.None);
        // 故障服务使用真实无法连接的回环端口，不是假Jena响应。
        var unavailable = Service(database, UnavailableRuntime());
        Assert.AreEqual(JsonSerializer.Serialize(created), JsonSerializer.Serialize(await unavailable.CreateAsync(actor, request, CancellationToken.None)));
        // 初次保存使用正常运行时，随后同一请求在故障运行时重放。
        var save = new SaveDraftRequest { Name = created.Name, Sources = request.Sources with { OntologyTurtle = request.Sources.OntologyTurtle + "\n# 重放\n" }, Command = Command(1) };
        // 保存真实revision2。
        var saved = await Service(database).SaveAsync(actor, created.DraftId, save, CancellationToken.None);
        Assert.AreEqual(JsonSerializer.Serialize(saved), JsonSerializer.Serialize(await unavailable.SaveAsync(actor, created.DraftId, save, CancellationToken.None)));
        // 异payload复用键不能借重放覆盖现有源。
        var conflict = await Assert.ThrowsAsync<SemanticOperationException>(() => unavailable.SaveAsync(actor, created.DraftId, save with { Sources = save.Sources with { OntologyTurtle = "different" } }, CancellationToken.None));
        Assert.AreEqual(409, conflict.Status);
        Assert.AreEqual(2, await database.Revisions.CountAsync(row => row.DraftId == created.DraftId));
        // 两次同请求重放都不能增加审计。
        await using var governance = Governance();
        Assert.AreEqual(2, await governance.AuditRecords.CountAsync(row => row.Resource == created.DraftId));
    }

    /// <summary>真实审计写入后注入失败，草稿/修订/回执/审计必须全部回滚。</summary>
    [TestMethod]
    public async Task AuditFailureRollsBackEveryWrite()
    {
        // 每个用例独立主体允许检查无残留审计。
        var actor = Actor();
        // 已迁移临时数据库而非EnsureCreated替代模型。
        await using var database = Database();
        // 故障发生在真实Governance写入之后，证明同物理事务原子性。
        var service = new OntologyService(database, SemanticFixture.Runtime(), new FailAfterAudit(Writer()), TimeProvider.System);
        // 唯一名称可直接查回失败命令是否错误留下草稿。
        var request = Request();
        await Assert.ThrowsAsync<SemanticOperationException>(() => service.CreateAsync(actor, request, CancellationToken.None));
        Assert.AreEqual(0, await database.Drafts.CountAsync(row => row.Name == request.Name));
        Assert.AreEqual(0, await database.Commands.CountAsync(row => row.SubjectId == actor.SubjectId));
        // 独立Governance上下文应读不到已回滚的真实审计写入。
        await using var governance = Governance();
        Assert.AreEqual(0, await governance.AuditRecords.CountAsync(row => row.Actor == actor.SubjectId));
    }

    /// <summary>完整三角色允许读，仅operator写；短名/未知角色和不完整范围拒绝。</summary>
    [TestMethod]
    public async Task FullPlatformRolesAndWholeScopeAreEnforced()
    {
        // 真实数据库存放完整双厂范围资源。
        await using var database = Database();
        // 可写主体使用真正OIDC平台role名称。
        var actor = Actor();
        // 真实创建保证正例不是人为插入不完整记录。
        var service = Service(database);
        // 初始双厂草稿。
        var draft = await service.CreateAsync(actor, Request(), CancellationToken.None);
        foreach (var role in new[] { "platform.operator", "platform.viewer", "platform.auditor" })
        {
            // 每个实际role单独访问，不靠operator组合通过。
            var reader = actor with { Roles = [role] };
            Assert.AreEqual(draft.DraftId, (await service.ReadAsync(reader, draft.DraftId, CancellationToken.None)).DraftId);
            Assert.IsTrue((await service.ListAsync(reader, CancellationToken.None)).Any(row => row.DraftId == draft.DraftId));
            if (role != "platform.operator") Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.SaveAsync(reader, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = draft.Sources, Command = Command(1) }, CancellationToken.None))).Status);
        }
        foreach (var role in new[] { "operator", "viewer", "auditor", "platform.unknown" })
            Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.ListAsync(actor with { Roles = [role] }, CancellationToken.None))).Status);
        // 只拥有首厂不能读双厂资源。
        var partial = actor with { SiteIds = ["site-a"] };
        Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.ReadAsync(partial, draft.DraftId, CancellationToken.None))).Status);
        Assert.IsFalse((await service.ListAsync(partial, CancellationToken.None)).Any(row => row.DraftId == draft.DraftId));
        Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.ReadAsync(actor with { OrganizationId = "different-org" }, draft.DraftId, CancellationToken.None))).Status);
        Assert.AreEqual(404, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.ReadAsync(actor, Guid.NewGuid().ToString("N"), CancellationToken.None))).Status);
    }

    /// <summary>非法源码不能写坏当前修订，旧revision写入不能覆盖。</summary>
    [TestMethod]
    public async Task InvalidSourceAndStaleRevisionNeverPersist()
    {
        // 独立模块上下文连接实际PG。
        await using var database = Database();
        // 当前可信操作主体。
        var actor = Actor();
        // 真实初始草稿内容。
        var service = Service(database);
        // 已提交revision1。
        var draft = await service.CreateAsync(actor, Request(), CancellationToken.None);
        Assert.AreEqual(422, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.SaveAsync(actor, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = draft.Sources with { OntologyTurtle = "not Turtle" }, Command = Command(1) }, CancellationToken.None))).Status);
        Assert.AreEqual(409, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.SaveAsync(actor, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = draft.Sources, Command = Command(0) }, CancellationToken.None))).Status);
        Assert.AreEqual(draft.Sources, (await service.ReadAsync(actor, draft.DraftId, CancellationToken.None)).Sources);
        Assert.AreEqual(1, await database.Revisions.CountAsync(row => row.DraftId == draft.DraftId));
    }

    /// <summary>真实PG草稿clone不可改变资产scope；目录使用明确的合同替身，完整PUB链路另行验证。</summary>
    [TestMethod]
    public async Task CloneInheritsOnlyTheCatalogAssetAndExactScope()
    {
        // 草稿创建与审计仍使用真实Jena/PG/Governance。
        await using var database = Database();
        // 唯一可信双厂主体。
        var actor = Actor();
        // 模拟已重新授权目录返回的不可变发布事实，只隔离发布模块依赖。
        var releaseId = Guid.NewGuid().ToString("N");
        // 目录资产身份不能由请求自己决定。
        var assetId = Guid.NewGuid().ToString("N");
        // 此替身只用于Ontology边界测试，不宣称存在真实Publishing发布。
        var catalog = new PinnedCatalog(new ReleaseSummary { Status = ReleaseStatus.Active, Manifest = new ReleaseManifest { SchemaVersion = 1, ReleaseId = releaseId, AssetId = assetId, Scope = new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a", "site-b"] } } });
        // 唯一应用服务通过公共catalog接口继承scope，不跨模块读写表。
        var service = new OntologyService(database, SemanticFixture.Runtime(), Writer(), TimeProvider.System, catalog);
        // 请求引用正式目录ID，而非自行传入assetId。
        var request = Request() with { BaseReleaseId = releaseId };
        // 合法clone继承完全相同asset和scope。
        var draft = await service.CreateAsync(actor, request, CancellationToken.None);
        Assert.AreEqual(assetId, draft.AssetId);
        Assert.AreEqual(releaseId, draft.BaseReleaseId);
        // 缩小成首厂虽然在actor授权内，仍不得改变该asset永久scope。
        var changed = request with { Name = "illegal-scope", Scope = request.Scope with { SiteIds = ["site-a"] }, Command = Command(0) };
        Assert.AreEqual("asset_scope_immutable", (await Assert.ThrowsAsync<SemanticOperationException>(() => service.CreateAsync(actor, changed, CancellationToken.None))).Code);
        Assert.AreEqual(1, await database.Drafts.CountAsync(row => row.AssetId == assetId));
    }

    /// <summary>G3增量只前进，回退拒绝后评估、报告、源历史和迁移记录均保持。</summary>
    [TestMethod]
    public async Task MigrationDownRefusesConcurrentAndNonemptyHistory()
    {
        // 真实迁移保护评估及与其一对一的原始验证报告。
        await using var database = Database();
        // 当前可信完整范围操作者。
        var actor = Actor();
        // 真实源历史是回退保护对象。
        var service = Service(database);
        // 创建并真实评估，证明拒绝回退不能仅保持空表。
        var draft = await service.CreateAsync(actor, Request(), default);
        // 报告与assessment同事务持久。
        var assessment = await service.AssessAsync(actor, draft.DraftId, new ValidateDraftRequest { Revision = 1, Hashes = draft.Hashes, Command = Command(1) }, default);
        // 第二物理连接模拟当前仍有真实业务持锁。
        await using var busy = Database();
        // Forward-only迁移甚至在开始数据库删表前就拒绝。
        await using (var transaction = await busy.Database.BeginTransactionAsync())
        {
            await busy.Drafts.FromSqlInterpolated($"SELECT * FROM ontology.\"Drafts\" WHERE \"DraftId\"={draft.DraftId} FOR UPDATE").SingleAsync();
            await Assert.ThrowsAsync<NotSupportedException>(() => database.GetService<IMigrator>().MigrateAsync("0"));
            await transaction.RollbackAsync();
        }
        // 无并发锁也绝不执行DropTable，不以删除数据实现应用回退。
        await Assert.ThrowsAsync<NotSupportedException>(() => database.GetService<IMigrator>().MigrateAsync("0"));
        Assert.AreEqual(assessment.AssessmentId, (await database.Assessments.AsNoTracking().SingleAsync(row => row.AssessmentId == assessment.AssessmentId)).AssessmentId);
        Assert.AreEqual(assessment.ValidationReportId, (await database.Validations.AsNoTracking().SingleAsync(row => row.ReportId == assessment.ValidationReportId)).ReportId);
        Assert.AreEqual(draft.Sources, (await service.ReadAsync(actor, draft.DraftId, default)).Sources);
        Assert.IsTrue((await database.Database.GetAppliedMigrationsAsync()).Contains("20261027032135_G3Assessments"));
    }

    /// <summary>仅应用Initial的独立空库仍验证原55P03与非空P0001，不绕过G3禁止降级。</summary>
    [TestMethod]
    public async Task InitialOnlyDatabaseKeepsOriginalLockAndNonemptyDownGuards()
    {
        // 仅在当前测试进程新建的隔离PG中创建随机子库。
        await using var admin = new NpgsqlConnection(Connection());
        await admin.OpenAsync();
        // 数据库名只能由固定前缀加服务器Guid组成。
        var name = "g3_initial_guard_" + Guid.NewGuid().ToString("N");
        await using (var create = new NpgsqlCommand("CREATE DATABASE \"" + name + "\"", admin)) await create.ExecuteNonQueryAsync();
        try
        {
            // 不启用连接池，finally可准确回收当前方法拥有的子库。
            var connection = new NpgsqlConnectionStringBuilder(Connection()) { Database = name, Pooling = false };
            // 只应用历史Initial，未应用G3不存在逆向删除评估表的路径。
            var options = new DbContextOptionsBuilder<OntologyDbContext>().UseNpgsql(connection.ConnectionString, database => database.MigrationsHistoryTable("__EFMigrationsHistory", "ontology")).Options;
            // 独立上下文执行真实旧迁移SQL。
            await using var initial = new OntologyDbContext(options);
            await initial.GetService<IMigrator>().MigrateAsync("20261026003221_InitialOntology");
            initial.Drafts.Add(new DraftRecord { DraftId = "guarded", AssetId = "guarded-asset", OrganizationId = "guarded-org", SiteIds = ["guarded-site"], Name = "Initial guard" });
            await initial.SaveChangesAsync();
            // 第二物理连接持真实行锁，旧Down必须NOWAIT拒绝。
            await using var busy = new OntologyDbContext(options);
            await using (var transaction = await busy.Database.BeginTransactionAsync())
            {
                await busy.Drafts.FromSqlRaw("SELECT * FROM ontology.\"Drafts\" WHERE \"DraftId\"='guarded' FOR UPDATE").SingleAsync();
                // 保留旧负例精确SQLSTATE，不用泛化异常冒充通过。
                var error = await Assert.ThrowsAsync<InvalidOperationException>(() => initial.GetService<IMigrator>().MigrateAsync("0"));
                Assert.IsInstanceOfType<PostgresException>(error.InnerException);
                Assert.AreEqual("55P03", ((PostgresException)error.InnerException!).SqlState);
                await transaction.RollbackAsync();
            }
            // 无锁但存在事实时旧Down同样拒绝，数据与迁移记录保持。
            var nonempty = await Assert.ThrowsAsync<PostgresException>(() => initial.GetService<IMigrator>().MigrateAsync("0"));
            Assert.AreEqual("P0001", nonempty.SqlState);
            Assert.AreEqual(1, await initial.Drafts.CountAsync());
            Assert.AreEqual(1, (await initial.Database.GetAppliedMigrationsAsync()).Count());
        }
        finally
        {
            // 仅删除本方法创建的随机子库，不触碰主测试governance库或外部资源。
            await using var drop = new NpgsqlCommand("DROP DATABASE \"" + name + "\" WITH (FORCE)", admin);
            await drop.ExecuteNonQueryAsync();
        }
    }

    /// <summary>相同幂等键真实并发只提交一次；不同载荷不允许共享回执。</summary>
    [TestMethod]
    [DataRow(false)]
    [DataRow(true)]
    public async Task ConcurrentIdempotencyHasOneCommit(bool differentPayload)
    {
        // 两个上下文在两条真实物理事务中竞争同一scope/操作/幂等键。
        await using var firstDatabase = Database();
        // 第二上下文不共享EF状态。
        await using var secondDatabase = Database();
        // 同一可信主体可以重放自己的成功结果。
        var actor = Actor();
        // 固定相同命令与最初源载荷。
        var request = Request();
        // 仅变更一处源码以证明payload绑定不只依赖scope和键。
        var competing = differentPayload ? request with { Sources = request.Sources with { OntologyTurtle = request.Sources.OntologyTurtle + "\n# 竞争载荷" } } : request;
        // 第一命令真实发出，不等待完成才开始第二命令。
        var first = CreateOutcome(Service(firstDatabase), actor, request);
        // 第二命令必须由PG事务锁和payload核验仲裁。
        var second = CreateOutcome(Service(secondDatabase), actor, competing);
        // 允许相同载荷两个响应，但只能一个持久事实。
        var outcomes = await Task.WhenAll(first, second);
        Assert.AreEqual(differentPayload ? 1 : 2, outcomes.Count(outcome => outcome.Status == 200));
        if (differentPayload) Assert.AreEqual(1, outcomes.Count(outcome => outcome.Status == 409));
        else Assert.AreEqual(JsonSerializer.Serialize(outcomes[0].Draft), JsonSerializer.Serialize(outcomes[1].Draft));
        Assert.AreEqual(1, await firstDatabase.Drafts.CountAsync(row => row.OwnerSubjectId == actor.SubjectId));
        Assert.AreEqual(1, await firstDatabase.Commands.CountAsync(row => row.SubjectId == actor.SubjectId));
        // Governance独立读回证明没有重复success审计。
        await using var governance = Governance();
        Assert.AreEqual(1, await governance.AuditRecords.CountAsync(row => row.Actor == actor.SubjectId));
    }


    /// <summary>合并图SHACL不能把仅本体或词汇的focus误标成空data源。</summary>
    [TestMethod]
    [DataRow("ontology")]
    [DataRow("vocabulary")]
    [DataRow("data")]
    [DataRow("ambiguous")]
    public async Task G3MergedShaclDiagnosticNeverGuessesDataSource(string focusSource)
    {
        // 本轮真实PG持久评估与Jena标准SHACL报告。
        await using var database = Database();
        // 完整可信操作者和生产服务。
        var actor = Actor();
        // 唯一真实RIOT/SHACL服务，不在测试伪造Issue来源。
        var service = Service(database);
        // 分别覆盖ontology-only/vocabulary-only/data-only及同一focus跨三源歧义，不能从合并报告猜来源。
        var sources = new SourceBundle { OntologyTurtle = focusSource is "ontology" or "ambiguous" ? "<urn:focus> a <urn:C> ." : "", VocabularyTurtle = focusSource is "vocabulary" or "ambiguous" ? "<urn:focus> a <urn:C> ." : null, DataTurtle = focusSource is "data" or "ambiguous" ? "<urn:focus> a <urn:C> ." : "", ShapesTurtle = "@prefix sh: <http://www.w3.org/ns/shacl#> . <urn:shape> a sh:NodeShape ; sh:targetClass <urn:C> ; sh:property [ sh:path <urn:required> ; sh:minCount 1 ] ." };
        // 真实保存后才能评估准确修订，语法与完整源均由服务器确认。
        var draft = await service.CreateAsync(actor, Request() with { Sources = sources }, default);
        // Jena在合并图实际产生focus定位，旧Issue合同仍标synthetic-data。
        var assessment = await service.AssessAsync(actor, draft.DraftId, new ValidateDraftRequest { Revision = 1, Hashes = draft.Hashes, Command = Command(1) }, default);
        Assert.IsFalse(assessment.PublishEligible);
        Assert.IsNotEmpty(assessment.Diagnostics);
        Assert.IsTrue(assessment.Diagnostics.Any(item => item.Diagnostic.FocusNode?.Value == "urn:focus"));
        Assert.IsTrue(assessment.Diagnostics.All(item => item.SourceId == "bundle" && item.SourceHash == draft.Hashes.BundleHash));
        Assert.IsTrue(assessment.Diagnostics.All(item => item.Line is null && item.Column is null));
        // 不修改历史report的wire shape或虚构具体data来源。
        var report = JsonSerializer.Deserialize<SemanticValidationReport>((await database.Validations.SingleAsync(row => row.ReportId == assessment.ValidationReportId)).ReportJson)!;
        Assert.IsTrue(report.Issues.All(issue => issue.SourceId == "synthetic-data"));
        // 包装层必须保留真实sourceShape，空白shape仍不伪造源码行列。
        Assert.IsTrue(assessment.Diagnostics.All(item => item.SourceShape is not null));
        CollectionAssert.AreEqual(report.Issues.Select(issue => issue.SourceShape).ToArray(), assessment.Diagnostics.Select(item => item.SourceShape).ToArray());
    }

    /// <summary>支持策略诊断根据实际解析来源唯一匹配时保留准确单源hash。</summary>
    [TestMethod]
    [DataRow("ontology")]
    [DataRow("vocabulary")]
    [DataRow("data")]
    public async Task G3SupportDiagnosticRetainsProvenSingleSourceHash(string sourceId)
    {
        // 当前真实PG、RIOT和审计边界。
        await using var database = Database();
        // 完整可信操作者。
        var actor = Actor();
        // 当前生产应用服务，诊断由实际源码生成。
        var service = Service(database);
        // 只有一个文档含未支持身份公理，服务器能够证明来源。
        var sources = new SourceBundle { OntologyTurtle = sourceId == "ontology" ? "<urn:a> <http://www.w3.org/2002/07/owl#sameAs> <urn:b> ." : "", VocabularyTurtle = sourceId == "vocabulary" ? "<urn:a> <http://www.w3.org/2002/07/owl#sameAs> <urn:b> ." : null, DataTurtle = sourceId == "data" ? "<urn:a> <http://www.w3.org/2002/07/owl#sameAs> <urn:b> ." : "" };
        // 源码保留不表示发布支持。
        var draft = await service.CreateAsync(actor, Request() with { Sources = sources }, default);
        // 支持阶段实际失败，SHACL明确未执行。
        var assessment = await service.AssessAsync(actor, draft.DraftId, new ValidateDraftRequest { Revision = 1, Hashes = draft.Hashes, Command = Command(1) }, default);
        Assert.IsFalse(assessment.PublishEligible);
        // hash必须属于真实单一源，不因SHACL保守修复把支持诊断全部降成bundle。
        var expectedHash = sourceId switch { "ontology" => draft.Hashes.OntologyHash, "vocabulary" => draft.Hashes.VocabularyHash, _ => draft.Hashes.DataHash };
        Assert.IsNotEmpty(assessment.Diagnostics);
        Assert.IsTrue(assessment.Diagnostics.All(item => item.SourceId == sourceId && item.SourceHash == expectedHash));
        Assert.AreEqual(AssessmentStageStatus.NotSupported, assessment.Stages.Single(stage => stage.Name == "SUPPORT").Status);
        Assert.AreEqual(AssessmentStageStatus.NotRun, assessment.Stages.Single(stage => stage.Name == "SHACL_CORE").Status);
    }

    /// <summary>真实assessment与报告/幂等/审计原子关联，重放不刷新时间。</summary>
    [TestMethod]
    public async Task G3AssessmentPersistsReplaysAndReauthorizesWholeScope()
    {
        // 使用Master生成的真实迁移和当前隔离PG。
        await using var database = Database();
        // 完整双厂可信主体。
        var actor = Actor();
        // 真实生产服务而非评估替身。
        var service = Service(database);
        // 初始源通过RIOT并保留原始字节。
        var draft = await service.CreateAsync(actor, Request(), default);
        // 相同命令在重放时必须返回相同AssessmentId和时间。
        var request = new ValidateDraftRequest { Revision = draft.Revision, Hashes = draft.Hashes, Command = Command(draft.Revision) };
        // 真正Jena报告与持久评估。
        var assessed = await service.AssessAsync(actor, draft.DraftId, request, default);
        Assert.AreEqual(assessed.AssessedAtUtc.AddHours(24), assessed.ExpiresAtUtc);
        Assert.AreEqual(SemanticProfile.AssessmentHash(assessed), assessed.AssessmentHash);
        Assert.IsTrue(assessed.PublishEligible);
        Assert.AreEqual(AssessmentStageStatus.NotRun, assessed.Stages.Single(stage => stage.Name == "OWL_REASONING").Status);
        Assert.AreEqual(1, await database.Assessments.CountAsync(row => row.DraftId == draft.DraftId));
        Assert.AreEqual(1, await database.Validations.CountAsync(row => row.DraftId == draft.DraftId));
        Assert.AreEqual(JsonSerializer.Serialize(assessed), JsonSerializer.Serialize(await Service(database, UnavailableRuntime()).AssessAsync(actor, draft.DraftId, request, default)));
        Assert.AreEqual(JsonSerializer.Serialize(assessed), JsonSerializer.Serialize(await service.ReadAssessmentAsync(actor with { Roles = ["platform.auditor"] }, assessed.AssessmentId, default)));
        Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.ReadAssessmentAsync(actor with { SiteIds = ["site-a"] }, assessed.AssessmentId, default))).Status);
        Assert.AreEqual(404, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.ReadAssessmentAsync(actor, Guid.NewGuid().ToString("N"), default))).Status);
        Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.AssessAsync(actor with { Roles = ["platform.auditor"] }, draft.DraftId, request with { Command = Command(1) }, default))).Status);
        // 原Validate响应不改形状，但同样生成一对一关联评估。
        var report = await service.ValidateAsync(actor, draft.DraftId, request with { Command = Command(1) }, default);
        Assert.IsNotNull(await database.Assessments.SingleOrDefaultAsync(row => row.ValidationReportId == report.ReportId));
        Assert.AreEqual(2, await database.Assessments.CountAsync(row => row.DraftId == draft.DraftId));
        // 故障在真实审计writer写入之后，报告与评估均须回滚。
        var failing = new OntologyService(database, SemanticFixture.Runtime(), new FailAfterAudit(Writer()), TimeProvider.System);
        await Assert.ThrowsAsync<SemanticOperationException>(() => failing.AssessAsync(actor, draft.DraftId, request with { Command = Command(1) }, default));
        Assert.AreEqual(2, await database.Assessments.CountAsync(row => row.DraftId == draft.DraftId));
        Assert.AreEqual(2, await database.Validations.CountAsync(row => row.DraftId == draft.DraftId));
        await using var governance = Governance();
        Assert.AreEqual(3, await governance.AuditRecords.CountAsync(row => row.Actor == actor.SubjectId));
    }

    /// <summary>审核只读锁允许auditor，过期/profile/内容篡改/旧报告全部失败关闭。</summary>
    [TestMethod]
    [DataRow("expired", "assessment_expired")]
    [DataRow("profile", "assessment_binding_conflict")]
    [DataRow("tampered", "assessment_binding_conflict")]
    [DataRow("legacy", "assessment_required")]
    [DataRow("ineligible", "assessment_not_eligible")]
    public async Task G3AssessmentLockRejectsInvalidPersistentFacts(string scenario, string expectedCode)
    {
        // 每用例独立真实草稿与评估。
        await using var database = Database();
        // 只偏移本次服务时钟，不改系统时间。
        var clock = new AssessmentClock();
        // 真实引擎与事务writer。
        var service = new OntologyService(database, SemanticFixture.Runtime(), Writer(), clock);
        // 当前完整操作者。
        var actor = Actor();
        // 不支持公理也能源码保留，但不能获得发布资格。
        var request = scenario == "ineligible" ? Request() with { Sources = new SourceBundle { OntologyTurtle = "<urn:a> <http://www.w3.org/2002/07/owl#sameAs> <urn:b> ." } } : Request();
        // 真实创建准确修订。
        var draft = await service.CreateAsync(actor, request, default);
        // 全部失败基于真实报告，不能客户端伪造正文。
        var assessment = await service.AssessAsync(actor, draft.DraftId, new ValidateDraftRequest { Revision = draft.Revision, Hashes = draft.Hashes, Command = Command(1) }, default);
        if (scenario == "expired") clock.Offset = TimeSpan.FromHours(25);
        if (scenario is "profile" or "tampered")
        {
            // 精确改变当前测试评估JSON，profile变体重新散列证明仍有独立策略绑定。
            var changed = scenario == "profile" ? assessment with { ProfileHash = new string('0', 64) } : assessment with { PublishEligible = !assessment.PublishEligible };
            if (scenario == "profile") changed = changed with { AssessmentHash = SemanticProfile.AssessmentHash(changed) };
            await database.Assessments.Where(row => row.AssessmentId == assessment.AssessmentId).ExecuteUpdateAsync(update => update.SetProperty(row => row.AssessmentJson, JsonSerializer.Serialize(changed)));
        }
        if (scenario == "legacy") await database.Assessments.Where(row => row.AssessmentId == assessment.AssessmentId).ExecuteDeleteAsync();
        // 发布方拥有同物理事务；auditor在此边界仅有只读核验权限。
        await using var connection = new NpgsqlConnection(Connection());
        await connection.OpenAsync();
        // 失败锁不能提交业务事实。
        await using var transaction = await connection.BeginTransactionAsync();
        // 本检查是实际数据库锁与评估读回，不是内存布尔替身。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => service.LockForPublicationAsync(actor with { Roles = ["platform.auditor"] }, draft.DraftId, draft.Revision, draft.Hashes, assessment.ValidationReportId, connection, transaction, default));
        Assert.AreEqual(expectedCode, error.Code);
        Assert.AreEqual(scenario == "ineligible" ? 422 : 409, error.Status);
        await transaction.RollbackAsync();
    }

    /// <summary>四源BOM/CRLF/注释原始字节跨保存、旧修订与同构比较均保持。</summary>
    [TestMethod]
    public async Task G3FourSourceBytesAndFixedRevisionComparisonRemainExact()
    {
        // 真实PG存储不重建任何四源文本。
        await using var database = Database();
        // 可信完整scope。
        var actor = Actor();
        // 生产实现复用当前Jena。
        var service = Service(database);
        // 每个源都含BOM、CRLF和中文注释，prefix独立。
        var sources = new SourceBundle { OntologyTurtle = "\uFEFF# 本体\r\n<urn:C> a <http://www.w3.org/2002/07/owl#Class> .\r\n", ShapesTurtle = "\uFEFF# 形状\r\n@prefix sh: <http://www.w3.org/ns/shacl#> .\r\n", VocabularyTurtle = "\uFEFF# 词汇\r\n", DataTurtle = "\uFEFF# 数据\r\n<urn:i> a <urn:C> .\r\n" };
        // 初次导入直接持久权威字符串，不读写文本文件造成BOM丢失。
        var created = await service.CreateAsync(actor, Request() with { Sources = sources }, default);
        // no-op保存仍保留完整字节和hash，不从投影导出。
        var saved = await service.SaveAsync(actor, created.DraftId, new SaveDraftRequest { Name = created.Name, Sources = sources, Command = Command(1) }, default);
        Assert.AreEqual(sources, saved.Sources);
        Assert.AreEqual(created.Hashes, saved.Hashes);
        Assert.AreEqual(sources, JsonSerializer.Deserialize<SourceBundle>((await database.Revisions.SingleAsync(row => row.DraftId == created.DraftId && row.Revision == 1)).SourcesJson));
        // 指定两个固定revision后解析比较，不能偷偷比较当前头两次。
        var comparison = await service.CompareAsync(actor, new CompareVersionsRequest { From = new VersionRef { Kind = VersionRefKind.Draft, Id = created.DraftId, Revision = 1 }, To = new VersionRef { Kind = VersionRefKind.Draft, Id = created.DraftId, Revision = 2 } }, default);
        Assert.IsTrue(comparison.All(item => !item.SourceChanged && item.Graph.Status == GraphComparisonStatus.Equivalent));
        // 跨资产即使scope相同也不能用比较泄露或混淆身份。
        var other = await service.CreateAsync(actor, Request(), default);
        Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.CompareAsync(actor, new CompareVersionsRequest { From = new VersionRef { Kind = VersionRefKind.Draft, Id = created.DraftId, Revision = 1 }, To = new VersionRef { Kind = VersionRefKind.Draft, Id = other.DraftId, Revision = 1 } }, default))).Status);
    }

    /// <summary>M2命名编辑通过真实事务保存、重开、评估与CAS，失败不改四源。</summary>
    [TestMethod]
    public async Task M2NamedEditAssessmentAndFailurePreserveCommittedSources()
    {
        // 真实隔离PG与Jena共同承载草稿，不提供业务替身。
        await using var database = Database();
        // 固定可信双厂身份，用于scope失败和持久化读回。
        var actor = Actor();
        // 生产用例复用真实事务审计。
        var service = Service(database);
        // 合法四源原文含CRLF注释，只有ontology允许结构命令变化。
        var sources = new SourceBundle { OntologyTurtle = "# M2\r\n<urn:a> a <http://www.w3.org/2002/07/owl#Class> . <urn:b> a <http://www.w3.org/2002/07/owl#Class> .\r\n", ShapesTurtle = "# shapes\r\n", VocabularyTurtle = "# vocabulary\r\n", DataTurtle = "# data\n" };
        // 创建真实已提交修订作为所有失败断言的基线。
        var created = await service.CreateAsync(actor, Request() with { Sources = sources }, default);
        // 精确命令对象不从显示标签推测。
        var edit = new SemanticEdit { SubjectIri = "urn:a", PredicateIri = "http://www.w3.org/2002/07/owl#equivalentClass", NewObject = new RdfTerm { Kind = RdfTermKind.Iri, Value = "urn:b" } };
        // 真实保存命名公理，并持久化第二修订。
        var changed = await service.EditAsync(actor, created.DraftId, new EditDraftRequest { Edit = edit, Command = Command(1) }, default);
        Assert.AreEqual(2L, changed.Revision);
        Assert.AreEqual(sources with { OntologyTurtle = changed.Sources.OntologyTurtle }, changed.Sources);
        Assert.AreEqual(created.Hashes.ShapesHash, changed.Hashes.ShapesHash);
        Assert.AreEqual(created.Hashes.VocabularyHash, changed.Hashes.VocabularyHash);
        Assert.AreEqual(created.Hashes.DataHash, changed.Hashes.DataHash);
        // 最新服务评估必须绑定当前profile版本、全源散列及修订。
        var assessment = await service.AssessAsync(actor, created.DraftId, new ValidateDraftRequest { Revision = 2, Hashes = changed.Hashes, Command = Command(2) }, default);
        Assert.AreEqual("2", assessment.ProfileVersion);
        Assert.AreEqual(changed.Hashes, assessment.Hashes);
        Assert.AreEqual(2L, assessment.Revision);
        Assert.IsTrue(assessment.PublishEligible);
        // stale CAS、缺权限厂区与非法类型公理全部保持已提交修订。
        Assert.AreEqual(409, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.EditAsync(actor, created.DraftId, new EditDraftRequest { Edit = edit, Command = Command(1) }, default))).Status);
        Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.EditAsync(actor with { SiteIds = ["site-a"] }, created.DraftId, new EditDraftRequest { Edit = edit, Command = Command(2) }, default))).Status);
        Assert.AreEqual("rdf_edit_invalid", (await Assert.ThrowsAsync<SemanticOperationException>(() => service.EditAsync(actor, created.DraftId, new EditDraftRequest { Edit = edit with { NewObject = new RdfTerm { Kind = RdfTermKind.Iri, Value = "urn:undeclared" } }, Command = Command(2) }, default))).Code);
        // no-op仍沿原保存规则增加修订，完整四源及散列逐字不变。
        var noop = await service.EditAsync(actor, created.DraftId, new EditDraftRequest { Edit = edit, Command = Command(2) }, default);
        Assert.AreEqual(3L, noop.Revision);
        Assert.AreEqual(changed.Sources, noop.Sources);
        Assert.AreEqual(changed.Hashes, noop.Hashes);
        // 旧assessment不能绑定新修订的发布冻结入口。
        await using (var connection = new NpgsqlConnection(Connection()))
        {
            await connection.OpenAsync();
            // 外部真实PG事务作为发布冻结的同事务边界。
            await using var transaction = await connection.BeginTransactionAsync();
            Assert.AreEqual(409, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.LockForPublicationAsync(actor, created.DraftId, 3, noop.Hashes, assessment.ValidationReportId, connection, transaction, default))).Status);
        }
        // 重新打开绕过EF跟踪缓存，核验权威原文和历史。
        await using var reopened = Database();
        Assert.AreEqual(noop.Sources, (await Service(reopened).ReadAsync(actor, created.DraftId, default)).Sources);
        Assert.AreEqual(3, await reopened.Revisions.CountAsync(row => row.DraftId == created.DraftId));
    }

    /// <summary>评估有效期测试专用局部时钟。</summary>
    private sealed class AssessmentClock : TimeProvider
    {
        /// <summary>仅当前实例的可控偏移。</summary>
        internal TimeSpan Offset { get; set; }

        /// <summary>真实UTC加当前实例偏移。</summary>
        public override DateTimeOffset GetUtcNow() => DateTimeOffset.UtcNow + Offset;
    }

    /// <summary>保留并发创建的真实结果或固定业务状态，不吞掉意外异常。</summary>
    private static async Task<(int Status, OntologyDraft? Draft)> CreateOutcome(OntologyService service, ActorContext actor, CreateDraftRequest request)
    {
        try { return (200, await service.CreateAsync(actor, request, CancellationToken.None)); }
        catch (SemanticOperationException exception) { return (exception.Status, null); }
    }

    /// <summary>同scope两个真正并发保存之一成功，返回固定状态用于集合断言。</summary>
    private static async Task<int> SaveStatus(OntologyService service, ActorContext actor, OntologyDraft draft, string marker)
    {
        try
        {
            await service.SaveAsync(actor, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = draft.Sources with { OntologyTurtle = draft.Sources.OntologyTurtle + "\n# " + marker }, Command = Command(1) }, CancellationToken.None);
            return 200;
        }
        catch (SemanticOperationException exception) { return exception.Status; }
    }

    /// <summary>只读当前测试进程注入的临时PG连接，不读取历史文件或凭证。</summary>
    private static string Connection()
    {
        // 连接由脚本随机创建并仅通过当前进程环境传递。
        var connection = Environment.GetEnvironmentVariable("G2_SEM_PG_CONNECTION");
        if (connection is null) Assert.Inconclusive("NOT_RUN: 需要draft-revision.py创建临时PG与真实迁移。");
        return connection;
    }

    /// <summary>创建只写Ontology schema的真实上下文。</summary>
    private static OntologyDbContext Database() => new(new DbContextOptionsBuilder<OntologyDbContext>().UseNpgsql(Connection(), options => options.MigrationsHistoryTable("__EFMigrationsHistory", "ontology")).Options);

    /// <summary>创建用于检查真实审计的Governance上下文。</summary>
    private static GovernanceDbContext Governance() => new(new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(Connection()).Options);

    /// <summary>构造生产Governance事务写入器，不在测试中自行写审计表。</summary>
    private static ITransactionalAuditWriter Writer() => new TransactionalAuditWriter(new PooledDbContextFactory<GovernanceDbContext>(new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(Connection()).Options));

    /// <summary>使用真正模块实现及实际时间构造应用用例。</summary>
    private static OntologyService Service(OntologyDbContext database, ISemanticRuntime? runtime = null) => new(database, runtime ?? SemanticFixture.Runtime(), Writer(), TimeProvider.System);

    /// <summary>构造完整可信平台身份，测试不通过客户端伪造HTTP身份头。</summary>
    private static ActorContext Actor() => new() { SubjectId = Guid.NewGuid().ToString("N"), OrganizationId = "org-demo", SiteIds = ["site-a", "site-b"], Roles = ["platform.operator"], TraceId = Guid.NewGuid().ToString("N"), CorrelationId = Guid.NewGuid().ToString("N") };

    /// <summary>生成唯一受控命令，避免用例之间共享幂等键。</summary>
    private static CommandContext Command(long revision) => new() { CommandId = Guid.NewGuid().ToString("N"), IdempotencyKey = Guid.NewGuid().ToString("N"), ExpectedRevision = revision, Reason = "合成数据真实事务验收" };

    /// <summary>标准双厂合成草稿请求，输入厂区顺序用于验证规范化。</summary>
    private static CreateDraftRequest Request() => new() { Name = "合成草稿-" + Guid.NewGuid().ToString("N"), Scope = new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-b", "site-a"] }, Sources = SemanticFixture.Sources(), Command = Command(0) };

    /// <summary>构造真实不可达Jena连接，回执重放不得调用它。</summary>
    private static ISemanticRuntime UnavailableRuntime()
    {
        // 回环端口1不使用任何历史运行时或生产网络。
        var configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?> { ["Semantics:ValidationOrigin"] = "http://127.0.0.1:1/validation/", ["Semantics:PublishedOrigin"] = "http://127.0.0.1:1/ontology/" }).Build();
        // 使用真实网络客户端，任何错误调用都将产生连接故障。
        var services = new ServiceCollection().AddHttpClient();
        return new JenaSemanticRuntime(services.BuildServiceProvider().GetRequiredService<IHttpClientFactory>(), configuration, TimeProvider.System);
    }

    /// <summary>仅注入提交前失败，不伪造审计成功；内层仍为生产Governance writer。</summary>
    private sealed class FailAfterAudit : ITransactionalAuditWriter
    {
        /// <summary>真实治理写入器。</summary>
        private readonly ITransactionalAuditWriter inner;

        /// <summary>保留真实写入器以验证写后失败仍原子回滚。</summary>
        public FailAfterAudit(ITransactionalAuditWriter inner)
        {
            this.inner = inner;
        }

        /// <summary>真实审计已写同事务后抛出固定注入故障。</summary>
        public async Task<string> WriteAsync(ActorContext actor, AuditCommand command, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken)
        {
            await inner.WriteAsync(actor, command, connection, transaction, cancellationToken);
            throw new SemanticOperationException(503, "injected_audit_failure");
        }
    }

    /// <summary>明确的发布目录合同替身，仅测试Ontology消费边界，不表示Publishing已验收。</summary>
    private sealed class PinnedCatalog : IReleaseCatalog
    {
        /// <summary>本测试固定的已授权目录响应。</summary>
        private readonly ReleaseSummary release;

        /// <summary>保存固定目录响应。</summary>
        public PinnedCatalog(ReleaseSummary release)
        {
            this.release = release;
        }

        /// <summary>按唯一发布ID返回测试目录响应，其他ID拒绝。</summary>
        public Task<ReleaseSummary> ReadAsync(ActorContext actor, string releaseId, CancellationToken cancellationToken) =>
            releaseId == release.Manifest.ReleaseId ? Task.FromResult(release) : throw new SemanticOperationException(404, "release_not_found");

        /// <summary>本测试不提供活动发布解析，防止误用为真实发布模块。</summary>
        public Task<ReleaseSummary> ResolveAsync(ActorContext actor, string assetId, string? releaseId, CancellationToken cancellationToken) => throw new NotSupportedException("仅验证Ontology消费目录边界。");
    }
}
