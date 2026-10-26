using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>通过发布ID和断言散列重新定位证据，无进程缓存依赖，打开时再次授权及hash回验。</summary>
public sealed class EvidenceService : IEvidenceService
{
    /// <summary>重新读取权威发布及完整作用域。</summary>
    private readonly IReleaseCatalog catalog;

    /// <summary>读取同版标准事实及来源断言。</summary>
    private readonly ISemanticRuntime runtime;

    /// <summary>真实不可变源对象校验边界。</summary>
    private readonly IReleaseArtifactStore artifacts;

    /// <summary>独立持久审计。</summary>
    private readonly IAuditTrail audit;

    /// <summary>所有依赖由所属模块提供，不直接读取其他模块表。</summary>
    public EvidenceService(IReleaseCatalog catalog, ISemanticRuntime runtime, IReleaseArtifactStore artifacts, IAuditTrail audit)
    {
        this.catalog = catalog;
        this.runtime = runtime;
        this.artifacts = artifacts;
        this.audit = audit;
    }

    /// <summary>拒绝伪造或跨scope定位，不信任答案携带的对象键和散列。</summary>
    public async Task<EvidenceRef> ReadAsync(ActorContext actor, string evidenceId, CancellationToken cancellationToken)
    {
        try
        {
            QueryRules.DemandActor(actor);
            if (evidenceId.Length != 97 || evidenceId[32] != '.' || !evidenceId[..32].All(char.IsAsciiHexDigitLower) || !evidenceId[33..].All(char.IsAsciiHexDigitLower)) throw new SemanticOperationException(404, "evidence_not_found");
            // 每次调用都读真实Catalog，不使用上次调用留在内存的对象。
            var release = await catalog.ReadAsync(actor, evidenceId[..32], cancellationToken);
            // 对象完整范围授权后，按同一正式snapshot取标准断言。
            var graph = new PublishedGraph(release.Manifest, await runtime.ReadPublishedAsync(release.Manifest.Snapshot, cancellationToken), cancellationToken);
            if (!graph.Evidence.TryGetValue(evidenceId, out var evidence)) throw new SemanticOperationException(404, "evidence_not_found");
            if (!QueryRules.Covers(actor, evidence.Scope)) throw new SemanticOperationException(403, "scope_denied");
            // 只接受刚从manifest定位出的精确引用，真正GET并重新计算字节散列。
            var artifact = release.Manifest.ArtifactObjects.Single(item => item.ObjectKey == evidence.SourceObjectKey && item.Hash == evidence.ContentHash);
            await artifacts.ReadVerifiedAsync(artifact, cancellationToken);
            await QueryRules.AuditAsync(audit, actor, "semantic.evidence.read", "allowed", cancellationToken);
            return evidence;
        }
        catch (SemanticOperationException failure)
        {
            await QueryRules.AuditAsync(audit, actor, "semantic.evidence.read", failure.Status == 403 ? "denied" : "failure", cancellationToken);
            throw;
        }
    }
}
