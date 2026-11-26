"""Offline release checks. Separate schema graphs keep ownership and dependencies observable."""

import csv
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import rdflib
from pyshacl import validate
from rdflib import DCTERMS, Graph, Literal, Namespace, OWL, RDF, RDFS, SH, SKOS, URIRef, XSD
from rdflib.compare import isomorphic, to_canonical_graph
from rdflib.paths import Path as RDFPath
from rdflib.plugins.sparql import prepareQuery
from rdflib.plugins.sparql.algebra import traverse

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT.parent / "samples/steel-industry/ontology"
STL = Namespace("https://w3id.org/ontology-platform/steel/")
UNIT = Namespace("http://qudt.org/vocab/unit/")
KIND = Namespace("http://qudt.org/vocab/quantitykind/")
LICENSE = URIRef("https://www.apache.org/licenses/LICENSE-2.0")
PRACTICE = STL["source/industry-practice"]
RELEASE = STL["ontology/steel"]
VERSION = "0.1.0"
LAYERS = {"core": (), "process": ("core",), "plain": ("core", "process"), "special": ("core", "process")}
VOCAB = (
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#", "http://www.w3.org/2000/01/rdf-schema#",
    "http://www.w3.org/2002/07/owl#", "http://www.w3.org/2001/XMLSchema#",
    "http://www.w3.org/2004/02/skos/core#", "http://purl.org/dc/terms/",
    "http://www.w3.org/ns/shacl#", "http://www.w3.org/ns/prov#", "http://www.w3.org/ns/sosa/",
)
PROPERTIES = (OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty)
TERMS = (OWL.Class, *PROPERTIES, RDFS.Datatype, SKOS.ConceptScheme)
SHAPES = (SH.NodeShape, SH.PropertyShape)
REQUIRED_CQS = {"core": range(1, 9), "process": range(1, 7), "plain": range(1, 3), "special": range(1, 6)}
PROCESS_BATCHES = (
    ({"ironmaking", "steelmaking", "casting"}, {1, 2, 3, 5}),
    ({"rolling", "tubemaking", "heattreatment", "finishing"}, {4, 6}),
)


def local(node):
    return str(node).removeprefix(str(STL))


def named(graph, types):
    return {s for t in types for s in graph.subjects(RDF.type, t) if isinstance(s, URIRef) and s.startswith(STL)}


def merged(graphs):
    result = Graph()
    for g in graphs:
        result += g
    return result


def parse(path):
    try:
        return Graph().parse(path, format="turtle")
    except Exception as exc:
        raise ValueError(f"{path} 解析失败 {exc}") from exc


def header(path):
    layer, stem = path.parent.name, path.stem
    return STL["ontology/" + (layer if layer == stem else f"{layer}/{stem}")]


def without_header(graph):
    heads = set(graph.subjects(RDF.type, OWL.Ontology))
    result = Graph()
    for s, p, o in graph:
        if s not in heads:
            result.add((s, p, o))
    return result


def payload(modules):
    return merged(without_header(g) for path, g in modules.items() if path.stem != path.parent.name)


def release_graph(modules):
    graph = payload(modules)
    graph.add((RELEASE, RDF.type, OWL.Ontology))
    graph.add((RELEASE, OWL.versionIRI, URIRef(f"{RELEASE}/{VERSION}")))
    graph.add((RELEASE, OWL.versionInfo, Literal(VERSION)))
    graph.add((RELEASE, DCTERMS.license, LICENSE))
    for lang, label in (("zh", "钢铁冶金通用本体"), ("en", "Steel manufacturing ontology")):
        graph.add((RELEASE, RDFS.label, Literal(label, lang=lang)))
    return graph


def build(modules):
    # Canonical blank node IDs also stabilize list and constraint ordering between builds.
    output = Graph()
    output += to_canonical_graph(release_graph(modules))
    for prefix, namespace in (("stl", STL), ("unit", UNIT), ("quantitykind", KIND), ("sh", SH),
                              ("sosa", VOCAB[-1]), ("prov", VOCAB[-2])):
        output.bind(prefix, namespace)
    sys.stdout.write(output.serialize(format="turtle"))


