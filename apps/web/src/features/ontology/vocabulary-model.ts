import type { OntologyDraft, RdfTerm, SourceHashes, VocabularyChange, VocabularySnapshot, VocabularySourceTriple } from "../../lib/api/g2-generated";
import { owl, rdfType, rdfs } from "./structural-edit";
export const skos = "http://www.w3.org/2004/02/skos/core#";
export const semantic = "urn:ontology-platform:semantics:";
export const xsd = "http://www.w3.org/2001/XMLSchema#";
export const prov = "http://www.w3.org/ns/prov#";
/** 受控表单直接编辑服务端RDF对象；标签只用于显示，IRI仍是身份。 */
export const predicates = [
  { iri: rdfType, label: "登记类型", kind: "iri" },
  ...[["prefLabel", "首选名称"], ["altLabel", "别名"], ["hiddenLabel", "隐藏标签"], ["notation", "标准编码 notation"], ["definition", "定义"]]
    .map(([name, label]) => ({ iri: skos + name, label, kind: "literal" })),
  ...[["inScheme", "所属术语集"], ["topConceptOf", "顶层所属集"], ["hasTopConcept", "顶层概念"], ["broader", "上位概念"], ["narrower", "下位概念"], ["related", "相关概念"],
    ["exactMatch", "精确对齐"], ["closeMatch", "近似对齐"], ["broadMatch", "上位对齐"], ["narrowMatch", "下位对齐"], ["relatedMatch", "相关对齐"]]
    .map(([name, label]) => ({ iri: skos + name, label, kind: "iri" })),
  { iri: rdfs + "label", label: "资源名称", kind: "literal" },
  { iri: owl + "deprecated", label: "废弃（保留IRI和历史）", kind: "literal" },
  ...[["canonicalUnit", "稳定单位IRI"], ["quantityKind", "量类型 quantity kind"], ["dimension", "量纲IRI"], ["nominalUnit", "属性标称单位版本IRI"], ["standardSource", "原始标准来源IRI"]]
    .map(([name, label]) => ({ iri: semantic + name, label, kind: "iri" })),
  ...[["version", "版本"], ["symbol", "显示符号"], ["precision", "声明精度（不确定用UNKNOWN）"], ["synthetic", "Synthetic标记"], ["lengthExponent", "长度指数"], ["massExponent", "质量指数"],
    ["timeExponent", "时间指数"], ["electricCurrentExponent", "电流指数"], ["temperatureExponent", "温度指数"], ["amountExponent", "物质的量指数"], ["luminousIntensityExponent", "发光强度指数"]]
    .map(([name, label]) => ({ iri: semantic + name, label, kind: "literal" })),
  { iri: prov + "wasDerivedFrom", label: "标准原始引用IRI", kind: "iri" },
];
export const resourceTypes = [
  { iri: skos + "Concept", label: "术语 Concept" }, { iri: skos + "ConceptScheme", label: "术语集 ConceptScheme" },
  { iri: semantic + "UnitDefinition", label: "Synthetic单位版本" }, { iri: semantic + "QuantityKind", label: "量类型 QuantityKind" },
  { iri: semantic + "Dimension", label: "七维量纲 Dimension" }, { iri: semantic + "StandardSource", label: "Synthetic标准来源" },
  { iri: owl + "DatatypeProperty", label: "属性单位绑定" },
];

/** 仅从真实快照聚合目录，不生成RDF事实或合并同名资源。 */
export function vocabularyDirectory(snapshot: VocabularySnapshot, search: string) {
  const subjects = new Map<string, VocabularySourceTriple[]>();
  for (const row of snapshot.triples) {
    if (row.triple.subject.kind !== "iri") continue;
    const list = subjects.get(row.triple.subject.value) ?? [];
    list.push(row);
    subjects.set(row.triple.subject.value, list);
  }
  const query = search.trim().toLocaleLowerCase();
  return [...subjects.entries()].filter(([iri, rows]) => {
    const relevant = rows.some(row => row.triple.predicate.startsWith(skos) || row.triple.predicate.startsWith(semantic)
      || row.triple.predicate === rdfType && resourceTypes.some(type => type.iri === row.triple.object.value));
    return relevant && (!query || [iri, ...rows.map(row => row.triple.object.value)].some(text => text.toLocaleLowerCase().includes(query)));
  }).map(([iri, rows]) => {
    const labels = rows.filter(row => [skos + "prefLabel", rdfs + "label"].includes(row.triple.predicate));
    return { iri, rows, labels, deprecated: rows.some(row => row.triple.predicate === owl + "deprecated" && ["true", "1"].includes(row.triple.object.value)) };
  }).sort((a, b) => a.iri.localeCompare(b.iri));
}

/** 替换/删除使用精确源和原始RdfTerm，不从渲染文本重建旧对象。 */
export function vocabularyChange(row: VocabularySourceTriple, next: RdfTerm | null): VocabularyChange | null {
  if (!["ontology", "vocabulary"].includes(row.sourceId) || row.triple.subject.kind !== "iri"
    || row.triple.object.kind === "blank") return null;
  return { sourceId: row.sourceId as "ontology" | "vocabulary", edit: { subjectIri: row.triple.subject.value,
    predicateIri: row.triple.predicate, oldObject: { ...row.triple.object }, newObject: next ? { ...next } : null } };
}

/** 四源hash都必须绑定同一草稿修订，不能只信bundle或后到响应。 */
export function sameHashes(left: SourceHashes, right: SourceHashes) {
  const keys: (keyof SourceHashes)[] = ["ontologyHash", "shapesHash", "vocabularyHash", "dataHash", "bundleHash"];
  return keys.every(key => (typeof left[key] === "string" || key === "vocabularyHash" && left[key] === null) && left[key] === right[key]);
}
export function snapshotMatches(snapshot: VocabularySnapshot, draft: OntologyDraft) {
  return snapshot.draftId === draft.draftId && snapshot.releaseId === null && snapshot.manifestHash === null
    && snapshot.revision === draft.revision && sameHashes(snapshot.hashes, draft.hashes);
}
/** 无历史语义档案即明确UNKNOWN，禁止代入当前profile。 */
export function releaseProfile(snapshot: VocabularySnapshot) {
  return snapshot.profileVersion && snapshot.profileHash ? `${snapshot.profileVersion} / ${snapshot.profileHash}` : "LEGACY_G2 / UNKNOWN";
}
/** 每项显示完整RDF身份，缺值和多值保持可见。 */
export function termText(term: RdfTerm) {
  return `${term.kind} · ${term.value}${term.language ? ` @${term.language}` : ""}${term.datatype ? ` ^^${term.datatype}` : ""}`;
}
