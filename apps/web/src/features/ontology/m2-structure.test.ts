import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { exactEdit, namedAxiomCandidates, structuralContext } from "./structural-edit";
import { StructuralForm } from "./structural-form";
import type { RdfTerm, SemanticProjection } from "../../lib/api/g2-generated";

const iri = (value: string): RdfTerm => ({ kind: "iri", value, datatype: null, language: null });
const owl = "http://www.w3.org/2002/07/owl#";
const rdfType = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
const label = "http://www.w3.org/2000/01/rdf-schema#label";
const langString = "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString";
const hashes = { ontologyHash: "o", shapesHash: "s", vocabularyHash: null, dataHash: "d", bundleHash: "b" };
export const projection: SemanticProjection = {
  revision: 3, hashes, structuralEditAllowed: true, diagnostics: [], edges: [],
  nodes: [
    { id: "urn:A", label: "甲类", kind: "class", typeIris: [owl + "Class"] },
    { id: "urn:B", label: "乙类", kind: "class", typeIris: [owl + "Class"] },
    { id: "urn:p", label: "对象属性", kind: "objectProperty", typeIris: [owl + "ObjectProperty"] },
    { id: "urn:q", label: "反向属性", kind: "objectProperty", typeIris: [owl + "ObjectProperty"] },
  ],
  triples: [
    ...["urn:A", "urn:B"].map(id => ({ subject: iri(id), predicate: rdfType, object: iri(owl + "Class") })),
    ...["urn:p", "urn:q"].map(id => ({ subject: iri(id), predicate: rdfType, object: iri(owl + "ObjectProperty") })),
    { subject: iri("urn:A"), predicate: label, object: { kind: "literal", value: "中文标签", datatype: langString, language: "zh" } },
  ],
};
const form = (selected: string, source = projection) => renderToStaticMarkup(createElement(StructuralForm, {
  projection: source, selected, blocked: false, onEdit: () => undefined,
}));

describe("M2 当前节点绑定的结构表单", () => {
  it("首个精确对象随当前节点初始化，不沿用空值或另一节点对象", () => {
    expect(form("urn:A")).toContain(`value="${owl}Class"`);
    expect(form("urn:p")).toContain(`value="${owl}ObjectProperty"`);
  });
  it("受控命名公理包含equivalent/disjoint/inverse三个登记谓词", () => {
    for (const name of ["equivalentClass", "disjointWith", "inverseOf"]) expect(form("urn:A")).toContain(owl + name);
  });
  it("语言字面量初始保留规范rdf:langString并允许精确操作", () => {
    const source = { ...projection, triples: projection.triples.filter(triple => triple.predicate === label) };
    const html = form("urn:A", source);
    expect(html).toContain('value="中文标签"');
    expect(html).toContain('value="zh"');
    expect(html).not.toMatch(/disabled=""[^>]*>提交真实结构编辑/);
  });
  it("复杂图明确结构只读且禁用表单输入", () => {
    const html = form("urn:A", { ...projection, structuralEditAllowed: false });
    expect(html).toContain("源码保存和原文导出仍可使用");
    expect(html).toMatch(/aria-label="结构操作"[^>]*disabled=""/);
  });
});

describe("M2 精确命令与修订边界", () => {
  it("删除完整复制旧语言字面量，datatype与language都不丢失", () => {
    const triple = projection.triples.at(-1)!;
    const edit = exactEdit(projection, structuralContext(projection, "urn:A"), {
      operation: "remove", subject: "urn:A", predicate: label, triple, object: iri("urn:unused"),
    });
    expect(edit?.oldObject).toEqual(triple.object);
    expect(edit?.newObject).toBeNull();
  });
  it("旧节点或旧revision的表单上下文不能提交到新投影", () => {
    const input = { operation: "remove" as const, subject: "urn:A", predicate: label,
      triple: projection.triples.at(-1)!, object: iri("urn:unused") };
    expect(exactEdit({ ...projection, revision: 4 }, structuralContext(projection, "urn:A"), input)).toBeNull();
    expect(exactEdit(projection, structuralContext(projection, "urn:B"), input)).toBeNull();
  });
  it("受控候选只接受显式rdf:type声明，不能靠节点标签或kind猜测", () => {
    expect(namedAxiomCandidates(projection, owl + "equivalentClass")).toEqual(["urn:A", "urn:B"]);
    expect(namedAxiomCandidates(projection, owl + "inverseOf")).toEqual(["urn:p", "urn:q"]);
    expect(namedAxiomCandidates({ ...projection, triples: [] }, owl + "inverseOf")).toEqual([]);
  });
  it("两端类型不匹配以及伪造旧对象都关闭提交", () => {
    const context = structuralContext(projection, "urn:A");
    expect(exactEdit(projection, context, { operation: "add", subject: "urn:A",
      predicate: owl + "equivalentClass", triple: undefined, object: iri("urn:p") })).toBeNull();
    expect(exactEdit(projection, context, { operation: "remove", subject: "urn:A", predicate: label,
      triple: { ...projection.triples.at(-1)!, object: iri("urn:forged") }, object: iri("urn:B") })).toBeNull();
  });
});
