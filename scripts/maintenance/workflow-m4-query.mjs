/** M4独立任务的真实OIDC与正式查询前提夹具；不调用M3验收入口。 */
import { createRequire } from "node:module";
import { readFile, realpath } from "node:fs/promises";
import { resolve } from "node:path";
const root = resolve(import.meta.dirname, "../..");
const args = process.argv.slice(2);
/** 参数只接受当前已批准任务与阶段，不能通过CLI切换旧任务私有目录。 */
function argument(name) {
  const flag = "--" + name, index = args.indexOf(flag);
  if (index < 0 || args.lastIndexOf(flag) !== index || index + 1 >= args.length) throw new Error("QUERY_ARGUMENT_REQUIRED");
  return args[index + 1];
}
const task = argument("task");
if (!["G4-M4-QUERY-001", "G4-M5-INTEGRATION-001", "G4-DORIS-MAPPING-QUERY-001"].includes(task)) throw new Error("QUERY_TASK_NOT_ADMITTED");
const doris = task === "G4-DORIS-MAPPING-QUERY-001";
const integration = task === "G4-M5-INTEGRATION-001", runId = doris ? "implementation-01" : integration ? "integration-01" : "query-impl-01";
const scenario = integration ? argument("scenario") : null;
if (integration && !["standard", "numeric", "safety", "aba"].includes(scenario)) throw new Error("INTEGRATION_SCENARIO_INVALID");
const moduleName = doris ? "workflow_doris_s1" : integration ? "workflow_m5_integration" : "workflow_m4_query";
const scenarioCode = integration ? `q.scenario("${scenario}");` : "";
const privateName = doris ? ".tools/security/g4-doris-mapping-query-001" : integration ? ".tools/security/g4-m5-integration-001" : ".tools/security/g4-m4-query-001";
const dorisReadRaces = {
  "s2-doris-revoke-race": ["after_read_revoke", "revoke-test", "DORIS_INFLIGHT_GRANT_REVOCATION"],
  "s2-doris-session-race": ["after_read_session_expiry", "session-test", "DORIS_INFLIGHT_SESSION_EXPIRY"],
  "s2-doris-ddl-race": ["source_postcheck_after_ddl", "ddl-test", "DORIS_INFLIGHT_CATALOG_DDL"],
  "s2-doris-deadline": ["platform_commit_deadline", "deadline-test", "DORIS_CONTENDED_COMMIT_DEADLINE"],
  "s2-doris-short-lock": ["platform_lock_timeout", "lock-test", "DORIS_PLATFORM_LOCK_TIMEOUT"],
  "s2-doris-disconnect": ["inflight_connection_closed", "disconnect-test", "DORIS_INFLIGHT_SOURCE_DISCONNECTED"],
  "s2-doris-batch-binding": ["verified_batch_faults", "batch-test", "DORIS_CANCEL_VERIFIED_RELEASE_BATCH"]
};
const twoTable = doris && argument("mode").startsWith("s2-doris-");
const stateName = twoTable ? "doris-two-table.json" : integration ? `scenario-${scenario}.json` : "runtime-fixture.json";
const port = value => doris ? ({15441:15641,15442:15642,15443:15643,15444:15644,15445:19030,15446:15645,15447:15646,15448:15647})[value] : integration ? value + 100 : value;
if (argument("task") !== task || argument("run-id") !== runId || await realpath(process.cwd()) !== root) throw new Error("QUERY_CONSUMER_BOUNDARY");
const mode = argument("mode"), require = createRequire(resolve(root, "apps/web/package.json"));
if (doris && !["provision","mapping","s1","s1-reopen","s1-current-catalog","s1-key-negative","s2-doris-mapping","s2-doris-queries","s2-doris-null","s2-doris-cancel","s2-doris-access","s2-doris-fanout","s2-doris-requalify","s2-doris-aba","s2-doris-admission-cancel","s2-doris-cancel-window","s2-doris-states","s2-doris-cardinality","s2-doris-identity","s2-doris-revoke-race","s2-doris-session-race","s2-doris-shape-prepare","s2-doris-shape-reject","s2-doris-shape-recover","s2-doris-cancel-profile","s2-doris-expiry","s2-doris-ddl-race","s2-doris-rotate-race","s2-doris-current-catalog","s2-doris-deadline","s2-doris-short-lock","s2-doris-disconnect","s2-doris-batch-binding"].includes(mode)) throw new Error("DORIS_SCENARIO_NOT_REGISTERED");
if (integration && ["standard-provision", "replace-disabled-connection", "numeric-provision", "s3-provision"].includes(mode)) throw new Error("INTEGRATION_USE_SEPARATE_SCENARIO_SETUP");
if (mode === "serve") {
  const { execFileSync } = await import("node:child_process");
  const { writeFile } = await import("node:fs/promises");
  const build = JSON.parse(execFileSync("python3", ["-B", "-c", `import sys,json;sys.path.insert(0,"scripts/maintenance");import ${moduleName} as q;${scenarioCode}print(json.dumps(q.web_binding()))`], { cwd: root, timeout: 30000, encoding: "utf8" }));
  process.env.PLATFORM_API_ORIGIN = `http://localhost:${port(15441)}`;
  process.env.NEXT_TELEMETRY_DISABLED = "1"; process.env.NODE_ENV = "production";
  const record = { taskId: task, runId, pid: process.pid, worktree: root, port: port(15442), build,
    processStartedAt: execFileSync("ps", ["-p", String(process.pid), "-o", "lstart="], { encoding: "utf8", env: { ...process.env, LC_ALL: "C" } }).trim(),
    startedAtUtc: new Date().toISOString(), decision: "KEEP", release: "M4 review and safe closeout" };
  await writeFile(resolve(root, "artifacts/workflow", task, runId, "web-process-" + process.pid + ".json"), JSON.stringify(record, null, 2) + "\n", { flag: "wx" });
  await require("next/dist/server/lib/start-server").startServer({ dir: resolve(root, "apps/web"), hostname: "127.0.0.1", port: port(15442),
    isDev: false, allowRetry: false, keepAliveTimeout: 5000 });
} else if (["s2-doris-revoke-race","s2-doris-session-race","s2-doris-shape-prepare","s2-doris-shape-reject","s2-doris-shape-recover","s2-doris-cancel-profile","s2-doris-expiry","s2-doris-ddl-race","s2-doris-rotate-race","s2-doris-current-catalog","s2-doris-deadline","s2-doris-short-lock","s2-doris-disconnect","s2-doris-batch-binding","s2-doris-cardinality","s2-doris-identity","s2-doris-states","s2-doris-cancel-window","s2-doris-admission-cancel","s2-doris-aba","s2-doris-requalify","s2-doris-fanout","s2-doris-access","s2-doris-cancel","s2-doris-mapping","s2-doris-queries","s2-doris-null","s1-current-catalog", "s1-key-negative", "ready", "ready-session-expired", "ready-session-short", "provision", "mapping", "s1", "s1-reopen", "ui-s1", "s2-basic", "s2-runtime", "s2-race", "s2-aba", "s2-aba-prepare", "s2-capacity", "s2-connection", "s2-inflight", "s3-provision", "s3", "ui-s3", "replace-disabled-connection", "numeric-provision", "numeric", "standard-provision"].includes(mode)) await browserRun(mode);
else throw new Error("QUERY_MODE_NOT_IMPLEMENTED");

