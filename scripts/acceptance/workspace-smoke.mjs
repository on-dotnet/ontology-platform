/** 在完整纵向链前验证真实工作区状态；所有读写使用本轮OIDC会话和合成资产。 */
import { createRequire } from "node:module";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { randomUUID } from "node:crypto";
import { performance } from "node:perf_hooks";
import { evidenceDirectory } from "./evidence-paths.mjs";
const require = createRequire(resolve(import.meta.dirname, "../../apps/web/package.json"));
const { expect } = require("@playwright/test");

/** 状态由真实可见控件与canvas共同证明，不通过CSS类推测默认视图。 */
export async function assertWorkspaceView(page, view, timeout = 3000) {
  await expect(page.getByRole("button", { name: view === "source" ? "源码视图" : "图视图", exact: true }))
    .toHaveAttribute("aria-pressed", "true", { timeout });
  if (view === "source") await expect(page.getByRole("textbox", { name: "本体 · OWL源码", exact: true })).toBeVisible({ timeout });
  else await expect(page.getByRole("region", { name: "本体关系图", exact: true }).locator("canvas").first()).toBeVisible({ timeout });
}

/** 总预算90秒，失败立即结束；注入只隐藏本轮页面canvas并在finally恢复。 */
export async function runWorkspaceSmoke({ root, origin, operator, viewer, command, faultCheck = false, setPhase }) {
  const started = performance.now();
  const startedAtUtc = new Date().toISOString();
  const page = operator.page;
  const oldTimeout = 30000;
  page.setDefaultTimeout(3000);
  const checks = [];
  let fault = null;
  let failure = null;
  let phase = "create";
  let deadline;
  const evidence = evidenceDirectory(root);
  await mkdir(evidence, { recursive: true });
  const check = (name, condition) => {
    checks.push({ name, status: condition ? "PASS" : "FAIL" });
    if (!condition) throw new Error("workspace_smoke_check_failed");
  };
  const step = value => { phase = value; setPhase?.("workspace_smoke_" + value); };
  async function execute() {
    const sources = {};
    for (const [key, file] of [["ontologyTurtle", "ontology.ttl"], ["shapesTurtle", "shapes.ttl"],
      ["vocabularyTurtle", "vocabulary.ttl"], ["dataTurtle", "data.ttl"]]) {
      sources[key] = await readFile(resolve(root, "samples/g2", file), "utf8");
    }
    const name = "Synthetic workspace smoke " + randomUUID().slice(0, 8);
    const created = await operator.api.post(origin + "/api/v1/ontology-drafts", { data: {
      name, sources, scope: { organizationId: "org-demo", siteIds: ["site-a", "site-b"] }, baseReleaseId: null, command: command(0),
    }, headers: operator.headers });
    check("real_create_200", created.status() === 200);
    const draft = await created.json();
    step("default_source");
    await page.goto(origin + "/ontologies");
    await page.getByRole("button").filter({ has: page.locator("strong", { hasText: name }) }).click();
    await assertWorkspaceView(page, "source");
    check("open_defaults_source", true);
    const entity = page.getByRole("region", { name: "本体实体树", exact: true }).getByRole("button").first();
    await entity.click();
    const selectedIri = await entity.getAttribute("title");
    step("explicit_graph");
    await page.getByRole("button", { name: "图视图", exact: true }).click();
    await assertWorkspaceView(page, "graph");
    check("explicit_graph_canvas", true);
    if (faultCheck) {
      const before = performance.now();
      const style = await page.addStyleTag({ content: 'section[aria-label="本体关系图"] canvas { display:none !important }' });
      let observed = false;
      try { await assertWorkspaceView(page, "graph", 300); }
      catch (error) { if (error?.matcherResult?.name !== "toBeVisible") throw error; observed = true; }
      finally { await style.evaluate(element => element.remove()); }
      fault = { outcome: observed ? "FAIL" : "UNEXPECTED_PASS", expectedFailure: true, durationMs: Math.round(performance.now() - before) };
      check("hidden_canvas_fails_quickly", observed && fault.durationMs < 3000);
      await assertWorkspaceView(page, "graph");
      fault.restoredOutcome = "PASS";
    }
    await page.getByRole("button", { name: "源码视图", exact: true }).click();
    await assertWorkspaceView(page, "source");
    check("selection_preserved_across_view", await page.getByRole("region", { name: "本体实体树", exact: true })
      .getByRole("button", { pressed: true }).getAttribute("title") === selectedIri);
    step("cancel_save");
    const editor = page.getByRole("textbox", { name: "本体 · OWL源码", exact: true });
    await editor.fill(sources.ontologyTurtle + "\n# Synthetic cancelled smoke\n");
    await page.getByRole("button", { name: "丢弃未保存修改", exact: true }).click();
    check("cancel_restores_authoritative_bytes", await editor.inputValue() === sources.ontologyTurtle);
    const iri = "urn:synthetic:smoke:" + randomUUID();
    await editor.fill(sources.ontologyTurtle + `\n<${iri}> a <http://www.w3.org/2002/07/owl#Class> .\n`);
    await page.getByRole("textbox", { name: "变更理由", exact: true }).fill("Synthetic workspace smoke save");
    const savedPromise = page.waitForResponse(response => response.url() === origin + "/api/v1/ontology-drafts/" + draft.draftId && response.request().method() === "PUT");
    await page.getByRole("button", { name: "保存新修订", exact: true }).click();
    const savedResponse = await savedPromise;
    check("real_save_200", savedResponse.status() === 200);
    const saved = await savedResponse.json();
    check("save_advances_exact_revision", saved.revision === draft.revision + 1);
    step("historical_diff");
    const diffPromise = page.waitForResponse(response => response.url().includes("/" + draft.draftId + "/diff?"));
    await page.getByRole("button", { name: "读取真实 Diff", exact: true }).click();
    const diffResponse = await diffPromise;
    const diff = await diffResponse.json();
    check("historical_diff_actual_added_iri", diffResponse.status() === 200 && diff.baseRevision === draft.revision
      && diff.targetRevision === saved.revision && diff.addedTriples.some(triple => triple.subject.value === iri));
    step("narrow_panels");
    await page.setViewportSize({ width: 390, height: 844 });
    const tabs = page.locator('[aria-label="移动工作区面板"]');
    for (const [label, region] of [["资产", "资产目录"], ["源码", "草稿源码"], ["图与校验", "图形与验证"]]) {
      await tabs.getByRole("button", { name: label, exact: true }).click();
      if (label !== "图与校验") await expect(page.getByLabel(region, { exact: true })).toBeVisible();
      else await expect(page.getByRole("heading", { name: "所选实体属性", exact: true })).toBeVisible();
    }
    check("narrow_explicit_panels", true);
    await page.setViewportSize({ width: 1440, height: 1000 });
    step("readonly");
    await viewer.page.goto(origin + "/ontologies");
    await viewer.page.getByRole("button").filter({ has: viewer.page.locator("strong", { hasText: name }) }).click();
    await assertWorkspaceView(viewer.page, "source");
    await expect(viewer.page.getByRole("textbox", { name: "本体 · OWL源码", exact: true })).toHaveAttribute("readonly", "");
    await expect(viewer.page.getByRole("button", { name: "保存新修订", exact: true })).toBeDisabled();
    check("viewer_source_readonly_save_disabled", true);
  }
  try {
    await Promise.race([execute(), new Promise((_, reject) => { deadline = setTimeout(() => reject(new Error("workspace_smoke_budget")), 90000); })]);
  } catch (error) { failure = { phase, category: error?.name ?? "Error", details: "SUPPRESSED" }; throw error; }
  finally {
    clearTimeout(deadline);
    page.setDefaultTimeout(oldTimeout);
    await writeFile(resolve(evidence, "workspace-smoke.json"), JSON.stringify({ schemaVersion: 1,
      status: failure ? "FAIL" : "PASS", startedAtUtc, completedAtUtc: new Date().toISOString(),
      durationMs: Math.round(performance.now() - started), checks, fault, failure }, null, 2) + "\n");
  }
}
