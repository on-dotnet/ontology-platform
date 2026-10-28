using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology;
using OntologyPlatform.Modules.Publishing;

namespace OntologyPlatform.PublishingTests;

/// <summary>独立历史V1及M1策略V2夹具真实保存对象/图，验证读取和回滚而不伪造新发布资格。</summary>
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

    /// <summary>历史M1的schema2清单及v1策略保持原字节可读，当前v2替换后仍独立审批和CAS回滚。</summary>
    [TestMethod]
    public async Task HistoricalM1ProfileV1ManifestV2ReadsAndRollsBackAfterCurrentProfileUpgrade()
    {
        // 隔离真实PG、Jena及RustFS保存本次合成历史事实。
        using var fixture = new PublishingFixture();
        // 可选历史分支使用真实服务评估和报告构造完整M1绑定，不伪造发布资格。
        var legacy = await SeedLegacyAsync(fixture, withM1Profile: true);
        // Catalog执行真实对象及正式图回验，不能以PG行存在代替可用。
        var read = await fixture.Catalog.ReadAsync(fixture.Author, legacy.ReleaseId, default);
        Assert.AreEqual(2, read.Manifest.SchemaVersion);
        Assert.AreEqual("1", read.Manifest.Semantics!.ProfileVersion);
        Assert.AreEqual("54e4db0fac2c7e4f89802678f3269b8a460190775b53b4fb74955f8cbadd8b86", read.Manifest.Semantics.ProfileHash);
        Assert.AreEqual(legacy.ManifestHash, read.ManifestHash);
        Assert.AreEqual(Hash(legacy.ManifestJson), read.ManifestHash);
        // 原始清单对象实际回读，后续回滚不能重序列化或升级历史字节。
        var manifestObject = JsonSerializer.Deserialize<ArtifactObject>(legacy.ManifestObjectJson)!;
        CollectionAssert.AreEqual(Encoding.UTF8.GetBytes(legacy.ManifestJson), await fixture.Artifacts.ReadVerifiedAsync(manifestObject, default));
        // 独立PG上下文重验历史评估自身hash及其真实SHACL报告来源。
        using (var historicalScope = fixture.Provider.CreateScope())
        {
            // 直接读取仅用于测试自洽性核验，不作为生产发布旁路。
            var ontology = historicalScope.ServiceProvider.GetRequiredService<OntologyDbContext>();
            // 精确历史评估引用必须对应同一已持久事实。
            var assessment = JsonSerializer.Deserialize<SemanticAssessment>((await ontology.Assessments.AsNoTracking().SingleAsync(row => row.AssessmentId == read.Manifest.Semantics.AssessmentId)).AssessmentJson)!;
            // 合格性来自实际RIOT/SHACL，不硬编码空成功报告。
            var report = JsonSerializer.Deserialize<SemanticValidationReport>((await ontology.Validations.AsNoTracking().SingleAsync(row => row.ReportId == assessment.ValidationReportId)).ReportJson)!;
            Assert.AreEqual(read.Manifest.DraftId, assessment.DraftId);
            Assert.AreEqual(read.Manifest.Revision, assessment.Revision);
            Assert.AreEqual(read.Manifest.Hashes, assessment.Hashes);
            Assert.AreEqual("1", assessment.ProfileVersion);
            Assert.AreEqual(SemanticProfile.LegacyM1().Hash, assessment.ProfileHash);
            Assert.AreEqual(SemanticProfile.AssessmentHash(assessment), assessment.AssessmentHash);
            Assert.AreEqual(read.Manifest.Semantics.AssessmentHash, assessment.AssessmentHash);
            Assert.AreEqual(ValidationKind.ShaclCore, report.Kind);
            Assert.IsTrue(report.Conforms);
            Assert.AreEqual(report.Conforms, assessment.PublishEligible);
        }
        // 精确注册版本/hash不能混配；篡改只在调用参数副本，原历史对象不变。
        var runtime = fixture.Provider.GetRequiredService<ISemanticRuntime>();
        Assert.AreEqual("release_profile_unsupported", (await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.VerifyAsync(read.Manifest with { Semantics = read.Manifest.Semantics with { ProfileHash = new string('a', 64) } }, PublishingFixture.Sources(), default))).Code);
        // 新草稿从已正式历史版本继承资产身份，正常新发布仍必须使用当前v2评估。
        var draft = await fixture.Ontology.CreateAsync(fixture.Author, new CreateDraftRequest { Name = "M2 clone from historical M1 profile", Scope = read.Manifest.Scope, Sources = PublishingFixture.Sources(), BaseReleaseId = legacy.ReleaseId, Command = PublishingFixture.Command() }, default);
        // 真正异人审批，不能重用历史PUBLISH提案。
        var proposal = await fixture.ApproveAsync(await fixture.ProposalForAsync(draft));
        // CAS用历史活动revision1替换为当前版本。
        var current = await fixture.Service.ActivateAsync(fixture.Author, new ActivateReleaseRequest { ProposalId = proposal.ProposalId, ExpectedActiveReleaseId = legacy.ReleaseId, ExpectedActivationRevision = 1, Command = PublishingFixture.Command(proposal.Revision) }, default);
        Assert.AreEqual(2, current.Manifest.SchemaVersion);
        Assert.AreEqual("3", current.Manifest.Semantics!.ProfileVersion);
        Assert.AreEqual(SemanticProfile.Current().Hash, current.Manifest.Semantics.ProfileHash);
        // 当前草稿推进后，旧评估不再绑定最新revision。
        var advanced = await fixture.Ontology.SaveAsync(fixture.Author, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = draft.Sources with { OntologyTurtle = draft.Sources.OntologyTurtle + "\n# current draft advanced beyond M1 rollback" }, Command = PublishingFixture.Command(1) }, default);
        // 历史回滚不能读取或要求当前草稿的已过期评估。
        using (var invalidScope = fixture.Provider.CreateScope())
        {
            // 只修改本次隔离PG的当前评估，保留旧历史评估和不可变正式对象。
            var ontology = invalidScope.ServiceProvider.GetRequiredService<OntologyDbContext>();
            // 当前发布对应的实际评估事实故意失效。
            var record = await ontology.Assessments.SingleAsync(row => row.AssessmentId == current.Manifest.Semantics.AssessmentId);
            // 保持hash自洽，模拟真实时间到期而非任意损坏。
            var assessment = JsonSerializer.Deserialize<SemanticAssessment>(record.AssessmentJson)!;
            assessment = assessment with { AssessedAtUtc = assessment.AssessedAtUtc.AddHours(-25), ExpiresAtUtc = assessment.ExpiresAtUtc.AddHours(-25) };
            assessment = assessment with { AssessmentHash = SemanticProfile.AssessmentHash(assessment) };
            record.AssessmentJson = JsonSerializer.Serialize(assessment);
            await ontology.SaveChangesAsync();
            Assert.AreEqual(409, (await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.CreateProposalAsync(fixture.Author, new CreateProposalRequest { Kind = ProposalKind.Publish, DraftId = advanced.DraftId, DraftRevision = advanced.Revision, Hashes = advanced.Hashes, ValidationReportId = assessment.ValidationReportId, Command = PublishingFixture.Command(advanced.Revision) }, default))).Status);
        }
        // 回滚仍走新提案、异人审批及当前活动指针CAS。
        var rollback = await fixture.ApproveAsync(await fixture.Service.CreateProposalAsync(fixture.Author, new CreateProposalRequest { Kind = ProposalKind.Rollback, TargetReleaseId = legacy.ReleaseId, TargetManifestHash = legacy.ManifestHash, Command = PublishingFixture.Command() }, default));
        Assert.AreEqual(409, (await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(rollback, current) with { ExpectedActiveReleaseId = legacy.ReleaseId }, default))).Status);
        Assert.AreEqual(current.ReleaseId, (await fixture.Database.ActiveReleases.AsNoTracking().SingleAsync(row => row.AssetId == current.Manifest.AssetId)).ReleaseId);
        // 正确CAS必须实际重新核验历史v1策略对象与图，再恢复原发布身份。
        var restored = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(rollback, current), default);
        Assert.AreEqual(legacy.ReleaseId, restored.ReleaseId);
        Assert.AreEqual(legacy.ManifestHash, restored.ManifestHash);
        Assert.AreEqual(3L, restored.ActivationRevision);
        Assert.AreEqual("1", restored.Manifest.Semantics!.ProfileVersion);
        Assert.AreEqual(SemanticProfile.LegacyM1().Hash, restored.Manifest.Semantics.ProfileHash);
        Assert.AreEqual(legacy.ManifestJson, (await fixture.Database.Releases.AsNoTracking().SingleAsync(row => row.ReleaseId == legacy.ReleaseId)).ManifestJson);
        CollectionAssert.AreEqual(Encoding.UTF8.GetBytes(legacy.ManifestJson), await fixture.Artifacts.ReadVerifiedAsync(manifestObject, default));
        Assert.AreEqual(legacy.ManifestHash, (await fixture.Catalog.ReadAsync(fixture.Author, legacy.ReleaseId, default)).ManifestHash);
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
    /// <param name="fixture">本次隔离的真实PG、Jena及RustFS夹具。</param>
    /// <param name="withM1Profile">明确导入带真实M1评估的V2历史，否则保持原V1默认行为。</param>
    /// <returns>已写入真实对象、正式图及PG目录的历史发布记录。</returns>
    private static async Task<ReleaseRecord> SeedLegacyAsync(PublishingFixture fixture, bool withM1Profile = false)
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
        if (withM1Profile)
        {
            // 先通过真实生产用例生成草稿、RIOT/SHACL报告、阶段及资格事实。
            var draft = await fixture.Ontology.CreateAsync(fixture.Author, new CreateDraftRequest { Name = "Isolated historical M1 assessment fixture", Scope = scope, Sources = sources, Command = PublishingFixture.Command() }, default);
            // 当前和历史策略的asserted-only发布规则相同，仅测试导入时登记原M1策略身份。
            var assessed = await ((IG3OntologyService)fixture.Ontology).AssessAsync(fixture.Author, draft.DraftId, new ValidateDraftRequest { Revision = draft.Revision, Hashes = draft.Hashes, Command = PublishingFixture.Command(draft.Revision) }, default);
            Assert.IsTrue(assessed.PublishEligible);
            Assert.AreEqual(analysis.Hashes, assessed.Hashes);
            // 历史工厂保留精确golden策略，真实阶段、预算、诊断和资格全部沿用报告。
            var profile = SemanticProfile.LegacyM1();
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
        // 默认无评估字段V1，可选M1分支绑定真实评估的V2；严格DTO核验版本判别。
        var manifest = new ReleaseManifest { SchemaVersion = withM1Profile ? 2 : 1, Semantics = semantics, ReleaseId = id, AssetId = asset, Scope = scope, DraftId = draftId, Revision = 1, Hashes = analysis.Hashes, Snapshot = snapshot, OntologyGraphIri = snapshot.OntologyGraphIri, DataGraphIri = snapshot.DataGraphIri, ArtifactObjects = objects.ToArray(), CreatedAtUtc = DateTimeOffset.UtcNow };
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

    /// <summary>仅计算精确原始UTF8字节hash，不规范化文本。</summary>
    private static string Hash(string value) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));
}
