using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.PublishingTests;

/// <summary>G2已有来源有效期元数据兼容，不把M4或OWL-Time模板混入M1。</summary>
[TestClass]
public sealed class G3MetadataTests
{
    /// <summary>既有validToUtc可真实新发布；未知相似谓词仍阻断。</summary>
    [TestMethod]
    [DataRow("validToUtc", true)]
    [DataRow("validUntilUtc", false)]
    public async Task ExistingValidToProvenancePublishesButUnknownMetadataDoesNot(string predicate, bool supported)
    {
        // 当前独占真实PG/Jena/RustFS夹具，不访问历史数据。
        using var fixture = new PublishingFixture();
        // 唯一变化是现有来源assertion的可选终点字段。
        var sources = PublishingFixture.Sources();
        sources = sources with { DataTurtle = sources.DataTurtle + "\n<urn:synthetic:assertion:0> <urn:ontology-platform:vocabulary:" + predicate + "> \"2026-12-31T00:00:00Z\"^^<http://www.w3.org/2001/XMLSchema#dateTime> .\n" };
        if (supported)
        {
            // 先用明确V1原支持策略真实部署/回验，证明不是新增时间模板能力。
            var runtime = fixture.Provider.GetRequiredService<ISemanticRuntime>();
            // 散列由实际权威源解析产生，不手写哈希事实。
            var analysis = await runtime.AnalyzeAsync(sources, 1, default);
            // 本测试独占历史图名，不覆盖任何旧制品。
            var id = Guid.NewGuid().ToString("N");
            // 明确无Semantics的原V1，runtime必须继续原算法。
            var legacy = new ReleaseManifest { SchemaVersion = 1, ReleaseId = id, Hashes = analysis.Hashes, OntologyGraphIri = "urn:ontology-platform:release:" + id + ":ontology", DataGraphIri = "urn:ontology-platform:release:" + id + ":data" };
            await runtime.DeployAsync(legacy, sources, default);
            Assert.IsTrue(await runtime.VerifyAsync(legacy, sources, default), "真实G2原策略必须接受既有可选validToUtc。");
        }
        // 新草稿由生产服务创建且完整scope来自可信主体。
        var draft = await fixture.Ontology.CreateAsync(fixture.Author, new CreateDraftRequest { Name = "Existing G2 provenance metadata", Scope = new ResourceScope { OrganizationId = fixture.Author.OrganizationId, SiteIds = fixture.Author.SiteIds }, Sources = sources, Command = PublishingFixture.Command() }, default);
        // 真实校验产生关联M1评估，不能用V1成功事实跳过新门禁。
        var report = await fixture.Ontology.ValidateAsync(fixture.Author, draft.DraftId, new ValidateDraftRequest { Revision = 1, Hashes = draft.Hashes, Command = PublishingFixture.Command(1) }, default);
        Assert.AreEqual(supported, report.Conforms);
        // 新发布只能使用本次真实M1报告及assessment。
        var proposalRequest = new CreateProposalRequest { Kind = ProposalKind.Publish, DraftId = draft.DraftId, DraftRevision = 1, Hashes = draft.Hashes, ValidationReportId = report.ReportId, Command = PublishingFixture.Command(1) };
        if (supported)
        {
            // 真实异人批准和S3/Jena回验后写V2，不能只检查内存支持布尔。
            var proposal = await fixture.ApproveAsync(await fixture.Service.CreateProposalAsync(fixture.Author, proposalRequest, default));
            // 成功正式发布必须仍携带当前评估绑定。
            var release = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(proposal), default);
            Assert.AreEqual(2, release.Manifest.SchemaVersion);
            Assert.IsNotNull(release.Manifest.Semantics);
        }
        else
        {
            // 相似未知词汇不是普通已登记annotation，不能顺带扩权限。
            var error = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.CreateProposalAsync(fixture.Author, proposalRequest, default));
            Assert.AreEqual(422, error.Status);
            Assert.AreEqual("assessment_not_eligible", error.Code);
        }
    }
}
