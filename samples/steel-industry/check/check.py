"""Check the release fixtures locally; RDF imports are never dereferenced."""

import csv
import re
import sys
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import rdflib
from pyshacl import validate
from rdflib import DCTERMS, OWL, RDF, RDFS, SH, SKOS, XSD, Graph, Literal, Namespace, URIRef
from rdflib.plugins.sparql.algebra import translateQuery, traverse
from rdflib.plugins.sparql.parser import parseQuery
from rdflib.plugins.sparql.parserutils import CompValue

ROOT = Path(__file__).resolve().parent.parent
STL = Namespace("https://w3id.org/ontology-platform/steel/")
SYNTHETIC = "urn:synthetic:steel-industry:"
MODULES = "core steelmaking rolling quality logistics codes standards shapes steel-industry".split()
LICENSE = URIRef("https://www.apache.org/licenses/LICENSE-2.0")
UNIT = "http://qudt.org/vocab/unit/"
KIND = "http://qudt.org/vocab/quantitykind/"
SYNTHETIC_MARKER = URIRef("urn:ontology-platform:vocabulary:synthetic")
CLASSES = """
    ManufacturingRecord Plan Operation Event MaterialPiece Equipment Location SalesOrder SalesOrderLine
    ProductionOrder SteelGrade StandardGrade StandardEdition MaterialSpecification ProcessSegment Heat
    CastSequence Slab HeatContribution Steelmaking Refining ContinuousCasting CuttingPlan Cutting Coil
    HotRolledCoil ColdRolledCoil FullHardCoil AnnealedCoil GalvanizedCoil RecoiledCoil HotRolling
    PicklingAndColdRolling Annealing Galvanizing Recoiling CoilSplitting CoilJoining Packing Package
    Sample Observation MeasurementPoint ChemicalAnalysis ElementResult CompositionLimit MechanicalTest CoatingTest
    InspectionLot QualityDecision QualityDisposition MillCertificate Defect StorageArea StorageLocation
    Crane MovementOrder MovementEvent Shipment
""".split()
OBJECTS = """
    producedOnFurnace unitType castOn castIn steelGrade numberingHeat sourceHeat contribution
    contributedHeat evidenceLevel previousGrade nextGrade fulfills producedBy performedOn inputPiece
    outputPiece derivedFrom coatingType definedIn satisfies requiresGrade allocatedTo partOf sampleOf
    sampleType measuredObject measurementItem measuredAtPoint analysisType testedSample element
    methodStandard assessedObject judgementResult dispositionType defectType previousOrderLine
    nextOrderLine applicableOrderLine coversPiece inspectionDocumentType applicableStandard destination
    movedPiece movementType eventLocation locatedIn shippedPackage shareBasis measurementMethod
    requiresSpecification assessedSpecification forOrderLine forProductionOrder hasPart lotMember
    respondsTo accompaniedBy triggeredBy
""".split()
ORDINALS = """
    unitNumber serialNumber lineNumber row column tier positionInHeat positionInSequence
    strandNumber sequenceInStrand cuttingSequence heatPositionInSequence
""".split()
COUNTS = ["applicableQuantity", "strandCount"]
TEXT_PROPERTIES = "samplePosition reason approvedByRole".split()
NUMERIC_TYPES = {XSD[name] for name in """
    decimal integer float double long int short byte unsignedLong unsignedInt unsignedShort unsignedByte
    nonPositiveInteger negativeInteger nonNegativeInteger positiveInteger
""".split()}
CODE_TABLES = {
    "unit-type": ("unitType", "BOF EAF LF RH CC HSM PLTCM CAL CGL RCL PCK"),
    "disposition-type": ("dispositionType", "RELEASE HOLD DEGRADE REASSIGN CONCESSION REWORK SCRAP"),
    "judgement-result": ("judgementResult", "CONFORM NONCONFORM PENDING"),
    "analysis-type": ("analysisType", "HEAT PROCESS PRODUCT"),
    "sample-type": ("sampleType", "ENDPOINT REFINING TUNDISH PRODUCT MECHANICAL COATING"),
    "share-basis": ("shareBasis", "LENGTH MASS"),
    "measurement-method": ("measurementMethod", "MANUAL AUTOMATIC"),
    "contribution-evidence": ("evidenceLevel", "MEASURED ESTIMATED UNKNOWN"),
    "inspection-document-type": ("inspectionDocumentType", "T21 T22 T31 T32"),
    "coating-type": ("coatingType", "GI GA"),
    "movement-event-type": ("movementType", "LIFT RELEASE LOAD DISPATCH"),
    "chemical-element": ("element", "C SI MN P S ALS N H O"),
    "measurement-item": ("measurementItem", "TEMP OXYACT TENSILE IMPACT COATMASS THICKNESS WIDTH CASTSPEED"),
    "defect-type": ("defectType", ""),
}
# Release fixture quantities, including dimensionless counts and ratios.
QUANTITIES = {
    ("NUM", "Count"): COUNTS,
    ("MilliM", "Length"): ("thickness", "width"),
    ("M", "Length"): ("plannedLength", "actualLength", "startLength", "endLength"),
    ("TONNE", "Mass"): ("grossMass", "netMass", "theoreticalMass"),
    ("DEG_C", "CelsiusTemperature"): ("temperature",),
    ("M-PER-MIN", "LinearVelocity"): ("castingSpeed",),
    ("PERCENT", "DimensionlessRatio"): ("share", "elongationAfterFracture"),
    ("PERCENT", "MassFraction"): ("massFraction", "lowerLimit", "upperLimit"),
    ("PPM", "MassFraction"): ("activeOxygen",),
    ("MegaPA", "Stress"): ("tensileStrength", "lowerYieldStrength", "upperYieldStrength"),
    ("J", "Energy"): ("impactEnergy",),
    ("GM-PER-M2", "MassPerArea"): ("coatingMass", "minimumCoatingMass"),
}
DATA_RANGES = {
    XSD.decimal: [n for names in QUANTITIES.values() for n in names if n not in COUNTS],
    XSD.positiveInteger: ORDINALS,
    XSD.nonNegativeInteger: COUNTS,
    XSD.dateTime: """sampledAt resultAt recordedAt occurredAt plannedStartAt plannedEndAt
        actualStartAt actualEndAt createdAt""".split(),
    XSD.date: ["issuedOn", "validUntilOn"],
    XSD.boolean: ["isTransitionSlab", "isConfirmed"],
}


