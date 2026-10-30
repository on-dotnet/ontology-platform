import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { OntologyDraft, VocabularySnapshot } from "../../lib/api/g2-generated";
import { IdentityTimeEditForm, IdentityTimeReadView } from "./identity-time-workbench";
const snapshot: VocabularySnapshot = { draftId: null, releaseId: "release-fixed", manifestHash: "manifest-fixed", revision: 4,
  hashes: { ontologyHash: "o", shapesHash: "s", vocabularyHash: "v", dataHash: "d", bundleHash: "bundle-fixed" },
  profileVersion: null, profileHash: null, triples: [], diagnostics: [] };
describe("M4中文身份与时间视图", () => {
  it("固定Release明确绑定历史profile和manifest，未知不冒充无影响", () => {
    const html = renderToStaticMarkup(createElement(IdentityTimeReadView, { snapshot, selected: "", onSelect: () => undefined }));
    for (const text of ["release-fixed", "manifest-fixed", "LEGACY_G2 / UNKNOWN", "[from,to)", "同编号、同标签不自动合并", "尚无匹配"])
      expect(html).toContain(text);
  });
  it("只读或dirty表单全部禁用，资产scope没有可输入组织或外部厂区", () => {
    const draft = { scope: { organizationId: "org-fixed", siteIds: ["site-a", "site-b"] } } as OntologyDraft;
    const html = renderToStaticMarkup(createElement(IdentityTimeEditForm, { draft, snapshot, blocked: "未保存源码或无编辑权限", busy: false,
      onCommit: () => undefined, onPending: () => undefined }));
    expect(html).toMatch(/readOnly=""/i);
    expect(html).toContain("org-fixed");
    expect(html).toContain('<option value="site-a"');
    expect(html).toContain('disabled=""');
    for (const text of ["未保存源码或无编辑权限", "关闭 / 收窄历史有效期", "事件时间起点", "事件观察时间", "原子提交身份时间"])
      expect(html).toContain(text);
    expect(html).not.toContain("删除身份声明");
  });
});
