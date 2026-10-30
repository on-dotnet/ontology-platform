using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SemanticTests;

/// <summary>真实PG/Jena影响报告的内容身份、唯一输入、并发、时效及证据边界。</summary>
[TestClass]
public sealed class G3M4ImpactReportTests
{
    /// <summary>同命令重放与同输入不同key均冻结首ID/时间/hash，只有一次生成审计。</summary>
    [TestMethod]
    public async Task ReportIdentityIdempotencyAndAuditAreFrozenToFirstInput()
    {
        // 当前真实PG上下文与生产服务，旧开发资源不参与测试。
        await using var database = Database();
        // 唯一可信主体避免与其它命令相互覆盖。
        var actor = Actor();
        // 可推进时钟仅作用于本服务，不改系统或S3签名时间。
        var clock = new ImpactClock();
        // 生产语义引擎始终为真实RIOT。
        var service = Service(database, clock);
        // 明确两版完整来源和真实assessment，普通版本对可分析但非Release基线不能发布。
        var request = await Prepare(service, actor, "label");
        // 第一次实际生成和保存不可变报告。
        var report = await service.GenerateImpactAsync(actor, request, default);
        Assert.AreEqual(ImpactContractRules.CanonicalHash(report), report.CanonicalHash);
        Assert.IsTrue(report.KnownImpacts.Any(item => item.Code == "impact_explicit_triple_added"));
        Assert.IsFalse(report.PublishEligible);
        Assert.IsTrue(report.Blockers.Any(item => item.Code == "impact_publication_baseline_required"));
        Assert.AreEqual(JsonSerializer.Serialize(report), JsonSerializer.Serialize(await service.ReadImpactAsync(actor, report.ReportId, default)));
        Assert.AreEqual(JsonSerializer.Serialize(report), JsonSerializer.Serialize(await service.GenerateImpactAsync(actor, request, default)));
        // 不同key仍返回首报告，不能刷新ID/生成/期限。
        var retried = await service.GenerateImpactAsync(actor, request with { Command = Command(request.Command.ExpectedRevision) }, default);
        Assert.AreEqual(JsonSerializer.Serialize(report), JsonSerializer.Serialize(retried));
        Assert.AreEqual(1, await database.ImpactReports.CountAsync(row => row.AssetId == report.Diff.AssetId));
        // 同key但修改固定输入时必须冲突，不把旧回执粘到另一个比较。
        Assert.AreEqual("idempotency_conflict", (await Assert.ThrowsAsync<SemanticOperationException>(() => service.GenerateImpactAsync(actor, request with { From = request.To }, default))).Code);
        // canonical明确排除图遥测及envelope，字段顺序由公共合同冻结。
        var telemetry = report with { GeneratedAtUtc = report.GeneratedAtUtc.AddMinutes(1), ExpiresAtUtc = report.ExpiresAtUtc.AddMinutes(1), Diff = report.Diff with { Sources = report.Diff.Sources.Select(source => source with { Graph = source.Graph with { ElapsedMilliseconds = 999, VisitedNodes = 12345 } }).Reverse().ToArray() } };
        Assert.AreEqual(report.CanonicalHash, ImpactContractRules.CanonicalHash(telemetry));
        // 报告到期后仍能审计读取，同输入重放不重新生成或延时。
        clock.Offset = TimeSpan.FromHours(25);
        Assert.IsTrue(report.ExpiresAtUtc < clock.GetUtcNow());
        Assert.AreEqual(report.ExpiresAtUtc, (await service.ReadImpactAsync(actor, report.ReportId, default)).ExpiresAtUtc);
        Assert.AreEqual(report.GeneratedAtUtc, (await service.GenerateImpactAsync(actor, request with { Command = Command(2) }, default)).GeneratedAtUtc);
        // 真实审计表只记录一次生成业务事件，不因其它key回执重复生成。
        await using var audit = new GovernanceDbContext(new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(Connection()).Options);
        Assert.AreEqual(1, await audit.AuditRecords.CountAsync(row => row.Actor == actor.SubjectId && row.Action == "ontology.impact.generate"));
        // Canonical不含随机blank或伪造行列，所有证据能经公共来源绑定验证。
        Assert.IsTrue(report.KnownImpacts.Concat(report.Blockers).Concat(report.UnknownCoverage).All(item => item.Evidence.Length > 0 && item.Evidence.All(evidence => evidence.Line is null && evidence.Column is null)));
    }

