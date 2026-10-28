import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { SupportProfile } from "./support-profile";
import { SourceEditor, sourceFields } from "./source-editor";
import { decodeSourceBytes } from "./source-bytes";
import { draftState, isDirty, updateSource } from "./draft-state";
import type { OntologyDraft, SemanticSupportProfile, SourceBundle } from "../../lib/api/g2-generated";

const profile: SemanticSupportProfile = {
  profileId: "ontology-platform/g3-m1", version: "1", hash: "profile-hash", reasoningMode: "ASSERTED_ONLY",
  comparisonBudget: { maxBlankNodes: 128, maxSearchNodes: 100000, timeoutMilliseconds: 5000 },
  capabilities: Array.from({ length: 20 }, (_, index) => ({
    id: String(index + 1).padStart(2, "0"), name: `能力${index + 1}`, edit: "SOURCE", preserve: "EXACT",
    publish: index < 11 ? "SUPPORTED" : "BLOCKED", validation: index < 11 ? "ASSERTED" : "NOT_SUPPORTED", reason: "保留原文",
  })),
};
const source = "\uFEFF# 🏭 Synthetic\r\n<urn:a> <urn:b> <urn:c> .\r\n";
const sources: SourceBundle = { ontologyTurtle: source, shapesTurtle: source, vocabularyTurtle: source, dataTurtle: source };
const noop = () => undefined;

describe("M1 实际组件输出与四源往返", () => {
  it("逐行展示服务端20项四维能力及共享预算，不宣称推理通过", () => {
    const html = renderToStaticMarkup(createElement(SupportProfile, { profile, loading: false, failed: false, onRefresh: noop }));
    expect(html.match(/scope="row"/g)).toHaveLength(20);
    expect(html).toContain("NOT_SUPPORTED");
    expect(html).toContain("BLOCKED");
    expect(html).toContain("EXACT");
    expect(html).toContain("128");
    expect(html).toContain("100000");
    expect(html).toContain("5000");
    expect(html).toContain("OWL 推理 NOT_RUN");
    expect(html).toContain('tabindex="0"');
  });
  it.each(["1", "2", "3"])("登记档案v%s显示完整矩阵且不误报UNKNOWN", version => {
    const count = version === "3" ? 22 : 20;
    const current = { ...profile, version, capabilities: Array.from({ length: count }, (_, index) => ({ ...profile.capabilities[0], id: String(index + 1).padStart(2, "0") })) };
    const html = renderToStaticMarkup(createElement(SupportProfile, { profile: current, loading: false, failed: false, onRefresh: noop }));
    expect(html.match(/scope="row"/g)).toHaveLength(count);
    expect(html).toContain(`${count}项能力矩阵，可横向滚动`);
    expect(html).not.toContain("UNKNOWN");
  });
  it.each(["missing", "duplicate", "unknown"])("档案%s继续显示UNKNOWN", fault => {
    const current = { ...profile, version: fault === "unknown" ? "99" : "1", capabilities: fault === "missing" ? profile.capabilities.slice(1) : fault === "duplicate" ? [...profile.capabilities.slice(1), profile.capabilities[1]] : profile.capabilities };
    const html = renderToStaticMarkup(createElement(SupportProfile, { profile: current, loading: false, failed: false, onRefresh: noop }));
    expect(html).toContain("UNKNOWN");
  });
  it("profile请求失败显示UNKNOWN和可恢复入口", () => {
    const html = renderToStaticMarkup(createElement(SupportProfile, { profile: null, loading: false, failed: true, onRefresh: noop }));
    expect(html).toContain("UNKNOWN");
    expect(html).toContain("刷新支持档案");
    expect(html).not.toContain("发布资格符合");
  });
  it.each(sourceFields)("$file 导出Blob再导入保留BOM/CRLF/非BMP全部字节，且不标dirty", async ({ key }) => {
    const draft = { name: "原始源", sources } as OntologyDraft;
    const bytes = new TextEncoder().encode(sources[key]!);
    const exported = new Blob([sources[key]!], { endings: "transparent" });
    const reimported = decodeSourceBytes(await exported.arrayBuffer());
    expect(new TextEncoder().encode(reimported)).toEqual(bytes);
    expect(isDirty(updateSource(draftState(draft), key, reimported))).toBe(false);
  });
  it("导入单源只改变该源，不触碰其它三个源字节", () => {
    const draft = { name: "原始源", sources } as OntologyDraft;
    const updated = updateSource(draftState(draft), "ontologyTurtle", "# changed\n");
    expect(updated.sources).toEqual({ ...sources, ontologyTurtle: "# changed\n" });
    expect(draft.sources).toEqual(sources);
  });
  it("absent术语源禁用导出和textarea，但可显式创建空源", () => {
    const html = renderToStaticMarkup(createElement(SourceEditor, {
      sources: { ...sources, vocabularyTurtle: null }, field: "vocabularyTurtle",
      onField: noop, onChange: noop, onAbsent: noop, onBeginImport: () => ({ isCurrent: () => false, commit: noop }),
    }));
    expect(html).toContain("absent");
    expect(html).toMatch(/disabled=""[^>]*>导出原始源/);
    expect(html).toMatch(/readonly=""/i);
    expect(html).toContain("创建空术语源");
  });
  it("只读角色不能载入文件或编辑源码", () => {
    const html = renderToStaticMarkup(createElement(SourceEditor, {
      sources, field: "ontologyTurtle", onField: noop, onChange: noop, onAbsent: noop, onBeginImport: () => ({ isCurrent: () => false, commit: noop }), readOnly: true,
    }));
    expect(html).toMatch(/type="file"[^>]*disabled=""/);
    expect(html).toMatch(/readonly=""/i);
  });
});
