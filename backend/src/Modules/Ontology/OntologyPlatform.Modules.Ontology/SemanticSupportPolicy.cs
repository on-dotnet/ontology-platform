using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>固定M1 asserted-only边界与历史G2策略显式分离。</summary>
public sealed partial class JenaSemanticRuntime
{
    /// <summary>按清单版本选择原始支持规则，历史回验不使用当前草稿策略。</summary>
    private static SemanticDiagnostic[] PublicationSupport(ReleaseManifest manifest, RdfTriple[] triples) => manifest.SchemaVersion switch
    {
        1 when manifest.Semantics is null => LegacySupport(triples),
        2 when manifest.Semantics is not null && SemanticProfile.Matches(manifest.Semantics) => Support(triples, m3: manifest.Semantics.ProfileVersion is "3" or "4", m4: manifest.Semantics.ProfileVersion == "4"),
        _ => throw new SemanticOperationException(409, "release_profile_unsupported")
    };

    /// <summary>仅命名基本事实及有限命名公理可发布；结构编辑仅接受已登记且类型匹配的命名公理。</summary>
    private static SemanticDiagnostic[] Support(RdfTriple[] triples, bool structural = false, bool m3 = true, bool m4 = true)
    {
        // 声明的属性允许简单断言；AnnotationProperty明确作为普通注释而非推理能力。
        var properties = triples.Where(triple => triple.Subject.Kind == RdfTermKind.Iri && triple.Predicate == JenaRdfCodec.Type && triple.Object.Kind == RdfTermKind.Iri && triple.Object.Value is JenaRdfCodec.Owl + "ObjectProperty" or JenaRdfCodec.Owl + "DatatypeProperty" or JenaRdfCodec.Owl + "AnnotationProperty").Select(triple => triple.Subject.Value).ToHashSet(StringComparer.Ordinal);
        // 属性种类按显式声明判定；不把literal关系猜成annotation，也不做隐式推理。
        var objectProperties = triples.Where(triple => triple.Predicate == JenaRdfCodec.Type && triple.Object.Value == JenaRdfCodec.Owl + "ObjectProperty").Select(triple => triple.Subject.Value).ToHashSet(StringComparer.Ordinal);
        // 数据属性简单断言必须保持literal词法项。
        var datatypeProperties = triples.Where(triple => triple.Predicate == JenaRdfCodec.Type && triple.Object.Value == JenaRdfCodec.Owl + "DatatypeProperty").Select(triple => triple.Subject.Value).ToHashSet(StringComparer.Ordinal);
        // 平台原G2来源字段是明确普通元数据，避免把任意自定义谓词放宽成注释。
        var metadata = new[] { "sourceId", "sourceRecordId", "validFromUtc", "validToUtc", "observedAtUtc", "modelVersion", "mappingStatus" }.Select(name => "urn:ontology-platform:vocabulary:" + name).ToHashSet(StringComparer.Ordinal);
        // SKOS明确登记的标签/说明及关系仍仅按原始显式事实处理。
        var skos = new[] { "prefLabel", "altLabel", "hiddenLabel", "notation", "definition", "scopeNote", "note", "broader", "narrower", "related", "inScheme", "topConceptOf", "hasTopConcept", "exactMatch", "closeMatch", "broadMatch", "narrowMatch", "relatedMatch" }.Select(name => "http://www.w3.org/2004/02/skos/core#" + name).ToHashSet(StringComparer.Ordinal);
        // PROV只保留明确登记的来源关系和时间元数据，不宣称PROV推理。
        var provenance = new[] { "wasDerivedFrom", "wasGeneratedBy", "wasAttributedTo", "generatedAtTime", "startedAtTime", "endedAtTime" }.Select(name => "http://www.w3.org/ns/prov#" + name).ToHashSet(StringComparer.Ordinal);
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
                blocked |= m3 && triple.Predicate == JenaRdfCodec.Owl + "deprecated" ? triple.Object.Kind != RdfTermKind.Literal || triple.Object.Datatype != Xsd + "boolean" || triple.Object.Value is not ("true" or "false" or "1" or "0") : !namedAxioms.Contains(triple.Predicate) || triple.Subject.Kind != RdfTermKind.Iri || triple.Object.Kind != RdfTermKind.Iri;
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
                // 普通annotation需明确声明或登记；任意未声明literal/IRI关系均不能猜作注释。
                blocked |= !properties.Contains(triple.Predicate) && !(metadata.Contains(triple.Predicate) && triple.Object.Kind == RdfTermKind.Literal) && !skos.Contains(triple.Predicate) && !provenance.Contains(triple.Predicate) && !(m3 && M3MetadataPredicate(triple.Predicate)) && !(m4 && M4Predicate(triple.Predicate));
                if (objectProperties.Contains(triple.Predicate)) blocked |= triple.Object.Kind != RdfTermKind.Iri;
                if (datatypeProperties.Contains(triple.Predicate)) blocked |= triple.Object.Kind != RdfTermKind.Literal;
            }
            // M2结构编辑额外要求公理两端显式声明；历史发布仍保持原asserted-only白名单。
            if (structural && namedAxioms.Contains(triple.Predicate)) blocked |= !NamedAxiomWellTyped(triple, triples);
            // M1未实现OWL-Time，声明及谓词都不得绕过SOURCE/BLOCKED矩阵。
            blocked |= triple.Predicate.StartsWith(TimeNamespace, StringComparison.Ordinal) && !(m4 && M4Predicate(triple.Predicate)) || (triple.Predicate == JenaRdfCodec.Type && triple.Object.Value.StartsWith(TimeNamespace, StringComparison.Ordinal) && !(m4 && triple.Object.Value is TimeNamespace + "Instant" or TimeNamespace + "Interval"));
            if (blocked) result.Add(new SemanticDiagnostic { Code = triple.Predicate == JenaRdfCodec.Owl + "imports" ? "import_unlocked" : "axiom_unsupported", Severity = DiagnosticSeverity.Error, Message = structural ? "源码完整保留；该图含仅SOURCE或未支持公理，结构改写被阻断。" : "源码完整保留；该公理超出M1命名显式事实子集，发布被阻断，OWL推理未运行。", FocusNode = triple.Subject, Path = triple.Predicate });
        }
        return result.ToArray();
    }

    /// <summary>命名等价/互斥要求两端显式Class，逆属性要求两端显式ObjectProperty。</summary>
    private static bool NamedAxiomWellTyped(RdfTriple triple, RdfTriple[] triples)
    {
        // 只处理本轮三个受控命名公理，不把未知OWL谓词放宽。
        var declaration = triple.Predicate switch
        {
            JenaRdfCodec.Owl + "equivalentClass" or JenaRdfCodec.Owl + "disjointWith" => JenaRdfCodec.Owl + "Class",
            JenaRdfCodec.Owl + "inverseOf" => JenaRdfCodec.Owl + "ObjectProperty",
            _ => null
        };
        return declaration is null || triple.Subject.Kind == RdfTermKind.Iri && triple.Object.Kind == RdfTermKind.Iri &&
            new[] { triple.Subject, triple.Object }.All(term => triples.Any(item => item.Subject == term && item.Predicate == JenaRdfCodec.Type && item.Object.Kind == RdfTermKind.Iri && item.Object.Value == declaration));
    }

    /// <summary>完整编辑前后图均不允许遗留两端类型不符的命名公理。</summary>
    private static void RequireNamedAxiomTypes(RdfTriple[] triples)
    {
        if (triples.Any(triple => triple.Subject.Kind == RdfTermKind.Iri && triple.Object.Kind == RdfTermKind.Iri && !NamedAxiomWellTyped(triple, triples)))
            throw new SemanticOperationException(422, "rdf_edit_invalid");
    }

    /// <summary>只有唯一源匹配真实诊断才宣称来源，否则明确使用bundle。</summary>
    private static string DiagnosticSource(RdfTriple[][] parsed, SemanticDiagnostic diagnostic)
    {
        // Shape安全诊断在独立策略处理，此处支持诊断来自其余三个源。
        var matches = new[] { 0, 2, 3 }.Where(index => parsed[index].Any(triple => triple.Subject == diagnostic.FocusNode && triple.Predicate == diagnostic.Path)).ToArray();
        return matches.Length == 1 ? matches[0] switch { 0 => "ontology", 2 => "vocabulary", _ => "data" } : "bundle";
    }
}
