using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Publishing;

/// <summary>单独只读Catalog不依赖草稿或PublishingService，避免跨模块DI环。</summary>
public sealed class PublishingCatalog : IReleaseCatalog
{
    /// <summary>只读取本模块正式发布及活动指针。</summary>
    private readonly PublishingDbContext database;

    /// <summary>每次正式解析真实核对对象与版本图。</summary>
    private readonly ReleaseVerifier verifier;

    /// <summary>注入只读查询与真实回验依赖。</summary>
    public PublishingCatalog(PublishingDbContext database, ReleaseVerifier verifier)
    {
        this.database = database;
        this.verifier = verifier;
    }

    /// <summary>从发布ID取得权威资产范围，未授权不访问外部源码。</summary>
    public async Task<ReleaseSummary> ReadAsync(ActorContext actor, string releaseId, CancellationToken cancellationToken)
    {
        PublishingRules.DemandRole(actor);
        // 半准备版本永远不能通过Catalog读取。
        var row = await database.Releases.AsNoTracking().SingleOrDefaultAsync(value => value.ReleaseId == releaseId && value.Published, cancellationToken) ?? throw new SemanticOperationException(404, "release_not_found");
        PublishingRules.DemandScope(actor, new ResourceScope { OrganizationId = row.OrganizationId, SiteIds = row.SiteIds });
        // 真实对象和图故障明确503，不静默切其他活动版。
        var manifest = await verifier.VerifyAsync(row, cancellationToken);
        // 此读取给出当时活动状态；snapshot保持已经选定的不可变版本。
        var active = await database.ActiveReleases.AsNoTracking().SingleOrDefaultAsync(value => value.AssetId == row.AssetId, cancellationToken);
        return new ReleaseSummary { Manifest = manifest, ManifestHash = row.ManifestHash, IsActive = active?.ReleaseId == releaseId, ActivationRevision = active?.Revision ?? 0, Status = active?.ReleaseId == releaseId ? ReleaseStatus.Active : ReleaseStatus.Superseded, TraceId = row.TraceId };
    }

    /// <summary>只解析一次活动指针后固定完整版本，不让查询中途混版。</summary>
    public async Task<ReleaseSummary> ResolveAsync(ActorContext actor, string assetId, string? releaseId, CancellationToken cancellationToken)
    {
        PublishingRules.DemandRole(actor);
        if (releaseId is null)
        {
            // 资产主键永久对应完整scope，不按客户端提供的厂区猜测。
            var active = await database.ActiveReleases.AsNoTracking().SingleOrDefaultAsync(value => value.AssetId == assetId, cancellationToken) ?? throw new SemanticOperationException(404, "release_not_found");
            PublishingRules.DemandScope(actor, new ResourceScope { OrganizationId = active.OrganizationId, SiteIds = active.SiteIds });
            releaseId = active.ReleaseId;
        }
        // 历史ID也必须重新授权并检查所属资产。
        var result = await ReadAsync(actor, releaseId, cancellationToken);
        if (result.Manifest.AssetId != assetId) throw new SemanticOperationException(404, "release_not_found");
        return result;
    }
}
