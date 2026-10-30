using System.Net;
using System.Text.Json;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology.Domain;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>共享Jena并发槽和真实RIOT，仅M1比较采用明确无法确定的预算结果。</summary>
public sealed partial class JenaSemanticRuntime : IG3VersionDiffRuntime
{
    /// <summary>四源共享5秒和十万搜索节点，任一预算失败撤回全部部分结论。</summary>
    public async Task<SourceComparison[]> CompareSourcesAsync(SourceBundle left, SourceBundle right, CancellationToken cancellationToken) =>
        (await DiffSourcesAsync(left, right, cancellationToken)).Select(item => new SourceComparison { SourceId = item.SourceId, LeftHash = item.BaseHash, RightHash = item.TargetHash, SourceChanged = item.SourceChanged, Graph = item.Graph }).ToArray();

    /// <summary>在M1同一个总预算中保留原文、真实统计与可靠地面delta，不二次解析。</summary>
    public Task<SourceVersionDiff[]> DiffSourcesAsync(SourceBundle left, SourceBundle right, CancellationToken cancellationToken) =>
        DiffSourcesCoreAsync(left, right, cancellationToken, null);

    /// <summary>影响分析取得同一次有界解析的事实，不在图预算之外再次访问RIOT。</summary>
    internal async Task<(SourceVersionDiff[] Sources, RdfTriple[][]? Base, RdfTriple[][]? Target)> DiffFactsAsync(SourceBundle left, SourceBundle right, CancellationToken cancellationToken)
    {
        // 原始blank事实只在模块内短暂保留，绝不进入canonical三元组delta。
        RdfTriple[][]? original = null;
        // 右侧事实保持本次独立解析作用域。
        RdfTriple[][]? target = null;
        // 两个消费者共享同一5秒解析/同构/统计执行。
        var sources = await DiffSourcesCoreAsync(left, right, cancellationToken, (a, b) => { original = a; target = b; });
        return (sources, original, target);
    }

    /// <summary>复用当前支持策略识别实际未覆盖公理，不下载imports或执行推理。</summary>
    internal static SemanticDiagnostic[] ImpactSupport(RdfTriple[] triples) => Support(triples);