def texts(graph, term, predicate, lang):
    return {str(x) for x in graph.objects(term, predicate)
            if isinstance(x, Literal) and x.language == lang and str(x).strip()}


def check_header(path, graph, iri, errors, *, comment=True):
    fields = {OWL.versionIRI: URIRef(f"{iri}/{VERSION}"), OWL.versionInfo: Literal(VERSION),
              DCTERMS.license: LICENSE}
    if set(graph.subjects(RDF.type, OWL.Ontology)) != {iri}:
        errors.append(f"{path} 本体头应唯一且为 {local(iri)}")
    for p, value in fields.items():
        if set(graph.objects(iri, p)) != {value}:
            errors.append(f"{path} 本体头的 {p} 应为 {value}")
    for lang in ("zh", "en"):
        for p in ([RDFS.label, RDFS.comment] if comment else [RDFS.label]):
            if not texts(graph, iri, p, lang):
                errors.append(f"{path} 本体头缺少 {p} @{lang}")


def check_aggregate(path, graph, iri, imports, errors):
    if any(subject != iri for subject in graph.subjects()) or set(graph.objects(iri, OWL.imports)) != imports:
        errors.append(f"{path} 汇总文件必须只有本体头并完整导入下属模块")


def check_metadata(graph, term, module, is_code, errors):
    labels = set(graph.objects(term, RDFS.label))
    if labels != set(graph.objects(term, SKOS.prefLabel)):
        errors.append(f"{local(term)} 的 label 与 prefLabel 不一致")
    for lang in ("zh", "en"):
        if len(texts(graph, term, RDFS.label, lang)) != 1:
            errors.append(f"{local(term)} 的 @{lang} 标签应唯一")
        if (lang == "zh" or not is_code) and not texts(graph, term, SKOS.definition, lang):
            errors.append(f"{local(term)} 缺少 @{lang} 定义")
    if not is_code and not set(graph.objects(term, DCTERMS.source)):
        errors.append(f"{local(term)} 缺少来源")
    if set(graph.objects(term, RDFS.isDefinedBy)) != {module}:
        errors.append(f"{local(term)} 的 isDefinedBy 应为 {local(module)}")


def iris(triple):
    for node in triple:
        if isinstance(node, URIRef):
            yield node
        elif isinstance(node, Literal) and node.datatype:
            yield node.datatype


def query_iris(query, graph):
    namespaces = dict(graph.namespaces())
    for decl in graph.objects(None, SH.declare):
        namespaces[str(graph.value(decl, SH.prefix))] = str(graph.value(decl, SH.namespace))
    result = set()

    def collect(value):
        if isinstance(value, URIRef):
            result.add(value)
        elif isinstance(value, Literal) and value.datatype:
            result.add(value.datatype)
        elif isinstance(value, RDFPath):
            for child in vars(value).values():
                for item in child if isinstance(child, (list, tuple)) else [child]:
                    collect(item)

    traverse(prepareQuery(str(query), initNs=namespaces).algebra, visitPre=collect)
    return result


