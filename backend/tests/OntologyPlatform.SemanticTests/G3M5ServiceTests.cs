using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SemanticTests;

/// <summary>固定版本表达式读取的短守卫回归与真实PG/RIOT只读、授权、字节保真回归。</summary>
[TestClass]
public sealed class G3M5ServiceTests
{
    /// <summary>应用直接调用也先拒绝无角色或无身份主体，不接触数据库和运行时。</summary>
    [TestMethod]
    [DataRow("role")]
    [DataRow("subject")]
    public async Task GuardRoleRunsBeforePersistenceAndSemanticRuntime(string scenario)
    {
        // 仅构造不会连接的上下文；若错误提前访问PG，本项应真实失败。
        await using var database = GuardDatabase();
        // 缺省运行时和审计故意不可用，确保守卫无需外部前提。
        var service = new OntologyService(database, null!, null!, TimeProvider.System);
        // 当前角色或身份的单点反例。
        var actor = scenario == "role" ? Actor() with { Roles = [] } : Actor() with { SubjectId = "" };
        Assert.AreEqual("role_denied", (await Assert.ThrowsAsync<SemanticOperationException>(() => service.ReadExpressionsAsync(actor, null!, default))).Code);
    }

    /// <summary>非法版本判别在第一条实际SQL或RIOT请求之前快速拒绝。</summary>
    [TestMethod]
    [DataRow("null")]
    [DataRow("empty-id")]
    [DataRow("long-id")]
    [DataRow("missing-revision")]
    [DataRow("zero-revision")]
    [DataRow("release-revision")]
    [DataRow("unknown-kind")]
    public async Task GuardInvalidVersionNeverConnectsToServices(string scenario)
    {
        // 准确项目服务实例执行输入守卫，不建立模拟的正确性替身。
        await using var database = GuardDatabase();
        // 输入错误必须在任何依赖解析或连接之前被发现。
        var service = new OntologyService(database, null!, null!, TimeProvider.System);
        // 每例只改变版本合同的一项判别条件。
        var reference = scenario switch
        {
            "null" => null,
            "empty-id" => new VersionRef { Kind = VersionRefKind.Draft, Id = " ", Revision = 1 },
            "long-id" => new VersionRef { Kind = VersionRefKind.Draft, Id = new string('x', 65), Revision = 1 },
            "missing-revision" => new VersionRef { Kind = VersionRefKind.Draft, Id = "draft", Revision = null },
            "zero-revision" => new VersionRef { Kind = VersionRefKind.Draft, Id = "draft", Revision = 0 },
            "release-revision" => new VersionRef { Kind = VersionRefKind.Release, Id = "release", Revision = 1 },
            _ => new VersionRef { Kind = (VersionRefKind)999, Id = "draft", Revision = 1 }
        };
        Assert.AreEqual("expression_reference_invalid", (await Assert.ThrowsAsync<SemanticOperationException>(() => service.ReadExpressionsAsync(Actor(), reference!, default))).Code);
    }

    /// <summary>正式版本读取没有目录/对象能力时失败关闭，不能降级为当前草稿。</summary>
    [TestMethod]
    public async Task GuardReleaseNeedsAuthoritativeCatalog()
    {
        // 正式分支不应尝试草稿SQL或不可用运行时。
        await using var database = GuardDatabase();
        // 此实例明确没有IReleaseCatalog，不能伪造正式源。
        var service = new OntologyService(database, null!, null!, TimeProvider.System);
        Assert.AreEqual("release_catalog_unavailable", (await Assert.ThrowsAsync<SemanticOperationException>(() => service.ReadExpressionsAsync(Actor(), new VersionRef { Kind = VersionRefKind.Release, Id = "release", Revision = null }, default))).Code);
    }

