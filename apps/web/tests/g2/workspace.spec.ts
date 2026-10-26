import { expect, test } from "@playwright/test";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import type { OntologyDraft, SourceBundle } from "../../src/lib/api/g2-generated";
const hash = "a".repeat(64);
const sources: SourceBundle = { ontologyTurtle: "@prefix ex: <urn:synthetic:> .\nex:Class a <http://www.w3.org/2002/07/owl#Class> .", shapesTurtle: "", vocabularyTurtle: null, dataTurtle: "" };
const hashes = { ontologyHash: hash, shapesHash: hash, vocabularyHash: null, dataHash: hash, bundleHash: hash };
const draft: OntologyDraft = { draftId: "draft-ui", assetId: "asset-ui", scope: { organizationId: "org-demo", siteIds: ["site-a"] }, baseReleaseId: null, revision: 1, etag: '"1"', name: "Synthetic 本体草稿", sources, hashes, ownerSubjectId: "g2-ui-fixture", updatedAtUtc: "2026-10-26T00:00:00Z", projection: { revision: 1, hashes, triples: [], nodes: [{ id: "urn:synthetic:Class", label: "Synthetic Class", kind: "class", typeIris: [] }], edges: [], structuralEditAllowed: true, diagnostics: [] } };
test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/platform/resources*", route => route.fulfill({ json: { items: [], traceId: "fixture", auditId: "fixture" } }));
  await page.route("**/api/v1/ontology-drafts", route => route.fulfill({ json: [draft] }));
  await page.route("**/api/v1/ontology-drafts/draft-ui", route => route.fulfill({ json: draft }));
  await page.route("**/auth/csrf", route => route.fulfill({ json: { requestToken: "ui-only-noncredential" } }));
});
for (const width of [1440, 1280, 390]) {
  test(`${width}深浅主题/ARIA/键盘/SSR水合无错误`, async ({ page }) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/ontologies");
    await expect(page.getByRole("heading", { name: "本体资产与草稿" })).toBeVisible();
    await page.getByRole("button", { name: /Synthetic 本体草稿/ }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("textbox", { name: "本体 · OWL源码" })).toHaveValue(sources.ontologyTurtle);
    if (width === 390) await page.getByRole("button", { name: "图与校验", exact: true }).click();
    await expect(page.getByRole("heading", { name: "RDF 结构投影" })).toBeVisible();
    await page.getByText("键盘访问节点与关系").click();
    await page.getByRole("button", { name: "Synthetic Class", exact: true }).focus();
    await page.keyboard.press("Enter");
    await expect(page.getByText("urn:synthetic:Class", { exact: true })).toBeVisible();
    for (const theme of ["dark", "light"]) {
      if (theme === "light") await page.getByRole("button", { name: "切换深浅主题" }).click();
      await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: `../../docs/evidence/G2-THIN-SLICE-001/FE/screenshots/${width}-${theme}.png`, fullPage: true, animations: "disabled" });
    }
    expect(errors).toEqual([]);
  });
}
test("409保留dirty文本并显式加载/对比远端版本", async ({ page }) => {
  await page.goto("/ontologies");
  await page.getByRole("button", { name: /Synthetic 本体草稿/ }).click();
  const source = page.getByRole("textbox", { name: "本体 · OWL源码" });
  await source.fill("local unsaved <script>alert(1)</script>");
  await page.getByRole("textbox", { name: "变更理由" }).fill("合成冲突测试");
  await page.route("**/api/v1/ontology-drafts/draft-ui", route => route.request().method() === "PUT" ? route.fulfill({ status: 409, json: { code: "revision_conflict", traceId: "safe-fixture-trace" } }) : route.fulfill({ json: { ...draft, revision: 2, sources: { ...sources, ontologyTurtle: "remote version" } } }));
  await page.getByRole("button", { name: "保存新修订" }).click();
  await expect(page.locator(".g2-notice[role=alert]")).toContainText("版本冲突");
  await expect(source).toHaveValue("local unsaved <script>alert(1)</script>");
  await page.getByRole("button", { name: "读取远端版本" }).click();
  await expect(page.getByRole("heading", { name: "远端 revision 2 与本地文本对比" })).toBeVisible();
  await expect(source).toHaveValue("local unsaved <script>alert(1)</script>");
  await page.getByRole("button", { name: "丢弃本地内容并载入此远端版本" }).click();
  await expect(source).toHaveValue("remote version");
});
test("上传真实四份标准源且scope默认不扩大", async ({ page }) => {
  let body: { sources: SourceBundle; scope: { siteIds: string[] } } | null = null;
  await page.route("**/api/v1/ontology-drafts", async route => { if (route.request().method() === "POST") { body = route.request().postDataJSON(); await route.fulfill({ json: { ...draft, sources: body!.sources } }); } else await route.fulfill({ json: [] }); });
  await page.goto("/ontologies");
  await page.getByRole("textbox", { name: "资产名称" }).fill("标准 Synthetic 示例");
  const files = [["ontologyTurtle", "ontology.ttl"], ["shapesTurtle", "shapes.ttl"], ["vocabularyTurtle", "vocabulary.ttl"], ["dataTurtle", "data.ttl"]] as const;
  for (const [key, file] of files) { await page.getByRole("combobox", { name: "选择源文档" }).selectOption(key); await page.getByLabel(`载入${file}`, { exact: true }).setInputFiles(resolve("../../samples/g2", file)); }
  await page.getByRole("textbox", { name: "变更理由" }).fill("导入仓库标准合成源");
  await page.getByRole("button", { name: "创建真实草稿" }).click();
  await expect.poll(() => body?.scope.siteIds).toEqual(["site-a"]);
  for (const [key, file] of files) expect(body!.sources[key]).toBe(readFileSync(resolve("../../samples/g2", file), "utf8"));
});
test("加载/503/403/404准确显示，不虚构成功数据", async ({ page }) => {
  let release: (() => void) | undefined;
  const gate = new Promise<void>(resolveGate => { release = resolveGate; });
  await page.route("**/api/v1/ontology-drafts", async route => { await gate; await route.fulfill({ status: 503, json: { code: "dependency_unavailable", traceId: "ui-503" } }); });
  await page.goto("/ontologies"); await expect(page.getByRole("status")).toContainText("正在加载授权资产"); release!();
  await expect(page.locator(".g2-notice[role=alert]")).toContainText("依赖暂时不可用");
  for (const status of [403, 404]) { await page.route("**/api/v1/ontology-drafts", route => route.fulfill({ status, json: { code: "safe" } })); await page.getByRole("button", { name: "刷新", exact: true }).click(); await expect(page.locator(".g2-notice[role=alert]")).toContainText(`HTTP ${status}`); }
});
test("结构新增Class发送唯一SemanticEdit，不浏览器重建本体", async ({ page }) => {
  let edit: unknown = null;
  await page.route("**/api/v1/ontology-drafts/draft-ui/edits", route => { edit = route.request().postDataJSON(); return route.fulfill({ json: { ...draft, revision: 2, etag: '"2"', projection: { ...draft.projection, revision: 2 } } }); });
  await page.goto("/ontologies"); await page.getByRole("button", { name: /Synthetic 本体草稿/ }).click();
  await page.getByRole("textbox", { name: "变更理由" }).fill("新增合成Class");
  await page.getByRole("combobox", { name: "结构操作" }).selectOption("add");
  await page.getByRole("textbox", { name: "主体IRI" }).fill("urn:synthetic:Added");
  await page.getByRole("combobox", { name: "标准声明快捷填入" }).selectOption("http://www.w3.org/2002/07/owl#Class");
  await page.getByRole("button", { name: "提交真实结构编辑" }).click();
  await expect.poll(() => edit).toMatchObject({ edit: { subjectIri: "urn:synthetic:Added", predicateIri: "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", oldObject: null, newObject: { kind: "iri", value: "http://www.w3.org/2002/07/owl#Class" } }, command: { expectedRevision: 1 } });
});
test("dirty阻断验证/结构编辑，图布局不产生语义写入", async ({ page }) => {
  let writes = 0;
  await page.route("**/api/v1/ontology-drafts/draft-ui/**", route => { if (route.request().method() !== "GET") writes++; return route.fulfill({ status: 503, json: { code: "not_expected" } }); });
  await page.goto("/ontologies"); await page.getByRole("button", { name: /Synthetic 本体草稿/ }).click();
  await page.getByRole("button", { name: "重新布局" }).click();
  await page.getByRole("textbox", { name: "变更理由" }).fill("合成编辑理由");
  await page.getByRole("textbox", { name: "本体 · OWL源码" }).fill("unsaved local text");
  await expect(page.getByRole("button", { name: "验证已保存修订" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "提交真实结构编辑" })).toBeDisabled();
  await expect(page.getByText("本地源码未保存，下图保留上次服务器确认版本。")).toBeVisible();
  expect(writes).toBe(0);
});
test("dirty草稿阻止内部导航，显式丢弃后才离开", async ({ page }) => {
  await page.goto("/ontologies"); await page.getByRole("button", { name: /Synthetic 本体草稿/ }).click();
  await page.getByRole("textbox", { name: "本体 · OWL源码" }).fill("keep this local draft");
  await page.getByRole("link", { name: "发布治理", exact: true }).click();
  await expect(page).toHaveURL(/\/ontologies$/);
  await expect(page.getByRole("textbox", { name: "本体 · OWL源码" })).toHaveValue("keep this local draft");
  await page.getByRole("button", { name: "丢弃未保存修改", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "本体 · OWL源码" })).toHaveValue(sources.ontologyTurtle);
});
