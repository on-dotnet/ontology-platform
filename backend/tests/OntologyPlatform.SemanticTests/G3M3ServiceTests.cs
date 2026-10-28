using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SemanticTests;

/// <summary>M3在真实PG/Jena的原子CAS、幂等、审计及治理评估绑定。</summary>
[TestClass]
public sealed class G3M3ServiceTests
{
    /// <summary>双源编辑一次修订/审计、相同请求重放、旧hash拒绝和范围先行。</summary>
    [TestMethod]
    public async Task AtomicVocabularyBatchUsesExistingRevisionAndAuditTransaction()
    {
        // 当前测试仅连接显式隔离PG，不使用任何历史持久资源。
        await using var database = Database();
        // 同scope真实审计写入器复用已批准生产实现。
        var service = Service(database);
        // 两厂可信主体用于测试完整scope拒绝。
        var actor = Actor();
        // 注册Scheme与Concept使初始图符合v3治理。
        var created = await service.CreateAsync(actor, new CreateDraftRequest { Name = "Synthetic M3", Scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = actor.SiteIds }, Sources = Sources(), Command = Command(0) }, default);
        // snapshot由同一服务重新授权并固定修订。
        var snapshot = await service.ReadVocabularyAsync(actor, created.DraftId, default);
        Assert.AreEqual(created.Hashes, snapshot.Hashes);
        Assert.AreEqual(created.DraftId, snapshot.DraftId);
        // 两源完整批次共用同一个command和四源hash。
        var request = new VocabularyEditsRequest { Hashes = snapshot.Hashes, Changes = [new() { SourceId = VocabularyEditSource.Ontology, Edit = new SemanticEdit { SubjectIri = "urn:synthetic:m3:C", PredicateIri = "http://www.w3.org/2000/01/rdf-schema#label", NewObject = new RdfTerm { Kind = RdfTermKind.Literal, Value = "温度类", Language = "zh" } } }, new() { SourceId = VocabularyEditSource.Vocabulary, Edit = new SemanticEdit { SubjectIri = "urn:synthetic:m3:c", PredicateIri = "http://www.w3.org/2004/02/skos/core#prefLabel", NewObject = new RdfTerm { Kind = RdfTermKind.Literal, Value = "温度", Language = "zh" } } }], Command = Command(1) };
        // 只授权第一厂必须在任何解析/写入前失败。
        Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.EditVocabularyAsync(actor with { SiteIds = ["site-a"] }, created.DraftId, request, default))).Status);
        // 原始hash中任一源不同都拒绝。
        Assert.AreEqual("vocabulary_edit_conflict", (await Assert.ThrowsAsync<SemanticOperationException>(() => service.EditVocabularyAsync(actor, created.DraftId, request with { Hashes = request.Hashes with { DataHash = new string('0', 64) } }, default))).Code);
        // 两源更新应当只追加一个不可变修订。
        var saved = await service.EditVocabularyAsync(actor, created.DraftId, request, default);
        Assert.AreEqual(2L, saved.Revision);
        Assert.AreEqual(2, await database.Revisions.CountAsync(row => row.DraftId == created.DraftId));
        Assert.AreEqual(created.Sources.ShapesTurtle, saved.Sources.ShapesTurtle);
        Assert.AreEqual(created.Sources.DataTurtle, saved.Sources.DataTurtle);
        Assert.AreEqual(JsonSerializer.Serialize(saved), JsonSerializer.Serialize(await service.EditVocabularyAsync(actor, created.DraftId, request, default)));
        Assert.AreEqual("idempotency_conflict", (await Assert.ThrowsAsync<SemanticOperationException>(() => service.EditVocabularyAsync(actor, created.DraftId, request with { Hashes = saved.Hashes }, default))).Code);
        // 创建和一次batch各一条事务回执及审计，重放不增加事实。
        Assert.AreEqual(2, await database.Commands.CountAsync(row => row.SubjectId == actor.SubjectId));
        // 新上下文证明实际PG审计，不依赖EF跟踪缓存。
        await using var governance = new GovernanceDbContext(new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(Connection()).Options);
        Assert.AreEqual(2, await governance.AuditRecords.CountAsync(row => row.Actor == actor.SubjectId));
    }

    /// <summary>M3诊断直接进入GOVERNANCE，真实SHACL仍PASS且OWL保持NOT_RUN。</summary>
    [TestMethod]
    public async Task GovernanceIsIndependentOfRealShaclReport()
    {
        // 真实PG保存两种不同治理结论，任何warning都不得新发布。
        await using var database = Database();
        // 生产服务的M3评估不能通过旧ValidationIssue链丢失精确代码。
        var service = Service(database);
        // 当前可信双厂身份。
        var actor = Actor();
        foreach (var label in new[] { "\"甲\"@zh, \"乙\"@ZH", "\"a\"@fr" })
        {
            // 普通源码保存允许保留冲突图，由assessment阻断发布。
            var sources = Sources() with { VocabularyTurtle = Sources().VocabularyTurtle + " <urn:synthetic:m3:c> <http://www.w3.org/2004/02/skos/core#prefLabel> " + label + " ." };
            // 创建时不清洗未知/冲突RDF，保留准确原文。
            var created = await service.CreateAsync(actor, new CreateDraftRequest { Name = "Synthetic conflict", Scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = actor.SiteIds }, Sources = sources, Command = Command(0) }, default);
            // 真实执行SHACL后追加治理，保持五阶段和预算。
            var assessment = await service.AssessAsync(actor, created.DraftId, new ValidateDraftRequest { Revision = 1, Hashes = created.Hashes, Command = Command(1) }, default);
            Assert.IsFalse(assessment.PublishEligible);
            Assert.AreEqual(5, assessment.Stages.Length);
            Assert.AreEqual(AssessmentStageStatus.Pass, assessment.Stages.Single(stage => stage.Name == "SHACL_CORE").Status);
            Assert.AreEqual(AssessmentStageStatus.NotRun, assessment.Stages.Single(stage => stage.Name == "OWL_REASONING").Status);
            Assert.AreEqual(label.Contains("@fr", StringComparison.Ordinal) ? AssessmentStageStatus.Indeterminate : AssessmentStageStatus.Fail, assessment.Stages.Single(stage => stage.Name == "GOVERNANCE").Status);
            Assert.IsTrue(assessment.Diagnostics.Any(item => item.Diagnostic.Code is "skos_pref_label_conflict" or "language_policy_unknown" && item.SourceHash == created.Hashes.VocabularyHash));
        }
    }

    /// <summary>本轮小型合法Synthetic图，不从行业符号推断身份。</summary>
    private static SourceBundle Sources() => new() { OntologyTurtle = "<urn:synthetic:m3:C> a <http://www.w3.org/2002/07/owl#Class> .", VocabularyTurtle = "@prefix skos: <http://www.w3.org/2004/02/skos/core#> . <urn:synthetic:m3:s> a skos:ConceptScheme . <urn:synthetic:m3:c> a skos:Concept ; skos:inScheme <urn:synthetic:m3:s> ." };

    /// <summary>仅允许脚本注入的临时PG连接。</summary>
    private static string Connection()
    {
        // 不读取机器历史runtime或凭证文件。
        var connection = Environment.GetEnvironmentVariable("G2_SEM_PG_CONNECTION");
        if (connection is null) Assert.Inconclusive("NOT_RUN: 需要隔离PG/Jena测试入口。");
        return connection;
    }

    /// <summary>Ontology专有schema上下文。</summary>
    private static OntologyDbContext Database() => new(new DbContextOptionsBuilder<OntologyDbContext>().UseNpgsql(Connection()).Options);

    /// <summary>真实Ontology及Governance生产服务。</summary>
    private static OntologyService Service(OntologyDbContext database) => new(database, SemanticFixture.Runtime(), new TransactionalAuditWriter(new PooledDbContextFactory<GovernanceDbContext>(new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(Connection()).Options)), TimeProvider.System);

    /// <summary>独立主体及完整可信双厂scope。</summary>
    private static ActorContext Actor() => new() { SubjectId = Guid.NewGuid().ToString("N"), OrganizationId = "org-demo", SiteIds = ["site-a", "site-b"], Roles = ["platform.operator"], TraceId = Guid.NewGuid().ToString("N"), CorrelationId = Guid.NewGuid().ToString("N") };

    /// <summary>唯一命令绑定精确期望修订及审计理由。</summary>
    private static CommandContext Command(long revision) => new() { CommandId = Guid.NewGuid().ToString("N"), IdempotencyKey = Guid.NewGuid().ToString("N"), ExpectedRevision = revision, Reason = "Synthetic M3事务验证" };
}
