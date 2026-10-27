using System.Buffers;
using System.Globalization;
using System.Text;
using System.Text.Json;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology.Domain;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>显式映射标准RDF/JSON，不创建自有RDF语法解析器。</summary>
internal static class JenaRdfCodec
{
    /// <summary>标准类型谓词。</summary>
    internal const string Type = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";

    /// <summary>标准标签谓词。</summary>
    internal const string Label = "http://www.w3.org/2000/01/rdf-schema#label";

    /// <summary>OWL词汇命名空间。</summary>
    internal const string Owl = "http://www.w3.org/2002/07/owl#";

    /// <summary>从真实Jena RDF/JSON映射完整三元组，保留词法/语言/空白节点。</summary>
    /// <param name="json">受上游字节预算限制的真实RDF/JSON响应。</param>
    /// <param name="cancellationToken">覆盖响应逐项映射的共享预算信号。</param>
    /// <param name="allowTemporaryMarker">仅内部源解析图可额外容纳一条随后必须核验并剔除的随机标记。</param>
    internal static RdfTriple[] Parse(string json, bool allowTemporaryMarker = false, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        // 文档仅在当前映射周期有效，不把JsonElement跨作用域暴露。
        using var document = JsonDocument.Parse(json);
        // 完整结果受到上游字节预算及此处三元组预算约束。
        var triples = new List<RdfTriple>();
        foreach (var subject in document.RootElement.EnumerateObject())
        {
            cancellationToken.ThrowIfCancellationRequested();
            foreach (var predicate in subject.Value.EnumerateObject())
            {
                cancellationToken.ThrowIfCancellationRequested();
                foreach (var term in predicate.Value.EnumerateArray())
                {
                    cancellationToken.ThrowIfCancellationRequested();
                    triples.Add(new RdfTriple
                    {
                        Subject = new RdfTerm { Kind = subject.Name.StartsWith("_:", StringComparison.Ordinal) ? RdfTermKind.Blank : RdfTermKind.Iri, Value = subject.Name },
                        Predicate = predicate.Name,
                        Object = new RdfTerm
                        {
                            Kind = term.GetProperty("type").GetString() switch { "uri" => RdfTermKind.Iri, "bnode" => RdfTermKind.Blank, "literal" => RdfTermKind.Literal, _ => throw new SemanticOperationException(503, "rdf_response_invalid") },
                            Value = term.GetProperty("value").GetString()!,
                            Datatype = term.TryGetProperty("datatype", out var datatype) ? datatype.GetString() : null,
                            Language = term.TryGetProperty("lang", out var language) ? language.GetString() : null
                        }
                    });
                    if (triples.Count > (allowTemporaryMarker ? 5001 : 5000)) throw new SemanticOperationException(422, "rdf_triple_budget");
                }
            }
        }
        return triples.ToArray();
    }

    /// <summary>计算唯一合同要求的完整源及组合散列。</summary>
    internal static SourceHashes Hashes(SourceBundle sources)
    {
        // 按字段顺序散列；词汇缺席与空字符串为不同事实。
        var hashes = new SourceHashes
        {
            OntologyHash = OntologyRules.Hash(sources.OntologyTurtle),
            ShapesHash = OntologyRules.Hash(sources.ShapesTurtle),
            VocabularyHash = sources.VocabularyTurtle is null ? null : OntologyRules.Hash(sources.VocabularyTurtle),
            DataHash = OntologyRules.Hash(sources.DataTurtle)
        };
        return hashes with { BundleHash = OntologyRules.Hash(string.Join('\n', hashes.OntologyHash, hashes.ShapesHash, hashes.VocabularyHash ?? "absent", hashes.DataHash)) };
    }

    /// <summary>为编辑输出合法N-Triples项；IRI按语法检查，字面量使用兼容转义。</summary>
    internal static string Term(RdfTerm term)
    {
        if (term.Value is null) throw new SemanticOperationException(422, "rdf_term_invalid");
        if (term.Kind == RdfTermKind.Iri)
        {
            if (term.Datatype is not null || term.Language is not null) throw new SemanticOperationException(422, "rdf_term_invalid");
            return "<" + Iri(term.Value) + ">";
        }
        if (term.Kind != RdfTermKind.Literal) throw new SemanticOperationException(422, "blank_edit_unsupported");
        // RIOT可能同时投影rdf:langString与language；只有规范组合能无损导出。
        if (term.Language is not null && term.Datatype is not null && term.Datatype != "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString" ||
            term.Language is null && term.Datatype == "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString")
            throw new SemanticOperationException(422, "rdf_term_invalid");
        if (term.Language is not null && !System.Text.RegularExpressions.Regex.IsMatch(term.Language, "^[a-zA-Z]+(-[a-zA-Z0-9]+)*$"))
            throw new SemanticOperationException(422, "rdf_term_invalid");
        return Literal(term.Value) + (term.Language is not null ? "@" + term.Language : term.Datatype is not null ? "^^<" + Iri(term.Datatype) + ">" : "");
    }

    /// <summary>按Unicode标量导出标准N-Triples字面量，不使用JSON的代理项转义或静默替换。</summary>
    /// <param name="value">必须无损保留的RDF词法值。</param>
    /// <returns>包含引号及必要转义的合法字面量，不包含语言或datatype后缀。</returns>
    private static string Literal(string value)
    {
        // 仅当前字面量的导出缓冲区，权威SourceBundle从未在此改写。
        var output = new StringBuilder("\"");
        // 逐Unicode标量推进，不能把有效非BMP拆成两个独立代理项。
        var remaining = value.AsSpan();
        while (!remaining.IsEmpty)
        {
            // 解码失败必须拒绝，不能沿用Rune枚举器默认的U+FFFD替换行为。
            if (Rune.DecodeFromUtf16(remaining, out var scalar, out var consumed) != OperationStatus.Done)
                throw new SemanticOperationException(422, "rdf_literal_invalid");
            remaining = remaining[consumed..];
            switch (scalar.Value)
            {
                case '"': output.Append("\\\""); break;
                case '\\': output.Append("\\\\"); break;
                case '\n': output.Append("\\n"); break;
                case '\r': output.Append("\\r"); break;
                case '\t': output.Append("\\t"); break;
                case '\b': output.Append("\\b"); break;
                case '\f': output.Append("\\f"); break;
                default:
                    if (Rune.IsControl(scalar)) output.Append("\\u").Append(scalar.Value.ToString("X4", CultureInfo.InvariantCulture));
                    else output.Append(scalar.ToString());
                    break;
            }
        }
        return output.Append('"').ToString();
    }

    /// <summary>阻断会破坏受控IRI项的字符，绝不把任意输入拼接为查询代码。</summary>
    internal static string Iri(string value)
    {
        if (string.IsNullOrEmpty(value) || !Uri.TryCreate(value, UriKind.Absolute, out _) || value.Any(character => char.IsWhiteSpace(character) || char.IsControl(character) || "<>\"{}|^`\\".Contains(character)))
            throw new SemanticOperationException(422, "rdf_iri_invalid");
        return value;
    }

    /// <summary>规范单三元组文本用于稳定边标识和无空白节点差异。</summary>
    internal static string Triple(RdfTriple triple) => Term(triple.Subject) + " <" + Iri(triple.Predicate) + "> " + Term(triple.Object) + " .";

    /// <summary>仅对已明确支持的无空白图进行稳定排序，不能冒称通用图同构。</summary>
    internal static string Canonical(RdfTriple[] triples) => string.Join('\n', triples.Select(Triple).Order(StringComparer.Ordinal));
}