    /// <summary>所有公开比较用例唯一执行核心，共享图、槽位和失败撤回。</summary>
    private async Task<SourceVersionDiff[]> DiffSourcesCoreAsync(SourceBundle left, SourceBundle right, CancellationToken cancellationToken, Action<RdfTriple[][], RdfTriple[][]>? capture)
    {
        if (left is null || right is null || left.OntologyTurtle is null || left.ShapesTurtle is null || left.DataTurtle is null || right.OntologyTurtle is null || right.ShapesTurtle is null || right.DataTurtle is null || !OntologyRules.WithinSourceBudget(left.OntologyTurtle, left.ShapesTurtle, left.VocabularyTurtle, left.DataTurtle) || !OntologyRules.WithinSourceBudget(right.OntologyTurtle, right.ShapesTurtle, right.VocabularyTurtle, right.DataTurtle))
            throw new SemanticOperationException(413, "source_byte_budget");
        // 同一时限从解析前开始，不按源或HTTP重新计时。
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(5));
        // 搜索计数与单调时间在四源之间共享。
        var comparison = new ExactGraphComparison(timeout.Token);
        // 所有源先保存原字节hash，预算失败时仍能返回准确变化事实。
        string?[] leftSources = [left.OntologyTurtle, left.ShapesTurtle, left.VocabularyTurtle, left.DataTurtle];
        // 缺词汇与空文档不相等，即使图同为空。
        string?[] rightSources = [right.OntologyTurtle, right.ShapesTurtle, right.VocabularyTurtle, right.DataTurtle];
        // 四源固定顺序不能由调用方控制。
        string[] ids = ["ontology", "shapes", "vocabulary", "data"];
        // 结果只在全比较完成后才返回，预算失败会全量覆盖状态。
        var results = ids.Select((id, index) => new SourceVersionDiff { SourceId = id, BaseText = leftSources[index], TargetText = rightSources[index], BaseHash = leftSources[index] is { } l ? OntologyRules.Hash(l) : null, TargetHash = rightSources[index] is { } r ? OntologyRules.Hash(r) : null, SourceChanged = leftSources[index] != rightSources[index], BaseTripleCount = null, TargetTripleCount = null, AddedTriples = [], RemovedTriples = [], TripleDeltaStatus = TripleDeltaStatus.Indeterminate, Graph = new GraphComparisonResult { Status = GraphComparisonStatus.Indeterminate, Code = "comparison_pending" } }).ToArray();
        // 每次操作独占临时图，finally精确删除本次创建的图。
        var graphs = new List<string>();
        // 只有取得槽位才能释放；已取消请求仍必须返回四个明确结果。
        var acquired = false;
        try
        {
            comparison.Check();
            acquired = await Slots.WaitAsync(0, timeout.Token);
            if (!acquired) throw new SemanticOperationException(429, "semantic_busy");
            // 比较不受Shape支持策略阻断，但所有源仍必须是合法Turtle且左右各总5000条。
            var parsedLeft = await ParseSourcesAsync(left, graphs, timeout.Token, checkShapes: false);
            // 右侧不能复用左侧blank作用域，实际另行RIOT解析。
            var parsedRight = await ParseSourcesAsync(right, graphs, timeout.Token, checkShapes: false);
            capture?.Invoke(parsedLeft, parsedRight);
            for (var index = 0; index < ids.Length; index++)
            {
                comparison.Check();
                // 即使字节相同仍核对blank预算；完整解析也拒绝相同非法源。
                var equivalent = comparison.Equivalent(parsedLeft[index], parsedRight[index]);
                // 原始统计来自本次真实RIOT集合，不用零冒充未解析的来源。
                var before = parsedLeft[index].DistinctBy(EditNoOpTriple).ToArray();
                // 右图保持独立blank作用域，不按随机标签对应。
                var after = parsedRight[index].DistinctBy(EditNoOpTriple).ToArray();
                // 地面三元组的键只按既有RDF1.1 no-op规则比较，输出保留原词法项。
                var oldGround = before.Where(GroundDelta).ToDictionary(EditNoOpTriple);
                // 每个源独立集合，空白节点从不进入canonical delta。
                var newGround = after.Where(GroundDelta).ToDictionary(EditNoOpTriple);
                comparison.Check();
                // 含blank变化时仅提供确定地面事实，剩余原始结构仍完整保存在两侧源。
                var hasBlank = before.Concat(after).Any(triple => !GroundDelta(triple));
                results[index] = results[index] with
                {
                    Graph = new GraphComparisonResult { Status = equivalent ? GraphComparisonStatus.Equivalent : GraphComparisonStatus.Different, Code = equivalent ? "graph_equivalent" : "graph_different", VisitedNodes = comparison.VisitedNodes, ElapsedMilliseconds = comparison.ElapsedMilliseconds },
                    BaseTripleCount = before.Length,
                    TargetTripleCount = after.Length,
                    AddedTriples = equivalent ? [] : newGround.Keys.Except(oldGround.Keys).Select(key => newGround[key]).ToArray(),
                    RemovedTriples = equivalent ? [] : oldGround.Keys.Except(newGround.Keys).Select(key => oldGround[key]).ToArray(),
                    TripleDeltaStatus = equivalent ? TripleDeltaStatus.Equivalent : hasBlank ? TripleDeltaStatus.Indeterminate : TripleDeltaStatus.Exact
                };
            }
            comparison.Check();
            return results;
        }
        catch (ComparisonLimitException exception) { return Indeterminate(exception.Code); }
        catch (OperationCanceledException) { return Indeterminate(cancellationToken.IsCancellationRequested ? "comparison_cancelled" : "comparison_timeout"); }
        catch (HttpRequestException) { throw new SemanticOperationException(503, "semantic_unavailable"); }
        catch (JsonException) { throw new SemanticOperationException(503, "rdf_response_invalid"); }
        finally
        {
            // 清理最多两秒，不使用用户已取消信号，也不改变比较的预算结论。
            using var cleanup = new CancellationTokenSource(TimeSpan.FromSeconds(2));
            try
            {
                foreach (var graph in graphs) await SendAsync(validation, "data?graph=" + Uri.EscapeDataString(graph), HttpMethod.Delete, null, "text/plain", cleanup.Token);
            }
            catch (Exception exception) when (exception is HttpRequestException or OperationCanceledException or SemanticOperationException) { }
            finally { if (acquired) Slots.Release(); }
        }

        // 总体预算失败后全四源撤回结论，保留准确字节变化和hash。
        SourceVersionDiff[] Indeterminate(string code) => results.Select(item => item with { AddedTriples = [], RemovedTriples = [], TripleDeltaStatus = TripleDeltaStatus.Indeterminate, Graph = new GraphComparisonResult { Status = GraphComparisonStatus.Indeterminate, Code = code, VisitedNodes = comparison.VisitedNodes, ElapsedMilliseconds = comparison.ElapsedMilliseconds } }).ToArray();
    }
    /// <summary>可信delta只含命名主体和非blank客体，不能让RIOT随机blank进入hash。</summary>
    private static bool GroundDelta(RdfTriple triple) => triple.Subject.Kind == RdfTermKind.Iri && triple.Object.Kind is RdfTermKind.Iri or RdfTermKind.Literal;
}
