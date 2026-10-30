using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SemanticTests;

/// <summary>真实PG与Jena验证身份历史、完整范围、幂等及同事务审计。</summary>
[TestClass]
public sealed class G3M4ServiceTests
{
    /// <summary>所有源码保存必须守住已有效声明，不能通过删除类型、范围或编号改写历史。</summary>
    /// <param name="scenario">单个历史破坏路径。</param>
    [TestMethod]
    [DataRow("target")]
    [DataRow("from")]
    [DataRow("delete")]
    [DataRow("type")]
    [DataRow("expand")]
    [DataRow("hide-with-error")]
    public async Task ValidHistoryCannotBeReplacedOrUnlockedByUnrelatedError(string scenario)
    {
        // 同一实际隔离PG连接，任何拒绝都必须回滚命令及业务修订。
        await using var database = Database();
        // 真实生产服务包含真实Jena及同物理事务审计。
        var service = Service(database);
        // 唯一可信主体避免与其它测试幂等键混淆。
        var actor = Actor();
        // 初始合法有界声明具有可保护历史。
        var source = G3M4IdentityTimeTests.Sources(G3M4IdentityTimeTests.Claim("one", to: "2026-03-01T00:00:00Z"));
        // 真实创建后固定当前修订hash。
        var draft = await Create(service, actor, source);
        if (scenario == "hide-with-error")
        {
            // 先实际保存不相关的非法时间claim，不能据bundle失败解锁先前有效claim。
            draft = await service.SaveAsync(actor, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = source with { OntologyTurtle = source.OntologyTurtle + G3M4IdentityTimeTests.Claim("bad", source: "bad.synthetic", from: "invalid") }, Command = Command(draft.Revision) }, default);
            source = draft.Sources;
        }
        // 一次只改变一个受保护语义，不让其它缺失掩盖拒绝原因。
        var text = scenario switch
        {
            "target" or "hide-with-error" => source.OntologyTurtle.Replace("p:targetIri ex:A", "p:targetIri ex:B", StringComparison.Ordinal),
            "from" => source.OntologyTurtle.Replace("2026-01-01T00:00:00Z", "2026-01-02T00:00:00Z", StringComparison.Ordinal),
            "delete" => G3M4IdentityTimeTests.Sources("").OntologyTurtle,
            "type" => source.OntologyTurtle.Replace("ex:claim-one a p:IdentityClaim ;", "ex:claim-one a owl:NamedIndividual ;", StringComparison.Ordinal),
            _ => source.OntologyTurtle.Replace("2026-03-01T00:00:00Z", "2026-04-01T00:00:00Z", StringComparison.Ordinal)
        };
        // 错误不是客户端自报，由实际锁内政策返回同一409。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => service.SaveAsync(actor, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = source with { OntologyTurtle = text }, Command = Command(draft.Revision) }, default));
        Assert.AreEqual(409, error.Status);
        Assert.AreEqual("identity_history_immutable", error.Code);
        Assert.AreEqual(draft.Revision, (await service.ReadAsync(actor, draft.DraftId, default)).Revision);
        Assert.AreEqual(draft.Revision, await database.Revisions.CountAsync(row => row.DraftId == draft.DraftId));
    }

    /// <summary>未曾形成有效声明的非法时间草稿可修正，旧源码修订仍完整保留。</summary>
    [TestMethod]
    public async Task InitiallyInvalidClaimCanBeRepairedWithoutErasingSourceRevision()
    {
        // 真实PG上下文读取历史原字节，不靠前端内存状态判断。
        await using var database = Database();
        // 生产服务负责保存和评估，测试不构造成功评估。
        var service = Service(database);
        // 合成可信双厂操作员。
        var actor = Actor();
        // 初稿非法词法仍能保存供专家修复，绝不能发布。
        var draft = await Create(service, actor, G3M4IdentityTimeTests.Sources(G3M4IdentityTimeTests.Claim("one", from: "invalid")));
        // 修复同一个claim的此前非法时间，PG原修订仍不覆盖。
        var repaired = await service.SaveAsync(actor, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = G3M4IdentityTimeTests.Sources(), Command = Command(1) }, default);
        Assert.AreEqual(2L, repaired.Revision);
        Assert.AreEqual(draft.Sources, JsonSerializer.Deserialize<SourceBundle>((await database.Revisions.AsNoTracking().SingleAsync(row => row.DraftId == draft.DraftId && row.Revision == 1)).SourcesJson));
        // 实际RIOT/SHACL/治理完成后才具备资格。
        var assessment = await service.AssessAsync(actor, draft.DraftId, new ValidateDraftRequest { Revision = 2, Hashes = repaired.Hashes, Command = Command(2) }, default);
        Assert.IsTrue(assessment.PublishEligible);
        Assert.AreEqual("4", assessment.ProfileVersion);
    }

    /// <summary>草稿单厂范围不因操作者拥有更多厂而被身份声明扩大。</summary>
    [TestMethod]
    [DataRow("site")]
    [DataRow("organization")]
    public async Task ClaimScopeCannotExceedAuthoritativeDraftScope(string dimension)
    {
        // 当前真实依赖不会访问任何历史开发数据。
        await using var database = Database();
        // 生产审计与事务复用相同模块入口。
        var service = Service(database);
        // 主体有双厂权限，但待创建资产仅site-a。
        var actor = Actor();
        // 客户端RDF字段不能扩大资产权威scope。
        var source = G3M4IdentityTimeTests.Sources(G3M4IdentityTimeTests.Claim("one", site: dimension == "site" ? "site-b" : "site-a"));
        if (dimension == "organization") source = source with { OntologyTurtle = source.OntologyTurtle.Replace("org-demo", "org-other", StringComparison.Ordinal) };
        // 真实事务失败，任何身份/命令/审计副作用都不提交。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => service.CreateAsync(actor, new CreateDraftRequest { Name = "Synthetic scope refusal", Scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = ["site-a"] }, Sources = source, Command = Command(0) }, default));
        Assert.AreEqual(403, error.Status);
        Assert.AreEqual("identity_scope_forbidden", error.Code);
        Assert.AreEqual(0, await database.Commands.CountAsync(row => row.SubjectId == actor.SubjectId));
    }

    /// <summary>关闭未知终点与新增相邻历史同批成功、幂等重放不重复审计。</summary>
    [TestMethod]
    public async Task ControlledEditClosesValidityThenReplaysExactlyOnce()
    {
        // 所有声明持久在同一真实PG事务边界。
        await using var database = Database();
        // 真实运行时不替换RDF解析或诊断结果。
        var service = Service(database);
        // 独立可信主体与幂等命令。
        var actor = Actor();
        // 开放终点合法，但不能默认解释为无限有效。
        var draft = await Create(service, actor, G3M4IdentityTimeTests.Sources());
        // 单批建立终点声明和旧区间引用，顺序不影响最终完整性。
        var request = new IdentityTimeEditsRequest
        {
            Hashes = draft.Hashes,
            Changes = [Change("interval-one", IdentityTimePolicyNames.Time + "hasEnd", Iri("to-one")), Change("to-one", IdentityTimePolicyNames.Type, new RdfTerm { Kind = RdfTermKind.Iri, Value = IdentityTimePolicyNames.Time + "Instant" }), Change("to-one", IdentityTimePolicyNames.Time + "inXSDDateTimeStamp", new RdfTerm { Kind = RdfTermKind.Literal, Value = "2026-02-01T00:00:00Z", Datatype = "http://www.w3.org/2001/XMLSchema#dateTimeStamp" })],
            Command = Command(1)
        };
        // 一次实际修订保存保留原始旧版本。
        var saved = await service.EditIdentityTimeAsync(actor, draft.DraftId, request, default);
        Assert.AreEqual(2L, saved.Revision);
        Assert.AreEqual(JsonSerializer.Serialize(saved), JsonSerializer.Serialize(await service.EditIdentityTimeAsync(actor, draft.DraftId, request, default)));
        Assert.AreEqual("idempotency_conflict", (await Assert.ThrowsAsync<SemanticOperationException>(() => service.EditIdentityTimeAsync(actor, draft.DraftId, request with { Hashes = saved.Hashes }, default))).Code);
        // 陈旧If-Match所指同修订命令在真实服务CAS再次拒绝。
        Assert.AreEqual("draft_revision_conflict", (await Assert.ThrowsAsync<SemanticOperationException>(() => service.EditIdentityTimeAsync(actor, draft.DraftId, request with { Command = Command(1) }, default))).Code);
        Assert.AreEqual(2, await database.Commands.CountAsync(row => row.SubjectId == actor.SubjectId));
        // 独立上下文直接读取真正审计表，重放不得重复成功事实。
        await using var governance = new GovernanceDbContext(new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(Connection()).Options);
        Assert.AreEqual(2, await governance.AuditRecords.CountAsync(row => row.Actor == actor.SubjectId));
        // 新增相邻同号不同target是独立有效历史，不覆盖旧身份。
        var history = await service.SaveAsync(actor, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = saved.Sources with { OntologyTurtle = saved.Sources.OntologyTurtle + G3M4IdentityTimeTests.Prefix + G3M4IdentityTimeTests.Claim("two", from: "2026-02-01T00:00:00Z", target: "B") }, Command = Command(2) }, default);
        Assert.IsEmpty((await service.ReadIdentityTimeAsync(actor, draft.DraftId, default)).Diagnostics);
        Assert.AreEqual(3L, history.Revision);
    }

    /// <summary>单个历史删除在专用编辑入口仍使用相同409，不因入口变为422。</summary>
    [TestMethod]
    public async Task DedicatedEditCannotDeleteValidClaimType()
    {
        // 本测试直接经过真实PG/Jena用例及强修订命令。
        await using var database = Database();
        // 生产服务不构造假成功数据。
        var service = Service(database);
        // 唯一可信双厂身份。
        var actor = Actor();
        // 合法初稿形成受保护身份历史。
        var draft = await Create(service, actor, G3M4IdentityTimeTests.Sources());
        // 精确删除已有rdf:type，不能借缺类型让旧声明变成新错误草稿。
        var request = new IdentityTimeEditsRequest { Hashes = draft.Hashes, Changes = [new VocabularyChange { SourceId = VocabularyEditSource.Ontology, Edit = new SemanticEdit { SubjectIri = "urn:synthetic:m4:claim-one", PredicateIri = IdentityTimePolicyNames.Type, OldObject = new RdfTerm { Kind = RdfTermKind.Iri, Value = "urn:ontology-platform:semantics:IdentityClaim" } } }], Command = Command(1) };
        // 前置历史检查与最终锁内检查保持相同失败合同。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => service.EditIdentityTimeAsync(actor, draft.DraftId, request, default));
        Assert.AreEqual(409, error.Status);
        Assert.AreEqual("identity_history_immutable", error.Code);
    }

    /// <summary>真实评估把身份冲突和未知关系与SHACL结果分开。</summary>
    [TestMethod]
    [DataRow(false)]
    [DataRow(true)]
    public async Task AmbiguousAndUnknownClaimsBlockAssessment(bool unknown)
    {
        // 当前独立PG运行包含真实报告和评估持久化。
        await using var database = Database();
        // 生产语义服务负责生成全部服务器hash。
        var service = Service(database);
        // 当前可信双厂范围。
        var actor = Actor();
        // 两个同号声明，已知重叠或端点未知必须分别失败关闭。
        var text = G3M4IdentityTimeTests.Claim("one", to: unknown ? null : "2026-03-01T00:00:00Z") + G3M4IdentityTimeTests.Claim("two", from: "2026-02-01T00:00:00Z", to: unknown ? null : "2026-04-01T00:00:00Z", target: "B");
        // 源码保留专家冲突输入，但不能由SHACL的conforms冒充无影响。
        var draft = await Create(service, actor, G3M4IdentityTimeTests.Sources(text));
        // 真实执行五阶段评估后保存同一修订事实。
        var assessment = await service.AssessAsync(actor, draft.DraftId, new ValidateDraftRequest { Revision = 1, Hashes = draft.Hashes, Command = Command(1) }, default);
        Assert.AreEqual(AssessmentStageStatus.Pass, assessment.Stages.Single(stage => stage.Name == "SHACL_CORE").Status);
        Assert.AreEqual(unknown ? AssessmentStageStatus.Indeterminate : AssessmentStageStatus.Fail, assessment.Stages.Single(stage => stage.Name == "GOVERNANCE").Status);
        Assert.IsFalse(assessment.PublishEligible);
        Assert.AreEqual(AssessmentStageStatus.NotRun, assessment.Stages.Single(stage => stage.Name == "OWL_REASONING").Status);
    }

    /// <summary>批次零项和超预算不写入，1与64项保持真实同批RDF集合语义。</summary>
    /// <param name="count">精确批次边界。</param>
    [TestMethod]
    [DataRow(0)]
    [DataRow(1)]
    [DataRow(64)]
    [DataRow(65)]
    public async Task ExactBatchCountBoundariesDoNotBypassCas(int count)
    {
        // 生产数据库和Jena解析均真实使用本次独立夹具。
        await using var database = Database();
        // 服务复用同事务审计。
        var service = Service(database);
        // 每个边界独立主体与草稿。
        var actor = Actor();
        // 合法身份历史不在本测试中被改变。
        var draft = await Create(service, actor, G3M4IdentityTimeTests.Sources());
        // 多次相同新增保持集合语义，不能用重复元素绕过64项输入预算。
        var request = new IdentityTimeEditsRequest { Hashes = draft.Hashes, Changes = Enumerable.Range(0, count).Select(_ => Change("A", "http://www.w3.org/2000/01/rdf-schema#label", new RdfTerm { Kind = RdfTermKind.Literal, Value = "合成设备", Language = "zh" })).ToArray(), Command = Command(1) };
        if (count is 0 or 65)
        {
            // 超界请求失败后，不产生第二条成功命令。
            var error = await Assert.ThrowsAsync<SemanticOperationException>(() => service.EditIdentityTimeAsync(actor, draft.DraftId, request, default));
            Assert.AreEqual(422, error.Status);
            Assert.AreEqual(1L, (await service.ReadAsync(actor, draft.DraftId, default)).Revision);
            Assert.AreEqual(1, await database.Commands.CountAsync(row => row.SubjectId == actor.SubjectId));
        }
        else
        {
            // 最大合法批次仍只追加一次修订与审计。
            var saved = await service.EditIdentityTimeAsync(actor, draft.DraftId, request, default);
            Assert.AreEqual(2L, saved.Revision);
            Assert.AreEqual(2, await database.Commands.CountAsync(row => row.SubjectId == actor.SubjectId));
        }
    }

    /// <summary>真正不同连接的同revision并发只允许一个事务成功。</summary>
    [TestMethod]
    public async Task TwoConcurrentWritersHaveOneCasWinnerAndOneAudit()
    {
        // 初始草稿由独立上下文创建，竞争者不会共享EF跟踪状态。
        await using var database = Database();
        // 固定可信主体及一次创建事实。
        var actor = Actor();
        // 同一草稿的两个写入均使用真正revision1。
        var draft = await Create(Service(database), actor, G3M4IdentityTimeTests.Sources());
        // 两个真实数据库连接各自完成Jena与行锁CAS，不用内存锁模拟竞争。
        var results = await Task.WhenAll(SaveConcurrent(actor, draft, "one"), SaveConcurrent(actor, draft, "two"));
        Assert.AreEqual(1, results.Count(value => value == "SUCCESS"));
        Assert.AreEqual(1, results.Count(value => value == "draft_revision_conflict"));
        // 新连接确认只有一个业务修订和一条成功审计进入PG。
        await using var check = Database();
        Assert.AreEqual(2L, (await Service(check).ReadAsync(actor, draft.DraftId, default)).Revision);
        Assert.AreEqual(2, await check.Commands.CountAsync(row => row.SubjectId == actor.SubjectId));
        // 实际Governance表不因失败竞争记录成功副作用。
        await using var governance = new GovernanceDbContext(new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(Connection()).Options);
        Assert.AreEqual(2, await governance.AuditRecords.CountAsync(row => row.Actor == actor.SubjectId));
    }

    /// <summary>越权角色或不完整厂区范围在源/Jena读取前失败关闭。</summary>
    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public async Task RoleAndCompleteScopePrecedeAnyJenaAccess(bool viewer)
    {
        // 初稿真实持久化，后续拒绝不能来自不存在的对象。
        await using var database = Database();
        // 当前真实主体拥有双厂范围。
        var actor = Actor();
        // 有效身份源及草稿范围固定。
        var draft = await Create(Service(database), actor, G3M4IdentityTimeTests.Sources());
        // 计数门只观察真实HTTP，不制造任何成功替身。
        var calls = 0;
        // 真正引擎工厂会在任何意外访问时计数，权限拒绝必须保持零。
        var runtime = SemanticFixture.RuntimeWithGate((_, _) => { Interlocked.Increment(ref calls); return Task.CompletedTask; });
        // 使用同样生产审计与数据库构造当前被测服务。
        var service = new OntologyService(database, runtime, new TransactionalAuditWriter(new PooledDbContextFactory<GovernanceDbContext>(new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(Connection()).Options)), TimeProvider.System);
        // 角色和范围分别独立失配，不能互相遮掩。
        var denied = viewer ? actor with { Roles = ["platform.viewer"] } : actor with { SiteIds = ["site-a"] };
        // 请求本身有效，唯一拒绝原因是当前可信主体授权。
        var request = new IdentityTimeEditsRequest { Hashes = draft.Hashes, Changes = [Change("A", "http://www.w3.org/2000/01/rdf-schema#label", new RdfTerm { Kind = RdfTermKind.Literal, Value = "合成设备", Language = "zh" })], Command = Command(1) };
        Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.EditIdentityTimeAsync(denied, draft.DraftId, request, default))).Status);
        Assert.AreEqual(0, calls);
        Assert.AreEqual(1, await database.Commands.CountAsync(row => row.SubjectId == actor.SubjectId));
    }

    /// <summary>拒绝未保存的冲突批次时仍返回固定可解释code，不任意挑身份值。</summary>
    /// <param name="scenario">新声明的单个语义错误类别。</param>
    /// <param name="code">公开安全错误类别。</param>
    [TestMethod]
    [DataRow("overlap", "identity_ambiguous")]
    [DataRow("unknown", "identity_relation_indeterminate")]
    [DataRow("zone", "time_timezone_required")]
    [DataRow("reverse", "time_interval_reversed")]
    public async Task NewControlledBatchReturnsDeterministicDiagnosticCode(string scenario, string code)
    {
        // 当前真实PG草稿不含旧身份，保证负例来自新输入而非历史保护。
        await using var database = Database();
        // 可信操作员及真实生产服务。
        var actor = Actor();
        // 在同一服务上复用源散列和CAS。
        var service = Service(database);
        // 空身份正控仍有明确资产类型声明。
        var draft = await Create(service, actor, G3M4IdentityTimeTests.Sources(""));
        // 新声明词法或关系只改变对应负例，所有编号均为Synthetic。
        var text = scenario switch
        {
            "zone" => G3M4IdentityTimeTests.Claim("one", from: "2026-01-01T00:00:00"),
            "reverse" => G3M4IdentityTimeTests.Claim("one", from: "2026-03-01T00:00:00Z", to: "2026-01-01T00:00:00Z"),
            "unknown" => G3M4IdentityTimeTests.Claim("one") + G3M4IdentityTimeTests.Claim("two", target: "B"),
            _ => G3M4IdentityTimeTests.Claim("one", to: "2026-03-01T00:00:00Z") + G3M4IdentityTimeTests.Claim("two", from: "2026-02-01T00:00:00Z", to: "2026-04-01T00:00:00Z", target: "B")
        };
        // 差异批次仍从真正RIOT三元组构造，不从显示字符串恢复RDF项。
        var runtime = (IG3VocabularyRuntime)SemanticFixture.Runtime();
        // 当前四源与目标四源独立解析后只新增真实缺失三元组。
        var before = await runtime.ReadVocabularyAsync(draft.Sources, 1, default);
        // 原始错误词法保留在目标源，读取诊断不伪装为保存成功。
        var target = await runtime.ReadVocabularyAsync(G3M4IdentityTimeTests.Sources(text), 1, default);
        // 精确RDF项和source槽位参与批次，每次完整请求小于64项。
        var changes = target.Triples.Where(item => item.SourceId == "ontology").Select(item => item.Triple).Except(before.Triples.Where(item => item.SourceId == "ontology").Select(item => item.Triple)).Select(triple => new VocabularyChange { SourceId = VocabularyEditSource.Ontology, Edit = new SemanticEdit { SubjectIri = triple.Subject.Value, PredicateIri = triple.Predicate, NewObject = triple.Object } }).ToArray();
        Assert.IsTrue(changes.Length is > 0 and <= 64);
        // 失败后服务器没有产生可伪造的assessment或历史修订。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => service.EditIdentityTimeAsync(actor, draft.DraftId, new IdentityTimeEditsRequest { Hashes = draft.Hashes, Changes = changes, Command = Command(1) }, default));
        Assert.AreEqual(422, error.Status);
        Assert.AreEqual(code, error.Code);
        Assert.AreEqual(1L, (await service.ReadAsync(actor, draft.DraftId, default)).Revision);
    }

    /// <summary>为并发测试单独打开上下文并经过真正SaveCore锁内CAS。</summary>
    private static async Task<string> SaveConcurrent(ActorContext actor, OntologyDraft draft, string marker)
    {
        // 此连接不共享其他竞争者的EF跟踪或事务。
        await using var database = Database();
        try
        {
            await Service(database).SaveAsync(actor, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = draft.Sources with { OntologyTurtle = draft.Sources.OntologyTurtle + "\n# concurrent " + marker + "\n" }, Command = Command(1) }, default);
            return "SUCCESS";
        }
        catch (SemanticOperationException error)
        {
            return error.Code;
        }
    }

    /// <summary>仅创建真实权威双厂草稿，版本由服务器产生。</summary>
    private static Task<OntologyDraft> Create(OntologyService service, ActorContext actor, SourceBundle sources) => service.CreateAsync(actor, new CreateDraftRequest { Name = "Synthetic M4 identity", Scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = actor.SiteIds }, Sources = sources, Command = Command(0) }, default);

    /// <summary>仅连接当前隔离夹具显式注入的PG，不读取历史runtime。</summary>
    private static string Connection() => Environment.GetEnvironmentVariable("G2_SEM_PG_CONNECTION") ?? throw new AssertInconclusiveException("NOT_RUN: requires real PG/Jena fixture");

    /// <summary>本体模块拥有自己的真实数据上下文。</summary>
    private static OntologyDbContext Database() => new(new DbContextOptionsBuilder<OntologyDbContext>().UseNpgsql(Connection()).Options);

    /// <summary>复用真实同事务审计，不提供成功业务替身。</summary>
    private static OntologyService Service(OntologyDbContext database) => new(database, SemanticFixture.Runtime(), new TransactionalAuditWriter(new PooledDbContextFactory<GovernanceDbContext>(new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(Connection()).Options)), TimeProvider.System);

    /// <summary>测试可信双厂身份由服务器夹具产生。</summary>
    private static ActorContext Actor() => new() { SubjectId = Guid.NewGuid().ToString("N"), OrganizationId = "org-demo", SiteIds = ["site-a", "site-b"], Roles = ["platform.operator"], TraceId = Guid.NewGuid().ToString("N"), CorrelationId = Guid.NewGuid().ToString("N") };

    /// <summary>真实CAS与幂等键只在创建新意图时生成。</summary>
    private static CommandContext Command(long revision) => new() { CommandId = Guid.NewGuid().ToString("N"), IdempotencyKey = Guid.NewGuid().ToString("N"), ExpectedRevision = revision, Reason = "Synthetic M4 identity verification" };

    /// <summary>每项精确目标IRI和原RDF对象参与批次，不从显示字符串猜身份。</summary>
    private static VocabularyChange Change(string subject, string predicate, RdfTerm value) => new() { SourceId = VocabularyEditSource.Ontology, Edit = new SemanticEdit { SubjectIri = "urn:synthetic:m4:" + subject, PredicateIri = predicate, NewObject = value } };

    /// <summary>测试固定命名IRI，无空白节点或外部加载。</summary>
    private static RdfTerm Iri(string local) => new() { Kind = RdfTermKind.Iri, Value = "urn:synthetic:m4:" + local };

    /// <summary>仅供测试精确谓词常量，不定义另一套产品治理。</summary>
    private static class IdentityTimePolicyNames
    {
        /// <summary>W3C受控时间词汇命名空间。</summary>
        internal const string Time = "http://www.w3.org/2006/time#";

        /// <summary>标准类型断言谓词。</summary>
        internal const string Type = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
    }
}
