/** M3仅消费本轮真实OIDC上下文；四源RDF、原子编辑、UI及既有正式发布链共用同一合成资产。 */
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve, relative, isAbsolute } from "node:path";
import { createHash, randomUUID } from "node:crypto";
import { execFileSync } from "node:child_process";
import { evidenceDirectory } from "./evidence-paths.mjs";
import { fullChain } from "./g2-full-chain.mjs";

const skos = "http://www.w3.org/2004/02/skos/core#";
const p = "urn:ontology-platform:semantics:";
const rdfs = "http://www.w3.org/2000/01/rdf-schema#";
const owl = "http://www.w3.org/2002/07/owl#";
const iri = value => ({ kind: "iri", value, datatype: null, language: null });
const literal = (value, language = null, datatype = null) => ({ kind: "literal", value, datatype, language });
const hashKeys = ["ontologyHash", "shapesHash", "vocabularyHash", "dataHash", "bundleHash"];
const sameHashes = (left, right) => hashKeys.every(key => Object.hasOwn(left, key) && left[key] === right[key]);
const sameTerm = (left, right) => Boolean(left && right) && ["kind", "value", "datatype", "language"].every(key => left[key] === right[key]);
const contains = (snapshot, subject, predicate, value) => snapshot.triples.some(row => row.triple.subject.value === subject
  && row.triple.predicate === predicate && row.triple.object.value === value);

