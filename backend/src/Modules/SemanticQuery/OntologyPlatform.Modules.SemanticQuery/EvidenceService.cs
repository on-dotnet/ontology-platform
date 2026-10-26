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
    private readonly VerifiedReleaseSources sources;

    /// <summary>独立持久审计。</summary>
    private readonly IAuditTrail audit;

    /// <summary>所有依赖由所属模块提供，不直接读取其他模块表。</summary>
    public EvidenceService(IReleaseCatalog catalog, ISemanticRuntime runtime, VerifiedReleaseSources sources, IAuditTrail audit)
    {
        this.catalog = catalog;
        this.runtime = runtime;
        this.sources = sources;
        this.audit = audit;
    }

    /// <summary>拒绝伪造或跨scope定位，不信任答案携带的对象键和散列。</summary>
    public async Task<EvidenceRef> ReadAsync(ActorContext actor, string evidenceId, CancellationToken cancellationToken)
    {
        // 证据读取同样有五秒整体上限，外部取消持续传播。
        using var budget = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        budget.CancelAfter(TimeSpan.FromSeconds(5));
        // 成功审计放在处理catch外，不以第二次审计隐藏真实审计错误。
        EvidenceRef evidence;
        try
        {
            QueryRules.DemandActor(actor);
            if (evidenceId.Length != 97 || evidenceId[32] != '.' || !evidenceId[..32].All(char.IsAsciiHexDigitLower) || !evidenceId[33..].All(char.IsAsciiHexDigitLower)) throw new SemanticOperationException(404, "evidence_not_found");
            // 每次调用都读真实Catalog，不使用上次调用留在内存的对象。
            var release = await catalog.ReadAsync(actor, evidenceId[..32], budget.Token);
            // 原始四源真实GET/hash/UTF8验证后，直接消费SEM与源精确对账的同一批数组。
            var verifiedSources = await sources.ReadAsync(release.Manifest, budget.Token);
            // 不再使用Catalog验证后的独立未校验ReadPublished窗口。
            var graph = new PublishedGraph(release.Manifest, await runtime.ReadVerifiedPublishedAsync(release.Manifest, verifiedSources, budget.Token), budget.Token);
            if (!graph.Evidence.TryGetValue(evidenceId, out evidence!)) throw new SemanticOperationException(404, "evidence_not_found");
            if (!QueryRules.Covers(actor, evidence.Scope)) throw new SemanticOperationException(403, "scope_denied");
            // 证据引用只能命中刚才逐槽位GET核验过的事实源对象。
            if (evidence.SourceObjectKey != release.Manifest.ArtifactObjects[^1].ObjectKey || evidence.ContentHash != release.Manifest.Snapshot.DataHash) throw new SemanticOperationException(503, "published_source_binding_invalid");
            budget.Token.ThrowIfCancellationRequested();
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new SemanticOperationException(503, "query_timeout");
        }
        catch (SemanticOperationException failure)
        {
            await QueryRules.AuditWithinBudgetAsync(audit, actor, "semantic.evidence.read", failure.Status == 403 ? "denied" : "failure", budget.Token, cancellationToken);
            throw;
        }
        await QueryRules.AuditWithinBudgetAsync(audit, actor, "semantic.evidence.read", "allowed", budget.Token, cancellationToken);
        return evidence;
    }
}
