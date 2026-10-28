using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>评估与版本比较沿用草稿的权限、幂等、CAS及审计事务。</summary>
public sealed partial class OntologyService
{
    /// <summary>返回当前v3策略的独立副本，历史版本由显式工厂登记。</summary>
    public SemanticSupportProfile GetProfile() => SemanticProfile.Current();

    /// <summary>评估端点返回真实持久评估而不接收客户端评估正文。</summary>
    public Task<SemanticAssessment> AssessAsync(ActorContext actor, string draftId, ValidateDraftRequest request, CancellationToken cancellationToken) =>
        AssessCoreAsync(actor, draftId, request, "ontology.assess", static (report, assessment) => assessment, cancellationToken);

    /// <summary>存在性与scope先于评估正文读取，已知越界返回403。</summary>
    public async Task<SemanticAssessment> ReadAssessmentAsync(ActorContext actor, string assessmentId, CancellationToken cancellationToken)
    {
        DemandRole(actor, false);
        // 只读取所属草稿身份进行重新授权。
        var owner = await database.Assessments.AsNoTracking().Where(row => row.AssessmentId == assessmentId).Select(row => row.DraftId).SingleOrDefaultAsync(cancellationToken)
            ?? throw new SemanticOperationException(404, "assessment_not_found");
        // 草稿scope为不可变授权依据，历史assessment不扩大范围。
        var draft = await FindAsync(owner, false, cancellationToken);
        DemandScope(actor, Scope(draft));
        // 已授权后才读取可能含实体定位信息的完整诊断。
        var record = await database.Assessments.AsNoTracking().SingleAsync(row => row.AssessmentId == assessmentId, cancellationToken);
        return JsonSerializer.Deserialize<SemanticAssessment>(record.AssessmentJson)!;
    }

    /// <summary>真实执行报告并以同一个短事务保存报告、评估、回执和审计。</summary>
    private async Task<T> AssessCoreAsync<T>(ActorContext actor, string draftId, ValidateDraftRequest request, string action, Func<SemanticValidationReport, SemanticAssessment, T> select, CancellationToken token) where T : class
    {
        DemandRole(actor, true);
        ValidateCommand(request.Command);
        // 必须先重新授权，不能借真实引擎验证探测其他资产。
        var current = await ReadAsync(actor, draftId, token);
        // 重放返回已提交事实，不刷新评估时刻和24h期限。
        var replay = await ReplayAsync<T>(actor, current.Scope, action, request.Command, new { draftId, request }, token);
        if (replay is not null) return replay;
        if (request.Revision != current.Revision || request.Command.ExpectedRevision != current.Revision || request.Hashes != current.Hashes)
            throw new SemanticOperationException(409, "draft_revision_conflict");
        // 唯一真实RIOT/SHACL结果；执行失败或请求取消时不落成功记录。
        var report = (await runtime.ValidateAsync(current.Sources, token)) with { DraftId = draftId, Revision = current.Revision, Hashes = current.Hashes, TraceId = actor.TraceId };
        token.ThrowIfCancellationRequested();
        // 时间取实际完成时刻，预算失败不能走到这里伪造完成。
        var now = clock.GetUtcNow();
        // 同一固定策略同时进入评估和后续发布绑定。
        var profile = GetProfile();
        // 不支持公理时SHACL确实未运行，不能冒称SHACL PASS。
        var supportPassed = report.Kind != ValidationKind.OwlSupport;
        // 报告定位只能沿用实际来源，不猜测行列；跨源内容使用bundle散列。
        var validationDiagnostics = report.Issues.Select(issue => WrapDiagnostic(issue, current.Hashes)).ToArray();
        if (runtime is not IG3VocabularyRuntime vocabulary) throw new SemanticOperationException(503, "vocabulary_runtime_unavailable");
        // M3治理读取同一固定四源，不通过旧ValidationIssue包装而丢失精确规则码。
        var governance = (await vocabulary.ReadVocabularyAsync(current.Sources, current.Revision, token)).Diagnostics;
        // 错误为FAIL，未知语言/精度为INDETERMINATE，两者都不具备发布资格。
        var governanceStatus = governance.Any(item => item.Diagnostic.Severity == DiagnosticSeverity.Error) ? AssessmentStageStatus.Fail : governance.Any(item => item.Diagnostic.Severity == DiagnosticSeverity.Warning) ? AssessmentStageStatus.Indeterminate : AssessmentStageStatus.Pass;
        // SHACL诊断保持原来来源绑定，新治理直接追加准确source/hash/focus/path。
        var diagnostics = validationDiagnostics.Concat(governance).ToArray();
        // 只有必要阶段通过及预算完成才有发布资格，OWL推理明确未执行。
        var assessment = new SemanticAssessment
        {
            AssessmentId = Guid.NewGuid().ToString("N"),
            ValidationReportId = report.ReportId,
            DraftId = draftId,
            Revision = current.Revision,
            Hashes = current.Hashes,
            ProfileVersion = profile.Version,
            ProfileHash = profile.Hash,
            AssessmentHash = "",
            AssessedAtUtc = now,
            ExpiresAtUtc = now.AddHours(24),
            ExecutorVersion = "jena-6.2.0/riot-shacl/g3-m1-1",
            Stages = [new AssessmentStage { Name = "PARSE", Status = AssessmentStageStatus.Pass, Code = "riot_parsed" },
                new AssessmentStage { Name = "SUPPORT", Status = supportPassed ? AssessmentStageStatus.Pass : AssessmentStageStatus.NotSupported, Code = supportPassed ? "asserted_subset_supported" : "axiom_unsupported" },
                new AssessmentStage { Name = "SHACL_CORE", Status = !supportPassed ? AssessmentStageStatus.NotRun : report.Conforms ? AssessmentStageStatus.Pass : AssessmentStageStatus.Fail, Code = !supportPassed ? "support_blocked" : report.Conforms ? "shacl_conforms" : "shacl_violation" },
                new AssessmentStage { Name = "GOVERNANCE", Status = governanceStatus, Code = governanceStatus == AssessmentStageStatus.Pass ? "scope_revision_bound" : "vocabulary_governance_blocked" },
                new AssessmentStage { Name = "OWL_REASONING", Status = AssessmentStageStatus.NotRun, Code = "asserted_only" }],
            PublishEligible = supportPassed && report.Conforms && governanceStatus == AssessmentStageStatus.Pass,
            Diagnostics = diagnostics,
            BudgetStatus = "COMPLETE"
        };
        assessment = assessment with { AssessmentHash = SemanticProfile.AssessmentHash(assessment) };
        return await WriteAsync<T>(actor, current.Scope, action, request.Command, new { draftId, request }, async transactionToken =>
        {
            // 外部执行期间的任何保存使本评估CAS失败，报告与评估均回滚。
            var row = await FindAsync(draftId, true, transactionToken);
            DemandScope(actor, Scope(row));
            if (row.Revision != current.Revision) throw new SemanticOperationException(409, "draft_revision_conflict");
            database.Validations.Add(new ValidationRecord { ReportId = report.ReportId, DraftId = draftId, Revision = report.Revision, BundleHash = report.Hashes.BundleHash, Conforms = report.Conforms, ReportJson = JsonSerializer.Serialize(report) });
            database.Assessments.Add(new AssessmentRecord { AssessmentId = assessment.AssessmentId, ValidationReportId = report.ReportId, DraftId = draftId, Revision = current.Revision, AssessmentJson = JsonSerializer.Serialize(assessment) });
            return (select(report, assessment), draftId);
        }, token);
    }

