using System.Net;
using System.Text.Json;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology.Domain;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>共享Jena并发槽和真实RIOT，仅M1比较采用明确无法确定的预算结果。</summary>
public sealed partial class JenaSemanticRuntime
{
    /// <summary>四源共享5秒和十万搜索节点，任一预算失败撤回全部部分结论。</summary>
    public async Task<SourceComparison[]> CompareSourcesAsync(SourceBundle left, SourceBundle right, CancellationToken cancellationToken)
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
        var results = ids.Select((id, index) => new SourceComparison { SourceId = id, LeftHash = leftSources[index] is { } l ? OntologyRules.Hash(l) : null, RightHash = rightSources[index] is { } r ? OntologyRules.Hash(r) : null, SourceChanged = leftSources[index] != rightSources[index], Graph = new GraphComparisonResult { Status = GraphComparisonStatus.Indeterminate, Code = "comparison_pending" } }).ToArray();
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
            for (var index = 0; index < ids.Length; index++)
            {
                comparison.Check();
                // 即使字节相同仍核对blank预算；完整解析也拒绝相同非法源。
                var equivalent = comparison.Equivalent(parsedLeft[index], parsedRight[index]);
                results[index] = results[index] with { Graph = new GraphComparisonResult { Status = equivalent ? GraphComparisonStatus.Equivalent : GraphComparisonStatus.Different, Code = equivalent ? "graph_equivalent" : "graph_different", VisitedNodes = comparison.VisitedNodes, ElapsedMilliseconds = comparison.ElapsedMilliseconds } };
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
        SourceComparison[] Indeterminate(string code) => results.Select(item => item with { Graph = new GraphComparisonResult { Status = GraphComparisonStatus.Indeterminate, Code = code, VisitedNodes = comparison.VisitedNodes, ElapsedMilliseconds = comparison.ElapsedMilliseconds } }).ToArray();
    }
}
