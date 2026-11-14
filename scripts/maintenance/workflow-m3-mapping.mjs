/** M3固定任务的真实Web/浏览器入口；只复用本机依赖，不下载、不写旧任务资源。 */
import { createRequire } from "node:module";
import { readFile, realpath } from "node:fs/promises";
import { resolve } from "node:path";
const root = resolve(import.meta.dirname, "../..");
const args = process.argv.slice(2);
const task = "G4-M3-MAPPING-001", runId = "mapping-impl-01";
function argument(name) {
  const flag = "--" + name, index = args.indexOf(flag);
  if (index < 0 || args.lastIndexOf(flag) !== index || index + 1 >= args.length) throw new Error("MAPPING_ARGUMENT_REQUIRED");
  return args[index + 1];
}
if (argument("task") !== task || argument("run-id") !== runId || await realpath(process.cwd()) !== root) throw new Error("MAPPING_CONSUMER_BOUNDARY");
const mode = argument("mode");
const require = createRequire(resolve(root, "apps/web/package.json"));
if (mode === "serve") {
  const binding = JSON.parse(await readFile(resolve(root, "artifacts/workflow", task, "web-build-binding.json"), "utf8"));
  if (binding.taskId !== task || binding.status !== "PASS" || binding.worktree !== root) throw new Error("MAPPING_WEB_BUILD_REQUIRED");
  process.env.PLATFORM_API_ORIGIN = "http://localhost:15600";
  process.env.NEXT_TELEMETRY_DISABLED = "1";
  process.env.NODE_ENV = "production";
  const { writeFile } = await import("node:fs/promises");
  const { execFileSync } = await import("node:child_process");
  const { createHash } = await import("node:crypto");
  const build = JSON.parse(execFileSync("python3", ["-B", "scripts/maintenance/workflow_m3_mapping.py", "web-start-binding", "--task", task, "--run-id", runId], { cwd: root, timeout: 30000, encoding: "utf8" }));
  const recordPath = resolve(root, "artifacts/workflow", task, runId, "web-process-" + process.pid + ".json");
  const row = { taskId: task, runId, pid: process.pid, worktree: root, port: 15630, build,
    processStartedAt: execFileSync("ps", ["-p", String(process.pid), "-o", "lstart="], { encoding: "utf8", env: { ...process.env, LC_ALL: "C" } }).trim(),
    startedAtUtc: new Date().toISOString(), decision: "KEEP", release: "M3 reviewed closeout" };
  const raw = JSON.stringify(row) + "\n";
  await writeFile(recordPath, raw, { flag: "wx" });
  await writeFile(resolve(root, "artifacts/workflow", task, runId, "web-process-current.json"), JSON.stringify({ path: recordPath, sha256: createHash("sha256").update(raw).digest("hex") }) + "\n");
  await require("next/dist/server/lib/start-server").startServer({ dir: resolve(root, "apps/web"), hostname: "127.0.0.1", port: 15630,
    isDev: false, allowRetry: false, keepAliveTimeout: 5000 });
} else if (["provision", "lifecycle", "visual", "faults", "recovery", "worker", "semantics", "negative", "permissions", "authority", "rotation"].includes(mode)) await browserRun(mode);
else throw new Error("MAPPING_MODE_NOT_IMPLEMENTED");


