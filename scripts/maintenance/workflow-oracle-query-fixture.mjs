import { spawn, execFileSync } from "node:child_process";
import { createInterface } from "node:readline";
import { randomUUID } from "node:crypto";

/** 只有任务已冻结的主 API、副 API、OIDC 和 Web 可以被正式浏览器场景访问。 */
export const ports = Object.freeze({ api: 15741, secondary: 15742, oidc: 15743, web: 15744 });
export const modes = Object.freeze(["serve", "provision", "mapping", "s0-oracle-auth", "s0-oracle-ready", "s0-oracle-natural", "s0-oracle-cancel", "s0-oracle-natural-cancel", "s1", "s1-reopen"]);
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
    const feedback = document.querySelector("#input-error, #kc-feedback-text, .alert-error, [role=alert]");
    if (/invalid username or password|invalid user credentials|用户名或密码(错误|无效)|无效的用户名或密码/i.test(feedback?.textContent ?? ""))
      return "ORACLE_LOGIN_CREDENTIALS_REJECTED";
    if (document.querySelector("#kc-error-message")) return "ORACLE_LOGIN_CALLBACK_ERROR";
    return false;
  }
  if (location.origin === api && location.pathname === "/signin-oidc" && !new URLSearchParams(location.search).has("error")) return false;
  return "ORACLE_LOGIN_CALLBACK_ERROR";
}
/** 替代卷上走正式 OIDC 表单。只传入公开用户名，密码由本机系统或操作者提交。 */
export async function completeCurrentLogin(page, label) {
  originalSubject(label);
  const callback = url => url.origin === "http://localhost:" + ports.api && url.pathname === "/api/v1/platform/me";
  const address = new URL(page.url());
  const deadline = Date.now() + 40000;
  if (!callback(address)) {
    if (address.origin !== "http://localhost:" + ports.oidc || !address.pathname.startsWith("/realms/g2-180e1435711f03fa/"))
      throw loginFailure("ORACLE_RESTORED_REALM");
    const username = "g2-" + label;
    await page.locator("#username").fill(username);
    await page.bringToFront();
    // 仅让浏览器提交它已自动填充的准确账号。脚本不取密码字段的值。
    await page.locator("#password").focus();
    const filled = page.locator('input#password[type="password"]:-webkit-autofill');
    try {
      await filled.waitFor({ state: "visible", timeout: 2000 });
    } catch (error) {
      if (error.name !== "TimeoutError") throw error;
    }
    if (await filled.count()) {
      await filled.evaluate((input, expected) => {
        const form = input.form;
        const submit = form?.querySelector("#kc-login");
        if (!submit || submit.form !== form || submit.hasAttribute("formaction") || submit.hasAttribute("formmethod") ||
            form.querySelector("#username")?.value !== expected.username) return;
        const action = new URL(form.action);
        if (location.origin === expected.origin && location.pathname.startsWith("/realms/g2-180e1435711f03fa/") &&
            action.origin === expected.origin &&
            action.pathname === "/realms/g2-180e1435711f03fa/login-actions/authenticate" &&
            form.method.toLowerCase() === "post" && input.matches(":-webkit-autofill")) form.requestSubmit(submit);
      }, { username, origin: address.origin }, { timeout: Math.max(1, deadline - Date.now()) });
    }
  }
  // 跨导航观察同一正常认证；明确拒绝即结束，未填写只消耗本次短窗口。
  try {
    const result = await page.waitForFunction(loginOutcome, { issuer: "http://localhost:" + ports.oidc,
      api: "http://localhost:" + ports.api, realm: "/realms/g2-180e1435711f03fa" },
      { polling: 100, timeout: Math.max(1, deadline - Date.now()) });
    const outcome = await result.jsonValue();
    if (outcome !== "CALLBACK") throw loginFailure(outcome);
  } catch (error) {
    if (error.name !== "TimeoutError") throw error;
    throw loginFailure(new URL(page.url()).origin === "http://localhost:" + ports.oidc
      ? "ORACLE_LOGIN_WAITING_FOR_INPUT" : "ORACLE_LOGIN_CALLBACK_ERROR");
  }
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
function grantState(state) {
  return { taskId: task, runId, scope: state.scope, subjects: state.subjects, connectionId: state.connectionId, catalog: state.catalog,
    mappingReceipt: state.mappingReceipt, mappingRelease: state.mappingRelease && { manifest: { binding: state.mappingRelease.manifest.binding } } };
}

/** 调用平台真实事务与只读采样；Python 异常正文不进入浏览器报告。 */
function platform(root, call, input) {
  const code = 'import sys,json;sys.path.insert(0,"scripts/maintenance");import workflow_oracle_mapping_platform as q;print(json.dumps(' + call + '))';
  return JSON.parse(execFileSync("python3", ["-B", "-c", code], { cwd: root, input: JSON.stringify(input),
    encoding: "utf8", timeout: 30000, stdio: ["pipe","pipe","pipe"] }));
}

/** 纯认证入口只把已有 Cookie 经私有 stdin 传给正式四票据消费者。 */
export function authSessions(root, actors) {
  const input = actors.map(actor => ({ subjectId: actor.me.subjectId, cookie: actor.sessionCookie }));
  try { return platform(root, "q.session_preflight(json.load(sys.stdin),210)", input); }
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

/** 每一正式长场景在同次登录中重读当前目录、激活和源夹具，而非使用旧缓存。 */
export async function ready({ root, state, operator, reader, get, check, mode, actors }) {
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
    actors.map(a => ({ subjectId: a.me.subjectId, cookie: a.sessionCookie })) });
  check("oracle_current_source_and_grants", row.taskId === task && row.runId === runId && row.status === "READY" && row.commandId
    && row.fieldCount === 11 && row.grantCount === 3 && row.requiredSeconds > 0 && row.remainingSeconds >= row.requiredSeconds && typeof row.fixtureBefore === "object" && row.fixtureBefore !== null);
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
export async function witness({ root, state, reader, mode, capability, get, request, check, report }) {
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
    "--idempotency-key", key, "--output", output], { cwd: root, timeout: 25000, killSignal: "SIGTERM", stdio: ["ignore","pipe","ignore"] });
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
    if (cancel) {
      const issued = Date.now();
      const response = await request(secondary, "POST", "/api/v1/data/semantic-queries/" + admitted.queryId + "/cancel", undefined, [200,403,409,503,504]);
      report.oracleWitness.cancel = { issuedUtc: new Date(issued).toISOString(), httpStatus: response.status, executionStatus: response.data?.executionStatus };
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
      "naturalCompletionBeforeCancel","naturalCleanupUpperMs","earliestCleanupMarginMs","nativeCancelCausedTermination","allSourceWorkEnded","nativeErrorCode","deadlineOrDisconnectBeforeCommit","cleanupUpperMs",
      "branchUpperMs","totalUpperMs","successfulResults","successReceipts","successAudits","residualSourceWork","slotReleased"];
    report.oracleWitness.final = Object.fromEntries(publicFields.filter(field => final && Object.hasOwn(final, field)).map(field => [field, final[field]]));
    check("oracle_witness_finished", await exit === 0 && final?.queryId === admitted.queryId && /^[0-9a-f]{32}$/.test(final.clientId)
      && (active ? active.queryId === admitted.queryId && final.clientId === active.clientId : !cancel || naturalRace));
    check("oracle_native_and_platform_budgets", final.allSourceWorkEnded === true && final.residualSourceWork === 0
      && [final.branchUpperMs, final.totalUpperMs].every(ms => Number.isFinite(ms) && ms >= 0)
      && final.branchUpperMs <= 1000 && final.totalUpperMs <= 5000 && result.elapsedMs <= 5000 && final.slotReleased === true);
    if (naturalRace) {
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
