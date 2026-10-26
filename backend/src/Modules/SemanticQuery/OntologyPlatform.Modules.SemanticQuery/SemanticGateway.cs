using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>REST、MCP和Agent唯一正式执行器，只读固定发布且传播取消。</summary>
public sealed class SemanticGateway : ISemanticGateway
{
    /// <summary>正式发布定位和完整范围授权。</summary>
    private readonly IReleaseCatalog catalog;

    /// <summary>受控真实Jena读取。</summary>
    private readonly ISemanticRuntime runtime;

    /// <summary>唯一机器Schema能力登记。</summary>
    private readonly CapabilityRegistry registry;

    /// <summary>独立持久审计。</summary>
    private readonly IAuditTrail audit;

    /// <summary>服务端UTC观察时间。</summary>
    private readonly TimeProvider clock;

    /// <summary>消费其他模块公共合同，不直接读写其表。</summary>
    public SemanticGateway(IReleaseCatalog catalog, ISemanticRuntime runtime, CapabilityRegistry registry, IAuditTrail audit, TimeProvider clock)
    {
        this.catalog = catalog;
        this.runtime = runtime;
        this.registry = registry;
        this.audit = audit;
        this.clock = clock;
    }

    /// <summary>返回三个实际能力和完整Schema版本。</summary>
    public SemanticCapability[] GetCapabilities() => registry.Read();

    /// <summary>前置失败保留HTTP错误；可信快照取得后才可返回业务六态。</summary>
    public async Task<SemanticQueryResult> ExecuteAsync(ActorContext actor, SemanticQueryPlan plan, CancellationToken cancellationToken)
    {
        // 跟踪中不含输入和源正文。
        using var activity = QueryRules.Activities.StartActivity("semantic.query");
        // 无可信快照时不能构造假release和hash。
        ReleaseManifest? manifest = null;
        // 预算涵盖Catalog与图读取，外部取消仍向上传播。
        using var budget = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        try
        {
            QueryRules.Validate(actor, plan);
            registry.Resolve(plan);
            budget.CancelAfter(plan.TimeoutMs);
            manifest = (await catalog.ResolveAsync(actor, plan.AssetId, plan.ReleaseId, budget.Token)).Manifest;
            if (!QueryRules.Covers(actor, manifest.Scope)) throw new SemanticOperationException(403, "scope_denied");
            if (!manifest.Snapshot.CapabilityVersions.Any(value => value.AssetId == plan.CapabilityId && value.Version == plan.CapabilityVersion)) throw new SemanticOperationException(409, "release_capability_mismatch");
            // 所有后续操作只使用一次固定的正式图。
            var graph = new PublishedGraph(manifest, await runtime.ReadPublishedAsync(manifest.Snapshot, budget.Token), budget.Token);
            if (plan.RelationshipIris.Any(value => !graph.Relationships.Contains(value)) || plan.EntityType is not null && !graph.Description.ClassIris.Contains(plan.EntityType, StringComparer.Ordinal)) throw new SemanticOperationException(422, "query_path_invalid");
            // 实体和关系都从正式标准断言派生。
            var result = Evaluate(actor, plan, manifest, graph, budget.Token);
            await QueryRules.AuditAsync(audit, actor, "semantic.query", result.Status == SemanticQueryStatus.Unauthorized ? "denied" : "allowed", cancellationToken);
            QueryRules.Queries.Add(1, new KeyValuePair<string, object?>("capability", plan.CapabilityId), new KeyValuePair<string, object?>("status", result.Status.ToString()));
            return result;
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            await QueryRules.AuditAsync(audit, actor, "semantic.query", "failure", cancellationToken);
            if (manifest is null) throw new SemanticOperationException(503, "query_timeout");
            return Result(actor, manifest, SemanticQueryStatus.Unavailable, diagnostics: [QueryRules.Diagnostic("query_timeout")]);
        }
        catch (SemanticOperationException failure)
        {
            await QueryRules.AuditAsync(audit, actor, "semantic.query", failure.Status == 403 ? "denied" : "failure", cancellationToken);
            if (manifest is null || failure.Status != 503) throw;
            return Result(actor, manifest, SemanticQueryStatus.Unavailable, diagnostics: [QueryRules.Diagnostic("source_unavailable")]);
        }
        catch (HttpRequestException)
        {
            await QueryRules.AuditAsync(audit, actor, "semantic.query", "failure", cancellationToken);
            if (manifest is null) throw new SemanticOperationException(503, "source_unavailable");
            return Result(actor, manifest, SemanticQueryStatus.Unavailable, diagnostics: [QueryRules.Diagnostic("source_unavailable")]);
        }
    }

