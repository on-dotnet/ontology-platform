import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { OntologyDraft, OwlExpressionNode, OwlExpressionSnapshot, OwlExpressionSource, RdfTerm } from "../../lib/api/g2-generated";
import {
  buildExpressionTree, expressionLocation, expressionSnapshotMatches, expressionTermLabel, ExpressionReadSession,
} from "./expression-model";
import { ExpressionReadView, DraftExpressions, ReleasedExpressions } from "./expression-tree";

const owl = "http://www.w3.org/2002/07/owl#";
const rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#";
const iri = (value: string): RdfTerm => ({ kind: "iri", value, datatype: null, language: null });
const blank = (value: string): RdfTerm => ({ kind: "blank", value: "_:" + value, datatype: null, language: null });
const literal = (value: string): RdfTerm => ({ kind: "literal", value, datatype: null, language: "zh" });
const node = (term: RdfTerm, kind = "term"): OwlExpressionNode => ({ term, kind, properties: [], orderedItems: [] });
const hashes = { ontologyHash: "a".repeat(64), shapesHash: "b".repeat(64), vocabularyHash: null, dataHash: "c".repeat(64), bundleHash: "d".repeat(64) };
const scope = { organizationId: "org-a", siteIds: ["site-b", "site-a"] };
const source = (): OwlExpressionSource => ({
  sourceId: "ontology", sourceHash: hashes.ontologyHash, status: "COMPLETE", sourcePreserved: true, readOnlyStructured: true,
  editable: false, inferred: false, publishEligible: "BLOCKED", roots: [], nodes: [], diagnostics: [],
});
const snapshot = (): OwlExpressionSnapshot => ({
  projectionVersion: "1", version: { kind: "DRAFT", id: "draft-fixed", revision: 7 }, scope, hashes,
  profileId: "ontology-platform/g3-m1", profileVersion: "4", profileHash: "e".repeat(64),
  sources: [source(), { ...source(), sourceId: "shapes", sourceHash: hashes.shapesHash }, { ...source(), sourceId: "data", sourceHash: hashes.dataHash }],
});
const target = { version: { kind: "DRAFT" as const, id: "draft-fixed", revision: 7 }, hashes, scope };
const draft = { draftId: "draft-fixed", revision: 7, hashes, scope } as OntologyDraft;

function collect(branches: ReturnType<typeof buildExpressionTree>["roots"]): string[] {
  return branches.flatMap(branch => [expressionTermLabel(branch.term), branch.reference ?? "", ...collect(branch.orderedItems),
    ...branch.properties.flatMap(property => collect(property.values))]);
}

describe("M5准确版本与源码绑定", () => {
  it("完整四源与范围相符才接受；范围顺序不改变原DTO", () => {
    const value = snapshot();
    value.scope = { ...scope, siteIds: ["site-a", "site-b"] };
    expect(expressionSnapshotMatches(value, target)).toBe(true);
    expect(scope.siteIds).toEqual(["site-b", "site-a"]);
  });
  it.each(["revision", "id", "kind", "bundle", "source", "organization", "site", "missing", "duplicate", "unknown", "publish", "inferred", "editable", "partial"])("拒绝%s错配或协议漂移", fault => {
    const value = structuredClone(snapshot());
    if (fault === "revision") value.version.revision = 8;
    if (fault === "id") value.version.id = "another-draft";
    if (fault === "kind") value.version.kind = "RELEASE";
    if (fault === "bundle") value.hashes.bundleHash = "f".repeat(64);
    if (fault === "source") value.sources[0].sourceHash = "f".repeat(64);
    if (fault === "organization") value.scope.organizationId = "other-org";
    if (fault === "site") value.scope.siteIds = ["site-a"];
    if (fault === "missing") value.sources.pop();
    if (fault === "duplicate") value.sources[1] = value.sources[0];
    if (fault === "unknown") value.sources[0].status = "PARSED_MEANS_PUBLISHED";
    if (fault === "publish") value.sources[0].publishEligible = "ELIGIBLE";
    if (fault === "inferred") value.sources[0].inferred = true;
    if (fault === "editable") value.sources[0].editable = true;
    if (fault === "partial") value.sources[0].status = "INDETERMINATE";
    expect(expressionSnapshotMatches(value, target)).toBe(false);
  });
  it("缺席与空vocabulary不混淆，提供源必须精确绑定该slot", () => {
    const value = structuredClone(snapshot());
    value.hashes.vocabularyHash = "f".repeat(64);
    expect(expressionSnapshotMatches(value, { version: value.version })).toBe(false);
    value.sources.push({ ...source(), sourceId: "vocabulary", sourceHash: value.hashes.vocabularyHash });
    expect(expressionSnapshotMatches(value, { version: value.version })).toBe(true);
  });
  it("固定正式Release要求相同ID且revision=null", () => {
    const value = snapshot();
    value.version = { kind: "RELEASE", id: "release-fixed", revision: null };
    expect(expressionSnapshotMatches(value, { version: value.version })).toBe(true);
    expect(expressionSnapshotMatches(value, { version: { ...value.version, revision: 7 } })).toBe(false);
  });
  it("dirty/hash失配禁用定位；只返回真实源字段而不捏造字符坐标", () => {
    expect(expressionLocation(source(), draft, false)).toBe("ontologyTurtle");
    expect(expressionLocation(source(), draft, true)).toBeNull();
    expect(expressionLocation({ ...source(), sourceHash: "f".repeat(64) }, draft, false)).toBeNull();
    expect(expressionLocation({ ...source(), sourceId: "unknown" }, draft, false)).toBeNull();
  });
  it("后发刷新及面板卸载都使旧读取无法获胜，即使旧网络回包较晚", async () => {
    const session = new ExpressionReadSession();
    const first = session.begin();
    let finish: (() => void) | undefined;
    const pending = new Promise<void>(resolve => { finish = resolve; });
    let accepted = false;
    const operation = pending.then(() => { if (session.isCurrent(first)) accepted = true; });
    const second = session.begin();
    finish?.();
    await operation;
    expect(accepted).toBe(false);
    expect(first.signal.aborted).toBe(true);
    expect(session.isCurrent(second)).toBe(true);
    session.invalidate();
    expect(session.isCurrent(second)).toBe(false);
  });
});

