/** M1验收仅接收既有受控验收器注入的认证会话；不读取认证文件或登录材料。 */
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { randomUUID, createHash } from "node:crypto";
import { evidenceDirectory } from "./evidence-paths.mjs";

/** 在已经建立的Synthetic测试会话中验证真实API与浏览器，不另建认证流程。 */
export async function runM1Checks({ root, origin, operator, viewer, single, check, command, setPhase }) {
  const checks = [];
  const observed = (name, condition, status) => {
    checks.push({ name, status: condition ? "PASS" : "FAIL" });
    check(name, condition, status);
  };
  const evidence = evidenceDirectory(root);
  let phase = "profile";
  let failed = false;
  const step = name => { phase = name; setPhase("m1_" + name); };
  async function post(path, data, expected = 200, match = true) {
    const response = await operator.api.post(origin + path, { data, headers: { ...operator.headers,
      ...(match && data?.command ? { "If-Match": '"' + data.command.expectedRevision + '"' } : {}) } });
    observed("m1_http_" + path.split("/").at(-1) + "_" + checks.length, response.status() === expected, response.status());
    return response.json();
  }
  try {
    const profileResponse = await viewer.api.get(origin + "/api/v1/semantic/support-profile");
    observed("m1_profile_authorized", profileResponse.status() === 200);
    const profile = await profileResponse.json();
    observed("m1_profile_twenty_asserted", profile.capabilities.length === 20 && profile.reasoningMode === "ASSERTED_ONLY");
    observed("m1_profile_budgets", profile.hash.length === 64 && profile.comparisonBudget.maxBlankNodes === 128
      && profile.comparisonBudget.maxSearchNodes === 100000 && profile.comparisonBudget.timeoutMilliseconds === 5000);
    step("four_source_bytes");
    const sources = {};
    const fields = [["ontologyTurtle", "ontology.ttl"], ["shapesTurtle", "shapes.ttl"],
      ["vocabularyTurtle", "vocabulary.ttl"], ["dataTurtle", "data.ttl"]];
    for (const [key, file] of fields) {
      sources[key] = "\uFEFF# M1 UTF8 中文 🧪\r\n" + (await readFile(resolve(root, "samples/g2", file), "utf8")).replace(/\r?\n/g, "\r\n");
    }
    const name = "Synthetic M1 bytes " + randomUUID().slice(0, 8);
    let draft = await post("/api/v1/ontology-drafts", { name, sources, baseReleaseId: null,
      scope: { organizationId: "org-demo", siteIds: ["site-a", "site-b"] }, command: command(0) });
    observed("m1_four_source_persist_exact", JSON.stringify(draft.sources) === JSON.stringify(sources));
    observed("m1_four_hashes_exact", Object.entries(sources).every(([key, value]) =>
      draft.hashes[key.replace("Turtle", "Hash")] === createHash("sha256").update(value, "utf8").digest("hex")));
    const revision1 = draft.revision;
    const noOp = await operator.api.put(origin + "/api/v1/ontology-drafts/" + draft.draftId, {
      headers: { ...operator.headers, "If-Match": '"' + draft.revision + '"' }, data: { name, sources, command: command(draft.revision) } });
    observed("m1_noop_save", noOp.status() === 200);
    draft = await noOp.json();
    observed("m1_noop_bytes", JSON.stringify(draft.sources) === JSON.stringify(sources));
    const compare = await post("/api/v1/ontology-comparisons", {
      from: { kind: "DRAFT", id: draft.draftId, revision: revision1 }, to: { kind: "DRAFT", id: draft.draftId, revision: draft.revision } });
    observed("m1_four_noop_graphs", compare.length === 4 && compare.every(item => !item.sourceChanged && item.graph.status === "EQUIVALENT"));
    const request = { revision: draft.revision, hashes: draft.hashes, command: command(draft.revision) };
    const assessmentPath = "/api/v1/ontology-drafts/" + draft.draftId + "/assessments";
    await post(assessmentPath, request, 428, false);
    await post(assessmentPath, { ...request, command: command(draft.revision), publishEligible: true }, 400);
    const assessment = await post(assessmentPath, { ...request, command: command(draft.revision) });
    observed("m1_real_assessment_stages", assessment.publishEligible && assessment.budgetStatus === "COMPLETE"
      && assessment.stages.filter(stage => stage.status === "PASS").length === 4
      && assessment.stages.some(stage => stage.name === "OWL_REASONING" && stage.status === "NOT_RUN"));
    observed("m1_assessment_binding", assessment.revision === draft.revision && assessment.hashes.bundleHash === draft.hashes.bundleHash
      && assessment.profileHash === profile.hash && assessment.assessmentHash.length === 64);
    observed("m1_assessment_persistent", (await operator.api.get(origin + "/api/v1/semantic-assessments/" + assessment.assessmentId)).status() === 200);
    observed("m1_assessment_scope", (await single.api.get(origin + "/api/v1/semantic-assessments/" + assessment.assessmentId)).status() === 403);
    const wrongRole = await viewer.api.post(origin + assessmentPath, { data: "{", headers: { "Content-Type": "application/json" } });
    observed("m1_role_prebinding", wrongRole.status() === 403);
    step("invalid_turtle");
    const invalid = await operator.api.put(origin + "/api/v1/ontology-drafts/" + draft.draftId, {
      headers: { ...operator.headers, "If-Match": '"' + draft.revision + '"' },
      data: { name, sources: { ...sources, ontologyTurtle: "{" }, command: command(draft.revision) } });
    observed("m1_invalid_turtle_rejected", invalid.status() === 422);
    const after = await (await operator.api.get(origin + "/api/v1/ontology-drafts/" + draft.draftId)).json();
    observed("m1_invalid_no_revision", after.revision === draft.revision && after.hashes.bundleHash === draft.hashes.bundleHash);
    step("ui_export_reimport");
    const page = operator.page;
    const uiErrors = [];
    page.on("pageerror", () => uiErrors.push("pageerror"));
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(origin + "/ontologies");
    await page.getByRole("button").filter({ has: page.locator("strong", { hasText: name }) }).click();
    await page.getByRole("region", { name: "20项能力矩阵，可横向滚动" }).waitFor();
    observed("m1_ui_twenty_rows", await page.locator(".g3-profile-table tbody tr").count() === 20);
    for (const [key, file] of fields) {
      await page.getByRole("combobox", { name: "选择源文档" }).selectOption(key);
      const waiting = page.waitForEvent("download");
      await page.getByRole("button", { name: "导出原始源", exact: true }).click();
      const bytes = await readFile(await (await waiting).path());
      observed("m1_ui_export_" + key, bytes.equals(Buffer.from(sources[key], "utf8")));
      await page.getByLabel("载入" + file, { exact: true }).setInputFiles({ name: file, mimeType: "text/turtle", buffer: bytes });
      observed("m1_ui_reimport_clean_" + key, await page.getByRole("button", { name: "保存新修订", exact: true }).isDisabled());
    }
    await page.getByRole("textbox", { name: "变更理由", exact: true }).fill("Synthetic M1 browser assessment");
    const response = page.waitForResponse(value => value.url().endsWith("/assessments") && value.request().method() === "POST");
    await page.getByRole("button", { name: "评估发布资格", exact: true }).click();
    observed("m1_ui_real_assessment", (await response).status() === 200);
    await page.getByText(/ELIGIBLE · 当前评估符合/).waitFor();
    await page.getByRole("button", { name: "精确比较四源", exact: true }).click();
    await page.getByText("四源比较已返回；逐源查看状态。", { exact: true }).waitFor();
    observed("m1_ui_four_comparisons", await page.locator("section[aria-label='版本源比较'] article").count() === 4);
    await page.getByRole("button", { name: "精确比较四源", exact: true }).focus();
    await page.keyboard.press("Tab");
    observed("m1_ui_keyboard", await page.evaluate(() => document.activeElement !== document.body));
    await mkdir(resolve(evidence, "screenshots"), { recursive: true });
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 1000 });
      if (width === 390) await page.getByRole("button", { name: "图与校验", exact: true }).click();
      for (const theme of ["light", "dark"]) {
        if (await page.evaluate(() => document.documentElement.dataset.theme) !== theme) {
          await page.getByRole("button", { name: "切换深浅主题", exact: true }).click();
        }
        observed("m1_ui_" + width + "_" + theme, await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await page.screenshot({ path: resolve(evidence, "screenshots/m1-" + width + "-" + theme + ".png"), fullPage: true });
      }
    }
    observed("m1_ui_no_hydration", uiErrors.length === 0);
    step("v2_fallback_artifact");
    const ids = JSON.parse(await readFile(resolve(evidence, "full-chain-identifiers.json"), "utf8"));
    const formal = await (await operator.api.get(origin + "/api/v1/releases/" + ids.ids.release1)).json();
    observed("m1_v2_formal_binding", formal.manifest.schemaVersion === 2 && formal.manifest.semantics?.assessmentHash?.length === 64);
    await mkdir(resolve(root, "artifacts/g3-m1"), { recursive: true });
    await writeFile(resolve(root, "artifacts/g3-m1/actual-v2-manifest.json"), JSON.stringify(formal.manifest));
  } catch (error) {
    failed = true;
    throw error;
  } finally {
    await writeFile(resolve(evidence, "m1-browser.json"), JSON.stringify({ status: failed ? "FAIL" : "PASS", phase, checks,
      scope: "Injected Synthetic authenticated sessions; actual API/PG/Jena/Web; no new credential reader" }, null, 2) + "\n");
  }
}