def check_modules(modules, layers, errors):
    # Index definitions locally, before taking the union. A second file adding
    # statements to somebody else's subject is also a cross-module redefinition.
    owner = {}
    for path, graph in modules.items():
        iri = header(path)
        check_header(path, graph, iri, errors)
        if path.stem == path.parent.name:
            check_aggregate(path, graph, iri, {header(x) for x in modules if x.parent == path.parent and x != path}, errors)
        elif any(graph.triples((None, OWL.imports, None))):
            errors.append(f"{path} 模块不得导入外部或其他模块")
        for s in set(graph.subjects()):
            if not isinstance(s, URIRef):
                continue
            if not s.startswith(STL):
                errors.append(f"{path} 在本地命名空间外定义 {s}")
            if not any(graph.objects(s, RDF.type)):
                errors.append(f"{local(s)} 缺少类型声明")
            if s in owner:
                errors.append(f"{local(s)} 重复定义于 {owner[s]} 和 {path}")
            else:
                owner[s] = path
        for t in named(graph, (*TERMS, SKOS.Concept)):
            code = (t, RDF.type, SKOS.Concept) in graph
            check_metadata(graph, t, iri, code, errors)
            if path.parent.name in ("plain", "special") and not code and (t, RDF.type, RDFS.Datatype) not in graph:
                if not any(v.startswith("下沉理由：") and v[5:].strip() for v in texts(graph, t, RDFS.comment, "zh")):
                    errors.append(f"{local(t)} 缺少下沉理由")
        for t in named(graph, SHAPES):
            if not texts(graph, t, RDFS.comment, "zh"):
                errors.append(f"{local(t)} 缺少形状的中文说明")
    for layer in layers:
        if ROOT / layer / f"{layer}.ttl" not in modules:
            errors.append(f"缺少 {layer} 层汇总")
    return owner


def check_refs(path, graph, owner, allowed_layers, sources, qudt, versions, errors, *, example=False):
    problems = set()
    for triple in graph:
        s, p, o = triple
        if p == DCTERMS.source and o not in sources:
            problems.add(f"{local(s)} 来源未收录 {local(o)}")
        used = set(iris(triple))
        if p in (SH.select, SH.ask):
            used |= query_iris(o, graph)
        for iri in used:
            if iri.startswith(STL):
                target = owner.get(iri) or versions.get(iri)
                if target is None:
                    problems.add(f"悬空 IRI {local(iri)}")
                elif target.parent.name not in allowed_layers:
                    problems.add(f"跨层依赖 {local(iri)} 位于 {target.parent.name}")
            elif str(iri).startswith((str(UNIT), str(KIND))):
                if iri not in qudt:
                    problems.add(f"未登记 QUDT IRI {iri}")
            elif str(iri).startswith(VOCAB):
                continue
            elif iri == o and ((p == DCTERMS.license and o == LICENSE) or
                               (p == RDFS.seeAlso and s in sources and str(o).startswith("https://"))):
                continue
            elif example and re.fullmatch(r"urn:synthetic:steel:[a-z][a-z0-9]*/[^/\s]+", str(iri)):
                continue
            else:
                problems.add(f"未允许的外部 IRI {iri}")
    errors.extend(f"{path.name} {msg}" for msg in sorted(problems))


def check_codes(graph, errors):
    schemes = named(graph, (SKOS.ConceptScheme,))
    codes = named(graph, (SKOS.Concept,))
    seen = set()
    for code in sorted(codes):
        scheme, _, value = str(code).rpartition("/")
        scheme = URIRef(scheme)
        if scheme not in schemes or set(graph.objects(code, SKOS.inScheme)) != {scheme}:
            errors.append(f"{local(code)} 的 IRI 与所属方案不一致")
        name = local(scheme).removeprefix("code/")
        datatype = STL["".join(word.capitalize() for word in name.split("-")) + "Code"]
        notations = set(graph.objects(code, SKOS.notation))
        if not re.fullmatch("[A-Z0-9]{1,10}", value) or (graph.value(datatype, RDF.type) != RDFS.Datatype
                or {n for n in notations if isinstance(n, Literal) and n.datatype == datatype}
                != {Literal(value, datatype=datatype)}):
            errors.append(f"{local(code)} 主代码格式、类型或 IRI 不正确")
        for n in notations:
            if (scheme, n) in seen:
                errors.append(f"{local(scheme)} 代码重复 {n.n3()}")
            seen.add((scheme, n))
        parents = set(graph.objects(code, SKOS.broader))
        top = set(graph.objects(code, SKOS.topConceptOf))
        if top != (set() if parents else {scheme}) or any(
                parent not in codes or (parent, SKOS.inScheme, scheme) not in graph for parent in parents):
            errors.append(f"{local(code)} 的分组与所属方案不一致")
        if (code, SKOS.broader * "+", code) in graph:
            errors.append(f"{local(code)} 代码上下位成环")
    for scheme in schemes:
        if not re.fullmatch(r"code/[a-z]+(?:-[a-z]+)*", local(scheme)):
            errors.append(f"代码方案名无效 {local(scheme)}")


