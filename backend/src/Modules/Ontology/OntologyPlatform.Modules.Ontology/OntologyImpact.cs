using System.Text.Json;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>固定版本四源差异与持久影响用例沿用本体权限、原始源及事务边界。</summary>
public sealed partial class OntologyService : IG3ImpactService
{
    /// <summary>先核验固定版本的真实来源和完整scope，再共享M1预算形成可追溯差异。</summary>
    public async Task<VersionDiff> DiffAsync(ActorContext actor, CompareVersionsRequest request, CancellationToken cancellationToken)
    {
        DemandRole(actor, false);
        if (request?.From is null || request.To is null) throw new SemanticOperationException(422, "comparison_reference_invalid");
        try { JsonSerializer.Serialize(request); }
        catch (JsonException) { throw new SemanticOperationException(422, "comparison_reference_invalid"); }
        // 两端分别恢复不可变来源，拒绝未知历史或跨资产授权组合。
        var left = await ReadVersionAsync(actor, request.From, cancellationToken);
        // 右端即使和左端ID相同，也真实核验同修订来源。
        var right = await ReadVersionAsync(actor, request.To, cancellationToken);
        if (left.AssetId != right.AssetId || left.Scope.OrganizationId != right.Scope.OrganizationId || !Normalize(left.Scope).SiteIds.SequenceEqual(Normalize(right.Scope).SiteIds, StringComparer.Ordinal)) throw new SemanticOperationException(403, "comparison_asset_scope_conflict");
        if (runtime is not IG3VersionDiffRuntime comparison) throw new SemanticOperationException(503, "comparison_runtime_unavailable");
        // 一次真实解析/比较同时给出统计和delta，不在总预算之外重新解析。
        var sources = await comparison.DiffSourcesAsync(left.Sources, right.Sources, cancellationToken);
        // 精确manifest身份随固定VersionRef保留，草稿明确为null。
        var result = new VersionDiff { AssetId = left.AssetId, Scope = Normalize(left.Scope), From = request.From, To = request.To, BaseHashes = JenaRdfCodec.Hashes(left.Sources), TargetHashes = JenaRdfCodec.Hashes(right.Sources), BaseManifestHash = left.ManifestHash, TargetManifestHash = right.ManifestHash, Sources = sources };
        ImpactContractRules.ValidateDiffIdentity(result);
        return result;
    }

    /// <summary>报告生成将在下一可运行子切片接入，当前明确不可用而不返回假报告。</summary>
    public Task<ImpactReport> GenerateImpactAsync(ActorContext actor, GenerateImpactReportRequest request, CancellationToken cancellationToken) =>
        throw new SemanticOperationException(503, "impact_implementation_pending");

    /// <summary>报告持久读取尚未接入时明确不可用，不将空报告伪装为成功。</summary>
    public Task<ImpactReport> ReadImpactAsync(ActorContext actor, string reportId, CancellationToken cancellationToken) =>
        throw new SemanticOperationException(503, "impact_implementation_pending");
}
