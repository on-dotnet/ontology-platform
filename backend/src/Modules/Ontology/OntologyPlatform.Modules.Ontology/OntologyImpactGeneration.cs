using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>不可变影响报告复用现有命令/审计事务及唯一固定输入，不引入第二套源权威。</summary>
public sealed partial class OntologyService
{
    /// <summary>先固定真实来源和评估身份，再有界比较并幂等保存首次报告。</summary>
    public async Task<ImpactReport> GenerateImpactAsync(ActorContext actor, GenerateImpactReportRequest request, CancellationToken cancellationToken)
    {
        DemandRole(actor, true);
        if (request?.From is null || request.To is null) throw new SemanticOperationException(422, "impact_reference_invalid");
        ValidateCommand(request.Command);
        try { JsonSerializer.Serialize(request); }
        catch (JsonException) { throw new SemanticOperationException(422, "impact_reference_invalid"); }
        if (request.Command.ExpectedRevision != (request.To.Kind == VersionRefKind.Draft ? request.To.Revision : 0)) throw new SemanticOperationException(409, "impact_target_conflict");
        // 草稿头即可重新授权并恢复成功命令，重放不依赖Jena当前可用性。
        if (request.To.Kind == VersionRefKind.Draft)
        {
            // 读取完整scope早于任何源正文或外部引擎。
            var owner = await FindAsync(request.To.Id, false, cancellationToken);
            DemandScope(actor, Scope(owner));
            // 原成功回执只定位真实不可变报告，不能靠修改结果JSON延长期限。
            var replay = await ReplayAsync<ImpactReport>(actor, Scope(owner), "ontology.impact.generate", request.Command, request, cancellationToken);
            if (replay is not null) return await ReadImpactAsync(actor, replay.ReportId, cancellationToken);
        }
        // 两端来源均必须恢复并核对实际原文，指纹不得仅用客户端hash。
        var left = await ReadVersionAsync(actor, request.From, cancellationToken);
        // 同一资产/完整scope才构成合法固定版本对。
        var right = await ReadVersionAsync(actor, request.To, cancellationToken);
        if (left.AssetId != right.AssetId || left.Scope.OrganizationId != right.Scope.OrganizationId || !Normalize(left.Scope).SiteIds.SequenceEqual(Normalize(right.Scope).SiteIds, StringComparer.Ordinal)) throw new SemanticOperationException(403, "comparison_asset_scope_conflict");
        // 完整源身份先构造，不执行昂贵图比较即可查询唯一输入回执。
        var identity = DiffIdentity(request.From, request.To, left.AssetId, left.Scope, left.Sources, right.Sources, left.ManifestHash, right.ManifestHash);
        // 真实评估的自身hash、来源、profile、时效和阶段都沿原CheckAssessment核验。
        var assessment = await ResolveImpactAssessmentAsync(actor, request, right.Sources, right.Semantics, cancellationToken);
        // 固定输入包含精确assessment而不包含命令、时间或图遥测。
        var fingerprint = ImpactContractRules.InputFingerprint(identity, request.BaselineKind, assessment.Semantics, assessment.ProfileVersion, assessment.ProfileHash);
        // 相同输入不同命令也只能返回首次报告，过期不得刷新生成时间。
        var existing = await database.ImpactReports.AsNoTracking().SingleOrDefaultAsync(row => row.InputFingerprint == fingerprint, cancellationToken);
        if (existing is not null) return await SaveImpactReceiptAsync(actor, request, identity.Scope, fingerprint, null, cancellationToken);
        if (request.BaselineKind == ImpactBaselineKind.Initial && releases is not null)
        {
            try
            {
                // INITIAL首次引入不能借自比绕过已有active；最终激活仍必须锁后复核。
                await releases.ResolveAsync(actor, identity.AssetId, null, cancellationToken);
                throw new SemanticOperationException(409, "impact_baseline_conflict");
            }
            catch (SemanticOperationException error) when (error.Status == 404 && error.Code == "release_not_found") { }
        }
        if (runtime is not JenaSemanticRuntime actual) throw new SemanticOperationException(503, "comparison_runtime_unavailable");
        // 真实事实和差异从同一个解析预算取得，不二次无界解析。
        var facts = await actual.DiffFactsAsync(left.Sources, right.Sources, cancellationToken);
        // 公共合同再次核验原文/hash/槽位/可信delta一致性。
        var diff = identity with { Sources = facts.Sources };
        ImpactContractRules.ValidateDiffIdentity(diff);
        // 执行完成后才记录首次真实生成时刻。
        var now = ImpactInstant(clock.GetUtcNow());
        // 到期不晚于首次24小时及实际绑定assessment的原期限。
        var expires = ImpactInstant(assessment.ExpiresAtUtc is { } deadline && deadline < now.AddHours(24) ? deadline : now.AddHours(24));
        // 纯有界结论分析只使用已解析事实，未知不等于无影响。
        var report = BuildImpactReport(diff, request.BaselineKind, assessment.Semantics, assessment.ProfileVersion, assessment.ProfileHash, assessment.Eligible, assessment.ErrorCode, facts.Base, facts.Target, now, expires, releases is not null, cancellationToken);
        report = report with { InputFingerprint = fingerprint, CanonicalHash = "" };
        report = report with { CanonicalHash = ImpactContractRules.CanonicalHash(report) };
        report = BoundImpactReport(report);
        return await SaveImpactReceiptAsync(actor, request, identity.Scope, fingerprint, report, cancellationToken);
    }

