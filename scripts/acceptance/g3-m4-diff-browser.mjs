/** M4两个固定版本的真实OIDC/API/UI窄闭环；不触发发布或报告。 */
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { evidenceDirectory } from "./evidence-paths.mjs";

const hash = text => createHash("sha256").update(text, "utf8").digest("hex");
const ref = draft => ({ kind: "DRAFT", id: draft.draftId, revision: draft.revision });
const slots = { ontology: "ontologyTurtle", shapes: "shapesTurtle", vocabulary: "vocabularyTurtle", data: "dataTurtle" };
export async function runM4DiffChecks({ root, origin, operator, viewer, single, check, command, setPhase, impactAnalysis = false }) {
  const checks = [], started = performance.now();
  let status = "FAIL", phase = "create", ids = {};
  const observe = (name, condition, observedStatus) => {
    checks.push({ name, status: condition ? "PASS" : "FAIL", ...(observedStatus === undefined ? {} : { observedStatus }) });
    check("m4_diff_" + name, Boolean(condition), observedStatus);
  };
  const step = value => { phase = value; setPhase("m4_diff_" + value); };
  async function request(user, method, path, data, label, expected = 200) {
    const response = await user.api[method](origin + path, { headers: { ...user.headers,
      ...(data?.command ? { "If-Match": '"' + data.command.expectedRevision + '"' } : {}) }, ...(data ? { data } : {}) });
    observe(label + "_http", response.status() === expected, response.status());
    return response.json();
  }
  try {
    const sources = {};
    for (const [key, file] of Object.entries(slots)) sources[file] = await readFile(resolve(root, "samples/g2", key + ".ttl"), "utf8");
    const name = "Synthetic M4 Diff " + randomUUID().slice(0, 8);
    const first = await request(operator, "post", "/api/v1/ontology-drafts", { name, sources, baseReleaseId: null,
      scope: { organizationId: "org-demo", siteIds: ["site-a", "site-b"] }, command: command(0) }, "create");
    ids = { assetId: first.assetId, draftId: first.draftId };
    const path = "/api/v1/ontology-drafts/" + first.draftId;
    const save = (previous, ontologyTurtle, label) => request(operator, "put", path,
      { name, sources: { ...sources, ontologyTurtle }, command: command(previous.revision) }, label);
    const compare = (from, to, label, user = viewer, expected = 200) => request(user, "post", "/api/v1/ontology-version-diffs",
      { from, to }, label, expected);
    const classIri = "urn:synthetic:m4:diff:AddedClass";
    const second = await save(first, sources.ontologyTurtle + '\n<' + classIri + '> a <http://www.w3.org/2002/07/owl#Class> .\n'
      + '<' + classIri + '> <http://www.w3.org/2000/01/rdf-schema#label> "类"@zh .\n', "save_named_delta");
    step("fixed_api");
    const diff = await compare(ref(first), ref(second), "fixed_pair");
    observe("fixed_identity_scope", diff.assetId === first.assetId && diff.from.revision === first.revision && diff.to.revision === second.revision
      && diff.scope.siteIds.slice().sort().join(",") === "site-a,site-b" && diff.baseManifestHash === null && diff.targetManifestHash === null);
    observe("all_four_sources_raw_hashes", diff.sources.length === 4 && diff.sources.every(row => Object.hasOwn(slots, row.sourceId)
      && row.baseText === first.sources[slots[row.sourceId]] && row.targetText === second.sources[slots[row.sourceId]]
      && row.baseHash === hash(row.baseText) && row.targetHash === hash(row.targetText)));
    const ontology = diff.sources.find(row => row.sourceId === "ontology");
    observe("typed_ground_delta_statistics", ontology.tripleDeltaStatus === "EXACT" && ontology.graph.status === "DIFFERENT"
      && ontology.targetTripleCount === ontology.baseTripleCount + 2 && ontology.addedTriples.length === 2 && ontology.removedTriples.length === 0
      && ontology.addedTriples.some(triple => triple.object.kind === "literal" && triple.object.value === "类" && triple.object.language === "zh"));
    const self = await compare(ref(second), ref(second), "same_fixed_version");
    observe("same_fixed_version_equivalent", self.sources.every(row => !row.sourceChanged && row.graph.status === "EQUIVALENT"
      && row.tripleDeltaStatus === "EQUIVALENT" && row.addedTriples.length === 0 && row.removedTriples.length === 0));
    await compare(ref(first), ref(second), "partial_scope_denied", single, 403);
    await compare(ref(first), { ...ref(second), revision: 987654321 }, "unknown_fixed_revision", viewer, 404);
    const noCsrf = await operator.api.post(origin + "/api/v1/ontology-version-diffs", { headers: { Origin: origin }, data: { from: ref(first), to: ref(second) } });
    observe("csrf_required", noCsrf.status() === 403, noCsrf.status());
    step("real_ui");
    await operator.page.setViewportSize({ width: 1440, height: 1000 });
    await operator.page.goto(origin + "/ontologies");
    await operator.page.getByRole("button").filter({ has: operator.page.locator("strong", { hasText: name }) }).click();
    const region = operator.page.getByRole("region", { name: "任意固定版本差异", exact: true });
    await region.getByLabel("基准固定修订", { exact: true }).fill(String(first.revision));
    await region.getByLabel("目标固定修订", { exact: true }).fill(String(second.revision));
    const waiting = operator.page.waitForResponse(response => response.url() === origin + "/api/v1/ontology-version-diffs" && response.request().method() === "POST");
    await region.getByRole("button", { name: "比较固定版本四源源码", exact: true }).click();
    observe("ui_real_diff_response", (await waiting).status() === 200);
    const result = region.getByRole("region", { name: "固定版本四源差异结果", exact: true });
    await result.waitFor();
    observe("ui_four_sources_typed_delta", await result.getByRole("article").count() === 4 && (await result.innerText()).includes("Typed delta：EXACT"));
    if (impactAnalysis) {
      await mkdir(resolve(evidenceDirectory(root), "screenshots"), { recursive: true });
      await operator.page.getByRole("textbox", { name: "变更理由", exact: true }).fill("Synthetic fixed-version bounded impact analysis");
      const analyzed = operator.page.waitForResponse(response => response.url() === origin + "/api/v1/impact-reports" && response.request().method() === "POST");
      await region.getByRole("button", { name: "生成所选版本影响分析", exact: true }).click();
      const response = await analyzed;
      observe("ui_arbitrary_pair_report_http", response.status() === 200, response.status());
      const report = await response.json();
      observe("arbitrary_pair_missing_assessment_is_blocked_analysis", report.baselineKind === "VERSION_PAIR" && !report.publishEligible
        && report.diff.from.revision === first.revision && report.diff.to.revision === second.revision
        && report.blockers.some(item => item.blocking) && report.targetSemantics === null);
      await region.getByRole("region", { name: "影响报告详情", exact: true }).waitFor();
      for (const theme of ["light", "dark"]) {
        await operator.page.evaluate(value => { document.documentElement.dataset.theme = value; localStorage.setItem("ontology-platform-theme", value); }, theme);
        await operator.page.setViewportSize({ width: 390, height: 1000 });
        await operator.page.getByRole("button", { name: "图与校验", exact: true }).click();
        observe("report_narrow_" + theme + "_no_overflow", await operator.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
        await region.getByRole("button", { name: "生成所选版本影响分析", exact: true }).focus();
        await operator.page.keyboard.press("Tab");
        observe("report_keyboard_" + theme, await operator.page.evaluate(() => document.activeElement?.tagName !== "BODY"));
        await operator.page.screenshot({ path: resolve(evidenceDirectory(root), "screenshots/m4-report-390-" + theme + ".png"), fullPage: true, animations: "disabled" });
      }
      await operator.page.setViewportSize({ width: 1440, height: 1000 });
    }
    step("blank_and_budget");
    const blankA = await save(second, second.sources.ontologyTurtle + '\n_:m4a <urn:synthetic:m4:edge> "one" .\n', "save_blank_a");
    const blankB = await save(blankA, second.sources.ontologyTurtle + '\n_:m4b <urn:synthetic:m4:edge> "one" .\n', "save_blank_renamed");
    const renamed = (await compare(ref(blankA), ref(blankB), "blank_rename")).sources.find(row => row.sourceId === "ontology");
    observe("blank_renaming_no_semantic_delta", renamed.sourceChanged && renamed.graph.status === "EQUIVALENT"
      && renamed.tripleDeltaStatus === "EQUIVALENT" && !renamed.addedTriples.length && !renamed.removedTriples.length);
    const blankChanged = await save(blankB, second.sources.ontologyTurtle + '\n_:m4c <urn:synthetic:m4:edge> "two" .\n', "save_blank_changed");
    const uncertain = (await compare(ref(blankB), ref(blankChanged), "blank_changed")).sources.find(row => row.sourceId === "ontology");
    observe("changed_blank_preserves_unknown_and_raw", uncertain.graph.status === "DIFFERENT" && uncertain.tripleDeltaStatus === "INDETERMINATE"
      && uncertain.baseText === blankB.sources.ontologyTurtle && uncertain.targetText === blankChanged.sources.ontologyTurtle
      && [...uncertain.addedTriples, ...uncertain.removedTriples].every(row => row.subject.kind !== "blank" && row.object.kind !== "blank"));
    const manyText = second.sources.ontologyTurtle + Array.from({ length: 129 }, (_, index) => '\n_:budget' + index + ' <urn:synthetic:m4:edge> "' + index + '" .').join("") + "\n";
    const many = await save(blankChanged, manyText, "save_over_budget");
    const budget = (await compare(ref(blankChanged), ref(many), "bounded_graph_budget")).sources.find(row => row.sourceId === "ontology");
    observe("budget_never_no_difference", budget.graph.status === "INDETERMINATE" && budget.tripleDeltaStatus === "INDETERMINATE"
      && budget.targetText === manyText);
    status = "PASS";
  } finally {
    await writeFile(resolve(evidenceDirectory(root), "m4-diff.json"), JSON.stringify({ taskId: "G3-M4-001", slice: "B-Diff", impactAnalysis, status, phase,
      durationMs: performance.now() - started, identifiers: ids, checks, notRun: [...(impactAnalysis ? [] : ["impact report UI"]), "approval binding: sibling impact/full-chain checks", "Windows native"] }, null, 2) + "\n");
  }
}
