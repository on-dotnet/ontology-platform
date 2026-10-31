using System.Data.Common;
using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>发布方同物理事务中的影响资格只读复核，不跨模块写表或持锁访问Jena。</summary>
public sealed partial class OntologyService : IImpactPublicationReader
{
    /// <summary>重新核验报告原文身份、目标、评估、策略及期限后冻结完整审批内容。</summary>
    public async Task<ImpactApprovalBinding> LockForPublicationAsync(ActorContext actor, string reportId, string canonicalHash, DraftPublicationSnapshot snapshot, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken)
    {
        DemandRole(actor, false);
        if (!actor.Roles.Any(role => role is "platform.operator" or "platform.auditor")) throw new SemanticOperationException(403, "role_denied");
        if (transaction.Connection != connection) throw new SemanticOperationException(409, "transaction_connection_mismatch");
        if (!ImpactContractRules.IsHash(canonicalHash) || string.IsNullOrWhiteSpace(reportId)) throw new SemanticOperationException(409, "impact_binding_conflict");
        // 独立Ontology上下文只使用调用方已打开连接和当前事务，不另开事务。
        var options = new DbContextOptionsBuilder<OntologyDbContext>().UseNpgsql(connection).Options;
        // 报告不变，无需在draft之后引入反向业务锁；本模块只读自己的表。
        await using var enlisted = new OntologyDbContext(options);
        await enlisted.Database.UseTransactionAsync(transaction, cancellationToken);
        // 授权之前只读取头信息，不读取四源报告正文。
        var head = await enlisted.ImpactReports.AsNoTracking().Where(row => row.ReportId == reportId).Select(row => new { row.OrganizationId, row.SiteIds }).SingleOrDefaultAsync(cancellationToken) ?? throw new SemanticOperationException(404, "impact_report_not_found");
        DemandScope(actor, new ResourceScope { OrganizationId = head.OrganizationId, SiteIds = head.SiteIds });
        // 报告的来源、证据、canonical和全部持久索引均必须自洽。
        var record = await enlisted.ImpactReports.AsNoTracking().SingleAsync(row => row.ReportId == reportId, cancellationToken);
        // 同一算法用于公开读取和发布资格，不存在宽松第二reader。
        var report = ReadImpactRecord(record);
        if (report.CanonicalHash != canonicalHash || report.GeneratedAtUtc > clock.GetUtcNow()) throw new SemanticOperationException(409, "impact_binding_conflict");
        if (report.ExpiresAtUtc <= clock.GetUtcNow()) throw new SemanticOperationException(409, "impact_expired");
        // 目标只能是同事务已经锁读的准确当前草稿与完整四源。
        var target = new VersionRef { Kind = VersionRefKind.Draft, Id = snapshot.Draft.DraftId, Revision = snapshot.Draft.Revision };
        if (report.Diff.To != target || report.Diff.AssetId != snapshot.Draft.AssetId || report.Diff.Scope.OrganizationId != snapshot.Draft.Scope.OrganizationId || !Normalize(report.Diff.Scope).SiteIds.SequenceEqual(Normalize(snapshot.Draft.Scope).SiteIds, StringComparer.Ordinal)
            || report.Diff.TargetHashes != snapshot.Draft.Hashes || JenaRdfCodec.Hashes(snapshot.Draft.Sources) != report.Diff.TargetHashes) throw new SemanticOperationException(409, "impact_target_conflict");
        if (snapshot.Semantics is null || report.TargetSemantics != snapshot.Semantics || report.ProfileVersion != snapshot.Semantics.ProfileVersion || report.ProfileHash != snapshot.Semantics.ProfileHash) throw new SemanticOperationException(409, "impact_binding_conflict");
        if (!report.PublishEligible || report.Blockers.Length > 0 || report.UnknownCoverage.Any(item => item.Blocking)) throw new SemanticOperationException(422, "impact_not_eligible");
        if (report.BaselineKind == ImpactBaselineKind.Initial ? report.Diff.From != report.Diff.To : report.Diff.From.Kind != VersionRefKind.Release || !ImpactContractRules.IsHash(report.Diff.BaseManifestHash)) throw new SemanticOperationException(409, "impact_baseline_conflict");
        // assessment已由LockDraft原检查完整核验，报告到期也不能晚于其真实期限。
        var assessment = await enlisted.Assessments.AsNoTracking().SingleAsync(row => row.AssessmentId == snapshot.Semantics.AssessmentId, cancellationToken);
        // 仅解析模块自己的不可变评估，不调用真实引擎或其它模块表。
        var assessed = System.Text.Json.JsonSerializer.Deserialize<SemanticAssessment>(assessment.AssessmentJson)!;
        if (report.ExpiresAtUtc > assessed.ExpiresAtUtc || report.GeneratedAtUtc < ImpactInstant(assessed.AssessedAtUtc)) throw new SemanticOperationException(409, "impact_binding_conflict");
        return new ImpactApprovalBinding { ReportId = report.ReportId, CanonicalHash = report.CanonicalHash, InputFingerprint = report.InputFingerprint, BaselineKind = report.BaselineKind, From = report.Diff.From, To = report.Diff.To, BaseHashes = report.Diff.BaseHashes, TargetHashes = report.Diff.TargetHashes, BaseManifestHash = report.Diff.BaseManifestHash, TargetSemantics = report.TargetSemantics!, GeneratedAtUtc = report.GeneratedAtUtc, ExpiresAtUtc = report.ExpiresAtUtc };
    }
}