    /// <summary>先授权报告头范围，再返回校验后的原报告；过期仍允许审计读取。</summary>
    public async Task<ImpactReport> ReadImpactAsync(ActorContext actor, string reportId, CancellationToken cancellationToken)
    {
        DemandRole(actor, false);
        // 授权前不读取可能包含四源正文的ReportJson。
        var head = await database.ImpactReports.AsNoTracking().Where(row => row.ReportId == reportId).Select(row => new { row.OrganizationId, row.SiteIds }).SingleOrDefaultAsync(cancellationToken) ?? throw new SemanticOperationException(404, "impact_report_not_found");
        DemandScope(actor, new ResourceScope { OrganizationId = head.OrganizationId, SiteIds = head.SiteIds });
        // 完整正文仅在明确授权后读取，内容身份与持久索引逐字段重算。
        var record = await database.ImpactReports.AsNoTracking().SingleAsync(row => row.ReportId == reportId, cancellationToken);
        return ReadImpactRecord(record);
    }

    /// <summary>输入advisory锁保证不同key也只有一个生成业务行和审计。</summary>
    private Task<ImpactReport> SaveImpactReceiptAsync(ActorContext actor, GenerateImpactReportRequest request, ResourceScope scope, string fingerprint, ImpactReport? candidate, CancellationToken token)
    {
        // 只在实际创建报告时生成业务审计；幂等回执仍原子保存。
        var created = false;
        return WriteAsync<ImpactReport>(actor, scope, "ontology.impact.generate", request.Command, request, async transactionToken =>
        {
            await database.Database.ExecuteSqlInterpolatedAsync($"SELECT pg_advisory_xact_lock(hashtextextended({"impact-input:" + fingerprint}, 0))", transactionToken);
            // 命令锁之后再取输入锁，所有报告生成路径顺序一致。
            var prior = await database.ImpactReports.AsNoTracking().SingleOrDefaultAsync(row => row.InputFingerprint == fingerprint, transactionToken);
            if (prior is not null) return (ReadImpactRecord(prior), prior.ReportId);
            if (candidate is null) throw new SemanticOperationException(409, "impact_binding_conflict");
            // 真实唯一输入行、命令回执和首次审计共享原WriteAsync事务。
            var report = candidate with { ReportId = Guid.NewGuid().ToString("N") };
            database.ImpactReports.Add(new ImpactReportRecord { ReportId = report.ReportId, InputFingerprint = fingerprint, AssetId = report.Diff.AssetId, OrganizationId = scope.OrganizationId, SiteIds = scope.SiteIds, TargetDraftId = report.Diff.To.Kind == VersionRefKind.Draft ? report.Diff.To.Id : null, TargetRevision = report.Diff.To.Kind == VersionRefKind.Draft ? report.Diff.To.Revision : null, AssessmentId = report.TargetSemantics?.AssessmentId, ReportHash = report.CanonicalHash, ReportJson = JsonSerializer.Serialize(report), GeneratedAtUtc = report.GeneratedAtUtc, ExpiresAtUtc = report.ExpiresAtUtc });
            created = true;
            return (report, report.ReportId);
        }, token, _ => created);
    }

