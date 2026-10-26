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
        var saved = await service.SaveAsync(actor, draft.DraftId, new SaveDraftRequest { Sources = changed, Command = Command(1) }, CancellationToken.None);
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
        var save = new SaveDraftRequest { Sources = request.Sources with { OntologyTurtle = request.Sources.OntologyTurtle + "\n# 重放\n" }, Command = Command(1) };
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
            if (role != "platform.operator") Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.SaveAsync(reader, draft.DraftId, new SaveDraftRequest { Sources = draft.Sources, Command = Command(1) }, CancellationToken.None))).Status);
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
        Assert.AreEqual(422, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.SaveAsync(actor, draft.DraftId, new SaveDraftRequest { Sources = draft.Sources with { OntologyTurtle = "not Turtle" }, Command = Command(1) }, CancellationToken.None))).Status);
        Assert.AreEqual(409, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.SaveAsync(actor, draft.DraftId, new SaveDraftRequest { Sources = draft.Sources, Command = Command(0) }, CancellationToken.None))).Status);
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
        var catalog = new PinnedCatalog(new ReleaseSummary { Status = ReleaseStatus.Active, Manifest = new ReleaseManifest { ReleaseId = releaseId, AssetId = assetId, Scope = new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a", "site-b"] } } });
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

    /// <summary>真实Down必须拒绝并发访问及非空历史，不能删除已经提交的源事实。</summary>
    [TestMethod]
    public async Task MigrationDownRefusesConcurrentAndNonemptyHistory()
    {
        // 使用本轮临时PG与实际Master迁移，绝不访问历史数据库。
        await using var database = Database();
        // 真实源历史是回退保护对象。
        var actor = Actor();
        // 保证此用例独立执行时数据库也不是空状态。
        var draft = await Service(database).CreateAsync(actor, Request(), CancellationToken.None);
        // 第二条物理连接模拟仍有业务持有草稿行锁。
        await using var busy = Database();
        // 活跃事务不能被迁移无限等待或绕过。
        await using (var transaction = await busy.Database.BeginTransactionAsync())
        {
            await busy.Drafts.FromSqlInterpolated($"SELECT * FROM ontology.\"Drafts\" WHERE \"DraftId\"={draft.DraftId} FOR UPDATE").SingleAsync();
            // NOWAIT必须给出锁不可用，而不是继续删除表。
            var concurrent = await Assert.ThrowsAsync<InvalidOperationException>(() => database.GetService<IMigrator>().MigrateAsync("0"));
            // Npgsql执行策略把瞬时55P03包装一层，必须核查真实内层SQLSTATE。
            var postgres = concurrent.InnerException as PostgresException;
            Assert.IsNotNull(postgres);
            Assert.AreEqual("55P03", postgres.SqlState);
            await transaction.RollbackAsync();
        }
        // 没有并发锁时也仍不能抹除已存在的任何源历史。
        var nonempty = await Assert.ThrowsAsync<PostgresException>(() => database.GetService<IMigrator>().MigrateAsync("0"));
        Assert.AreEqual("P0001", nonempty.SqlState);
        Assert.AreEqual(draft.Sources, (await Service(database).ReadAsync(actor, draft.DraftId, CancellationToken.None)).Sources);
        Assert.IsTrue((await database.Database.GetAppliedMigrationsAsync()).Contains("20261026003221_InitialOntology"));
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
            await service.SaveAsync(actor, draft.DraftId, new SaveDraftRequest { Sources = draft.Sources with { OntologyTurtle = draft.Sources.OntologyTurtle + "\n# " + marker }, Command = Command(1) }, CancellationToken.None);
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
