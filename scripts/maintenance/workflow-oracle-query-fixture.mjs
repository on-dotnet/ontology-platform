import { spawn, execFileSync } from "node:child_process";
import { createInterface } from "node:readline";
import { randomUUID } from "node:crypto";

/** 只有任务已冻结的主 API、副 API、OIDC 和 Web 可以被正式浏览器场景访问。 */
export const ports = Object.freeze({ api: 15741, secondary: 15742, oidc: 15743, web: 15744 });
export const modes = Object.freeze(["serve", "provision", "mapping", "s0-oracle-ready", "s0-oracle-natural", "s0-oracle-cancel", "s0-oracle-natural-cancel", "s1"]);
export const config = Object.freeze({ type: "ORACLE", profile: { host: "oracle-source", port: 2484, serviceName: "FREEPDB1",
  username: "FIXTURE_READER", allowedOwners: ["PRODUCTION", "CaseOwner"], tls: true } });
const task = "G4-ORACLE-MAPPING-QUERY-001";
const runId = "implementation-01";
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
      "naturalCompletionBeforeCancel","naturalCleanupUpperMs","nativeCancelCausedTermination","allSourceWorkEnded","nativeErrorCode","deadlineOrDisconnectBeforeCommit","cleanupUpperMs",
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
        && final.naturalCleanupUpperMs >= 0 && final.naturalCleanupUpperMs <= 250);
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