def check_quantities(graph, errors):
    for p in named(graph, (OWL.DatatypeProperty,)):
        ranges = set(graph.objects(p, RDFS.range))
        units = set(graph.objects(p, STL.unit))
        kinds = set(graph.objects(p, STL.quantityKind))
        if XSD.positiveInteger in ranges:
            if units or kinds:
                errors.append(f"序号 {local(p)} 不应带单位或量纲")
        elif ranges & {XSD.decimal, XSD.nonNegativeInteger} or units or kinds:
            if len(units) != 1 or not all(isinstance(u, URIRef) and u.startswith(UNIT) for u in units):
                errors.append(f"{local(p)} 应有一个 QUDT 单位")
            if len(kinds) != 1 or not all(isinstance(k, URIRef) and k.startswith(KIND) for k in kinds):
                errors.append(f"{local(p)} 应有一个 QUDT 量纲")
            if XSD.nonNegativeInteger in ranges and (units != {UNIT.NUM} or kinds != {KIND.Count}):
                errors.append(f"{local(p)} 件数应使用 NUM 和 Count")


def check_core(graph, errors):
    required = {
        OWL.Class: """
            ManufacturingRecord Event Operation Plan ProcessSegment ProcessRoute Equipment Site Area WorkCenter
            WorkUnit MeasuringInstrument SalesOrder SalesOrderLine ProductionOrder ProductionSchedule PersonnelRole
            Material MaterialSpecification MaterialLot MaterialPiece Heat SemiFinishedProduct FinishedProduct
            Package SourceContribution HeatContribution StandardEdition StandardGrade SteelGrade CompositionLimit
            PropertyRequirement DimensionRequirement DeliveryCondition Sampling Sample TestPiece Observation
            MeasurementPoint ChemicalAnalysis ElementResult MechanicalTest TensileTest ImpactTest HardnessTest
            BendTest NondestructiveTest MetallographicExamination InspectionLot LotFormationRule QualityDecision
            QualityDisposition Defect MillCertificate Location StorageArea StorageLocation Crane MovementOrder
            MovementEvent Shipment TransportUnit""",
        OWL.ObjectProperty: """
            executesSegment performedOn partOfEquipment equipmentType processType inputPiece outputPiece
            consumedLot fulfills forOrderLine allocatedTo derivedFrom producedBy hasPart partOf materialCategory
            productForm steelGrade sourceHeat definedIn satisfies steelClassByComposition steelQualityClass
            steelUseClass sampleOf sampleType analysisType testType ndtMethod methodStandard element
            judgementResult dispositionType""",
        OWL.DatatypeProperty: """
            consumedQuantity plannedStartAt plannedEndAt actualStartAt actualEndAt occurredAt sampledAt
            resultAt createdAt recordedAt thickness width grossMass netMass theoreticalMass numericDesignation
            massFraction""",
        OWL.AnnotationProperty: "unit quantityKind",
        SKOS.ConceptScheme: """
            equipment-type process-type product-form material-category chemical-element sample-type analysis-type
            test-type ndt-method defect-type judgement-result disposition-type inspection-document-type
            delivery-condition surface-condition steel-class-composition steel-class-quality steel-class-use
            measurement-item measurement-method contribution-evidence share-basis movement-event-type personnel-role""",
    }
    for kind, names in required.items():
        for name in names.split():
            term = STL[("code/" if kind == SKOS.ConceptScheme else "") + name]
            if (term, RDF.type, kind) not in graph:
                errors.append(f"核心层缺少 {local(term)} 的 {kind} 声明")
    for name in ("MaterialClass", "unitType", "code/unit-type"):
        if (STL[name], None, None) in graph:
            errors.append(f"核心层不得复用 {name}")
    for name, domain, target in (("derivedFrom", STL.Material, STL.Material),
                                 ("sourceHeat", STL.MaterialPiece, STL.Heat)):
        if set(graph.objects(STL[name], RDFS.domain)) != {domain} or set(graph.objects(STL[name], RDFS.range)) != {target}:
            errors.append(f"{name} 应从 {local(domain)} 指向 {local(target)}")