def local(term):
    return str(term).removeprefix(str(STL))


def check_modules(modules, errors):
    module_ids = {STL["module/" + name] for name in MODULES}
    definitions = {}
    for name, graph in modules.items():
        iri = STL["module/" + name]
        if set(graph.subjects(RDF.type, OWL.Ontology)) != {iri}:
            errors.append(f"{name}.ttl 的本体声明应为 {iri}")
        if set(graph.objects(iri, OWL.versionIRI)) != {URIRef(f"{iri}/0.1.0")}:
            errors.append(f"{name}.ttl 的版本 IRI 应为 {iri}/0.1.0")
        if set(graph.objects(iri, DCTERMS.license)) != {LICENSE}:
            errors.append(f"{name}.ttl 缺少指定的 Apache-2.0 许可或有多余许可")
        for category in (OWL.Class, OWL.ObjectProperty, OWL.DatatypeProperty, OWL.AnnotationProperty):
            for term in graph.subjects(RDF.type, category):
                if not isinstance(term, URIRef):
                    continue  # Anonymous OWL expressions are not vocabulary entries.
                if not term.startswith(STL):
                    errors.append(f"{name}.ttl 在通用层命名空间之外定义了 {term}")
                if term in definitions:
                    errors.append(f"{term} 出现重复声明，见 {definitions[term]}.ttl 和 {name}.ttl")
                definitions[term] = name
        for subject, target in graph.subject_objects(OWL.imports):
            if subject != iri or target not in module_ids - {iri}:
                errors.append(f"{name}.ttl 的导入无效 {subject} → {target}")
        if name == "steel-industry":
            targets = set(graph.objects(iri, OWL.imports))
            if targets != module_ids - {iri}:
                errors.append(f"汇总本体的导入差异 {sorted(targets ^ (module_ids - {iri}))}")


def check_labels(graph, term, errors):
    def texts(predicate, lang):
        return {
            str(value) for value in graph.objects(term, predicate)
            if isinstance(value, Literal) and value.language == lang
        }

    for lang in ("zh", "en"):
        labels = texts(RDFS.label, lang)
        if len(labels) != 1 or not all(v.strip() for v in labels) or labels != texts(SKOS.prefLabel, lang):
            errors.append(f"{term} 应有一个 @{lang} 标签且与首选标签一致")
        if not any(v.strip() for v in texts(SKOS.definition, lang)):
            errors.append(f"{term} 缺少 @{lang} 定义")


