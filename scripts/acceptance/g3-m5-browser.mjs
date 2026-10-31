/** M5真实复杂源/只读API与中文工作台；沿用现有OIDC用户和当前任务隔离环境。 */
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve, relative, isAbsolute } from "node:path";
import { randomUUID } from "node:crypto";
import { evidenceDirectory } from "./evidence-paths.mjs";

/** 从真实ReleaseSummary嵌套manifest取固定ID，只选择已发布可读状态。 */
export function readableRelease(releases) {
  const candidates = releases.filter(item => ["ACTIVE", "SUPERSEDED"].includes(item.status)
    && typeof item.manifest?.releaseId === "string" && item.manifest.releaseId.length > 0);
  return candidates.find(item => item.status === "ACTIVE") ?? candidates[0];
}

/** 端点依据合同的manifest.releaseId，不使用不存在的顶层releaseId。 */
export function expressionReleasePath(release) {
  return "/api/v1/releases/" + encodeURIComponent(release.manifest.releaseId) + "/expressions";
}

/** 复杂源保真与发布分级独立验收；完整链中的M1–M4仍走原真实发布/查询/回滚。 */
export async function runM5Checks({ root, origin, operator, viewer, single, check, command, apiOnly = false, requireRelease = false, setPhase }) {
  const evidence = evidenceDirectory(root);
  const boundary = relative(resolve(root, "docs/evidence/G3-M5-001"), evidence);
  if (boundary.startsWith("..") || isAbsolute(boundary)) throw new Error("m5_evidence_boundary_required");
  await mkdir(evidence, { recursive: true });
  const checks = [], startedAtUtc = new Date().toISOString(), tick = performance.now();
  let phase = "create", status = "FAIL", fixedRelease = "NOT_RUN";
  const observe = (name, condition, observedStatus) => {
    checks.push({ name, status: condition ? "PASS" : "FAIL", ...(observedStatus === undefined ? {} : { observedStatus }) });
    check("m5_" + name, Boolean(condition), observedStatus);
    if (!condition) throw new Error("m5_assertion_failed");
  };
  const step = value => { phase = value; setPhase("m5_" + value); };
  async function request(user, method, path, data, label, expected = 200) {
    const headers = { ...user.headers, ...(data?.command ? { "If-Match": '"' + data.command.expectedRevision + '"' } : {}) };
    const response = await user.api[method](origin + path, { headers, ...(data ? { data } : {}) });
    observe(label, response.status() === expected, response.status());
    return response.json();
  }
  try {
    const sources = {};
    for (const [key, file] of [["ontologyTurtle", "ontology.ttl"], ["shapesTurtle", "shapes.ttl"], ["vocabularyTurtle", "vocabulary.ttl"], ["dataTurtle", "data.ttl"]]) {
      sources[key] = await readFile(resolve(root, "samples/g2", file), "utf8");
    }
    sources.ontologyTurtle += "\n" + await readFile(resolve(root, "samples/g3/m5/advanced.owl.ttl"), "utf8");
    const name = "Synthetic M5 OWL " + randomUUID().slice(0, 8);
    let draft = await request(operator, "post", "/api/v1/ontology-drafts", { name, sources, baseReleaseId: null,
      scope: { organizationId: "org-demo", siteIds: ["site-a", "site-b"] }, command: command(0) }, "create_complex_source");
    const path = "/api/v1/ontology-drafts/" + draft.draftId, revision = draft.revision;
    const readPath = path + "/expressions?revision=" + revision;
    step("fixed_read_authorization");
    const snapshot = await request(viewer, "get", readPath, null, "viewer_reads_saved_complex");
    const ontology = snapshot.sources.find(source => source.sourceId === "ontology");
    observe("exact_version_scope_hash", snapshot.version.kind === "DRAFT" && snapshot.version.id === draft.draftId
      && snapshot.version.revision === revision && snapshot.hashes.bundleHash === draft.hashes.bundleHash
      && snapshot.scope.siteIds.length === 2 && snapshot.profileVersion === "4");
    observe("preserved_readonly_blocked_uninferred", ontology?.sourceHash === draft.hashes.ontologyHash && ontology.sourcePreserved
      && ontology.readOnlyStructured && ontology.status === "COMPLETE" && !ontology.editable && !ontology.inferred && ontology.publishEligible === "BLOCKED");
    for (const kind of ["restriction", "intersection", "union", "complement", "list"]) {
      observe("real_" + kind, ontology.nodes.some(node => node.kind === kind));
    }
    const chain = ontology.nodes.find(node => node.term.value === "urn:synthetic:m5:chain");
    const head = chain.properties.find(property => property.predicateIri.endsWith("#propertyChainAxiom")).values[0];
    const list = ontology.nodes.find(node => node.term.kind === head.kind && node.term.value === head.value);
    observe("property_chain_order", JSON.stringify(list.orderedItems.map(item => item.value)) === JSON.stringify(["urn:synthetic:m5:p", "urn:synthetic:m5:q"]));
    observe("imports_are_reference_only", ontology.diagnostics.some(item => item.code === "imports_not_loaded"));
    observe("cardinality_lexical_preserved", ontology.nodes.some(node => node.properties.some(property => property.values.some(value => value.value === "+02"))));
    await request(single, "get", readPath, null, "single_site_read_denied", 403);
    await request(viewer, "get", path + "/expressions?revision=0", null, "invalid_revision_denied", 422);
    await request(viewer, "get", path + "/expressions?revision=999999", null, "missing_revision_denied", 404);
    const before = await request(operator, "get", path, null, "read_after_projection");
    observe("read_causes_no_revision_or_source_change", before.revision === revision && before.hashes.bundleHash === draft.hashes.bundleHash
      && Object.keys(sources).every(slot => before.sources[slot] === sources[slot]));
    const assessment = await request(operator, "post", path + "/assessments", { revision, hashes: draft.hashes, command: command(revision) }, "complex_assessment");
    observe("complex_assessment_cannot_publish", assessment.publishEligible === false);
    await request(operator, "post", path + "/edits", { edit: { subjectIri: "urn:synthetic:m5:A",
      predicateIri: "http://www.w3.org/2000/01/rdf-schema#subClassOf", oldObject: null,
      newObject: { kind: "iri", value: "urn:synthetic:m5:B", datatype: null, language: null } }, command: command(revision) }, "unsupported_structural_write_denied", 422);
    draft = await request(operator, "put", path, { name, sources, command: command(revision) }, "no_op_save");
    observe("saved_original_bytes_preserved", Object.keys(sources).every(slot => draft.sources[slot] === sources[slot]));
    const historical = await request(viewer, "get", readPath, null, "old_revision_still_readable");
    observe("historical_read_has_original_hash", historical.hashes.bundleHash === snapshot.hashes.bundleHash && historical.version.revision === revision);
    const releases = await request(viewer, "get", "/api/v1/releases", null, "read_compatible_release_catalog");
    const selectedRelease = readableRelease(releases);
    if (requireRelease) observe("published_control_release_available", Boolean(selectedRelease));
    if (selectedRelease) {
      const released = await request(viewer, "get", expressionReleasePath(selectedRelease), null, "fixed_released_expressions");
      observe("release_ref_is_fixed_and_uninferred", released.version.kind === "RELEASE" && released.version.revision === null
        && released.version.id === selectedRelease.manifest.releaseId && released.sources.every(source => !source.inferred && !source.editable));
      fixedRelease = "PASS";
    }
    if (apiOnly) { status = "PASS"; return; }
    step("readonly_ui_and_export");
    const page = operator.page;
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(origin + "/ontologies");
    await page.getByRole("button").filter({ has: page.locator("strong", { hasText: name }) }).click();
    await page.getByRole("button", { name: "高阶表达式", exact: true }).click();
    const view = page.getByRole("region", { name: "高阶表达式只读视图", exact: true });
    await view.waitFor();
    observe("chinese_limits_visible", (await view.textContent()).includes("allValuesFrom 不保证存在") && (await view.textContent()).includes("Monaco") === false);
    const ontologyTree = view.locator('details[aria-label="表达式源 ontology"]');
    await ontologyTree.locator(":scope > summary").focus();
    await page.keyboard.press("Enter");
    observe("keyboard_collapses_source", await ontologyTree.getAttribute("open") === null);
    await page.keyboard.press("Enter");
    observe("keyboard_expands_source", await ontologyTree.getAttribute("open") !== null);
    const details = ontologyTree.locator("details");
    for (let index = 0; index < Math.min(await details.count(), 128); index++) await details.nth(index).evaluate(element => { element.open = true; });
    observe("ordered_list_visible", await ontologyTree.getByRole("list", { name: "有序 RDF List 成员" }).count() > 0);
    const theme = page.getByRole("button", { name: "切换深浅主题", exact: true });
    if (await page.evaluate(() => document.documentElement.dataset.theme ?? "dark") !== "light") await theme.click();
    observe("light_theme", await page.evaluate(() => document.documentElement.dataset.theme) === "light");
    await page.screenshot({ path: resolve(evidence, "m5-owl-light.png") });
    await theme.click();
    observe("dark_theme", await page.evaluate(() => document.documentElement.dataset.theme) === "dark");
    await page.screenshot({ path: resolve(evidence, "m5-owl-dark.png") });
    await page.setViewportSize({ width: 390, height: 844 });
    const center = page.getByRole("button", { name: "源码", exact: true });
    if (await center.count()) await center.first().click();
    await page.getByRole("button", { name: "高阶表达式", exact: true }).click();
    await view.waitFor();
    observe("narrow_no_horizontal_document_overflow", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    await page.screenshot({ path: resolve(evidence, "m5-owl-narrow.png") });
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.getByRole("button", { name: "查看 ontology 原始源码", exact: true }).click();
    await page.getByRole("combobox", { name: "选择源文档", exact: true }).selectOption("ontologyTurtle");
    const waiting = page.waitForEvent("download");
    await page.getByRole("button", { name: "导出原始源", exact: true }).click();
    const downloaded = await readFile(await (await waiting).path());
    observe("complex_source_export_exact_bytes", downloaded.equals(Buffer.from(sources.ontologyTurtle, "utf8")));
    await page.getByRole("button", { name: "高阶表达式", exact: true }).click();
    await view.waitFor();
    const routePattern = "**/api/v1/ontology-drafts/*/expressions?revision=*";
    await page.route(routePattern, route => route.fulfill({ status: 503, contentType: "application/problem+json",
      body: JSON.stringify({ type: "about:blank", title: "Synthetic expression dependency failure", status: 503 }) }));
    await page.getByRole("button", { name: "刷新高阶表达式", exact: true }).click();
    await page.getByRole("region", { name: "草稿高阶表达式", exact: true }).getByRole("alert").waitFor();
    observe("dependency_failure_is_visible", true);
    await page.unroute(routePattern);
    await page.getByRole("button", { name: "刷新高阶表达式", exact: true }).click();
    await view.waitFor();
    observe("dependency_recovery_reloads_bound_snapshot", (await view.textContent()).includes(draft.hashes.bundleHash));
    status = "PASS";
  } finally {
    await writeFile(resolve(evidence, apiOnly ? "m5-api.json" : "m5-browser.json"), JSON.stringify({ taskId: "G3-M5-001", status,
      phase, startedAtUtc, completedAtUtc: new Date().toISOString(), durationMs: performance.now() - tick, checks, fixedRelease,
      limitations: ["真实付费LLM/Monaco/Windows/Intel/生产NOT_RUN或BLOCKED；兼容发布在完整M1–M4链单独验收。"] }, null, 2) + "\n");
  }
}