def expect_counts(path):
    expected = Counter()
    for i, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not re.match(r"^\s*#\s*EXPECT\b", line):
            continue
        fields = re.sub(r"^\s*#\s*EXPECT\b", "", line).split()
        if len(fields) != 3:
            raise ValueError(f"{path}:{i} 的 EXPECT 须列明 focus、shape 与组件")
        focus, shape, component = (v.removeprefix("<").removesuffix(">") for v in fields)
        if not focus.startswith(("urn:synthetic:steel:", str(STL))) or not shape.startswith(STL) or not re.fullmatch(
                r"[A-Z][A-Za-z]*ConstraintComponent", component):
            raise ValueError(f"{path}:{i} 的 EXPECT 标识无效")
        expected[URIRef(focus), URIRef(shape), SH[component]] += 1
    return expected


def check_examples(layer, modules, graphs, errors):
    paths = [ROOT / "examples" / f"{layer}{suffix}.ttl" for suffix in ("", "-invalid")]
    available = {layer, *LAYERS[layer]}
    ontology = merged(g for path, g in modules.items() if path.parent.name in available)
    shapes = merged(g for path, g in modules.items() if path.parent.name in available and
                    (path.stem == "shapes" or path.stem.endswith("-shapes")))
    own_shapes = set().union(*(named(g, SHAPES) for path, g in modules.items() if path.parent.name == layer))
    if not own_shapes:
        errors.append(f"{layer} 层缺少具名形状")
    print(f"{layer} 正例 {len(graphs[paths[0]])} 个三元组，反例 {len(graphs[paths[1]])} 个三元组")
    for path in paths:
        if path == paths[0]:
            example = graphs[path]
            for s in set(example.subjects()):
                match = re.fullmatch(r"urn:synthetic:steel:([a-z][a-z0-9]*)/[^/\s]+", str(s))
                classes = {local(t).lower() for t in example.objects(s, RDF.type) if (t, RDF.type, OWL.Class) in ontology}
                if not match or match[1] not in classes:
                    errors.append(f"{path.name} 正例个体 IRI 与类不符 {s}")
                for obj in example.objects(s):
                    if isinstance(obj, URIRef) and obj.startswith("urn:synthetic:") and (obj, RDF.type, None) not in example:
                        errors.append(f"{path.name} 正例中引用了未声明的合成对象 {obj}")
        data = ontology + graphs[path]
        conforms, report, summary = validate(data, shacl_graph=shapes, inference="none",
                                              do_owl_imports=False, advanced=True, abort_on_first=False)
        if path == paths[0]:
            if not conforms:
                errors.append(f"{path.name} 正例违反约束\n{summary}")
            continue
        if not isinstance(report, Graph):
            raise ValueError(f"{path.name} 未返回 SHACL 报告 {summary}")
        expected = expect_counts(path)
        actual = Counter(tuple(report.value(result, p, any=False) for p in
                               (SH.focusNode, SH.sourceShape, SH.sourceConstraintComponent))
                         for result in report.subjects(RDF.type, SH.ValidationResult))
        for title, diff in (("缺少", expected - actual), ("意外", actual - expected)):
            for (focus, shape, component), count in sorted(diff.items()):
                errors.append(f"{path.name} {title} {count} 次 {focus} {local(shape)} {str(component).removeprefix(str(SH))}")
        hit = {shape for _, shape, _ in actual}
        # sh:property cites its child as sourceShape in the validation report.
        for shape in sorted(own_shapes - hit):
            children = set(shapes.objects(shape, SH.property * "+"))
            if children & hit:
                _, isolated, _ = validate(data, shacl_graph=shapes, use_shapes=[str(shape)], advanced=True,
                                          do_owl_imports=False, abort_on_first=False)
                if isinstance(isolated, Graph) and set(isolated.objects(None, SH.sourceShape)) & children:
                    continue
            errors.append(f"{path.name} 未覆盖形状 {local(shape)}")
        if not actual or conforms:
            errors.append(f"{path.name} 未产生预期的违例")
        print(f"{layer} 形状 {len(own_shapes)} 个，反例报告 {actual.total()} 条")
    return ontology + graphs[paths[0]]


