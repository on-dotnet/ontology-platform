/** M4身份时间真实API、中文UI、固定发布与历史Run隔离；不访问生产或收费模型。 */
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve, relative, isAbsolute } from "node:path";
import { randomUUID, createHash } from "node:crypto";
import { execFileSync } from "node:child_process";
import { evidenceDirectory } from "./evidence-paths.mjs";
import { fullChain } from "./g2-full-chain.mjs";

const p = "urn:ontology-platform:semantics:";
const time = "http://www.w3.org/2006/time#";
const rdfType = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
const xsd = "http://www.w3.org/2001/XMLSchema#";
const iri = value => ({ kind: "iri", value, datatype: null, language: null });
const literal = (value, datatype = null) => ({ kind: "literal", value, datatype, language: null });
const change = (subjectIri, predicateIri, newObject, oldObject = null) => ({ sourceId: "ontology", edit: { subjectIri, predicateIri, oldObject, newObject } });
const contains = (snapshot, subject, predicate, value) => snapshot.triples.some(row => row.triple.subject.value === subject
  && row.triple.predicate === predicate && row.triple.object.value === value);
const sameHashes = (a, b) => ["ontologyHash", "shapesHash", "vocabularyHash", "dataHash", "bundleHash"].every(key => a[key] === b[key]);
const targetA = "urn:synthetic:org-demo:site-a:local:heat-1";
const targetB = "urn:synthetic:org-demo:site-b:local:heat-1";

/** 每个声明使用独立命名区间/端点；缺终点不写空literal或伪无限时间。 */
function claimChanges(id, site, target, from, to, external = "M4-EQ-01", namespace = "erp.synthetic", organization = "org-demo") {
  const rows = [change(id, rdfType, iri(p + "IdentityClaim")),
    ...[["organizationId", organization], ["siteId", site], ["sourceNamespace", namespace], ["externalIdentifier", external]]
      .map(([name, value]) => change(id, p + name, literal(value))),
    change(id, p + "targetIri", iri(target)), change(id, p + "declarationSource", iri("urn:synthetic:m4:source:v1")),
    change(id, p + "validityInterval", iri(id + ":validity")), change(id + ":validity", rdfType, iri(time + "Interval"))];
  for (const [relation, value, suffix] of [["hasBeginning", from, ":from"], ["hasEnd", to, ":to"]]) {
    if (value !== null) rows.push(change(id + ":validity", time + relation, iri(id + suffix)),
      change(id + suffix, rdfType, iri(time + "Instant")), change(id + suffix, time + "inXSDDateTimeStamp", literal(value, xsd + "dateTimeStamp")));
  }
  return rows;
}

