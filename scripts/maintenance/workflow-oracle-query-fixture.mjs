import { spawn, execFileSync } from "node:child_process";
import { createInterface } from "node:readline";
import { readFileSync } from "node:fs";
import { randomUUID } from "node:crypto";

/** 只有任务已冻结的主 API、副 API、OIDC 和 Web 可以被正式浏览器场景访问。 */
export const ports = Object.freeze({ api: 15741, secondary: 15742, oidc: 15743, web: 15744 });
export const modes = Object.freeze(["s2-s3-oracle", "s2-oracle-vocabulary", "s2-oracle-mapping", "s2-oracle-queries", "s2-oracle-relations", "s2-oracle-access", "s2-oracle-aba", "s2-oracle-connection", "s2-oracle-versions", "s2-oracle-states", "s2-oracle-reopen", "s3", "ui-s3", "ui-s1", "auth-handoff-s1", "reader-auth", "serve", "provision", "mapping", "s0-oracle-auth", "s0-oracle-ready", "s0-oracle-natural", "s0-oracle-cancel", "s0-oracle-natural-cancel", "s1", "s1-reopen"]);
export const config = Object.freeze({ type: "ORACLE", profile: { host: "oracle-source", port: 2484, serviceName: "FREEPDB1",
  username: "FIXTURE_READER", allowedOwners: ["PRODUCTION", "CaseOwner"], tls: true } });
const task = "G4-ORACLE-MAPPING-QUERY-001";
export const productResume = process.env.OMQ_PRODUCT_RUN === "product-resume-01";
if (process.env.OMQ_PRODUCT_RUN !== undefined && !productResume) throw new Error("ORACLE_PRODUCT_RUN");
export const runId = productResume ? "product-resume-01" : "implementation-01";
// 四个已封存的正常登录主体。当前 /me 必须由当前的正式登录重新取得。
const subjects = Object.freeze({
  "operator-ab": "5af20722-3900-4de9-b23a-7dcae3ca5927", "auditor-ab": "650199ae-8bd4-430a-885d-71cd69b6781e",
  "operator-a": "bcf7f7f8-6af0-4f94-a28c-1220461ee62e", "viewer-a": "f902a743-7079-4e22-a643-a51deb027e89",
});
export function originalSubject(label) {
  if (!Object.hasOwn(subjects, label)) throw new Error("ORACLE_OIDC_SUBJECT");
  return subjects[label];
}
function loginFailure(code) {
  return Object.assign(new Error(code), { safeCode: code });
}

export function currentProjection(label, me) {
  const role = label === "auditor-ab" ? "platform.auditor" : label === "viewer-a" ? "platform.viewer" : "platform.operator";
  const sites = label.endsWith("-ab") ? ["site-a", "site-b"] : ["site-a"];
  return me?.subjectId === originalSubject(label) && me.roles?.length === 1 && me.roles[0] === role
    && Array.isArray(me.scopes) && me.scopes.length === sites.length
    && sites.every(site => me.scopes.some(s => s.organizationId === "org-demo" && s.siteId === site));
}

// 只返回固定分类。浏览器中的授权码、认证表单和页面正文均不离开页面。
export function loginOutcome({ issuer, api, realm }) {
  if (location.origin === api && location.pathname === "/api/v1/platform/me") return "CALLBACK";
  if (location.origin === issuer && location.pathname.startsWith(realm + "/")) {
    const feedback = document.querySelectorAll('[id^="input-error"], #kc-feedback-text, .alert-error, [role=alert]');
    if ([...feedback].some(node => /invalid username or password|invalid user credentials|用户名或密码(错误|无效)|无效的用户名或密码/i.test(node.textContent ?? "")))
      return "ORACLE_LOGIN_CREDENTIALS_REJECTED";
    if (document.querySelector("#kc-error-message")) return "ORACLE_LOGIN_CALLBACK_ERROR";
    return false;
  }
  if (location.origin === api && location.pathname === "/signin-oidc" && !new URLSearchParams(location.search).has("error")) return false;
  return "ORACLE_LOGIN_CALLBACK_ERROR";
}
/** 当前业务阶段只消费原单调截止，外部调用不能另起完整预算。 */
export function stageRemaining(deadline = Infinity) {
  const remaining = deadline - performance.now();
  if (!(remaining > 0)) throw loginFailure("ORACLE_STAGE_TIMEOUT");
  return Number.isFinite(remaining) ? Math.max(1, Math.floor(remaining)) : 30000;
}