    /// <summary>从持久正文和索引重算报告身份，不刷新原ID/时间或相信声称的hash。</summary>
    private static ImpactReport ReadImpactRecord(ImpactReportRecord record)
    {
        if (Encoding.UTF8.GetByteCount(record.ReportJson) > 8 * 1024 * 1024) throw new SemanticOperationException(409, "impact_binding_conflict");
        try
        {
            // 反序列化自动执行同一严格DTO及证据绑定合同。
            var report = JsonSerializer.Deserialize<ImpactReport>(record.ReportJson)!;
            ImpactContractRules.ValidateReportIdentity(report);
            if (report.ReportId != record.ReportId || report.InputFingerprint != record.InputFingerprint || report.CanonicalHash != record.ReportHash || ImpactContractRules.CanonicalHash(report) != record.ReportHash
                || report.Diff.AssetId != record.AssetId || report.Diff.Scope.OrganizationId != record.OrganizationId || !Normalize(report.Diff.Scope).SiteIds.SequenceEqual(record.SiteIds, StringComparer.Ordinal)
                || (report.Diff.To.Kind == VersionRefKind.Draft ? report.Diff.To.Id : null) != record.TargetDraftId || (report.Diff.To.Kind == VersionRefKind.Draft ? report.Diff.To.Revision : null) != record.TargetRevision
                || report.TargetSemantics?.AssessmentId != record.AssessmentId || report.GeneratedAtUtc != record.GeneratedAtUtc || report.ExpiresAtUtc != record.ExpiresAtUtc || report.ExpiresAtUtc > report.GeneratedAtUtc.AddHours(24)) throw new SemanticOperationException(409, "impact_binding_conflict");
            return report;
        }
        catch (JsonException) { throw new SemanticOperationException(409, "impact_binding_conflict"); }
    }

    /// <summary>以真实目标评估或正式清单恢复策略，缺席保持明确不可发布。</summary>
    private async Task<(PublicationSemantics? Semantics, string ProfileVersion, string ProfileHash, DateTimeOffset? ExpiresAtUtc, bool Eligible, string? ErrorCode)> ResolveImpactAssessmentAsync(ActorContext actor, GenerateImpactReportRequest request, SourceBundle target, PublicationSemantics? released, CancellationToken token)
    {
        // 没有评估时只使用当前策略描述覆盖范围，不伪造assessment ID。
        var current = GetProfile();
        if (request.To.Kind == VersionRefKind.Release)
        {
            if (request.AssessmentId is not null) throw new SemanticOperationException(422, "impact_reference_invalid");
            return (released, released?.ProfileVersion ?? current.Version, released?.ProfileHash ?? current.Hash, null, false, "impact_target_not_draft");
        }
        if (request.AssessmentId is null) return (null, current.Version, current.Hash, null, false, "impact_assessment_required");
        // 先核验真实assessment所属草稿完整scope，再读取其正文。
        var assessment = await ReadAssessmentAsync(actor, request.AssessmentId, token);
        // 持久索引与指定固定目标必须完全对应，不能拿另一资产/修订报告代替。
        var record = await database.Assessments.AsNoTracking().SingleAsync(row => row.AssessmentId == request.AssessmentId, token);
        if (record.DraftId != request.To.Id || record.Revision != request.To.Revision || assessment.DraftId != request.To.Id || assessment.Revision != request.To.Revision || assessment.Hashes != JenaRdfCodec.Hashes(target) || assessment.AssessmentHash != SemanticProfile.AssessmentHash(assessment)) throw new SemanticOperationException(409, "impact_binding_conflict");
        // 真实旧profile可分析保留，但新发布必须通过当前CheckAssessment。
        var semantics = new PublicationSemantics { ProfileVersion = assessment.ProfileVersion, ProfileHash = assessment.ProfileHash, AssessmentId = assessment.AssessmentId, AssessmentHash = assessment.AssessmentHash };
        if (!SemanticProfile.Matches(semantics)) throw new SemanticOperationException(409, "impact_binding_conflict");
        // 评估所绑定真实SHACL报告也必须存在并对应同一来源。
        var validation = await database.Validations.AsNoTracking().SingleOrDefaultAsync(row => row.ReportId == assessment.ValidationReportId, token);
        if (validation is null || validation.DraftId != request.To.Id || validation.Revision != request.To.Revision || validation.BundleHash != assessment.Hashes.BundleHash) throw new SemanticOperationException(409, "impact_binding_conflict");
        // 原SHACL JSON与索引也必须对应同一真实报告，不能只信Conforms列。
        var report = JsonSerializer.Deserialize<SemanticValidationReport>(validation.ReportJson)!;
        if (report.ReportId != validation.ReportId || report.DraftId != request.To.Id || report.Revision != request.To.Revision || report.Hashes != assessment.Hashes || report.Conforms != validation.Conforms || assessment.PublishEligible && (!report.Conforms || report.Kind != ValidationKind.ShaclCore)) throw new SemanticOperationException(409, "impact_binding_conflict");
        // 当前头只用于范围授权，CheckAssessment按固定历史修订核验真实评估内容。
        var owner = await FindAsync(request.To.Id, false, token);
        // 不将当前更高修订冒充本次明确选择的历史版本。
        var fixedDraft = new DraftRecord { DraftId = owner.DraftId, AssetId = owner.AssetId, OrganizationId = owner.OrganizationId, SiteIds = owner.SiteIds, Revision = request.To.Revision!.Value };
        try
        {
            CheckAssessment(assessment, record, fixedDraft, JenaRdfCodec.Hashes(target), validation.ReportId, target);
            return (semantics, assessment.ProfileVersion, assessment.ProfileHash, assessment.ExpiresAtUtc, true, null);
        }
        catch (SemanticOperationException error) when (error.Code is "assessment_expired" or "assessment_not_eligible" or "assessment_binding_conflict")
        {
            return (semantics, assessment.ProfileVersion, assessment.ProfileHash, assessment.ExpiresAtUtc, false, error.Code);
        }
    }