    /// <summary>将旧报告诊断包装成可精确核对来源hash的新合同。</summary>
    private static AssessmentDiagnostic WrapDiagnostic(ValidationIssue issue, SourceHashes hashes)
    {
        // 只有真实支持诊断证明的来源可使用单源hash；旧synthetic-data表示合并图，必须使用bundle，不能猜成data。
        var source = issue.SourceId switch { "ontology" => "ontology", "shapes" => "shapes", "vocabulary" => "vocabulary", "data" => "data", "synthetic-data" => "bundle", _ => "bundle" };
        return new AssessmentDiagnostic { SourceId = source, SourceHash = source switch { "ontology" => hashes.OntologyHash, "shapes" => hashes.ShapesHash, "vocabulary" => hashes.VocabularyHash ?? hashes.BundleHash, "data" => hashes.DataHash, _ => hashes.BundleHash }, Diagnostic = new SemanticDiagnostic { Code = "validation_issue", Severity = issue.Severity, Message = issue.Message, FocusNode = issue.FocusNode, Path = issue.Path }, SourceShape = issue.SourceShape, Line = null, Column = null };
    }

    /// <summary>重新散列并逐字段核查持久评估，任何绑定或时效漂移失败关闭。</summary>
    private void CheckAssessment(SemanticAssessment assessment, AssessmentRecord record, DraftRecord draft, SourceHashes hashes, string reportId, SourceBundle sources)
    {
        // 当前profile只用于新发布；旧Release回滚不调用本检查。
        var profile = GetProfile();
        if (record.AssessmentId != assessment.AssessmentId || record.ValidationReportId != reportId || record.DraftId != draft.DraftId || record.Revision != draft.Revision || assessment.ValidationReportId != reportId || assessment.DraftId != draft.DraftId || assessment.Revision != draft.Revision || assessment.Hashes != hashes || JenaRdfCodec.Hashes(sources) != hashes || assessment.ProfileVersion != profile.Version || assessment.ProfileHash != profile.Hash || SemanticProfile.AssessmentHash(assessment) != assessment.AssessmentHash || assessment.AssessedAtUtc > clock.GetUtcNow() || assessment.ExpiresAtUtc != assessment.AssessedAtUtc.AddHours(24))
            throw new SemanticOperationException(409, "assessment_binding_conflict");
        if (assessment.ExpiresAtUtc <= clock.GetUtcNow()) throw new SemanticOperationException(409, "assessment_expired");
        if (!assessment.PublishEligible || assessment.BudgetStatus != "COMPLETE" || assessment.Stages.Length != 5 || new[] { "PARSE", "SUPPORT", "SHACL_CORE", "GOVERNANCE" }.Any(name => assessment.Stages.Count(stage => stage.Name == name && stage.Status == AssessmentStageStatus.Pass) != 1) || assessment.Stages.Count(stage => stage.Name == "OWL_REASONING" && stage.Status == AssessmentStageStatus.NotRun) != 1)
            throw new SemanticOperationException(422, "assessment_not_eligible");
    }

