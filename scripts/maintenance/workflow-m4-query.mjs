/** M4独立任务的真实OIDC与正式查询前提夹具；不调用M3验收入口。 */
import { createRequire } from "node:module";
import { readFile, realpath } from "node:fs/promises";
import { resolve } from "node:path";
const root = resolve(import.meta.dirname, "../..");
const args = process.argv.slice(2), task = "G4-M4-QUERY-001", runId = "query-impl-01";
/** 参数只接受当前已批准任务与阶段，不能通过CLI切换旧任务私有目录。 */
function argument(name) {
  const flag = "--" + name, index = args.indexOf(flag);
  if (index < 0 || args.lastIndexOf(flag) !== index || index + 1 >= args.length) throw new Error("QUERY_ARGUMENT_REQUIRED");
  return args[index + 1];
}
if (argument("task") !== task || argument("run-id") !== runId || await realpath(process.cwd()) !== root) throw new Error("QUERY_CONSUMER_BOUNDARY");
const mode = argument("mode"), require = createRequire(resolve(root, "apps/web/package.json"));
if (mode === "serve") {
  const { execFileSync } = await import("node:child_process");
  const { writeFile } = await import("node:fs/promises");
  const build = JSON.parse(execFileSync("python3", ["-B", "-c", 'import sys,json;sys.path.insert(0,"scripts/maintenance");import workflow_m4_query as q;print(json.dumps(q.web_binding()))'], { cwd: root, timeout: 30000, encoding: "utf8" }));
  process.env.PLATFORM_API_ORIGIN = "http://localhost:15441";
  process.env.NEXT_TELEMETRY_DISABLED = "1"; process.env.NODE_ENV = "production";
  const record = { taskId: task, runId, pid: process.pid, worktree: root, port: 15442, build,
    processStartedAt: execFileSync("ps", ["-p", String(process.pid), "-o", "lstart="], { encoding: "utf8", env: { ...process.env, LC_ALL: "C" } }).trim(),
    startedAtUtc: new Date().toISOString(), decision: "KEEP", release: "M4 review and safe closeout" };
  await writeFile(resolve(root, "artifacts/workflow", task, runId, "web-process-" + process.pid + ".json"), JSON.stringify(record, null, 2) + "\n", { flag: "wx" });
  await require("next/dist/server/lib/start-server").startServer({ dir: resolve(root, "apps/web"), hostname: "127.0.0.1", port: 15442,
    isDev: false, allowRetry: false, keepAliveTimeout: 5000 });
} else if (["provision", "mapping", "s1", "s1-reopen", "ui-s1", "s2-basic", "s2-runtime", "s2-race"].includes(mode)) await browserRun(mode);
else throw new Error("QUERY_MODE_NOT_IMPLEMENTED");

