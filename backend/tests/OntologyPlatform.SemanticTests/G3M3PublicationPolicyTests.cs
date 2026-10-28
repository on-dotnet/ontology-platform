using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SemanticTests;

/// <summary>直接运行时入口同样执行精确profile治理，防止绕过草稿assessment。</summary>
[TestClass]
public sealed class G3M3PublicationPolicyTests
{
    /// <summary>缺陷源即使拥有真实hash和自洽manifest，也不能通过v3部署、回验或正式读取。</summary>
    [TestMethod]
    [DataRow("skos")]
    [DataRow("precision")]
    [DataRow("dimension")]
    public async Task DirectV3EntrypointsCannotBypassGovernance(string scenario)
    {
        // 固定缺陷通过合法RDF保留；不是拿语法错误冒充治理拒绝。
        var sources = scenario == "skos" ? SkosSources() : G3M3UnitTests.Sources() with { OntologyTurtle = "<urn:synthetic:m3:C> a <http://www.w3.org/2002/07/owl#Class> .", DataTurtle = "<urn:synthetic:m3:i> a <urn:synthetic:m3:C> ." };
        if (scenario == "precision") sources = sources with { VocabularyTurtle = sources.VocabularyTurtle!.Replace("declared-exact", "UNKNOWN", StringComparison.Ordinal) };
        if (scenario == "dimension") sources = sources with { VocabularyTurtle = sources.VocabularyTurtle!.Replace("p:nominalUnit ex:K-v1", "p:nominalUnit ex:MPa-v1", StringComparison.Ordinal) };
        // 真实生产运行时为每个测试建立独立图和执行预算。
        var runtime = SemanticFixture.Runtime();
        // 哈希从真实四源解析获得，排除清单错版导致的假阳性。
        var analysis = await runtime.AnalyzeAsync(sources, 1, default);
        // 自洽v3清单不会因为缺失snapshot提前失败。
        var manifest = Manifest(analysis.Hashes, SemanticProfile.Current());
        Assert.AreEqual("publication_unsupported", (await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.DeployAsync(manifest, sources, default))).Code);
        Assert.IsFalse(await runtime.VerifyAsync(manifest, sources, default));
        Assert.AreEqual("published_source_unsupported", (await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ReadVerifiedPublishedAsync(manifest, sources, default))).Code);
    }

    /// <summary>v2历史策略不追溯追加SKOS语言政策；v3读取同源必须失败。</summary>
    [TestMethod]
    public async Task ExactLegacyM2ProfileKeepsHistoricalPolicy()
    {
        // 无语言标签是v3治理缺陷，但属于v2明确已支持原始SKOS事实。
        var sources = SkosSources();
        // 真实Jena部署并读回，不能仅比较内存profile工厂。
        var runtime = SemanticFixture.Runtime();
        // 历史hash使用当前源真实RIOT得到而不捏造。
        var analysis = await runtime.AnalyzeAsync(sources, 1, default);
        // 旧v2精确注册profile，不把Current改名冒充历史。
        var manifest = Manifest(analysis.Hashes, SemanticProfile.LegacyM2());
        await runtime.DeployAsync(manifest, sources, default);
        Assert.IsTrue(await runtime.VerifyAsync(manifest, sources, default));
        Assert.IsNotEmpty((await runtime.ReadVerifiedPublishedAsync(manifest, sources, default)).OntologyTriples);
        // 只改profile而保持源/hash/正式图，证明区别确为M3政策。
        var current = SemanticProfile.Current();
        // 原历史图和清单副本保持不变，v3仅作为调用参数测试。
        var upgraded = manifest with { Semantics = manifest.Semantics! with { ProfileVersion = current.Version, ProfileHash = current.Hash } };
        Assert.IsFalse(await runtime.VerifyAsync(upgraded, sources, default));
        Assert.AreEqual("published_source_unsupported", (await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ReadVerifiedPublishedAsync(upgraded, sources, default))).Code);
        Assert.IsTrue(await runtime.VerifyAsync(manifest, sources, default));
    }

    /// <summary>治理缺陷是无语言标签，不是缺少图或不支持的RDF语法。</summary>
    private static SourceBundle SkosSources() => new() { OntologyTurtle = "<urn:synthetic:m3:C> a <http://www.w3.org/2002/07/owl#Class> .", DataTurtle = "<urn:synthetic:m3:i> a <urn:synthetic:m3:C> .", VocabularyTurtle = "@prefix skos: <http://www.w3.org/2004/02/skos/core#> . <urn:synthetic:m3:s> a skos:ConceptScheme . <urn:synthetic:m3:c> a skos:Concept ; skos:inScheme <urn:synthetic:m3:s> ; skos:prefLabel \"原始历史词汇\" ." };

    /// <summary>构造隔离测试清单；实际源/hash/profile均由生产运行时提供。</summary>
    private static ReleaseManifest Manifest(SourceHashes hashes, SemanticSupportProfile profile)
    {
        // 每个测试图名独立，绝不覆盖旧正式数据。
        var id = Guid.NewGuid().ToString("N");
        // 快照字段精确绑定四源身份，正式消费会重新逐项核对。
        var snapshot = new AssetVersionSnapshot { ReleaseId = id, OntologyGraphIri = "urn:ontology-platform:release:" + id + ":ontology", DataGraphIri = "urn:ontology-platform:release:" + id + ":data", OntologyHash = hashes.OntologyHash, ShapesHash = hashes.ShapesHash, VocabularyHash = hashes.VocabularyHash, DataHash = hashes.DataHash };
        return new ReleaseManifest { SchemaVersion = 2, ReleaseId = id, AssetId = "synthetic-policy", DraftId = "synthetic-policy", Revision = 1, Scope = new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a", "site-b"] }, Hashes = hashes, Snapshot = snapshot, OntologyGraphIri = snapshot.OntologyGraphIri, DataGraphIri = snapshot.DataGraphIri, Semantics = new PublicationSemantics { ProfileVersion = profile.Version, ProfileHash = profile.Hash, AssessmentId = "synthetic-runtime-policy", AssessmentHash = new string('a', 64) }, CreatedAtUtc = DateTimeOffset.UtcNow };
    }
}
