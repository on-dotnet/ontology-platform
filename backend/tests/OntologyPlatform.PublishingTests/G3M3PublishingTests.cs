using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology;
using OntologyPlatform.Modules.Publishing;

namespace OntologyPlatform.PublishingTests;

/// <summary>M3真实PG/Jena/RustFS发布、固定词汇消费及精确v2历史回滚。</summary>
[TestClass]
public sealed class G3M3PublishingTests
{
    /// <summary>合法Synthetic单位经真实异人审批发布后，只返回固定release而不是后续草稿。</summary>
    [TestMethod]
    public async Task RealM3VocabularyReleaseStaysBoundToImmutableSources()
    {
        // 当前脚本创建的独占三依赖，不接触历史开发资源。
        using var fixture = new PublishingFixture();
        // 单位合成文档保留完整量纲、版本、精度与出处。
        var sources = UnitSources();
        // 草稿scope必须完整双厂，后续发布继承同一个资产。
        var draft = await fixture.Ontology.CreateAsync(fixture.Author, new CreateDraftRequest { Name = "Synthetic M3 release", Scope = new ResourceScope { OrganizationId = fixture.Author.OrganizationId, SiteIds = fixture.Author.SiteIds }, Sources = sources, Command = PublishingFixture.Command() }, default);
        // 真正SHACL/治理评估、异人批准及对象存储和正式图回验。
        var proposal = await fixture.ApproveAsync(await fixture.ProposalForAsync(draft));
        // 初次活动CAS要求空活动版本。
        var release = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(proposal), default);
        Assert.AreEqual("4", release.Manifest.Semantics!.ProfileVersion);
        // 正式词汇仍由同生产服务组合实现，不能另建假Catalog。
        var vocabulary = (IG3VocabularyService)fixture.Ontology;
        // 实际消费路径重新校验对象和Jena同批图。
        var snapshot = await vocabulary.ReadReleaseVocabularyAsync(fixture.Author, release.ReleaseId, default);
        Assert.AreEqual(release.ReleaseId, snapshot.ReleaseId);
        Assert.AreEqual(release.ManifestHash, snapshot.ManifestHash);
        Assert.AreEqual(release.Manifest.Revision, snapshot.Revision);
        Assert.AreEqual(release.Manifest.Hashes, snapshot.Hashes);
        Assert.AreEqual(release.Manifest.Semantics.ProfileHash, snapshot.ProfileHash);
        Assert.IsEmpty(snapshot.Diagnostics);
        // 当前草稿追加冲突不能污染不可变正式词汇。
        await fixture.Ontology.SaveAsync(fixture.Author, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = sources with { VocabularyTurtle = sources.VocabularyTurtle + "\n<urn:synthetic:m3:K-v1> <urn:ontology-platform:semantics:symbol> \"changed-draft\" ." }, Command = PublishingFixture.Command(draft.Revision) }, default);
        // 第二次正式消费保持相同固定修订和源hash。
        var read = await vocabulary.ReadReleaseVocabularyAsync(fixture.Author, release.ReleaseId, default);
        Assert.AreEqual(snapshot.Hashes, read.Hashes);
        Assert.AreEqual(snapshot.Revision, read.Revision);
        Assert.IsFalse(read.Triples.Any(item => item.Triple.Object.Value == "changed-draft"));
        // 重新授权必须在任何对象或Jena访问前完成。
        var calls = 0;
        fixture.Gate = (_, _) => { Interlocked.Increment(ref calls); return Task.CompletedTask; };
        Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => vocabulary.ReadReleaseVocabularyAsync(fixture.Author with { SiteIds = ["site-a"] }, release.ReleaseId, default))).Status);
        Assert.AreEqual(0, calls);
    }

    /// <summary>SHACL真实conforms仍不能越过单位未知或错配治理产生提案。</summary>
    [TestMethod]
    [DataRow("precision")]
    [DataRow("dimension")]
    public async Task RealProposalRejectsUnitGovernanceEvenWhenShaclConforms(string scenario)
    {
        // 三依赖全部由当前脚本随机命名并真实运行。
        using var fixture = new PublishingFixture();
        // 源码保存保留问题，由治理assessment明确阻断。
        var sources = UnitSources();
        sources = sources with { VocabularyTurtle = scenario == "precision" ? sources.VocabularyTurtle!.Replace("declared-exact", "UNKNOWN", StringComparison.Ordinal) : sources.VocabularyTurtle!.Replace("p:nominalUnit ex:K-v1", "p:nominalUnit ex:MPa-v1", StringComparison.Ordinal) };
        // 本测试独立资产不会与其他负例互相影响活动指针。
        var draft = await fixture.Ontology.CreateAsync(fixture.Author, new CreateDraftRequest { Name = "Synthetic governance refusal", Scope = new ResourceScope { OrganizationId = fixture.Author.OrganizationId, SiteIds = fixture.Author.SiteIds }, Sources = sources, Command = PublishingFixture.Command() }, default);
        // SHACL原始报告与M3治理是分开的事实，前者不伪装后者失败。
        var report = await fixture.Ontology.ValidateAsync(fixture.Author, draft.DraftId, new ValidateDraftRequest { Revision = 1, Hashes = draft.Hashes, Command = PublishingFixture.Command(1) }, default);
        Assert.IsTrue(report.Conforms);
        // 即使传入真实成功SHACL报告，也必须由持久assessment阻断。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.CreateProposalAsync(fixture.Author, new CreateProposalRequest { Kind = ProposalKind.Publish, DraftId = draft.DraftId, DraftRevision = 1, Hashes = draft.Hashes, ValidationReportId = report.ReportId, Command = PublishingFixture.Command(1) }, default));
        Assert.AreEqual("assessment_not_eligible", error.Code);
        Assert.IsFalse(await fixture.Database.Releases.AnyAsync(row => row.AssetId == draft.AssetId));
    }

    /// <summary>精确旧v2清单对象可读及异人审批回滚；旧v2评估不能作为新发布资格。</summary>
    [TestMethod]
    public async Task ExactLegacyV2ReleaseReadsAndRollsBackWithoutRepublishingOldAssessment()
    {
        // 历史夹具仅导入本次隔离服务，不改真实旧制品。
        using var fixture = new PublishingFixture();
        // 真实报告、S3对象、Jena正式图和PG目录均须自洽。
        var legacy = await SeedLegacyM2Async(fixture);
        // Catalog检查原始清单字节和正式图而不是仅查PG行。
        var read = await fixture.Catalog.ReadAsync(fixture.Author, legacy.ReleaseId, default);
        Assert.AreEqual("2", read.Manifest.Semantics!.ProfileVersion);
        Assert.AreEqual(SemanticProfile.LegacyM2().Hash, read.Manifest.Semantics.ProfileHash);
        // 原始对象严格读回，验证后续回滚不会重序列化。
        var manifestObject = JsonSerializer.Deserialize<ArtifactObject>(legacy.ManifestObjectJson)!;
        CollectionAssert.AreEqual(Encoding.UTF8.GetBytes(legacy.ManifestJson), await fixture.Artifacts.ReadVerifiedAsync(manifestObject, default));
        // 正式词汇也携带旧profile，绝不填当前v3。
        var vocabulary = (IG3VocabularyService)fixture.Ontology;
        Assert.AreEqual("2", (await vocabulary.ReadReleaseVocabularyAsync(fixture.Author, legacy.ReleaseId, default)).ProfileVersion);
        using (var checkScope = fixture.Provider.CreateScope())
        {
            // 测试读取旧持久评估报告引用，生产仍走正式新提案服务。
            var ontology = checkScope.ServiceProvider.GetRequiredService<OntologyDbContext>();
            // 旧评估hash自身正确，拒绝必须来自版本绑定而非篡改。
            var assessment = JsonSerializer.Deserialize<SemanticAssessment>((await ontology.Assessments.AsNoTracking().SingleAsync(row => row.AssessmentId == read.Manifest.Semantics.AssessmentId)).AssessmentJson)!;
            Assert.AreEqual(SemanticProfile.AssessmentHash(assessment), assessment.AssessmentHash);
            Assert.AreEqual("assessment_binding_conflict", (await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.CreateProposalAsync(fixture.Author, new CreateProposalRequest { Kind = ProposalKind.Publish, DraftId = read.Manifest.DraftId, DraftRevision = read.Manifest.Revision, Hashes = read.Manifest.Hashes, ValidationReportId = assessment.ValidationReportId, Command = PublishingFixture.Command(read.Manifest.Revision) }, default))).Code);
        }
        // 新草稿从旧release继承资产，取得当前v3新评估与独立批准。
        var draft = await fixture.Ontology.CreateAsync(fixture.Author, new CreateDraftRequest { Name = "M3 clone from exact M2", Scope = read.Manifest.Scope, Sources = LegacySources(), BaseReleaseId = legacy.ReleaseId, Command = PublishingFixture.Command() }, default);
        // 后续发布CAS必须明确旧活动指针及revision。
        var proposal = await fixture.ApproveAsync(await fixture.ProposalForAsync(draft));
        // 新发布精确使用v3，与旧v2正式版共存。
        var current = await fixture.Service.ActivateAsync(fixture.Author, new ActivateReleaseRequest { ProposalId = proposal.ProposalId, ExpectedActiveReleaseId = legacy.ReleaseId, ExpectedActivationRevision = 1, Command = PublishingFixture.Command(proposal.Revision) }, default);
        Assert.AreEqual("4", current.Manifest.Semantics!.ProfileVersion);
        // 回滚仍要求新提案、当前权限、独立批准与活动CAS，不读取旧草稿资格。
        var rollback = await fixture.ApproveAsync(await fixture.Service.CreateProposalAsync(fixture.Author, new CreateProposalRequest { Kind = ProposalKind.Rollback, TargetReleaseId = legacy.ReleaseId, TargetManifestHash = legacy.ManifestHash, Command = PublishingFixture.Command() }, default));
        // 真正回验旧对象和图后更新活动指针。
        var restored = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(rollback, current), default);
        Assert.AreEqual(legacy.ReleaseId, restored.ReleaseId);
        Assert.AreEqual(legacy.ManifestHash, restored.ManifestHash);
        Assert.AreEqual("2", restored.Manifest.Semantics!.ProfileVersion);
        Assert.AreEqual(3L, restored.ActivationRevision);
        Assert.AreEqual(legacy.ManifestJson, (await fixture.Database.Releases.AsNoTracking().SingleAsync(row => row.ReleaseId == legacy.ReleaseId)).ManifestJson);
    }

    /// <summary>加载已提交单位fixture，同时提供非空命名类及事实以真实回验两张正式图。</summary>
    private static SourceBundle UnitSources()
    {
        // 脚本明确注入的公开样例根，不读取私有runtime。
        var root = Environment.GetEnvironmentVariable("G2_PUB_SAMPLES") ?? throw new InvalidOperationException("NOT_RUN: 缺少明确隔离样例根。");
        return LegacySources() with { VocabularyTurtle = File.ReadAllText(Path.Combine(root, "..", "g3-m3", "units.ttl")) };
    }

    /// <summary>旧v2支持的最小四源，不依赖后续M3单位能力。</summary>
    private static SourceBundle LegacySources() => new() { OntologyTurtle = "<urn:synthetic:m3:C> a <http://www.w3.org/2002/07/owl#Class> .", DataTurtle = "<urn:synthetic:m3:i> a <urn:synthetic:m3:C> .", VocabularyTurtle = "<urn:synthetic:m3:v> <http://www.w3.org/2000/01/rdf-schema#label> \"历史合成来源\"@zh ." };

    /// <summary>仅测试导入已固定的历史事实；生产新发布没有这条写入入口。</summary>
    /// <param name="fixture">本次隔离的真实PG、Jena及RustFS夹具。</param>
    /// <param name="withM2Profile">明确导入带真实M2评估的V2历史，否则保持原V1默认行为。</param>
    /// <returns>已写入真实对象、正式图及PG目录的历史发布记录。</returns>
    private static async Task<ReleaseRecord> SeedLegacyM2Async(PublishingFixture fixture, bool withM2Profile = true)
    {
        // 使用真实G2合成四源，并由当前真实RIOT计算原始源hash。
        var sources = LegacySources();
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
        // V1默认没有评估和语义字段，保持原测试及原始manifest输出路径不变。
        PublicationSemantics? semantics = null;
        // V1旧草稿标识默认值不得被新测试分支改写。
        var draftId = "legacy-" + id;
        // V1默认报告引用保持历史原形。
        var reportId = "legacy-report";
        if (withM2Profile)
        {
            // 先通过真实生产用例生成草稿、RIOT/SHACL报告、阶段及资格事实。
            var draft = await fixture.Ontology.CreateAsync(fixture.Author, new CreateDraftRequest { Name = "Isolated historical M2 assessment fixture", Scope = scope, Sources = sources, Command = PublishingFixture.Command() }, default);
            // 当前和历史策略的asserted-only发布规则相同，仅测试导入时登记原M2策略身份。
            var assessed = await ((IG3OntologyService)fixture.Ontology).AssessAsync(fixture.Author, draft.DraftId, new ValidateDraftRequest { Revision = draft.Revision, Hashes = draft.Hashes, Command = PublishingFixture.Command(draft.Revision) }, default);
            Assert.IsTrue(assessed.PublishEligible);
            Assert.AreEqual(analysis.Hashes, assessed.Hashes);
            // 历史工厂保留精确golden策略，真实阶段、预算、诊断和资格全部沿用报告。
            var profile = SemanticProfile.LegacyM2();
            // 仅隔离历史事实的策略身份变化，必须重新计算自身完整hash。
            var historical = assessed with { ProfileVersion = profile.Version, ProfileHash = profile.Hash, AssessmentHash = "" };
            historical = historical with { AssessmentHash = SemanticProfile.AssessmentHash(historical) };
            using (var importScope = fixture.Provider.CreateScope())
            {
                // 该直接表写只导入本次测试的历史事实，生产无此入口。
                var ontology = importScope.ServiceProvider.GetRequiredService<OntologyDbContext>();
                // 原评估和真实报告仍使用同一身份、修订及全源hash。
                var record = await ontology.Assessments.SingleAsync(row => row.AssessmentId == historical.AssessmentId);
                record.AssessmentJson = JsonSerializer.Serialize(historical);
                await ontology.SaveChangesAsync();
            }
            asset = draft.AssetId;
            draftId = draft.DraftId;
            reportId = historical.ValidationReportId;
            semantics = new PublicationSemantics { ProfileVersion = historical.ProfileVersion, ProfileHash = historical.ProfileHash, AssessmentId = historical.AssessmentId, AssessmentHash = historical.AssessmentHash };
        }
        // 服务器固定图名与源散列快照。
        var snapshot = new AssetVersionSnapshot { ReleaseId = id, OntologyGraphIri = "urn:ontology-platform:release:" + id + ":ontology", DataGraphIri = "urn:ontology-platform:release:" + id + ":data", OntologyHash = analysis.Hashes.OntologyHash, ShapesHash = analysis.Hashes.ShapesHash, VocabularyHash = analysis.Hashes.VocabularyHash, DataHash = analysis.Hashes.DataHash };
        // 四源对象顺序沿用G2合同，V1默认仍无Semantics，既有历史对象不被改写。
        var contents = sources.VocabularyTurtle is null ? new[] { sources.OntologyTurtle, sources.ShapesTurtle, sources.DataTurtle } : new[] { sources.OntologyTurtle, sources.ShapesTurtle, sources.VocabularyTurtle, sources.DataTurtle };
        // 所有对象均真实写入当前隔离S3并读回验证。
        var objects = new List<ArtifactObject>();
        for (var index = 0; index < contents.Length; index++) objects.Add(await fixture.Artifacts.PutImmutableAsync("releases/" + id + "/source-" + index + "-" + Hash(contents[index]) + ".ttl", Encoding.UTF8.GetBytes(contents[index]), "text/turtle", default));
        // 默认无评估字段V1，可选M2分支绑定真实评估的V2；严格DTO核验版本判别。
        var manifest = new ReleaseManifest { SchemaVersion = withM2Profile ? 2 : 1, Semantics = semantics, ReleaseId = id, AssetId = asset, Scope = scope, DraftId = draftId, Revision = 1, Hashes = analysis.Hashes, Snapshot = snapshot, OntologyGraphIri = snapshot.OntologyGraphIri, DataGraphIri = snapshot.DataGraphIri, ArtifactObjects = objects.ToArray(), CreatedAtUtc = DateTimeOffset.UtcNow };
        // 原始manifest序列化一次，后续hash永远针对保存的原始字节。
        var json = JsonSerializer.Serialize(manifest);
        // 清单对象独立，不创建自引用hash。
        var manifestObject = await fixture.Artifacts.PutImmutableAsync("releases/" + id + "/manifest-" + Hash(json) + ".json", Encoding.UTF8.GetBytes(json), "application/json", default);
        await runtime.DeployAsync(manifest, sources, default);
        Assert.IsTrue(await runtime.VerifyAsync(manifest, sources, default));
        // 历史提案按各版本原始字段保留，标已消费防止重用。
        var proposal = new ReleaseProposal { ProposalId = Guid.NewGuid().ToString("N"), Kind = ProposalKind.Publish, AssetId = asset, Scope = scope, DraftId = manifest.DraftId, DraftRevision = 1, Hashes = analysis.Hashes, ValidationReportId = reportId, Semantics = semantics, SubmittedBy = fixture.Author.SubjectId, SubmittedAtUtc = DateTimeOffset.UtcNow, ExpiresAtUtc = DateTimeOffset.UtcNow.AddHours(24), Status = ProposalStatus.Approved, Revision = 2 };
        fixture.Database.Proposals.Add(new ProposalRecord { ProposalId = proposal.ProposalId, AssetId = asset, OrganizationId = scope.OrganizationId, SiteIds = scope.SiteIds, Revision = 2, Activated = true, ProposalJson = JsonSerializer.Serialize(proposal) });
        // 历史正式记录只为本轮兼容验收，不修改外部旧制品。
        var row = new ReleaseRecord { ReleaseId = id, ProposalId = proposal.ProposalId, AssetId = asset, OrganizationId = scope.OrganizationId, SiteIds = scope.SiteIds, SourcesJson = JsonSerializer.Serialize(sources), ManifestJson = json, ManifestHash = Hash(json), ManifestObjectJson = JsonSerializer.Serialize(manifestObject), State = "ACTIVE", Published = true };
        fixture.Database.Releases.Add(row);
        fixture.Database.ActiveReleases.Add(new ActiveReleaseRecord { AssetId = asset, OrganizationId = scope.OrganizationId, SiteIds = scope.SiteIds, ReleaseId = id, Revision = 1 });
        await fixture.Database.SaveChangesAsync();
        fixture.Database.ChangeTracker.Clear();
        return row;
    }

    /// <summary>仅计算精确UTF8字节hash，不规范化历史清单。</summary>
    private static string Hash(string value) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
}
