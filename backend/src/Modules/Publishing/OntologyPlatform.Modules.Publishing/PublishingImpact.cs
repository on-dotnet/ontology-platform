using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Publishing;

/// <summary>发布各关口重核固定报告及active基线，不把影响报告当自动发布许可。</summary>
public sealed partial class PublishingService
{
    /// <summary>影响报告只通过Ontology提供的当前同物理事务reader核验。</summary>
    private Task<ImpactApprovalBinding> LockImpactAsync(ActorContext actor, string? reportId, string? canonicalHash, DraftPublicationSnapshot snapshot, CancellationToken token)
    {
        if (string.IsNullOrWhiteSpace(reportId) || canonicalHash is null) throw new SemanticOperationException(422, "impact_required");
        if (impacts is null) throw new SemanticOperationException(503, "impact_reader_unavailable");
        return impacts.LockForPublicationAsync(actor, reportId, canonicalHash, snapshot, database.Database.GetDbConnection(), database.Database.CurrentTransaction!.GetDbTransaction(), token);
    }

    /// <summary>审核、准备及最终提交必须逐字段匹配原服务器绑定，不能换另一份assessment。</summary>
    private async Task CheckImpactBindingAsync(ActorContext actor, ReleaseProposal proposal, DraftPublicationSnapshot? snapshot, CancellationToken token)
    {
        if (proposal.Kind != ProposalKind.Publish) return;
        if (proposal.Impact is null || snapshot is null) throw new SemanticOperationException(422, "impact_required");
        // 当前报告、源、评估、策略及时间都在同事务重新核验。
        var actual = await LockImpactAsync(actor, proposal.Impact.ReportId, proposal.Impact.CanonicalHash, snapshot, token);
        if (actual != proposal.Impact) throw new SemanticOperationException(409, "impact_binding_conflict");
        await CheckImpactBaselineAsync(proposal.AssetId, proposal.Scope, actual, token);
    }

    /// <summary>只读取本模块已知active和原清单，最终调用位于active锁之后，不持锁访问Jena。</summary>
    private async Task CheckImpactBaselineAsync(string assetId, ResourceScope scope, ImpactApprovalBinding impact, CancellationToken token)
    {
        // 首次和普通版本对明确分支，不能让target自比绕过实际基线。
        var active = await database.ActiveReleases.AsNoTracking().SingleOrDefaultAsync(row => row.AssetId == assetId, token);
        if (impact.BaselineKind == ImpactBaselineKind.Initial)
        {
            if (active is not null || impact.From != impact.To || impact.From.Kind != VersionRefKind.Draft || impact.BaseHashes != impact.TargetHashes || impact.BaseManifestHash is not null) throw new SemanticOperationException(409, "impact_baseline_conflict");
            return;
        }
        if (active is null || active.ReleaseId != impact.From.Id || impact.From.Kind != VersionRefKind.Release || active.OrganizationId != scope.OrganizationId || !active.SiteIds.SequenceEqual(scope.SiteIds, StringComparer.Ordinal)) throw new SemanticOperationException(409, "impact_baseline_conflict");
        // 精确PG正式基线清单hash/source身份必须仍与报告相同，旧版本不被覆盖。
        var release = await database.Releases.AsNoTracking().SingleOrDefaultAsync(row => row.ReleaseId == active.ReleaseId && row.Published, token) ?? throw new SemanticOperationException(409, "impact_baseline_conflict");
        if (release.ManifestHash != impact.BaseManifestHash || PublishingRules.Hash(release.ManifestJson) != impact.BaseManifestHash || release.AssetId != assetId || release.OrganizationId != scope.OrganizationId || !release.SiteIds.SequenceEqual(scope.SiteIds, StringComparer.Ordinal)) throw new SemanticOperationException(409, "impact_baseline_conflict");
        // 原清单仅严格读取，不使用当前draft或另一个Release替换。
        var manifest = JsonSerializer.Deserialize<ReleaseManifest>(release.ManifestJson)!;
        if (manifest.ReleaseId != impact.From.Id || manifest.AssetId != assetId || manifest.Hashes != impact.BaseHashes || manifest.Scope.OrganizationId != scope.OrganizationId || !manifest.Scope.SiteIds.SequenceEqual(scope.SiteIds, StringComparer.Ordinal)) throw new SemanticOperationException(409, "impact_baseline_conflict");
    }
}
