import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { EntityTree, EntityProperties } from "./entity-tree";
import { DiagnosticCard } from "./diagnostic-card";
import { AssessmentPanel } from "./assessment-panel";
import type { OntologyDraft } from "../../lib/api/g2-generated";

const hashes = { ontologyHash: "o", shapesHash: "s", vocabularyHash: null, dataHash: "d", bundleHash: "b" };
export const draft = {
  draftId: "draft", revision: 3, hashes, name: "测试资产",
  sources: { ontologyTurtle: "<urn:A> <urn:p> <urn:B> .", shapesTurtle: "<urn:Shape> <urn:p> <urn:A> .",
    vocabularyTurtle: null, dataTurtle: "" },
  projection: { revision: 3, hashes, nodes: [], triples: [], edges: [], diagnostics: [], structuralEditAllowed: true },
} as unknown as OntologyDraft;

describe("M2 四项能力分别展示", () => {
  it("没有assessment/profile时显示UNKNOWN，不把可保存当可发布或可推理", () => {
    const html = renderToStaticMarkup(createElement(AssessmentPanel, {
      draft, profile: null, dirty: true, busy: false, canEdit: true, reason: "测试",
      execute: async () => undefined, onNotice: () => undefined,
    }));
    for (const title of ["可保存", "可结构编辑", "可发布", "可推理"]) expect(html).toContain(title);
    expect(html).toContain("UNKNOWN");
    expect(html).toContain("NOT_RUN");
    expect(html).toContain("保存时由服务端解析校验");
  });
});

describe("M2 可访问实体与来源证据", () => {
  it("四类实体分组和选中状态来自实际投影，选中按钮可被浏览器测试识别", () => {
    const projection = { ...draft.projection, nodes: [{ id: "urn:A", label: "设备类", kind: "class" as const, typeIris: [] }] };
    const html = renderToStaticMarkup(createElement(EntityTree, { projection, selected: "urn:A", onSelect: () => undefined }));
    expect(html).toContain('aria-label="本体实体树"');
    expect(html).toContain('aria-pressed="true"');
    for (const title of ["类", "对象属性", "数据属性", "个体"]) expect(html).toContain(title);
    expect(html).toContain("设备类");
  });
  it("属性检查器逐项保留字面量language和datatype", () => {
    const projection = { ...draft.projection, nodes: [{ id: "urn:A", label: "设备类", kind: "class" as const, typeIris: [] }],
      triples: [{ subject: { kind: "iri" as const, value: "urn:A", datatype: null, language: null }, predicate: "urn:label",
        object: { kind: "literal" as const, value: "中文", datatype: "urn:lang", language: "zh" } }] };
    const html = renderToStaticMarkup(createElement(EntityProperties, { projection, selected: "urn:A" }));
    expect(html).toContain("中文");
    expect(html).toContain("datatype urn:lang · language zh");
  });
  it("blank shape的诊断显示中文解释与UNKNOWN，过期诊断不出现定位按钮", () => {
    const item = { sourceId: "ontology", sourceHash: "old", line: null, column: null,
      sourceShape: { kind: "blank" as const, value: "b0", datatype: null, language: null },
      diagnostic: { code: "validation_issue", severity: "error" as const, message: "MinCount", path: "urn:p", focusNode: null } };
    const html = renderToStaticMarkup(createElement(DiagnosticCard, { item, draft, dirty: false, index: 0 }));
    expect(html).toContain("SHACL 约束");
    expect(html).toContain("空白 shape 标识不代表稳定源码位置");
    expect(html).toContain("UNKNOWN");
    expect(html).toContain('data-source-current="false"');
    expect(html).not.toContain("定位诊断来源 1");
  });
});
