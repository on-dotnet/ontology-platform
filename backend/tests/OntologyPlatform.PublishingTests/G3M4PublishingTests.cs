using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology;
using OntologyPlatform.Modules.Publishing;

namespace OntologyPlatform.PublishingTests;

/// <summary>真实PG/Jena/RustFS验证v4身份发布、不可变读取及精确旧v3回滚。</summary>
[TestClass]
public sealed class G3M4PublishingTests
{
    /// <summary>新审批发布精确绑定v4，正式身份读取与后续草稿和活动回滚隔离。</summary>
    [TestMethod]
    public async Task VersionFourIdentityPublicationAndExactVersionThreeRollback()
    {
        // 使用当前脚本随机新建的真实三依赖，不读历史开发凭证或资源。
        using var fixture = new PublishingFixture();
        // 原v3清单与源对象真实写入隔离S3，图真实部署并回验。
        var legacy = await SeedLegacyM3Async(fixture);
        // 历史版本只使用自己的显式profile和原始manifest。
        var old = await fixture.Catalog.ReadAsync(fixture.Author, legacy.ReleaseId, default);
        Assert.AreEqual("3", old.Manifest.Semantics!.ProfileVersion);
        Assert.AreEqual(SemanticProfile.LegacyM3().Hash, old.Manifest.Semantics.ProfileHash);
        // 服务DI必须接入真实身份用例，不另造正式读取替身。
        var identity = (IG3IdentityTimeService)fixture.Ontology;
        Assert.AreEqual("3", (await identity.ReadReleaseIdentityTimeAsync(fixture.Author, legacy.ReleaseId, default)).ProfileVersion);
        // clone继承同asset/scope，并添加仅v4开放的受控身份与时间。
        var draft = await fixture.Ontology.CreateAsync(fixture.Author, new CreateDraftRequest { Name = "Synthetic M4 from exact M3", Scope = old.Manifest.Scope, Sources = IdentitySources(fixture.Author.OrganizationId), BaseReleaseId = legacy.ReleaseId, Command = PublishingFixture.Command() }, default);
        // SHACL/治理及异人审批均通过真实应用服务。
        var proposal = await fixture.ApproveAsync(await fixture.ProposalForAsync(draft));
        // 活动指针CAS明确指向已有v3和revision1。
        var current = await fixture.Service.ActivateAsync(fixture.Author, new ActivateReleaseRequest { ProposalId = proposal.ProposalId, ExpectedActiveReleaseId = legacy.ReleaseId, ExpectedActivationRevision = 1, Command = PublishingFixture.Command(proposal.Revision) }, default);
        Assert.AreEqual("4", current.Manifest.Semantics!.ProfileVersion);
        Assert.AreEqual(SemanticProfile.Current().Hash, current.Manifest.Semantics.ProfileHash);
        // 已提交版本快照在回滚后仍指向原版本，不跟随active指针漂移。
        var fixedSnapshot = current.Manifest.Snapshot;
        // 正式读取必须经过真实对象和同批Jena图核验。
        var formal = await identity.ReadReleaseIdentityTimeAsync(fixture.Author, current.ReleaseId, default);
        Assert.AreEqual(current.ReleaseId, formal.ReleaseId);
        Assert.AreEqual(current.ManifestHash, formal.ManifestHash);
        Assert.AreEqual(current.Manifest.Hashes, formal.Hashes);
        Assert.IsEmpty(formal.Diagnostics);
        Assert.IsTrue(formal.Triples.Any(item => item.Triple.Predicate == "urn:ontology-platform:semantics:externalIdentifier" && item.Triple.Object.Value == "EQ-01"));
        // 当前草稿追加后续说明，不得改变不可变Release的身份历史和源hash。
        await fixture.Ontology.SaveAsync(fixture.Author, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = draft.Sources with { OntologyTurtle = draft.Sources.OntologyTurtle + "\n# draft advanced after immutable v4 release\n" }, Command = PublishingFixture.Command(1) }, default);
        Assert.AreEqual(formal.Hashes, (await identity.ReadReleaseIdentityTimeAsync(fixture.Author, current.ReleaseId, default)).Hashes);
        // 从已发布v4再clone时也不能通过新草稿删除有效身份历史。
        var erase = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Ontology.CreateAsync(fixture.Author, new CreateDraftRequest { Name = "Synthetic invalid clone", Scope = old.Manifest.Scope, Sources = PublishingFixture.Sources(), BaseReleaseId = current.ReleaseId, Command = PublishingFixture.Command() }, default));
        Assert.AreEqual("identity_history_immutable", erase.Code);
        // 回滚以新提案和异人批准重新授权技术回验，而不是复活旧审批。
        var rollback = await fixture.ApproveAsync(await fixture.Service.CreateProposalAsync(fixture.Author, new CreateProposalRequest { Kind = ProposalKind.Rollback, TargetReleaseId = legacy.ReleaseId, TargetManifestHash = legacy.ManifestHash, Command = PublishingFixture.Command() }, default));
        // 真实回验旧v3原始对象/图后原子更新active CAS。
        var restored = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(rollback, current), default);
        Assert.AreEqual(legacy.ReleaseId, restored.ReleaseId);
        Assert.AreEqual(legacy.ManifestHash, restored.ManifestHash);
        Assert.AreEqual("3", restored.Manifest.Semantics!.ProfileVersion);
        Assert.AreEqual(3L, restored.ActivationRevision);
        Assert.AreEqual(legacy.ManifestJson, (await fixture.Database.Releases.AsNoTracking().SingleAsync(row => row.ReleaseId == legacy.ReleaseId)).ManifestJson);
        // active解析选择已回滚v3，固定历史读取仍返回原v4，不混用当前草稿。
        Assert.AreEqual(legacy.ReleaseId, (await fixture.Catalog.ResolveAsync(fixture.Author, draft.AssetId, null, default)).Manifest.ReleaseId);
        Assert.AreEqual(current.ReleaseId, fixedSnapshot.ReleaseId);
        Assert.AreEqual(current.Manifest.Hashes.OntologyHash, fixedSnapshot.OntologyHash);
        Assert.AreEqual(formal.Hashes, (await identity.ReadReleaseIdentityTimeAsync(fixture.Author, current.ReleaseId, default)).Hashes);
    }

    /// <summary>即使真实SHACL符合，身份歧义或不确定时间仍无法创建新提案。</summary>
    /// <param name="unknown">未知关系与确定冲突分别覆盖。</param>
    [TestMethod]
    [DataRow(false)]
    [DataRow(true)]
    public async Task IdentityGovernanceCannotBeOverriddenByReviewer(bool unknown)
    {
        // 正常服务全部访问当前真实隔离依赖。
        using var fixture = new PublishingFixture();
        // 两个同号声明使用不同target，未知不能被当作安全不相交。
        var sources = IdentitySources(fixture.Author.OrganizationId, unknown ? null : "2026-03-01T00:00:00Z");
        sources = sources with { OntologyTurtle = sources.OntologyTurtle + Claim(fixture.Author.OrganizationId, "two", unknown ? null : "2026-04-01T00:00:00Z", target: "B", from: "2026-02-01T00:00:00Z") };
        // 源码可以保存供专家纠正，但评估必须失败关闭。
        var draft = await fixture.Ontology.CreateAsync(fixture.Author, new CreateDraftRequest { Name = "Synthetic identity governance refusal", Scope = new ResourceScope { OrganizationId = fixture.Author.OrganizationId, SiteIds = fixture.Author.SiteIds }, Sources = sources, Command = PublishingFixture.Command() }, default);
        // 报告确实来自真实SHACL，不手写conforms成功。
        var report = await fixture.Ontology.ValidateAsync(fixture.Author, draft.DraftId, new ValidateDraftRequest { Revision = 1, Hashes = draft.Hashes, Command = PublishingFixture.Command(1) }, default);
        Assert.IsTrue(report.Conforms);
        // 审核者尚无可审核提案，不能覆盖技术阻断项。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.CreateProposalAsync(fixture.Author, new CreateProposalRequest { Kind = ProposalKind.Publish, DraftId = draft.DraftId, DraftRevision = 1, Hashes = draft.Hashes, ValidationReportId = report.ReportId, Command = PublishingFixture.Command(1) }, default));
        Assert.AreEqual("assessment_not_eligible", error.Code);
        Assert.IsFalse(await fixture.Database.Releases.AnyAsync(row => row.AssetId == draft.AssetId));
    }

    /// <summary>v4专用身份读取在任何对象或图访问前核验全部厂区范围。</summary>
    [TestMethod]
    public async Task FormalIdentityReadRejectsPartialScopeBeforeExternalRead()
    {
        // 当前真实服务组合与依赖独立于其它测试。
        using var fixture = new PublishingFixture();
        // 新资产保留完整双厂scope。
        var draft = await fixture.Ontology.CreateAsync(fixture.Author, new CreateDraftRequest { Name = "Synthetic identity scope", Scope = new ResourceScope { OrganizationId = fixture.Author.OrganizationId, SiteIds = fixture.Author.SiteIds }, Sources = IdentitySources(fixture.Author.OrganizationId), Command = PublishingFixture.Command() }, default);
        // 真正评估、审核和发布，确保拒绝并非资源不存在。
        var release = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(await fixture.ApproveAsync(await fixture.ProposalForAsync(draft))), default);
        // Gate只计数真实传输，不能提供假成功结果。
        var calls = 0;
        fixture.Gate = (_, _) => { Interlocked.Increment(ref calls); return Task.CompletedTask; };
        Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => ((IG3IdentityTimeService)fixture.Ontology).ReadReleaseIdentityTimeAsync(fixture.Author with { SiteIds = ["site-a"] }, release.ReleaseId, default))).Status);
        Assert.AreEqual(0, calls);
    }

    /// <summary>真实baseline提供非空正式数据图，本轮只追加明确Synthetic身份模板。</summary>
    private static SourceBundle IdentitySources(string organization, string? end = null)
    {
        // 四源基线由已提交fixture读取，额外实例均有Synthetic命名空间。
        var sources = PublishingFixture.Sources();
        return sources with { OntologyTurtle = sources.OntologyTurtle + Prefix + "ex:A a owl:NamedIndividual . ex:B a owl:NamedIndividual . " + Claim(organization, "one", end) };
    }

    /// <summary>明确组织/厂区/来源/编号/目标/来源版本及半开有效时间。</summary>
    private static string Claim(string organization, string id, string? end, string target = "A", string from = "2026-01-01T00:00:00Z") =>
        $"ex:claim-{id} a p:IdentityClaim ; p:organizationId \"{organization}\" ; p:siteId \"site-a\" ; p:sourceNamespace \"erp.synthetic\" ; p:externalIdentifier \"EQ-01\" ; p:targetIri ex:{target} ; p:declarationSource <urn:synthetic:m4:declaration:v1> ; p:validityInterval ex:interval-{id} . ex:interval-{id} a time:Interval ; time:hasBeginning ex:from-{id} . ex:from-{id} a time:Instant ; time:inXSDDateTimeStamp \"{from}\"^^xsd:dateTimeStamp . " + (end is null ? "" : $"ex:interval-{id} time:hasEnd ex:to-{id} . ex:to-{id} a time:Instant ; time:inXSDDateTimeStamp \"{end}\"^^xsd:dateTimeStamp . ");

    /// <summary>受控标准词汇和Synthetic实例前缀，禁止imports联网。</summary>
    private const string Prefix = "\n@prefix ex: <urn:synthetic:m4:> . @prefix p: <urn:ontology-platform:semantics:> . @prefix time: <http://www.w3.org/2006/time#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix owl: <http://www.w3.org/2002/07/owl#> . ";

    /// <summary>仅本次隔离兼容fixture直接登记历史v3；生产新发布没有此写入入口。</summary>
    private static async Task<ReleaseRecord> SeedLegacyM3Async(PublishingFixture fixture, bool withM3Profile = true)
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
        // V1默认没有评估和语义字段，保持原测试及原始manifest输出路径不变。
        PublicationSemantics? semantics = null;
        // V1旧草稿标识默认值不得被新测试分支改写。
        var draftId = "legacy-" + id;
        // V1默认报告引用保持历史原形。
        var reportId = "legacy-report";
        if (withM3Profile)
        {
            // 先通过真实生产用例生成草稿、RIOT/SHACL报告、阶段及资格事实。
            var draft = await fixture.Ontology.CreateAsync(fixture.Author, new CreateDraftRequest { Name = "Isolated historical M3 assessment fixture", Scope = scope, Sources = sources, Command = PublishingFixture.Command() }, default);
            // 当前和历史策略的asserted-only发布规则相同，仅测试导入时登记原M3策略身份。
            var assessed = await ((IG3OntologyService)fixture.Ontology).AssessAsync(fixture.Author, draft.DraftId, new ValidateDraftRequest { Revision = draft.Revision, Hashes = draft.Hashes, Command = PublishingFixture.Command(draft.Revision) }, default);
            Assert.IsTrue(assessed.PublishEligible);
            Assert.AreEqual(analysis.Hashes, assessed.Hashes);
            // 历史工厂保留精确golden策略，真实阶段、预算、诊断和资格全部沿用报告。
            var profile = SemanticProfile.LegacyM3();
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
        // 默认无评估字段V1，可选M3分支绑定真实评估的V2；严格DTO核验版本判别。
        var manifest = new ReleaseManifest { SchemaVersion = withM3Profile ? 2 : 1, Semantics = semantics, ReleaseId = id, AssetId = asset, Scope = scope, DraftId = draftId, Revision = 1, Hashes = analysis.Hashes, Snapshot = snapshot, OntologyGraphIri = snapshot.OntologyGraphIri, DataGraphIri = snapshot.DataGraphIri, ArtifactObjects = objects.ToArray(), CreatedAtUtc = DateTimeOffset.UtcNow };
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

    /// <summary>历史清单散列只针对精确UTF8字节，不重写历史序列化。</summary>
    private static string Hash(string value) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
}