    /// <summary>图内等值匹配和有界遍历，不拼接SPARQL或猜测关系。</summary>
    private SemanticQueryResult Evaluate(ActorContext actor, SemanticQueryPlan plan, ReleaseManifest manifest, PublishedGraph graph, CancellationToken token)
    {
        if (plan.CapabilityId == "describe_ontology") return Result(actor, manifest, SemanticQueryStatus.Found, [new SemanticDatum { Kind = SemanticDatumKind.Ontology, Ontology = graph.Description }]);
        if (plan.EntityIri is not null && graph.Entities.TryGetValue(plan.EntityIri, out var requested) && !graph.Visible(actor, requested, plan.SiteId)) return Result(actor, manifest, SemanticQueryStatus.Unauthorized, diagnostics: [QueryRules.Diagnostic("scope_denied")]);
        // 同号候选先授权，不把两个厂身份字符串合并。
        var matches = graph.Entities.Values.Where(entity => graph.Visible(actor, entity, plan.SiteId) && (plan.EntityIri is null || entity.Iri == plan.EntityIri) && (plan.ExternalId is null || entity.ExternalId == plan.ExternalId) && (plan.EntityType is null || entity.TypeIris.Contains(plan.EntityType, StringComparer.Ordinal))).OrderBy(entity => entity.Iri, StringComparer.Ordinal).ToArray();
        if (matches.Length == 0) return Result(actor, manifest, SemanticQueryStatus.Empty);
        if (matches.Length > 1)
        {
            // 先确定全部候选再截断，不把一行预算误判为唯一身份。
            var candidates = matches.Take(plan.MaxRows).Select(entity => new EntityCandidate { EntityIri = entity.Iri, EntityTypeIris = entity.TypeIris, ExternalId = entity.ExternalId, OrganizationId = entity.OrganizationId, SiteId = entity.SiteId, Label = entity.Label, EvidenceIds = graph.DescribeEntity(actor, entity).Properties.Where(value => value.PredicateIri == PublishedGraph.Vocabulary + "externalId").SelectMany(value => value.EvidenceIds).Distinct(StringComparer.Ordinal).ToArray() }).ToArray();
            // 仅返回实际候选引用的来源。
            var evidence = candidates.SelectMany(value => value.EvidenceIds).Distinct(StringComparer.Ordinal).Select(id => graph.Evidence[id]).ToArray();
            return Result(actor, manifest, SemanticQueryStatus.Ambiguous, candidates: candidates, evidence: evidence, limited: matches.Length > plan.MaxRows);
        }
        // 行预算同时计算实体和关系。
        var rows = new List<SemanticDatum>();
        // 每条边两端必须已进入结果。
        var included = new HashSet<string>(StringComparer.Ordinal);
        // 完整三元组去重，保留多对多。
        var seenEdges = new HashSet<RdfTriple>();
        // 队列固定深度，环不重复扩张。
        var queue = new Queue<(SemanticEntity Entity, int Depth)>();
        // 记录真实行预算截断。
        var limited = false;
        AddEntity(matches[0], 0);
        if (plan.CapabilityId == "traverse_relationships")
        {
            while (queue.TryDequeue(out var current))
            {
                token.ThrowIfCancellationRequested();
                if (current.Depth >= plan.Depth) continue;
                foreach (var edge in graph.Triples.Where(value => value.Subject.Value == current.Entity.Iri && graph.Relationships.Contains(value.Predicate) && (plan.RelationshipIris.Length == 0 || plan.RelationshipIris.Contains(value.Predicate, StringComparer.Ordinal))).OrderBy(value => value.Predicate, StringComparer.Ordinal).ThenBy(value => value.Object.Value, StringComparer.Ordinal))
                {
                    token.ThrowIfCancellationRequested();
                    if (edge.Object.Kind != RdfTermKind.Iri || !graph.Entities.TryGetValue(edge.Object.Value, out var target) || !graph.Visible(actor, target, plan.SiteId) || !seenEdges.Add(edge)) continue;
                    if (rows.Count + (included.Contains(target.Iri) ? 1 : 2) > plan.MaxRows)
                    {
                        limited = true;
                        continue;
                    }
                    if (!included.Contains(target.Iri)) AddEntity(target, current.Depth + 1);
                    rows.Add(new SemanticDatum { Kind = SemanticDatumKind.Relationship, Relationship = new SemanticRelationship { SourceIri = current.Entity.Iri, PredicateIri = edge.Predicate, TargetIri = target.Iri, EvidenceIds = graph.For(actor, edge).Select(value => value.EvidenceId).ToArray() } });
                }
            }
        }
        // 仅实际输出断言对应来源进入响应。
        var ids = rows.SelectMany(value => value.Entity is { } entity ? entity.Properties.SelectMany(property => property.EvidenceIds) : value.Relationship!.EvidenceIds).Distinct(StringComparer.Ordinal).ToArray();
        // 缺少reification时保留真实事实但明确PARTIAL。
        var missing = rows.Any(value => value.Entity is { } entity ? entity.Properties.Any(property => property.EvidenceIds.Length == 0) : value.Relationship!.EvidenceIds.Length == 0);
        // 诊断只表达批准的固定信息。
        var diagnostics = new List<SemanticDiagnostic>();
        if (missing) diagnostics.Add(QueryRules.Diagnostic("evidence_missing"));
        if (limited) diagnostics.Add(QueryRules.Diagnostic("query_limited"));
        return Result(actor, manifest, missing || limited ? SemanticQueryStatus.Partial : SemanticQueryStatus.Found, rows.ToArray(), evidence: ids.Select(id => graph.Evidence[id]).ToArray(), limited: limited, diagnostics: diagnostics.ToArray());

        // 添加当前请求已授权实体并保留真实属性来源。
        void AddEntity(SemanticEntity entity, int depth)
        {
            included.Add(entity.Iri);
            rows.Add(new SemanticDatum { Kind = SemanticDatumKind.Entity, Entity = graph.DescribeEntity(actor, entity) });
            queue.Enqueue((entity, depth));
        }
    }

