import type {
  OntologyDraft, OwlExpressionNode, OwlExpressionSnapshot, OwlExpressionSource,
  RdfTerm, ResourceScope, SourceBundle, SourceHashes, VersionRef,
} from "../../lib/api/g2-generated";

const rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#";
const owl = "http://www.w3.org/2002/07/owl#";
const sourceFields: Record<string, keyof SourceBundle> = {
  ontology: "ontologyTurtle", shapes: "shapesTurtle", vocabulary: "vocabularyTurtle", data: "dataTurtle",
};
const sourceHashes: Record<string, keyof SourceHashes> = {
  ontology: "ontologyHash", shapes: "shapesHash", vocabulary: "vocabularyHash", data: "dataHash",
};

/** 请求固定版本；草稿同时绑定完整范围和四源散列，正式版本由服务器核验不可变源。 */
export type ExpressionTarget = { version: VersionRef; hashes?: SourceHashes; scope?: ResourceScope };

/** 单次有界树显示项，引用不会再次复制共享或循环节点。 */
export type ExpressionBranch = {
  term: RdfTerm;
  node?: OwlExpressionNode;
  reference?: "shared" | "cycle" | "budget";
  properties: Array<{ predicateIri: string; values: ExpressionBranch[] }>;
  orderedItems: ExpressionBranch[];
};

/** RDF项的kind参与身份，字面量词法、datatype和language原样呈现。 */
export function expressionTermKey(term: RdfTerm): string {
  return JSON.stringify([term.kind, term.value, term.datatype, term.language]);
}

/** 不联网解引用IRI；标准缩写仅显示，原IRI仍作为证据保留。 */
export function expressionTermLabel(term: RdfTerm): string {
  if (term.kind !== "literal") return term.value;
  return `${JSON.stringify(term.value)}${term.language ? `@${term.language}` : term.datatype ? `^^<${term.datatype}>` : ""}`;
}

/** 中文标签不能替代实际标准谓词，不把语义声明解释为已推理事实。 */
export function expressionPredicateLabel(iri: string): string {
  const names: Record<string, string> = {
    someValuesFrom: "存在值限制", allValuesFrom: "所有值限制", hasValue: "指定值限制", onProperty: "作用属性",
    cardinality: "精确基数", minCardinality: "最小基数", maxCardinality: "最大基数",
    qualifiedCardinality: "限定精确基数", minQualifiedCardinality: "限定最小基数", maxQualifiedCardinality: "限定最大基数",
    onClass: "限定类", onDataRange: "限定数据范围", intersectionOf: "交集", unionOf: "并集", complementOf: "补集",
    propertyChainAxiom: "有序属性链", imports: "导入引用（未加载）", sameAs: "相同个体声明", differentFrom: "不同个体声明",
    hasKey: "身份键公理", equivalentClass: "等价类公理", disjointWith: "不相交公理", inverseOf: "逆属性公理",
  };
  return iri.startsWith(owl) && names[iri.slice(owl.length)] ? names[iri.slice(owl.length)] : "RDF谓词";
}

/** 检查草稿或正式版本身份及四源hash自洽，拒绝旧请求回包与跨源错配。 */
export function expressionSnapshotMatches(snapshot: OwlExpressionSnapshot, target: ExpressionTarget): boolean {
  if (!snapshot || snapshot.projectionVersion !== "1" || !snapshot.version || !snapshot.hashes || !snapshot.scope
    || snapshot.version.kind !== target.version.kind || snapshot.version.id !== target.version.id
    || snapshot.version.revision !== target.version.revision || !Array.isArray(snapshot.sources)) return false;
  if (target.hashes && Object.keys(sourceHashes).some(id => snapshot.hashes[sourceHashes[id]] !== target.hashes?.[sourceHashes[id]])) return false;
  if (target.hashes && snapshot.hashes.bundleHash !== target.hashes.bundleHash) return false;
  if (target.scope && (target.scope.organizationId !== snapshot.scope.organizationId
    || JSON.stringify([...target.scope.siteIds].sort()) !== JSON.stringify([...snapshot.scope.siteIds].sort()))) return false;
  const expected = ["ontology", "shapes", "data", ...(snapshot.hashes.vocabularyHash === null ? [] : ["vocabulary"])];
  const ids = snapshot.sources.map(source => source.sourceId);
  if (new Set(ids).size !== expected.length || ids.length !== expected.length || expected.some(id => !ids.includes(id))) return false;
  return snapshot.sources.every(source => source.sourceHash === snapshot.hashes[sourceHashes[source.sourceId]]
    && /^(?:[0-9a-f]{64})$/.test(source.sourceHash)
    && ["COMPLETE", "INDETERMINATE"].includes(source.status)
    && ["BLOCKED", "NOT_ASSESSED"].includes(source.publishEligible)
    && source.editable === false && source.inferred === false
    && !(source.status === "INDETERMINATE" && source.readOnlyStructured)
    && Array.isArray(source.roots) && Array.isArray(source.nodes) && source.nodes.length <= 512
    && Array.isArray(source.diagnostics));
}