/** API_ONLY只证明服务子集；uiOnly和完整模式都执行真实UI、异人审批、Run/SSE、正式查询及回滚。 */
export async function runM3Checks({ root, origin, operator, audit, single, viewer, check, command, apiOnly = false, uiOnly = false, setPhase }) {
  const address = new URL(origin);
  if (!["localhost", "127.0.0.1", "[::1]"].includes(address.hostname) || address.protocol !== "http:") throw new Error("m3_local_origin_required");
  const evidence = evidenceDirectory(root);
  const allowed = ["G3-M3-001", "G3-M4-001", "G3-M5-001"].some(task => {
    const boundary = relative(resolve(root, "docs/evidence", task), evidence);
    return !boundary.startsWith("..") && !isAbsolute(boundary);
  });
  if (!allowed) throw new Error("m3_evidence_task_boundary_required");
  await mkdir(evidence, { recursive: true });
  const checks = [];
  const samples = [];
  const startedAtUtc = new Date().toISOString();
  const started = performance.now();
  let phase = "profile";
  let status = "FAIL";
  let identifiers = {};
  const observe = (name, condition, observedStatus) => {
    checks.push({ name, status: condition ? "PASS" : "FAIL", ...(observedStatus === undefined ? {} : { observedStatus }) });
    check("m3_" + name, Boolean(condition), observedStatus);
    if (!condition) throw new Error("m3_assertion_failed");
  };
  const step = name => { phase = name; setPhase("m3_" + name); };
  async function get(user, path, label, expected = 200) {
    const timer = performance.now();
    const response = await user.api.get(origin + path);
    samples.push({ operation: label, durationMs: performance.now() - timer, status: response.status() });
    observe(label + "_http", response.status() === expected, response.status());
    return response.json();
  }
  async function post(user, path, data, label, expected = 200, match = true) {
    const timer = performance.now();
    const response = await user.api.post(origin + path, { data, headers: { ...user.headers,
      ...(match && data?.command ? { "If-Match": '"' + data.command.expectedRevision + '"' } : {}) } });
    samples.push({ operation: label, durationMs: performance.now() - timer, status: response.status() });
    observe(label + "_http", response.status() === expected, response.status());
    return response.json();
  }
  const request = (draft, changes) => ({ hashes: draft.hashes, changes, command: command(draft.revision) });
  try {
    observe("mode_not_contradictory", !(apiOnly && uiOnly));
    step("profile");
    const profile = await get(viewer, "/api/v1/semantic/support-profile", "current_profile");
    observe("current_registered_m3_profile", ["3", "4"].includes(profile.version) && profile.capabilities.length === (profile.version === "4" ? 23 : 22) && profile.reasoningMode === "ASSERTED_ONLY"
      && typeof profile.hash === "string" && profile.hash.length === 64
      && ["21", "22"].every(id => profile.capabilities.some(row => row.id === id && row.edit === "BASIC" && row.preserve === "EXACT")));
    step("create_four_source_vocabulary");
    const sources = {};
    for (const [key, file] of [["ontologyTurtle", "ontology.ttl"], ["shapesTurtle", "shapes.ttl"], ["vocabularyTurtle", "vocabulary.ttl"], ["dataTurtle", "data.ttl"]]) {
      sources[key] = await readFile(resolve(root, "samples/g2", file), "utf8");
    }
    const units = await readFile(resolve(root, "samples/g3-m3/units.ttl"), "utf8");
    const suffix = randomUUID().replaceAll("-", "");
    const concept = "urn:synthetic:m3:concept:" + suffix;
    const scheme = "urn:synthetic:m3:scheme:" + suffix;
    const name = "Synthetic M3 vocabulary " + suffix.slice(0, 8);
    sources.vocabularyTurtle += "\n" + units + "\n"
      + `<${scheme}> a <${skos}ConceptScheme>; <${skos}prefLabel> "合成温度标准集"@zh .\n`
      + `<${concept}> a <${skos}Concept>; <${skos}inScheme> <${scheme}>; <${skos}prefLabel> "合成温度术语"@zh, "Synthetic temperature"@en; `
      + `<${skos}altLabel> "合成气温"@zh; <${skos}hiddenLabel> "合成温度旧拼写"@zh; <${skos}notation> "M3-${suffix}"; `
      + `<${skos}definition> "人工构造的术语标准验收"@zh; <${p}version> "synthetic-1"; <${p}standardSource> <urn:synthetic:m3:standard-v1> .\n`;
    let draft = await post(operator, "/api/v1/ontology-drafts", { name, sources, baseReleaseId: null,
      scope: { organizationId: "org-demo", siteIds: ["site-a", "site-b"] }, command: command(0) }, "create");
    identifiers = { assetId: draft.assetId, draftId: draft.draftId };
    observe("initial_four_source_bytes_and_hashes", JSON.stringify(draft.sources) === JSON.stringify(sources)
      && Object.entries(sources).every(([key, value]) => draft.hashes[key.replace("Turtle", "Hash")] === createHash("sha256").update(value, "utf8").digest("hex")));
    const draftPath = "/api/v1/ontology-drafts/" + encodeURIComponent(draft.draftId);
    const vocabularyPath = draftPath + "/vocabulary";
    const editsPath = draftPath + "/vocabulary-edits";
    let snapshot = await get(viewer, vocabularyPath, "snapshot");
    observe("snapshot_four_source_bound", snapshot.draftId === draft.draftId && snapshot.releaseId === null && snapshot.manifestHash === null
      && snapshot.revision === draft.revision && sameHashes(snapshot.hashes, draft.hashes) && snapshot.profileVersion === profile.version && snapshot.profileHash === profile.hash);
    observe("actual_four_sources_projected", ["ontology", "shapes", "vocabulary", "data"].every(sourceId => snapshot.triples.some(row => row.sourceId === sourceId)));
    observe("terminology_and_unit_identities", contains(snapshot, concept, skos + "prefLabel", "Synthetic temperature")
      && contains(snapshot, concept, skos + "notation", "M3-" + suffix)
      && contains(snapshot, "urn:synthetic:m3:K-v1", p + "symbol", "K")
      && contains(snapshot, "urn:synthetic:m3:C-v1", p + "symbol", "℃")
      && contains(snapshot, "urn:synthetic:m3:reading", p + "nominalUnit", "urn:synthetic:m3:K-v1")
      && contains(snapshot, "urn:synthetic:m3:standard-v1", p + "version", "synthetic-1"));
    observe("seven_explicit_dimension_exponents", ["length", "mass", "time", "electricCurrent", "temperature", "amount", "luminousIntensity"]
      .every(name => snapshot.triples.some(row => row.triple.subject.value === "urn:synthetic:m3:temperature" && row.triple.predicate === p + name + "Exponent")));
    step("scope_cas_atomic_negative");
    await get(single, vocabularyPath, "multisite_read_denied", 403);
    const label = snapshot.triples.find(row => row.sourceId === "vocabulary" && row.triple.subject.value === concept
      && row.triple.predicate === skos + "prefLabel" && row.triple.object.language?.toLowerCase() === "zh");
    observe("exact_label_source_found", Boolean(label));
    const replace = { sourceId: "vocabulary", edit: { subjectIri: concept, predicateIri: skos + "prefLabel", oldObject: label.triple.object, newObject: literal("合成温度术语（修订）", "zh") } };
    await post(viewer, editsPath, request(draft, [replace]), "viewer_write_denied", 403);
    await post(single, editsPath, request(draft, [replace]), "single_write_denied", 403);
    await post(operator, editsPath, request(draft, [replace]), "missing_cas", 428, false);
    const stale = request(draft, [replace]); stale.command = command(draft.revision - 1);
    await post(operator, editsPath, stale, "stale_revision", 409);
    const wrongHash = request(draft, [replace]); wrongHash.hashes = { ...draft.hashes, dataHash: "0".repeat(64) };
    await post(operator, editsPath, wrongHash, "wrong_source_hash", 409);
    const invalidOld = { sourceId: "vocabulary", edit: { ...replace.edit, oldObject: literal("不存在的旧值", "zh") } };
    const comment = { sourceId: "ontology", edit: { subjectIri: "urn:synthetic:metals:Heat", predicateIri: rdfs + "comment", oldObject: null, newObject: literal("Synthetic M3 atomic edit", "zh") } };
    await post(operator, editsPath, request(draft, [comment, invalidOld]), "atomic_late_conflict", 409);
    const preserved = await get(operator, draftPath, "negative_readback");
    observe("all_rejections_preserve_every_source", preserved.revision === draft.revision && sameHashes(preserved.hashes, draft.hashes)
      && JSON.stringify(preserved.sources) === JSON.stringify(draft.sources));
    step("cross_source_atomic_edit_replay");
    const before = draft;
    const batch = request(draft, [comment, replace]);
    draft = await post(operator, editsPath, batch, "cross_source_commit");
    observe("one_revision_two_source_atomic_commit", draft.revision === before.revision + 1
      && draft.hashes.ontologyHash !== before.hashes.ontologyHash && draft.hashes.vocabularyHash !== before.hashes.vocabularyHash
      && draft.sources.shapesTurtle === sources.shapesTurtle && draft.sources.dataTurtle === sources.dataTurtle);
    const replay = await post(operator, editsPath, batch, "same_command_replay");
    observe("idempotent_same_revision_and_hash", replay.revision === draft.revision && sameHashes(replay.hashes, draft.hashes));
    const alteredReplay = { ...batch, changes: [comment] };
    await post(operator, editsPath, alteredReplay, "idempotent_payload_conflict", 409);
    await post(operator, editsPath, request(draft, [replace]), "stale_exact_old_object", 409);
    snapshot = await get(operator, vocabularyPath, "committed_snapshot");
    observe("new_label_real_pg_riot_readback", snapshot.revision === draft.revision && sameHashes(snapshot.hashes, draft.hashes)
      && contains(snapshot, concept, skos + "prefLabel", "合成温度术语（修订）")
      && !contains(snapshot, concept, skos + "prefLabel", "合成温度术语"));
    step("governance_diagnostic_sources");
    const badSources = { ...draft.sources, vocabularyTurtle: draft.sources.vocabularyTurtle
      + `\n<${concept}> <${skos}prefLabel> "冲突首选名称"@ZH .\n`
      + `<urn:synthetic:m3:badReading:${suffix}> a <${owl}DatatypeProperty>; <${p}quantityKind> <urn:synthetic:m3:Temperature>; <${p}dimension> <urn:synthetic:m3:pressure>; <${p}nominalUnit> <urn:synthetic:m3:K-v1> .\n` };
    const invalid = await post(operator, "/api/v1/ontology-drafts", { name: "Synthetic M3 diagnostic " + suffix.slice(0, 8), sources: badSources, baseReleaseId: null,
      scope: { organizationId: "org-demo", siteIds: ["site-a", "site-b"] }, command: command(0) }, "create_conflicting_draft");
    const invalidAssessment = await post(operator, "/api/v1/ontology-drafts/" + invalid.draftId + "/assessments", {
      revision: invalid.revision, hashes: invalid.hashes, command: command(invalid.revision),
    }, "conflict_assessment");
    observe("conflicts_block_formal_eligibility", !invalidAssessment.publishEligible && invalidAssessment.stages.some(stage => stage.name === "GOVERNANCE" && stage.status === "FAIL"));
    for (const code of ["skos_pref_label_conflict", "unit_dimension_mismatch"]) {
      observe("source_diagnostic_" + code, invalidAssessment.diagnostics.some(row => row.diagnostic.code === code && row.sourceId === "vocabulary"
        && row.sourceHash === invalid.hashes.vocabularyHash && row.diagnostic.focusNode && row.diagnostic.path && row.line === null && row.column === null));
    }
    const assess = async label => {
      const assessment = await post(operator, draftPath + "/assessments", { revision: draft.revision, hashes: draft.hashes, command: command(draft.revision) }, label);
      observe(label + "_eligible_fixed_profile", assessment.publishEligible && assessment.revision === draft.revision && sameHashes(assessment.hashes, draft.hashes)
        && assessment.profileVersion === profile.version && assessment.profileHash === profile.hash && assessment.budgetStatus === "COMPLETE"
        && ["PARSE", "SUPPORT", "SHACL_CORE", "GOVERNANCE"].every(name => assessment.stages.some(stage => stage.name === name && stage.status === "PASS"))
        && assessment.stages.some(stage => stage.name === "OWL_REASONING" && stage.status === "NOT_RUN"));
    };
    await assess("api_valid_assessment");
    if (apiOnly) { status = "PASS"; return; }
    step("ui_vocabulary_exact_source_edit");
    const page = operator.page;
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(origin + "/ontologies");
    await page.getByRole("button").filter({ has: page.locator("strong", { hasText: name }) }).click();
    observe("ui_default_source", await page.getByRole("button", { name: "源码视图", exact: true }).getAttribute("aria-pressed") === "true");
    await page.getByRole("textbox", { name: "变更理由", exact: true }).fill("Synthetic M3 real browser semantic edit");
    await page.getByRole("button", { name: "术语与单位", exact: true }).click();
    const workbench = page.getByRole("region", { name: "术语与单位工作区", exact: true });
    const form = page.getByRole("region", { name: "词汇精确批量编辑", exact: true });
    const directory = workbench.getByRole("list", { name: "词汇目录", exact: true });
    await directory.getByRole("button").filter({ hasText: concept }).click();
    observe("ui_directory_real_multilingual_and_notation", (await workbench.innerText()).includes("Synthetic temperature") && (await workbench.innerText()).includes("M3-" + suffix));
    await form.getByRole("combobox", { name: "词汇语义字段", exact: true }).selectOption(skos + "altLabel");
    await form.getByRole("textbox", { name: "词汇RDF值", exact: true }).fill("待取消的合成别名");
    await form.getByRole("button", { name: "排队添加字段", exact: true }).click();
    await page.getByRole("button", { name: "源码视图", exact: true }).click();
    observe("pending_queue_locks_source", await page.getByRole("textbox", { name: "本体 · OWL源码", exact: true }).getAttribute("readonly") !== null);
    await page.getByRole("button", { name: "术语与单位", exact: true }).click();
    await form.getByRole("heading", { name: "待提交批次 1 / 64", exact: true }).waitFor();
    await form.getByRole("button", { name: "取消待提交批次", exact: true }).click();
    await form.getByRole("heading", { name: "待提交批次 0 / 64", exact: true }).waitFor();
    const afterCancel = await get(operator, draftPath, "ui_cancel_readback");
    observe("ui_cancel_does_not_write_revision", afterCancel.revision === draft.revision && sameHashes(afterCancel.hashes, draft.hashes));
    async function editExisting(subject, predicate, oldValue, newValue, newKind) {
      await workbench.getByRole("textbox", { name: "词汇目录搜索", exact: true }).fill(subject);
      await directory.getByRole("button").filter({ hasText: subject }).click();
      const details = form.locator("details");
      if (!await details.evaluate(element => element.open)) await details.locator("summary").click();
      const row = details.locator("article").filter({ hasText: predicate }).filter({ hasText: oldValue });
      await row.getByRole("button", { name: /^编辑字段 / }).click();
      observe("ui_exact_source_" + checks.length, await form.getByRole("combobox", { name: "词汇写入源", exact: true }).inputValue() === "vocabulary");
      await form.getByRole("combobox", { name: "词汇RDF类型", exact: true }).selectOption(newKind);
      await form.getByRole("textbox", { name: "词汇RDF值", exact: true }).fill(newValue);
      await form.getByRole("button", { name: "排队精确替换", exact: true }).click();
      const original = snapshot.triples.find(item => item.sourceId === "vocabulary" && item.triple.subject.value === subject && item.triple.predicate === predicate && item.triple.object.value === oldValue);
      const waiting = page.waitForResponse(response => response.url() === origin + editsPath && response.request().method() === "POST");
      await form.getByRole("button", { name: "批量原子提交", exact: true }).click();
      const response = await waiting;
      observe("ui_real_commit_http_" + checks.length, response.status() === 200, response.status());
      const sent = response.request().postDataJSON();
      observe("ui_old_rdf_term_and_hashes_" + checks.length, sent.changes.length === 1 && sent.changes[0].sourceId === "vocabulary"
        && sameTerm(sent.changes[0].edit.oldObject, original?.triple.object) && sameHashes(sent.hashes, draft.hashes)
        && sent.command.expectedRevision === draft.revision);
      const next = await response.json();
      observe("ui_one_new_revision_" + checks.length, next.revision === draft.revision + 1 && next.sources.shapesTurtle === sources.shapesTurtle && next.sources.dataTurtle === sources.dataTurtle);
      draft = next;
      await form.getByRole("heading", { name: "待提交批次 0 / 64", exact: true }).waitFor();
      snapshot = await get(operator, vocabularyPath, "ui_snapshot_" + checks.length);
      observe("ui_committed_fact_" + checks.length, snapshot.revision === draft.revision && contains(snapshot, subject, predicate, newValue));
    }
    await editExisting(concept, skos + "prefLabel", "合成温度术语（修订）", "合成温度术语·浏览器", "literal");
    await editExisting("urn:synthetic:m3:reading", p + "nominalUnit", "urn:synthetic:m3:K-v1", "urn:synthetic:m3:C-v1", "iri");
    observe("unit_identity_is_version_iri_not_symbol", contains(snapshot, "urn:synthetic:m3:reading", p + "nominalUnit", "urn:synthetic:m3:C-v1")
      && contains(snapshot, "urn:synthetic:m3:K-v1", p + "dimension", "urn:synthetic:m3:temperature")
      && contains(snapshot, "urn:synthetic:m3:C-v1", p + "dimension", "urn:synthetic:m3:temperature"));
    await page.setViewportSize({ width: 390, height: 1000 });
    await page.getByRole("button", { name: "源码", exact: true }).click();
    observe("ui_narrow_source_panel_and_selection", await page.getByRole("button", { name: "术语与单位", exact: true }).getAttribute("aria-pressed") === "true"
      && await directory.getByRole("button").filter({ hasText: "urn:synthetic:m3:reading" }).getAttribute("aria-pressed") === "true"
      && await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.getByRole("button", { name: "图与校验", exact: true }).click();
    await page.getByRole("button", { name: "评估发布资格", exact: true }).waitFor();
    await page.setViewportSize({ width: 1440, height: 1000 });
    await assess("ui_valid_assessment");
    step("publication_query_run_sse_rollback");
    observe("independent_auditor_available", Boolean(audit?.page && audit?.api));
    const published = await fullChain({ root, origin, operator, audit, single, viewer, draft, check: observe, command, setPhase: step });
    observe("chain_returned_fixed_identifiers", published?.assetId === draft.assetId && ["release1", "release2", "runId"].every(key => typeof published?.[key] === "string" && published[key].length > 0));
    identifiers = { ...identifiers, ...published };
    step("immutable_release_vocabulary_after_rollback");
    for (const [index, releaseId] of [published.release1, published.release2].entries()) {
      const release = await get(operator, "/api/v1/releases/" + encodeURIComponent(releaseId), "release_manifest_" + index);
      const fixed = await get(viewer, "/api/v1/releases/" + encodeURIComponent(releaseId) + "/vocabulary", "release_vocabulary_" + index);
      observe("manifest_profile_and_every_hash_" + index, fixed.releaseId === releaseId && fixed.manifestHash === release.manifestHash
        && fixed.revision === release.manifest.revision && sameHashes(fixed.hashes, release.manifest.hashes)
        && fixed.profileVersion === release.manifest.semantics?.profileVersion && fixed.profileHash === release.manifest.semantics?.profileHash);
      observe("fixed_release_retains_terminology_and_unit_binding_" + index, contains(fixed, concept, skos + "prefLabel", "合成温度术语·浏览器")
        && contains(fixed, "urn:synthetic:m3:reading", p + "nominalUnit", "urn:synthetic:m3:C-v1")
        && contains(fixed, "urn:synthetic:m3:standard-v1", p + "version", "synthetic-1"));
      observe("rollback_active_and_superseded_remain_readable_" + index, release.isActive === (index === 0));
      await get(single, "/api/v1/releases/" + encodeURIComponent(releaseId) + "/vocabulary", "release_scope_denied_" + index, 403);
    }
    step("ui_fixed_release_readback");
    await page.goto(origin + "/ontologies");
    await page.getByRole("textbox", { name: "固定词汇Release ID", exact: true }).fill(published.release1);
    const waiting = page.waitForResponse(response => response.url() === origin + "/api/v1/releases/" + encodeURIComponent(published.release1) + "/vocabulary");
    await page.getByRole("button", { name: "读取固定Release词汇", exact: true }).click();
    const fixedResponse = await waiting;
    observe("ui_fixed_release_http", fixedResponse.status() === 200, fixedResponse.status());
    const fixed = await fixedResponse.json();
    const releasedView = page.getByRole("region", { name: "固定Release词汇读取", exact: true });
    await releasedView.getByText(fixed.manifestHash, { exact: true }).waitFor();
    observe("ui_real_fixed_release_profile", (await releasedView.innerText()).includes(published.release1)
      && (await releasedView.innerText()).includes(fixed.profileVersion + " / " + fixed.profileHash));
    status = "PASS";
  } finally {
    const report = { taskId: "G3-M3-001", status, phase, startedAtUtc, completedAtUtc: new Date().toISOString(), durationMs: performance.now() - started,
      sourceHead: execFileSync("git", ["rev-parse", "HEAD"], { cwd: root, encoding: "utf8" }).trim(),
      scope: apiOnly ? "API_ONLY: real OIDC/API/PG/RIOT/SHACL, four-source vocabulary/CAS/governance" : "real M3 UI/API/PG/Jena/RustFS, independent approval/publication/query/Run/SSE/rollback",
      ...(status === "PASS" ? {} : { failureCategory: checks.some(item => item.status === "FAIL") ? "ASSERTION" : "UNEXPECTED_ERROR" }),
      identifiers, checks, samples, notRun: [...(apiOnly ? ["UI / publication / formal query / Run / SSE / rollback"] : []), "real LLM", "QUDT assets / universal unit conversion", "full OWL reasoning", "Windows/Intel native", "production HA/SLO"] };
    await writeFile(resolve(evidence, apiOnly ? "m3-api.json" : uiOnly ? "m3-ui.json" : "m3-browser.json"), JSON.stringify(report, null, 2) + "\n");
    if (status !== "PASS" || checks.length === 0) process.exitCode = 1;
  }
}
