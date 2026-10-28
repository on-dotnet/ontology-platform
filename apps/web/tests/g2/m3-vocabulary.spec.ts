import { expect, test } from "@playwright/test";
import type { OntologyDraft, VocabularyEditsRequest, VocabularySnapshot } from "../../src/lib/api/g2-generated";
const hashes = { ontologyHash: "o", shapesHash: "s", vocabularyHash: "v", dataHash: "d", bundleHash: "b" };
const draft: OntologyDraft = { draftId: "m3-ui", assetId: "m3-asset", name: "M3 Synthetic词汇", revision: 2, etag: '"2"', scope: { organizationId: "org-demo", siteIds: ["site-a"] }, baseReleaseId: null,
  sources: { ontologyTurtle: "# ontology\n", shapesTurtle: "", vocabularyTurtle: "# vocabulary\n", dataTurtle: "" }, hashes, ownerSubjectId: "g2-ui-fixture", updatedAtUtc: "2026-10-28T00:00:00Z",
  projection: { revision: 2, hashes, triples: [], nodes: [], edges: [], structuralEditAllowed: true, diagnostics: [] } };
const iri = (value: string) => ({ kind: "iri" as const, value, datatype: null, language: null });
const snapshot: VocabularySnapshot = { draftId: draft.draftId, releaseId: null, manifestHash: null, revision: 2, hashes, profileVersion: "3", profileHash: "profile3", diagnostics: [], triples: [
  { sourceId: "ontology", triple: { subject: iri("urn:synthetic:m3:temperature"), predicate: "http://www.w3.org/2004/02/skos/core#prefLabel", object: { kind: "literal", value: "温度", language: "ZH", datatype: "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString" } } },
  { sourceId: "vocabulary", triple: { subject: iri("urn:synthetic:m3:temperature"), predicate: "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", object: iri("http://www.w3.org/2004/02/skos/core#Concept") } },
] };
// 有界网络夹具仅证明交互和发包合同，不代表真实PG/Jena/OIDC业务通过。
test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/ontology-drafts", route => route.fulfill({ json: [draft] }));
  await page.route("**/api/v1/ontology-drafts/m3-ui", route => route.fulfill({ json: draft }));
  await page.route("**/api/v1/ontology-drafts/m3-ui/vocabulary", route => route.fulfill({ json: snapshot }));
  await page.route("**/api/v1/semantic/support-profile", route => route.fulfill({ json: { profileId: "m3", version: "3", hash: "profile3", reasoningMode: "ASSERTED_ONLY", capabilities: [{ id: "21", name: "SKOS", edit: "BASIC", preserve: "EXACT", publish: "SUPPORTED", validation: "ASSERTED", reason: "显式治理" }], comparisonBudget: { maxBlankNodes: 128, maxSearchNodes: 100000, timeoutMilliseconds: 5000 } } }));
  await page.route("**/auth/csrf", route => route.fulfill({ json: { requestToken: "bounded-ui-noncredential" } }));
});
for (const width of [1440, 390]) {
  test(`${width}词汇精确替换保留来源/语言，视图切换保留批次，409不丢队列`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1000 });
    let body: VocabularyEditsRequest | undefined;
    await page.route("**/api/v1/ontology-drafts/m3-ui/vocabulary-edits", route => { body = route.request().postDataJSON(); return route.fulfill({ status: 409, json: { code: "vocabulary_edit_conflict" } }); });
    await page.goto("/ontologies");
    await page.getByRole("button", { name: /M3 Synthetic词汇/ }).click();
    await expect(page.getByRole("button", { name: "源码视图", exact: true })).toHaveAttribute("aria-pressed", "true");
    await page.getByRole("textbox", { name: "变更理由", exact: true }).fill("Synthetic词汇精确修订");
    await page.getByRole("button", { name: "术语与单位", exact: true }).click();
    await page.getByRole("list", { name: "词汇目录", exact: true }).getByRole("button", { name: /温度/ }).click();
    await page.getByText(/精确替换 \/ 删除已保存字段/).click();
    await page.getByRole("button", { name: "编辑字段 1", exact: true }).click();
    await expect(page.getByRole("combobox", { name: "词汇写入源" })).toHaveValue("ontology");
    await expect(page.getByRole("textbox", { name: "词汇RDF语言" })).toHaveValue("ZH");
    await page.getByRole("textbox", { name: "词汇RDF值" }).fill("环境温度");
    await page.getByRole("button", { name: "排队精确替换" }).click();
    await page.getByRole("button", { name: "源码视图", exact: true }).click();
    await expect(page.getByRole("textbox", { name: "本体 · OWL源码" })).toHaveAttribute("readonly", "");
    await page.getByRole("button", { name: "术语与单位", exact: true }).click();
    await expect(page.getByRole("heading", { name: "待提交批次 1 / 64" })).toBeVisible();
    await page.getByRole("button", { name: "批量原子提交" }).click();
    await expect(page.locator(".g2-notice[role=alert]")).toContainText("409");
    expect(body?.hashes).toEqual(hashes);
    expect(body?.command.expectedRevision).toBe(2);
    expect(body?.changes[0].sourceId).toBe("ontology");
    expect(body?.changes[0].edit.oldObject?.language).toBe("ZH");
    await expect(page.getByRole("heading", { name: "待提交批次 1 / 64" })).toBeVisible();
    await page.getByRole("button", { name: "取消待提交批次" }).click();
    await expect(page.getByRole("heading", { name: "待提交批次 0 / 64" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}
test("固定历史Release按自身profile读回，拒绝过期草稿快照", async ({ page }) => {
  await page.route("**/api/v1/ontology-drafts/m3-ui/vocabulary", route => route.fulfill({ json: { ...snapshot, revision: 1 } }));
  await page.route("**/api/v1/releases/legacy-release/vocabulary", route => route.fulfill({ json: { ...snapshot, draftId: "historical-draft", releaseId: "legacy-release", manifestHash: "immutable-manifest", profileVersion: null, profileHash: null } }));
  await page.goto("/ontologies");
  await page.getByRole("button", { name: /M3 Synthetic词汇/ }).click();
  await page.getByRole("button", { name: "术语与单位", exact: true }).click();
  await expect(page.getByRole("region", { name: "术语与单位工作区" })).toContainText("快照不可用");
  await page.getByRole("textbox", { name: "固定词汇Release ID" }).fill("legacy-release");
  await page.getByRole("button", { name: "读取固定Release词汇" }).click();
  const released = page.getByRole("region", { name: "固定Release词汇读取" });
  await expect(released).toContainText("immutable-manifest");
  await expect(released).toContainText("LEGACY_G2 / UNKNOWN");
});