/** 单调截止由首次可交互表单建立；提交后网络预算不重新发放。 */
export function loginRemaining(deadline, now = () => performance.now()) {
  const remaining = deadline - now();
  if (!(remaining > 0)) throw loginFailure("ORACLE_LOGIN_SUBMITTED_TIMEOUT");
  return Math.max(1, Math.floor(remaining));
}

/** 替代卷只提交公开用户名；只观察核准表单的请求元数据，不读取密码或请求体。 */
export async function completeCurrentLogin(page, label, options = {}) {
  originalSubject(label);
  const now = options.now ?? (() => performance.now());
  const wait = options.wait ?? (ms => new Promise(done => setTimeout(done, ms)));
  const window = options.window ?? { deadline: null, durationMs: 600000 };
  const issuer = "http://localhost:" + ports.oidc, api = "http://localhost:" + ports.api;
  const realm = "/realms/g2-180e1435711f03fa";
  const address = new URL(page.url());
  if (address.origin !== issuer || !address.pathname.startsWith(realm + "/")) throw loginFailure("ORACLE_RESTORED_REALM");
  const observation = { label, submitted: false, classification: "UNKNOWN", startedAtUtc: new Date().toISOString() };
  let submittedAt, handedAt, deadline;
  const onRequest = request => {
    const url = new URL(request.url());
    if (request.method() === "POST" && request.frame() === page.mainFrame()
        && url.origin === issuer && url.pathname === realm + "/login-actions/authenticate" && submittedAt === undefined) {
      submittedAt = now(); deadline = Math.min(window.deadline, submittedAt + 40000);
      observation.submitted = true; observation.submittedAtUtc = new Date().toISOString();
      options.onProgress?.({ event: "SUBMITTED", label });
    }
  };
  const finish = classification => {
    observation.classification = classification;
    observation.finishedAtUtc = new Date().toISOString();
    observation.humanWaitMs = Math.max(0, (submittedAt ?? now()) - (handedAt ?? now()));
    observation.networkMs = submittedAt === undefined ? 0 : Math.max(0, now() - submittedAt);
    return observation;
  };
  try {
    await page.locator("#username").fill("g2-" + label);
    await page.locator("#password").waitFor({ state: "visible", timeout: 15000 });
    if (!(await page.locator("#password").isEnabled()) || !(await page.locator("#kc-login").isEnabled()))
      throw loginFailure("ORACLE_LOGIN_FORM_NOT_INTERACTIVE");
    const valid = await page.evaluate(({ issuer, realm, username }) => {
      const user = document.querySelector("#username"), password = document.querySelector("#password");
      const form = user?.form, button = document.querySelector("#kc-login");
      if (!form || password?.form !== form || button?.form !== form || user.value !== username
          || button.hasAttribute("formaction") || button.hasAttribute("formmethod")) return false;
      const action = new URL(form.action);
      return location.origin === issuer && location.pathname.startsWith(realm + "/")
        && action.origin === issuer && action.pathname === realm + "/login-actions/authenticate" && form.method.toLowerCase() === "post";
    }, { issuer, realm, username: "g2-" + label });
    if (!valid) throw loginFailure("ORACLE_LOGIN_FORM_MISMATCH");
    handedAt = now();
    window.deadline ??= Math.min(handedAt + window.durationMs, window.maxDeadline ?? Infinity);
    deadline = window.deadline;
    page.on("request", onRequest);
    await page.bringToFront(); await page.locator("#password").focus();
    observation.handoffAtUtc = new Date().toISOString();
    observation.windowRemainingMs = Math.max(0, deadline - handedAt);
    options.onProgress?.({ event: "FORM_INTERACTIVE", label, remainingSeconds: Math.floor((deadline - now()) / 1000),
      entry: label === "operator-ab" ? "operator-reset-01-20261120" : "040700Z" });
    while (true) {
      if (options.signal?.aborted || page.isClosed()) throw loginFailure("ORACLE_LOGIN_CANCELLED");
      if (now() >= deadline) throw loginFailure(submittedAt === undefined ? "ORACLE_LOGIN_WAITING_FOR_INPUT" : "ORACLE_LOGIN_SUBMITTED_TIMEOUT");
      let outcome;
      try { outcome = await page.evaluate(loginOutcome, { issuer, api, realm }); }
      catch (error) {
        if (!String(error.message).includes("Execution context was destroyed")) throw error;
      }
      if (outcome === "CALLBACK") {
        if (submittedAt === undefined) throw loginFailure("ORACLE_LOGIN_SUBMISSION_UNKNOWN");
        loginRemaining(deadline, now);
        return { deadline, observation, finish, remaining: () => loginRemaining(deadline, now) };
      }
      if (outcome) throw loginFailure(outcome);
      await wait(Math.min(100, Math.max(1, deadline - now())));
    }
  } catch (error) {
    if (!error.safeCode) error.safeCode = "ORACLE_LOGIN_UNKNOWN";
    error.loginObservation = finish(error.safeCode);
    throw error;
  } finally { page.off("request", onRequest); }
}