describe("M5只读结构顺序与预算", () => {
  it("propertyChain列表保留原顺序与typed词法，不按IRI排序", () => {
    const value = source();
    const chain = node(iri("urn:chain"), "axiom");
    chain.properties = [{ predicateIri: owl + "propertyChainAxiom", values: [blank("list")] }];
    const list = node(blank("list"), "list");
    list.orderedItems = [iri("urn:z"), iri("urn:a"), { ...literal("+001"), language: null, datatype: "http://www.w3.org/2001/XMLSchema#nonNegativeInteger" }];
    value.roots = [chain.term]; value.nodes = [chain, list];
    const members = buildExpressionTree(value).roots[0].properties[0].values[0].orderedItems;
    expect(members.map(item => item.term.value)).toEqual(["urn:z", "urn:a", "+001"]);
    expect(expressionTermLabel(members[2].term)).toContain('"+001"^^<http://www.w3.org/2001/XMLSchema#nonNegativeInteger>');
  });
  it("共享blank仅展开一次，源DTO不变", () => {
    const value = source();
    const root = node(iri("urn:root"));
    root.properties = [{ predicateIri: owl + "someValuesFrom", values: [blank("shared"), blank("shared")] }];
    value.roots = [root.term]; value.nodes = [root, node(blank("shared"), "restriction")];
    const original = JSON.stringify(value);
    expect(collect(buildExpressionTree(value).roots)).toContain("shared");
    expect(JSON.stringify(value)).toBe(original);
  });
  it("无roots纯环仍展示并停止循环引用", () => {
    const value = source();
    const cyclic = node(blank("cycle"), "restriction");
    cyclic.properties = [{ predicateIri: owl + "someValuesFrom", values: [cyclic.term] }];
    value.nodes = [cyclic];
    const result = buildExpressionTree(value);
    expect(result.roots).toHaveLength(1);
    expect(collect(result.roots)).toContain("cycle");
    expect(result.truncated).toBe(false);
  });
  it("不同源相同blank标签不会共享节点或内容", () => {
    const first = source(), second = { ...source(), sourceId: "data", sourceHash: hashes.dataHash };
    for (const [value, text] of [[first, "本体值"], [second, "实例值"]] as const) {
      const item = node(blank("same")); item.properties = [{ predicateIri: "urn:value", values: [literal(text)] }]; value.nodes = [item];
    }
    expect(collect(buildExpressionTree(first).roots).join(" ")).toContain("本体值");
    expect(collect(buildExpressionTree(second).roots).join(" ")).toContain("实例值");
    expect(collect(buildExpressionTree(second).roots).join(" ")).not.toContain("本体值");
  });
  it("33成员合法列表不被表达式深度32误截断，rest只显示真实引用", () => {
    const value = source();
    const list = node(blank("head"), "list");
    list.orderedItems = Array.from({ length: 33 }, (_, index) => iri("urn:member:" + index));
    list.properties = [{ predicateIri: rdf + "rest", values: [blank("next")] }];
    value.nodes = [list];
    const result = buildExpressionTree(value);
    expect(result.roots[0].orderedItems).toHaveLength(33);
    expect(result.truncated).toBe(false);
  });
  it("实际嵌套或UI条目超预算有显式截断状态，不偷偷完整化", () => {
    const value = source();
    value.nodes = Array.from({ length: 40 }, (_, index) => ({ ...node(blank(String(index)), "restriction"),
      properties: index < 39 ? [{ predicateIri: owl + "someValuesFrom", values: [blank(String(index + 1))] }] : [] }));
    expect(buildExpressionTree(value).truncated).toBe(true);
    expect(buildExpressionTree(value, 3).truncated).toBe(true);
  });
});