/** 独立浏览器上下文只保留内存会话，不保存Cookie、HAR、trace或storageState。 */
async function browserRun(mode) {
  const { randomUUID, createHash } = await import("node:crypto");
  const { writeFile, mkdir } = await import("node:fs/promises");
  const output = resolve(root, "artifacts/workflow", task, runId);
  const privateRoot = resolve(root, ".tools/security/g4-m4-query-001", runId);
  const realm = JSON.parse(await readFile(resolve(privateRoot, "runtime/realm.json"), "utf8"));
  if (!realm.authority.startsWith("http://localhost:15443/realms/g2-")) throw new Error("QUERY_REALM_BOUNDARY");
  const origin = "http://localhost:15441";
  const file = resolve(output, "browser-" + mode + "-" + Date.now() + ".json");
  const report = { taskId: task, runId, mode, startedAtUtc: new Date().toISOString(), checks: [], http: [], status: "FAIL" };
  const { execFileSync } = await import("node:child_process");
  const binding = () => JSON.parse(execFileSync("python3", ["-B", "-c", 'import sys,json;sys.path.insert(0,"scripts/maintenance");import workflow_m4_query as q;print(json.dumps({"api":q.runtime_binding(),"web":q.web_binding() if "ui-s1" in sys.argv else None}))', mode], { cwd: root, timeout: 30000, encoding: "utf8" }));
  const contexts = [];
  let browser, phase = "launch";
  const command = (expectedRevision = 0) => ({ commandId: randomUUID(), idempotencyKey: randomUUID(), expectedRevision, reason: "M4 isolated query prerequisite" });
  const check = (name, value) => { report.checks.push({ name, status: value ? "PASS" : "FAIL" }); if (!value) { const error = new Error(); error.safeCode = name; throw error; } };
  const secrets = [realm.clientSecret, ...Object.values(realm.identities).map(value => value.password)];
  async function request(actor, method, path, body, expected = 200, etag) {
    const start = performance.now();
    const response = await actor.context.request.fetch((actor.apiOrigin ?? origin) + path, { method, data: body, timeout: 45000, maxRedirects: 0,
      headers: { ...actor.headers, ...(etag ? { "If-Match": etag } : {}), ...(body ? { "Content-Type": "application/json" } : {}) } });
    const raw = await response.text();
    check("no_known_secret_" + report.http.length, !secrets.some(secret => secret && raw.includes(secret)));
    let data; try { data = JSON.parse(raw); } catch { data = null; }
    report.http.push({ method, path, status: response.status(), elapsedMs: performance.now() - start,
      ...(data?.code ? { code: data.code } : {}), sha256: createHash("sha256").update(raw).digest("hex") });
    check("http_" + report.http.length + "_" + expected, (Array.isArray(expected) ? expected.includes(response.status()) : response.status() === expected));
    return { data, raw, status: response.status(), etag: response.headers()["etag"] ?? "", queryId: response.headers()["x-query-id"] ?? "", cacheControl: response.headers()["cache-control"] };
  }
  const get = async (actor, path) => (await request(actor, "GET", path)).data;
  const post = async (actor, path, body, expected = 200, etag) => (await request(actor, "POST", path, body, expected, etag ?? (body.command ? `"${body.command.expectedRevision}"` : undefined))).data;
  async function identity(label) {
    phase = "oidc_" + label;
    const context = await browser.newContext({ serviceWorkers: "block" }); contexts.push(context);
    await context.route("**/*", route => {
      if ([origin, "http://localhost:15443"].includes(new URL(route.request().url()).origin)) return route.continue();
      report.externalRequests ??= []; report.externalRequests.push(new URL(route.request().url()).origin); return route.abort();
    });
    context.setDefaultTimeout(15000);
    const page = await context.newPage();
    const user = realm.identities["g2-" + label]; check("identity_exists_" + label, Boolean(user));
    await page.goto(origin + "/auth/login?returnUrl=%2Fapi%2Fv1%2Fplatform%2Fme");
    await page.locator("#username").fill(user.username); await page.locator("#password").fill(user.password);
    await page.locator("#kc-login").click();
    await page.waitForURL(url => url.origin === origin && url.pathname === "/api/v1/platform/me");
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
    catch { state = { taskId: task, runId, scope: { organizationId: "org-demo", siteIds: ["site-a", "site-b"] } }; }
    check("fixture_identity", state.taskId === task && state.runId === runId);
    state.subjects = { operator: operator.me.subjectId, auditor: auditor.me.subjectId };
    await save(state);
    if (mode === "s1-reopen") {
      phase = "query_after_api_restart";
      const original = state.latestQuery ?? state.firstQuery;
      check("original_query_exists", Boolean(original));
      const restored = await request(operator, "GET", `/api/v1/data/semantic-queries/${original.queryId}/result`);
      check("new_api_process_decrypts_original_result", createHash("sha256").update(restored.raw).digest("hex") === original.resultHash);
      report.status = "PASS"; report.scope = "S1_NEW_API_PROCESS_ORIGINAL_RESULT_HASH";
    } else if (mode === "s2-basic") {
      phase = "query_s2_ambiguity";
      const capability = (await get(operator, "/api/v1/capabilities")).find(item => item.id === "g4_resolve_entity");
      const query = { ...state.latestQuery.query, capabilityVersion: capability.version, filters: { entityExternalId: "asset-1" } };
      const execute = (plan, selection, expected = 200, key = randomUUID()) => request({ ...operator,
        headers: { ...operator.headers, "Idempotency-Key": key, ...(selection ? { "X-Selection-Query-Id": selection } : {}) } },
        "POST", "/api/v1/data/semantic-queries", plan, expected);
      const ambiguous = await execute(query);
      check("same_external_id_two_authorized_candidates", ambiguous.data.status === "AMBIGUOUS" && ambiguous.data.data.length === 0
        && ambiguous.data.candidates.length === 2 && new Set(ambiguous.data.candidates.map(item => item.siteId)).size === 2);
      const candidate = ambiguous.data.candidates.find(item => item.siteId === "site-a");
      const chosen = { ...query, filters: { ...query.filters, siteId: candidate.siteId, entityIri: candidate.entityIri } };
      const selected = await execute(chosen, ambiguous.queryId);
      check("selection_returns_exact_authorized_entity", selected.data.status === "FOUND" && selected.data.data.length === 1 && selected.data.data[0].entityIri === candidate.entityIri);
      await execute(chosen, undefined, 422);
      await execute({ ...chosen, maxRows: 99 }, ambiguous.queryId, 422);
      await execute({ ...chosen, filters: { ...chosen.filters, entityIri: "urn:unpublished:unknown-entity" } }, ambiguous.queryId, 422);
      await execute(chosen, selected.queryId, 422);
      await execute(chosen, "query-00000000000000000000000000000000", 404);
      phase = "query_s2_empty_and_injection";
      const empty = await execute({ ...query, filters: { entityExternalId: "missing-fixture-entity" } });
      check("successful_zero_rows_is_empty", empty.data.status === "EMPTY" && empty.data.data.length === 0 && empty.data.candidates.length === 0
        && empty.data.subSources.every(item => item.status === "EMPTY"));
      const injection = await execute({ ...query, filters: { entityExternalId: "' OR true --" } });
      check("sql_shaped_identifier_is_parameter_not_query", injection.data.status === "EMPTY" && injection.data.data.length === 0);
      await execute({ ...query, filters: { siteId: "site-outside", entityExternalId: "asset-1" } }, undefined, 403);
      await execute({ ...query, filters: { ...query.filters, sql: "SELECT * FROM production.assets" } }, undefined, 400);
      phase = "query_s2_cancel_completed";
      await request(operator, "POST", `/api/v1/data/semantic-queries/${selected.queryId}/cancel`, undefined, 409);
      check("completed_cancel_does_not_destroy_result", (await request(operator, "GET", `/api/v1/data/semantic-queries/${selected.queryId}/result`)).raw === selected.raw);
      state.s2Ambiguous = { queryId: ambiguous.queryId, query, candidates: ambiguous.data.candidates }; await save(state);
      report.status = "PASS"; report.scope = "S2_REAL_PG_AMBIGUITY_SELECTION_EMPTY_INJECTION_COMPLETED_CANCEL";
    } else if (mode === "s2-runtime" || mode === "s2-race") {
      const { execFile, spawn } = await import("node:child_process");
      const control = (action, value = "") => new Promise((resolveControl, rejectControl) => execFile("python3", ["-B", "-c",
        'import sys,json;sys.path.insert(0,"scripts/maintenance");import workflow_m4_query as q;print(json.dumps(q.query_fixture_control(sys.argv[1],sys.argv[2] or None)))', action, value],
        { cwd: root, timeout: 15000, encoding: "utf8" }, (error, stdout) => error ? rejectControl(new Error("query_fixture_control_failed")) : resolveControl(JSON.parse(stdout))));
      const sourceBarrier = async () => {
        const child = spawn("python3", ["-B", "-c", 'import sys;sys.path.insert(0,"scripts/maintenance");import workflow_m4_query as q;q.query_source_barrier()'], { cwd: root, stdio: ["ignore", "pipe", "pipe"] });
        let readyResolve, readyReject, finishResolve, buffer = "", released = false;
        const ready = new Promise((resolveReady, rejectReady) => { readyResolve = resolveReady; readyReject = rejectReady; });
        const finished = new Promise(resolveFinish => { finishResolve = resolveFinish; });
        child.stdout.on("data", chunk => {
          buffer += chunk.toString(); let boundary;
          while ((boundary = buffer.indexOf("\n")) >= 0) {
            const line = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 1);
            try { const event = JSON.parse(line); if (event.status === "READY") readyResolve(); if (event.status === "RELEASED") released = true; }
            catch { readyReject(new Error("query_barrier_protocol_invalid")); }
          }
        });
        child.stderr.resume();
        child.on("error", () => { readyReject(new Error("query_barrier_start_failed")); finishResolve(false); });
        child.on("exit", code => { if (code !== 0) readyReject(new Error("query_barrier_failed")); finishResolve(code === 0 && released); });
        await ready; return { finished };
      };
      const query = state.latestQuery.query, queryId = state.latestQuery.queryId;
      const secondary = { ...operator, apiOrigin: "http://localhost:15448" };
      check("second_api_same_current_identity", (await get(secondary, "/api/v1/platform/me")).subjectId === operator.me.subjectId);
      await get(secondary, "/api/v1/capabilities");
      const execute = (actor = operator, key = randomUUID(), expected = 200) => request({ ...actor, headers: { ...actor.headers, "Idempotency-Key": key } },
        "POST", "/api/v1/data/semantic-queries", query, expected);
      if (mode === "s2-runtime") {
      phase = "query_current_grant_revocation";
      for (const permission of ["result", "evidence", "execute"]) {
        await control("revoke-" + permission);
        try {
          if (permission === "evidence") {
            const result = await get(operator, `/api/v1/data/semantic-queries/${queryId}/result`);
            await request(operator, "GET", "/api/v1/data/source-evidence/" + encodeURIComponent(result.evidence[0].evidenceId), undefined, 403);
          } else await request(operator, "GET", `/api/v1/data/semantic-queries/${queryId}/result`, undefined, 403);
          if (permission === "execute") {
            const denied = await execute();
            check("revoked_execute_is_no_data_unauthorized", denied.data.status === "UNAUTHORIZED" && denied.data.data.length === 0 && denied.data.candidates.length === 0);
          }
        } finally { await control("restore-" + permission); }
      }
      check("current_regrant_recovers_original_bytes", createHash("sha256").update((await request(operator, "GET", `/api/v1/data/semantic-queries/${queryId}/result`)).raw).digest("hex") === state.latestQuery.resultHash);
      phase = "query_current_source_acl";
      await control("source-deny");
      try { await request(operator, "GET", `/api/v1/data/semantic-queries/${queryId}/result`, undefined, [403, 503]); }
      finally { await control("source-allow"); }
      check("source_acl_restore_recovers_same_bytes", createHash("sha256").update((await request(operator, "GET", `/api/v1/data/semantic-queries/${queryId}/result`)).raw).digest("hex") === state.latestQuery.resultHash);
      }
      phase = "query_cross_api_cancel";
      const key = randomUUID();
      const watcher = spawn("python3", ["-B", "-c", 'import sys;sys.path.insert(0,"scripts/maintenance");import workflow_m4_query as q;q.query_admission_watch(sys.argv[1])', key], { cwd: root, stdio: ["ignore", "pipe", "pipe"] });
      let markReady, rejectReady, markFound, rejectFound, buffer = "";
      const ready = new Promise((resolveWatch, rejectWatch) => { markReady = resolveWatch; rejectReady = rejectWatch; });
      const found = new Promise((resolveWatch, rejectWatch) => { markFound = resolveWatch; rejectFound = rejectWatch; }).then(value => ({ value }), error => ({ error }));
      watcher.stdout.on("data", chunk => {
        buffer += chunk.toString();
        let boundary;
        while ((boundary = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, boundary); buffer = buffer.slice(boundary + 1);
          try { const event = JSON.parse(line); if (event.status === "READY") markReady(event); if (event.status === "FOUND") markFound(event); } catch { rejectFound(new Error("query_watch_protocol_invalid")); }
        }
      });
      watcher.stderr.resume();
      watcher.on("error", () => { rejectReady(new Error("query_watch_start_failed")); rejectFound(new Error("query_watch_start_failed")); });
      watcher.on("exit", code => { if (code !== 0) { rejectReady(new Error("query_watch_failed")); rejectFound(new Error("query_watch_failed")); } });
      await ready;
      const { finished: barrier } = await sourceBarrier();
      try {
        // 立即接管异步拒绝，保证任何时序失败仍经过finally保存报告和释放夹具。
        const running = execute(operator, key, [200, 202, 409, 503]).then(value => ({ value }), error => ({ error }));
        const observed = await found;
        if (observed.error) throw observed.error;
        const id = observed.value.queryId;
        check("real_api_execution_admitted_before_cancel", /^query-[0-9a-f]{32}$/.test(id));
        const cancelled = await request(secondary, "POST", `/api/v1/data/semantic-queries/${id}/cancel`);
        check("second_api_commits_cancel", cancelled.data.executionStatus === "CANCELLED");
        const finished = await running;
        if (finished.error) throw finished.error;
        check("first_api_late_response_rejected", [409, 503].includes(finished.value.status));
        const after = JSON.parse((await control("query-probe", key)).output);
        check("late_worker_cannot_commit_completed", after.status === "CANCELLED" && after.cancel === true);
        await request(operator, "GET", `/api/v1/data/semantic-queries/${id}/result`, undefined, 409);
      } finally { check("cancel_source_barrier_released", await barrier); await found; }
      phase = "query_source_timeout";
      const { finished: fault } = await sourceBarrier();
      try {
        const unavailable = await execute();
        check("real_source_lock_timeout_never_empty", unavailable.data.status === "UNAVAILABLE" && unavailable.data.data.length === 0
          && unavailable.data.candidates.length === 0 && unavailable.data.subSources.every(item => item.status !== "EMPTY"));
      } finally { check("timeout_source_barrier_released", await fault); }
      report.status = "PASS"; report.scope = mode === "s2-race" ? "S2_CROSS_API_CANCEL_SOURCE_FAILURE" : "S2_CURRENT_GRANTS_SOURCE_ACL_CROSS_API_CANCEL_SOURCE_FAILURE";
    } else if (mode === "provision") {
      if (!state.ontologyDraft) {
        phase = "g3_create";
        const sources = {};
        for (const name of ["ontology", "shapes", "vocabulary", "data"]) sources[name + "Turtle"] = await readFile(resolve(root, "samples/g2", name + ".ttl"), "utf8");
        sources.ontologyTurtle += '\n<urn:synthetic:mapping:Asset> a <http://www.w3.org/2002/07/owl#Class> .\n'
          + '<urn:synthetic:mapping:label> a <http://www.w3.org/2002/07/owl#DatatypeProperty>; <http://www.w3.org/2000/01/rdf-schema#domain> <urn:synthetic:mapping:Asset>; <http://www.w3.org/2000/01/rdf-schema#range> <http://www.w3.org/2001/XMLSchema#string> .\n';
        state.ontologyDraft = await post(operator, "/api/v1/ontology-drafts", { name: "Synthetic M4 query vocabulary", scope: state.scope, sources, baseReleaseId: null, command: command() }); await save(state);
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
        const existing = (await get(operator, "/api/v1/connections")).items.filter(value => value.displayName === "M4 synthetic PostgreSQL query");
        check("resume_connection_unambiguous", existing.length <= 1);
        if (existing.length === 1) { state.connectionId = existing[0].id; await save(state); }
      }
      if (!state.connectionId) {
        phase = "pg_connection_create";
        const password = await readFile(resolve(privateRoot, "pg-source/reader-password"), "utf8"); secrets.push(password);
        const secret = await post(operator, "/api/v1/connection-secrets", { secretValue: password, scopeSelection: state.scope, purpose: "POSTGRESQL_READONLY", command: command() }, 201);
        secrets.push(secret.secretRef);
        const config = { type: "POSTGRESQL", profile: { host: "pg-source", port: 5432, database: "fixture", username: "fixture_reader", sslMode: "VerifyFull", allowedSchemas: ["production", "public"] } };
        const connection = await post(operator, "/api/v1/connections", { displayName: "M4 synthetic PostgreSQL query", scopeSelection: state.scope, config, secretRef: secret.secretRef, command: command() }, 201);
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

    } else if (mode === "mapping") {
      check("formal_prerequisites", Boolean(state.catalog && state.ontologyRelease));
      const dataset = { snapshotId: state.catalog.snapshotId, schema: "production", name: "assets", kind: "TABLE" };
      const table = state.catalog.objects.find(value => value.schema === "production" && value.name === "assets");
      const field = name => ({ datasetRef: dataset, name, ordinal: table.fields.find(value => value.name === name).ordinal });
      const definition = { entities: [{ id: "asset", entityClassIri: "urn:synthetic:mapping:Asset", datasetRef: dataset,
        identitySpecId: "asset-identity", temporalSpecId: "asset-time", scopeFields: { organization: field("organization_id"), site: field("site_id") } }],
        identitySpecs: [{ id: "asset-identity", organizationFieldRef: field("organization_id"), siteFieldRef: field("site_id"), sourceNamespace: "query-fixture-v1",
          externalIdFieldRefs: [field("asset_id")], validFromFieldRef: field("valid_from"), validToFieldRef: field("valid_to") }],
        temporalSpecs: [{ id: "asset-time", eventTimeFieldRef: field("valid_from"), observedAtFieldRef: field("valid_from"),
          validFromFieldRef: field("valid_from"), validToFieldRef: field("valid_to"), timezonePolicy: { kind: "UTC", zoneId: null }, precision: "MICROSECOND" }],
        properties: [{ id: "label", entityBindingId: "asset", propertyIri: "urn:synthetic:mapping:label", fieldRef: field("label"), conversionId: null, unitSpecId: null, nullPolicy: "REJECT_NULL" }],
        relations: [], conversions: [], unitSpecs: [] };
      if (!state.mappingDraft) {
        phase = "query_mapping_create";
        state.mappingCreate ??= { scope: state.scope, ontologyReleaseId: state.ontologyRelease.manifest.releaseId,
          ontologyManifestHash: state.ontologyRelease.manifestHash, sourceConnectionId: state.connectionId,
          sourceCatalogSnapshotId: state.catalog.snapshotId, mapping: definition, command: command() };
        await save(state);
        state.mappingDraft = await post(operator, "/api/v1/mappings", state.mappingCreate, 201); await save(state);
      }
      const draft = state.mappingDraft, path = "/api/v1/mappings/" + draft.mappingId;
      if (!state.mappingJob) {
        phase = "query_mapping_validate";
        state.mappingValidation ??= { target: { kind: "PUBLISH", draftRevision: draft.revision }, command: command(draft.revision) };
        await save(state);
        state.mappingJob = await post(operator, path + "/validate", state.mappingValidation, 202, `"mapping:${draft.revision}"`); await save(state);
      }
      if (!state.mappingAssessment) {
        phase = "query_mapping_wait";
        for (let attempt = 0; attempt < 60; attempt++) {
          const job = await get(operator, "/api/v1/mapping-jobs/" + state.mappingJob.jobId);
          if (job.status === "SUCCEEDED") { state.mappingAssessment = await get(operator, "/api/v1/mapping-assessments/" + job.assessmentId); break; }
          check("mapping_prerequisite_job_" + attempt, ["QUEUED", "RUNNING"].includes(job.status));
          await new Promise(done => setTimeout(done, 500));
        }
        check("mapping_prerequisite_ready", state.mappingAssessment?.status === "READY_FOR_PROPOSAL"); await save(state);
      }
      const assessment = state.mappingAssessment;
      if (!state.mappingProposal) {
        phase = "query_mapping_propose";
        state.mappingProposalCommand ??= { kind: "PUBLISH", schemaVersion: "g4.mapping.v1", scope: draft.scope,
          binding: assessment.binding, expectedActive: assessment.expectedActive, expiresAtUtc: assessment.expiresAtUtc,
          draftId: draft.draftId, draftRevision: draft.revision, command: command() }; await save(state);
        state.mappingProposal = await post(operator, path + "/proposals", state.mappingProposalCommand, 201); await save(state);
      }
      if (!state.mappingApproved) {
        phase = "query_mapping_independent_review";
        const proposal = state.mappingProposal;
        state.mappingDecision ??= { decision: "APPROVE", bindingHash: proposal.bindingHash, command: command(proposal.proposalRevision) }; await save(state);
        state.mappingApproved = await post(auditor, `/api/v1/mapping-proposals/${proposal.proposalId}/decisions`, state.mappingDecision, 200, `"proposal:${proposal.proposalRevision}"`);
        check("mapping_distinct_review_subject", state.mappingApproved.submittedBy !== state.mappingApproved.decision.decidedBy); await save(state);
      }
      if (!state.mappingReceipt) {
        phase = "query_mapping_activate";
        const proposal = state.mappingApproved;
        state.mappingActivation ??= { bindingHash: proposal.bindingHash, expectedActive: proposal.expectedActive, command: command(proposal.proposalRevision) }; await save(state);
        state.mappingReceipt = await post(operator, `/api/v1/mapping-proposals/${proposal.proposalId}/activate`, state.mappingActivation, 200, `"proposal:${proposal.proposalRevision}"`); await save(state);
      }
      state.mappingRelease = await get(operator, "/api/v1/mapping-releases/" + state.mappingReceipt.mappingReleaseId); await save(state);
      check("query_mapping_original", state.mappingRelease.manifest.mapping.entities.length === 1 && state.mappingRelease.manifest.mapping.entities[0].datasetRef.snapshotId === state.catalog.snapshotId);
      report.status = "PASS"; report.scope = "M4_QUERY_FIXED_MAPPING_PREREQUISITE_ONLY";
    } else if (mode === "s1") {
      phase = "query_capability";
      const capability = (await get(operator, "/api/v1/capabilities")).find(item => item.id === "g4_resolve_entity");
      check("g4_registered_capability", Boolean(capability && state.mappingRelease));
      const query = { assetId: state.ontologyRelease.manifest.assetId, ontologyReleaseId: state.ontologyRelease.manifest.releaseId,
        mappingReleaseIds: [state.mappingReceipt.mappingReleaseId], capabilityId: capability.id, capabilityVersion: capability.version,
        relationshipIris: [], depth: 1, maxRows: 100, timeoutMs: 5000, filters: { siteId: "site-a", entityExternalId: "asset-1" } };
      phase = "query_default_zero_grant";
      const denied = await request({ ...auditor, headers: { ...auditor.headers, "Idempotency-Key": randomUUID() } }, "POST", "/api/v1/data/semantic-queries", query);
      check("default_zero_data_grant", denied.data?.status === "UNAUTHORIZED" && denied.data.data.length === 0 && denied.data.evidence.length === 0);
      check("denied_no_store", denied.cacheControl === "no-store");
      phase = "query_first_real_pg";
      const key = randomUUID(), writer = { ...operator, headers: { ...operator.headers, "Idempotency-Key": key } };
      const first = await request(writer, "POST", "/api/v1/data/semantic-queries", query);
      check("real_pg_found", first.data?.status === "FOUND" && first.data.data.length === 1 && first.data.data[0].kind === "entity");
      check("actual_query_reference", /^query-[0-9a-f]{32}$/.test(first.queryId));
      check("real_source_receipt", first.data.subSources.length === 1 && first.data.subSources[0].status === "SUCCESS" && first.data.subSources[0].sourceReadReceiptId);
      check("precise_identity_evidence", first.data.evidence.length > 0 && first.data.evidence.every(item => item.precision === "ROW_KEY" && item.sourceRecordRef && !Object.hasOwn(item, "graphIri")));
      check("real_scope_projection", first.data.data[0].identity.siteId === "site-a" && first.data.data[0].identity.externalId === "asset-1");
      check("completed_no_store", first.cacheControl === "no-store");
      phase = "query_restore_exact_bytes";
      const restored = await request(operator, "GET", `/api/v1/data/semantic-queries/${first.queryId}/result`);
      check("restore_exact_canonical_bytes", restored.raw === first.raw);
      const replay = await request(writer, "POST", "/api/v1/data/semantic-queries", query);
      check("idempotency_same_reference_and_bytes", replay.queryId === first.queryId && replay.raw === first.raw);
      await request(writer, "POST", "/api/v1/data/semantic-queries", { ...query, maxRows: 99 }, 409);
      await request(auditor, "GET", `/api/v1/data/semantic-queries/${first.queryId}/result`, undefined, 404);
      phase = "query_source_evidence";
      const evidence = await get(operator, "/api/v1/data/source-evidence/" + encodeURIComponent(first.data.evidence[0].evidenceId));
      check("real_evidence_chain", evidence.schemaVersion === "g4.source-evidence.v1" && evidence.receipt.queryId === first.queryId
        && evidence.receipt.mappingReleaseId === state.mappingReceipt.mappingReleaseId && evidence.receipt.activationId === state.mappingReceipt.activationId);
      check("no_internal_binding", !Object.hasOwn(evidence.receipt, "configHash") && !Object.hasOwn(evidence.receipt, "secretVersion") && !Object.hasOwn(evidence.receipt, "binding"));
      await writeFile(file.replace(".json", "-result.json"), first.raw, { flag: "wx" });
      state.latestQuery = { queryId: first.queryId, query, idempotencyKey: key, resultHash: createHash("sha256").update(first.raw).digest("hex") };
      state.firstQuery ??= state.latestQuery; await save(state);
      report.status = "PASS"; report.scope = "S1_REAL_OIDC_FORMAL_MAPPING_PG_QUERY_RESTORE_EVIDENCE_HTTP";
    } else if (mode === "ui-s1") {
      phase = "query_ui_execute";
      await operator.page.goto(origin + "/analysis");
      await operator.page.getByRole("button", { name: "查询业务源", exact: true }).waitFor();
      await operator.page.getByLabel("源查询本体资产", { exact: true }).fill(state.ontologyRelease.manifest.assetId);
      await operator.page.getByLabel("源查询本体发布", { exact: true }).fill(state.ontologyRelease.manifest.releaseId);
      await operator.page.getByLabel("源查询映射发布", { exact: true }).fill(state.mappingReceipt.mappingReleaseId);
      await operator.page.getByLabel("源查询外部号", { exact: true }).fill("asset-1");
      await operator.page.getByLabel("源查询厂区", { exact: true }).selectOption("site-a");
      const queryResponse = operator.page.waitForResponse(response => response.url() === origin + "/api/v1/data/semantic-queries" && response.request().method() === "POST");
      await operator.page.getByRole("button", { name: "查询业务源", exact: true }).click();
      const response = await queryResponse, result = await response.json();
      check("ui_real_query_found", response.status() === 200 && result.status === "FOUND");
      await operator.page.getByRole("region", { name: "业务源查询结果" }).getByRole("heading", { name: "FOUND · 找到可信结果", exact: true }).waitFor();
      const queryId = response.headers()["x-query-id"];
      check("ui_recoverable_url_only_id", new URL(operator.page.url()).searchParams.get("query") === queryId);
      const observed = () => JSON.parse(execFileSync("python3", ["-B", "-c", 'import sys,json;sys.path.insert(0,"scripts/maintenance");import workflow_m4_query as q;print(json.dumps(q.source_scan_snapshot()))'], { cwd: root, timeout: 30000, encoding: "utf8" }));
      const count = row => row.seqScan + row.idxScan;
      await new Promise(done => setTimeout(done, 2100)); const before = observed();
      await new Promise(done => setTimeout(done, 1100)); const settled = observed();
      check("source_statistics_settled", count(before) === count(settled) && count(before) > 0);
      let writes = 0;
      operator.page.on("request", request => { if (request.url().includes("/api/v1/data/semantic-queries") && request.method() !== "GET") writes++; });
      phase = "query_ui_refresh";
      const restoredResponse = operator.page.waitForResponse(response => response.url() === origin + `/api/v1/data/semantic-queries/${queryId}/result`);
      await operator.page.reload();
      const restored = await restoredResponse;
      check("browser_refresh_same_result", restored.status() === 200 && JSON.stringify(await restored.json()) === JSON.stringify(result));
      await operator.page.getByRole("region", { name: "业务源查询结果" }).getByRole("heading", { name: "FOUND · 找到可信结果", exact: true }).waitFor();
      await new Promise(done => setTimeout(done, 2100)); const after = observed();
      await new Promise(done => setTimeout(done, 1100)); const confirmed = observed();
      report.sourceScans = { before, settled, after, confirmed };
      check("browser_refresh_no_business_query", count(before) === count(after) && count(after) === count(confirmed) && writes === 0);
      check("browser_result_not_in_persistent_storage", await operator.page.evaluate(async () => localStorage.length === 0 && sessionStorage.length === 0 && (await indexedDB.databases()).length === 0));
      await operator.page.screenshot({ path: file.replace(".json", "-desktop.png"), fullPage: true });
      await operator.page.setViewportSize({ width: 390, height: 844 });
      await operator.page.waitForFunction(() => document.querySelector("#platform-navigation")?.getBoundingClientRect().right <= 0);
      check("query_mobile_no_horizontal_overflow", await operator.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      const queryRegion = operator.page.getByRole("region", { name: "业务源查询", exact: true });
      await queryRegion.scrollIntoViewIfNeeded();
      check("query_mobile_region_visible", await queryRegion.isVisible() && (await queryRegion.boundingBox()).width <= 390);
      await queryRegion.screenshot({ path: file.replace(".json", "-mobile.png") });
      phase = "query_ui_identity_invalidation";
      let releaseHeld, markCaptured;
      const held = new Promise(done => { releaseHeld = done; }), captured = new Promise(done => { markCaptured = done; });
      const resultUrl = origin + `/api/v1/data/semantic-queries/${queryId}/result`;
      await operator.page.route(resultUrl, async route => {
        const originalResponse = await route.fetch();
        check("late_response_was_real_authorized_result", originalResponse.status() === 200);
        markCaptured(); await held;
        await route.fulfill({ response: originalResponse }).catch(() => {});
      });
      await operator.page.getByRole("button", { name: "恢复查询结果", exact: true }).click();
      await captured;
      const second = await operator.context.newPage();
      await second.goto(origin + "/analysis"); await second.bringToFront();
      await operator.page.waitForFunction(() => !document.querySelector('[aria-label="业务源查询结果"]'));
      check("other_tab_activation_clears_old_query", await operator.page.getByRole("region", { name: "业务源查询结果" }).count() === 0);
      await second.getByRole("button", { name: "安全退出" }).click();
      await second.waitForURL(url => url.origin === origin && url.pathname === "/signed-out");
      const other = realm.identities["g2-auditor-ab"];
      await second.goto(origin + "/auth/login?returnUrl=%2Fapi%2Fv1%2Fplatform%2Fme");
      await second.locator("#username").fill(other.username); await second.locator("#password").fill(other.password);
      await second.locator("#kc-login").click();
      await second.waitForURL(url => url.origin === origin && url.pathname === "/api/v1/platform/me");
      check("same_browser_subject_really_changed", (await get(operator, "/api/v1/platform/me")).subjectId === auditor.me.subjectId);
      releaseHeld(); await operator.page.unroute(resultUrl); await operator.page.bringToFront();
      await operator.page.waitForFunction(() => !document.querySelector('[aria-label="恢复源查询引用"]')?.disabled);
      check("late_old_subject_response_not_rendered", await operator.page.getByRole("region", { name: "业务源查询结果" }).count() === 0);
      const forbiddenRestore = operator.page.waitForResponse(response => response.url() === resultUrl);
      await operator.page.getByRole("button", { name: "恢复查询结果", exact: true }).click();
      check("changed_subject_cannot_restore_previous_query", (await forbiddenRestore).status() === 404);
      check("rejected_restore_keeps_results_cleared", await operator.page.getByRole("region", { name: "业务源查询结果" }).count() === 0);
      await second.close();
      report.status = "PASS"; report.scope = "S1_BROWSER_QUERY_REFRESH_SAME_BYTES_NO_SOURCE_REPLAY";
    } else check("supported_mode", false);
  } catch (error) {
    report.failure = { phase, category: error?.name ?? "Error", code: error.safeCode ?? "query_browser_runtime_failure" };
  } finally {
    for (const context of contexts) await context.close().catch(() => {});
    await browser?.close().catch(() => {});
    try { report.inputsUnchanged = JSON.stringify(report.inputBinding) === JSON.stringify(binding()); }
    catch { report.inputsUnchanged = false; }
    if (!report.inputsUnchanged) { report.status = "FAIL"; report.bindingFailure = "QUERY_BROWSER_INPUT_DRIFT"; }
    if (report.externalRequests?.length) { report.status = "FAIL"; report.networkFailure = "UNEXPECTED_EXTERNAL_REQUEST"; }
    report.finishedAtUtc = new Date().toISOString();
    await mkdir(output, { recursive: true }); await writeFile(file, JSON.stringify(report, null, 2) + "\n", { flag: "wx" });
    console.log(JSON.stringify({ status: report.status, phase, report: file, checks: report.checks.length, failure: report.failure ?? null }));
    process.exitCode = report.status === "PASS" ? 0 : 1;
  }
}