/** 独立浏览器上下文只保留内存会话，不保存Cookie、HAR、trace或storageState。 */
async function browserRun(mode) {
  const { randomUUID, createHash } = await import("node:crypto");
  const { writeFile, mkdir } = await import("node:fs/promises");
  const output = resolve(root, "artifacts/workflow", task, runId);
  const privateRoot = resolve(root, privateName, runId);
  const realm = JSON.parse(await readFile(resolve(privateRoot, "runtime/realm.json"), "utf8"));
  if (!realm.authority.startsWith(`http://localhost:${port(15443)}/realms/g2-`)) throw new Error("QUERY_REALM_BOUNDARY");
  const origin = `http://localhost:${port(15441)}`;
  const file = resolve(output, "browser-" + mode + "-" + Date.now() + ".json");
  const report = { taskId: task, runId, mode, startedAtUtc: new Date().toISOString(), checks: [], http: [], status: "FAIL" };
  const { execFileSync } = await import("node:child_process");
  const binding = () => JSON.parse(execFileSync("python3", ["-B", "-c", `import sys,json;sys.path.insert(0,"scripts/maintenance");import ${moduleName} as q;${scenarioCode}print(json.dumps({"api":q.runtime_binding(),"web":q.web_binding() if any(arg.startswith("ui-") for arg in sys.argv) else None}))`, mode], { cwd: root, timeout: 30000, encoding: "utf8" }));
  const observed = () => JSON.parse(execFileSync("python3", ["-B", "-c", `import sys,json;sys.path.insert(0,"scripts/maintenance");import ${moduleName} as q;${scenarioCode}print(json.dumps(q.source_scan_snapshot()))`], { cwd: root, timeout: 30000, encoding: "utf8" }));
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
      if ([origin, `http://localhost:${port(15443)}`].includes(new URL(route.request().url()).origin)) return route.continue();
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
    actor.sessionCookie = cookie.value;
    return actor;
  }
  async function save(state) {
    const bytes = JSON.stringify(state, null, 2) + "\n";
    if (integration) await writeFile(resolve(output, `prerequisite-${scenario}-${randomUUID()}.json`), bytes, { flag: "wx" });
    await writeFile(resolve(output, stateName), bytes);
  }
  async function heldQuery(actor, query, mutate, revoke = false) {
    const { spawn, execFileSync } = await import("node:child_process");
    const key = randomUUID();
    const launch = (code, args = []) => {
      const child = spawn("python3", ["-B", "-c", code, ...args], { cwd: root, stdio: ["ignore", "pipe", "pipe"] });
      let buffer = "", readyResolve, readyReject, endResolve;
      const events = [];
      const ready = new Promise((yes, no) => { readyResolve = yes; readyReject = no; });
      const done = new Promise(yes => { endResolve = yes; });
      child.stdout.on("data", chunk => {
        buffer += chunk.toString(); let end;
        while ((end = buffer.indexOf("\n")) >= 0) {
          const line = buffer.slice(0, end); buffer = buffer.slice(end + 1);
          try { const event = JSON.parse(line); events.push(event); if (event.status === "READY") readyResolve(); }
          catch { readyReject(new Error("race_fixture_protocol_invalid")); }
        }
      });
      child.stderr.resume();
      child.on("error", () => { readyReject(new Error("race_fixture_start_failed")); endResolve({ code: -1, events }); });
      child.on("exit", code => { if (code !== 0) readyReject(new Error("race_fixture_failed")); endResolve({ code, events }); });
      return { ready, done };
    };
    const prefix = `import sys;sys.path.insert(0,"scripts/maintenance");import ${moduleName} as q;${scenarioCode}`;
    const watcher = launch(prefix + 'q.query_admission_watch(sys.argv[1],sys.argv[2]=="true")', [key, String(revoke)]);
    await watcher.ready;
    const barrier = launch(prefix + 'q.query_source_barrier()');
    await barrier.ready;
    try {
      const running = request({ ...actor, headers: { ...actor.headers, "Idempotency-Key": key } }, "POST", "/api/v1/data/semantic-queries", query, [403, 409, 503])
        .then(value => ({ value }), error => ({ error }));
      const watched = await watcher.done;
      const admitted = watched.events.find(item => item.status === "FOUND");
      check("inflight_real_admission", watched.code === 0 && /^query-[0-9a-f]{32}$/.test(admitted?.queryId ?? ""));
      await mutate();
      const response = await running;
      if (response.error) throw response.error;
      check("inflight_current_change_rejects_completion", [403, 409].includes(response.value.status));
      const probe = JSON.parse(execFileSync("python3", ["-B", "-c", prefix+'import json;print(json.dumps(q.query_fixture_control("query-probe",sys.argv[1])))', key], { cwd: root, encoding: "utf8", timeout: 15000 }));
      check("inflight_no_completed_record", JSON.parse(probe.output).status !== "COMPLETED");
    } finally {
      const released = await barrier.done;
      check("inflight_barrier_released", released.code === 0 && released.events.some(item => item.status === "RELEASED"));
    }
  }
  try {
    report.inputBinding = binding();
    const { chromium } = require("@playwright/test");
    browser = await chromium.launch({ channel: "msedge", headless: true, args: ["--disable-background-networking", "--disable-component-update"] });
    const operator = await identity("operator-ab"), auditor = await identity("auditor-ab");
    const activator = doris ? await identity("operator-a") : operator;
    const reader = doris ? await identity("viewer-a") : operator;
    check("distinct_oidc_subjects", operator.me.subjectId !== auditor.me.subjectId);
    let state;
    try { state = JSON.parse(await readFile(resolve(output, stateName), "utf8")); }
    catch (error) {
      if (error.code !== "ENOENT") throw error;
      if (twoTable) {
        check("initial_two_table_mapping", mode === "s2-doris-mapping");
        state = JSON.parse(await readFile(resolve(output, "runtime-fixture.json"), "utf8"));
        check("single_table_baseline", state.latestQuery?.resultHash && state.mappingRelease?.manifest.mapping.entities.length === 1);
        for (const key of Object.keys(state)) if (key.startsWith("mapping") || ["firstQuery","latestQuery"].includes(key)) delete state[key];
      } else state = { taskId: task, runId, ...(integration ? { scenario, s3: true, numeric: scenario === "numeric" } : {}), scope: { organizationId: "org-demo", siteIds: doris ? ["site-a"] : ["site-a", "site-b"] } }; }
    check("fixture_identity", state.taskId === task && state.runId === runId);
    if (doris) {
      check("distinct_four_roles", new Set([operator,auditor,activator,reader].map(a => a.me.subjectId)).size === 4);
      state.connectionDisplayName = "Doris Mapping Query synthetic";
      state.subjects = { operator: operator.me.subjectId, auditor: auditor.me.subjectId, activator: activator.me.subjectId, reader: reader.me.subjectId };
      await save(state);
    }
    if (integration) { state.subjects = { operator: operator.me.subjectId, auditor: auditor.me.subjectId }; await save(state); }
    if (integration && mode !== "provision") {
      phase = "scenario_ready";
      const prerequisite = (key, value) => {
        if (!value) { const error = new Error(); error.safeCode = "PREREQUISITE_STALE:" + key; throw error; }
      };
      prerequisite("session", Boolean(operator.me.subjectId && auditor.me.subjectId));
      const probeSession = () => JSON.parse(execFileSync("python3", ["-B", "-c",
        `import sys,json;sys.path.insert(0,"scripts/maintenance");import workflow_m5_integration as q;print(json.dumps(q.browser_session_ready(json.load(sys.stdin))))`],
        { cwd: root, encoding: "utf8", timeout: 60000, input: JSON.stringify([operator, auditor].map(actor => ({ cookie: actor.sessionCookie, subjectId: actor.me.subjectId }))) }));
      const sessionProbe = probeSession();
      prerequisite("session", sessionProbe.status === "READY");
      report.sessionPreflight = sessionProbe;
      if (["ready-session-expired", "ready-session-short"].includes(mode)) {
        const sessionHash = sessionProbe.observations[0].sessionHash;
        const changeExpiry = value => JSON.parse(execFileSync("python3", ["-B", "-c",
          'import sys,json;sys.path.insert(0,"scripts/maintenance");import workflow_m5_integration as q;print(json.dumps(q.session_expiry_control(sys.argv[1],sys.argv[2])))', sessionHash, value],
          { cwd: root, encoding: "utf8", timeout: 15000 }));
        const changed = changeExpiry(mode === "ready-session-expired" ? "expired" : "short");
        let rejected = false;
        try {
          try { probeSession(); }
          catch (error) { rejected = error.status !== 0 && String(error.stderr).includes("PREREQUISITE_STALE:session_deadline"); }
        } finally {
          const restored = changeExpiry(changed.before);
          check("original_session_expiry_restored", Date.parse(restored.after) === Date.parse(changed.before));
          report.sessionNegative = { changed, restored, rejected, businessOperationStarted: false };
        }
        check("same_session_deadline_rejected_before_long_operation", rejected);
        report.status = "PASS"; report.scope = "SESSION_PREREQUISITE_COUNTEREXAMPLE_ONLY";
        return;
      }
      prerequisite("scenario", state.scenario === scenario);
      prerequisite("connection", Boolean(state.connectionId));
      const connection = await get(operator, `/api/v1/connections/${state.connectionId}`);
      prerequisite("connection", connection.state === "ACTIVE");
      const local = JSON.parse(execFileSync("python3", ["-B", "-c",
        `import sys,json;sys.path.insert(0,"scripts/maintenance");import ${moduleName} as q;${scenarioCode}print(json.dumps(q.local_ready(${mode.startsWith("ui-") ? "True" : "False"},${mode === "mapping" ? "False" : "True"})))`],
        { cwd: root, encoding: "utf8", timeout: 60000 }));
      if (mode !== "mapping") {
        prerequisite("activation", Boolean(state.mappingReceipt));
        const active = await get(operator, `/api/v1/mappings/${state.mappingDraft.mappingId}/active`);
        const expected = state.mappingCurrentReceipt ?? state.mappingReceipt;
        report.activationPreflight = { active, expected: { mappingId: expected.mappingId, mappingReleaseId: expected.mappingReleaseId, activationRevision: expected.activationRevision } };
        prerequisite("activation", active.mappingId === expected.mappingId && active.mappingReleaseId === expected.mappingReleaseId && active.manifestHash === expected.manifestHash && active.activationRevision === expected.activationRevision);
      }
      report.scenarioReady = { status: "SCENARIO_READY", scenario, taskId: task, resourceOwner: task, runId, localReceipt: local.receipt,
        subjects: state.subjects, fixedRelease: state.mappingReceipt?.mappingReleaseId, observedAtUtc: new Date().toISOString() };
    }
    if (!doris) state.subjects = { operator: operator.me.subjectId, auditor: auditor.me.subjectId };
    await save(state);
    const prepareShape = mode === "s2-doris-shape-prepare";
    if (mode === "s2-doris-aba" || prepareShape) mode = "s2-aba-prepare";
    if (mode === "s2-doris-requalify") {
      if (!state.replacedDorisMapping) {
        const previous = state.mappingReceipt;
        check("known_original_release", previous?.mappingReleaseId === "release-a5f93d1137a04133a3fe1265642abed5" &&
          state.mappingRelease.manifest.mapping.entities.length === 2 && Boolean(state.latestQuery));
        const archive = "s2-before-exact-join-" + previous.mappingReleaseId + ".json";
        await writeFile(resolve(output, archive), JSON.stringify(state, null, 2), { flag: "wx" });
        state.replacedDorisMapping = { mappingId: previous.mappingId, releaseId: previous.mappingReleaseId, archive };
        for (const key of Object.keys(state))
          if (key.startsWith("mapping") || ["firstQuery", "latestQuery"].includes(key)) delete state[key];
        await save(state);
      }
      mode = "s2-doris-mapping";
    }
    if (mode === "s2-doris-mapping") mode = "mapping";
    if (doris && ["mapping", "s1","s2-doris-queries"].includes(mode)) {
      phase = "explicit_synthetic_grants";
      report.grants = JSON.parse(execFileSync("python3", ["-B", "scripts/maintenance/workflow_doris_s1.py",
        (twoTable ? "s2-" : "") + (mode === "mapping" ? "mapping-grants" : "query-grants")], { cwd: root, timeout: 30000, encoding: "utf8" }));
    }
    if (mode === "ready") {
      report.status = "PASS"; report.scope = "SCENARIO_PREREQUISITE_ONLY";
    } else if (mode === "standard-provision") {
      check("standard_follows_numeric_proof", Boolean(state.numeric && state.numericResult));
      const retired = { retiredAtUtc: new Date().toISOString(), reason: "numeric-proof-preserved-standard-safety-regression" };
      for (const key of Object.keys(state)) if (/^(mapping|s2)/.test(key) || ["connectionId", "catalog", "firstQuery", "latestQuery", "connectionDisplayName", "numericResult"].includes(key)) { retired[key] = state[key]; delete state[key]; }
      state.retiredFixtures ??= []; state.retiredFixtures.push(retired); state.numeric = false;
      state.connectionDisplayName = "M4 review-fix standard safety regression"; await save(state); mode = "provision";
    }
    if (mode === "numeric-provision") {
      if (!state.numeric) {
        const retired = { retiredAtUtc: new Date().toISOString(), reason: "review-fix-numeric-independent-fixture" };
        for (const key of Object.keys(state)) if (/^(mapping|s2)/.test(key) || ["connectionId", "catalog", "firstQuery", "latestQuery", "connectionDisplayName"].includes(key)) { retired[key] = state[key]; delete state[key]; }
        state.retiredFixtures ??= []; state.retiredFixtures.push(retired);
        state.numeric = true; state.s3 = true;
        state.connectionDisplayName = "M4 numeric review-fix synthetic connection"; await save(state);
      }
      mode = "provision";
    }
    if (mode === "s3-provision") {
      if (!state.s3) {
        const retired = { retiredAtUtc: new Date().toISOString(), reason: "s3_formal_vocabulary_and_two_table_mapping" };
        for (const key of Object.keys(state)) if (/^(ontology|mapping|s2)/.test(key) || ["firstQuery", "latestQuery"].includes(key)) { retired[key] = state[key]; delete state[key]; }
        state.retiredFixtures ??= []; state.retiredFixtures.push(retired); state.s3 = true; await save(state);
      }
      mode = "provision";
    }
    if (mode === "replace-disabled-connection") {
      const disabled = await get(operator, `/api/v1/connections/${state.connectionId}`);
      check("replacement_only_for_terminal_disabled_connection", disabled.state === "DISABLED");
      const retired = { retiredAtUtc: new Date().toISOString(), reason: "terminal_disabled_and_query_test_isolation_failure" };
      for (const key of Object.keys(state)) {
        if (/^(mapping|s2)/.test(key) || ["connectionId", "catalog", "firstQuery", "latestQuery", "connectionDisplayName"].includes(key)) {
          retired[key] = state[key]; delete state[key];
        }
      }
      state.retiredFixtures ??= []; state.retiredFixtures.push(retired);
      state.connectionDisplayName = "M4 synthetic PostgreSQL query replacement " + state.retiredFixtures.length;
      await save(state);
      mode = "provision";
    }
    if (mode === "s2-doris-current-catalog") {
      phase = "current_doris_connection_after_rotation";
      const prior = state.credentialRotation;
      check("rotation_bound_to_this_connection", prior?.connectionId === state.connectionId && prior.archive === "s2-pre-rotation-"+prior.originalQueryId+".json");
      const current = await get(operator,"/api/v1/connections/"+state.connectionId);
      check("rotation_committed_once",current.secretVersion===prior.version+1 && current.configRevision>=prior.revision+1);
      if (!prior.reset) {
        const archived = JSON.parse(await readFile(resolve(output,prior.archive),"utf8"));
        check("restoration_origins",archived.connectionId===state.connectionId && archived.latestQuery.queryId===prior.originalQueryId &&
          archived.catalog.snapshotId===prior.snapshot && archived.mappingReceipt.mappingReleaseId===prior.release);
        for (const key of Object.keys(state)) {
          if (key.startsWith("mapping") || ["catalog","latestQuery","firstQuery","shapePreparation","s2AbaInFlight"].includes(key)) delete state[key];
        }
        prior.reset=true;
        await save(state);
      }
      mode = "provision";
    }
    if (doris && mode === "s1-current-catalog") {
      phase = "doris_post_release_catalog";
      check("previous_run_complete", Boolean(state.ontologyRelease && state.latestQuery && state.catalog));
      await writeFile(resolve(output, "s1-before-discovery-" + state.latestQuery.queryId + ".json"), JSON.stringify(state, null, 2), { flag: "wx" });
      for (const key of Object.keys(state)) if (key.startsWith("mapping") || ["firstQuery","latestQuery","catalog"].includes(key)) delete state[key];
      await save(state);
      mode = "provision";
    }
    if (mode === "s2-doris-fanout") {
      phase = "fanout_after_activation";
      const change = value => JSON.parse(execFileSync("python3", ["-B", "scripts/maintenance/workflow_doris_s1.py", "fanout", "--fanout", value],
        { cwd: root, timeout: 40000, encoding: "utf8" }));
      const traverse = () => request({ ...reader, headers: { ...reader.headers, "Idempotency-Key": randomUUID() } },
        "POST", "/api/v1/data/semantic-queries", state.latestQuery.query);
      const edgeIds = result => result.data.data.filter(x => x.kind === "relationship").map(x => x.target.identity.externalId).sort();
      {
        const ten = change("ten");
        const complete = await traverse();
        check("all_ten_edges_match_independent_sql", complete.data.status === "FOUND" && !complete.data.limited &&
          JSON.stringify(edgeIds(complete)) === JSON.stringify(ten.expected));
        const eleven = change("eleven");
        const partial = await traverse();
        check("eleventh_edge_rejected_before_expansion", eleven.expected.length === 11 && partial.data.status === "PARTIAL" &&
          partial.data.data.some(x => x.kind === "entity") && edgeIds(partial).length === 0 &&
          partial.data.subSources.some(x => x.status === "UNAVAILABLE" && !x.sourceReadReceiptId));
        report.fanout = { ten: { queryId: complete.queryId, edges: edgeIds(complete) },
          eleven: { queryId: partial.queryId, status: partial.data.status, expected: eleven.expected, edges: edgeIds(partial) } };
        mode = "s2-doris-fanout-negative";
      }
    }
    if (mode === "s2-doris-rotate-race") {
      phase = "rotate_doris_after_real_read";
      const current = await request(operator,"GET","/api/v1/connections/"+state.connectionId);
      check("one_active_connection_before_rotation",current.data.state==="ACTIVE" && !state.credentialRotation &&
        state.catalog.connectionId===state.connectionId && state.mappingRelease.manifest.mapping.entities.length===2);
      const cap=(await get(reader,"/api/v1/capabilities")).find(c=>c.id==="g4_resolve_entity");
      const query={...state.latestQuery.query,capabilityId:cap.id,capabilityVersion:cap.version,relationshipIris:[],filters:{siteId:"site-a",entityExternalId:"E1"}};
      const original=await request({...reader,headers:{...reader.headers,"Idempotency-Key":randomUUID()}},"POST","/api/v1/data/semantic-queries",query);
      check("known_real_source_row",original.data.status==="FOUND");
      const prior={connectionId:state.connectionId,revision:current.data.configRevision,version:current.data.secretVersion,
        snapshot:state.catalog.snapshotId,release:state.mappingReceipt.mappingReleaseId,originalQueryId:state.latestQuery.queryId,
        originalResultHash:state.latestQuery.resultHash,archive:"s2-pre-rotation-"+state.latestQuery.queryId+".json"};
      await writeFile(resolve(output,prior.archive),JSON.stringify(state,null,2),{flag:"wx"});
      state.credentialRotation=prior;
      await save(state);
      const password=await readFile(resolve(privateRoot,"../implementation-01-source/reader.pass"),"utf8");
      secrets.push(password);
      const secret=await post(operator,"/api/v1/connection-secrets",{secretValue:password,scopeSelection:state.scope,purpose:"DORIS_READONLY",command:command()},201);
      secrets.push(secret.secretRef);
      const envelope={queryId:original.queryId,rotation:{connectionId:state.connectionId,revision:prior.revision,version:prior.version,etag:current.etag,reference:secret.secretRef},
        roles:[[operator,"A"],[auditor,"B"],[activator,"C"],[reader,"Q"]].map(([a,role])=>({role,subjectId:a.me.subjectId,cookie:a.sessionCookie}))};
      report.race=JSON.parse(execFileSync("python3",["-B","scripts/maintenance/workflow_doris_s1.py","rotate-test"],{
        cwd:root,input:JSON.stringify(envelope),timeout:40000,encoding:"utf8",stdio:["pipe","pipe","pipe"]}));
      const advanced=await get(operator,"/api/v1/connections/"+state.connectionId);
      check("same_connection_new_version",advanced.id===state.connectionId && advanced.secretVersion===prior.version+1 && advanced.configRevision===prior.revision+1);
      await request(reader,"GET","/api/v1/data/semantic-queries/"+original.queryId+"/result",undefined,403);
      report.versions={connectionId:prior.connectionId,before:prior.version,after:advanced.secretVersion,revision:advanced.configRevision};
      report.status="PASS"; report.scope="DORIS_INFLIGHT_CREDENTIAL_VERSION";
      return;
    }
    if (Object.hasOwn(dorisReadRaces, mode)) {
      const [racePhase, testCommand, raceScope] = dorisReadRaces[mode];
      phase = racePhase;
      const cap=(await get(reader,"/api/v1/capabilities")).find(c=>c.id==="g4_resolve_entity");
      const query={...state.latestQuery.query,capabilityId:cap.id,capabilityVersion:cap.version,relationshipIris:[],filters:{siteId:"site-a",entityExternalId:"E1"}};
      const original=await request({...reader,headers:{...reader.headers,"Idempotency-Key":randomUUID()}},"POST","/api/v1/data/semantic-queries",query);
      check("known_real_source_row",original.data.status==="FOUND");
      const envelope={queryId:original.queryId,roles:[[operator,"A"],[auditor,"B"],[activator,"C"],[reader,"Q"]].map(([a,role])=>({role,subjectId:a.me.subjectId,cookie:a.sessionCookie}))};
      report.race=JSON.parse(execFileSync("python3",["-B","scripts/maintenance/workflow_doris_s1.py",testCommand],
        {cwd:root,input:JSON.stringify(envelope),timeout:40000,encoding:"utf8",stdio:["pipe","pipe","pipe"]}));
      if (mode === "s2-doris-ddl-race") execFileSync("python3",["-B","scripts/maintenance/workflow_doris_s1.py","ddl-fixture","--ddl-action","restore"],{cwd:root,timeout:10000});
      const recovered=await request(reader,"GET","/api/v1/data/semantic-queries/"+original.queryId+"/result");
      check("restored_original",recovered.raw===original.raw);
      report.status="PASS";report.scope=raceScope;
    } else if (mode === "s2-doris-expiry") {
      phase = "expire_disposable_completed_query";
      const cap=(await get(reader,"/api/v1/capabilities")).find(c=>c.id==="g4_resolve_entity");
      const query={...state.latestQuery.query,capabilityId:cap.id,capabilityVersion:cap.version,relationshipIris:[],filters:{siteId:"site-a",entityExternalId:"E1"}};
      const key=randomUUID();
      const original=await request({...reader,headers:{...reader.headers,"Idempotency-Key":key}},"POST","/api/v1/data/semantic-queries",query);
      check("disposable_entity",original.data.status==="FOUND" && original.data.evidence.length>0);
      const resultPath="/api/v1/data/semantic-queries/"+original.queryId+"/result";
      const evidencePath="/api/v1/data/source-evidence/"+encodeURIComponent(original.data.evidence[0].evidenceId);
      check("before_expiry_original_bytes",(await request(reader,"GET",resultPath)).raw===original.raw);
      const hash=createHash("sha256").update(original.raw).digest("hex");
      report.expiry=JSON.parse(execFileSync("python3",["-B","scripts/maintenance/workflow_doris_s1.py","expire-disposable","--query-identity",original.queryId,key,hash],{cwd:root,encoding:"utf8",timeout:20000}));
      const before=observed();
      const expired=await request(reader,"GET",resultPath,undefined,410);
      const detail=await request(reader,"GET",evidencePath,undefined,410);
      const after=observed();
      check("expired_result_and_evidence",expired.data.code==="result_expired" && detail.data.code==="result_expired");
      check("expired_reads_do_not_execute",before.auditInode===after.auditInode && before.queryIdsSha256===after.queryIdsSha256);
      report.expiry={...report.expiry,before,after};
      report.status="PASS";report.scope="DORIS_DISPOSABLE_QUERY_TTL";
    } else if (mode === "s2-doris-cancel-profile") {
      phase = "profile_cancel_on_completed_query";
      const cap=(await get(reader,"/api/v1/capabilities")).find(c=>c.id==="g4_resolve_entity");
      const query={...state.latestQuery.query,capabilityId:cap.id,capabilityVersion:cap.version,relationshipIris:[],filters:{siteId:"site-a",entityExternalId:"E1"}};
      const completed=await request({...reader,headers:{...reader.headers,"Idempotency-Key":randomUUID()}},"POST","/api/v1/data/semantic-queries",query);
      check("ordinary_entity_read",completed.data.status==="FOUND");
      for (let sample=0;sample<3;sample++) {
        const prior=await request(reader,"POST","/api/v1/data/semantic-queries/"+completed.queryId+"/cancel",undefined,409);
        check("already_completed_"+sample,prior.data.code==="query_already_finished");
      }
      report.measuredQueryId=completed.queryId;
      report.scope="READONLY_COMPLETED_CANCEL_TIMINGS"; report.status="PASS";
    } else if (mode === "s2-doris-shape-reject") {
      phase = "activate_previously_approved_proposal_with_changed_catalog";
      const prev = state.shapePreparation;
      check("shape_proposal_bound", prev?.approved?.status === "APPROVED");
      const proposal = prev.approved;
      const baseline = await get(activator,"/api/v1/mappings/"+state.mappingDraft.mappingId+"/active");
      check("reviewed_activation", baseline.activationId===prev.baseline.activationId);
      const result = await request(activator,"POST","/api/v1/mapping-proposals/"+proposal.proposalId+"/activate",
        {bindingHash:proposal.bindingHash,expectedActive:proposal.expectedActive,command:command(proposal.proposalRevision)},
        409,`"proposal:${proposal.proposalRevision}"`);
      check("persisted_activation_check",result.data.code==="mapping_activation_check_failed" && Boolean(result.data.checkId));
      state.shapePreparation.lastCheck = result.data.checkId;
      await save(state);
      const denied = await request(activator,"GET","/api/v1/mapping-activation-checks/"+result.data.checkId,undefined,403);
      check("changed_source_blocks_check_disclosure",denied.data.code==="mapping_source_access_unverified");
      const after = await get(activator,"/api/v1/mappings/"+state.mappingDraft.mappingId+"/active");
      check("previous_release_retained",after.mappingReleaseId===baseline.mappingReleaseId &&
        after.activationId===baseline.activationId && after.activationRevision===baseline.activationRevision);
      report.shapeCheck={proposalId:proposal.proposalId,checkId:result.data.checkId,before:baseline,after};
      report.status="PASS"; report.scope="DORIS_ACTIVATION_REFUSES_CHANGED_SOURCE";
    } else if (mode === "s2-doris-shape-recover") {
      phase = "read_original_check_after_source_restoration";
      const prev=state.shapePreparation;
      const checked=await get(activator,"/api/v1/mapping-activation-checks/"+prev.lastCheck);
      const codes=checked.stages.flatMap(s=>s.issueCodes);
      report.shapeCheck={proposalId:checked.proposalId,checkId:checked.checkId,stages:checked.stages};
      check("original_bound_check",checked.checkId===prev.lastCheck && checked.proposalId===prev.approved.proposalId);
      check("source_failure_persisted",codes.includes("mapping_source_shape_invalid"));
      const active=await get(activator,"/api/v1/mappings/"+state.mappingDraft.mappingId+"/active");
      check("baseline_activation_after_restore",active.mappingReleaseId===prev.baseline.mappingReleaseId &&
          active.activationId===prev.baseline.activationId && active.activationRevision===prev.baseline.activationRevision);
      report.status="PASS";report.scope="DORIS_ACTIVATION_CHECK_RECOVERED";
    } else if (mode === "s2-doris-states") {
      phase = "normal_states_and_source_acl";
      const cap = (await get(reader, "/api/v1/capabilities")).find(c => c.id === "g4_resolve_entity");
      const execute = filters => request({...reader, headers:{...reader.headers,"Idempotency-Key":randomUUID()}}, "POST",
        "/api/v1/data/semantic-queries", {...state.latestQuery.query, capabilityId:cap.id, capabilityVersion:cap.version, relationshipIris:[], filters});
      const empty = await execute({siteId:"site-a",entityExternalId:"missing"});
      check("verified_empty", empty.data.status==="EMPTY" && !empty.data.limited && empty.data.evidence.length===0);
      const both = await execute({siteId:"site-a"});
      check("two_true_candidates", both.data.status==="AMBIGUOUS" && both.data.candidates.length===2 && !both.data.limited);
      const path = "/api/v1/data/semantic-queries/"+state.latestQuery.queryId+"/result";
      const original = await request(reader,"GET",path);
      const evidence = "/api/v1/data/source-evidence/"+encodeURIComponent(original.data.evidence[0].evidenceId);
      const change = action => execFileSync("python3",["-B","scripts/maintenance/workflow_doris_s1.py","state-fixture","--state-operation",action],
        {cwd:root,encoding:"utf8",timeout:15000});
      change("deny");
      try {
        const old = await request(reader,"GET",path,undefined,403);
        const denied = await request(reader,"GET",evidence,undefined,403);
        const before = observed();
        const fresh = await execute({siteId:"site-a",entityExternalId:"E1"});
        const after = observed();
        check("source_acl_denied_without_business_projection", fresh.data.status==="UNAUTHORIZED" && fresh.data.data.length===0 &&
          fresh.data.evidence.length===0 && before.queryIdsSha256===after.queryIdsSha256 && before.auditInode===after.auditInode);
        report.sourceAccess={result:old.status,evidence:denied.status,before,after};
      } finally { change("allow"); }
      check("source_acl_restored_original_bytes",(await request(reader,"GET",path)).raw===original.raw);
      report.status="PASS";report.scope="DORIS_EMPTY_AMBIGUOUS_SOURCE_PRIVILEGE";
    } else if (mode === "s2-doris-access") {
      phase="current_authority";
      const original=state.latestQuery;
      const path="/api/v1/data/semantic-queries/"+original.queryId+"/result";
      const read=await request(reader,"GET",path);
      const evidence=read.data.evidence[0].evidenceId;
      const change=action=>JSON.parse(execFileSync("python3",["-B","scripts/maintenance/workflow_doris_s1.py","permission","--permission",action],
        {cwd:root,timeout:20000,encoding:"utf8"}));
      report.grantEvents=[];
      for (const kind of ["result","evidence","execute"]) {
        report.grantEvents.push(change("revoke-"+kind));
        try {
          if(kind==="evidence") await request(reader,"GET","/api/v1/data/source-evidence/"+encodeURIComponent(evidence),undefined,403);
          else await request(reader,"GET",path,undefined,403);
          if(kind==="execute"){
            const before=observed();
            const denied=await request({...reader,headers:{...reader.headers,"Idempotency-Key":randomUUID()}},"POST","/api/v1/data/semantic-queries",original.query);
            const after=observed();
            check("no_source_rows_after_revocation",denied.data.status==="UNAUTHORIZED" && denied.data.data.length===0 && denied.data.evidence.length===0 &&
              before.auditInode===after.auditInode && before.queryIdsSha256===after.queryIdsSha256);
            report.denyScans={before,after};
          }
        } finally { report.grantEvents.push(change("restore-"+kind)); }
      }
      check("same_saved_bytes_after_regrant",(await request(reader,"GET",path)).raw===read.raw);
      report.status="PASS";report.scope="DORIS_CURRENT_AUTHORITY";
    } else if (["s2-doris-cancel","s2-doris-admission-cancel","s2-doris-cancel-window"].includes(mode)) {
      const admission = mode === "s2-doris-admission-cancel";
      phase="formal_cancel";
      const {spawn}=await import("node:child_process");
      const {createInterface}=await import("node:readline");
      // 真实已完成查询用于预热同一正式取消路由，先检查 409 不改原结果。
      const warmed = await request(reader, "POST", "/api/v1/data/semantic-queries/"+state.latestQuery.queryId+"/cancel", undefined, 409);
      check("previous_completed_cancel_warmed", warmed.data.code === "query_already_finished");
      const key=randomUUID();
      const monitor=spawn("python3",["-B","scripts/maintenance/doris_query_cancel_witness.py",key,...(admission?["--admit-first"]:[])],{cwd:root,stdio:["ignore","pipe","ignore"]});
      const lines=createInterface({input:monitor.stdout})[Symbol.asyncIterator]();
      const next=async () => { const entry=await lines.next(); check("witness_event_"+report.checks.length,!entry.done); return JSON.parse(entry.value); };
      try {
        check("armed_witness",(await next()).event==="ready");
        const capability=(await get(reader,"/api/v1/capabilities")).find(c=>c.id==="g4_resolve_entity");
        const query={...state.latestQuery.query,capabilityId:capability.id,capabilityVersion:capability.version,relationshipIris:[],filters:{siteId:"site-a"}};
        const begin=performance.now();
        const running=request({...reader,headers:{...reader.headers,"Idempotency-Key":key}},"POST","/api/v1/data/semantic-queries",query,[200,403,409,422,503,504]);
        const active=await next();
        report.witness=active;
        if(active.event!==(admission?"admitted":"active")){await running;check("source_was_executing",false);}
        if (mode === "s2-doris-cancel-window") {
          await running;
          const final = await next();
          check("natural_source_window", final.beEvents.some(e=>e.kind==="registered") && final.beEvents.some(e=>e.kind==="context_end"));
          report.naturalWindow = final;
          report.status="PASS"; report.scope="CANCEL_PRESSURE_WINDOW_MEASUREMENT_ONLY";
          return;
        }
        const issued=Date.now();
        const cancelled=await request(reader,"POST","/api/v1/data/semantic-queries/"+active.queryId+"/cancel",undefined,[200,409]);
        const delivery=await running;
        const elapsed=performance.now()-begin;
        const final=await next();
        report.cancel={issuedUtc:new Date(issued).toISOString(),httpStatus:cancelled.status,initialStatus:delivery.status,elapsedMs:elapsed,witness:final};
        check("cancel_committed_and_no_success",cancelled.status===200 && final.terminal==="CANCELLED" && final.persisted.bytes===0 &&
          final.persisted.resultHash===null && final.persisted.readReceipts===0 && final.persisted.cancelRequested && final.cancelAuditCount===1 && final.successfulAuditCount===0);
        if (admission) {
          report.status="PASS";
          report.scope="DORIS_CANCEL_WON_AT_PLATFORM";
          // 此用例只要求真实取消成功和持久化 fence，源在途终止由独立门禁裁决。
          return;
        }
        const kinds=final.beEvents.map(e=>e.kind);
        check("server_cancelled_active_query",final.cancelVisibleBeforeBeKilled === true && ["registered","cancel_arrived","task_cancelled","fragment_end","context_end"].every(k=>kinds.includes(k)));
        const when=e=>Date.parse(e.beUtc.replace(/^(\d{4})(\d{2})(\d{2}) /,"$1-$2-$3T")+"Z");
        const firstRegistration = Math.min(...final.beEvents.filter(e=>e.kind==="registered").map(when));
        const endFloorMs = Math.max(...final.beEvents.filter(e=>e.kind==="context_end").map(when));
        // 毫秒解析会舍弃小数，用区间上界判定，不把边界舍入成通过。
        const cleanupUpperMs = endFloorMs + 1 - issued;
        report.cancel.cleanupUpperMs = cleanupUpperMs;
        check("source_active_before_request",firstRegistration + 1 <= issued);
        check("source_cleanup_inside_deadline",cleanupUpperMs>=0 && cleanupUpperMs<=250 && final.sourceCounts==="0\t0" && elapsed<=5000);
        report.status="PASS"; report.scope="DORIS_FORMAL_CANCELLATION";
      } finally { monitor.stdout.destroy(); }
    } else if (mode === "s2-doris-queries") {
      phase = "two_table_exact_edges";
      const capabilities = await get(reader, "/api/v1/capabilities");
      const capId = "g4_traverse_relationships";
      const query = { assetId: state.ontologyRelease.manifest.assetId, ontologyReleaseId:state.ontologyRelease.manifest.releaseId,
        mappingReleaseIds:[state.mappingReceipt.mappingReleaseId], capabilityId:capId, capabilityVersion:capabilities.find(c => c.id === capId).version,
        relationshipIris:["urn:synthetic:mapping:hasReading"], depth:1,maxRows:100,timeoutMs:5000,filters:{siteId:"site-a",entityExternalId:"E1"} };
      const result = await request({...reader,headers:{...reader.headers,"Idempotency-Key":randomUUID()}},"POST","/api/v1/data/semantic-queries",query);
      const edges = result.data.data.filter(item => item.kind === "relationship");
      check("two_exact_targets", result.data.status === "FOUND" && !result.data.limited &&
        JSON.stringify(edges.map(edge => edge.target.identity.externalId).sort()) === JSON.stringify(["T1","T2"]));
      check("only_current_scope", edges.every(edge => edge.source.identity.externalId === "E1" && edge.target.identity.siteId === "site-a"));
      check("two_source_windows_unknown", result.data.subSources.length === 2 && result.data.subSources.every(b => b.status === "SUCCESS" && b.watermarkKind === "UNKNOWN"));
      const restored=await request(reader,"GET","/api/v1/data/semantic-queries/"+result.queryId+"/result");
      check("two_table_canonical_recovery",restored.raw===result.raw);
      for (const edge of edges) for (const id of edge.evidenceIds) {
        const evidence = await get(reader,"/api/v1/data/source-evidence/"+encodeURIComponent(id));
        check("edge_source_evidence_"+id,evidence.receipt.queryId===result.queryId && evidence.receipt.watermark===null && evidence.receipt.watermarkKind==="UNKNOWN");
      }
      await writeFile(file.replace(".json","-result.json"),result.raw,{flag:"wx"});
      state.latestQuery={query,queryId:result.queryId,resultHash:createHash("sha256").update(result.raw).digest("hex")};
      await save(state); report.status="PASS"; report.scope="DORIS_TWO_TABLE_QUERY";
    } else if (doris && ["s1-key-negative","s2-doris-null","s2-doris-fanout-negative","s2-doris-identity","s2-doris-cardinality"].includes(mode)) {
      const expectedIssue = {
        "s1-key-negative": "mapping_source_shape_invalid", "s2-doris-identity": "mapping_source_shape_invalid",
        "s2-doris-null": "mapping_relation_endpoint_unknown", "s2-doris-fanout-negative": "mapping_fanout_exceeded",
        "s2-doris-cardinality": "mapping_cardinality_conflict"
      }[mode];
      const fanout = mode === "s2-doris-fanout-negative";
      phase = fanout ? "fanout_assessment" : twoTable ? "null_relation_assessment" : "unsupported_identity_assessment";
      const requestBody = structuredClone(state.mappingCreate);
      const identity = requestBody.mapping.identitySpecs[0];
      if (expectedIssue === "mapping_source_shape_invalid") identity.externalIdFieldRefs = [{ ...identity.externalIdFieldRefs[0], name: "join_key", ordinal: 4 }];
      requestBody.command = command();
      const draft = await post(operator, "/api/v1/mappings", requestBody, 201);
      const invalidPath = "/api/v1/mappings/" + draft.mappingId;
      const startJob = await post(operator, invalidPath + "/validate", {target:{kind:"PUBLISH",draftRevision:draft.revision},command:command(draft.revision)}, 202,
        `"mapping:${draft.revision}"`);
      let rejected;
      for (let i = 0; i < 45; i++) {
        const job = await get(operator, "/api/v1/mapping-jobs/" + startJob.jobId);
        if (job.status === "SUCCEEDED") { rejected = await get(operator, "/api/v1/mapping-assessments/" + job.assessmentId); break; }
        check("negative_job_advances_" + i, ["QUEUED","RUNNING"].includes(job.status));
        await new Promise(done => setTimeout(done, 300));
      }
      check("unsupported_identity_never_publishable", rejected?.status === "BLOCKED" && rejected.issues.some(i => i.code === expectedIssue));
      const active = (await request(operator, "GET", invalidPath + "/active", undefined, 404)).data;
      check("unsupported_identity_has_no_activation", active.code === "mapping_active_missing");
      report.rejected = { mappingId:draft.mappingId, assessmentId:rejected.assessmentId, issues:rejected.issues.map(i => i.code), active };
      report.status="PASS"; report.scope=mode==="s2-doris-cardinality" ? "OVERLAPPING_PARENTS_REJECTED" : mode==="s2-doris-identity" ? "COLLIDING_IDENTITY_PLAN_REJECTED" : fanout ? "DORIS_FANOUT_TEN_ELEVEN" : twoTable ? "DORIS_NULL_RELATION_NEGATIVE" : "DORIS_IDENTITY_NEGATIVE";
    } else if (mode === "numeric") {
      phase = "numeric_formal_gateway";
      const capability = (await get(operator, "/api/v1/capabilities")).find(item => item.id === "g4_traverse_relationships");
      const query = { ...state.latestQuery.query, capabilityId: capability.id, capabilityVersion: capability.version,
        relationshipIris: ["urn:synthetic:mapping:hasReading"] };
      const result = await request({ ...operator, headers: { ...operator.headers, "Idempotency-Key": randomUUID() } }, "POST", "/api/v1/data/semantic-queries", query);
      await writeFile(file.replace(".json", "-relationships.json"), result.raw);
      const edges = result.data.data.filter(item => item.kind === "relationship");
      check("numeric_found_complete", result.data.status === "FOUND" && !result.data.limited);
      check("numeric_independent_expected_endpoints", JSON.stringify(edges.map(item => item.target.identity.externalId).sort()) === JSON.stringify(["numeric-target-1", "numeric-target-2"]));
      check("numeric_correct_source_and_scope", edges.every(item => item.source.identity.externalId === "asset-1" && item.source.identity.siteId === "site-a" && item.target.identity.siteId === "site-a"));
      for (const edge of edges) for (const id of edge.evidenceIds) {
        const evidence = await get(operator, "/api/v1/data/source-evidence/" + encodeURIComponent(id));
        check("numeric_evidence_resolvable_" + id, evidence.receipt.queryId === result.queryId && evidence.receipt.mappingReleaseId === state.mappingReceipt.mappingReleaseId);
      }
      const recovered = await request(operator, "GET", `/api/v1/data/semantic-queries/${result.queryId}/result`);
      check("numeric_canonical_recovery", recovered.raw === result.raw);
      state.numericResult = { queryId: result.queryId, resultHash: createHash("sha256").update(result.raw).digest("hex"), query };
      await save(state); report.status = "PASS"; report.scope = "RF01_RF03_REAL_PG_FORMAL_MAPPING_GATEWAY";
    } else if (mode === "s1-reopen") {
      phase = "query_after_api_restart";
      const original = state.numericResult ?? state.latestQuery ?? state.firstQuery;
      check("original_query_exists", Boolean(original));

      const count = row => doris ? row.businessQueries : row.seqScan + row.idxScan;
      await new Promise(done => setTimeout(done, 2100)); const before = observed();
      await new Promise(done => setTimeout(done, 1100)); const settled = observed();
      check("reopen_source_statistics_settled", count(before) === count(settled) && count(before) > 0);
      const restored = await request(reader, "GET", `/api/v1/data/semantic-queries/${original.queryId}/result`);
      check("new_api_process_decrypts_original_result", createHash("sha256").update(restored.raw).digest("hex") === original.resultHash);
      await new Promise(done => setTimeout(done, 2100)); const after = observed();
      await new Promise(done => setTimeout(done, 1100)); const confirmed = observed();
      report.sourceScans = { before, settled, after, confirmed };
      if (doris) check("same_doris_audit_file_and_queries", [settled,after,confirmed].every(value =>
        value.containerId === before.containerId && value.auditInode === before.auditInode && value.queryIdsSha256 === before.queryIdsSha256));
      check("restart_recovery_no_business_reread", count(before) === count(after) && count(after) === count(confirmed));
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
    } else if (mode === "s3") {
      const { execFileSync } = await import("node:child_process");
      const capabilities = await get(operator, "/api/v1/capabilities");
      const execute = async (id, overrides = {}) => {
        const capability = capabilities.find(item => item.id === id);
        check("s3_registered_" + id, Boolean(capability));
        const query = { ...state.latestQuery.query, capabilityId: id, capabilityVersion: capability.version, ...overrides };
        return request({ ...operator, headers: { ...operator.headers, "Idempotency-Key": randomUUID() } }, "POST", "/api/v1/data/semantic-queries", query);
      };
      phase = "s3_unknown_path_before_empty";
      const pathCapability = capabilities.find(item => item.id === "g4_traverse_relationships");
      await request({ ...operator, headers: { ...operator.headers, "Idempotency-Key": randomUUID() } }, "POST", "/api/v1/data/semantic-queries",
        { ...state.latestQuery.query, capabilityId: pathCapability.id, capabilityVersion: pathCapability.version,
          relationshipIris: ["urn:synthetic:mapping:unpublished"], filters: { entityExternalId: "missing-fixture-entity" } }, 422);
      phase = "s3_real_observations";
      const observations = await execute("g4_read_observations");
      await writeFile(file.replace(".json", "-observations.json"), observations.raw);
      const values = observations.data.data.filter(item => item.kind === "observation");
      check("s3_exact_kelvin_conversion", values.some(item => item.value.lexical === "293.2750" && item.unit?.unitIri === "urn:synthetic:m3:K-v1"));
      check("s3_registered_json_scalar", values.filter(item => item.propertyIri === "urn:synthetic:mapping:quality").every(item => item.value.type === "string" && item.value.lexical === "good"));
      check("s3_source_observed_microseconds", values.some(item => item.observedAtUtc === "2026-11-14T00:00:01.123456Z"));
      check("s3_independent_table_receipts", observations.data.subSources.length === 2 && new Set(observations.data.evidence.map(item => item.sourceReadReceiptId)).size === 2);
      check("s3_observations_recover_exact_bytes", (await request(operator, "GET", `/api/v1/data/semantic-queries/${observations.queryId}/result`)).raw === observations.raw);
      phase = "s3_real_relationships";
      const edges = await execute("g4_traverse_relationships", { relationshipIris: ["urn:synthetic:mapping:hasReading"] });
      await writeFile(file.replace(".json", "-relationships.json"), edges.raw);
      check("s3_published_relationship_endpoints", edges.data.data.filter(item => item.kind === "relationship").length === 2 && edges.data.data.filter(item => item.kind === "relationship").every(item => item.source.identity.siteId === "site-a" && item.target.identity.siteId === "site-a" && item.evidenceIds.length === 2));
      const rootLimited = await execute("g4_read_observations", { maxRows: 2 });
      const rootEvidenceId = rootLimited.data.data.find(item => item.kind === "entity").evidenceIds[0];
      const rootReceiptId = rootLimited.data.evidence.find(item => item.evidenceId === rootEvidenceId).sourceReadReceiptId;
      check("s3_root_observations_truncated_branch", rootLimited.data.status === "PARTIAL" && rootLimited.data.subSources.find(item => item.sourceReadReceiptId === rootReceiptId)?.limited);
      const rootEvidence = await request(operator, "GET", "/api/v1/data/source-evidence/" + encodeURIComponent(rootEvidenceId));
      check("s3_root_observations_truncated_receipt", rootEvidence.data.receipt.limited);
      const limited = await execute("g4_read_observations", { maxRows: 2 });
      check("s3_shared_row_budget_partial", limited.data.status === "PARTIAL" && limited.data.limited && limited.data.data.length === 2);
      const control = action => execFileSync("python3", ["-B", "-c", `import sys;sys.path.insert(0,"scripts/maintenance");import ${moduleName} as q;${scenarioCode}import json;print(json.dumps(q.query_fixture_control(sys.argv[1])))`, action], { cwd: root, timeout: 15000 });
      phase = "s3_independent_source_denial";
      control("readings-deny");
      try {
        const partial = await execute("g4_read_observations");
        check("s3_denied_child_preserves_root_only", partial.data.status === "PARTIAL" && partial.data.data.every(item => item.kind === "entity" || item.identity.sourceNamespace === "query-fixture-v1") && partial.data.subSources.some(item => item.status === "FORBIDDEN"));
      } finally { control("readings-allow"); }
      phase = "s3_real_source_and_response_budgets";
      try {
        const added = JSON.parse(JSON.parse(control("readings-budget-add").toString()).output);
        check("s3_source_has_101_rows", added.ownedRows === 99 && added.siteRows === 101);
        const budgeted = await execute("g4_read_observations");
        await writeFile(file.replace(".json", "-budget.json"), budgeted.raw);
        check("s3_real_byte_budget_keeps_prefix", budgeted.data.status === "PARTIAL" && budgeted.data.limited && budgeted.data.data.length > 1 && budgeted.data.data.length < 100 && Buffer.byteLength(budgeted.raw) <= 1024 * 1024);
        check("s3_real_read_limit_receipt", budgeted.data.subSources.some(item => item.limited && item.sourceReadReceiptId));
        check("s3_budget_evidence_closed", budgeted.data.data.every(item => item.evidenceIds.every(id => budgeted.data.evidence.some(evidence => evidence.evidenceId === id))));
        check("s3_budget_recovery_exact", (await request(operator, "GET", `/api/v1/data/semantic-queries/${budgeted.queryId}/result`)).raw === budgeted.raw);
      } finally {
        const removed = JSON.parse(JSON.parse(control("readings-budget-remove").toString()).output);
        check("s3_owned_budget_rows_removed", removed.ownedRows === 0 && removed.siteRows === 2);
      }
      phase = "s3_real_mcp";
      let rpcId = 0;
      const rpc = async (method, params) => {
        const reply = await request({ ...operator, headers: { ...operator.headers, Accept: "application/json, text/event-stream", "MCP-Protocol-Version": "2025-11-25" } }, "POST", "/api/v1/mcp", { jsonrpc: "2.0", id: ++rpcId, method, params });
        const payload = reply.data ?? JSON.parse(reply.raw.split("\n").find(line => line.startsWith("data:")).slice(5));
        check("s3_mcp_protocol_" + rpcId, !payload.error && payload.id === rpcId);
        return payload.result;
      };
      await rpc("initialize", { protocolVersion: "2025-11-25", capabilities: {}, clientInfo: { name: "m4-controlled-query", version: "1" } });
      const listed = await rpc("tools/list", {});
      check("s3_mcp_old_and_new_tool_closure", listed.tools.length === 7 && listed.tools.some(item => item.name === "describe_ontology") && listed.tools.some(item => item.name === "g4_query_result"));
      const legacy = await rpc("tools/call", { name: "describe_ontology", arguments: { assetId: state.ontologyRelease.manifest.assetId, releaseId: state.ontologyRelease.manifest.releaseId, depth: 1, maxRows: 100, timeoutMs: 5000 } });
      check("s3_legacy_mcp_executes_unchanged_contract", !legacy.isError && legacy.structuredContent.snapshot.releaseId === state.ontologyRelease.manifest.releaseId && !legacy.structuredContent.schemaVersion);
      const restored = await rpc("tools/call", { name: "g4_query_result", arguments: { queryId: observations.queryId } });
      check("s3_mcp_same_canonical_result", !restored.isError && restored.content.length === 1 && restored.content[0].text === observations.raw && JSON.stringify(restored.structuredContent) === JSON.stringify(JSON.parse(observations.raw)));
      const capability = capabilities.find(item => item.id === "g4_traverse_relationships");
      const called = await rpc("tools/call", { name: capability.id, arguments: { query: { ...state.latestQuery.query, capabilityId: capability.id, capabilityVersion: capability.version }, idempotencyKey: randomUUID(), selectionQueryId: null } });
      check("s3_mcp_executes_shared_gateway", !called.isError && called.structuredContent.data.some(item => item.kind === "relationship"));
      const rejected = await rpc("tools/call", { name: "g4_query_result", arguments: { queryId: observations.queryId, actor: operator.me.subjectId } });
      check("s3_mcp_rejects_client_identity", rejected.isError === true && !rejected.structuredContent && rejected.content.length === 1 && rejected.content[0].text === "semantic_tool_rejected");
      const duplicated = await request({ ...operator, headers: { ...operator.headers, Accept: "application/json, text/event-stream", "MCP-Protocol-Version": "2025-11-25" } }, "POST", "/api/v1/mcp",
        '{"jsonrpc":"2.0","id":999,"method":"tools/call","params":{"name":"g4_query_result","arguments":{"queryId":"missing","queryId":' + JSON.stringify(observations.queryId) + '}}}');
      const duplicatePayload = duplicated.data ?? JSON.parse(duplicated.raw.split("\n").find(line => line.startsWith("data:")).slice(5));
      check("s3_mcp_raw_duplicate_rejected", duplicatePayload.result.isError === true && !duplicatePayload.result.structuredContent && duplicatePayload.result.content[0].text === "semantic_tool_rejected");
      state.s3Results = { observationsQueryId: observations.queryId, relationshipsQueryId: edges.queryId }; await save(state);
      report.status = "PASS"; report.scope = "S3_REAL_PG_OBSERVATIONS_RELATIONSHIPS_PARTIAL_MCP";
    } else if (mode === "s2-inflight") {
      const { execFileSync } = await import("node:child_process");
      try { await heldQuery(operator, state.latestQuery.query, async () => {}, true); }
      finally { execFileSync("python3", ["-B", "-c", `import sys;sys.path.insert(0,"scripts/maintenance");import ${moduleName} as q;${scenarioCode}q.query_fixture_control("restore-execute")`], { cwd: root, timeout: 15000 }); }
      check("regrant_preserves_existing_result", createHash("sha256").update((await request(operator, "GET", `/api/v1/data/semantic-queries/${state.latestQuery.queryId}/result`)).raw).digest("hex") === state.latestQuery.resultHash);
      report.status = "PASS"; report.scope = "S2_REAL_INFLIGHT_GRANT_REVOCATION";
    } else if (["s2-aba", "s2-aba-prepare"].includes(mode)) {
      const path = "/api/v1/mappings/" + state.mappingDraft.mappingId;
      const capability = (await get(operator, "/api/v1/capabilities")).find(item => item.id === "g4_resolve_entity");
      const query = { ...state.latestQuery.query, capabilityId: capability.id, capabilityVersion: capability.version,
        ...(doris ? { relationshipIris: [], filters: { siteId: "site-a", entityExternalId: "E1" } } : { filters: { entityExternalId: "asset-1" } }) };
      const prepareOnly = mode === "s2-aba-prepare";
      let dorisBaseline;
      if (doris) {
        dorisBaseline = await get(activator,path+"/active");
        check("known_active_A",dorisBaseline.mappingReleaseId===state.mappingReceipt.mappingReleaseId &&
          dorisBaseline.manifestHash===state.mappingReceipt.manifestHash &&
          dorisBaseline.activationRevision===(state.mappingCurrentReceipt??state.mappingReceipt).activationRevision);
        if (state.s2AbaInFlight && (state.s2AbaInFlight.baselineRevision??state.mappingReceipt.activationRevision)!==dorisBaseline.activationRevision) {
          (state.previousAbaCases??=[]).push(state.s2AbaInFlight);
          delete state.s2AbaInFlight;
        }
        (state.s2AbaInFlight??={}).baselineRevision=dorisBaseline.activationRevision;
      }
      const aba = prepareOnly ? (state.s2AbaInFlight ??= {}) : (state.s2Aba ??= {});
      if (doris || !aba.original) {
        phase = "query_aba_original";
        const original = await request({ ...reader, headers: { ...reader.headers, "Idempotency-Key": randomUUID() } }, "POST", "/api/v1/data/semantic-queries", query);
        check("aba_original_qualified", original.data.status === (doris ? "FOUND" : "AMBIGUOUS"));
        aba.original = { queryId: original.queryId, resultHash: createHash("sha256").update(original.raw).digest("hex"), candidate: original.data.candidates[0], query }; await save(state);
      }
      const old = aba.original, selected = doris ? null : { ...old.query, filters: { ...old.query.filters, entityIri: old.candidate.entityIri, siteId: old.candidate.siteId } };
      async function checkHistory(label) {
        const original = await request(operator, "GET", `/api/v1/data/semantic-queries/${old.queryId}/result`);
        check(label + "_historical_bytes_unchanged", createHash("sha256").update(original.raw).digest("hex") === old.resultHash);
        await request({ ...operator, headers: { ...operator.headers, "Idempotency-Key": randomUUID(), "X-Selection-Query-Id": old.queryId } }, "POST", "/api/v1/data/semantic-queries", selected, 409);
      }
      async function activateRound(label, target, draft) {
        const round = aba[label] ??= {}; await save(state);
        if (!round.job) {
          phase = "query_aba_" + label + "_validate";
          round.validation ??= { target, command: command(draft.revision) }; await save(state);
          round.job = await post(operator, path + "/validate", round.validation, 202, `"mapping:${draft.revision}"`); await save(state);
        }
        if (!round.assessment) {
          for (let attempt = 0; attempt < 60; attempt++) {
            const job = await get(operator, "/api/v1/mapping-jobs/" + round.job.jobId);
            if (job.status === "SUCCEEDED") { round.assessment = await get(operator, "/api/v1/mapping-assessments/" + job.assessmentId); break; }
            check("aba_" + label + "_job_" + attempt, ["QUEUED", "RUNNING"].includes(job.status)); await new Promise(done => setTimeout(done, 300));
          }
          check("aba_" + label + "_ready", round.assessment?.status === "READY_FOR_PROPOSAL"); await save(state);
        }
        if (!round.proposal) {
          const assessment = round.assessment;
          round.proposalCommand ??= { kind: target.kind, schemaVersion: "g4.mapping.v1", scope: draft.scope,
            binding: assessment.binding, expectedActive: assessment.expectedActive, expiresAtUtc: assessment.expiresAtUtc,
            ...(target.kind === "PUBLISH" ? { draftId: draft.draftId, draftRevision: draft.revision } : { targetReleaseId: target.targetReleaseId, manifestHash: target.manifestHash }), command: command() }; await save(state);
          round.proposal = await post(operator, path + "/proposals", round.proposalCommand, 201); await save(state);
        }
        if (!round.approved) {
          const proposal = round.proposal;
          round.decision ??= { decision: "APPROVE", bindingHash: proposal.bindingHash, command: command(proposal.proposalRevision) }; await save(state);
          round.approved = await post(auditor, `/api/v1/mapping-proposals/${proposal.proposalId}/decisions`, round.decision, 200, `"proposal:${proposal.proposalRevision}"`); await save(state);
        }
        if (prepareOnly) return round.approved;
        if (!round.receipt) {
          phase = "query_aba_" + label + "_activate";
          const proposal = round.approved;
          round.activation ??= { bindingHash: proposal.bindingHash, expectedActive: proposal.expectedActive, command: command(proposal.proposalRevision) }; await save(state);
          round.receipt = await post(operator, `/api/v1/mapping-proposals/${proposal.proposalId}/activate`, round.activation, 200, `"proposal:${proposal.proposalRevision}"`); await save(state);
        }
        return round.receipt;
      }
      if (!aba.draftB) {
        phase = "query_aba_edit_b";
        const current = await get(operator, path), mapping = structuredClone(current.mapping);
        mapping.identitySpecs[0].sourceNamespace = doris ? "query-fixture-aba-b-" + dorisBaseline.activationRevision : "query-fixture-aba-b";
        aba.patch ??= { mapping, command: command(current.revision) }; await save(state);
        aba.draftB = (await request(operator, "PATCH", path, aba.patch, 200, `"mapping:${current.revision}"`)).data; await save(state);
      }
      const b = await activateRound("b", { kind: "PUBLISH", draftRevision: aba.draftB.revision }, aba.draftB);
      if (prepareOnly) {
        check("inflight_b_approved_without_activation", b.status === "APPROVED" && !aba.b.receipt);
        if (doris) {
          const baseline = await get(activator, path + "/active");
          check("original_A_still_active", baseline.mappingReleaseId === state.mappingReceipt.mappingReleaseId && baseline.manifestHash === state.mappingReceipt.manifestHash && baseline.activationRevision === dorisBaseline.activationRevision);
          if (prepareShape) {
            state.shapePreparation = { approved: b, baseline };
            await save(state);
            report.shapePreparation = {proposalId:b.proposalId,baseline};
            report.status="PASS"; report.scope="DORIS_APPROVED_BEFORE_SHAPE_CHANGE";
            return;
          }
          const envelope = { queryId: aba.original.queryId, proposalId: b.proposalId,
            roles: [[operator,"A"],[auditor,"B"],[activator,"C"],[reader,"Q"]].map(([actor,role]) => ({ role, subjectId: actor.me.subjectId, cookie: actor.sessionCookie })) };
          const result = execFileSync("python3", ["-B", "scripts/maintenance/workflow_doris_s1.py", "aba-test"], {
            cwd: root, input: JSON.stringify(envelope), timeout: 40000, encoding: "utf8", stdio: ["pipe","pipe","pipe"] });
          report.aba = JSON.parse(result);
          const active = await get(activator, path + "/active");
          check("same_release_distinct_new_activation", active.mappingReleaseId === baseline.mappingReleaseId &&
            active.manifestHash === baseline.manifestHash && active.activationRevision === baseline.activationRevision + 2);
          state.mappingCurrentReceipt = active;
          await save(state);
          report.status = "PASS"; report.scope = "DORIS_INFLIGHT_ABA";
        } else {
          report.status = "PASS"; report.scope = "S2_INFLIGHT_ABA_PREPARATION_ONLY";
        }
        return;
      }
      check("aba_b_is_distinct_release", b.mappingReleaseId !== state.mappingReceipt.mappingReleaseId);
      if (!aba.a?.receipt) await checkHistory("while_b_active");
      const a = await activateRound("a", { kind: "ROLLBACK", targetReleaseId: state.mappingReceipt.mappingReleaseId, manifestHash: state.mappingRelease.manifestHash }, aba.draftB);
      check("aba_same_release_new_activation", a.mappingReleaseId === state.mappingReceipt.mappingReleaseId
        && a.activationId !== state.mappingReceipt.activationId && a.activationRevision > b.activationRevision && b.activationRevision > state.mappingReceipt.activationRevision);
      await checkHistory("after_aba");
      const fresh = await request({ ...operator, headers: { ...operator.headers, "Idempotency-Key": randomUUID() } }, "POST", "/api/v1/data/semantic-queries", query);
      check("aba_fresh_query_uses_new_activation", fresh.data.status === "AMBIGUOUS" && fresh.queryId !== old.queryId);
      const proof = await get(operator, "/api/v1/data/source-evidence/" + encodeURIComponent(fresh.data.evidence[0].evidenceId));
      check("aba_evidence_binds_new_activation", proof.receipt.activationId === a.activationId && proof.receipt.activationRevision === String(a.activationRevision));
      state.mappingCurrentReceipt = a; await save(state);
      report.status = "PASS"; report.scope = "S2_REAL_MAPPING_A_B_A_HISTORY_AND_SELECTION_BINDING";
    } else if (mode === "s2-connection") {
      const path = `/api/v1/connections/${state.connectionId}`;
      const queryPath = `/api/v1/data/semantic-queries/${state.latestQuery.queryId}/result`;
      let current = await request(operator, "GET", path);
      state.s2Connection ??= { initial: current.data }; await save(state);
      const steps = state.s2Connection;
      phase = "query_connection_baseline";
      check("rotation_baseline_recoverable", createHash("sha256").update((await request(operator, "GET", queryPath)).raw).digest("hex") === state.latestQuery.resultHash);
      check("rotation_starts_from_active_connection", current.data.state === "ACTIVE");
      phase = "query_connection_secret_rotated";
      const secretValue = await readFile(resolve(privateRoot, "pg-source/reader-password"), "utf8"); secrets.push(secretValue);
      const secret = await post(operator, "/api/v1/connection-secrets", { secretValue, scopeSelection: state.scope, purpose: "POSTGRESQL_READONLY", command: command() }, 201);
      secrets.push(secret.secretRef);
      const rotated = await post(operator, path + "/rotate-secret", { secretRef: secret.secretRef, command: command(current.data.configRevision) }, 200, current.etag);
      check("secret_version_really_advanced", rotated.secretVersion > steps.initial.secretVersion && rotated.configRevision > steps.initial.configRevision);
      steps.rotated = rotated; await save(state);
      await request(operator, "GET", queryPath, undefined, 403);
      phase = "query_connection_restore_current_access";
      current = await request(operator, "GET", path);
      const probe = await post(operator, path + "/test", { command: command(current.data.configRevision) }, 200, current.etag);
      check("current_secret_real_tls_probe", probe.status === "TEST_OK");
      current = await request(operator, "GET", path);
      await post(operator, path + "/enable", { command: command(current.data.configRevision) }, 200, current.etag);
      const restored = await request(operator, "GET", queryPath);
      check("history_recovery_checks_new_secret_and_keeps_old_bytes", createHash("sha256").update(restored.raw).digest("hex") === state.latestQuery.resultHash);
      await request({ ...operator, headers: { ...operator.headers, "Idempotency-Key": randomUUID() } }, "POST", "/api/v1/data/semantic-queries", state.latestQuery.query, 409);
      phase = "query_connection_terminal_disable";
      current = await request(operator, "GET", path);
      await post(operator, path + "/disable", { command: command(current.data.configRevision) }, 200, current.etag);
      await request(operator, "GET", queryPath, undefined, 403);
      steps.disabledDenied = true;
      steps.current = (await request(operator, "GET", path)).data; await save(state);
      report.status = "PASS"; report.scope = "S2_ROTATED_CURRENT_RECOVERY_NEW_EXECUTION_STALE_AND_TERMINAL_DISABLE";
    } else if (["s2-runtime", "s2-race", "s2-capacity"].includes(mode)) {
      const { execFile, spawn } = await import("node:child_process");
      const control = (action, value = "") => new Promise((resolveControl, rejectControl) => execFile("python3", ["-B", "-c",
        `import sys,json;sys.path.insert(0,"scripts/maintenance");import ${moduleName} as q;${scenarioCode}print(json.dumps(q.query_fixture_control(sys.argv[1],sys.argv[2] or None)))`, action, value],
        { cwd: root, timeout: 15000, encoding: "utf8" }, (error, stdout) => error ? rejectControl(new Error("query_fixture_control_failed")) : resolveControl(JSON.parse(stdout))));
      const sourceBarrier = async () => {
        const child = spawn("python3", ["-B", "-c", `import sys;sys.path.insert(0,"scripts/maintenance");import ${moduleName} as q;${scenarioCode}q.query_source_barrier()`], { cwd: root, stdio: ["ignore", "pipe", "pipe"] });
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
      const secondary = { ...operator, apiOrigin: `http://localhost:${port(15448)}` };
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
      const watcher = spawn("python3", ["-B", "-c", `import sys;sys.path.insert(0,"scripts/maintenance");import ${moduleName} as q;${scenarioCode}q.query_admission_watch(sys.argv[1])`, key], { cwd: root, stdio: ["ignore", "pipe", "pipe"] });
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
        if (mode === "s2-capacity") {
          await execute(secondary, randomUUID(), 429);
          const finished = await running;
          if (finished.error) throw finished.error;
          check("capacity_denial_does_not_cancel_first_query", finished.value.status === 200 && finished.value.data.status === "UNAVAILABLE");
        } else {
        const cancelled = await request(secondary, "POST", `/api/v1/data/semantic-queries/${id}/cancel`);
        check("second_api_commits_cancel", cancelled.data.executionStatus === "CANCELLED");
        const finished = await running;
        if (finished.error) throw finished.error;
        check("first_api_late_response_rejected", [409, 503].includes(finished.value.status));
        const after = JSON.parse((await control("query-probe", key)).output);
        check("late_worker_cannot_commit_completed", after.status === "CANCELLED" && after.cancel === true);
        await request(operator, "GET", `/api/v1/data/semantic-queries/${id}/result`, undefined, 409);
        }
      } finally { check("cancel_source_barrier_released", await barrier); await found; }
      if (mode !== "s2-capacity") {
      phase = "query_source_timeout";
      const { finished: fault } = await sourceBarrier();
      try {
        const unavailable = await execute();
        check("real_source_lock_timeout_never_empty", unavailable.data.status === "UNAVAILABLE" && unavailable.data.data.length === 0
          && unavailable.data.candidates.length === 0 && unavailable.data.subSources.every(item => item.status !== "EMPTY"));
      } finally { check("timeout_source_barrier_released", await fault); }
      }
      report.status = "PASS"; report.scope = mode === "s2-capacity" ? "S2_CROSS_API_ACTOR_CAPACITY" : mode === "s2-race" ? "S2_CROSS_API_CANCEL_SOURCE_FAILURE" : "S2_CURRENT_GRANTS_SOURCE_ACL_CROSS_API_CANCEL_SOURCE_FAILURE";
    } else if (mode === "provision") {
      if (doris && state.mappingJob && !state.mappingReceipt && !state.dorisUnitFixtureRevision) {
        const job = await get(operator, "/api/v1/mapping-jobs/" + state.mappingJob.jobId);
        const rejected = await get(operator, "/api/v1/mapping-assessments/" + job.assessmentId);
        check("previous_unit_validation_blocked", rejected.status === "BLOCKED" && rejected.issues.some(i => i.code === "mapping_unit_unknown"));
        await writeFile(resolve(output, "s1-unit-rejection-" + rejected.assessmentId + ".json"), JSON.stringify({ state, rejected }, null, 2), { flag: "wx" });
        for (const key of Object.keys(state)) if (key.startsWith("ontology") || key.startsWith("mapping")) delete state[key];
        state.dorisUnitFixtureRevision = 1;
        await save(state);
      }
      if (!state.ontologyDraft) {
        phase = "g3_create";
        const sources = {};
        for (const name of ["ontology", "shapes", "vocabulary", "data"]) sources[name + "Turtle"] = await readFile(resolve(root, "samples/g2", name + ".ttl"), "utf8");
        sources.ontologyTurtle += '\n<urn:synthetic:mapping:Asset> a <http://www.w3.org/2002/07/owl#Class> .\n'
          + '<urn:synthetic:mapping:label> a <http://www.w3.org/2002/07/owl#DatatypeProperty>; <http://www.w3.org/2000/01/rdf-schema#domain> <urn:synthetic:mapping:Asset>; <http://www.w3.org/2000/01/rdf-schema#range> <http://www.w3.org/2001/XMLSchema#string> .\n';
        if (doris) {
          sources.vocabularyTurtle += "\n" + await readFile(resolve(root, "samples/g3-m3/units.ttl"), "utf8");
          sources.ontologyTurtle += `
@prefix m: <urn:synthetic:mapping:> .
@prefix u: <urn:synthetic:m3:> .
@prefix p: <urn:ontology-platform:semantics:> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
m:amount a owl:DatatypeProperty; rdfs:domain m:Asset; rdfs:range xsd:decimal;
  p:nominalUnit u:K-v1; p:dimension u:temperature; p:quantityKind u:Temperature .
m:Reading a owl:Class .
m:hasReading a owl:ObjectProperty; rdfs:domain m:Asset; rdfs:range m:Reading .
`;
        }
        if (state.s3) {
          sources.vocabularyTurtle += "\n" + await readFile(resolve(root, "samples/g3-m3/units.ttl"), "utf8");
          sources.ontologyTurtle += `
@prefix m: <urn:synthetic:mapping:> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
m:Reading a owl:Class .
m:label2 a owl:DatatypeProperty; rdfs:domain m:Asset; rdfs:range xsd:string .
m:quality a owl:DatatypeProperty; rdfs:domain m:Reading; rdfs:range xsd:string .
<urn:synthetic:m3:reading> rdfs:domain m:Reading; rdfs:range xsd:decimal .
m:hasReading a owl:ObjectProperty; rdfs:domain m:Asset; rdfs:range m:Reading .
`;
        }
        state.ontologyDraft = await post(operator, "/api/v1/ontology-drafts", { name: doris ? "Doris 合成温度量与关系词汇" : "Synthetic M4 query vocabulary", scope: state.scope, sources, baseReleaseId: null, command: command() }); await save(state);
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
        const existing = (await get(operator, "/api/v1/connections")).items.filter(value => value.displayName === (state.connectionDisplayName ?? "M4 synthetic PostgreSQL query"));
        check("resume_connection_unambiguous", existing.length <= 1);
        if (existing.length === 1) { state.connectionId = existing[0].id; await save(state); }
      }
      if (!state.connectionId) {
        phase = "pg_connection_create";
        const password = await readFile(doris ? resolve(privateRoot, "../implementation-01-source/reader.pass") : resolve(privateRoot, "pg-source/reader-password"), "utf8"); secrets.push(password);
        const secret = await post(operator, "/api/v1/connection-secrets", { secretValue: password, scopeSelection: state.scope, purpose: doris ? "DORIS_READONLY" : "POSTGRESQL_READONLY", command: command() }, 201);
        secrets.push(secret.secretRef);
        const config = doris ? { type: "DORIS", profile: { feHost: "localhost", queryPort: 19030, catalog: "internal", database: "fixture", username: "fixture_reader", tls: true } } : { type: "POSTGRESQL", profile: { host: "pg-source", port: 5432, database: "fixture", username: "fixture_reader", sslMode: "VerifyFull", allowedSchemas: ["production", "public"] } };
        const connection = await post(operator, "/api/v1/connections", { displayName: state.connectionDisplayName ?? "M4 synthetic PostgreSQL query", scopeSelection: state.scope, config, secretRef: secret.secretRef, command: command() }, 201);
        state.connectionId = connection.id; await save(state);
      }
      const connectionPath = `/api/v1/connections/${state.connectionId}`;
      let current = await request(operator, "GET", connectionPath);
      if (!current.data.probeFresh) {
        phase = (doris ? "doris_tls_readonly_probe" : "pg_tls_readonly_probe");
        const probe = await post(operator, connectionPath + "/test", { command: command(current.data.configRevision) }, 200, current.etag);
        check((doris ? "doris_real_probe" : "pg_real_probe"), probe.status === "TEST_OK");
        current = await request(operator, "GET", connectionPath);
      }
      if (current.data.state !== "ACTIVE") {
        phase = (doris ? "doris_enable" : "pg_enable");
        await post(operator, connectionPath + "/enable", { command: command(current.data.configRevision) }, 200, current.etag);
      }
      if (!state.catalog) {
        phase = (doris ? "doris_catalog" : "pg_catalog"); current = await request(operator, "GET", connectionPath);
        const job = await post(operator, connectionPath + "/discoveries", { command: command(current.data.configRevision) }, 202, current.etag);
        for (let attempt = 0; attempt < 30; attempt++) {
          const progress = await get(operator, connectionPath + "/discoveries/" + job.jobId);
          if (progress.status === "SUCCEEDED") { state.catalog = await get(operator, "/api/v1/catalogs/" + progress.snapshotId); break; }
          check((doris ? "doris_job_nonfailure_" : "pg_job_nonfailure_") + attempt, ["QUEUED", "RUNNING"].includes(progress.status));
          await new Promise(done => setTimeout(done, 500));
        }
        check((doris ? "doris_catalog_ready" : "pg_catalog_ready"), state.catalog?.status === "READY"); await save(state);
      }
      report.status = "PASS";
      if (twoTable && state.credentialRotation?.reset) {
        const prior=state.credentialRotation;
        check("new_catalog_bound_to_rotated_version",state.catalog.connectionId===prior.connectionId &&
          state.catalog.snapshotId!==prior.snapshot && state.catalog.secretVersion===prior.version+1);
        const historic=await request(reader,"GET","/api/v1/data/semantic-queries/"+prior.originalQueryId+"/result");
        check("rotated_current_access_restores_original_bytes",createHash("sha256").update(historic.raw).digest("hex")===prior.originalResultHash);
        report.catalogRecovery={connectionId:prior.connectionId,oldSnapshot:prior.snapshot,newSnapshot:state.catalog.snapshotId,version:state.catalog.secretVersion};
      }
      report.scope = doris ? "G3_RELEASE_AND_DORIS_DISCOVERY" : "G3_FORMAL_RELEASE_AND_PG_CATALOG_ONLY";

    } else if (mode === "mapping") {
      check("formal_prerequisites", Boolean(state.catalog && state.ontologyRelease));
      const sourceTable = name => doris ? (name === "assets" ? "dmq_entity" : "dmq_target") : state.numeric ? "numeric_" + name : name;
      const dataset = { snapshotId: state.catalog.snapshotId, schema: doris ? "fixture" : "production", name: sourceTable("assets"), kind: "TABLE" };
      const table = state.catalog.objects.find(value => value.schema === dataset.schema && value.name === sourceTable("assets"));
      const field = input => {
        const name = doris ? ({organization_id:"org_id",asset_id:"entity_id",label:"amount"}[input] ?? input) : input;
        return { datasetRef: dataset, name, ordinal: table.fields.find(value => value.name === name).ordinal };
      };
      const definition = { entities: [{ id: "asset", entityClassIri: "urn:synthetic:mapping:Asset", datasetRef: dataset,
        identitySpecId: "asset-identity", temporalSpecId: "asset-time", scopeFields: { organization: field("organization_id"), site: field("site_id") } }],
        identitySpecs: [{ id: "asset-identity", organizationFieldRef: field("organization_id"), siteFieldRef: field("site_id"), sourceNamespace: "query-fixture-v1",
          externalIdFieldRefs: [field("asset_id")], validFromFieldRef: field("valid_from"), validToFieldRef: field("valid_to") }],
        temporalSpecs: [{ id: "asset-time", eventTimeFieldRef: field("valid_from"), observedAtFieldRef: field("valid_from"),
          validFromFieldRef: field("valid_from"), validToFieldRef: field("valid_to"), timezonePolicy: { kind: "UTC", zoneId: null }, precision: "MICROSECOND" }],
        properties: [{ id: "label", entityBindingId: "asset", propertyIri: "urn:synthetic:mapping:label", fieldRef: field("label"), conversionId: null, unitSpecId: null, nullPolicy: "REJECT_NULL" }],
        relations: [], conversions: [], unitSpecs: [] };
      if (doris) {
        definition.properties[0] = { ...definition.properties[0], id: "amount", propertyIri:"urn:synthetic:mapping:amount", unitSpecId:"amount-k", conversionId:"amount-identity" };
        definition.unitSpecs = [{ id: "amount-k", sourceUnitIri: "urn:synthetic:m3:K-v1", targetUnitIri: "urn:synthetic:m3:K-v1",
          sourceUnitFieldRef: field("unit_code"), sourceUnitCode: "K", unitRegistryVersion: "1", evidenceKind: "SOURCE_FIELD" }];
        definition.conversions = [{ id: "amount-identity", registeredId: "identity", version: "1", parameters: {} }];
        definition.temporalSpecs[0].eventTimeFieldRef = field("event_at");
        definition.temporalSpecs[0].observedAtFieldRef = field("observed_at");
        definition.temporalSpecs[0].timezonePolicy = {kind:"REGISTERED_ZONE", zoneId:"Etc/UTC"};
      }
      if (twoTable) {
        const target = state.catalog.objects.find(t => t.name === "dmq_target" && t.schema === "fixture");
        const targetRef = { ...dataset, name:"dmq_target" };
        const col = name => ({datasetRef:targetRef,name,ordinal:target.fields.find(f => f.name === name).ordinal});
        definition.entities.push({id:"target",entityClassIri:"urn:synthetic:mapping:Reading",datasetRef:targetRef,
          identitySpecId:"target-key",temporalSpecId:"target-time",scopeFields:{organization:col("org_id"),site:col("site_id")}});
        definition.identitySpecs.push({id:"target-key",organizationFieldRef:col("org_id"),siteFieldRef:col("site_id"),sourceNamespace:"dmq-target-v1",
          externalIdFieldRefs:[col("target_id")],validFromFieldRef:col("valid_from"),validToFieldRef:col("valid_to")});
        definition.temporalSpecs.push({id:"target-time",eventTimeFieldRef:col("event_at"),observedAtFieldRef:col("observed_at"),
          validFromFieldRef:col("valid_from"),validToFieldRef:col("valid_to"),timezonePolicy:{kind:"REGISTERED_ZONE",zoneId:"Etc/UTC"},precision:"MICROSECOND"});
        definition.relations=[{id:"targets",fromBindingId:"asset",toBindingId:"target",predicateIri:"urn:synthetic:mapping:hasReading",
          cardinality:"ONE_TO_MANY",temporalJoinPolicy:"HALF_OPEN_OVERLAP",joinFieldPairs:[{from:field("join_key"),to:col("join_key")}]}];
      }
      if (state.s3) {
      definition.properties.push({ id: "label2", entityBindingId: "asset", propertyIri: "urn:synthetic:mapping:label2", fieldRef: field("label"), conversionId: null, unitSpecId: null, nullPolicy: "REJECT_NULL" });
      const ref = (table, name) => ({ datasetRef: { snapshotId: state.catalog.snapshotId, schema: "production", name: sourceTable(table), kind: "TABLE" },
        name, ordinal: state.catalog.objects.find(item => item.name === sourceTable(table)).fields.find(field => field.name === name).ordinal });
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
      definition.relations = [{ id: "readings", fromBindingId: "asset", toBindingId: "reading", predicateIri: "urn:synthetic:mapping:hasReading", cardinality: "ONE_TO_MANY", temporalJoinPolicy: "HALF_OPEN_OVERLAP", joinFieldPairs: [{ from: ref("assets", state.numeric ? "numeric_key" : "asset_id"), to: ref("readings", state.numeric ? "numeric_key" : "asset_id") }] }];
      }
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
        state.mappingReceipt = await post(activator, `/api/v1/mapping-proposals/${proposal.proposalId}/activate`, state.mappingActivation, 200, `"proposal:${proposal.proposalRevision}"`); await save(state);
      }
      state.mappingRelease = await get(operator, "/api/v1/mapping-releases/" + state.mappingReceipt.mappingReleaseId); await save(state);
      check("query_mapping_original", state.mappingRelease.manifest.mapping.entities.length === (state.s3 || twoTable ? 2 : 1) && state.mappingRelease.manifest.mapping.entities[0].datasetRef.snapshotId === state.catalog.snapshotId);
      report.status = "PASS"; report.scope = "M4_QUERY_FIXED_MAPPING_PREREQUISITE_ONLY";
    } else if (mode === "s1") {
      phase = "query_capability";
      const capability = (await get(reader, "/api/v1/capabilities")).find(item => item.id === "g4_resolve_entity");
      check("g4_registered_capability", Boolean(capability && state.mappingRelease));
      const query = { assetId: state.ontologyRelease.manifest.assetId, ontologyReleaseId: state.ontologyRelease.manifest.releaseId,
        mappingReleaseIds: [state.mappingReceipt.mappingReleaseId], capabilityId: capability.id, capabilityVersion: capability.version,
        relationshipIris: [], depth: 1, maxRows: 100, timeoutMs: 5000, filters: { siteId: "site-a", entityExternalId: doris ? "E1" : "asset-1" } };
      const beforeDoris = doris ? observed() : null;
      phase = "query_default_zero_grant";
      const denied = await request({ ...auditor, headers: { ...auditor.headers, "Idempotency-Key": randomUUID() } }, "POST", "/api/v1/data/semantic-queries", query);
      check("default_zero_data_grant", denied.data?.status === "UNAUTHORIZED" && denied.data.data.length === 0 && denied.data.evidence.length === 0);
      check("denied_no_store", denied.cacheControl === "no-store");
      phase = "query_first_real_pg";
      const key = randomUUID(), writer = { ...reader, headers: { ...reader.headers, "Idempotency-Key": key } };
      const first = await request(writer, "POST", "/api/v1/data/semantic-queries", query);
      check(doris ? "real_doris_found" : "real_pg_found", first.data?.status === "FOUND" && first.data.data.length === 1 && first.data.data[0].kind === "entity");
      if (doris) {
        const amount = first.data.data[0].properties.find(p => p.propertyIri === "urn:synthetic:mapping:amount");
        check("doris_amount_exact", amount?.value.type === "decimal" && amount.value.lexical === "9007199254740993.20" && amount.value.precision === 20 && amount.value.scale === 2);
        check("doris_kelvin_source_evidence", amount.unit.unitIri === "urn:synthetic:m3:K-v1" && amount.unit.source === "SOURCE_FIELD" && amount.unit.evidenceIds.length > 0);
        check("doris_event_microseconds", amount.eventTime.lexical === "2026-11-17T12:00:00.123456Z");
        check("doris_unknown_data_watermark", first.data.subSources[0].watermarkKind === "UNKNOWN");
      }
      check("actual_query_reference", /^query-[0-9a-f]{32}$/.test(first.queryId));
      check("real_source_receipt", first.data.subSources.length === 1 && first.data.subSources[0].status === "SUCCESS" && first.data.subSources[0].sourceReadReceiptId);
      check("precise_identity_evidence", first.data.evidence.length > 0 && first.data.evidence.every(item => item.precision === "ROW_KEY" && item.sourceRecordRef && !Object.hasOwn(item, "graphIri")));
      check("real_scope_projection", first.data.data[0].identity.siteId === "site-a" && first.data.data[0].identity.externalId === (doris ? "E1" : "asset-1"));
      check("completed_no_store", first.cacheControl === "no-store");
      phase = "query_restore_exact_bytes";
      const restored = await request(reader, "GET", `/api/v1/data/semantic-queries/${first.queryId}/result`);
      check("restore_exact_canonical_bytes", restored.raw === first.raw);
      const replay = await request(writer, "POST", "/api/v1/data/semantic-queries", query);
      check("idempotency_same_reference_and_bytes", replay.queryId === first.queryId && replay.raw === first.raw);
      await request(writer, "POST", "/api/v1/data/semantic-queries", { ...query, maxRows: 99 }, 409);
      await request(auditor, "GET", `/api/v1/data/semantic-queries/${first.queryId}/result`, undefined, 404);
      phase = "query_source_evidence";
      const evidence = await get(reader, "/api/v1/data/source-evidence/" + encodeURIComponent(first.data.evidence[0].evidenceId));
      check("real_evidence_chain", evidence.schemaVersion === "g4.source-evidence.v1" && evidence.receipt.queryId === first.queryId
        && evidence.receipt.mappingReleaseId === state.mappingReceipt.mappingReleaseId && evidence.receipt.activationId === (state.mappingCurrentReceipt ?? state.mappingReceipt).activationId);
      check("no_internal_binding", !Object.hasOwn(evidence.receipt, "configHash") && !Object.hasOwn(evidence.receipt, "secretVersion") && !Object.hasOwn(evidence.receipt, "binding"));
      await writeFile(file.replace(".json", "-result.json"), first.raw, { flag: "wx" });
      state.latestQuery = { actor: { subjectId: reader.me.subjectId, organizationId: reader.me.scopes[0].organizationId,
        siteIds: reader.me.scopes.map(scope => scope.siteId), roles: reader.me.roles.filter(role => ["platform.viewer", "platform.operator", "platform.auditor"].includes(role)), traceId: randomUUID().replaceAll("-", ""), correlationId: randomUUID().replaceAll("-", "") }, queryId: first.queryId, query, idempotencyKey: key, resultHash: createHash("sha256").update(first.raw).digest("hex") };
      if (doris) {
        await new Promise(done => setTimeout(done, 1600));
        const after = observed();
        report.sourceQueryControl = { before: beforeDoris, after };
        check("exactly_one_doris_business_read", beforeDoris.auditInode === after.auditInode &&
          beforeDoris.queryIdsSha256 !== after.queryIdsSha256 && after.businessQueries === beforeDoris.businessQueries + 1);
      }
      state.firstQuery ??= state.latestQuery; await save(state);
      report.status = "PASS"; report.scope = doris ? "S1_DORIS_OIDC_QUERY_PERSISTENCE" : "S1_REAL_OIDC_FORMAL_MAPPING_PG_QUERY_RESTORE_EVIDENCE_HTTP";
    } else if (mode === "ui-s3") {
      phase = "s3_ui_observations";
      await operator.page.goto(origin + "/analysis");
      await operator.page.getByRole("button", { name: "查询业务源", exact: true }).waitFor();
      await operator.page.getByLabel("源查询本体资产", { exact: true }).fill(state.ontologyRelease.manifest.assetId);
      await operator.page.getByLabel("源查询本体发布", { exact: true }).fill(state.ontologyRelease.manifest.releaseId);
      await operator.page.getByLabel("源查询映射发布", { exact: true }).fill(state.mappingReceipt.mappingReleaseId);
      await operator.page.getByLabel("源查询外部号", { exact: true }).fill("asset-1");
      await operator.page.getByLabel("源查询厂区", { exact: true }).selectOption("site-a");
      for (const capability of ["g4_read_observations", "g4_traverse_relationships"]) {
        await operator.page.getByLabel("业务源查询能力", { exact: true }).selectOption(capability);
        await operator.page.getByLabel("源查询关系路径", { exact: true }).fill("urn:synthetic:mapping:hasReading");
        const pending = operator.page.waitForResponse(response => response.url() === origin + "/api/v1/data/semantic-queries" && response.request().method() === "POST");
        await operator.page.getByRole("button", { name: "查询业务源", exact: true }).click();
        const response = await pending, result = await response.json();
        check("s3_ui_actual_" + capability, response.status() === 200 && result.status === "FOUND" && result.data.some(item => item.kind === (capability === "g4_read_observations" ? "observation" : "relationship")));
        const region = operator.page.getByRole("region", { name: "业务源查询结果", exact: true });
        await region.getByRole("heading", { name: "FOUND · 找到可信结果", exact: true }).waitFor();
        check("s3_ui_renders_" + capability, (await region.innerText()).includes(capability === "g4_read_observations" ? "293.2750" : "hasReading"));
        await region.screenshot({ path: file.replace(".json", "-" + capability + ".png") });
      }
      await operator.page.setViewportSize({ width: 390, height: 844 });
      await operator.page.waitForFunction(() => document.querySelector("#platform-navigation")?.getBoundingClientRect().right <= 0);
      check("s3_mobile_no_overflow", await operator.page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      await operator.page.getByRole("region", { name: "业务源查询", exact: true }).screenshot({ path: file.replace(".json", "-mobile.png") });
      report.status = "PASS"; report.scope = "S3_REAL_BROWSER_OBSERVATIONS_RELATIONSHIPS";
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

      const count = row => doris ? row.businessQueries : row.seqScan + row.idxScan;
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
