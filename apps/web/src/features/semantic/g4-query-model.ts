import type { G4QueryCandidate, G4QueryResultV1, G4QueryValue, G4QueryView } from "../../lib/api/g4-generated";

/** 完整实体IRI区分同厂区、同外部号但有效身份不同的候选。 */
export function displayQueryCandidate(candidate: G4QueryCandidate): string {
  return `${candidate.label} · ${candidate.externalId} · ${candidate.organizationId}/${candidate.siteId} · ${candidate.entityIri}`;
}

/** 页面离开立即清除敏感状态；恢复必须先失效旧代次，再核验当前身份。 */
export function bindQuerySessionBoundary(windowEvents: EventTarget, documentEvents: EventTarget & { readonly visibilityState: string },
  invalidate: () => void, verify: () => void): () => void {
  const resume = () => { invalidate(); if (documentEvents.visibilityState === "visible") verify(); };
  const visibility = () => documentEvents.visibilityState === "hidden" ? invalidate() : resume();
  const restored = (event: Event) => { if ((event as PageTransitionEvent).persisted) resume(); };
  windowEvents.addEventListener("blur", invalidate);
  windowEvents.addEventListener("pagehide", invalidate);
  windowEvents.addEventListener("focus", resume);
  windowEvents.addEventListener("pageshow", restored);
  documentEvents.addEventListener("visibilitychange", visibility);
  return () => {
    windowEvents.removeEventListener("blur", invalidate);
    windowEvents.removeEventListener("pagehide", invalidate);
    windowEvents.removeEventListener("focus", resume);
    windowEvents.removeEventListener("pageshow", restored);
    documentEvents.removeEventListener("visibilitychange", visibility);
  };
}

/** 执行状态与业务结果分开，运行中不会被解释成空结果。 */
export type QueryResponse = { kind: "result"; result: G4QueryResultV1 } | { kind: "execution"; view: G4QueryView };

/** 显示源词法原值，不经过Number、parseFloat或浏览器时间舍入。 */
export function displayQueryValue(value: G4QueryValue): string {
  if (value.type === "null") return "空值";
  if (typeof value.lexical !== "string") throw new Error("query_value_invalid");
  return value.type === "string" && value.lexical === "" ? "空字符串" : value.lexical;
}

/** 仅解码正式生成物的两种顶层形状，缺字段和未知执行状态不能降级为EMPTY。 */
export function decodeQueryResponse(value: unknown): QueryResponse {
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("query_response_invalid");
  const record = value as Record<string, unknown>;
  if (Object.hasOwn(record, "schemaVersion")) {
    const fields = ["schemaVersion", "status", "data", "candidates", "evidence", "snapshot", "subSources", "validTime", "observedAtUtc", "traceId", "limited", "diagnostics"];
    if (record.schemaVersion !== "g4.query-result.v1" || !exactFields(record, fields) || typeof record.status !== "string"
      || !["FOUND", "EMPTY", "AMBIGUOUS", "PARTIAL", "UNAVAILABLE", "UNAUTHORIZED"].includes(record.status)
      || !["data", "candidates", "evidence", "subSources", "diagnostics"].every(key => Array.isArray(record[key]))
      || typeof record.limited !== "boolean" || typeof record.traceId !== "string" || typeof record.observedAtUtc !== "string"
      || !record.snapshot || typeof record.snapshot !== "object") throw new Error("query_response_invalid");
    return { kind: "result", result: value as G4QueryResultV1 };
  }
  if (!exactFields(record, ["queryId", "executionStatus", "createdAtUtc", "completedAtUtc", "expiresAtUtc", "resultHash", "errorCode"])
    || typeof record.queryId !== "string" || typeof record.executionStatus !== "string"
    || !["RUNNING", "COMPLETED", "CANCELLED", "FAILED"].includes(record.executionStatus)
    || typeof record.createdAtUtc !== "string" || typeof record.expiresAtUtc !== "string"
    || !["completedAtUtc", "resultHash", "errorCode"].every(key => record[key] === null || typeof record[key] === "string")) throw new Error("query_response_invalid");
  return { kind: "execution", view: value as G4QueryView };
}

/** 闭合顶层集合用于传输判别，完整来源与授权由服务端当前事务核验。 */
function exactFields(value: Record<string, unknown>, fields: string[]): boolean {
  return Object.keys(value).length === fields.length && fields.every(key => Object.hasOwn(value, key));
}

/** 所有展示状态固定中文，不把未知代码或异常正文作为可信解释。 */
export const queryStatusLabels: Record<G4QueryResultV1["status"], string> = {
  FOUND: "找到可信结果", AMBIGUOUS: "存在多个授权候选，请选择", EMPTY: "查询成功，无匹配结果",
  PARTIAL: "仅返回可证实的部分结果", UNAUTHORIZED: "当前权限不允许读取", UNAVAILABLE: "本次无法取得可信结果",
};