def check_terms(graph, data, errors):
    required = {
        OWL.Class: CLASSES,
        OWL.ObjectProperty: OBJECTS,
        OWL.DatatypeProperty: TEXT_PROPERTIES + [n for names in DATA_RANGES.values() for n in names],
        OWL.AnnotationProperty: ["unit", "quantityKind"],
    }
    declared = {}
    for category, names in required.items():
        terms = {s for s in graph.subjects(RDF.type, category) if isinstance(s, URIRef) and s.startswith(STL)}
        declared[category] = terms
        missing = {STL[n] for n in names} - terms
        if missing:
            errors.append(f"{category} 缺少声明 {', '.join(sorted(map(local, missing)))}")
        for term in terms:
            name = local(term)
            pattern = r"[A-Z][a-z][A-Za-z]*" if category == OWL.Class else r"[a-z][A-Za-z]*"
            if not re.fullmatch(pattern, name):
                errors.append(f"{term} 的本地名不符合第 4.2 节")
            check_labels(graph, term, errors)

    props = declared[OWL.ObjectProperty] | declared[OWL.DatatypeProperty] | declared[OWL.AnnotationProperty]
    classes = declared[OWL.Class]
    datatypes = {t for t in graph.subjects(RDF.type, RDFS.Datatype) if isinstance(t, URIRef) and t.startswith(STL)}
    for term in datatypes:
        if not re.fullmatch(r"[A-Z][a-z][A-Za-z]*", local(term)):
            errors.append(f"自定义数据类型 {term} 的本地名不符合规则")
        check_labels(graph, term, errors)
    for predicate, allowed in (
        (RDF.type, classes), (RDFS.domain, classes), (RDFS.range, classes | datatypes),
        (RDFS.subClassOf, classes), (RDFS.subPropertyOf, props), (SH.targetClass, classes),
        (SH["class"], classes), (SH.path, props), (SH.targetSubjectsOf, props), (SH.targetObjectsOf, props),
    ):
        for term in set(graph.objects(None, predicate)):
            if isinstance(term, URIRef) and term.startswith(STL) and term not in allowed:
                errors.append(f"{predicate} 引用了未按相应类型声明的术语 {term}")
    for prop in set(graph.predicates()):
        if prop.startswith(STL) and prop not in props:
            errors.append(f"本体使用了未声明的属性 {prop}")
    for dtype, names in DATA_RANGES.items():
        for name in names:
            if set(graph.objects(STL[name], RDFS.range)) != {dtype}:
                errors.append(f"stl:{name} 的值域应为 {dtype}")

    numeric = set()
    for prop in props:
        ranges = set(graph.objects(prop, RDFS.range))
        if ranges & NUMERIC_TYPES or any(graph.objects(prop, STL.unit)) or any(graph.objects(prop, STL.quantityKind)):
            numeric.add(prop)
        for dtype, pattern in ((XSD.boolean, r"is[A-Z].*"), (XSD.date, r".+On"), (XSD.dateTime, r".+At")):
            if dtype in ranges and not re.fullmatch(pattern, local(prop)):
                errors.append(f"{prop} 的命名与值域 {dtype} 不一致")

    for subject, prop, value in data:
        if prop.startswith(STL) and prop not in props:
            errors.append(f"{subject} 使用未声明的属性 {prop}")
        if prop == RDF.type and isinstance(value, URIRef) and value.startswith(STL) and value not in classes:
            errors.append(f"{subject} 使用未声明的类 {value}")
        if prop.startswith(STL) and isinstance(value, Literal) and value.datatype in NUMERIC_TYPES:
            numeric.add(prop)
    numeric_ranges = {
        name: dtype for dtype, names in DATA_RANGES.items() if dtype in NUMERIC_TYPES for name in names
    }
    for prop in sorted(numeric):
        # Recognise the units used by this pack at a camel-case word boundary.
        if re.search(
            r"(?:Mm|MM|Millimet(?:er|re)s?|M|Met(?:er|re)s?|Tonne?s?|DegC|Celsius|"
            r"Percent|Pct|Ppm|PPM|MPa|Mpa|Megapascals?|J|Joules?|MetresPerMinute|"
            r"GramsPerSquareMetre)$", local(prop)
        ):
            errors.append(f"数值属性 {prop} 的本地名含单位，请将单位记录在 stl:unit")
        name = local(prop)
        dtype = numeric_ranges.get(name, XSD.decimal)
        if prop not in declared[OWL.DatatypeProperty] or set(graph.objects(prop, RDFS.range)) != {dtype}:
            errors.append(f"数值或序号属性 {prop} 应声明为数据属性，值域为 {dtype}")
        for subject, value in data.subject_objects(prop):
            if not isinstance(value, Literal) or value.datatype != dtype or value.ill_typed:
                errors.append(f"{subject} 的 {prop} 应为有效的 {dtype}，实际为 {value.n3()}")
        for annotation, prefix in ((STL.unit, UNIT), (STL.quantityKind, KIND)):
            values = list(graph.objects(prop, annotation))
            if name in ORDINALS:
                if values:
                    errors.append(f"序号 {prop} 不应带有 {annotation}")
                continue
            if len(values) != 1 or not isinstance(values[0], URIRef) or not re.fullmatch(
                re.escape(prefix) + r"[A-Za-z0-9_-]+", str(values[0])
            ):
                errors.append(f"{prop} 应有唯一的 {annotation}，且为 {prefix} 下的 IRI")
        if (prop, STL.unit, URIRef(UNIT + "PPM")) in graph and prop != STL.activeOxygen:
            errors.append(f"{prop} 使用了仅供在线测氧的 unit:PPM")
    for (unit, kind), names in QUANTITIES.items():
        for name in names:
            if ((STL[name], STL.unit, URIRef(UNIT + unit)) not in graph
                    or (STL[name], STL.quantityKind, URIRef(KIND + kind)) not in graph):
                errors.append(f"stl:{name} 应使用 unit:{unit} 和 quantitykind:{kind}")
    print(f"类 {len(classes)}，对象属性 {len(declared[OWL.ObjectProperty])}，"
          f"数据属性 {len(declared[OWL.DatatypeProperty])}，注释属性 {len(declared[OWL.AnnotationProperty])}")