    /// <summary>不同连接并发同输入、不同key只创建一个报告和一个生成业务审计。</summary>
    [TestMethod]
    public async Task ConcurrentInputCreatesOneReportAndOneBusinessAudit()
    {
        // 准备真实来源/assessment后释放到独立连接竞争。
        await using var database = Database();
        // 同主体同scope的两个明确命令不共享内存锁。
        var actor = Actor();
        // 固定同一准确版本对和评估引用。
        var request = await Prepare(Service(database), actor, "label");
        // 真正advisory锁和唯一索引负责业务去重。
        var results = await Task.WhenAll(GenerateSeparate(actor, request with { Command = Command(2) }), GenerateSeparate(actor, request with { Command = Command(2) }));
        Assert.AreEqual(results[0].ReportId, results[1].ReportId);
        Assert.AreEqual(results[0].CanonicalHash, results[1].CanonicalHash);
        Assert.AreEqual(results[0].GeneratedAtUtc, results[1].GeneratedAtUtc);
        Assert.AreEqual(1, await database.ImpactReports.CountAsync(row => row.AssetId == results[0].Diff.AssetId));
        // 新上下文读取PG真实成功事实，不用EF跟踪缓存作证据。
        await using var audit = new GovernanceDbContext(new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(Connection()).Options);
        Assert.AreEqual(1, await audit.AuditRecords.CountAsync(row => row.Actor == actor.SubjectId && row.Action == "ontology.impact.generate"));
    }

    /// <summary>missing/unsupported/import/blank/预算均有真实证据并阻断，不把未知当无影响。</summary>
    /// <param name="scenario">独立实际覆盖缺口。</param>
    /// <param name="code">报告必须呈现的固定分类。</param>
    [TestMethod]
    [DataRow("missing", "impact_assessment_required")]
    [DataRow("unsupported", "impact_unsupported_axiom")]
    [DataRow("imports", "impact_imports_unresolved")]
    [DataRow("blank", "impact_blank_alignment_indeterminate")]
    [DataRow("blank-budget", "impact_comparison_indeterminate")]
    [DataRow("conclusion-budget", "impact_conclusion_budget")]
    public async Task ActualUnknownAndTechnicalBlockersHaveBoundEvidence(string scenario, string code)
    {
        // 所有源及报告都由当前真实PG/Jena产生。
        await using var database = Database();
        // 独立actor和asset保证唯一输入不被别例复用。
        var actor = Actor();
        // 正常生产服务复用同物理审计事务。
        var service = Service(database);
        // 每个负例都保留目标原文，不伪造现有assessment。
        var request = await Prepare(service, actor, scenario, assess: false);
        // 报告是实际执行的保守分析，不等于新发布成功。
        var report = await service.GenerateImpactAsync(actor, request, default);
        Assert.IsFalse(report.PublishEligible);
        Assert.IsTrue(report.Blockers.Concat(report.UnknownCoverage).Any(item => item.Code == code && item.Blocking), code);
        Assert.IsTrue(report.KnownImpacts.Length + report.Blockers.Length + report.UnknownCoverage.Length <= 256);
        Assert.AreEqual(report.CanonicalHash, ImpactContractRules.CanonicalHash(report));
        foreach (var item in report.KnownImpacts.Concat(report.Blockers).Concat(report.UnknownCoverage))
            foreach (var evidence in item.Evidence)
            {
                ImpactContractRules.ValidateEvidence(evidence);
                Assert.IsFalse(evidence.FocusIri?.StartsWith("_:", StringComparison.Ordinal) == true);
                Assert.IsFalse(evidence.Triple?.Subject.Kind == RdfTermKind.Blank || evidence.Triple?.Object.Kind == RdfTermKind.Blank);
            }
        // 实际持久报告可完整重读，不能仅靠返回内存对象通过。
        Assert.AreEqual(report.CanonicalHash, (await service.ReadImpactAsync(actor, report.ReportId, default)).CanonicalHash);
    }

