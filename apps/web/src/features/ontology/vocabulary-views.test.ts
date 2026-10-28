import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { VocabularyReadView, VocabularyEditForm } from "./vocabulary-workbench";
import type { VocabularySnapshot } from "../../lib/api/g2-generated";
const snapshot: VocabularySnapshot = { draftId: null, releaseId: "release-fixed", manifestHash: "manifest-fixed", revision: 4,
  hashes: { ontologyHash: "o", shapesHash: "s", vocabularyHash: "v", dataHash: "d", bundleHash: "bundle-fixed" },
  profileVersion: null, profileHash: null, triples: [], diagnostics: [] };
describe("M3 中文词汇与单位视图", () => {
  it("固定发布显示真实release/manifest/profile及四源散列，空数据保持明确", () => {
    const html = renderToStaticMarkup(createElement(VocabularyReadView, { snapshot, selected: "", onSelect: () => undefined }));
    for (const text of ["release-fixed", "manifest-fixed", "bundle-fixed", "LEGACY_G2 / UNKNOWN", "尚无匹配词汇", "原始标准", "Synthetic"]) expect(html).toContain(text);
  });
  it("只读或dirty明确禁用批量编辑，提供精确RDF来源和语言输入", () => {
    const html = renderToStaticMarkup(createElement(VocabularyEditForm, { selected: "urn:a", snapshot, blocked: "请先保存或丢弃未保存源码", onCommit: () => undefined }));
    expect(html).toContain("请先保存或丢弃未保存源码");
    expect(html).toContain("批量原子提交");
    expect(html).toContain("RDF语言");
    expect(html).toContain("写入源");
    expect(html).toContain('disabled=""');
  });
});