    /// <summary>只使用真实快照、可信Trace和当前观察时间，不伪造业务有效区间。</summary>
    private SemanticQueryResult Result(ActorContext actor, ReleaseManifest manifest, SemanticQueryStatus status, SemanticDatum[]? data = null, EntityCandidate[]? candidates = null, EvidenceRef[]? evidence = null, bool limited = false, SemanticDiagnostic[]? diagnostics = null)
    {
        // 源断言观察时间仍由Evidence单独保留。
        var observed = clock.GetUtcNow();
        return new SemanticQueryResult { Status = status, Data = data ?? [], Candidates = candidates ?? [], Evidence = evidence ?? [], Snapshot = manifest.Snapshot, ObservedAtUtc = observed, TraceId = actor.TraceId, Limited = limited, Diagnostics = diagnostics ?? [], SubSources = [new SemanticSubSource { SourceId = "published-rdf", Status = status == SemanticQueryStatus.Unavailable ? SubSourceStatus.Unavailable : status == SemanticQueryStatus.Empty ? SubSourceStatus.Empty : status == SemanticQueryStatus.Partial ? SubSourceStatus.Partial : SubSourceStatus.Available, ReleaseId = manifest.ReleaseId, DataHash = manifest.Snapshot.DataHash, ObservedAtUtc = observed, Code = diagnostics?.FirstOrDefault()?.Code }] };
    }
}