    /// <summary>报告读取重新授权完整scope，正文/hash索引漂移时失败关闭。</summary>
    [TestMethod]
    public async Task ReadRejectsPartialScopeAndPersistedCanonicalTamper()
    {
        // 真实报告先存在，拒绝不能来自假ID。
        await using var database = Database();
        // 当前可信双厂actor。
        var actor = Actor();
        // 实际服务不以替身报告模拟成功。
        var service = Service(database);
        // 完整源与assessment绑定同一真实目标。
        var report = await service.GenerateImpactAsync(actor, await Prepare(service, actor, "label"), default);
        Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.ReadImpactAsync(actor with { SiteIds = ["site-a"] }, report.ReportId, default))).Status);
        // 隔离PG故障注入只改canonical索引，不改不可变正文。
        var row = await database.ImpactReports.SingleAsync(item => item.ReportId == report.ReportId);
        row.ReportHash = new string('0', 64);
        await database.SaveChangesAsync();
        Assert.AreEqual("impact_binding_conflict", (await Assert.ThrowsAsync<SemanticOperationException>(() => service.ReadImpactAsync(actor, report.ReportId, default))).Code);
    }

    /// <summary>准备任意两个固定草稿修订与可选真实评估，不捏造成功来源或报告。</summary>
    private static async Task<GenerateImpactReportRequest> Prepare(OntologyService service, ActorContext actor, string scenario, bool assess = true)
    {
        // 正常命名类型保持v4支持正控，后续每个场景只添加对应事实。
        var source = G3M4IdentityTimeTests.Sources("");
        if (scenario == "blank") source = source with { OntologyTurtle = source.OntologyTurtle + "_:old <urn:p> \"a\" ." };
        // 初始修订确实存在于当前PG。
        var created = await service.CreateAsync(actor, new CreateDraftRequest { Name = "Synthetic impact", Scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = actor.SiteIds }, Sources = source, Command = Command(0) }, default);
        // 目标变更原文始终保真，unsupported仍可作为专家源保存。
        var text = scenario switch
        {
            "unsupported" => source.OntologyTurtle + "<urn:synthetic:m4:A> <http://www.w3.org/2002/07/owl#hasKey> <urn:key> .",
            "imports" => source.OntologyTurtle + "<urn:synthetic:m4:A> <http://www.w3.org/2002/07/owl#imports> <https://example.invalid/not-loaded> .",
            "blank" => source.OntologyTurtle.Replace("\"a\"", "\"b\"", StringComparison.Ordinal),
            "blank-budget" => source.OntologyTurtle + string.Join('\n', Enumerable.Range(0, 129).Select(index => "_:b" + index + " <urn:p> \"value\" .")),
            "conclusion-budget" => source.OntologyTurtle + string.Join('\n', Enumerable.Range(0, 300).Select(index => "<urn:synthetic:class:" + index + "> a <http://www.w3.org/2002/07/owl#Class> .")),
            _ => source.OntologyTurtle + "<urn:synthetic:m4:A> <http://www.w3.org/2000/01/rdf-schema#label> \"合成设备\"@zh ."
        };
        // 同一CAS只新增一个完整目标修订。
        var changed = await service.SaveAsync(actor, created.DraftId, new SaveDraftRequest { Name = created.Name, Sources = source with { OntologyTurtle = text }, Command = Command(1) }, default);
        // 可选真实assessment对应准确revision2，不从客户端传成功布尔值。
        var assessment = assess ? await service.AssessAsync(actor, created.DraftId, new ValidateDraftRequest { Revision = 2, Hashes = changed.Hashes, Command = Command(2) }, default) : null;
        return new GenerateImpactReportRequest { From = new VersionRef { Kind = VersionRefKind.Draft, Id = created.DraftId, Revision = 1 }, To = new VersionRef { Kind = VersionRefKind.Draft, Id = created.DraftId, Revision = 2 }, BaselineKind = ImpactBaselineKind.VersionPair, AssessmentId = assessment?.AssessmentId, Command = Command(2) };
    }

    /// <summary>并发生成使用独立物理连接，PG锁而非共享上下文去重。</summary>
    private static async Task<ImpactReport> GenerateSeparate(ActorContext actor, GenerateImpactReportRequest request)
    {
        // 每个竞争者独立上下文，不共享跟踪状态。
        await using var database = Database();
        return await Service(database).GenerateImpactAsync(actor, request, default);
    }

    /// <summary>只允许当前隔离脚本注入的真实连接。</summary>
    private static string Connection() => Environment.GetEnvironmentVariable("G2_SEM_PG_CONNECTION") ?? throw new AssertInconclusiveException("NOT_RUN: real PG/Jena fixture required");

    /// <summary>Ontology模块专属真实数据上下文。</summary>
    private static OntologyDbContext Database() => new(new DbContextOptionsBuilder<OntologyDbContext>().UseNpgsql(Connection()).Options);

    /// <summary>真实运行时与同事务审计使用原生产实现。</summary>
    private static OntologyService Service(OntologyDbContext database, TimeProvider? clock = null) => new(database, SemanticFixture.Runtime(), new TransactionalAuditWriter(new PooledDbContextFactory<GovernanceDbContext>(new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(Connection()).Options)), clock ?? TimeProvider.System);

    /// <summary>可信范围不来自请求中伪造actor。</summary>
    private static ActorContext Actor() => new() { SubjectId = Guid.NewGuid().ToString("N"), OrganizationId = "org-demo", SiteIds = ["site-a", "site-b"], Roles = ["platform.operator"], TraceId = "test", CorrelationId = "test" };

    /// <summary>只在新的明确业务意图产生新幂等键。</summary>
    private static CommandContext Command(long revision) => new() { CommandId = Guid.NewGuid().ToString("N"), IdempotencyKey = Guid.NewGuid().ToString("N"), ExpectedRevision = revision, Reason = "Synthetic impact report" };

    /// <summary>测试时钟只影响当前应用，不修改机器或容器时间。</summary>
    private sealed class ImpactClock : TimeProvider
    {
        /// <summary>测试所需的明确时效推进量。</summary>
        internal TimeSpan Offset { get; set; }

        /// <summary>实际UTC加当前测试偏移。</summary>
        public override DateTimeOffset GetUtcNow() => DateTimeOffset.UtcNow + Offset;
    }
}