/** 唯一本批固定计划，由 Python 生产者和资格消费者读取同一原件。 */
export const authPlan = Object.freeze(JSON.parse(readFileSync(new URL("./workflow-oracle-auth-plan.json", import.meta.url), "utf8")));

/** 同一个浏览器与内存 actors 串行推进；失败、取消或越期立即阻止下一阶段。 */
export const s2Plan = Object.freeze(JSON.parse(readFileSync(new URL("./workflow-oracle-s2-plan.json", import.meta.url), "utf8")));

export async function runAuthHandoffPlan(shared, runStage, now = () => performance.now()) {
  const plan = shared.plan ?? authPlan;
  shared.plan = plan;
  shared.stages = [];
  for (const [index, spec] of plan.stages.entries()) {
    if (shared.signal?.aborted) throw loginFailure("ORACLE_LOGIN_CANCELLED");
    shared.stageSpec = { ...spec, index };
    shared.stageStart = now(); shared.stageDeadline = shared.stageStart + spec.seconds * 1000;
    if (spec.kind === "authentication") shared.loginWindow = { deadline: null, durationMs: spec.seconds * 1000, maxDeadline: shared.stageDeadline };
    const result = await runStage(spec.mode, shared);
    shared.stages.push(result);
    if (result.status !== "PASS" || result.failure || now() > shared.stageDeadline) return false;
  }
  return true;
}

const columns = ["ROW_ID", "JOIN_KEY", "VAL", "ORG_ID", "SITE_ID", "EXT_ID", "LABEL", "FROM_TS", "TO_TS", "EVENT_TS", "OBSERVED_TS"];

/** 由准确快照确认列序再生成权限范围；本阶段正式根只授权实体表。 */
export function projection(catalog, connectionId) {
  if (catalog?.status !== "READY" || catalog.connectionId !== connectionId || catalog.objects.length !== 2) throw new Error("ORACLE_CATALOG");
  for (const [owner, name] of [["PRODUCTION","OMQ_ENTITY"], ["CaseOwner","OmqTarget"]]) {
    const table = catalog.objects.find(t => t.schema === owner && t.name === name && t.kind === "TABLE");
    if (table?.fields.length !== columns.length || !columns.every((name, i) => table.fields[i].name === name && table.fields[i].ordinal === i + 1))
      throw new Error("ORACLE_COLUMNS");
  }
  const object = "PRODUCTION/OMQ_ENTITY";
  return { objects: [object], fields: columns.map((name, i) => object + "/" + (i + 1) + "/" + name) };
}