/** API_ONLY不认证UI或发布；其余模式实际操作页面后复用异人发布、正式查询、Run/SSE和回滚。 */
export async function runM4Checks({ root, origin, operator, audit, single, viewer, check, command, apiOnly = false, uiOnly = false, setPhase }) {
  const address = new URL(origin);
  if (!["localhost", "127.0.0.1", "[::1]"].includes(address.hostname) || address.protocol !== "http:") throw new Error("m4_local_origin_required");
  const evidence = evidenceDirectory(root);
  const boundary = relative(resolve(root, "docs/evidence/G3-M4-001"), evidence);
  if (boundary.startsWith("..") || isAbsolute(boundary)) throw new Error("m4_evidence_boundary_required");
  await mkdir(evidence, { recursive: true });
  const checks = [], samples = [];
  const startedAtUtc = new Date().toISOString(), started = performance.now();
  let phase = "profile", status = "FAIL", identifiers = {};
  const observe = (name, condition, observedStatus) => {
    checks.push({ name, status: condition ? "PASS" : "FAIL", ...(observedStatus === undefined ? {} : { observedStatus }) });
    check("m4_" + name, Boolean(condition), observedStatus);
    if (!condition) throw new Error("m4_assertion_failed");
  };
  const step = name => { phase = name; setPhase("m4_" + name); };
  async function request(user, method, path, data, label, expected = 200) {
    const start = performance.now();
    const headers = { ...user.headers, ...(data?.command ? { "If-Match": '"' + data.command.expectedRevision + '"' } : {}) };
    const response = await user.api[method](origin + path, { headers, ...(data ? { data } : {}) });
    samples.push({ operation: label, durationMs: performance.now() - start, status: response.status() });
    observe(label + "_http", response.status() === expected, response.status());
    return response.json();
  }
  try {
    observe("mode_unambiguous", !(apiOnly && uiOnly));
    const profile = await request(viewer, "get", "/api/v1/semantic/support-profile", null, "profile");
    observe("registered_current_profile_v4", profile.version === "4" && profile.capabilities.length === 23
      && profile.capabilities.some(item => item.id === "20" && item.publish === "SUPPORTED")
      && profile.capabilities.some(item => item.id === "23" && item.edit === "BASIC") && profile.reasoningMode === "ASSERTED_ONLY");
    const sources = {};
    for (const [key, file] of [["ontologyTurtle", "ontology.ttl"], ["shapesTurtle", "shapes.ttl"], ["vocabularyTurtle", "vocabulary.ttl"], ["dataTurtle", "data.ttl"]]) {
      sources[key] = await readFile(resolve(root, "samples/g2", file), "utf8");
    }
    const suffix = randomUUID().replaceAll("-", "");
    const name = "Synthetic M4 identity " + suffix.slice(0, 8), claim = "urn:synthetic:m4:claim:" + suffix;
    let draft = await request(operator, "post", "/api/v1/ontology-drafts", { name, sources, baseReleaseId: null,
      scope: { organizationId: "org-demo", siteIds: ["site-a", "site-b"] }, command: command(0) }, "create");
    identifiers = { assetId: draft.assetId, draftId: draft.draftId };
    const path = "/api/v1/ontology-drafts/" + encodeURIComponent(draft.draftId), edits = path + "/identity-time-edits";
    const batch = (changes, current = draft) => ({ hashes: current.hashes, changes, command: command(current.revision) });
    step("explicit_identity_scope_and_time");
    const initial = batch([...claimChanges(claim + ":a", "site-a", targetA, "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z"),
      ...claimChanges(claim + ":b", "site-b", targetB, "2026-01-01T08:00:00+08:00", null)]);
    const originalRevision = draft.revision;
    draft = await request(operator, "post", edits, initial, "two_sites_same_external_identifier");
    observe("one_atomic_revision_and_unrelated_source_bytes", draft.revision === originalRevision + 1
      && draft.sources.shapesTurtle === sources.shapesTurtle && draft.sources.dataTurtle === sources.dataTurtle);
    const replay = await request(operator, "post", edits, initial, "idempotent_replay");
    observe("replay_same_revision_hashes", replay.revision === draft.revision && sameHashes(replay.hashes, draft.hashes));
    let snapshot = await request(viewer, "get", path + "/identity-time", null, "scope_snapshot");
    observe("same_number_different_sites_not_merged", contains(snapshot, claim + ":a", p + "targetIri", targetA)
      && contains(snapshot, claim + ":b", p + "targetIri", targetB)
      && !snapshot.triples.some(row => row.triple.predicate === "http://www.w3.org/2002/07/owl#sameAs"));
    observe("unknown_end_is_absent_not_infinite", !snapshot.triples.some(row => row.triple.subject.value === claim + ":b:validity" && row.triple.predicate === time + "hasEnd"));
    draft = await request(operator, "post", edits, batch(claimChanges(claim + ":history", "site-a", targetB, "2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z")), "adjacent_historical_identifier");
    const beforeFailures = draft;
    for (const [label, changes, expected] of [
      ["overlapping_identifier_ambiguous", claimChanges(claim + ":overlap", "site-a", targetB, "2026-01-15T00:00:00Z", "2026-01-20T00:00:00Z"), 422],
      ["unknown_relation_indeterminate", claimChanges(claim + ":unknown", "site-a", targetB, "2026-01-15T00:00:00Z", null), 422],
      ["cross_site_write_denied", claimChanges(claim + ":foreign", "site-other", targetA, "2027-01-01T00:00:00Z", null), 403],
      ["cross_organization_write_denied", claimChanges(claim + ":foreign-org", "site-a", targetA, "2027-01-01T00:00:00Z", null, "ID-X", "erp.synthetic", "org-other"), 403],
      ["historical_identity_cannot_be_overwritten", [change(claim + ":a", p + "targetIri", iri(targetB), iri(targetA))], 409],
      ["historical_identity_cannot_be_deleted", [change(claim + ":a", rdfType, null, iri(p + "IdentityClaim"))], 409],
      ["missing_timezone_rejected", claimChanges(claim + ":bad-zone", "site-a", targetA, "2028-01-01T00:00:00", null, "ID-ZONE"), 422],
      ["reversed_interval_rejected", claimChanges(claim + ":reversed", "site-a", targetA, "2028-02-01T00:00:00Z", "2028-01-01T00:00:00Z", "ID-REVERSED"), 422],
    ]) await request(operator, "post", edits, batch(changes), label, expected);
    const unchanged = await request(operator, "get", path, null, "read_after_failures");
    observe("failures_leave_no_partial_revision", unchanged.revision === beforeFailures.revision && sameHashes(unchanged.hashes, beforeFailures.hashes));
    await request(operator, "post", edits, { ...initial, changes: [change(targetA, "http://www.w3.org/2000/01/rdf-schema#comment", literal("different replay payload"))] }, "same_key_changed_payload_conflict", 409);
    await request(viewer, "post", edits, batch([change(targetA, "http://www.w3.org/2000/01/rdf-schema#comment", literal("无权写入"))]), "viewer_cannot_edit", 403);
    await request(single, "get", path + "/identity-time", null, "single_site_cannot_read_multi_scope", 403);
    const stale = batch([change(targetA, "http://www.w3.org/2000/01/rdf-schema#comment", literal("陈旧命令"))], beforeFailures);
    draft = await request(operator, "post", edits, batch([change(targetA, "http://www.w3.org/2000/01/rdf-schema#comment", literal("M4 audited synthetic annotation"))]), "successful_annotation");
    await request(operator, "post", edits, stale, "stale_revision_fails_closed", 409);
    snapshot = await request(viewer, "get", path + "/identity-time", null, "final_snapshot");
    observe("snapshot_profile_revision_source_provenance", snapshot.revision === draft.revision && sameHashes(snapshot.hashes, draft.hashes)
      && snapshot.profileVersion === profile.version && snapshot.profileHash === profile.hash);
    if (apiOnly) { status = "PASS"; return; }
    step("identity_and_event_ui");
    const page = operator.page;
    await page.goto(origin + "/ontologies");
    await page.getByRole("button").filter({ has: page.locator("strong", { hasText: name }) }).click();
    await page.getByRole("textbox", { name: "变更理由", exact: true }).fill("Synthetic M4 identity and event browser acceptance");
    await page.getByRole("button", { name: "身份与时间", exact: true }).click();
    const structural = page.getByRole("region", { name: "精确结构编辑", exact: true });
    await structural.getByRole("combobox", { name: "结构操作", exact: true }).selectOption("add");
    await structural.getByRole("textbox", { name: "主体IRI", exact: true }).fill("urn:synthetic:m4:pending-guard:" + suffix);
    await structural.getByRole("combobox", { name: "标准声明快捷填入", exact: true }).selectOption("http://www.w3.org/2002/07/owl#Class");
    observe("structural_form_initially_executable", await structural.getByRole("button", { name: "提交真实结构编辑", exact: true }).isEnabled());
    const workspace = page.getByRole("region", { name: "身份与时间工作区", exact: true });
    await workspace.getByRole("textbox", { name: "身份声明IRI", exact: true }).fill(claim + ":ui");
    observe("organization_cannot_expand_scope", await workspace.getByRole("textbox", { name: "身份组织", exact: true }).inputValue() === "org-demo"
      && await workspace.getByRole("textbox", { name: "身份组织", exact: true }).getAttribute("readonly") !== null);
    await workspace.getByRole("combobox", { name: "身份厂区", exact: true }).selectOption("site-a");
    for (const [label, value] of [["身份来源命名空间", "browser.synthetic"], ["身份外部编号", "M4-UI-01"], ["身份目标IRI", targetA],
      ["身份声明来源IRI", "urn:synthetic:m4:browser:source"], ["身份有效起点", "2026-04-01T00:00:00Z"], ["身份有效终点", "2026-05-01T00:00:00Z"]]) {
      await workspace.getByLabel(label, { exact: true }).fill(value);
    }
    await workspace.getByRole("button", { name: "排队新增身份声明", exact: true }).click();
    observe("pending_identity_blocks_other_structural_commit", await structural.getByRole("button", { name: "提交真实结构编辑", exact: true }).isDisabled());
    observe("queued_identity_stays_visible", (await workspace.innerText()).includes(claim + ":ui"));
    for (const [label, value] of [["事件IRI", "urn:synthetic:m4:event:" + suffix], ["事件时间资源IRI", "urn:synthetic:m4:event-time:" + suffix],
      ["事件时间起点", "2026-04-02T00:00:00Z"], ["事件观察时间", "2026-04-02T01:00:00Z"]]) {
      await workspace.getByLabel(label, { exact: true }).fill(value);
    }
    await workspace.getByRole("button", { name: "排队保存事件时间", exact: true }).click();
    const savedResponse = page.waitForResponse(response => response.url() === origin + edits && response.request().method() === "POST");
    await workspace.getByRole("button", { name: "原子提交身份时间", exact: true }).click();
    const saved = await savedResponse;
    observe("ui_identity_and_event_atomic_api", saved.status() === 200, saved.status());
    draft = await saved.json();
    snapshot = await request(viewer, "get", path + "/identity-time", null, "ui_readback");
    observe("ui_persisted_identity_and_separate_observation", contains(snapshot, claim + ":ui", p + "externalIdentifier", "M4-UI-01")
      && contains(snapshot, "urn:synthetic:m4:event:" + suffix, p + "observedAtUtc", "2026-04-02T01:00:00Z"));
    for (const theme of ["light", "dark"]) {
      await page.evaluate(value => { document.documentElement.dataset.theme = value; localStorage.setItem("ontology-platform-theme", value); }, theme);
      await page.setViewportSize({ width: 390, height: 1000 });
      await page.getByRole("button", { name: "源码", exact: true }).click();
      observe("narrow_" + theme + "_no_overflow", await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await workspace.getByRole("textbox", { name: "身份声明IRI", exact: true }).focus();
      await page.keyboard.press("Tab");
      observe("keyboard_focus_" + theme, await page.evaluate(() => document.activeElement?.tagName !== "BODY"));
    }
    await page.getByRole("button", { name: "图与校验", exact: true }).click();
    await page.setViewportSize({ width: 1440, height: 1000 });
    await viewer.page.goto(origin + "/ontologies");
    await viewer.page.getByRole("button").filter({ has: viewer.page.locator("strong", { hasText: name }) }).click();
    await viewer.page.getByRole("button", { name: "身份与时间", exact: true }).click();
    observe("readonly_ui_disables_identity_commit", await viewer.page.getByRole("button", { name: "原子提交身份时间", exact: true }).isDisabled());
    step("publication_active_query_old_run_and_rollback");
    const published = await fullChain({ root, origin, operator, audit, single, viewer, draft, check: observe, command, setPhase: step });
    identifiers = { ...identifiers, ...published };
    for (const releaseId of [published.release1, published.release2]) {
      const release = await request(viewer, "get", "/api/v1/releases/" + releaseId, null, "release_" + releaseId);
      const fixed = await request(viewer, "get", "/api/v1/releases/" + releaseId + "/identity-time", null, "formal_identity_" + releaseId);
      observe("fixed_identity_matches_manifest_" + releaseId, fixed.releaseId === releaseId && fixed.manifestHash === release.manifestHash
        && sameHashes(fixed.hashes, release.manifest.hashes) && fixed.profileVersion === "4" && contains(fixed, claim + ":a", p + "targetIri", targetA));
    }
    status = "PASS";
  } finally {
    await writeFile(resolve(evidence, apiOnly ? "m4-api.json" : uiOnly ? "m4-ui.json" : "m4-browser.json"), JSON.stringify({ taskId: "G3-M4-001", slice: "A", status, phase,
      startedAtUtc, completedAtUtc: new Date().toISOString(), durationMs: performance.now() - started,
      sourceHead: execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim(), identifiers, checks, samples,
      notRun: [...(apiOnly ? ["UI/publication/formal query/Run/SSE/rollback"] : []), "Slice B impact governance", "full OWL reasoning", "Monaco", "real LLM", "Windows/Intel/production"] }, null, 2) + "\n");
    if (status !== "PASS" || checks.length === 0) process.exitCode = 1;
  }
}
