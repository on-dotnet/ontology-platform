using System.Diagnostics;
using System.Text.Json;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>集合语义下的有界精确空白节点双射；预算覆盖四源全部处理。</summary>
internal sealed class ExactGraphComparison
{
    /// <summary>覆盖解析、细化、搜索和最终集合检查的共享单调时钟。</summary>
    private readonly long started = Stopwatch.GetTimestamp();

    /// <summary>调用方和本次5秒预算的联合取消。</summary>
    private readonly CancellationToken token;

    /// <summary>四源共享的实际搜索节点累计。</summary>
    internal long VisitedNodes { get; private set; }

    /// <summary>单次比较从开始到当前的真实毫秒数。</summary>
    internal long ElapsedMilliseconds => (long)Stopwatch.GetElapsedTime(started).TotalMilliseconds;

    /// <summary>保存整个操作共同使用的取消信号。</summary>
    internal ExactGraphComparison(CancellationToken token) => this.token = token;

    /// <summary>每个处理循环都检查同一预算；绝不将预算耗尽当图不同。</summary>
    internal void Check()
    {
        token.ThrowIfCancellationRequested();
        if (ElapsedMilliseconds >= 5000) throw new ComparisonLimitException("comparison_timeout");
    }

    /// <summary>先去重、分区细化，再穷尽受限双射搜索并核验完整三元组集合。</summary>
    internal bool Equivalent(RdfTriple[] leftTriples, RdfTriple[] rightTriples)
    {
        Check();
        // RDF/JSON中主语带_:前缀而宾语不带，统一仅用于本源局部标识。
        var left = Normalize(leftTriples);
        // 左右blank label永不直接对等，后续只通过双射对应。
        var right = Normalize(rightTriples);
        // 空白节点上限在任何快速判异之前检查，防止越限冒充DIFFERENT。
        var leftBlanks = Blanks(left);
        // 每个源两图分别最多128个空白节点。
        var rightBlanks = Blanks(right);
        if (leftBlanks.Length > 128 || rightBlanks.Length > 128) throw new ComparisonLimitException("blank_node_budget");
        if (left.Length != right.Length || leftBlanks.Length != rightBlanks.Length) return false;
        // 全部非blank三元组必须精确一致，包括typed lexical和语言。
        var rightSet = right.ToHashSet();
        if (leftBlanks.Length == 0) return left.ToHashSet().SetEquals(rightSet);
        // 联合palette确保相同结构在左右图得到相同颜色，不依赖label。
        var colorsLeft = leftBlanks.ToDictionary(value => value, _ => "0", StringComparer.Ordinal);
        // 两个映射分别属于各自源，不能污染下一源。
        var colorsRight = rightBlanks.ToDictionary(value => value, _ => "0", StringComparer.Ordinal);
        // 每次真正分裂至少增加一个颜色类，至多256轮；无分裂即可安全停止。
        for (var round = 0; round < leftBlanks.Length + rightBlanks.Length; round++)
        {
            Check();
            // 邻接签名包括上轮颜色，分区只会细化不会合并。
            var signaturesLeft = Signatures(left, colorsLeft);
            // 右图使用同一构造规则。
            var signaturesRight = Signatures(right, colorsRight);
            // 确定性联合palette不将哈希碰撞作为同构证据。
            var palette = signaturesLeft.Values.Concat(signaturesRight.Values).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).Select((value, index) => (value, index)).ToDictionary(pair => pair.value, pair => pair.index.ToString(System.Globalization.CultureInfo.InvariantCulture), StringComparer.Ordinal);
            // 记录旧颜色类数判断是否出现进一步分裂。
            var previous = colorsLeft.Values.Concat(colorsRight.Values).Distinct(StringComparer.Ordinal).Count();
            colorsLeft = signaturesLeft.ToDictionary(pair => pair.Key, pair => palette[pair.Value], StringComparer.Ordinal);
            colorsRight = signaturesRight.ToDictionary(pair => pair.Key, pair => palette[pair.Value], StringComparer.Ordinal);
            if (!colorsLeft.Values.Order(StringComparer.Ordinal).SequenceEqual(colorsRight.Values.Order(StringComparer.Ordinal), StringComparer.Ordinal)) return false;
            if (palette.Count == previous) break;
        }
        // 只在颜色相同的分区搜索，双射最终仍核对所有三元组。
        var candidates = leftBlanks.ToDictionary(value => value, value => rightBlanks.Where(other => colorsLeft[value] == colorsRight[other]).ToArray(), StringComparer.Ordinal);
        // 高约束节点优先，减少稀疏或对称图的不必要分支。
        var order = leftBlanks.OrderBy(value => candidates[value].Length).ThenByDescending(value => left.Count(triple => IsBlank(triple.Subject, value) || IsBlank(triple.Object, value))).ToArray();
        // 当前部分双射；每层返回时恢复，不跨源复用。
        var mapping = new Dictionary<string, string>(StringComparer.Ordinal);
        // 右侧已占节点确保是双射，不能把两个节点合并。
        var used = new HashSet<string>(StringComparer.Ordinal);
        return Search(0);

