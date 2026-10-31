using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SemanticTests;

/// <summary>精确内建登记与按consumer种类判断显式定义删除的真实PG/Jena正反例。</summary>
[TestClass]
public sealed class G3M4ImpactDependencyTests
{
    /// <summary>W3C或平台命名空间外观不能替代精确登记，真实内建及本地声明有正控。</summary>
    /// <param name="scenario">唯一命名或登记边界。</param>
    /// <param name="unresolved">是否应明确报告未解析依赖。</param>
    [TestMethod]
    [DataRow("w3-fake", true)]
    [DataRow("platform-fake", true)]
    [DataRow("builtin-owl", false)]
    [DataRow("business-local", false)]
    public async Task OnlyExactBuiltinOrLocalClassDeclarationResolvesType(string scenario, bool unresolved)
    {
        // 每个测试使用实际PG/Jena保存和生成，不直接调用私有纯helper伪装集成。
        await using var database = Database();
        // 独立可信主体及草稿使其它例子不能复用本输入的报告。
        var actor = Actor();
        // 仅有明确Asset/A/B声明的正控基线。
        var before = G3M4IdentityTimeTests.Sources("");
        // 原始Turtle输入精确给出边界，不触发网络或自动imports解析。
        var suffix = scenario switch
        {
            "w3-fake" => """<urn:x> a <http://www.w3.org/synthetic-unregistered-class> .""",
            "w3-https-fake" => """<urn:x> a <https://www.w3.org/synthetic-unregistered-class> .""",
            "platform-fake" => """<urn:x> a <urn:ontology-platform:semantics:SyntheticUnregisteredClass> .""",
            "w3-label-only" => """<http://www.w3.org/synthetic-unregistered-class> <http://www.w3.org/2000/01/rdf-schema#label> "只是标签"@zh . <urn:x> a <http://www.w3.org/synthetic-unregistered-class> .""",
            "builtin-owl" => """<urn:x> a <http://www.w3.org/2002/07/owl#NamedIndividual> .""",
            "builtin-time" => """<urn:x> a <http://www.w3.org/2006/time#Instant> .""",
            "builtin-platform" => """<urn:x> a <urn:ontology-platform:semantics:Dimension> .""",
            "w3-local-explicit" => """<http://www.w3.org/synthetic-unregistered-class> a <http://www.w3.org/2002/07/owl#Class> . <urn:x> a <http://www.w3.org/synthetic-unregistered-class> .""",
            _ => """<urn:local-class> a <http://www.w3.org/2002/07/owl#Class> . <urn:x> a <urn:local-class> ."""
        };
        // 未提供assessment是明确分析模式；这里只断言特定依赖结论，不冒充发布资格。
        var report = await Generate(database, actor, before, before with { OntologyTurtle = before.OntologyTurtle + suffix });
        Assert.AreEqual(unresolved, report.UnknownCoverage.Any(item => item.Code == "impact_dependency_unresolved" && item.Blocking));
        Assert.IsFalse(report.UnknownCoverage.Any(item => item.Code == "impact_imports_unresolved"));
        Assert.IsTrue(report.UnknownCoverage.Where(item => item.Code == "impact_dependency_unresolved").All(item => item.Evidence.Any(evidence => evidence.SourceId == "ontology" && evidence.SourceHash == report.Diff.TargetHashes.OntologyHash && evidence.Version == report.Diff.To)));
    }

