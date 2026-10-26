using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>在Jena执行前检查全部Shapes图，仅接受已登记、无递归的Core子集。</summary>
internal static class ShapePolicy
{
    /// <summary>SHACL标准词汇空间。</summary>
    internal const string Sh = "http://www.w3.org/ns/shacl#";

    /// <summary>唯一允许执行的谓词清单，不允许扩展约束或自定义target。</summary>
    private static readonly HashSet<string> Allowed = new(StringComparer.Ordinal)
    {
        "targetClass", "property", "path", "minCount", "maxCount", "datatype", "class", "nodeKind", "minInclusive", "maxInclusive", "in", "message", "severity", "name", "description"
    };

    /// <summary>拒绝所有未支持谓词和危险形状结构，不执行SPARQL/JS/远程抓取。</summary>
    internal static void Check(RdfTriple[] triples)
    {
        // 本轮只支持NodeShape到单层PropertyShape，路径节点不能再递归引用property。
        if (triples.Any(triple => triple.Predicate == Sh + "property" && triples.Any(candidate => candidate.Subject == triple.Subject && candidate.Predicate == Sh + "path"))) Reject();
        foreach (var triple in triples)
        {
            if (triple.Predicate.StartsWith(Sh, StringComparison.Ordinal))
            {
                if (!Allowed.Contains(triple.Predicate[Sh.Length..])) Reject();
                if (triple.Predicate is Sh + "path" or Sh + "targetClass" or Sh + "datatype" or Sh + "class" && triple.Object.Kind != RdfTermKind.Iri) Reject();
                if (triple.Predicate is Sh + "minCount" or Sh + "maxCount" &&
                    (triple.Object.Kind != RdfTermKind.Literal || !int.TryParse(triple.Object.Value, out var count) || count is < 0 or > 5000)) Reject();
                if (triple.Predicate == Sh + "nodeKind" && !new[] { "IRI", "Literal", "BlankNode", "BlankNodeOrIRI", "BlankNodeOrLiteral", "IRIOrLiteral" }.Any(kind => triple.Object.Value == Sh + kind)) Reject();
                if (triple.Predicate == Sh + "severity" && !new[] { "Violation", "Warning", "Info" }.Any(kind => triple.Object.Value == Sh + kind)) Reject();
                if (triple.Predicate == Sh + "property" && !triples.Any(candidate => candidate.Subject == triple.Object && candidate.Predicate == Sh + "path")) Reject();
                if (triple.Predicate == Sh + "in") CheckList(triples, triple.Object);
            }
            else if (triple.Predicate == JenaRdfCodec.Type)
            {
                if (triple.Object.Value is not (Sh + "NodeShape") and not (Sh + "PropertyShape")) Reject();
            }
            else if (triple.Predicate is not "http://www.w3.org/1999/02/22-rdf-syntax-ns#first" and not "http://www.w3.org/1999/02/22-rdf-syntax-ns#rest") Reject();
        }
    }

    /// <summary>只允许有界无环列表，避免用户输入导致验证器循环。</summary>
    private static void CheckList(RdfTriple[] triples, RdfTerm head)
    {
        // 跟踪已访问列表节点，预算至多128个成员。
        var visited = new HashSet<RdfTerm>();
        // 当前列表项每次沿唯一rdf:rest推进。
        var current = head;
        while (current.Value != "http://www.w3.org/1999/02/22-rdf-syntax-ns#nil")
        {
            if (!visited.Add(current) || visited.Count > 128) Reject();
            // 标准列表必须恰好一个first和rest，不接受歧义图。
            var first = triples.Where(triple => triple.Subject == current && triple.Predicate.EndsWith("#first", StringComparison.Ordinal)).ToArray();
            // 下一个节点由标准rest唯一确定。
            var rest = triples.Where(triple => triple.Subject == current && triple.Predicate.EndsWith("#rest", StringComparison.Ordinal)).ToArray();
            if (first.Length != 1 || rest.Length != 1) Reject();
            current = rest[0].Object;
        }
    }

    /// <summary>使用固定错误码暴露支持边界，原始Shape不进错误日志。</summary>
    private static void Reject() => throw new SemanticOperationException(422, "shape_unsupported");
}