        // 只有穷尽全部候选且未超预算才返回false；找到双射需完整集合核验。
        bool Search(int depth)
        {
            Check();
            if (depth == order.Length)
            {
                // 完整映射后每条原三元组恰好出现于目标集合才等价。
                foreach (var triple in left)
                {
                    Check();
                    if (!rightSet.Contains(Map(triple, mapping))) return false;
                }
                return true;
            }
            foreach (var candidate in candidates[order[depth]])
            {
                Check();
                if (used.Contains(candidate)) continue;
                if (++VisitedNodes > 100000) throw new ComparisonLimitException("search_node_budget");
                mapping.Add(order[depth], candidate);
                used.Add(candidate);
                // 已完全映射的边立即剪枝；未映射边保留给后续搜索，不能过早判异。
                var possible = true;
                foreach (var triple in left)
                {
                    Check();
                    if ((triple.Subject.Kind != RdfTermKind.Blank || mapping.ContainsKey(triple.Subject.Value)) && (triple.Object.Kind != RdfTermKind.Blank || mapping.ContainsKey(triple.Object.Value)) && !rightSet.Contains(Map(triple, mapping))) { possible = false; break; }
                }
                if (possible && Search(depth + 1)) return true;
                mapping.Remove(order[depth]);
                used.Remove(candidate);
            }
            return false;
        }
    }

    /// <summary>对所有节点计算完整有向邻接签名，不按度数近似判等。</summary>
    private Dictionary<string, string> Signatures(RdfTriple[] graph, Dictionary<string, string> colors)
    {
        // 每个节点独立签名保留多重邻接及方向。
        var result = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var node in colors.Keys)
        {
            Check();
            // JSON编码每个项防止用户IRI或literal分隔符碰撞。
            var edges = new List<string>();
            foreach (var triple in graph)
            {
                Check();
                if (IsBlank(triple.Subject, node)) edges.Add(JsonSerializer.Serialize(new[] { "out", triple.Predicate, Describe(triple.Object, colors) }));
                if (IsBlank(triple.Object, node)) edges.Add(JsonSerializer.Serialize(new[] { "in", triple.Predicate, Describe(triple.Subject, colors) }));
            }
            result.Add(node, JsonSerializer.Serialize(new { Color = colors[node], Edges = edges.Order(StringComparer.Ordinal).ToArray() }));
        }
        return result;
    }

    /// <summary>标准项精确编码，空白邻居只使用当前分区颜色。</summary>
    private static string Describe(RdfTerm term, Dictionary<string, string> colors) => term.Kind == RdfTermKind.Blank ? "blank:" + colors[term.Value] : JsonSerializer.Serialize(term);

    /// <summary>去重并统一源内blank label前缀，不改变任何非blank RDF项。</summary>
    private RdfTriple[] Normalize(RdfTriple[] graph)
    {
        // 集合去重发生在同构前，不把重复序列化当多条事实。
        var result = new HashSet<RdfTriple>();
        foreach (var triple in graph)
        {
            Check();
            result.Add(triple with { Subject = NormalizeTerm(triple.Subject), Object = NormalizeTerm(triple.Object) });
        }
        return result.ToArray();
    }

    /// <summary>空白节点标签是源内身份，统一已解析label格式。</summary>
    private static RdfTerm NormalizeTerm(RdfTerm term) => term.Kind == RdfTermKind.Blank ? term with { Value = term.Value.StartsWith("_:", StringComparison.Ordinal) ? term.Value[2..] : term.Value } : term;

    /// <summary>收集本图的完整空白节点集合。</summary>
    private static string[] Blanks(RdfTriple[] graph) => graph.SelectMany(triple => new[] { triple.Subject, triple.Object }).Where(term => term.Kind == RdfTermKind.Blank).Select(term => term.Value).Distinct(StringComparer.Ordinal).ToArray();

    /// <summary>显式区分IRI与同名blank label。</summary>
    private static bool IsBlank(RdfTerm term, string value) => term.Kind == RdfTermKind.Blank && term.Value == value;

    /// <summary>将已完整映射的三元组转换为右图项，保留全部非blank词法。</summary>
    private static RdfTriple Map(RdfTriple triple, Dictionary<string, string> mapping) => triple with { Subject = MapTerm(triple.Subject, mapping), Object = MapTerm(triple.Object, mapping) };

    /// <summary>只更改空白节点标识，不能替换IRI或literal值。</summary>
    private static RdfTerm MapTerm(RdfTerm term, Dictionary<string, string> mapping) => term.Kind == RdfTermKind.Blank ? term with { Value = mapping[term.Value] } : term;
}

/// <summary>仅内部受控预算失败，外层统一四源INDETERMINATE。</summary>
internal sealed class ComparisonLimitException : Exception
{
    /// <summary>固定预算原因，不带用户源码。</summary>
    internal string Code { get; }

    /// <summary>保存可公开的有限原因码。</summary>
    internal ComparisonLimitException(string code) => Code = code;
}