    /// <summary>只消费准确声明种类，合法多类型与删除无consumer声明不会误报。</summary>
    /// <param name="scenario">显式声明与consumer角色组合。</param>
    /// <param name="blocked">是否仍消费已删除的准确声明。</param>
    [TestMethod]
    [DataRow("class-masked-by-individual", true)]
    [DataRow("object-property-masked", true)]
    [DataRow("datatype-property-masked", true)]
    [DataRow("keep-class-drop-individual", false)]
    public async Task DefinitionRemovalUsesExactKindAndConsumerRole(string scenario, bool blocked)
    {
        // 真正保存两个固定版本，差异与结论来自真实RIOT解析后的事实。
        await using var database = Database();
        // 可信双厂范围不从Turtle字段扩大。
        var actor = Actor();
        // 固定标准语法前缀，全部业务IRI均为Synthetic。
        var source = G3M4IdentityTimeTests.Sources("");
        // 类多类型正控，本轮不执行OWL一致性推理，也不禁止合法punning。
        const string classBoth = "ex:C a owl:Class, owl:NamedIndividual . ex:x a ex:C .";
        // 具体场景分别固定原定义和目标consumer，不能用其它类型掩盖语义角色。
        var pair = scenario switch
        {
            "class-masked-by-property" => (classBoth, "ex:C a owl:ObjectProperty . ex:x a ex:C ."),
            "class-subject-subclass" => ("ex:C a owl:Class, owl:NamedIndividual . ex:D a owl:Class . ex:C <http://www.w3.org/2000/01/rdf-schema#subClassOf> ex:D .", "ex:C a owl:NamedIndividual . ex:D a owl:Class . ex:C <http://www.w3.org/2000/01/rdf-schema#subClassOf> ex:D ."),
            "object-property-masked" => ("ex:p a owl:ObjectProperty, owl:NamedIndividual . ex:A ex:p ex:B .", "ex:p a owl:NamedIndividual . ex:A ex:p ex:B ."),
            "datatype-property-masked" => ("""ex:p a owl:DatatypeProperty, owl:NamedIndividual . ex:A ex:p "42"^^xsd:integer .""", """ex:p a owl:NamedIndividual . ex:A ex:p "42"^^xsd:integer ."""),
            "keep-class-drop-individual" => (classBoth, "ex:C a owl:Class . ex:x a ex:C ."),
            "keep-object-property-drop-individual" => ("ex:p a owl:ObjectProperty, owl:NamedIndividual . ex:A ex:p ex:B .", "ex:p a owl:ObjectProperty . ex:A ex:p ex:B ."),
            "drop-class-use-only-individual" => ("ex:C a owl:Class, owl:NamedIndividual . ex:p a owl:ObjectProperty . ex:A ex:p ex:C .", "ex:C a owl:NamedIndividual . ex:p a owl:ObjectProperty . ex:A ex:p ex:C ."),
            "drop-class-no-consumer" => ("ex:C a owl:Class, owl:NamedIndividual .", "ex:C a owl:NamedIndividual ."),
            _ => (classBoth, "ex:C a owl:NamedIndividual . ex:x a ex:C .")
        };
        // 固定源中保留原文多类型，不用画布投影构造目标。
        var report = await Generate(database, actor, source with { OntologyTurtle = source.OntologyTurtle + pair.Item1 }, source with { OntologyTurtle = source.OntologyTurtle + pair.Item2 });
        Assert.AreEqual(blocked, report.Blockers.Any(item => item.Code == "impact_removed_definition_referenced"), scenario);
        if (blocked)
        {
            // 每个删除阻断既指出目标consumer，也指向原准确声明，而不是另一条rdf:type。
            var blockers = report.Blockers.Where(item => item.Code == "impact_removed_definition_referenced").ToArray();
            Assert.IsTrue(blockers.All(item => item.Evidence.Any(evidence => evidence.Version == report.Diff.To) && item.Evidence.Any(evidence => evidence.Version == report.Diff.From && evidence.Triple?.Predicate == "http://www.w3.org/1999/02/22-rdf-syntax-ns#type")));
        }
        else Assert.IsFalse(report.UnknownCoverage.Any(item => item.Code == "impact_dependency_unresolved" && item.Blocking), scenario);
    }

    /// <summary>真实创建、CAS保存及固定版本报告，不伪造原文hash或成功assessment。</summary>
    private static async Task<ImpactReport> Generate(OntologyDbContext database, ActorContext actor, SourceBundle before, SourceBundle after)
    {
        // 原审计writer加入相同物理事务，任何审计失败会整笔回滚。
        var service = new OntologyService(database, SemanticFixture.Runtime(), new TransactionalAuditWriter(new PooledDbContextFactory<GovernanceDbContext>(new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(Connection()).Options)), TimeProvider.System);
        // 完整范围由服务器资源创建合同固定。
        var created = await service.CreateAsync(actor, new CreateDraftRequest { Name = "Synthetic dependency review regression", Scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = actor.SiteIds }, Sources = before, Command = Command(0) }, default);
        await service.SaveAsync(actor, created.DraftId, new SaveDraftRequest { Name = created.Name, Sources = after, Command = Command(1) }, default);
        return await service.GenerateImpactAsync(actor, new GenerateImpactReportRequest { From = new VersionRef { Kind = VersionRefKind.Draft, Id = created.DraftId, Revision = 1 }, To = new VersionRef { Kind = VersionRefKind.Draft, Id = created.DraftId, Revision = 2 }, BaselineKind = ImpactBaselineKind.VersionPair, AssessmentId = null, Command = Command(2) }, default);
    }

    /// <summary>只读当前真实隔离PG连接，不读取历史runtime。</summary>
    private static string Connection() => Environment.GetEnvironmentVariable("G2_SEM_PG_CONNECTION") ?? throw new AssertInconclusiveException("NOT_RUN: real PG/Jena required");

    /// <summary>本模块专属真实数据上下文。</summary>
    private static OntologyDbContext Database() => new(new DbContextOptionsBuilder<OntologyDbContext>().UseNpgsql(Connection()).Options);

    /// <summary>测试可信主体及完整双厂范围。</summary>
    private static ActorContext Actor() => new() { SubjectId = Guid.NewGuid().ToString("N"), OrganizationId = "org-demo", SiteIds = ["site-a", "site-b"], Roles = ["platform.operator"], TraceId = "test", CorrelationId = "test" };

    /// <summary>显式意图使用独立命令与幂等键。</summary>
    private static CommandContext Command(long revision) => new() { CommandId = Guid.NewGuid().ToString("N"), IdempotencyKey = Guid.NewGuid().ToString("N"), ExpectedRevision = revision, Reason = "Synthetic dependency regression" };
}