/** 每轮真实浏览器上下文独立登录，永不保存Cookie、HAR、trace或storageState。 */
async function browserRun(mode) {
  const { randomUUID, createHash } = await import("node:crypto");
  const { writeFile, mkdir } = await import("node:fs/promises");
  const output = resolve(root, "artifacts/workflow", task, runId);
  const privateRoot = resolve(root, ".tools/security/g4-m3-mapping-001", runId);
  const realm = JSON.parse(await readFile(resolve(privateRoot, "runtime/realm.json"), "utf8"));
  if (!realm.authority.startsWith("http://localhost:15680/realms/g2-")) throw new Error("MAPPING_REALM_BOUNDARY");
  const origin = "http://localhost:15600";
  const file = resolve(output, "browser-" + mode + "-" + Date.now() + ".json");
  const report = { taskId: task, runId, mode, startedAtUtc: new Date().toISOString(), checks: [], http: [], status: "FAIL" };
  const { execFileSync } = await import("node:child_process");
  const binding = () => JSON.parse(execFileSync("python3", ["-B", "scripts/maintenance/workflow_m3_mapping.py", "runtime-binding", "--task", task, "--run-id", runId], { cwd: root, timeout: 30000, encoding: "utf8" }));
  const contexts = [];
  let browser, phase = "launch";
  const command = (expectedRevision = 0) => ({ commandId: randomUUID(), idempotencyKey: randomUUID(), expectedRevision, reason: "M3 isolated synthetic acceptance" });
  const check = (name, value) => { report.checks.push({ name, status: value ? "PASS" : "FAIL" }); if (!value) { const error = new Error(); error.safeCode = name; throw error; } };
  const secrets = [realm.clientSecret, ...Object.values(realm.identities).map(value => value.password)];
  async function request(actor, method, path, body, expected = 200, etag) {
    const start = performance.now();
    const response = await actor.context.request.fetch(origin + path, { method, data: body, timeout: 45000, maxRedirects: 0,
      headers: { ...actor.headers, ...(etag ? { "If-Match": etag } : {}), ...(body ? { "Content-Type": "application/json" } : {}) } });
    const raw = await response.text();
    check("no_known_secret_" + report.http.length, !secrets.some(secret => secret && raw.includes(secret)));
    let data; try { data = JSON.parse(raw); } catch { data = null; }
    report.http.push({ method, path, status: response.status(), elapsedMs: performance.now() - start,
      ...(data?.code ? { code: data.code } : {}), sha256: createHash("sha256").update(raw).digest("hex") });
    check("http_" + report.http.length + "_" + expected, (Array.isArray(expected) ? expected.includes(response.status()) : response.status() === expected));
    return { data, status: response.status(), etag: response.headers()["etag"] ?? "" };
  }
  const get = async (actor, path) => (await request(actor, "GET", path)).data;
  const post = async (actor, path, body, expected = 200, etag) => (await request(actor, "POST", path, body, expected, etag ?? (body.command ? `"${body.command.expectedRevision}"` : undefined))).data;
  async function identity(label) {
    phase = "oidc_" + label;
    const context = await browser.newContext({ serviceWorkers: "block" }); contexts.push(context);
    await context.route("**/*", route => {
      if ([origin, "http://localhost:15680"].includes(new URL(route.request().url()).origin)) return route.continue();
      report.externalRequests ??= []; report.externalRequests.push(new URL(route.request().url()).origin); return route.abort();
    });
    context.setDefaultTimeout(15000);
    const page = await context.newPage();
    const user = realm.identities["g2-" + label]; check("identity_exists_" + label, Boolean(user));
    await page.goto(origin + "/auth/login?returnUrl=%2Fdata%2Fmappings");
    await page.locator("#username").fill(user.username); await page.locator("#password").fill(user.password);
    await page.locator("#kc-login").click();
    await page.waitForURL(url => url.origin === origin && url.pathname === "/data/mappings");
    const cookie = (await context.cookies()).find(item => item.name === ".OntologyPlatform.Session");
    check("real_oidc_cookie_" + label, cookie?.httpOnly && cookie.sameSite === "Lax");
    secrets.push(cookie.value);
    const actor = { context, page, headers: { Origin: origin } };
    actor.headers["X-CSRF-TOKEN"] = (await get(actor, "/auth/csrf")).requestToken;
    actor.me = await get(actor, "/api/v1/platform/me");
    return actor;
  }
  async function save(state) { await writeFile(resolve(output, "runtime-fixture.json"), JSON.stringify(state, null, 2) + "\n"); }
  try {
    report.inputBinding = binding();
    const { chromium } = require("@playwright/test");
    browser = await chromium.launch({ channel: "msedge", headless: true, args: ["--disable-background-networking", "--disable-component-update"] });
    const operator = await identity("operator-ab"), auditor = await identity("auditor-ab");
    check("distinct_oidc_subjects", operator.me.subjectId !== auditor.me.subjectId);
    let state;
    try { state = JSON.parse(await readFile(resolve(output, "runtime-fixture.json"), "utf8")); }
    catch { state = { taskId: task, runId, scope: { organizationId: "org-demo", siteIds: ["site-a"] } }; }
    check("fixture_identity", state.taskId === task && state.runId === runId);
    state.subjects = { operator: operator.me.subjectId, auditor: auditor.me.subjectId };
    await save(state);
    if (mode === "provision") {
      if (!state.ontologyDraft) {
        phase = "g3_create";
        const sources = {};
        for (const name of ["ontology", "shapes", "vocabulary", "data"]) sources[name + "Turtle"] = await readFile(resolve(root, "samples/g2", name + ".ttl"), "utf8");
        sources.ontologyTurtle += '\n<urn:synthetic:mapping:Asset> a <http://www.w3.org/2002/07/owl#Class> .\n'
          + '<urn:synthetic:mapping:label> a <http://www.w3.org/2002/07/owl#DatatypeProperty>; <http://www.w3.org/2000/01/rdf-schema#domain> <urn:synthetic:mapping:Asset>; <http://www.w3.org/2000/01/rdf-schema#range> <http://www.w3.org/2001/XMLSchema#string> .\n';
        state.ontologyDraft = await post(operator, "/api/v1/ontology-drafts", { name: "Synthetic M3 fixed vocabulary", scope: state.scope, sources, baseReleaseId: null, command: command() }); await save(state);
      }
      const draft = state.ontologyDraft;
      if (!state.ontologyAssessment) {
        phase = "g3_assessment";
        state.ontologyAssessment = await post(operator, `/api/v1/ontology-drafts/${draft.draftId}/assessments`, { revision: draft.revision, hashes: draft.hashes, command: command(draft.revision) });
        check("g3_assessment_eligible", state.ontologyAssessment.publishEligible); await save(state);
      }
      if (!state.ontologyImpact) {
        phase = "g3_impact";
        const target = { kind: "DRAFT", id: draft.draftId, revision: draft.revision };
        state.ontologyImpact = await post(operator, "/api/v1/impact-reports", { from: target, to: target, baselineKind: "INITIAL", assessmentId: state.ontologyAssessment.assessmentId, command: command(draft.revision) });
        check("g3_impact_eligible", state.ontologyImpact.publishEligible); await save(state);
      }
      if (!state.ontologyProposal) {
        phase = "g3_proposal";
        state.ontologyProposal = await post(operator, "/api/v1/release-proposals", { kind: "PUBLISH", draftId: draft.draftId, draftRevision: draft.revision, hashes: draft.hashes,
          validationReportId: state.ontologyAssessment.validationReportId, targetReleaseId: null, targetManifestHash: null,
          impactReportId: state.ontologyImpact.reportId, impactHash: state.ontologyImpact.canonicalHash, command: command(draft.revision) }); await save(state);
      }
      if (!state.ontologyApproved) {
        phase = "g3_independent_review";
        const p = state.ontologyProposal;
        state.ontologyApproved = await post(auditor, `/api/v1/approvals/${p.proposalId}/decisions`, { decision: "approve", command: command(p.revision) }); await save(state);
      }
      if (!state.ontologyRelease) {
        phase = "g3_activate";
        const p = state.ontologyApproved;
        const receipt = await post(operator, "/api/v1/release-activations", { proposalId: p.proposalId, expectedActivationRevision: 0, expectedActiveReleaseId: null, command: command(p.revision) });
        state.ontologyRelease = await get(operator, `/api/v1/releases/${receipt.releaseId}`); await save(state);
        check("g3_formal_original", state.ontologyRelease.manifest.schemaVersion === 2 && state.ontologyRelease.manifest.artifactObjects.length === 4);
      }
      if (!state.connectionId) {
        const existing = (await get(operator, "/api/v1/connections")).items.filter(value => value.displayName === "M3 synthetic PostgreSQL mapping");
        check("resume_connection_unambiguous", existing.length <= 1);
        if (existing.length === 1) { state.connectionId = existing[0].id; await save(state); }
      }
      if (!state.connectionId) {
        phase = "pg_connection_create";
        const password = await readFile(resolve(privateRoot, "pg-source/reader-password"), "utf8"); secrets.push(password);
        const secret = await post(operator, "/api/v1/connection-secrets", { secretValue: password, scopeSelection: state.scope, purpose: "POSTGRESQL_READONLY", command: command() }, 201);
        secrets.push(secret.secretRef);
        const config = { type: "POSTGRESQL", profile: { host: "pg-source", port: 5432, database: "fixture", username: "fixture_reader", sslMode: "VerifyFull", allowedSchemas: ["production", "public"] } };
        const connection = await post(operator, "/api/v1/connections", { displayName: "M3 synthetic PostgreSQL mapping", scopeSelection: state.scope, config, secretRef: secret.secretRef, command: command() }, 201);
        state.connectionId = connection.id; await save(state);
      }
      const connectionPath = `/api/v1/connections/${state.connectionId}`;
      let current = await request(operator, "GET", connectionPath);
      if (!current.data.probeFresh) {
        phase = "pg_tls_readonly_probe";
        const probe = await post(operator, connectionPath + "/test", { command: command(current.data.configRevision) }, 200, current.etag);
        check("pg_real_probe", probe.status === "TEST_OK");
        current = await request(operator, "GET", connectionPath);
      }
      if (current.data.state !== "ACTIVE") {
        phase = "pg_enable";
        await post(operator, connectionPath + "/enable", { command: command(current.data.configRevision) }, 200, current.etag);
      }
      if (!state.catalog) {
        phase = "pg_catalog"; current = await request(operator, "GET", connectionPath);
        const job = await post(operator, connectionPath + "/discoveries", { command: command(current.data.configRevision) }, 202, current.etag);
        for (let attempt = 0; attempt < 30; attempt++) {
          const progress = await get(operator, connectionPath + "/discoveries/" + job.jobId);
          if (progress.status === "SUCCEEDED") { state.catalog = await get(operator, "/api/v1/catalogs/" + progress.snapshotId); break; }
          check("pg_job_nonfailure_" + attempt, ["QUEUED", "RUNNING"].includes(progress.status));
          await new Promise(done => setTimeout(done, 500));
        }
        check("pg_catalog_ready", state.catalog?.status === "READY"); await save(state);
      }
      report.status = "PASS";
      report.scope = "G3_FORMAL_RELEASE_AND_PG_CATALOG_ONLY";
    } else if (mode === "faults") {
      const { execFileSync } = await import("node:child_process");
      function fixture(operation) {
        const value = JSON.parse(execFileSync("python3", ["-B", "experiments/g4-m3-mapping-001/grant-fixture.py", "--task", task, "--run-id", runId, "--operation", operation], { cwd: root, timeout: 30000, encoding: "utf8" }));
        report.faultOperations ??= []; report.faultOperations.push(value);
        check("fixture_" + operation, value.status === "PASS"); return value.observation;
      }
      const mappingId = state.mappingDraft.mappingId;
      const path = "/api/v1/mappings/" + mappingId;
      const release = state.rounds.second.release;
      phase = "source_revocation_loaded_page";
      await operator.page.goto(origin + "/data/mapping-releases/" + release.manifest.mappingReleaseId);
      await operator.page.getByText("历史发布", { exact: true }).waitFor();
      try {
        fixture("source-deny");
        await request(operator, "GET", "/api/v1/mapping-releases/" + release.manifest.mappingReleaseId, undefined, 403);
        await operator.page.getByRole("button", { name: "比较当前发布与此原件", exact: true }).click();
        await operator.page.getByText("当前身份无权读取或操作此映射", { exact: true }).waitFor();
        check("revoked_manifest_removed", await operator.page.locator(".mapping-hash").count() === 0 && await operator.page.getByText("完整原始映射定义", { exact: true }).count() === 0);
        await operator.page.screenshot({ path: resolve(output, "mapping-source-revoked.png"), fullPage: true });
        const old = state.rounds.rollback;
        const replay = await post(operator, `/api/v1/mapping-proposals/${old.proposal.proposalId}/activate`, old.activationCommand, 200, old.activationEtag);
        check("committed_replay_without_source_select", JSON.stringify(replay) === JSON.stringify(old.receipt));
      } finally { fixture("source-restore"); }
      await operator.page.reload(); await operator.page.getByText("历史发布", { exact: true }).waitFor();
      phase = "fault_fresh_assessment";
      const draft = await get(operator, path);
      const job = await post(operator, path + "/validate", { target: { kind: "PUBLISH", draftRevision: draft.revision }, command: command(draft.revision) }, 202, `"mapping:${draft.revision}"`);
      let assessment;
      for (let attempt = 0; attempt < 40; attempt++) {
        const progress = await get(operator, "/api/v1/mapping-jobs/" + job.jobId);
        if (progress.status === "SUCCEEDED") { assessment = await get(operator, "/api/v1/mapping-assessments/" + progress.assessmentId); break; }
        check("fault_job_pending_" + attempt, ["QUEUED", "RUNNING"].includes(progress.status));
        await new Promise(done => setTimeout(done, 500));
      }
      check("fault_seven_pass", assessment?.status === "READY_FOR_PROPOSAL" && assessment.stages.length === 7 && assessment.stages.every(item => item.status === "PASS"));
      const proposal = await post(operator, path + "/proposals", { kind: "PUBLISH", schemaVersion: "g4.mapping.v1", scope: draft.scope,
        draftId: draft.draftId, draftRevision: draft.revision, binding: assessment.binding, expectedActive: assessment.expectedActive,
        expiresAtUtc: assessment.expiresAtUtc, command: command() }, 201, '"proposal:0"');
      const approved = await post(auditor, `/api/v1/mapping-proposals/${proposal.proposalId}/decisions`, { decision: "APPROVE", bindingHash: proposal.bindingHash,
        command: command(proposal.proposalRevision) }, 200, `"proposal:${proposal.proposalRevision}"`);
      const activation = { bindingHash: approved.bindingHash, expectedActive: approved.expectedActive, command: command(approved.proposalRevision) };
      const etag = `"proposal:${approved.proposalRevision}"`, activationPath = `/api/v1/mapping-proposals/${proposal.proposalId}/activate`;
      state.faultRound = { job, assessment, proposal, approved, activation }; await save(state);
      for (const fault of ["audit", "outbox", "cas"]) {
        phase = "transaction_" + fault;
        const before = fixture("observe");
        try {
          fixture(fault + "-on");
          await post(operator, activationPath, activation, fault === "cas" ? 409 : 503, etag);
        } finally { fixture(fault + "-off"); }
        const after = fixture("observe");
        check(fault + "_atomic_rollback", ["active", "releases", "activations", "outbox", "commands", "audits", "faults"].every(key => JSON.stringify(before[key]) === JSON.stringify(after[key])));
        check(fault + "_check_retained", after.checks === before.checks + 1);
      }
      phase = "transaction_retry_commit";
      const receipt = await post(operator, activationPath, activation, 200, etag);
      check("one_commit_after_three_failures", receipt.activationRevision === assessment.expectedActive.activationRevision + 1);
      state.faultRound.receipt = receipt; await save(state);
      const replay = await post(operator, activationPath, activation, 200, etag);
      check("fault_retry_original_receipt", JSON.stringify(replay) === JSON.stringify(receipt));
      check("all_faults_removed", fixture("observe").faults === 0);
      report.status = "PASS"; report.scope = "REAL_SOURCE_REVOKE_CLEAR_RECOVER_AND_AUDIT_OUTBOX_CAS_ROLLBACK";
    } else if (mode === "recovery") {
      phase = "candidate_create";
      const create = structuredClone(state.createCommand); create.command = command(); create.mapping.properties = [];
      const created = await post(operator, "/api/v1/mappings", create, 201);
      state.recoveryMapping = created; await save(state);
      const path = "/api/v1/mappings/" + created.mappingId;
      await operator.page.goto(origin + "/data/mappings/" + created.mappingId);
      await operator.page.getByRole("textbox", { name: /^完整映射定义/ }).waitFor();
      const pending = operator.page.waitForResponse(response => response.url() === origin + path + "/suggestions" && response.request().method() === "POST");
      await operator.page.getByRole("button", { name: "读取规则候选", exact: true }).click();
      const response = await pending; check("candidate_actual_endpoint", response.status() === 200);
      const suggestions = await response.json();
      check("candidate_metadata_only", suggestions.revision === created.revision && suggestions.candidates.length === 1 && suggestions.candidates[0].evidence === "METADATA" && suggestions.candidates[0].status === "CANDIDATE_ONLY");
      const section = operator.page.locator("section").filter({ has: operator.page.getByRole("heading", { name: "确定性规则候选 · AI OFF", exact: true }) });
      await section.getByRole("checkbox").check();
      await section.getByRole("button", { name: "将勾选低风险候选写入待保存定义", exact: true }).click();
      check("candidate_adoption_not_persisted", (await get(operator, path)).revision === created.revision);
      await operator.page.getByLabel("修改理由", { exact: true }).fill("人工采纳固定目录同名直接字符串候选");
      const waitingSave = operator.page.waitForResponse(response => response.url() === origin + path && response.request().method() === "PATCH");
      await operator.page.getByRole("button", { name: "保存新修订", exact: true }).click();
      const savedResponse = await waitingSave; check("candidate_explicit_patch", savedResponse.status() === 200);
      const saved = await savedResponse.json();
      check("candidate_not_approval", saved.revision === 2 && saved.status === "DRAFT" && saved.mapping.properties.length === 1);
      await post(operator, path + "/suggestions", { mode: "ON", command: command(saved.revision) }, 422, '"mapping:2"');
      phase = "unsaved_conflict";
      const local = structuredClone(saved.mapping); local.identitySpecs[0].sourceNamespace = "local-unsaved";
      const localText = JSON.stringify(local, null, 2);
      await operator.page.getByRole("textbox", { name: /^完整映射定义/ }).fill(localText);
      const remote = structuredClone(saved.mapping); remote.identitySpecs[0].sourceNamespace = "remote-saved";
      await request(operator, "PATCH", path, { mapping: remote, command: command(2) }, 200, '"mapping:2"');
      const conflict = operator.page.waitForResponse(response => response.url() === origin + path && response.request().method() === "PATCH");
      await operator.page.getByRole("button", { name: "保存新修订", exact: true }).click();
      check("ui_conflict_409", (await conflict).status() === 409);
      check("unsaved_text_retained", await operator.page.getByRole("textbox", { name: /^完整映射定义/ }).inputValue() === localText);
      await operator.page.getByRole("button", { name: "读取当前版本供比较", exact: true }).click();
      await operator.page.getByRole("heading", { name: "服务器当前修订 3", exact: true }).waitFor();
      check("compare_does_not_overwrite", await operator.page.getByRole("textbox", { name: /^完整映射定义/ }).inputValue() === localText);
      await operator.page.getByRole("button", { name: "以此修订重新保存本页内容", exact: true }).click();
      const rebased = operator.page.waitForResponse(response => response.url() === origin + path && response.request().method() === "PATCH");
      await operator.page.getByRole("button", { name: "保存新修订", exact: true }).click();
      check("explicit_rebase_saved", (await rebased).status() === 200);
      const current = await get(operator, path);
      check("local_intent_revision4", current.revision === 4 && current.mapping.identitySpecs[0].sourceNamespace === "local-unsaved");
      await operator.page.reload(); await operator.page.getByRole("textbox", { name: /^完整映射定义/ }).waitFor();
      check("saved_reload_restored", JSON.parse(await operator.page.getByRole("textbox", { name: /^完整映射定义/ }).inputValue()).identitySpecs[0].sourceNamespace === "local-unsaved");
      await operator.page.screenshot({ path: resolve(output, "mapping-candidate-conflict-recovered.png"), fullPage: true });
      report.status = "PASS"; report.scope = "REAL_RULE_CANDIDATE_EXPLICIT_ADOPTION_AND_CONFLICT_RECOVERY";
    } else if (mode === "worker") {
      const { execFile } = await import("node:child_process");
      const { promisify } = await import("node:util");
      const invoke = promisify(execFile);
      async function fixture(operation) {
        const raw = await invoke("python3", ["-B", "experiments/g4-m3-mapping-001/grant-fixture.py", "--task", task, "--run-id", runId, "--operation", operation], { cwd: root, timeout: 60000, encoding: "utf8" });
        const value = JSON.parse(raw.stdout); report.workerOperations ??= []; report.workerOperations.push(value);
        check("worker_fixture_" + operation, value.status === "PASS"); return value.observation;
      }
      const mappingId = state.mappingDraft.mappingId;
      const draft = await get(operator, "/api/v1/mappings/" + mappingId);
      await operator.page.goto("about:blank"); await auditor.page.goto("about:blank");
      phase = "worker_actual_source_wait";
      const held = fixture("source-hold");
      try {
        const job = await post(operator, `/api/v1/mappings/${mappingId}/validate`, { target: { kind: "PUBLISH", draftRevision: draft.revision }, command: command(draft.revision) }, 202, `"mapping:${draft.revision}"`);
        state.workerJob = job; await save(state);
        let waiting = false, running;
        for (let attempt = 0; attempt < 20; attempt++) {
          running = await fixture("job-observe");
          if (running.status === "RUNNING" && Number(await fixture("source-waiting")) > 0) { waiting = true; break; }
          await new Promise(done => setTimeout(done, 150));
        }
        check("actual_pg_source_lock_wait_observed", waiting);
        check("worker_claimed_real_job", running.status === "RUNNING" && running.fence > 0);
        phase = "worker_cancel_during_source_wait";
        const cancelled = await post(operator, `/api/v1/mapping-jobs/${job.jobId}/cancel`, { command: command(running.revision) }, 200, `"job:${running.revision}"`);
        check("cancel_committed_terminal", cancelled.status === "CANCELLED" && cancelled.assessmentId === null);
        await held;
        const after = await get(operator, "/api/v1/mapping-jobs/" + job.jobId);
        check("late_worker_cannot_overwrite_cancel", after.status === "CANCELLED" && after.assessmentId === null);
        const persisted = await fixture("job-observe");
        check("cancel_fence_increased", persisted.fence > running.fence && persisted.resultId === null);
        await operator.page.goto(origin + `/data/mappings/${mappingId}?job=${job.jobId}`);
        await operator.page.getByText(/^已取消 · job-/).waitFor();
        await operator.page.reload(); await operator.page.getByText(/^已取消 · job-/).waitFor();
        check("cancel_reload_same_job", new URL(operator.page.url()).searchParams.get("job") === job.jobId);
      } finally { await held; }
      await operator.page.goto("about:blank");
      phase = "worker_process_takeover";
      const takeoverHold = fixture("source-hold");
      let takeoverAttempted = false;
      try {
        const job = await post(operator, `/api/v1/mappings/${mappingId}/validate`, { target: { kind: "PUBLISH", draftRevision: draft.revision }, command: command(draft.revision) }, 202, `"mapping:${draft.revision}"`);
        state.workerJob = job; await save(state);
        let running;
        for (let attempt = 0; attempt < 20; attempt++) {
          running = await fixture("job-observe");
          if (running.status === "RUNNING" && Number(await fixture("source-waiting")) > 0) break;
          await new Promise(done => setTimeout(done, 100));
        }
        check("takeover_real_running_lease", running.status === "RUNNING" && running.fence > 0);
        takeoverAttempted = true;
        await fixture("takeover-start");
        await takeoverHold;
        let persisted;
        for (let attempt = 0; attempt < 80; attempt++) {
          persisted = await fixture("job-observe");
          if (persisted.status === "SUCCEEDED") break;
          check("takeover_lease_still_pending_" + attempt, ["QUEUED", "RUNNING"].includes(persisted.status));
          await new Promise(done => setTimeout(done, 1000));
        }
        check("takeover_new_fence_same_job_completed", persisted.status === "SUCCEEDED" && persisted.fence > running.fence && Boolean(persisted.resultId));
        await fixture("takeover-finish"); takeoverAttempted = false;
        let ready = false;
        for (let attempt = 0; attempt < 40; attempt++) {
          try { const response = await operator.context.request.get(origin + "/api/v1/platform/me", { timeout: 1000 }); if (response.status() === 200) { ready = true; break; } } catch {}
          await new Promise(done => setTimeout(done, 250));
        }
        check("primary_restarted_after_secondary_completed", ready);
        const after = await get(operator, "/api/v1/mapping-jobs/" + job.jobId);
        check("takeover_original_session_and_job_survive", after.jobId === job.jobId && after.assessmentId === persisted.resultId);
        const assessment = await get(operator, "/api/v1/mapping-assessments/" + after.assessmentId);
        check("takeover_seven_stages_pass", assessment.status === "READY_FOR_PROPOSAL" && assessment.stages.length === 7 && assessment.stages.every(item => item.status === "PASS"));
      } finally {
        await takeoverHold;
        if (takeoverAttempted) await fixture("takeover-finish");
      }
      report.status = "PASS"; report.scope = "REAL_SOURCE_LOCK_WAIT_CANCEL_FENCE_RELOAD_AND_PROCESS_TAKEOVER";
    } else if (mode === "semantics") {
      phase = "semantic_formal_release";
      state.semantic ??= {}; const semanticState = state.semantic;
      if (!semanticState.release) {
        const sources = {};
        for (const name of ["ontology", "shapes", "vocabulary", "data"]) sources[name + "Turtle"] = await readFile(resolve(root, "samples/g2", name + ".ttl"), "utf8");
        sources.vocabularyTurtle += "\n" + await readFile(resolve(root, "samples/g3-m3/units.ttl"), "utf8");
        sources.ontologyTurtle += `
@prefix m: <urn:synthetic:mapping:> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
m:Asset a owl:Class . m:Reading a owl:Class .
m:label a owl:DatatypeProperty; rdfs:domain m:Asset; rdfs:range xsd:string .
m:quality a owl:DatatypeProperty; rdfs:domain m:Reading; rdfs:range xsd:string .
<urn:synthetic:m3:reading> rdfs:domain m:Reading; rdfs:range xsd:decimal .
m:hasReading a owl:ObjectProperty; rdfs:domain m:Asset; rdfs:range m:Reading .
m:wrongEndpoint a owl:ObjectProperty; rdfs:domain m:Reading; rdfs:range m:Asset .
`;
        const draft = await post(operator, "/api/v1/ontology-drafts", { name: "M3 two-table exact semantics", scope: state.scope, sources, baseReleaseId: null, command: command() });
        const assessment = await post(operator, `/api/v1/ontology-drafts/${draft.draftId}/assessments`, { revision: draft.revision, hashes: draft.hashes, command: command(draft.revision) });
        check("semantic_g3_publish_eligible", assessment.publishEligible);
        const target = { kind: "DRAFT", id: draft.draftId, revision: draft.revision };
        const impact = await post(operator, "/api/v1/impact-reports", { from: target, to: target, baselineKind: "INITIAL", assessmentId: assessment.assessmentId, command: command(draft.revision) });
        const proposal = await post(operator, "/api/v1/release-proposals", { kind: "PUBLISH", draftId: draft.draftId, draftRevision: draft.revision, hashes: draft.hashes,
          validationReportId: assessment.validationReportId, targetReleaseId: null, targetManifestHash: null, impactReportId: impact.reportId, impactHash: impact.canonicalHash, command: command(draft.revision) });
        const approved = await post(auditor, `/api/v1/approvals/${proposal.proposalId}/decisions`, { decision: "approve", command: command(proposal.revision) });
        const receipt = await post(operator, "/api/v1/release-activations", { proposalId: proposal.proposalId, expectedActivationRevision: 0, expectedActiveReleaseId: null, command: command(approved.revision) });
        semanticState.release = await get(operator, "/api/v1/releases/" + receipt.releaseId); await save(state);
      }
      const ref = (table, name) => ({ datasetRef: { snapshotId: state.catalog.snapshotId, schema: "production", name: table, kind: "TABLE" },
        name, ordinal: state.catalog.objects.find(item => item.name === table).fields.find(field => field.name === name).ordinal });
      const definition = structuredClone(state.createCommand.mapping);
      definition.entities.push({ id: "reading", entityClassIri: "urn:synthetic:mapping:Reading", datasetRef: ref("readings", "reading_id").datasetRef,
        identitySpecId: "reading-identity", temporalSpecId: "reading-time", scopeFields: { organization: ref("readings", "organization_id"), site: ref("readings", "site_id") } });
      definition.identitySpecs.push({ id: "reading-identity", organizationFieldRef: ref("readings", "organization_id"), siteFieldRef: ref("readings", "site_id"), sourceNamespace: "readings",
        externalIdFieldRefs: [ref("readings", "reading_id")], validFromFieldRef: ref("readings", "valid_from"), validToFieldRef: ref("readings", "valid_to") });
      definition.temporalSpecs.push({ id: "reading-time", eventTimeFieldRef: ref("readings", "valid_from"), observedAtFieldRef: ref("readings", "observed_at"),
        validFromFieldRef: ref("readings", "valid_from"), validToFieldRef: ref("readings", "valid_to"), timezonePolicy: { kind: "UTC", zoneId: null }, precision: "MICROSECOND" });
      definition.properties.push({ id: "temperature", entityBindingId: "reading", propertyIri: "urn:synthetic:m3:reading", fieldRef: ref("readings", "temperature"), conversionId: "kelvin", unitSpecId: "temperature-unit", nullPolicy: "REJECT_NULL" },
        { id: "quality", entityBindingId: "reading", propertyIri: "urn:synthetic:mapping:quality", fieldRef: ref("readings", "attributes"), conversionId: "quality-json", unitSpecId: null, nullPolicy: "REJECT_NULL" });
      definition.unitSpecs = [{ id: "temperature-unit", sourceUnitIri: "urn:synthetic:m3:C-v1", targetUnitIri: "urn:synthetic:m3:K-v1", sourceUnitFieldRef: ref("readings", "unit_code"), sourceUnitCode: "Cel", unitRegistryVersion: "1", evidenceKind: "SOURCE_FIELD" }];
      definition.conversions = [{ id: "kelvin", registeredId: "celsius-to-kelvin", version: "1", parameters: {} }, { id: "quality-json", registeredId: "json-top-level-scalar", version: "1", parameters: { key: "quality", valueType: "STRING" } }];
      definition.relations = [{ id: "readings", fromBindingId: "asset", toBindingId: "reading", predicateIri: "urn:synthetic:mapping:hasReading", cardinality: "ONE_TO_MANY", temporalJoinPolicy: "HALF_OPEN_OVERLAP", joinFieldPairs: [{ from: ref("assets", "asset_id"), to: ref("readings", "asset_id") }] }];
      const body = { ...state.createCommand, ontologyReleaseId: semanticState.release.manifest.releaseId, ontologyManifestHash: semanticState.release.manifestHash, mapping: definition, command: command() };
      let draft = await post(operator, "/api/v1/mappings", body, 201);
      semanticState.mappingId = draft.mappingId; await save(state);
      async function assess(label, mapping, passed, code) {
        phase = "semantic_" + label;
        draft = (await request(operator, "PATCH", "/api/v1/mappings/" + draft.mappingId, { mapping, command: command(draft.revision) }, 200, `"mapping:${draft.revision}"`)).data;
        const job = await post(operator, `/api/v1/mappings/${draft.mappingId}/validate`, { target: { kind: "PUBLISH", draftRevision: draft.revision }, command: command(draft.revision) }, 202, `"mapping:${draft.revision}"`);
        for (let attempt = 0; attempt < 45; attempt++) {
          const progress = await get(operator, "/api/v1/mapping-jobs/" + job.jobId);
          if (progress.status === "SUCCEEDED") {
            const value = await get(operator, "/api/v1/mapping-assessments/" + progress.assessmentId);
            report.semanticCases ??= []; report.semanticCases.push({ label, jobId: job.jobId, assessment: value });
            check(label + "_seven_stage_result", (value.status === "READY_FOR_PROPOSAL") === passed && value.stages.length === 7);
            if (code) check(label + "_exact_diagnostic", value.issues.some(issue => issue.code === code));
            return value;
          }
          check(label + "_job_pending_" + attempt, ["QUEUED", "RUNNING"].includes(progress.status));
          await new Promise(done => setTimeout(done, 300));
        }
        check(label + "_deadline", false);
      }
      await assess("one_to_many_exact_units_json", definition, true);
      const many = structuredClone(definition); many.relations[0].cardinality = "MANY_TO_MANY";
      await assess("many_to_many", many, true);
      const wrong = structuredClone(definition); wrong.relations[0].predicateIri = "urn:synthetic:mapping:wrongEndpoint";
      await assess("wrong_formal_endpoints", wrong, false, "mapping_relation_domain_unknown");
      const units = structuredClone(definition); units.unitSpecs[0].sourceUnitCode = "K";
      await assess("unknown_actual_unit", units, false, "mapping_unit_evidence_invalid");
      const precision = structuredClone(definition); precision.temporalSpecs[1].precision = "SECOND";
      await assess("precision_loss", precision, false, "mapping_time_precision_loss");
      const missing = structuredClone(definition); missing.conversions[1].parameters.key = "absent";
      await assess("json_missing", missing, false, "mapping_json_key_missing");
      function mutate(operation) {
        const receipt = JSON.parse(execFileSync("python3", ["-B", "experiments/g4-m3-mapping-001/grant-fixture.py", "--task", task, "--run-id", runId, "--operation", operation], { cwd: root, timeout: 30000, encoding: "utf8" }));
        report.sourceMutations ??= []; report.sourceMutations.push(receipt); check(operation, receipt.status === "PASS");
      }
      try {
        mutate("source-json-empty"); await assess("json_empty_preserved", definition, true);
        mutate("source-json-null"); await assess("json_null_rejected", definition, false, "mapping_null_rejected");
        const nullable = structuredClone(definition); nullable.properties.find(item => item.id === "quality").nullPolicy = "KEEP_NULL";
        await assess("json_null_preserved", nullable, true);
        mutate("source-json-zero"); await assess("json_zero_not_string", definition, false, "mapping_json_type_invalid");
        mutate("source-json-missing"); await assess("json_missing_not_null", nullable, false, "mapping_json_key_missing");
      } finally { mutate("source-json-restore"); }
      try {
        mutate("source-fanout-on"); await assess("fanout_no_truncation", definition, false, "mapping_fanout_exceeded");
      } finally { mutate("source-fanout-off"); }
      semanticState.finalAssessment = await assess("restored_valid", definition, true); await save(state);
      report.status = "PASS"; report.scope = "REAL_G3_PG_TWO_TABLE_RELATIONS_UNITS_MICROSECONDS_JSON";
    } else if (mode === "negative") {
      const mappingId = state.mappingDraft.mappingId, path = "/api/v1/mappings/" + mappingId;
      const viewer = await identity("viewer-a");
      await request(viewer, "GET", path, undefined, 403);
      await request(operator, "GET", path + "?limit=invalid", undefined, 400);
      const draft = await get(operator, path);
      const malformed = structuredClone(draft.mapping); malformed.entities[0].identitySpecId = null;
      await request(operator, "PATCH", path, { mapping: malformed, command: command(draft.revision) }, 400, `"mapping:${draft.revision}"`);
      const mismatch = { mapping: draft.mapping, command: command(draft.revision) };
      await request(operator, "PATCH", path, mismatch, 428);
      await request(operator, "PATCH", path, mismatch, 409, 'W/"mapping:2"');
      async function assessed(target = { kind: "PUBLISH", draftRevision: draft.revision }) {
        const job = await post(operator, path + "/validate", { target, command: command(draft.revision) }, 202, `"mapping:${draft.revision}"`);
        for (let attempt = 0; attempt < 40; attempt++) {
          const value = await get(operator, "/api/v1/mapping-jobs/" + job.jobId);
          if (value.status === "SUCCEEDED") return get(operator, "/api/v1/mapping-assessments/" + value.assessmentId);
          check("negative_job_pending_" + report.http.length, ["QUEUED", "RUNNING"].includes(value.status));
          await new Promise(done => setTimeout(done, 300));
        }
        check("negative_job_deadline", false);
      }
      function proposalBody(assessment) {
        return { kind: assessment.target.kind, schemaVersion: "g4.mapping.v1", scope: draft.scope, binding: assessment.binding,
          expectedActive: assessment.expectedActive, expiresAtUtc: assessment.expiresAtUtc, command: command(),
          ...(assessment.target.kind === "PUBLISH" ? { draftId: draft.draftId, draftRevision: draft.revision } : { targetReleaseId: assessment.target.targetReleaseId, manifestHash: assessment.target.manifestHash }) };
      }
      async function approve(body) {
        const proposal = await post(operator, path + "/proposals", body, 201);
        return post(auditor, `/api/v1/mapping-proposals/${proposal.proposalId}/decisions`, { decision: "APPROVE", bindingHash: proposal.bindingHash, command: command(proposal.proposalRevision) }, 200, `"proposal:${proposal.proposalRevision}"`);
      }
      const activate = (proposal, expected = 200) => post(operator, `/api/v1/mapping-proposals/${proposal.proposalId}/activate`,
        { bindingHash: proposal.bindingHash, expectedActive: proposal.expectedActive, command: command(proposal.proposalRevision) }, expected, `"proposal:${proposal.proposalRevision}"`);
      phase = "strict_proposal_and_expiry";
      const assessment = await assessed();
      check("negative_fresh_seven_pass", assessment.status === "READY_FOR_PROPOSAL");
      const body = proposalBody(assessment);
      await post(operator, path + "/proposals", { ...body, targetReleaseId: state.rounds.first.receipt.mappingReleaseId }, 400);
      await post(operator, path + "/proposals", { ...body, expiresAtUtc: "2020-01-01T00:00:00.0000000Z" }, 409);
      const expiring = await post(operator, path + "/proposals", { ...body, command: command(), expiresAtUtc: new Date(Date.now() + 1500).toISOString().replace("Z", "0000Z") }, 201);
      await new Promise(done => setTimeout(done, 1600));
      await post(auditor, `/api/v1/mapping-proposals/${expiring.proposalId}/decisions`, { decision: "APPROVE", bindingHash: expiring.bindingHash, command: command(expiring.proposalRevision) }, 409, `"proposal:${expiring.proposalRevision}"`);
      phase = "aba_stale_approval";
      const first = await approve(proposalBody(assessment));
      const stale = await approve(proposalBody(assessment));
      const baseline = await get(operator, path + "/active");
      const originalRelease = await get(operator, "/api/v1/mapping-releases/" + baseline.mappingReleaseId);
      const published = await activate(first);
      check("aba_forward_revision", published.activationRevision === baseline.activationRevision + 1);
      const rollbackAssessment = await assessed({ kind: "ROLLBACK", targetReleaseId: baseline.mappingReleaseId, manifestHash: originalRelease.manifestHash });
      const rollback = await approve(proposalBody(rollbackAssessment));
      const restored = await activate(rollback);
      check("aba_same_release_new_revision", restored.mappingReleaseId === baseline.mappingReleaseId && restored.activationRevision === baseline.activationRevision + 2);
      await activate(stale, 409);
      check("aba_stale_request_no_switch", (await get(operator, path + "/active")).activationRevision === restored.activationRevision);
      phase = "connection_disable_invalidates_approval";
      const current = await approve(proposalBody(await assessed()));
      const connectionPath = "/api/v1/connections/" + state.connectionId;
      const connection = await request(operator, "GET", connectionPath);
      const observe = () => JSON.parse(execFileSync("python3", ["-B", "experiments/g4-m3-mapping-001/grant-fixture.py", "--task", task, "--run-id", runId, "--operation", "observe"], { cwd: root, timeout: 30000, encoding: "utf8" })).observation;
      const beforeDisable = observe();
      await post(operator, connectionPath + "/disable", { command: command(connection.data.configRevision) }, 200, connection.etag);
      await request(operator, "GET", "/api/v1/mapping-releases/" + baseline.mappingReleaseId, undefined, 403);
      await activate(current, 409);
      const afterDisable = observe();
      check("failed_activation_preserves_pointer", JSON.stringify(afterDisable.active) === JSON.stringify(beforeDisable.active) && afterDisable.activations === beforeDisable.activations && afterDisable.audits === beforeDisable.audits);
      check("disabled_is_terminal", (await get(operator, connectionPath)).state === "DISABLED");
      report.status = "PASS"; report.scope = "REAL_STRICT_PAYLOAD_EXPIRY_ABA_AND_CONNECTION_REVOCATION";
    } else if (mode === "rotation") {
      const path = "/api/v1/mappings/" + state.mappingDraft.mappingId;
      const draft = await get(operator, path);
      const activeBeforeRotation = await get(operator, path + "/active");
      const historicalId = activeBeforeRotation.mappingReleaseId === state.rounds.first.receipt.mappingReleaseId ? state.rounds.second.receipt.mappingReleaseId : state.rounds.first.receipt.mappingReleaseId;
      const oldRelease = await get(operator, "/api/v1/mapping-releases/" + historicalId);
      async function approved(target) {
        const job = await post(operator, path + "/validate", { target, command: command(draft.revision) }, 202, `"mapping:${draft.revision}"`);
        let assessment;
        for (let attempt = 0; attempt < 50; attempt++) {
          const value = await get(operator, "/api/v1/mapping-jobs/" + job.jobId);
          if (value.status === "SUCCEEDED") { assessment = await get(operator, "/api/v1/mapping-assessments/" + value.assessmentId); break; }
          check("rotation_pending_" + report.http.length, ["QUEUED", "RUNNING"].includes(value.status));
          await new Promise(done => setTimeout(done, 250));
        }
        check("rotation_seven_pass_" + target.kind, assessment?.status === "READY_FOR_PROPOSAL");
        const proposal = await post(operator, path + "/proposals", { kind: target.kind, schemaVersion: "g4.mapping.v1", scope: draft.scope,
          binding: assessment.binding, expectedActive: assessment.expectedActive, expiresAtUtc: assessment.expiresAtUtc, command: command(),
          ...(target.kind === "PUBLISH" ? { draftId: draft.draftId, draftRevision: draft.revision } : { targetReleaseId: target.targetReleaseId, manifestHash: target.manifestHash }) }, 201);
        return post(auditor, `/api/v1/mapping-proposals/${proposal.proposalId}/decisions`, { decision: "APPROVE", bindingHash: proposal.bindingHash,
          command: command(proposal.proposalRevision) }, 200, `"proposal:${proposal.proposalRevision}"`);
      }
      const observe = () => JSON.parse(execFileSync("python3", ["-B", "experiments/g4-m3-mapping-001/grant-fixture.py", "--task", task, "--run-id", runId, "--operation", "observe"], { cwd: root, timeout: 30000, encoding: "utf8" })).observation;
      phase = "approved_credential_rotation";
      const stale = await approved({ kind: "PUBLISH", draftRevision: draft.revision });
      const connectionPath = "/api/v1/connections/" + state.connectionId;
      const beforeConnection = await request(operator, "GET", connectionPath);
      const password = await readFile(resolve(privateRoot, "pg-source/reader-password"), "utf8"); secrets.push(password);
      const secret = await post(operator, "/api/v1/connection-secrets", { secretValue: password, scopeSelection: state.scope, purpose: "POSTGRESQL_READONLY", command: command() }, 201);
      secrets.push(secret.secretRef);
      const rotated = await post(operator, connectionPath + "/rotate-secret", { secretRef: secret.secretRef, command: command(beforeConnection.data.configRevision) }, 200, beforeConnection.etag);
      check("actual_new_secret_version", rotated.secretVersion > beforeConnection.data.secretVersion);
      const before = observe();
      await post(operator, `/api/v1/mapping-proposals/${stale.proposalId}/activate`, { bindingHash: stale.bindingHash, expectedActive: stale.expectedActive,
        command: command(stale.proposalRevision) }, [403, 409], `"proposal:${stale.proposalRevision}"`);
      const after = observe();
      check("rotated_approval_no_commit", JSON.stringify(before.active) === JSON.stringify(after.active) && before.activations === after.activations && before.audits === after.audits);
      let current = await request(operator, "GET", connectionPath);
      check("rotated_actual_probe", (await post(operator, connectionPath + "/test", { command: command(current.data.configRevision) }, 200, current.etag)).status === "TEST_OK");
      current = await request(operator, "GET", connectionPath);
      if (current.data.state !== "ACTIVE") {
        await post(operator, connectionPath + "/enable", { command: command(current.data.configRevision) }, 200, current.etag);
        current = await request(operator, "GET", connectionPath);
      }
      const discovery = await post(operator, connectionPath + "/discoveries", { command: command(current.data.configRevision) }, 202, current.etag);
      for (let attempt = 0; attempt < 40; attempt++) {
        const value = await get(operator, connectionPath + "/discoveries/" + discovery.jobId);
        if (value.status === "SUCCEEDED") { state.latestCatalog = await get(operator, "/api/v1/catalogs/" + value.snapshotId); await save(state); break; }
        check("rotated_discovery_pending_" + attempt, ["QUEUED", "RUNNING"].includes(value.status));
        await new Promise(done => setTimeout(done, 250));
      }
      phase = "current_binding_historical_rollback";
      const rollback = await approved({ kind: "ROLLBACK", targetReleaseId: oldRelease.manifest.mappingReleaseId, manifestHash: oldRelease.manifestHash });
      check("rollback_new_secret_binding", rollback.binding.secretVersion === rotated.secretVersion && rollback.binding.secretVersion !== stale.binding.secretVersion);
      const endpoint = `/api/v1/mapping-proposals/${rollback.proposalId}/activate`;
      await operator.page.goto(origin + "/data/mapping-proposals/" + rollback.proposalId);
      await operator.page.getByLabel("决定或操作理由", { exact: true }).fill("新凭据重新实证，回滚固定旧原件");
      let committed, sent, resolveDrop, rejectDrop;
      const dropped = new Promise((resolve, reject) => { resolveDrop = resolve; rejectDrop = reject; });
      const beforeDrop = observe();
      await operator.page.route(origin + endpoint, async route => {
        try {
        sent = { body: route.request().postDataJSON(), etag: route.request().headers()["if-match"] };
        const actual = await route.fetch();
        check("commit_succeeded_before_response_drop", actual.status() === 200);
        phase = "drop_response_parse_committed";
        committed = await actual.json();
        phase = "drop_response_abort";
        await route.abort("failed"); resolveDrop();
        } catch (error) { rejectDrop(error); await route.abort("failed"); }
      });
      await operator.page.getByRole("button", { name: "重新核验并回滚到固定发布", exact: true }).click();
      let dropTimer;
      try { await Promise.race([dropped, new Promise((_, reject) => { dropTimer = setTimeout(() => reject(new Error("response_drop_deadline")), 45000); })]); }
      finally { clearTimeout(dropTimer); }
      phase = "response_dropped_wait_ui_error";
      await operator.page.locator(".mapping-alert").waitFor({ state: "visible" });
      await operator.page.unroute(origin + endpoint);
      check("actual_response_discarded", Boolean(committed && sent));
      const retry = await post(operator, endpoint, sent.body, 200, sent.etag);
      check("lost_response_original_receipt", JSON.stringify(retry) === JSON.stringify(committed));
      await post(operator, endpoint, { ...sent.body, command: { ...sent.body.command, reason: "same key different payload" } }, 409, sent.etag);
      const afterDrop = observe();
      check("lost_response_single_commit_audit", afterDrop.activations === beforeDrop.activations + 1 && afterDrop.outbox === beforeDrop.outbox + 1 && afterDrop.audits === beforeDrop.audits + 1 && afterDrop.releases === beforeDrop.releases);
      await operator.page.reload(); await operator.page.getByText("已原子提交", { exact: true }).waitFor();
      const preserved = await get(operator, "/api/v1/mapping-releases/" + oldRelease.manifest.mappingReleaseId);
      check("rollback_immutable_old_manifest", preserved.manifestHash === oldRelease.manifestHash && JSON.stringify(preserved.manifest) === JSON.stringify(oldRelease.manifest));
      const g3 = await get(operator, "/api/v1/releases/" + state.ontologyRelease.manifest.releaseId);
      check("g3_fixed_original_manifest_preserved", JSON.stringify(g3.manifest) === JSON.stringify(state.ontologyRelease.manifest));
      report.status = "PASS"; report.scope = "REAL_SECRET_ROTATION_CURRENT_BINDING_OLD_RELEASE_AND_COMMIT_RESPONSE_LOSS";
    } else if (mode === "authority") {
      function fixture(operation) {
        const row = JSON.parse(execFileSync("python3", ["-B", "experiments/g4-m3-mapping-001/grant-fixture.py", "--task", task, "--run-id", runId, "--operation", operation], { cwd: root, timeout: 30000, encoding: "utf8" }));
        report.authorityOperations ??= []; report.authorityOperations.push(row); check(operation, row.status === "PASS"); return row.observation;
      }
      const path = "/api/v1/mappings/" + state.mappingDraft.mappingId;
      const draft = await get(operator, path);
      async function approved(submitter = operator, reviewer = auditor, expires) {
        const job = await post(operator, path + "/validate", { target: { kind: "PUBLISH", draftRevision: draft.revision }, command: command(draft.revision) }, 202, `"mapping:${draft.revision}"`);
        let assessment;
        for (let attempt = 0; attempt < 40; attempt++) {
          const progress = await get(operator, "/api/v1/mapping-jobs/" + job.jobId);
          if (progress.status === "SUCCEEDED") { assessment = await get(operator, "/api/v1/mapping-assessments/" + progress.assessmentId); break; }
          check("authority_job_pending_" + report.http.length, ["QUEUED", "RUNNING"].includes(progress.status));
          await new Promise(done => setTimeout(done, 200));
        }
        check("authority_actual_seven_pass_" + report.http.length, assessment?.status === "READY_FOR_PROPOSAL");
        const proposal = await post(submitter, path + "/proposals", { kind: "PUBLISH", schemaVersion: "g4.mapping.v1", scope: draft.scope, binding: assessment.binding,
          expectedActive: assessment.expectedActive, expiresAtUtc: expires ? new Date(Date.now() + 2000).toISOString().replace("Z", "0000Z") : assessment.expiresAtUtc,
          command: command(), draftId: draft.draftId, draftRevision: draft.revision }, 201);
        return post(reviewer, `/api/v1/mapping-proposals/${proposal.proposalId}/decisions`, { decision: "APPROVE", bindingHash: proposal.bindingHash,
          command: command(proposal.proposalRevision) }, 200, `"proposal:${proposal.proposalRevision}"`);
      }
      async function rejected(label, proposal, needsCheck = false) {
        const before = fixture("observe");
        const result = await request(operator, "POST", `/api/v1/mapping-proposals/${proposal.proposalId}/activate`, { bindingHash: proposal.bindingHash,
          expectedActive: proposal.expectedActive, command: command(proposal.proposalRevision) }, [403, 409], `"proposal:${proposal.proposalRevision}"`);
        const after = fixture("observe");
        check(label + "_no_business_commit", JSON.stringify(before.active) === JSON.stringify(after.active) && before.releases === after.releases && before.activations === after.activations && before.outbox === after.outbox && before.audits === after.audits);
        if (needsCheck) check(label + "_failed_check_retained", after.checks === before.checks + 1 && result.data.code === "mapping_activation_check_failed");
      }
      phase = "approved_expired";
      const expired = await approved(operator, auditor, true);
      await new Promise(done => setTimeout(done, 2100));
      await rejected("approved_expired", expired);
      async function filtered(status) {
        const items = []; let cursor;
        for (let page = 0; page < 60; page++) {
          const result = await get(auditor, "/api/v1/mapping-proposals?mappingId=" + draft.mappingId + "&limit=2&status=" + status + (cursor ? "&cursor=" + encodeURIComponent(cursor) : ""));
          check("filtered_" + status + "_only_current_status_" + page, result.items.every(item => item.status === status));
          items.push(...result.items); cursor = result.nextCursor;
          if (!cursor) return items;
        }
        check("filtered_scan_bounded", false);
      }
      check("expired_projection_in_correct_filter", (await filtered("EXPIRED")).some(item => item.proposalId === expired.proposalId));
      check("expired_projection_absent_from_approved", !(await filtered("APPROVED")).some(item => item.proposalId === expired.proposalId));

      await operator.page.goto(origin + "/data/mapping-proposals/" + expired.proposalId);
      await operator.page.getByText("发布 · 已过期", { exact: true }).waitFor();
      check("expired_ui_cannot_activate", await operator.page.getByRole("button", { name: "重新核验并激活发布", exact: true }).count() === 0);
      await operator.page.reload(); await operator.page.getByText("发布 · 已过期", { exact: true }).waitFor();

      for (const party of ["submitter", "reviewer"]) {
        phase = "approved_" + party + "_logout";
        const temporary = await identity(party === "submitter" ? "operator-ab" : "auditor-ab");
        const proposal = await approved(party === "submitter" ? temporary : operator, party === "reviewer" ? temporary : auditor);
        await request(temporary, "POST", "/auth/logout", undefined, 302);
        await rejected("approved_" + party + "_logout", proposal);
      }
      for (const operation of ["reviewer-revoke", "reviewer-expire", "reviewer-scope"]) {
        phase = operation;
        const proposal = await approved();
        try { fixture(operation); await rejected(operation, proposal); }
        finally { fixture("reviewer-restore"); }
        if (operation === "reviewer-revoke") {
          check("stale_projection_in_correct_filter", (await filtered("STALE")).some(item => item.proposalId === proposal.proposalId));
          check("stale_projection_absent_from_approved", !(await filtered("APPROVED")).some(item => item.proposalId === proposal.proposalId));
        }
      }
      phase = "approved_source_schema_drift";
      const drifted = await approved();
      try { fixture("source-schema-on"); await rejected("approved_source_schema_drift", drifted, true); }
      finally { fixture("source-schema-off"); }
      phase = "approved_source_unavailable";
      const disconnected = await approved();
      try { fixture("source-pause"); await rejected("approved_source_unavailable", disconnected, true); }
      finally { fixture("source-resume"); }
      await operator.page.goto(origin + "/data/mapping-proposals/" + disconnected.proposalId);
      await operator.page.getByText(/ · 未通过$/).waitFor();
      check("partial_failed_check_never_shown_as_pass", await operator.page.getByText(/ · 七项通过$/).count() === 0);
      await operator.page.reload(); await operator.page.getByText(/ · 未通过$/).waitFor();
      report.status = "PASS"; report.scope = "REAL_APPROVED_EXPIRY_PARTY_SESSIONS_REVIEWER_GRANTS_SCHEMA_AND_SOURCE_OUTAGE";
    } else if (mode === "permissions") {
      function fixture(operation) {
        const row = JSON.parse(execFileSync("python3", ["-B", "experiments/g4-m3-mapping-001/grant-fixture.py", "--task", task, "--run-id", runId, "--operation", operation], { cwd: root, timeout: 30000, encoding: "utf8" }));
        report.permissionOperations ??= []; report.permissionOperations.push(row); check(operation, row.status === "PASS"); return row.observation;
      }
      async function discover() {
        const path = "/api/v1/connections/" + state.connectionId;
        let connection = await request(operator, "GET", path);
        if (!connection.data.probeFresh) {
          const probe = await post(operator, path + "/test", { command: command(connection.data.configRevision) }, 200, connection.etag);
          check("acl_current_actual_probe", probe.status === "TEST_OK");
          connection = await request(operator, "GET", path);
        }
        const job = await post(operator, path + "/discoveries", { command: command(connection.data.configRevision) }, 202, connection.etag);
        for (let attempt = 0; attempt < 40; attempt++) {
          const progress = await get(operator, path + "/discoveries/" + job.jobId);
          if (progress.status === "SUCCEEDED") return get(operator, "/api/v1/catalogs/" + progress.snapshotId);
          check("acl_discovery_pending_" + attempt, ["QUEUED", "RUNNING"].includes(progress.status));
          await new Promise(done => setTimeout(done, 250));
        }
        check("acl_discovery_deadline", false);
      }
      phase = "unused_old_field_candidate_revocation";
      const body = structuredClone(state.createCommand); body.command = command(); body.mapping.properties = [];
      const draft = await post(operator, "/api/v1/mappings", body, 201);
      const path = "/api/v1/mappings/" + draft.mappingId;
      const suggestionBody = { mode: "OFF", command: command(draft.revision) }, etag = `"mapping:${draft.revision}"`;
      const original = await post(operator, path + "/suggestions", suggestionBody, 200, etag);
      check("old_unused_label_was_candidate", original.candidates.some(item => item.fieldRef.name === "label"));
      const on = await post(operator, path + "/suggestions", { mode: "ON", command: command(draft.revision) }, 422, etag);
      check("ai_on_explicitly_disabled", on.code === "mapping_model_not_enabled");
      try {
        fixture("source-comment-on"); await discover();
        const injected = await post(operator, path + "/suggestions", { mode: "OFF", command: command(draft.revision) }, 200, etag);
        check("source_comment_cannot_change_candidates_or_policy", JSON.stringify(injected.candidates) === JSON.stringify(original.candidates) && injected.candidates.every(item => item.status === "CANDIDATE_ONLY"));
      } finally { fixture("source-comment-off"); state.latestCatalog = await discover(); await save(state); }

      try {
        fixture("source-deny");
        const reduced = await discover();
        check("current_catalog_removed_unused_field", !reduced.objects.find(item => item.name === "assets").fields.some(item => item.name === "label"));
        const fresh = await post(operator, path + "/suggestions", { mode: "OFF", command: command(draft.revision) }, 200, etag);
        check("fresh_suggestions_never_expose_revoked_old_field", fresh.candidates.every(item => item.fieldRef.name !== "label"));
        await post(operator, path + "/suggestions", suggestionBody, 403, etag);
      } finally {
        fixture("source-restore");
        state.latestCatalog = await discover(); await save(state);
      }
      const restored = await post(operator, path + "/suggestions", suggestionBody, 200, etag);
      check("original_candidate_replay_after_actual_restoration", JSON.stringify(original) === JSON.stringify(restored));
      phase = "dual_role_self_review_and_concurrent_cas";
      const otherSession = await identity("operator-ab");
      check("dual_roles_real_oidc", [operator, auditor, otherSession].every(actor => actor.me.roles.includes("platform.operator") && actor.me.roles.includes("platform.auditor")));
      const primaryPath = "/api/v1/mappings/" + state.mappingDraft.mappingId;
      const primary = await get(operator, primaryPath);
      const job = await post(operator, primaryPath + "/validate", { target: { kind: "PUBLISH", draftRevision: primary.revision }, command: command(primary.revision) }, 202, `"mapping:${primary.revision}"`);
      let assessment;
      for (let attempt = 0; attempt < 40; attempt++) {
        const progress = await get(operator, "/api/v1/mapping-jobs/" + job.jobId);
        if (progress.status === "SUCCEEDED") { assessment = await get(operator, "/api/v1/mapping-assessments/" + progress.assessmentId); break; }
        check("cas_job_pending_" + attempt, ["QUEUED", "RUNNING"].includes(progress.status));
        await new Promise(done => setTimeout(done, 250));
      }
      check("cas_actual_assessment", assessment?.status === "READY_FOR_PROPOSAL");
      const proposalBody = () => ({ kind: "PUBLISH", schemaVersion: "g4.mapping.v1", scope: primary.scope, binding: assessment.binding,
        expectedActive: assessment.expectedActive, expiresAtUtc: assessment.expiresAtUtc, command: command(), draftId: primary.draftId, draftRevision: primary.revision });
      const left = await post(operator, primaryPath + "/proposals", proposalBody(), 201);
      const self = await post(otherSession, `/api/v1/mapping-proposals/${left.proposalId}/decisions`,
        { decision: "APPROVE", bindingHash: left.bindingHash, command: command(left.proposalRevision) }, 403, `"proposal:${left.proposalRevision}"`);
      check("same_subject_other_session_rejected_explicitly", self.code === "mapping_self_review_forbidden");
      const right = await post(auditor, primaryPath + "/proposals", proposalBody(), 201);
      const approve = (actor, proposal) => post(actor, `/api/v1/mapping-proposals/${proposal.proposalId}/decisions`,
        { decision: "APPROVE", bindingHash: proposal.bindingHash, command: command(proposal.proposalRevision) }, 200, `"proposal:${proposal.proposalRevision}"`);
      const approvedLeft = await approve(auditor, left), approvedRight = await approve(operator, right);
      const before = fixture("observe");
      const activate = (actor, proposal) => request(actor, "POST", `/api/v1/mapping-proposals/${proposal.proposalId}/activate`,
        { bindingHash: proposal.bindingHash, expectedActive: proposal.expectedActive, command: command(proposal.proposalRevision) }, [200, 409], `"proposal:${proposal.proposalRevision}"`);
      const competed = await Promise.all([activate(operator, approvedLeft), activate(auditor, approvedRight)]);
      check("concurrent_distinct_subject_one_winner", competed.filter(item => item.status === 200).length === 1 && competed.filter(item => item.status === 409).length === 1);
      const after = fixture("observe");
      check("cas_exactly_one_business_commit", after.active.revision === before.active.revision + 1 && after.activations === before.activations + 1 && after.releases === before.releases + 1 && after.outbox === before.outbox + 1 && after.audits === before.audits + 1);
      phase = "server_ticket_logout";
      const sessionActor = await identity("operator-ab");
      check("same_subject_distinct_session", sessionActor.me.subjectId === operator.me.subjectId);
      await request(sessionActor, "GET", path);
      await sessionActor.page.goto(origin + "/data/mappings/" + draft.mappingId);
      await sessionActor.page.getByRole("textbox", { name: /^完整映射定义/ }).fill("UNSAVED_PREVIOUS_SUBJECT_M3");
      await request(sessionActor, "POST", "/auth/logout", undefined, 302);
      await request(sessionActor, "GET", path, undefined, 401);
      check("other_session_still_reads", (await get(operator, path)).mappingId === draft.mappingId);
      await sessionActor.context.clearCookies();
      await sessionActor.page.goto(origin + "/auth/login?returnUrl=%2Fdata%2Fmappings");
      const viewer = realm.identities["g2-viewer-ab"];
      await sessionActor.page.locator("#username").fill(viewer.username); await sessionActor.page.locator("#password").fill(viewer.password);
      await sessionActor.page.locator("#kc-login").click(); await sessionActor.page.waitForURL(origin + "/data/mappings");
      await sessionActor.page.goto(origin + "/data/mappings/" + draft.mappingId);
      await sessionActor.page.getByRole("alert").filter({ hasText: "无权" }).waitFor();
      check("changed_subject_no_previous_definition", await sessionActor.page.getByRole("textbox", { name: /^完整映射定义/ }).count() === 0 && !(await sessionActor.page.locator("main").innerText()).includes("urn:synthetic:mapping:Asset") && !(await sessionActor.page.locator("main").innerText()).includes("UNSAVED_PREVIOUS_SUBJECT_M3"));

      report.status = "PASS"; report.scope = "REAL_FIELD_REVOCATION_DUAL_ROLE_SELF_REVIEW_CONCURRENT_CAS_AND_LOGOUT";
    } else if (mode === "visual") {
      phase = "visual_release";
      const releaseId = state.rounds.first.release.manifest.mappingReleaseId;
      await operator.page.goto(origin + "/data/mapping-releases/" + releaseId);
      await operator.page.getByText("当前发布", { exact: true }).waitFor();
      await operator.page.screenshot({ path: resolve(output, "mapping-release-desktop-current.png"), fullPage: true, animations: "disabled" });
      const themeBefore = await operator.page.locator("html").getAttribute("data-theme");
      await operator.page.getByRole("button", { name: "切换深浅主题", exact: true }).click();
      check("actual_theme_switch", await operator.page.locator("html").getAttribute("data-theme") !== themeBefore);
      await operator.page.screenshot({ path: resolve(output, "mapping-release-desktop-alternate-theme.png"), fullPage: true, animations: "disabled" });
      await operator.page.reload(); await operator.page.getByText("当前发布", { exact: true }).waitFor();
      check("theme_survives_reload", await operator.page.locator("html").getAttribute("data-theme") !== themeBefore);
      const keyboardLink = operator.page.getByRole("navigation", { name: "映射工作区" }).getByRole("link", { name: "映射列表", exact: true });
      await keyboardLink.focus();
      check("keyboard_focus_visible", await keyboardLink.evaluate(element => element === document.activeElement && getComputedStyle(element).outlineStyle !== "none"));
      await operator.page.keyboard.press("Enter"); await operator.page.waitForURL(origin + "/data/mappings");
      await operator.page.goto(origin + "/data/mapping-releases/" + releaseId); await operator.page.getByText("当前发布", { exact: true }).waitFor();

      await operator.page.setViewportSize({ width: 390, height: 844 });
      await operator.page.waitForFunction(() => document.querySelector(".sidebar")?.getBoundingClientRect().right <= 0);
      check("mobile_sidebar_closed", await operator.page.locator(".sidebar").evaluate(element => element.inert && element.getBoundingClientRect().right <= 0));
      check("mobile_main_visible", await operator.page.locator(".mapping-workspace").evaluate(element => element.getBoundingClientRect().left >= 0 && element.getBoundingClientRect().right <= window.innerWidth));
      await operator.page.screenshot({ path: resolve(output, "mapping-release-mobile-current.png"), fullPage: true, animations: "disabled" });
      report.status = "PASS"; report.scope = "ACTUAL_RESPONSIVE_RELEASE_VISUAL";
    } else if (mode === "lifecycle") {
      if (state.rounds?.rollback?.receipt) {
        state.completedLifecycles ??= []; state.completedLifecycles.push({ mappingId: state.mappingDraft.mappingId, rounds: state.rounds });
        delete state.mappingDraft; delete state.createCommand; delete state.rounds; delete state.secondDraft; await save(state);
      }
      check("runtime_prerequisites", Boolean(state.catalog && state.ontologyRelease));
      const dataset = { snapshotId: state.catalog.snapshotId, schema: "production", name: "assets", kind: "TABLE" };
      const table = state.catalog.objects.find(value => value.schema === "production" && value.name === "assets");
      const field = name => ({ datasetRef: dataset, name, ordinal: table.fields.find(value => value.name === name).ordinal });
      const definition = { entities: [{ id: "asset", entityClassIri: "urn:synthetic:mapping:Asset", datasetRef: dataset,
        identitySpecId: "asset-identity", temporalSpecId: "asset-time", scopeFields: { organization: field("organization_id"), site: field("site_id") } }],
        identitySpecs: [{ id: "asset-identity", organizationFieldRef: field("organization_id"), siteFieldRef: field("site_id"), sourceNamespace: "mapping-fixture-v1",
          externalIdFieldRefs: [field("asset_id")], validFromFieldRef: field("valid_from"), validToFieldRef: field("valid_to") }],
        temporalSpecs: [{ id: "asset-time", eventTimeFieldRef: field("valid_from"), observedAtFieldRef: field("valid_from"),
          validFromFieldRef: field("valid_from"), validToFieldRef: field("valid_to"), timezonePolicy: { kind: "UTC", zoneId: null }, precision: "MICROSECOND" }],
        properties: [{ id: "label", entityBindingId: "asset", propertyIri: "urn:synthetic:mapping:label", fieldRef: field("label"), conversionId: null, unitSpecId: null, nullPolicy: "REJECT_NULL" }],
        relations: [], conversions: [], unitSpecs: [] };
      async function click(actor, button, path, expected = 200) {
        const waiting = actor.page.waitForResponse(response => response.url() === origin + path && response.request().method() === "POST", { timeout: 45000 });
        await actor.page.getByRole("button", { name: button, exact: true }).click();
        const response = await waiting;
        const data = await response.json();
        report.http.push({ method: "POST", path, transport: "BROWSER_UI", status: response.status(), ...(data?.code ? { code: data.code } : {}) });
        check("ui_http_" + report.http.length, (Array.isArray(expected) ? expected.includes(response.status()) : response.status() === expected));
        return { data, request: response.request().postDataJSON(), etag: response.request().headers()["if-match"] };
      }
      async function waitJob(jobId) {
        for (let attempt = 0; attempt < 35; attempt++) {
          const job = await get(operator, "/api/v1/mapping-jobs/" + jobId);
          if (job.status === "SUCCEEDED") return get(operator, "/api/v1/mapping-assessments/" + job.assessmentId);
          if (!["QUEUED", "RUNNING"].includes(job.status)) report.failedJob = { status: job.status, issueCodes: job.issueCodes };
          check("mapping_job_nonfailure_" + attempt, ["QUEUED", "RUNNING"].includes(job.status));
          await new Promise(done => setTimeout(done, 500));
        }
        check("mapping_job_deadline", false);
      }
      if (!state.mappingDraft) {
        phase = "mapping_ui_create";
        await operator.page.goto(origin + "/data/mappings/new?snapshotId=" + state.catalog.snapshotId);
        phase = "mapping_ui_select_release";
        await operator.page.getByRole("combobox", { name: /^G3 正式发布/ }).selectOption(state.ontologyRelease.manifest.releaseId);
        phase = "mapping_ui_fill_definition";
        await operator.page.getByRole("textbox", { name: /^完整映射定义/ }).fill(JSON.stringify(definition, null, 2));
        await operator.page.getByLabel("创建理由", { exact: true }).fill("人工确认固定资产字段、身份和时间");
        phase = "mapping_ui_save_first";
        const created = await click(operator, "保存第一修订", "/api/v1/mappings", 201);
        state.mappingDraft = created.data; state.createCommand = created.request; await save(state);
        const replay = await post(operator, "/api/v1/mappings", created.request, 201);
        check("create_original_receipt_replay", JSON.stringify(replay) === JSON.stringify(created.data));
      }
      const mappingId = state.mappingDraft.mappingId;
      async function publishRound(label, kind, targetRelease) {
        state.rounds ??= {};
        const round = state.rounds[label] ??= {};
        if (!round.assessment) {
          phase = label + "_ui_validate";
          if (kind === "PUBLISH") {
            await operator.page.goto(origin + "/data/mappings/" + mappingId);
            await operator.page.getByRole("textbox", { name: /^完整映射定义/ }).waitFor();
            round.job = (await click(operator, "验证已保存修订", "/api/v1/mappings/" + mappingId + "/validate", 202)).data;
          } else {
            await operator.page.goto(origin + "/data/mapping-releases/" + targetRelease.manifest.mappingReleaseId);
            round.job = (await click(operator, "开始固定目标的回滚验证", "/api/v1/mappings/" + mappingId + "/validate", 202)).data;
          }
          await save(state);
          round.assessment = await waitJob(round.job.jobId); await save(state);
          report.lastAssessment = { status: round.assessment.status, stages: round.assessment.stages, issues: round.assessment.issues };
          check(label + "_seven_actual_pass", round.assessment.status === "READY_FOR_PROPOSAL" && round.assessment.stages.length === 7 && round.assessment.stages.every(value => value.status === "PASS"));
        }
        if (!round.proposal) {
          phase = label + "_ui_propose";
          await operator.page.goto(origin + `/data/mappings/${mappingId}/assessments/${round.assessment.assessmentId}`);
          await operator.page.getByLabel("提交理由", { exact: true }).fill("本次固定七项实证已人工复核");
          const proposed = await click(operator, "提交固定提案", "/api/v1/mappings/" + mappingId + "/proposals", 201);
          round.proposal = proposed.data; await save(state);
          check(label + "_discriminator", proposed.request.kind === kind && (kind !== "ROLLBACK" || !Object.hasOwn(proposed.request, "draftRevision") && !Object.hasOwn(proposed.request, "draftId")));
          await post(operator, `/api/v1/mapping-proposals/${round.proposal.proposalId}/decisions`, { decision: "APPROVE", bindingHash: round.proposal.bindingHash,
            command: command(round.proposal.proposalRevision) }, 403, `"proposal:${round.proposal.proposalRevision}"`);
        }
        if (!round.approved) {
          phase = label + "_ui_independent_review";
          report.proposalProjection = await get(auditor, "/api/v1/mapping-proposals/" + round.proposal.proposalId);
          await auditor.page.goto(origin + "/data/mapping-proposals/" + round.proposal.proposalId);
          await auditor.page.getByLabel("决定或操作理由", { exact: true }).fill("独立主体逐项审核固定目标与版本绑定");
          round.approved = (await click(auditor, "批准固定提案", `/api/v1/mapping-proposals/${round.proposal.proposalId}/decisions`)).data; await save(state);
          check(label + "_different_subject", round.approved.submittedBy !== round.approved.decision.decidedBy);
        }
        if (!round.receipt) {
          phase = label + "_ui_activate";
          await operator.page.goto(origin + "/data/mapping-proposals/" + round.proposal.proposalId);
          await operator.page.getByLabel("决定或操作理由", { exact: true }).fill("复核当前前提并原子切换已批准指针");
          const activated = await click(operator, kind === "PUBLISH" ? "重新核验并激活发布" : "重新核验并回滚到固定发布", `/api/v1/mapping-proposals/${round.proposal.proposalId}/activate`);
          round.receipt = activated.data; round.activationCommand = activated.request; round.activationEtag = activated.etag; await save(state);
          const replay = await post(operator, `/api/v1/mapping-proposals/${round.proposal.proposalId}/activate`, activated.request, 200, activated.etag);
          check(label + "_activation_replay_original", JSON.stringify(replay) === JSON.stringify(activated.data));
        }
        phase = label + "_readback";
        round.release = await get(operator, "/api/v1/mapping-releases/" + round.receipt.mappingReleaseId);
        check(label + "_definition_original_catalog_preserved", round.release.manifest.mapping.entities[0].datasetRef.snapshotId === state.catalog.snapshotId);
        if (label === "first") check("published_readback_original_catalog_differs_from_binding", round.release.manifest.mapping.entities[0].datasetRef.snapshotId !== round.release.manifest.binding.sourceCatalogSnapshotId);
 await save(state);
        const active = await get(operator, "/api/v1/mappings/" + mappingId + "/active");
        check(label + "_active_binding", active.mappingReleaseId === round.receipt.mappingReleaseId && active.activationRevision === round.receipt.activationRevision);
        check(label + "_current_usable", active.usable && round.release.projection.usable);
        return round.release;
      }
      const first = await publishRound("first", "PUBLISH");
      if (!state.secondDraft) {
        phase = "mapping_ui_edit";
        await operator.page.goto(origin + "/data/mappings/" + mappingId);
        const changed = structuredClone(definition); changed.identitySpecs[0].sourceNamespace = "mapping-fixture-v2";
        await operator.page.getByRole("textbox", { name: /^完整映射定义/ }).fill(JSON.stringify(changed, null, 2));
        await operator.page.getByLabel("修改理由", { exact: true }).fill("显式编辑第二修订以验证历史回滚");
        const waiting = operator.page.waitForResponse(response => response.url() === origin + "/api/v1/mappings/" + mappingId && response.request().method() === "PATCH");
        await operator.page.getByRole("button", { name: "保存新修订", exact: true }).click();
        const response = await waiting; check("ui_patch_saved", response.status() === 200); state.secondDraft = await response.json(); await save(state);
      }
      const second = await publishRound("second", "PUBLISH");
      check("distinct_releases", first.manifest.mappingReleaseId !== second.manifest.mappingReleaseId);
      const restored = await publishRound("rollback", "ROLLBACK", first);
      check("rollback_original_manifest", JSON.stringify(restored.manifest) === JSON.stringify(first.manifest) && restored.manifestHash === first.manifestHash);
      check("monotonic_aba_revision", ["first", "second", "rollback"].map(key => state.rounds[key].receipt.activationRevision).join(",") === "1,2,3");
      phase = "deep_link_reload";
      let writes = 0;
      operator.page.on("request", request => { if (request.url().startsWith(origin + "/api/v1/") && !["GET", "HEAD"].includes(request.method())) writes++; });
      await operator.page.goto(origin + "/data/mapping-releases/" + first.manifest.mappingReleaseId);
      await operator.page.getByRole("heading", { name: "不可变映射发布", exact: true }).waitFor();
      await operator.page.reload(); await operator.page.getByText("当前发布", { exact: true }).waitFor();
      check("deep_link_refresh_no_write", writes === 0);
      await operator.page.screenshot({ path: resolve(output, "mapping-release-desktop.png"), fullPage: true });
      await operator.page.setViewportSize({ width: 390, height: 844 });
      await operator.page.screenshot({ path: resolve(output, "mapping-release-mobile.png"), fullPage: true });
      check("mobile_no_horizontal_overflow", await operator.page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth));
      report.status = "PASS"; report.scope = "REAL_UI_CREATE_PUBLISH_SECOND_RELEASE_ROLLBACK_REFRESH";
    } else check("supported_mode", false);
  } catch (error) {
    report.failure = { phase, category: error?.name ?? "Error", code: error.safeCode ?? "mapping_browser_runtime_failure" };
    if (!phase.startsWith("oidc_")) {
      const page = contexts[phase.includes("independent_review") ? 1 : 0]?.pages()[0];
      if (page && new URL(page.url()).origin === origin) {
        const text = await page.locator("body").innerText().catch(() => "BODY_UNAVAILABLE");
        report.failure.visibleText = secrets.some(secret => secret && text.includes(secret)) ? "REDACTED" : text.slice(0, 4000);
        await page.screenshot({ path: file.replace(".json", ".png"), fullPage: true }).catch(() => {});
      }
    }
  } finally {
    for (const context of contexts) await context.close().catch(() => {});
    await browser?.close().catch(() => {});
    try { report.inputsUnchanged = JSON.stringify(report.inputBinding) === JSON.stringify(binding()); }
    catch { report.inputsUnchanged = false; }
    if (!report.inputsUnchanged) { report.status = "FAIL"; report.bindingFailure = "MAPPING_BROWSER_INPUT_DRIFT"; }
    if (report.externalRequests?.length) { report.status = "FAIL"; report.networkFailure = "UNEXPECTED_EXTERNAL_REQUEST"; }
    report.finishedAtUtc = new Date().toISOString();
    await mkdir(output, { recursive: true }); await writeFile(file, JSON.stringify(report, null, 2) + "\n", { flag: "wx" });
    console.log(JSON.stringify({ status: report.status, phase, report: file, checks: report.checks.length, failure: report.failure ?? null }));
    process.exitCode = report.status === "PASS" ? 0 : 1;
  }
}