def check_codes(graph, data, errors):
    schemes = set(graph.subjects(RDF.type, SKOS.ConceptScheme))
    concepts = set(graph.subjects(RDF.type, SKOS.Concept))
    expected_schemes = {STL["code/" + name] for name in CODE_TABLES}
    if schemes != expected_schemes:
        errors.append(f"代码方案差异 {sorted(schemes ^ expected_schemes)}")
    codes_by_scheme = defaultdict(set)
    notations = {}
    for code in concepts:
        check_labels(graph, code, errors)
        match = re.fullmatch(r"code/([a-z]+(?:-[a-z]+)*)/([A-Z0-9]{1,10})", local(code))
        if not match:
            errors.append(f"代码 IRI 不符合规则 {code}")
            continue
        name, value = match.groups()
        scheme = STL["code/" + name]
        codes_by_scheme[scheme].add(value)
        if scheme not in schemes or set(graph.objects(code, SKOS.inScheme)) != {scheme}:
            errors.append(f"{code} 的所属方案应为 {scheme}")
        datatype = STL["".join(part.capitalize() for part in name.split("-")) + "Code"]
        terms = list(graph.objects(code, SKOS.notation))
        primary = {v for v in terms if isinstance(v, Literal) and v.datatype == datatype}
        if primary != {Literal(value, datatype=datatype)}:
            errors.append(f"{code} 的主 notation 应为 {value}^^{datatype}")
        seen_types = set()
        for term in terms:
            if (not isinstance(term, Literal) or term.datatype is None or
                    (term.datatype.startswith(STL) and (term.datatype, RDF.type, RDFS.Datatype) not in graph)):
                errors.append(f"{code} 使用未声明的 notation 类型 {term.n3()}")
                continue
            if term.datatype in seen_types:
                errors.append(f"{code} 同一数据类型有多个 notation")
            seen_types.add(term.datatype)
            key = (scheme, term.datatype, str(term))
            if key in notations:
                errors.append(f"{code} 与 {notations[key]} 的 notation 重复")
            notations[key] = code
    for name, (prop, required) in CODE_TABLES.items():
        scheme = STL["code/" + name]
        values = codes_by_scheme[scheme]
        missing = set(required.split()) - values
        minimum = 2 if name in ("coating-type", "share-basis", "measurement-method") else 3
        if missing or not minimum <= len(values) <= 15:
            errors.append(f"{scheme} 应有 {minimum}–15 项，现有 {len(values)} 项，缺项 {sorted(missing)}")
        for subject, value in data.subject_objects(STL[prop]):
            if value not in concepts or (value, SKOS.inScheme, scheme) not in graph:
                errors.append(f"{subject} 的 {prop} 未引用 {scheme} 的代码 {value}")
    for primary, segment in (("PLTCM", "PL"), ("CAL", "CA"), ("CGL", "CG"), ("RCL", "RC")):
        code = STL["code/unit-type/" + primary]
        if (code, SKOS.notation, Literal(segment, datatype=STL.LineSegmentCode)) not in graph:
            errors.append(f"{code} 缺少机组段码 {segment}")
    for result in data.subjects(RDF.type, STL.ElementResult):
        if len(set(data.objects(result, STL.massFraction))) != 1:
            errors.append(f"元素结果 {result} 应有一个以质量百分数记录的 massFraction")
    print(f"代码方案 {len(schemes)}，代码 {len(concepts)}")