def check_queries(layer, graph, errors):
    directory = ROOT / "cq" / layer
    queries = {p.stem for p in directory.glob("*.rq")}
    csvs = {p.stem for p in directory.glob("*.csv")}
    numbers = REQUIRED_CQS[layer]
    if layer == "process":
        modules = {p.stem for p in (ROOT / layer).glob("*.ttl")}
        numbers = set().union(*(questions for batch, questions in PROCESS_BATCHES if modules & batch))
        if not numbers:
            errors.append("工艺层缺少工序模块")
    required = {f"cq{i:02}" for i in numbers}
    for name in sorted(required - queries | (csvs ^ queries)):
        errors.append(f"{layer}/{name} 缺少查询或期望 CSV")
    for name in sorted(queries & csvs):
        try:
            with (directory / f"{name}.csv").open(encoding="utf-8-sig", newline="") as stream:
                reader = csv.reader(stream, strict=True)
                header_row = next(reader, [])
                expected = list(reader)
            result = graph.query((directory / f"{name}.rq").read_text(encoding="utf-8-sig"))
            if result.type != "SELECT" or list(map(str, result.vars)) != header_row:
                raise ValueError("SELECT 变量与 CSV 表头不一致")
            empty = layer == "special" and name == "cq05"
            if empty != (not expected):
                raise ValueError("S5 应为空，其余 CQ 必须有期望行")
            bindings = result.bindings
            if len(bindings) != len(expected):
                raise ValueError(f"期望 {len(expected)} 行，实际 {len(bindings)} 行")
            for i, (row, binding) in enumerate(zip(expected, bindings, strict=True), 2):
                for want, var in zip(row, result.vars, strict=True):
                    value = binding.get(var)
                    if want == ("" if value is None else str(value)):
                        continue
                    if isinstance(value, Literal) and value.datatype and value.eq(Literal(want, datatype=value.datatype)):
                        continue
                    raise ValueError(f"第 {i} 行 {var} 期望 {want!r}，实际 {value!r}")
            print(f"{layer}/{name} 通过，{len(expected)} 行")
        except Exception as exc:
            errors.append(f"{layer}/{name} 失败 {exc}")


def ancestors(graph, term):
    return {term, *graph.objects(term, RDFS.subClassOf * "+")}


def alternatives(graph, node):
    union = graph.value(node, OWL.unionOf)
    return set(graph.items(union)) if union is not None else {node}


def broader_or_equal(graph, old, new):
    # Multiple rdfs:domain/range axioms are intersections. Each new restriction
    # must be implied by the old intersection; union members are alternatives.
    for restriction in new:
        targets = alternatives(graph, restriction)
        if targets & {OWL.Thing, RDFS.Resource}:
            continue
        if not any(all(ancestors(graph, member) & targets for member in alternatives(graph, before))
                   for before in old):
            return False
    return True


def term_kinds(graph):
    kinds = defaultdict(set)
    for kind in (*TERMS, SKOS.Concept):
        for term in named(graph, (kind,)):
            kinds[term].add(kind)
    return kinds