    /// <summary>真实PG源含BOM、CRLF及注释，读取两次不改源、旧投影、修订、回执或业务审计。</summary>
    [TestMethod]
    public async Task RealReadOnlySnapshotPreservesRawBytesAndDoesNotWrite()
    {
        // 当前测试只连接本轮隔离PG及Jena。
        await using var database = Database();
        // 可信双厂主体持有真实创建权限。
        var actor = Actor();
        // 原源码准确字节包含BOM和Windows换行，不使用RIOT重排文本作为基线。
        var sources = G3M5ExpressionTests.ComplexSources() with { OntologyTurtle = "\uFEFF" + G3M5ExpressionTests.ComplexSources().OntologyTurtle.Replace("\n", "\r\n", StringComparison.Ordinal) };
        // 生产服务完成真实解析及Governance同事务审计。
        var service = Service(database);
        // 复杂源仍可保存；发布资格继续由assessment/profile阻断。
        var draft = await service.CreateAsync(actor, Request(actor, sources), default);
        // 原始持久投影仅作只读无写对照，不替代权威源。
        var before = await database.Revisions.AsNoTracking().SingleAsync(row => row.DraftId == draft.DraftId && row.Revision == 1);
        // 读取前真实业务回执数量。
        var commands = await database.Commands.CountAsync(row => row.SubjectId == actor.SubjectId);
        // Governance拥有自己的上下文，测试只读取实际事务审计事实。
        await using var governance = Governance();
        // 已提交创建业务审计的真实数量。
        var audits = await governance.AuditRecords.CountAsync(row => row.Actor == actor.SubjectId);
        foreach (var count in new[] { 1, 2 })
        {
            // 每次读取都按精确固定版本授权、恢复hash并实际解析。
            var snapshot = await service.ReadExpressionsAsync(actor, Reference(draft.DraftId, 1), default);
            Assert.AreEqual("1", snapshot.ProjectionVersion);
            Assert.AreEqual(draft.Hashes, snapshot.Hashes);
            Assert.AreEqual(1L, snapshot.Version.Revision);
            CollectionAssert.AreEqual(actor.SiteIds, snapshot.Scope.SiteIds);
            Assert.AreEqual(SemanticProfile.Current().Hash, snapshot.ProfileHash);
            Assert.AreEqual("4", snapshot.ProfileVersion);
            Assert.AreEqual("BLOCKED", snapshot.Sources.Single(source => source.SourceId == "ontology").PublishEligible);
            Assert.IsTrue(snapshot.Sources.All(source => source.SourcePreserved && !source.Editable && !source.Inferred));
        }
        // 独立上下文读取排除EF跟踪导致的虚假无修改。
        await using var reopened = Database();
        // 固定修订中的原文和历史投影必须保持准确原JSON字节。
        var after = await reopened.Revisions.AsNoTracking().SingleAsync(row => row.DraftId == draft.DraftId && row.Revision == 1);
        Assert.AreEqual(before.SourcesJson, after.SourcesJson);
        Assert.AreEqual(before.ProjectionJson, after.ProjectionJson);
        Assert.AreEqual(before.HashesJson, after.HashesJson);
        Assert.AreEqual(commands, await reopened.Commands.CountAsync(row => row.SubjectId == actor.SubjectId));
        Assert.AreEqual(audits, await governance.AuditRecords.CountAsync(row => row.Actor == actor.SubjectId));
        Assert.AreEqual(1, await reopened.Revisions.CountAsync(row => row.DraftId == draft.DraftId));
        CollectionAssert.AreEqual(Encoding.UTF8.GetBytes(sources.OntologyTurtle), Encoding.UTF8.GetBytes(JsonSerializer.Deserialize<SourceBundle>(after.SourcesJson)!.OntologyTurtle));
    }