def check_references(graph, data, invalid, errors):
    for subject in set(data.subjects()):
        if not isinstance(subject, URIRef) or not subject.startswith(SYNTHETIC):
            errors.append(f"样例个体未使用合成数据命名空间 {subject}")
            continue
        typename, separator, code = str(subject).removeprefix(SYNTHETIC).partition("/")
        types = {local(t).lower() for t in data.objects(subject, RDF.type) if (t, RDF.type, OWL.Class) in graph}
        if not separator or not code or typename not in types:
            errors.append(f"个体 IRI 应以显式类名的小写形式和编码组成 {subject}")
        if not any(isinstance(v, Literal) and v.datatype == XSD.boolean and v.value is True
                   for v in data.objects(subject, SYNTHETIC_MARKER)):
            errors.append(f"{subject} 缺少 op:synthetic true")
    heat = URIRef(SYNTHETIC + "heat/H22600124")
    if set(data.objects(heat, STL.producedOnFurnace)) != {URIRef(SYNTHETIC + "equipment/BOF2")}:
        errors.append("主线 B 的炉次 H22600124 应在 BOF2 冶炼")
    for source in (graph, data, invalid):
        for term in set(source.all_nodes()) | set(source.predicates()):
            iri = term.datatype if isinstance(term, Literal) else term
            if isinstance(iri, URIRef) and iri.startswith(STL):
                name = local(iri)
                if not name.isascii() or re.search(r"\s|%[0-9a-fA-F]{2}", name):
                    errors.append(f"通用层 IRI 含非 ASCII 字符、空格或转义名 {iri}")
    for term in set(graph.all_nodes()) | set(data.all_nodes()):
        if not isinstance(term, URIRef):
            continue
        if term.startswith(STL["std/"]):
            edition, separator, grade = str(term).partition("/grade/")
            if not re.fullmatch(r"std/[a-z]+(?:-[a-z0-9]+)+-[0-9]{4}", local(edition)):
                errors.append(f"标准版次 IRI 格式错误 {edition}")
            if (URIRef(edition), RDF.type, STL.StandardEdition) not in graph:
                errors.append(f"标准版次 {edition} 缺少显式的 stl:StandardEdition 声明")
            if separator:
                names = list(graph.objects(term, SKOS.notation))
                if ((term, RDF.type, STL.StandardGrade) not in graph
                        or set(graph.objects(term, STL.definedIn)) != {URIRef(edition)}
                        or len(names) != 1 or not isinstance(names[0], Literal)
                        or not grade or re.sub(r"[^A-Z0-9]", "-", str(names[0])) != grade):
                    errors.append(f"标准牌号 {term} 的声明、notation 或 definedIn 与 IRI 不符")
        if term.startswith(STL["code/"]) and not any(source_type in {SKOS.ConceptScheme, SKOS.Concept}
                                                     for source_type in graph.objects(term, RDF.type)):
            errors.append(f"引用未声明的代码或方案 {term}")
    bibliography = {
        entry
        for source in (graph, data)
        for kind in (STL.StandardEdition, DCTERMS.BibliographicResource)
        for entry in source.subjects(RDF.type, kind)
        if isinstance(entry, URIRef)
    }
    for source in (graph, data):
        for subject, target in source.subject_objects(DCTERMS.source):
            if target not in bibliography:
                errors.append(f"{subject} 的 dcterms:source 应指向已声明的文献条目，实际为 {target.n3()}")
    if (STL["std/gbt-708-2026"], DCTERMS.replaces, STL["std/gbt-708-2019"]) not in graph:
        errors.append("GB/T 708-2026 缺少指向 2019 版的 dcterms:replaces")