    /// <summary>只比较同一资产同一完整scope的服务器固定版本，不写业务记录。</summary>
    public async Task<SourceComparison[]> CompareAsync(ActorContext actor, CompareVersionsRequest request, CancellationToken cancellationToken)
    {
        DemandRole(actor, false);
        // DTO严格检查同时用于非HTTP应用调用，客户端hash和任意地址不存在入口。
        if (request?.From is null || request.To is null) throw new SemanticOperationException(422, "comparison_reference_invalid");
        try { JsonSerializer.Serialize(request); }
        catch (JsonException) { throw new SemanticOperationException(422, "comparison_reference_invalid"); }
        // 两端均先完成授权和原始源核验，之后才能解析比较。
        var left = await ReadVersionAsync(actor, request.From, cancellationToken);
        // 历史版本不可缩小为第一厂区，不允许跨资产比较。
        var right = await ReadVersionAsync(actor, request.To, cancellationToken);
        if (left.AssetId != right.AssetId || left.Scope.OrganizationId != right.Scope.OrganizationId || !Normalize(left.Scope).SiteIds.SequenceEqual(Normalize(right.Scope).SiteIds, StringComparer.Ordinal))
            throw new SemanticOperationException(403, "comparison_asset_scope_conflict");
        cancellationToken.ThrowIfCancellationRequested();
        if (runtime is not IG3SemanticRuntime comparison) throw new SemanticOperationException(503, "comparison_runtime_unavailable");
        return await comparison.CompareSourcesAsync(left.Sources, right.Sources, cancellationToken);
    }

    /// <summary>从已授权不可变修订或正式对象中恢复完整四源。</summary>
    private async Task<(string AssetId, ResourceScope Scope, SourceBundle Sources)> ReadVersionAsync(ActorContext actor, VersionRef reference, CancellationToken token)
    {
        if (reference.Kind == VersionRefKind.Draft)
        {
            // 头只用于授权，正文严格按指定修订读取。
            var draft = await FindAsync(reference.Id, false, token);
            DemandScope(actor, Scope(draft));
            // 不可变历史修订不能由当前Projection替代。
            var revision = await database.Revisions.AsNoTracking().SingleOrDefaultAsync(row => row.DraftId == reference.Id && row.Revision == reference.Revision, token) ?? throw new SemanticOperationException(404, "revision_not_found");
            return (draft.AssetId, Scope(draft), JsonSerializer.Deserialize<SourceBundle>(revision.SourcesJson)!);
        }
        if (releases is null || artifacts is null) throw new SemanticOperationException(503, "release_catalog_unavailable");
        // Catalog重新授权并核验实际manifest对象原始字节和正式图。
        var release = await releases.ReadAsync(actor, reference.Id, token);
        // 固定槽位次序来自发布合同，不读取客户端对象地址。
        var manifest = release.Manifest;
        // 严格UTF8解码拒绝替换字符，避免改变源hash。
        var utf8 = new UTF8Encoding(false, true);
        // 词汇缺席不同于空字符串。
        string[] expected = manifest.Hashes.VocabularyHash is { } vocabulary ? [manifest.Hashes.OntologyHash, manifest.Hashes.ShapesHash, vocabulary, manifest.Hashes.DataHash] : [manifest.Hashes.OntologyHash, manifest.Hashes.ShapesHash, manifest.Hashes.DataHash];
        if (manifest.ArtifactObjects.Length != expected.Length) throw new SemanticOperationException(503, "published_source_binding_invalid");
        // 保存本次实际读取且已核对散列的源内容。
        var texts = new string[expected.Length];
        for (var index = 0; index < texts.Length; index++)
        {
            // 固定位置、键和媒体类型同时核验，不能交换不同源。
            var item = manifest.ArtifactObjects[index];
            if (item.Hash != expected[index] || item.ObjectKey != "releases/" + manifest.ReleaseId + "/source-" + index + "-" + expected[index] + ".ttl" || item.ContentType != "text/turtle" || item.SizeBytes is < 0 or > 256 * 1024) throw new SemanticOperationException(503, "published_source_binding_invalid");
            // 对象适配之外再核对实际返回字节的源散列。
            var bytes = await artifacts.ReadVerifiedAsync(item, token);
            if (bytes.LongLength != item.SizeBytes || Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(bytes)) != expected[index]) throw new SemanticOperationException(503, "published_source_binding_invalid");
            try { texts[index] = utf8.GetString(bytes); }
            catch (DecoderFallbackException) { throw new SemanticOperationException(503, "published_source_encoding_invalid"); }
        }
        return (manifest.AssetId, manifest.Scope, new SourceBundle { OntologyTurtle = texts[0], ShapesTurtle = texts[1], VocabularyTurtle = texts.Length == 4 ? texts[2] : null, DataTurtle = texts[^1] });
    }
}
