import type { RdfTerm, RdfTriple, SemanticEdit, SemanticProjection } from "../../lib/api/g2-generated";

export const rdfType = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
export const rdfs = "http://www.w3.org/2000/01/rdf-schema#";
export const owl = "http://www.w3.org/2002/07/owl#";
export const langString = "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString";
export const namedAxioms = ["equivalentClass", "disjointWith", "inverseOf"].map(name => owl + name);

/** 表单绑定服务端投影与所选节点，换节点或修订必须重新初始化。 */
export function structuralContext(projection: SemanticProjection, selected: string) {
  return { revision: projection.revision, hash: projection.hashes.bundleHash, selected };
}

/** 受控命名公理只使用显式声明，不能从标签、图布局或推断类型生成候选。 */
export function namedAxiomCandidates(projection: SemanticProjection, predicate: string): string[] {
  if (!namedAxioms.includes(predicate)) return [];
  const type = owl + (predicate === owl + "inverseOf" ? "ObjectProperty" : "Class");
  return [...new Set(projection.triples.filter(triple => triple.subject.kind === "iri" && triple.predicate === rdfType
    && triple.object.kind === "iri" && triple.object.value === type).map(triple => triple.subject.value))].sort();
}

/** 绝对IRI只做输入级保护；正式RDF词法和支持矩阵仍由服务器校验。 */
function absoluteIri(value: string): boolean {
  return /^[A-Za-z][A-Za-z0-9+.-]*:[^<>"{}|^`\\\s]*$/.test(value);
}

/** 精确对象相等包括语言和datatype，不能仅比较字符串值。 */
function sameTerm(left: RdfTerm, right: RdfTerm): boolean {
  return left.kind === right.kind && left.value === right.value
    && left.datatype === right.datatype && left.language === right.language;
}

/** 从同一服务修订构建单条命令，完整保留旧对象；拒绝陈旧表单或不正确的受控类型。 */
export function exactEdit(
  projection: SemanticProjection,
  context: ReturnType<typeof structuralContext>,
  input: { operation: "add" | "replace" | "remove"; subject: string; predicate: string; triple?: RdfTriple; object: RdfTerm },
): SemanticEdit | null {
  if (!projection.structuralEditAllowed || context.revision !== projection.revision
    || context.hash !== projection.hashes.bundleHash) return null;
  const { operation, triple, object } = input;
  if (operation !== "add" && (!triple || !projection.triples.some(item => sameTerm(item.subject, triple.subject)
    && item.predicate === triple.predicate && sameTerm(item.object, triple.object)))) return null;
  const subject = operation === "add" ? input.subject.trim() : triple!.subject.value;
  const predicate = operation === "add" ? input.predicate : triple!.predicate;
  if (context.selected && operation !== "add" && subject !== context.selected) return null;
  if (!absoluteIri(subject) || !absoluteIri(predicate)) return null;
  if (operation !== "remove") {
    if (object.kind === "blank" || (object.kind === "iri"
      && (!absoluteIri(object.value) || object.datatype !== null || object.language !== null))) return null;
    if (object.kind === "literal" && ((object.datatype && !absoluteIri(object.datatype))
      || (object.language && object.datatype && object.datatype !== langString))) return null;
    if (namedAxioms.includes(predicate)) {
      const candidates = namedAxiomCandidates(projection, predicate);
      if (object.kind !== "iri" || !candidates.includes(subject) || !candidates.includes(object.value)) return null;
    }
  }
  return {
    subjectIri: subject, predicateIri: predicate,
    oldObject: operation === "add" ? null : { ...triple!.object },
    newObject: operation === "remove" ? null : { ...object },
  };
}