def check_mappings(path, graph):
    required = {
        "subject_id", "subject_label", "predicate_id", "object_id", "object_label",
        "mapping_justification", "author_label", "mapping_date", "comment",
    }
    prefixes = {}
    in_map = False
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for line in stream:
            if not line.startswith("#"):
                header = line
                break
            entry = line.removeprefix("#").removeprefix(" ").rstrip()
            if entry and not entry[0].isspace():
                in_map = entry == "curie_map:"
            elif in_map and entry:
                key, separator, iri = entry.strip().partition(":")
                iri = iri.strip().strip("\"'")
                if not separator or not iri or key in prefixes:
                    raise ValueError(f"curie_map 声明无效或重复 {entry}")
                prefixes[key] = iri
        else:
            raise ValueError("缺少 TSV 表头")
        columns = next(csv.reader([header], delimiter="\t", strict=True))
        if not required.issubset(columns) or len(set(columns)) != len(columns):
            raise ValueError(f"表头有重复或缺少必填列 {sorted(required - set(columns))}")
        reader = csv.DictReader(stream, fieldnames=columns, delimiter="\t", strict=True)
        count = 0
        for count, row in enumerate(reader, 1):
            empty = sorted(key for key in required if not (row[key] or "").strip())
            if empty or None in row:
                raise ValueError(f"第 {count} 条映射缺少必填值 {empty} 或有多余字段")
            for field in ("subject_id", "predicate_id", "object_id", "mapping_justification"):
                prefix, separator, suffix = row[field].partition(":")
                if not separator or not suffix or prefix not in prefixes or re.search(r"\s", row[field]):
                    raise ValueError(f"第 {count} 条映射的 {field} 使用了无效或未声明的 CURIE {row[field]}")
                if field == "subject_id" and (URIRef(prefixes[prefix] + suffix), RDF.type, None) not in graph:
                    raise ValueError(f"第 {count} 条映射的 {row[field]} 未在本体中声明")
    if not count:
        raise ValueError("映射表缺少数据行")
    print(f"SSSOM 映射 {count} 条")


# These parameters produce reports. sh:property delegates to its child shape.
# sh:flags, sh:ignoredProperties and sh:qualifiedValueShape modify a primary parameter.
PARAMETERS = """
    class datatype nodeKind minCount maxCount minExclusive minInclusive maxExclusive maxInclusive
    minLength maxLength pattern languageIn uniqueLang equals disjoint lessThan lessThanOrEquals
    not and or xone node qualifiedMinCount qualifiedMaxCount closed hasValue in
""".split()
COMPONENTS = {SH[p]: SH[p[0].upper() + p[1:] + "ConstraintComponent"] for p in PARAMETERS}
COMPONENTS[SH.sparql] = SH.SPARQLConstraintComponent


def expectations(path):
    counts = Counter()
    for line_no, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not re.match(r"^\s*#\s*EXPECT\b", line):
            continue
        tokens = re.sub(r"^\s*#\s*EXPECT\b", "", line).split()
        tokens = [v[1:-1] if v.startswith("<") and v.endswith(">") else v for v in tokens]
        if (len(tokens) != 3
                or not all(re.fullmatch(r"(?:https?://|urn:)[^<>\s]+", t) for t in tokens[:2])
                or not re.fullmatch(r"[A-Z][A-Za-z0-9]*ConstraintComponent", tokens[2])):
            raise ValueError(f"{path.name}:{line_no} 的 EXPECT 应为完整 focus IRI、完整 shape IRI、组件本地名")
        focus, shape, component = tokens
        counts[URIRef(shape), SH[component], URIRef(focus)] += 1
    if not counts:
        raise ValueError(f"{path.name} 没有 EXPECT 注释")
    return counts


def validate_graph(data, shapes):
    conforms, report, description = validate(
        data_graph=data, shacl_graph=shapes, inference="none", do_owl_imports=False, abort_on_first=False
    )
    if not isinstance(report, Graph):
        raise ValueError(f"SHACL 验证器未返回结果图 {description}")
    return conforms, report, description