describe("M5中文只读组件", () => {
  it.each(["RELEASE", "DRAFT"] as const)("%s 历史版本明确区分当前支持策略和只读投影协议", kind => {
    const value = snapshot();
    value.version = kind === "RELEASE"
      ? { kind, id: "historical-release-v1", revision: null }
      : { kind, id: "historical-draft", revision: 2 };
    const before = JSON.stringify(value);
    const html = renderToStaticMarkup(createElement(ExpressionReadView, { snapshot: value }));
    expect(html).toContain(`当前平台支持策略 Profile：${value.profileId} · v4 · ${value.profileHash}`);
    expect(html).toContain("只读投影协议版本：1");
    expect(html).toContain(kind === "RELEASE"
      ? "固定正式 Release historical-release-v1 · revision 不适用"
      : "固定草稿 historical-draft · revision 2");
    expect(html).toContain(kind === "RELEASE"
      ? "此策略不是当前选中历史 Release 发布时的策略快照。"
      : "此策略不是当前选中草稿修订保存时的策略快照。");
    expect(html).not.toContain(kind === "RELEASE" ? "草稿修订保存时" : "Release 发布时");
    expect(html).not.toMatch(/(?:发布时|保存时)(?:的)?(?:策略|Profile)[：: ]*v4|只读投影协议版本：4/);
    expect(html).not.toContain('class="g2-hash">profile ');
    for (const hash of [hashes.bundleHash, hashes.ontologyHash, hashes.shapesHash, hashes.dataHash])
      expect(html).toContain(hash);
    expect(JSON.stringify(value)).toBe(before);
  });
  it("支持五维分级、来源、语义限制与标准term准确呈现且没有写入控件", () => {
    const value = snapshot();
    value.sources[0].nodes = [{ ...node(iri("urn:chain"), "axiom"), properties: [{ predicateIri: owl + "imports", values: [iri("https://invalid.example/import")] }] }];
    const html = renderToStaticMarkup(createElement(ExpressionReadView, { snapshot: value }));
    for (const text of ["高阶表达式只读视图", "source-preserved", "read-only-structured", "editable", "publishEligible", "inferred",
      hashes.ontologyHash, "BLOCKED", "allValuesFrom 不保证存在关系", "Functional 不等于数据库唯一键", "UNKNOWN", owl + "imports", "固定草稿"])
      expect(html).toContain(text);
    expect(html).not.toMatch(/<input|<textarea|href="https/);
    expect(html).toContain("导入引用（未加载）");
  });
  it("恶意RDF字面量按文本转义，不执行HTML或imports外部导航", () => {
    const value = snapshot();
    const item = node(iri("urn:untrusted"));
    item.properties = [{ predicateIri: "urn:annotation", values: [literal('<script>alert("synthetic")</script>')] }];
    value.sources[0].nodes = [item];
    const html = renderToStaticMarkup(createElement(ExpressionReadView, { snapshot: value }));
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain("<script>");
  });
  it("损坏结构、未知位置和诊断仍显示真实证据，不把失败解释为源码丢失", () => {
    const value = snapshot();
    value.sources[0] = { ...source(), status: "INDETERMINATE", readOnlyStructured: false,
      diagnostics: [{ code: "list_invalid", message: "列表断裂，源保留", focusNode: blank("broken"), predicateIri: rdf + "rest", line: null, column: null }] };
    const html = renderToStaticMarkup(createElement(ExpressionReadView, { snapshot: value }));
    expect(html).toContain("INDETERMINATE · 结构不完整");
    expect(html).toContain("原文保留");
    expect(html).toContain("list_invalid");
    expect(html).toContain("行 UNKNOWN / 列 UNKNOWN");
  });
  it("新面板初始显示读取中，正式版本入口不假冒当前草稿", () => {
    const html = renderToStaticMarkup(createElement(DraftExpressions, { draft, dirty: true, onLocate: () => undefined }));
    expect(html).toContain("正在读取准确修订");
    expect(html).toContain("来源定位已禁用");
    const released = renderToStaticMarkup(createElement(ReleasedExpressions));
    expect(released).toContain("读取固定正式Release高阶表达式");
    expect(released).toContain('aria-label="表达式Release ID"');
    expect(released).not.toContain("高阶表达式只读视图");
  });
});
