using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>固定M1 asserted-only边界与历史G2策略显式分离。</summary>
public sealed partial class JenaSemanticRuntime
{
    /// <summary>按清单版本选择原始支持规则，历史回验不使用当前草稿策略。</summary>
    private static SemanticDiagnostic[] PublicationSupport(ReleaseManifest manifest, RdfTriple[] triples) => manifest.SchemaVersion switch
    {
        1 when manifest.Semantics is null => LegacySupport(triples),
        2 when manifest.Semantics is not null && SemanticProfile.Matches(manifest.Semantics) => Support(triples),
        _ => throw new SemanticOperationException(409, "release_profile_unsupported")
    };

    /// <summary>仅命名基本事实及有限命名公理可发布；结构编辑拒绝SOURCE公理。</summary>
    private static SemanticDiagnostic[] Support(RdfTriple[] triples, bool structural = false)
    {
        // 声明的属性允许简单断言；AnnotationProperty明确作为普通注释而非推理能力。
        var properties = triples.Where(triple => triple.Subject.Kind == RdfTermKind.Iri && triple.Predicate == JenaRdfCodec.Type && triple.Object.Kind == RdfTermKind.Iri && triple.Object.Value is JenaRdfCodec.Owl + "ObjectProperty" or JenaRdfCodec.Owl + "DatatypeProperty" or JenaRdfCodec.Owl + "AnnotationProperty").Select(triple => triple.Subject.Value).ToHashSet(StringComparer.Ordinal);
        // 只允许这些显式声明，不把未知OWL或RDFS内建类型当普通业务类型。
        var owlDeclarations = new[] { "Class", "ObjectProperty", "DatatypeProperty", "NamedIndividual", "Ontology", "AnnotationProperty" }.Select(name => JenaRdfCodec.Owl + name).ToHashSet(StringComparer.Ordinal);
        // 有限命名IRI对仅表达原始公理，不执行闭包或一致性证明。
        var namedAxioms = new[] { "equivalentClass", "disjointWith", "inverseOf" }.Select(name => JenaRdfCodec.Owl + name).ToHashSet(StringComparer.Ordinal);
        // 安全诊断保留每项真正的focus/path，不删除任何源码。
        var result = new List<SemanticDiagnostic>();
        foreach (var triple in triples)
        {
            // 所有ontology/vocabulary/data blank表达式均保守阻断；Shapes另走ShapePolicy。
            var blocked = triple.Subject.Kind == RdfTermKind.Blank || triple.Object.Kind == RdfTermKind.Blank;
            if (triple.Predicate.StartsWith(JenaRdfCodec.Owl, StringComparison.Ordinal))
                blocked |= structural || !namedAxioms.Contains(triple.Predicate) || triple.Subject.Kind != RdfTermKind.Iri || triple.Object.Kind != RdfTermKind.Iri;
            else if (triple.Predicate == JenaRdfCodec.Type)
            {
                blocked |= triple.Object.Kind != RdfTermKind.Iri;
                blocked |= triple.Object.Value.StartsWith(JenaRdfCodec.Owl, StringComparison.Ordinal) && !owlDeclarations.Contains(triple.Object.Value);
                blocked |= triple.Object.Value.StartsWith("http://www.w3.org/2000/01/rdf-schema#", StringComparison.Ordinal);
            }
            else if (triple.Predicate.StartsWith("http://www.w3.org/2000/01/rdf-schema#", StringComparison.Ordinal))
            {
                // 命名domain/range/subClassOf不是必填约束，复杂表达式不能发布。
                blocked |= !EditablePredicate(triple.Predicate, []);
                if (triple.Predicate is "http://www.w3.org/2000/01/rdf-schema#domain" or "http://www.w3.org/2000/01/rdf-schema#range" or "http://www.w3.org/2000/01/rdf-schema#subClassOf") blocked |= triple.Object.Kind != RdfTermKind.Iri;
            }
            else if (triple.Predicate.StartsWith("http://www.w3.org/1999/02/22-rdf-syntax-ns#", StringComparison.Ordinal))
            {
                // G2标准reification来源事实仍可显式保留，列表与未知RDF内建不能混入本体。
                blocked |= triple.Predicate is not ("http://www.w3.org/1999/02/22-rdf-syntax-ns#subject" or "http://www.w3.org/1999/02/22-rdf-syntax-ns#predicate" or "http://www.w3.org/1999/02/22-rdf-syntax-ns#object");
            }
            else
            {
                // 普通literal注释及显式SKOS/PROV来源不是OWL推理；任意未声明IRI关系仍阻断。
                blocked |= !properties.Contains(triple.Predicate) && triple.Object.Kind != RdfTermKind.Literal && !triple.Predicate.StartsWith("http://www.w3.org/2004/02/skos/core#", StringComparison.Ordinal) && !triple.Predicate.StartsWith("http://www.w3.org/ns/prov#", StringComparison.Ordinal);
            }
            // M1未实现OWL-Time，声明及谓词都不得绕过SOURCE/BLOCKED矩阵。
            blocked |= triple.Predicate.StartsWith("http://www.w3.org/2006/time#", StringComparison.Ordinal) || (triple.Predicate == JenaRdfCodec.Type && triple.Object.Value.StartsWith("http://www.w3.org/2006/time#", StringComparison.Ordinal));
            if (blocked) result.Add(new SemanticDiagnostic { Code = triple.Predicate == JenaRdfCodec.Owl + "imports" ? "import_unlocked" : "axiom_unsupported", Severity = DiagnosticSeverity.Error, Message = structural ? "源码完整保留；该图含仅SOURCE或未支持公理，结构改写被阻断。" : "源码完整保留；该公理超出M1命名显式事实子集，发布被阻断，OWL推理未运行。", FocusNode = triple.Subject, Path = triple.Predicate });
        }
        return result.ToArray();
    }

    /// <summary>只有唯一源匹配真实诊断才宣称来源，否则明确使用bundle。</summary>
    private static string DiagnosticSource(RdfTriple[][] parsed, SemanticDiagnostic diagnostic)
    {
        // Shape安全诊断在独立策略处理，此处支持诊断来自其余三个源。
        var matches = new[] { 0, 2, 3 }.Where(index => parsed[index].Any(triple => triple.Subject == diagnostic.FocusNode && triple.Predicate == diagnostic.Path)).ToArray();
        return matches.Length == 1 ? matches[0] switch { 0 => "ontology", 2 => "vocabulary", _ => "data" } : "bundle";
    }
}