def result_counts(report):
    counts = Counter()
    for result in report.subjects(RDF.type, SH.ValidationResult):
        key = tuple(report.value(result, p, any=False) for p in
                    (SH.sourceShape, SH.sourceConstraintComponent, SH.focusNode))
        if None in key:
            raise ValueError(f"SHACL 结果缺少 sourceShape、sourceConstraintComponent 或 focusNode {result}")
        counts[key] += 1
    return counts


def check_coverage(shapes, data, report, counts, errors):
    covered = {(shape, component) for shape, component, _ in counts}
    sparql_hits = set(report.subject_objects(SH.sourceConstraint))
    queries = {(report.value(result, SH.sourceShape), constraint) for result, constraint in sparql_hits}
    total = 0
    for param, component in COMPONENTS.items():
        for shape in set(shapes.subjects(param)):
            if not isinstance(shape, URIRef) or (shape, SH.deactivated, Literal(True)) in shapes:
                continue
            values = set(shapes.objects(shape, param))
            for value in values:
                if param in (SH.closed, SH.uniqueLang) and value.toPython() is False:
                    continue
                if param == SH.sparql and (value, SH.deactivated, Literal(True)) in shapes:
                    continue
                total += 1
                hit = (shape, component) in covered
                if param == SH.sparql:
                    hit = (shape, value) in queries
                elif hit and len(values) > 1:
                    # Core reports omit the parameter value. Test each sibling independently.
                    isolated = Graph()
                    isolated += shapes
                    isolated.set((shape, param, value))
                    _, isolated_report, _ = validate_graph(data, isolated)
                    hit = any(s == shape and c == component for s, c, _ in result_counts(isolated_report))
                if not hit:
                    rule = shapes.value(value, SH.select) if param == SH.sparql else value
                    errors.append(f"反例未覆盖 {shape} {param} {rule}")
    if not total:
        errors.append("shapes.ttl 没有具名 shape 上的可检验约束")
    print(f"具名 shape 上的约束 {total}，反例实际报告 {counts.total()} 条")


def check_invalid(path, data, shapes, errors):
    expected = expectations(path)
    conforms, report, _ = validate_graph(data, shapes)
    if conforms:
        errors.append("反例图意外合规")
    actual = result_counts(report)
    for label, difference in (("缺少", expected - actual), ("未标注", actual - expected)):
        for (shape, component, focus), count in sorted(difference.items()):
            errors.append(f"反例{label} {count} 次：{focus} {shape} {str(component).removeprefix(str(SH))}")
    check_coverage(shapes, data, report, actual, errors)