def check_legacy(graph, errors):
    files = sorted(BASELINE.glob("*.ttl"))
    if not files or not (BASELINE / "steel-industry.ttl").is_file():
        raise ValueError("缺少 main 上的 samples/steel-industry/ontology/ 基线")
    old = merged(parse(p) for p in files)
    missing_modules = set(old.objects(None, OWL.imports)) - set(old.subjects(RDF.type, OWL.Ontology))
    if missing_modules:
        raise ValueError(f"#67 基线模块不全 {sorted(map(local, missing_modules))}")
    hierarchy = old + graph
    before, after = term_kinds(old), term_kinds(graph)
    process_modules = {p.stem for p in (ROOT / "process").glob("*.ttl")}
    process_complete = all(batch <= process_modules for batch, _ in PROCESS_BATCHES)
    for term in sorted(before.keys() & after.keys()):
        if before[term] != after[term]:
            errors.append(f"#67 {local(term)} 种类发生变化")
        if OWL.Class in before[term]:
            supers = ancestors(hierarchy, term)
            for x in supers:
                if supers & set(hierarchy.objects(x, OWL.disjointWith)):
                    errors.append(f"#67 {local(term)} 的上位类互不相交 {local(x)}")
        for p, label in ((RDFS.domain, "定义域"), (RDFS.range, "值域")):
            a, b = set(old.objects(term, p)), set(graph.objects(term, p))
            if not broader_or_equal(hierarchy, a, b):
                errors.append(f"#67 {local(term)} {label}收窄：{'、'.join(sorted(map(local, a))) or '未限定'} → "
                              f"{'、'.join(sorted(map(local, b)))}")
        if set(old.objects(term, SKOS.inScheme)) != set(graph.objects(term, SKOS.inScheme)):
            errors.append(f"#67 {local(term)} 的代码方案归属发生变化")
    # Each old term has one disposition. Future targets must be identified as such.
    with (ROOT / "mappings/samples-steel-industry.sssom.tsv").open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader((line for line in stream if not line.startswith("#")), delimiter="\t", strict=True)
        seen = set()
        for row in reader:
            term = STL[row["subject_id"].removeprefix("stl:")]
            obj = row["object_id"]
            pred = row["predicate_id"]
            if term in seen or term not in before or not row["subject_id"].startswith("stl:"):
                errors.append(f"#67 去向表有重复或未知术语 {local(term)}")
            seen.add(term)
            if term in after:
                if pred != "skos:exactMatch" or obj != row["subject_id"]:
                    errors.append(f"#67 {local(term)} 沿用时须映射到自身")
            elif not obj or not row["comment"].strip():
                errors.append(f"#67 {local(term)} 缺少去向或理由")
            elif obj != "sssom:NoTermFound":
                deferred = "由工艺层 PR 收录" in row["comment"] and not process_complete
                if not obj.startswith("stl:") or (STL[obj[4:]] not in after and not deferred):
                    errors.append(f"#67 {local(term)} 指向未声明的替代术语 {obj}")
        missing = named(old, TERMS) - seen
        if missing:
            errors.append(f"#67 去向表漏项 {'、'.join(sorted(map(local, missing)))}")
    print(f"#67 去向表 {len(seen)} 行，同名比对 {len(before.keys() & after.keys())} 项")


def check_external(graph, errors):
    path = ROOT / "mappings/external.sssom.tsv"
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader((line for line in stream if not line.startswith("#")), delimiter="\t", strict=True))
    targets = set()
    for row in rows:
        subject = row["subject_id"]
        target = row["object_id"]
        targets.add(target.partition(":")[0])
        if not subject.startswith("stl:") or (STL[subject[4:]], RDF.type, None) not in graph:
            errors.append(f"外部映射缺少本地术语 {subject}")
        if row["predicate_id"] not in {"skos:exactMatch", "skos:closeMatch", "skos:broadMatch", "skos:relatedMatch"}:
            errors.append(f"{subject} 外部映射关系无效")
        if not target or not row["object_label"] or not row["mapping_justification"]:
            errors.append(f"{subject} 外部映射缺少对象或依据")
    if not {"iec62264", "prov", "sosa", "epcis"} <= targets:
        errors.append("外部映射未覆盖四种指定模型")


