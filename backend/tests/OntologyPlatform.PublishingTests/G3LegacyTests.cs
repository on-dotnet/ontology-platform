using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Publishing;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.PublishingTests;

/// <summary>独立历史V1夹具真实保存对象/图，验证读取和回滚而不伪造新发布资格。</summary>
[TestClass]
public sealed class G3LegacyTests
{
    /// <summary>历史V1原字节可读回滚，新PUBLISH只写V2且旧提案不能重新激活。</summary>
    [TestMethod]
    public async Task LegacyV1ReadsAndRollsBackWithoutCurrentDraftAssessment()
    {
        // 本轮独占真实PG/Jena/S3，不读历史私有runtime。
        using var fixture = new PublishingFixture();
        // 历史夹具明确构造无Semantics的V1并写真实对象、图与独立表。
        var legacy = await SeedLegacyAsync(fixture);
        // Catalog回读真实V1，并校验原始manifest对象hash。
        var read = await fixture.Catalog.ReadAsync(fixture.Author, legacy.ReleaseId, default);
        Assert.AreEqual(1, read.Manifest.SchemaVersion);
        Assert.IsNull(read.Manifest.Semantics);
        Assert.AreEqual(legacy.ManifestHash, read.ManifestHash);
        // 旧正式版本作为基线继承服务器资产身份，创建当前草稿。
        var draft = await fixture.Ontology.CreateAsync(fixture.Author, new CreateDraftRequest { Name = "G3 clone from true V1", Scope = read.Manifest.Scope, Sources = PublishingFixture.Sources(), BaseReleaseId = legacy.ReleaseId, Command = PublishingFixture.Command() }, default);
        // 新报告自动关联当前M1评估，再取得新批准。
        var proposal = await fixture.ApproveAsync(await fixture.ProposalForAsync(draft));
        // 新V2与旧V1共存，活动CAS依照历史版本revision1。
        var current = await fixture.Service.ActivateAsync(fixture.Author, new ActivateReleaseRequest { ProposalId = proposal.ProposalId, ExpectedActiveReleaseId = legacy.ReleaseId, ExpectedActivationRevision = 1, Command = PublishingFixture.Command(proposal.Revision) }, default);
        Assert.AreEqual(2, current.Manifest.SchemaVersion);
        Assert.IsNotNull(current.Manifest.Semantics);
        // 输出的只是本次真实发布的公开合成manifest字节，供独立兼容二进制读回。
        var output = Environment.GetEnvironmentVariable("G3_M1_MANIFEST_OUTPUT");
        if (output is not null)
        {
            Directory.CreateDirectory(output);
            File.WriteAllText(Path.Combine(output, "real-v1-manifest.json"), legacy.ManifestJson);
            File.WriteAllText(Path.Combine(output, "real-v2-manifest.json"), (await fixture.Database.Releases.AsNoTracking().SingleAsync(row => row.ReleaseId == current.ReleaseId)).ManifestJson);
        }
        // 当前草稿与assessment故意推进/过期，回滚不得锁当前草稿或补新评估。
        await fixture.Ontology.SaveAsync(fixture.Author, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = draft.Sources with { OntologyTurtle = draft.Sources.OntologyTurtle + "\n# current draft advanced" }, Command = PublishingFixture.Command(1) }, default);
        // 仅使当前持久评估过期，不能偏移S3签名使用的真实UTC。
        using (var invalidScope = fixture.Provider.CreateScope())
        {
            // 数据只在当前隔离PG内变异，模拟已过期的评估事实。
            var ontology = invalidScope.ServiceProvider.GetRequiredService<OntologyDbContext>();
            // 当前正式V2对应的评估现在已超24h，回滚V1不应读取它。
            var record = await ontology.Assessments.SingleAsync(row => row.AssessmentId == current.Manifest.Semantics!.AssessmentId);
            // 保持自身hash正确，真实测试有效期失效而非单纯hash损坏。
            var assessment = JsonSerializer.Deserialize<SemanticAssessment>(record.AssessmentJson)!;
            assessment = assessment with { AssessedAtUtc = assessment.AssessedAtUtc.AddHours(-25), ExpiresAtUtc = assessment.ExpiresAtUtc.AddHours(-25) };
            assessment = assessment with { AssessmentHash = SemanticProfile.AssessmentHash(assessment) };
            record.AssessmentJson = JsonSerializer.Serialize(assessment);
            await ontology.SaveChangesAsync();
        }
        // 全新回滚批准仍遵守当前权限、异人和24h期限。
        var rollback = await fixture.ApproveAsync(await fixture.Service.CreateProposalAsync(fixture.Author, new CreateProposalRequest { Kind = ProposalKind.Rollback, TargetReleaseId = legacy.ReleaseId, TargetManifestHash = legacy.ManifestHash, Command = PublishingFixture.Command() }, default));
        // 旧V1源/图原始支持边界再次真实核验，成功CAS回滚。
        var restored = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(rollback, current), default);
        Assert.AreEqual(legacy.ReleaseId, restored.ReleaseId);
        Assert.AreEqual(legacy.ManifestHash, restored.ManifestHash);
        Assert.AreEqual(1, restored.Manifest.SchemaVersion);
        Assert.AreEqual(3, restored.ActivationRevision);
        Assert.AreEqual(legacy.ManifestJson, (await fixture.Database.Releases.AsNoTracking().SingleAsync(row => row.ReleaseId == legacy.ReleaseId)).ManifestJson);
        // 历史PUBLISH提案没有assessment，不得当作新的激活授权。
        var stale = JsonSerializer.Deserialize<ReleaseProposal>((await fixture.Database.Proposals.AsNoTracking().SingleAsync(row => row.ProposalId == legacy.ProposalId)).ProposalJson)!;
        Assert.AreEqual(409, (await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(stale, restored), default))).Status);
    }

    /// <summary>旧V1对象不可用时回滚必须失败且当前active保持不变。</summary>
    [TestMethod]
    public async Task LegacyV1CorruptArtifactRollbackFailsClosed()
    {
        // 历史夹具也必须实际部署，不用预制验证成功。
        using var fixture = new PublishingFixture();
        // 原V1版本真实正式存在。
        var legacy = await SeedLegacyAsync(fixture);
        // 故障发生前允许真实创建与独立审核回滚提案。
        var proposal = await fixture.ApproveAsync(await fixture.Service.CreateProposalAsync(fixture.Author, new CreateProposalRequest { Kind = ProposalKind.Rollback, TargetReleaseId = legacy.ReleaseId, TargetManifestHash = legacy.ManifestHash, Command = PublishingFixture.Command() }, default));
        fixture.Gate = (message, _) => message.Method == HttpMethod.Get && message.RequestUri!.AbsolutePath.Contains(legacy.ReleaseId, StringComparison.Ordinal) ? throw new HttpRequestException("isolated legacy source unavailable") : Task.CompletedTask;
        // 外部回验失败发生在最终事务前，禁止半更新。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.ActivateAsync(fixture.Author, new ActivateReleaseRequest { ProposalId = proposal.ProposalId, ExpectedActiveReleaseId = legacy.ReleaseId, ExpectedActivationRevision = 1, Command = PublishingFixture.Command(proposal.Revision) }, default));
        Assert.AreEqual(503, error.Status);
        Assert.AreEqual(legacy.ReleaseId, (await fixture.Database.ActiveReleases.AsNoTracking().SingleAsync(row => row.AssetId == legacy.AssetId)).ReleaseId);
        Assert.AreEqual(1L, (await fixture.Database.ActiveReleases.AsNoTracking().SingleAsync(row => row.AssetId == legacy.AssetId)).Revision);
    }

    /// <summary>仅测试导入已固定的历史事实；生产新发布没有这条写入入口。</summary>
    private static async Task<ReleaseRecord> SeedLegacyAsync(PublishingFixture fixture)
    {
        // 使用真实G2合成四源，并由当前真实RIOT计算原始源hash。
        var sources = PublishingFixture.Sources();
        // 正式运行时仍来自唯一生产DI组合。
        var runtime = fixture.Provider.GetRequiredService<ISemanticRuntime>();
        // 必须真实解析，不能手写成功报告或源hash。
        var analysis = await runtime.AnalyzeAsync(sources, 1, default);
        // 不可猜的隔离历史版本身份。
        var id = Guid.NewGuid().ToString("N");
        // 单独历史资产供新草稿继承。
        var asset = Guid.NewGuid().ToString("N");
        // 完整scope保持双厂授权，不取第一厂。
        var scope = new ResourceScope { OrganizationId = fixture.Author.OrganizationId, SiteIds = fixture.Author.SiteIds };
        // 服务器固定图名与源散列快照。
        var snapshot = new AssetVersionSnapshot { ReleaseId = id, OntologyGraphIri = "urn:ontology-platform:release:" + id + ":ontology", DataGraphIri = "urn:ontology-platform:release:" + id + ":data", OntologyHash = analysis.Hashes.OntologyHash, ShapesHash = analysis.Hashes.ShapesHash, VocabularyHash = analysis.Hashes.VocabularyHash, DataHash = analysis.Hashes.DataHash };
        // 原G2固定源对象顺序，不向历史manifest补Semantics。
        var contents = sources.VocabularyTurtle is null ? new[] { sources.OntologyTurtle, sources.ShapesTurtle, sources.DataTurtle } : new[] { sources.OntologyTurtle, sources.ShapesTurtle, sources.VocabularyTurtle, sources.DataTurtle };
        // 所有对象均真实写入当前隔离S3并读回验证。
        var objects = new List<ArtifactObject>();
        for (var index = 0; index < contents.Length; index++) objects.Add(await fixture.Artifacts.PutImmutableAsync("releases/" + id + "/source-" + index + "-" + Hash(contents[index]) + ".ttl", Encoding.UTF8.GetBytes(contents[index]), "text/turtle", default));
        // 无评估字段的精确V1，由严格生成DTO验证版本分支。
        var manifest = new ReleaseManifest { SchemaVersion = 1, ReleaseId = id, AssetId = asset, Scope = scope, DraftId = "legacy-" + id, Revision = 1, Hashes = analysis.Hashes, Snapshot = snapshot, OntologyGraphIri = snapshot.OntologyGraphIri, DataGraphIri = snapshot.DataGraphIri, ArtifactObjects = objects.ToArray(), CreatedAtUtc = DateTimeOffset.UtcNow };
        // 原始manifest序列化一次，后续hash永远针对保存的原始字节。
        var json = JsonSerializer.Serialize(manifest);
        // 清单对象独立，不创建自引用hash。
        var manifestObject = await fixture.Artifacts.PutImmutableAsync("releases/" + id + "/manifest-" + Hash(json) + ".json", Encoding.UTF8.GetBytes(json), "application/json", default);
        await runtime.DeployAsync(manifest, sources, default);
        Assert.IsTrue(await runtime.VerifyAsync(manifest, sources, default));
        // 历史提案保留没有Semantics的原形，标已消费防止重用。
        var proposal = new ReleaseProposal { ProposalId = Guid.NewGuid().ToString("N"), Kind = ProposalKind.Publish, AssetId = asset, Scope = scope, DraftId = manifest.DraftId, DraftRevision = 1, Hashes = analysis.Hashes, ValidationReportId = "legacy-report", SubmittedBy = fixture.Author.SubjectId, SubmittedAtUtc = DateTimeOffset.UtcNow, ExpiresAtUtc = DateTimeOffset.UtcNow.AddHours(24), Status = ProposalStatus.Approved, Revision = 2 };
        fixture.Database.Proposals.Add(new ProposalRecord { ProposalId = proposal.ProposalId, AssetId = asset, OrganizationId = scope.OrganizationId, SiteIds = scope.SiteIds, Revision = 2, Activated = true, ProposalJson = JsonSerializer.Serialize(proposal) });
        // 历史正式记录只为本轮兼容验收，不修改外部旧制品。
        var row = new ReleaseRecord { ReleaseId = id, ProposalId = proposal.ProposalId, AssetId = asset, OrganizationId = scope.OrganizationId, SiteIds = scope.SiteIds, SourcesJson = JsonSerializer.Serialize(sources), ManifestJson = json, ManifestHash = Hash(json), ManifestObjectJson = JsonSerializer.Serialize(manifestObject), State = "ACTIVE", Published = true };
        fixture.Database.Releases.Add(row);
        fixture.Database.ActiveReleases.Add(new ActiveReleaseRecord { AssetId = asset, OrganizationId = scope.OrganizationId, SiteIds = scope.SiteIds, ReleaseId = id, Revision = 1 });
        await fixture.Database.SaveChangesAsync();
        fixture.Database.ChangeTracker.Clear();
        return row;
    }

    /// <summary>仅计算精确原始UTF8字节hash，不规范化文本。</summary>
    private static string Hash(string value) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
}