/** 仅把授权/就绪检查所需的固定公开身份送给同任务的平台夹具。 */
export function grantState(state) {
  return { taskId: task, runId, scope: state.scope, subjects: state.subjects, connectionId: state.connectionId, catalog: state.catalog,
    mappingReceipt: state.mappingReceipt, mappingCurrentReceipt: state.mappingCurrentReceipt, combinedGrantIds: state.combinedGrantIds, mappingRelease: state.mappingRelease && { manifest: { binding: state.mappingRelease.manifest.binding } } };
}

/** 调用平台真实事务与只读采样；Python 异常正文不进入浏览器报告。 */
export function platform(root, call, input, deadline) {
  const code = 'import sys,json;sys.path.insert(0,"scripts/maintenance");import workflow_oracle_mapping_platform as q;print(json.dumps(' + call + '))';
  return JSON.parse(execFileSync("python3", ["-B", "-c", code], { cwd: root, input: JSON.stringify(input),
    encoding: "utf8", timeout: Math.min(30000, stageRemaining(deadline)), stdio: ["pipe","pipe","pipe"] }));
}

/** 纯认证入口只把已有 Cookie 经私有 stdin 传给正式四票据消费者。 */
export function authSessions(root, actors, deadline) {
  const input = actors.map(actor => ({ subjectId: actor.me.subjectId, cookie: actor.sessionCookie }));
  try { return platform(root, "q.session_preflight(json.load(sys.stdin),210)", input, deadline); }
  catch (error) {
    throw loginFailure(sessionRejection(error.stderr));
  }
}

export function sessionRejection(stderr) {
  const match = /^ValueError: ORACLE_ADMISSION_(OMQ_SESSION_(?:SUBJECT_MISMATCH|TTL_INSUFFICIENT|REVOKED|TICKET_UNAVAILABLE))_[a-f0-9]{32}$/m.exec(String(stderr));
  return match?.[1] ?? "ORACLE_LOGIN_SESSION_PROBE_FAILED";
}

/** 沿既有 grant_transaction 真实签发并回读；过期原件不能靠同一 ID 覆盖。 */
export function grants(root, state, mode) {
  const { objects, fields } = projection(state.catalog, state.connectionId);
  const row = platform(root, "q.grant_fixture(*json.load(sys.stdin))", [mode, objects, fields, grantState(state)]);
  if (row.taskId !== task || row.runId !== runId || row.mode !== mode || !row.commandId || row.inputsUnchanged !== true
      || row.grantCount !== (mode === "query" ? 3 : 12) || row.fieldCount !== 11 || !(row.remainingSeconds > 0))
    throw new Error("ORACLE_GRANT_READBACK");
  return row;
}

/** 认证落盘后才检查原15项授权；仅自然到期原范围可追加四小时记录。 */
export function batchGrants(root, state, executionId, deadline) {
  return platform(root, "q.batch_grants(*json.load(sys.stdin))", [grantState(state), executionId], deadline);
}