    /// <summary>PostgreSQL timestamp以微秒保存，envelope先向下对齐避免JSON与索引舍入漂移。</summary>
    private static DateTimeOffset ImpactInstant(DateTimeOffset value) => new(value.UtcTicks - value.UtcTicks % 10, TimeSpan.Zero);

    /// <summary>昂贵比较前构造全部已核验原文身份，pending图状态不能伪造为完成。</summary>
    private static VersionDiff DiffIdentity(VersionRef from, VersionRef to, string assetId, ResourceScope scope, SourceBundle left, SourceBundle right, string? baseManifest, string? targetManifest)
    {
        // 固定槽位顺序不能由客户端控制，缺词汇与空字符串分别保留。
        string?[] a = [left.OntologyTurtle, left.ShapesTurtle, left.VocabularyTurtle, left.DataTurtle];
        // 目标四源同样保留原UTF8文本，不做格式归一。
        string?[] b = [right.OntologyTurtle, right.ShapesTurtle, right.VocabularyTurtle, right.DataTurtle];
        // 公共纯验证器逐槽重算来源hash，pending只用于输入指纹而非最终结果。
        var sources = new[] { "ontology", "shapes", "vocabulary", "data" }.Select((name, index) => new SourceVersionDiff { SourceId = name, BaseText = a[index], TargetText = b[index], BaseHash = a[index] is { } old ? OntologyPlatform.Modules.Ontology.Domain.OntologyRules.Hash(old) : null, TargetHash = b[index] is { } changed ? OntologyPlatform.Modules.Ontology.Domain.OntologyRules.Hash(changed) : null, SourceChanged = a[index] != b[index], BaseTripleCount = null, TargetTripleCount = null, Graph = new GraphComparisonResult { Status = GraphComparisonStatus.Indeterminate, Code = "comparison_pending" }, TripleDeltaStatus = TripleDeltaStatus.Indeterminate }).ToArray();
        return new VersionDiff { AssetId = assetId, Scope = Normalize(scope), From = from, To = to, BaseHashes = JenaRdfCodec.Hashes(left), TargetHashes = JenaRdfCodec.Hashes(right), BaseManifestHash = baseManifest, TargetManifestHash = targetManifest, Sources = sources };
    }
}