def cell_value(text, datatype):
    if datatype == XSD.boolean:
        lowered = text.lower()
        if lowered in ("true", "1"):
            return True
        if lowered in ("false", "0"):
            return False
        raise ValueError("布尔值无效")
    if datatype in NUMERIC_TYPES:
        if not re.fullmatch(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?", text):
            raise ValueError("数值无效")
        return Decimal(text)
    if datatype == XSD.dateTime:
        # Compare instants, retaining precision beyond Python's six fractional digits.
        match = re.fullmatch(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(?:\.(\d+))?(Z|[+-]\d\d:\d\d)", text)
        if not match:
            raise ValueError("需要带时区的日期时间")
        whole, fraction, offset = match.groups()
        return datetime.fromisoformat(whole + offset), (fraction or "").rstrip("0")
    if datatype == XSD.date:
        match = re.fullmatch(r"(\d{4}-\d\d-\d\d)(Z|[+-]\d\d:\d\d)?", text)
        if not match:
            raise ValueError("日期无效")
        day, offset = match.groups()
        return datetime.fromisoformat(day + "T00:00:00" + offset) if offset else date.fromisoformat(day)
    return text


def reject_identifier_function(node):
    if isinstance(node, CompValue) and node.name in {
        "Builtin_SUBSTR", "Builtin_REGEX", "Builtin_STRSTARTS", "Builtin_STRAFTER",
        "Builtin_STRBEFORE", "Builtin_CONTAINS", "Builtin_STRENDS",
    }:
        raise ValueError(f"能力问题不得依赖编码解析函数 {node.name.removeprefix('Builtin_')}")


def check_query(name, graph, *, expect_empty=False):
    query = parseQuery((ROOT / "cq" / f"{name}.rq").read_text(encoding="utf-8-sig"))
    if query[1].name != "SelectQuery" or "orderby" not in query[1]:
        raise ValueError("需要包含外层 ORDER BY 的 SELECT 查询")
    if name != "cq14":
        traverse(query[1], visitPre=reject_identifier_function)
    result = graph.query(translateQuery(query))
    with (ROOT / "cq" / f"{name}.csv").open(encoding="utf-8-sig", newline="") as stream:
        expected = csv.reader(stream, strict=True)
        header = next(expected, [])
        if header != list(map(str, result.vars)) or len(header) != len(set(header)):
            raise ValueError(f"CSV 表头 {header} 与 SELECT 变量 {result.vars} 不一致或有重复列")
        rows = [] if expect_empty else list(expected)
    bindings = result.bindings  # An all-unbound SELECT row is still one CSV row.
    if not rows and not expect_empty:
        raise ValueError("CSV 须包含至少一行期望结果")
    if len(rows) != len(bindings):
        raise ValueError(f"期望 {len(rows)} 行，查询返回 {len(bindings)} 行")
    for line_no, (row, binding) in enumerate(zip(rows, bindings, strict=True), 2):
        if len(row) != len(header):
            raise ValueError(f"CSV 第 {line_no} 行应有 {len(header)} 列，实际有 {len(row)} 列")
        for variable, wanted in zip(result.vars, row, strict=True):
            term = binding.get(variable)
            actual = "" if term is None else str(term)
            datatype = term.datatype if isinstance(term, Literal) else None
            try:
                equal = cell_value(actual, datatype) == cell_value(wanted, datatype)
            except ValueError as exc:
                raise ValueError(f"CSV 第 {line_no} 行 {variable} 期望 {wanted!r}，实际 {actual!r}（{exc}）") from exc
            if not equal:
                raise ValueError(f"CSV 第 {line_no} 行 {variable} 期望 {wanted!r}，实际 {actual!r}")
    fixture = (" 正例" if expect_empty else " 反例") if name == "cq14" else ""
    print(f"{name}{fixture} 通过，{len(rows)} 行")


def main():
    # Keep source lexical forms available to SHACL (e.g. a timezone or a malformed value).
    rdflib.NORMALIZE_LITERALS = False
    paths = {name: ROOT / "ontology" / f"{name}.ttl" for name in MODULES}
    paths.update({name: ROOT / "data" / f"{name}.ttl" for name in ("data", "invalid-data")})
    graphs = {}
    errors = []
    for name, path in paths.items():
        try:
            graphs[name] = Graph().parse(path, format="turtle")
        except Exception as exc:
            errors.append(f"{path.relative_to(ROOT)} 解析失败 {exc}")
    if not errors:
        print(f"Turtle 解析通过，{len(graphs)} 个文件")
        ontology = Graph()
        modules = {name: graphs[name] for name in MODULES}
        for module in modules.values():
            ontology += module
        shapes = graphs["shapes"]
        data = graphs["data"]
        invalid = graphs["invalid-data"]
        positive, negative = ontology + data, ontology + invalid

        try:
            conforms, _, description = validate_graph(positive, shapes)
            if not conforms:
                errors.append(f"正例违反约束\n{description}")
            else:
                print("正例 SHACL 合规")
        except Exception as exc:
            errors.append(f"正例验证失败 {exc}")
        try:
            check_invalid(paths["invalid-data"], negative, shapes, errors)
        except Exception as exc:
            errors.append(f"反例验证失败 {exc}")
        for number in range(1, 15):
            name = f"cq{number:02d}"
            try:
                check_query(name, negative if number == 14 else positive)
            except Exception as exc:
                errors.append(f"{name} 失败 {exc}")
        try:
            check_query("cq14", positive, expect_empty=True)
        except Exception as exc:
            errors.append(f"cq14 正例失败 {exc}")
        try:
            check_mappings(ROOT / "ontology" / "mappings.sssom.tsv", ontology)
        except (OSError, ValueError, csv.Error) as exc:
            errors.append(f"SSSOM 映射表失败 {exc}")
        check_modules(modules, errors)
        check_terms(ontology, data, errors)
        check_codes(ontology, data, errors)
        check_references(ontology, data, invalid, errors)
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        print(f"自检失败，共 {len(errors)} 条诊断。", file=sys.stderr)
        return 1
    print("案例自检全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