/** 每一正式长场景在同次登录中重读当前目录、激活和源夹具，而非使用旧缓存。 */
export async function ready({ root, state, operator, reader, get, check, mode, actors, deadline }) {
  const connection = await get(operator, "/api/v1/connections/" + state.connectionId);
  const catalog = await get(operator, "/api/v1/catalogs/" + state.catalog.snapshotId);
  const active = await get(operator, "/api/v1/mappings/" + state.mappingDraft.mappingId + "/active");
  const binding = state.mappingRelease.manifest.binding;
  check("oracle_ready_catalog_projection", projection(catalog, state.connectionId).fields.length === 11
    && catalog.snapshotId === state.catalog.snapshotId && catalog.schemaFingerprint === state.catalog.schemaFingerprint);
  check("oracle_ready_current_connection", connection.state === "ACTIVE" && connection.configRevision === binding.connectionRevision
    && connection.secretVersion === binding.secretVersion && binding.sourceConnectionId === state.connectionId
    && binding.sourceCatalogSnapshotId === catalog.snapshotId && binding.sourceCatalogFingerprint === catalog.schemaFingerprint);
  check("oracle_ready_closed_versions", binding.sourceType === "ORACLE" && binding.adapterVersion === "oracle-mapping-v1"
    && binding.executorVersion === "oracle-mapping-validator-v1" && binding.canonicalVersion === "mapping-c14n-v1");
  check("oracle_ready_current_activation", active.mappingId === state.mappingReceipt.mappingId && active.mappingReleaseId === state.mappingReceipt.mappingReleaseId
    && active.activationRevision === state.mappingReceipt.activationRevision && active.manifestHash === state.mappingReceipt.manifestHash);
  const capability = (await get(reader, "/api/v1/capabilities")).find(c => c.id === "g4_resolve_entity");
  check("oracle_capability_registered", Boolean(capability?.version));
  // 原会话只进只读平台检查的私有 stdin；报告仅接收非秘密观察。
  const row = platform(root, "q.ready_fixture(json.load(sys.stdin))", { ...grantState(state), mode, actors:
    actors.map(a => ({ subjectId: a.me.subjectId, cookie: a.sessionCookie })) }, deadline);
  check("oracle_current_source_and_grants", row.taskId === task && row.runId === runId && row.status === "READY" && row.commandId
    && row.fieldCount === 11 && row.grantCount === 3 && row.requiredSeconds > 0 && row.remainingSeconds >= row.requiredSeconds && (mode === "s1-reopen" ? row.fixtureBefore === null : typeof row.fixtureBefore === "object" && row.fixtureBefore !== null));
  return { capability, row };
}

/** 宿主与资源先核定身份。Ports 与已冻结端口不合便终止，阻止旧栈被调用。 */
export function checkBinding(binding) {
  const api = binding.api;
  if (api?.taskId !== task || api.runId !== runId || !api.commandId || !Object.entries(ports).every(([role, value]) => api.ports?.[role] === value))
    throw new Error("ORACLE_HOST_PORT_BINDING");
  if (productResume && (!/^[0-9a-f]{64}$/.test(api.resourceManifestSha256) || !api.services?.["api-secondary"]))
    throw new Error("ORACLE_RESUME_HOST_BINDING");
}

/** 两次独立 inspect 有各自回执，其他环境字段必须逐一相同。 */
export function sameHost(before, after) {
  if (!before?.api?.commandId || !after?.api?.commandId || before.api.commandId === after.api.commandId) return false;
  const stable = item => {
    const { commandId, ...api } = item.api;
    return { ...item, api };
  };
  return JSON.stringify(stable(before)) === JSON.stringify(stable(after));
}