/** 不伪造字符位置；仅同修订、单源hash相符且本地未改时返回源码文档。 */
export function expressionLocation(source: OwlExpressionSource, draft: OntologyDraft, dirty: boolean): keyof SourceBundle | null {
  const field = sourceFields[source.sourceId];
  return !dirty && field && source.sourceHash === draft.hashes[sourceHashes[source.sourceId]] ? field : null;
}

/** 每源单独建树；共享节点、纯环分量、列表顺序与UI预算都显式呈现。 */
export function buildExpressionTree(source: OwlExpressionSource, maxEntries = 1024): { roots: ExpressionBranch[]; truncated: boolean } {
  const nodes = new Map(source.nodes.map(node => [expressionTermKey(node.term), node]));
  const seen = new Set<string>();
  const budget = Math.max(1, Math.min(maxEntries, 1024));
  let entries = 0;
  let truncated = false;
  const empty = (term: RdfTerm): ExpressionBranch => ({ term, properties: [], orderedItems: [] });
  function visit(term: RdfTerm, path: Set<string>, depth: number): ExpressionBranch {
    const key = expressionTermKey(term);
    const branch = empty(term);
    const node = nodes.get(key);
    if (entries >= budget || depth > 32) {
      truncated = true;
      return { ...branch, reference: "budget" };
    }
    entries += 1;
    if (!node) return branch;
    if (path.has(key)) return { ...branch, reference: "cycle" };
    if (seen.has(key)) return { ...branch, reference: "shared" };
    seen.add(key);
    const nextPath = new Set([...path, key]);
    branch.node = node;
    for (const property of node.properties) {
      if (entries >= budget) { truncated = true; break; }
      // 列表链通过有序成员展示，不将rest链长度当表达式嵌套深度。
      const orderedList = node.kind === "list" && [rdf + "first", rdf + "rest"].includes(property.predicateIri);
      const values: ExpressionBranch[] = [];
      for (const value of property.values) {
        if (entries >= budget) { truncated = true; break; }
        values.push(orderedList ? (entries += 1, empty(value)) : visit(value, nextPath, depth + 1));
      }
      branch.properties.push({ predicateIri: property.predicateIri, values });
    }
    for (const item of node.orderedItems) {
      if (entries >= budget) { truncated = true; break; }
      branch.orderedItems.push(visit(item, nextPath, depth + 1));
    }
    return branch;
  }
  const roots: ExpressionBranch[] = [];
  // roots可能因纯环为空，仍逐项显示未访问的真实主体，不把没有根误报为空图。
  for (const term of [...source.roots, ...source.nodes.map(node => node.term)]) {
    if (seen.has(expressionTermKey(term))) continue;
    if (entries >= budget) { truncated = true; break; }
    roots.push(visit(term, new Set(), 0));
  }
  return { roots, truncated };
}

/** 同一面板的新请求立即取消旧票据，完成顺序不能覆盖后发或不同版本的快照。 */
export class ExpressionReadSession {
  private current: AbortController | null = null;

  begin(): AbortController {
    this.invalidate();
    this.current = new AbortController();
    return this.current;
  }

  invalidate(): void {
    this.current?.abort();
    this.current = null;
  }

  isCurrent(controller: AbortController): boolean {
    return controller === this.current && !controller.signal.aborted;
  }
}