def audit(layers, modules, graphs, errors):
    owner = check_modules(modules, layers, errors)
    ontology = merged(modules.values())
    check_core(merged(g for p, g in modules.items() if p.parent.name == "core"), errors)
    versions = {URIRef(f"{header(p)}/{VERSION}"): p for p in modules}
    sources = {s for p, g in modules.items() if p.stem == "standards" or p.stem.endswith("-standards")
               for s in g.subjects(RDF.type, STL.StandardEdition)}
    sources.add(PRACTICE)
    qudt = {URIRef(line) for line in (ROOT / "check/qudt-units.txt").read_text().splitlines()
            if line and not line.startswith("#")}
    for path in modules:
        layer = path.parent.name
        check_refs(path, modules[path], owner, {layer, *LAYERS[layer]}, sources, qudt, versions, errors)
    root_aggregate = ROOT / "steel.ttl"
    if root_aggregate in graphs:
        check_header(root_aggregate, graphs[root_aggregate], RELEASE, errors)
        check_aggregate(root_aggregate, graphs[root_aggregate], RELEASE, {STL[f"ontology/{l}"] for l in layers}, errors)
    check_codes(ontology, errors)
    check_quantities(ontology, errors)
    for layer in layers:
        try:
            for suffix in ("", "-invalid"):
                path = ROOT / "examples" / f"{layer}{suffix}.ttl"
                if path not in graphs:
                    raise ValueError(f"缺少 {path}")
                check_refs(path, graphs[path], owner, {layer, *LAYERS[layer]}, sources, qudt, versions, errors, example=True)
            graph = check_examples(layer, modules, graphs, errors)
            check_queries(layer, graph, errors)
        except Exception as exc:
            errors.append(f"{layer} 示例检查失败 {exc}")
    path = ROOT / "dist/steel.ttl"
    if path not in graphs:
        errors.append("缺少 dist/steel.ttl，请运行 check.ps1 -Build")
    else:
        dist = graphs[path]
        check_header(path, dist, RELEASE, errors, comment=False)
        if any(dist.triples((None, OWL.imports, None))):
            errors.append("dist/steel.ttl 含 owl:imports")
        if not isomorphic(dist, release_graph(modules)):
            errors.append("dist/steel.ttl 与模块并集不同构")
        size = path.stat().st_size
        if len(dist) > 50_000 or size > 5 * 1024 * 1024:
            errors.append("dist/steel.ttl 超过平台导入上限")
        print(f"dist/steel.ttl {len(dist)} 个三元组，{size} 字节")
    for p, g in modules.items():
        terms = named(g, (OWL.Class, *PROPERTIES, SKOS.ConceptScheme))
        refs = {t for t in terms if sources.intersection(g.objects(t, DCTERMS.source)) - {PRACTICE}}
        common = {t for t in terms if (t, DCTERMS.source, PRACTICE) in g}
        print(f"{p.parent.name}/{p.name}：{len(g)} 个三元组，类 {len(named(g, (OWL.Class,)))}，"
              f"属性 {len(named(g, PROPERTIES))}，方案 {len(named(g, (SKOS.ConceptScheme,)))}，"
              f"代码 {len(named(g, (SKOS.Concept,)))}，书目来源 {len(refs)}，行业通用 {len(common)}")
    check_external(ontology, errors)
    check_legacy(ontology, errors)


def main():
    rdflib.NORMALIZE_LITERALS = False
    errors = []
    try:
        layers = [layer for layer in LAYERS if (ROOT / layer).is_dir()]
        if "core" not in layers:
            raise ValueError("缺少 core 层")
        modules = {path: parse(path) for layer in layers for path in sorted((ROOT / layer).glob("*.ttl"))}
        if sys.argv[1:] == ["build"]:
            build(modules)
            return 0
        if sys.argv[1:]:
            raise ValueError("参数应为空或 build")
        graphs = modules.copy()
        for path in sorted(set(ROOT.rglob("*.ttl")) - modules.keys()):
            graphs[path] = parse(path)
        audit(layers, modules, graphs, errors)
    except Exception as exc:
        errors.append(f"自检失败 {exc}")
    stream = sys.stderr if sys.argv[1:] == ["build"] else sys.stdout
    for error in errors:
        print(error, file=stream)
    print(f"steel check: {str(len(errors)) + ' errors' if errors else 'ok'}", file=stream)
    return int(bool(errors))


if __name__ == "__main__":
    sys.exit(main())