/** 先启动同任务只读观测者，再用相同 Q 从两个正式 API 提交执行与取消。 */
export async function witness({ root, state, reader, mode, capability, get, request, check, report, deadline }) {
  const naturalRace = mode === "s0-oracle-natural-cancel";
  const cancel = mode === "s0-oracle-cancel" || naturalRace;
  const secondary = { ...reader, apiOrigin: "http://localhost:" + ports.secondary };
  check("oracle_second_api_same_actor", (await get(secondary, "/api/v1/platform/me")).subjectId === reader.me.subjectId);
  const key = randomUUID();
  const output = "formal-witness-" + key + ".json";
  const query = { assetId: state.ontologyRelease.manifest.assetId, ontologyReleaseId: state.ontologyRelease.manifest.releaseId,
    mappingReleaseIds: [state.mappingReceipt.mappingReleaseId], capabilityId: capability.id, capabilityVersion: capability.version,
    relationshipIris: [], depth: 1, maxRows: 100, timeoutMs: 5000, filters: { siteId: "site-a", entityExternalId: "omq-entity-1" } };
  const process = spawn("python3", ["-B", "scripts/maintenance/workflow_oracle_mapping_platform.py", "observe",
    "--idempotency-key", key, "--output", output, ...(naturalRace ? ["--natural-return"] : [])], { cwd: root, timeout: Math.min(25000, stageRemaining(deadline)), killSignal: "SIGTERM", stdio: [naturalRace ? "pipe" : "ignore","pipe","ignore"] });
  const exit = new Promise(resolve => { process.once("error", () => resolve(-1)); process.once("close", code => resolve(code)); });
  const lines = createInterface({ input: process.stdout })[Symbol.asyncIterator]();
  const next = async () => {
    const value = await lines.next();
    if (value.done || value.value.length > 16384) throw new Error("ORACLE_OBSERVER_STREAM");
    return JSON.parse(value.value);
  };
  let running;
  report.oracleWitness = { output, idempotencyKey: key, events: [] };
  try {
    check("oracle_observer_armed", (await next()).status === "READY");
    const begin = performance.now();
    running = request({ ...reader, headers: { ...reader.headers, "Idempotency-Key": key } }, "POST",
      "/api/v1/data/semantic-queries", query, [200,403,409,422,429,503,504])
      .then(value => ({ value, elapsedMs: performance.now() - begin }), error => ({ error }));
    const admitted = await next();
    check("oracle_platform_admission", admitted.status === "ADMITTED" && /^query-[0-9a-f]{32}$/.test(admitted.queryId));
    report.oracleWitness.events.push({ status: admitted.status, queryId: admitted.queryId });
    if (naturalRace) {
      const returned = await next();
      check("oracle_natural_return_trigger", returned.status === "NATURAL_RETURN" && returned.queryId === admitted.queryId);
      report.oracleWitness.events.push(returned);
    }
    if (cancel) {
      const issued = Date.now();
      const response = await request(secondary, "POST", "/api/v1/data/semantic-queries/" + admitted.queryId + "/cancel", undefined, [200,403,409,503,504]);
      report.oracleWitness.cancel = { issuedUtc: new Date(issued).toISOString(), httpStatus: response.status, executionStatus: response.data?.executionStatus, code: response.data?.code, observedUtc: new Date().toISOString() };
      if (naturalRace) process.stdin.end(JSON.stringify({status: "CANCEL_OBSERVED",queryId: admitted.queryId,httpStatus: response.status}) + "\n");
    }
    let active, final;
    for (let i = 0; i < 2; i++) {
      const event = await next();
      if (event.status === "ACTIVE" && !active) active = event;
      else if (event.status === "FINAL") { final = event; break; }
      else throw new Error("ORACLE_OBSERVER_ORDER");
    }
    const result = await running;
    if (result.error) throw result.error;
    report.oracleWitness.execute = { status: result.value.status, queryStatus: result.value.data?.status, elapsedMs: result.elapsedMs };
    // 完整观测由独立工具保存原件。报告只取受审指标与关联身份。
    const publicFields = ["status","queryId","clientId","naturalCompletion","formalCancelCommitted","sameExecutionActiveAtCommit",
      "naturalSuccessWon","successCleanupUpperMs","naturalCompletionBeforeCancel","naturalCleanupUpperMs","earliestCleanupMarginMs","nativeCancelCausedTermination","allSourceWorkEnded","nativeErrorCode","deadlineOrDisconnectBeforeCommit","cleanupUpperMs",
      "branchUpperMs","totalUpperMs","successfulResults","successReceipts","successAudits","residualSourceWork","slotReleased"];
    report.oracleWitness.final = Object.fromEntries(publicFields.filter(field => final && Object.hasOwn(final, field)).map(field => [field, final[field]]));
    check("oracle_witness_finished", await exit === 0 && final?.queryId === admitted.queryId && /^[0-9a-f]{32}$/.test(final.clientId)
      && (active ? active.queryId === admitted.queryId && final.clientId === active.clientId : !cancel || naturalRace));
    check("oracle_native_and_platform_budgets", final.allSourceWorkEnded === true && final.residualSourceWork === 0
      && [final.branchUpperMs, final.totalUpperMs].every(ms => Number.isFinite(ms) && ms >= 0)
      && final.branchUpperMs <= 1000 && final.totalUpperMs <= 5000 && result.elapsedMs <= 5000 && final.slotReleased === true);
    if (naturalRace && final.naturalSuccessWon === true) {
      check("oracle_success_won_cancel_conflict", report.oracleWitness.cancel.httpStatus === 409
        && report.oracleWitness.cancel.code === "query_already_finished" && result.value.status === 200 && result.value.data?.status === "FOUND"
        && final.naturalCompletion === true && final.nativeErrorCode === 0 && final.formalCancelCommitted === false
        && final.nativeCancelCausedTermination === false && final.successfulResults === 1 && final.successReceipts === 1 && final.successAudits === 1);
      check("oracle_success_owned_cleanup", Number.isFinite(final.successCleanupUpperMs) && final.successCleanupUpperMs >= 0
        && final.successCleanupUpperMs <= 250 && Number.isFinite(final.earliestCleanupMarginMs) && final.earliestCleanupMarginMs >= 0);
    } else if (naturalRace) {
      check("oracle_late_platform_cancel", report.oracleWitness.cancel.httpStatus === 200 && report.oracleWitness.cancel.executionStatus === "CANCELLED"
        && final.formalCancelCommitted === true && final.sameExecutionActiveAtCommit === false && final.nativeCancelCausedTermination === false);
      check("oracle_natural_end_before_cancel", final.naturalCompletionBeforeCancel === true && Number.isFinite(final.naturalCleanupUpperMs)
        && final.naturalCleanupUpperMs >= 0 && final.naturalCleanupUpperMs <= 250
        && Number.isFinite(final.earliestCleanupMarginMs) && final.earliestCleanupMarginMs >= 0);
      check("oracle_zero_success_side_effects", [409,503,504].includes(result.value.status) && final.successfulResults === 0 && final.successReceipts === 0 && final.successAudits === 0);
    } else if (cancel) {
      check("oracle_formal_cancel_committed", report.oracleWitness.cancel.httpStatus === 200 && report.oracleWitness.cancel.executionStatus === "CANCELLED"
        && final.formalCancelCommitted === true && final.sameExecutionActiveAtCommit === true);
      check("oracle_native_cancel_causality", final.nativeCancelCausedTermination === true && final.nativeErrorCode === 1013
        && final.deadlineOrDisconnectBeforeCommit === false && Number.isFinite(final.cleanupUpperMs) && final.cleanupUpperMs >= 0 && final.cleanupUpperMs <= 250);
      check("oracle_zero_success_side_effects", [409,503,504].includes(result.value.status) && final.successfulResults === 0 && final.successReceipts === 0 && final.successAudits === 0);
    } else {
      check("oracle_natural_completion", result.value.status === 200 && result.value.data?.status === "FOUND" && final.naturalCompletion === true
        && final.nativeErrorCode === 0 && final.formalCancelCommitted === false && final.nativeCancelCausedTermination === false);
    }
  } finally {
    if (running) await running;
    await exit;
  }
}

/** 新批次固定双表闭包，旧单表projection仍保留原来的严格十一列。 */
export function combinedProjection(catalog, connectionId) {
  projection(catalog, connectionId);
  const objects = ["PRODUCTION/OMQ_ENTITY", "CaseOwner/OmqTarget"];
  return { objects, fields: objects.flatMap(object => columns.map((name, i) => object + "/" + (i + 1) + "/" + name)) };
}

/** 只能调用本任务白名单函数，正文通过私有stdin；执行预算来自当前阶段。 */
export function s2Call(root, method, values, deadline) {
  if (!["grants", "ready", "source_case", "source_snapshot", "permission_case", "await_expiry", "access_case", "runtime_case"].includes(method)) throw new Error("ORACLE_S2_CALL");
  return platform(root, "__import__('workflow_oracle_mapping_s2')." + method + "(*json.load(sys.stdin))", values, deadline);
}