    /// <summary>精确旧修订不被当前头替代，读回再导入保持原字节且真实图同构。</summary>
    [TestMethod]
    public async Task RealHistoricalSnapshotAndReimportRetainExactSourceAndBlankGraph()
    {
        // 同一临时PG隔离多个唯一资产，不复用历史任务数据。
        await using var database = Database();
        // 生产服务读写权威源，不经过客户端图重建。
        var service = Service(database);
        // 每测试唯一主体/幂等键避免并行串扰。
        var actor = Actor();
        // 共享blank仅在同源重复引用；图比较必须容忍RIOT分配新标识。
        var sources = G3M5ExpressionTests.ComplexSources() with { OntologyTurtle = G3M5ExpressionTests.ComplexSources().OntologyTurtle + "\n_:shared a owl:Restriction ; owl:onProperty ex:p ; owl:hasValue ex:i .\nex:A owl:equivalentClass _:shared .\nex:B rdfs:subClassOf _:shared .\n" };
        // 第一固定源作为无损往返基线。
        var draft = await service.CreateAsync(actor, Request(actor, sources), default);
        // 仅增加专家注释仍必须形成不同sourceHash的真实新修订。
        var next = sources with { OntologyTurtle = sources.OntologyTurtle + "# revision two keeps graph semantics\n" };
        // 保存沿既有CAS及真实源/审计事务，不改变旧修订。
        var saved = await service.SaveAsync(actor, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = next, Command = Command(1) }, default);
        // 历史读取按固定修订恢复原hash，不能偷用当前projection。
        var old = await service.ReadExpressionsAsync(actor, Reference(draft.DraftId, 1), default);
        // 当前读取绑定修订2的准确源hash。
        var current = await service.ReadExpressionsAsync(actor, Reference(draft.DraftId, 2), default);
        Assert.AreEqual(draft.Hashes, old.Hashes);
        Assert.AreEqual(saved.Hashes, current.Hashes);
        Assert.AreNotEqual(old.Hashes.OntologyHash, current.Hashes.OntologyHash);
        // 重新从PG原文恢复，相当于服务权威源导出后的重入输入。
        var row = await database.Revisions.AsNoTracking().SingleAsync(item => item.DraftId == draft.DraftId && item.Revision == 1);
        // 原文UTF8每字节保持，包括共享blank标签与全部注释。
        var exported = JsonSerializer.Deserialize<SourceBundle>(row.SourcesJson)!;
        CollectionAssert.AreEqual(Encoding.UTF8.GetBytes(sources.OntologyTurtle), Encoding.UTF8.GetBytes(exported.OntologyTurtle));
        // 新资产重入仍由生产CreateAsync执行真实RIOT解析及PG保存。
        var reimported = await service.CreateAsync(actor, Request(actor, exported), default);
        Assert.AreEqual(draft.Hashes, reimported.Hashes);
        // 显式重命名同源blank只改变语法标签，真实有界同构仍应等价。
        var renamed = exported with { OntologyTurtle = exported.OntologyTurtle.Replace("_:shared", "_:renamed", StringComparison.Ordinal) };
        // 不使用字符串比较代替包含blank双射的实际图比较。
        var comparison = await ((IG3SemanticRuntime)SemanticFixture.Runtime()).CompareSourcesAsync(exported, renamed, default);
        Assert.IsTrue(comparison.All(item => item.Graph.Status == GraphComparisonStatus.Equivalent));
        // 高阶结构不能由基本编辑器覆盖，即使更改的是一个普通label。
        var label = draft.Projection.Triples.Single(item => item.Predicate == "http://www.w3.org/2000/01/rdf-schema#label");
        Assert.AreEqual("structural_edit_unsupported", (await Assert.ThrowsAsync<SemanticOperationException>(() => service.EditAsync(actor, draft.DraftId, new EditDraftRequest { Command = Command(2), Edit = new SemanticEdit { SubjectIri = label.Subject.Value, PredicateIri = label.Predicate, OldObject = label.Object, NewObject = label.Object with { Value = "不能覆盖复杂结构" } } }, default))).Code);
        Assert.AreEqual(saved.Hashes, (await service.ReadAsync(actor, draft.DraftId, default)).Hashes);
    }

    /// <summary>越权组织、缺一厂区及无角色在RIOT前拒绝；合法viewer仍能准确读取。</summary>
    [TestMethod]
    public async Task RealScopeAuthorizationPrecedesProjectionRequests()
    {
        // 真实PG中的完整双厂资源作为授权事实。
        await using var database = Database();
        // 已授权创建者用于准备真实资源。
        var actor = Actor();
        // 创建使用正常实际运行时，不由模拟数据代替。
        var created = await Service(database).CreateAsync(actor, Request(actor, G3M5ExpressionTests.ComplexSources()), default);
        // 只计固定受控HTTP请求，不记录地址或源码正文。
        var requests = 0;
        // 钩子仍转发到真实Jena，允许证明拒绝发生在首个语义请求之前。
        var runtime = SemanticFixture.RuntimeWithGate((request, token) => { Interlocked.Increment(ref requests); return Task.CompletedTask; });
        // 服务主体范围与版本读取沿生产实现，不通过测试替身授权。
        var reader = Service(database, runtime);
        foreach (var denied in new[] { actor with { OrganizationId = "other-org" }, actor with { SiteIds = ["site-a"] }, actor with { Roles = [] } })
            Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => reader.ReadExpressionsAsync(denied, Reference(created.DraftId, 1), default))).Status);
        Assert.AreEqual(0, requests);
        Assert.AreEqual(404, (await Assert.ThrowsAsync<SemanticOperationException>(() => reader.ReadExpressionsAsync(actor, Reference(created.DraftId, 999), default))).Status);
        Assert.AreEqual(0, requests);
        // 只读角色不需要操作者权限，仍必须覆盖完整双厂范围。
        var snapshot = await reader.ReadExpressionsAsync(actor with { Roles = ["platform.viewer"] }, Reference(created.DraftId, 1), default);
        Assert.AreEqual(created.Hashes, snapshot.Hashes);
        Assert.IsTrue(requests > 0);
    }

    /// <summary>持久原文/散列绑定被破坏时在首条RIOT请求前503，不返回虚构保真结果。</summary>
    [TestMethod]
    public async Task RealTamperedRevisionHashCannotProducePreservedSnapshot()
    {
        // 本例只篡改本测试创建的唯一临时资产，其他任务/资产不受影响。
        await using var database = Database();
        // 独立主体使审计及命令边界可追溯。
        var actor = Actor();
        // 真实创建先完成，保证负例针对存储绑定而非无效初始源。
        var draft = await Service(database).CreateAsync(actor, Request(actor, G3M5ExpressionTests.ComplexSources()), default);
        // 保留原字段给finally恢复，不将损坏存储残留给其他测试。
        var row = await database.Revisions.SingleAsync(item => item.DraftId == draft.DraftId && item.Revision == 1);
        // 原hash JSON字节仅留本进程，不写日志。
        var original = row.HashesJson;
        // HTTP计数确认hash拒绝发生在运行时投影之前。
        var requests = 0;
        // 钩子只观察真实传输，不提供模拟RDF。
        var runtime = SemanticFixture.RuntimeWithGate((request, token) => { Interlocked.Increment(ref requests); return Task.CompletedTask; });
        try
        {
            row.HashesJson = JsonSerializer.Serialize(draft.Hashes with { OntologyHash = new string('0', 64) });
            await database.SaveChangesAsync();
            Assert.AreEqual("revision_source_binding_invalid", (await Assert.ThrowsAsync<SemanticOperationException>(() => Service(database, runtime).ReadExpressionsAsync(actor, Reference(draft.DraftId, 1), default))).Code);
            Assert.AreEqual(0, requests);
        }
        finally
        {
            row.HashesJson = original;
            await database.SaveChangesAsync();
        }
    }

    /// <summary>只构造无秘密且不可意外长连接的守卫上下文，不访问实际数据库。</summary>
    private static OntologyDbContext GuardDatabase() => new(new DbContextOptionsBuilder<OntologyDbContext>().UseNpgsql("Host=127.0.0.1;Port=1;Database=synthetic_m5_guard;Timeout=1").Options);

    /// <summary>仅允许本轮隔离harness显式提供的真实PG连接。</summary>
    private static string Connection()
    {
        // 不读取任何历史runtime、凭证文件或机器配置。
        var connection = Environment.GetEnvironmentVariable("G2_SEM_PG_CONNECTION");
        if (connection is null) Assert.Inconclusive("NOT_RUN: 需要本轮隔离PG/RIOT服务。");
        return connection;
    }

    /// <summary>读取本体模块独有schema的真实临时PG上下文。</summary>
    private static OntologyDbContext Database() => new(new DbContextOptionsBuilder<OntologyDbContext>().UseNpgsql(Connection()).Options);

    /// <summary>只读取治理模块自身审计，不跨模块写表。</summary>
    private static GovernanceDbContext Governance() => new(new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(Connection()).Options);

    /// <summary>使用生产语义服务及真实Governance同事务审计写入器。</summary>
    private static OntologyService Service(OntologyDbContext database, ISemanticRuntime? runtime = null) => new(database, runtime ?? SemanticFixture.Runtime(), new TransactionalAuditWriter(new PooledDbContextFactory<GovernanceDbContext>(new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(Connection()).Options)), TimeProvider.System);

    /// <summary>本轮唯一可信主体及完整双厂范围。</summary>
    private static ActorContext Actor() => new() { SubjectId = Guid.NewGuid().ToString("N"), OrganizationId = "org-demo", SiteIds = ["site-a", "site-b"], Roles = ["platform.operator"], TraceId = Guid.NewGuid().ToString("N"), CorrelationId = Guid.NewGuid().ToString("N") };

    /// <summary>原文保存请求使用唯一幂等命令及相同完整scope。</summary>
    private static CreateDraftRequest Request(ActorContext actor, SourceBundle sources) => new() { Name = "Synthetic M5保真", Scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = actor.SiteIds }, Sources = sources, Command = Command(0) };

    /// <summary>固定草稿修订定位，不使用当前头隐式替换。</summary>
    private static VersionRef Reference(string draftId, long revision) => new() { Kind = VersionRefKind.Draft, Id = draftId, Revision = revision };

    /// <summary>测试专有幂等命令及准确CAS修订。</summary>
    private static CommandContext Command(long revision) => new() { CommandId = Guid.NewGuid().ToString("N"), IdempotencyKey = Guid.NewGuid().ToString("N"), ExpectedRevision = revision, Reason = "Synthetic M5只读与源保真验证" };
}
