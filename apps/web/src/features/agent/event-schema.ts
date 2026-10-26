import type { AssetVersionSnapshot, ExecutionEvent } from "../../lib/api/g2-generated";
/** 以下守卫只验证唯一生成合同，不创建另一套业务DTO；未知字段也停止接收。 */
function shape(value: unknown, fields: string): value is Record<string, unknown> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return false;
  const keys = fields.split(" ");
  return Object.keys(value).length === keys.length && keys.every(key => Object.hasOwn(value, key));
}
const text = (value: unknown): value is string => typeof value === "string";
const nonempty = (value: unknown): value is string => text(value) && value.length > 0;
const nullableText = (value: unknown) => value === null || text(value);
const hash = (value: unknown) => text(value) && /^[0-9a-f]{64}$/.test(value);
const timestamp = (value: unknown) => text(value) && /^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value));
const integer = (value: unknown, min: number, max: number) => typeof value === "number" && Number.isSafeInteger(value) && value >= min && value <= max;
const list = (value: unknown, guard: (item: unknown) => boolean): value is unknown[] => Array.isArray(value) && value.every(guard);
const strings = (value: unknown) => list(value, text);
const oneOf = (value: unknown, values: string[]) => text(value) && values.includes(value);
const queryStatuses = ["FOUND", "EMPTY", "PARTIAL", "UNAVAILABLE", "UNAUTHORIZED", "AMBIGUOUS"];
/** 快照比较按对象字段排序，数组保持正式合同的顺序，不受JSON字段排列影响。 */
function canonical(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value && typeof value === "object") return `{${Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => `${JSON.stringify(key)}:${canonical(item)}`).join(",")}}`;
  return JSON.stringify(value);
}
/** 完整验证正式快照的全部hash、图及真实版本关联字段。 */
export function validSnapshot(value: unknown): value is AssetVersionSnapshot {
  const version = (item: unknown) => shape(item, "assetId version") && nonempty(item.assetId) && nonempty(item.version);
  return shape(value, "releaseId ontologyHash shapesHash vocabularyHash dataHash ontologyGraphIri dataGraphIri mappingVersions metricVersions ruleVersions capabilityVersions") && nonempty(value.releaseId) && hash(value.ontologyHash) && hash(value.shapesHash) && (value.vocabularyHash === null || hash(value.vocabularyHash)) && hash(value.dataHash) && nonempty(value.ontologyGraphIri) && nonempty(value.dataGraphIri) && list(value.mappingVersions, version) && list(value.metricVersions, version) && list(value.ruleVersions, version) && list(value.capabilityVersions, version);
}
/** 所有事件、工具结果与证据都绑定所选Run的同一个完整不可变快照。 */
function sameSnapshot(value: unknown, expected: AssetVersionSnapshot) { return validSnapshot(value) && canonical(value) === canonical(expected); }
function scope(value: unknown) { return shape(value, "organizationId siteIds") && nonempty(value.organizationId) && list(value.siteIds, nonempty) && value.siteIds.length >= 1 && value.siteIds.length <= 16 && new Set(value.siteIds).size === value.siteIds.length; }
function term(value: unknown) { return shape(value, "kind value datatype language") && oneOf(value.kind, ["iri", "blank", "literal"]) && text(value.value) && nullableText(value.datatype) && nullableText(value.language); }
function diagnostic(value: unknown) { return shape(value, "code severity message focusNode path") && nonempty(value.code) && oneOf(value.severity, ["info", "warning", "error"]) && text(value.message) && (value.focusNode === null || term(value.focusNode)) && nullableText(value.path); }
function property(value: unknown) { return shape(value, "predicateIri value evidenceIds") && nonempty(value.predicateIri) && term(value.value) && strings(value.evidenceIds); }
function ontology(value: unknown) { return shape(value, "classIris objectPropertyIris datatypePropertyIris labels supportedAxioms diagnostics") && strings(value.classIris) && strings(value.objectPropertyIris) && strings(value.datatypePropertyIris) && list(value.labels, property) && strings(value.supportedAxioms) && list(value.diagnostics, diagnostic); }
function entity(value: unknown) { return shape(value, "iri typeIris label externalId organizationId siteId synthetic properties") && nonempty(value.iri) && strings(value.typeIris) && text(value.label) && text(value.externalId) && nonempty(value.organizationId) && nonempty(value.siteId) && value.synthetic === true && list(value.properties, property); }
function relationship(value: unknown) { return shape(value, "sourceIri predicateIri targetIri evidenceIds") && nonempty(value.sourceIri) && nonempty(value.predicateIri) && nonempty(value.targetIri) && strings(value.evidenceIds); }
/** SemanticDatum必须精确满足已知互斥分支，不能以未知kind或残缺对象构成答案。 */
function datum(value: unknown) {
  if (!shape(value, "kind ontology entity relationship")) return false;
  switch (value.kind) {
    case "ontology": return ontology(value.ontology) && value.entity === null && value.relationship === null;
    case "entity": return value.ontology === null && entity(value.entity) && value.relationship === null;
    case "relationship": return value.ontology === null && value.entity === null && relationship(value.relationship);
    default: return false;
  }
}
function candidate(value: unknown) { return shape(value, "entityIri entityTypeIris externalId organizationId siteId label evidenceIds") && nonempty(value.entityIri) && strings(value.entityTypeIris) && text(value.externalId) && nonempty(value.organizationId) && nonempty(value.siteId) && text(value.label) && strings(value.evidenceIds); }
function evidence(value: unknown, expected: AssetVersionSnapshot) {
  return shape(value, "evidenceId releaseId scope graphIri subjectIri predicateIri objectTerm sourceId sourceRecordId sourceObjectKey contentHash validFromUtc validToUtc observedAtUtc modelVersion mappingVersion synthetic") && nonempty(value.evidenceId) && value.releaseId === expected.releaseId && scope(value.scope) && oneOf(value.graphIri, [expected.ontologyGraphIri, expected.dataGraphIri]) && nonempty(value.subjectIri) && nonempty(value.predicateIri) && term(value.objectTerm) && nonempty(value.sourceId) && text(value.sourceRecordId) && nonempty(value.sourceObjectKey) && hash(value.contentHash) && timestamp(value.validFromUtc) && (value.validToUtc === null || timestamp(value.validToUtc)) && timestamp(value.observedAtUtc) && nonempty(value.modelVersion) && nullableText(value.mappingVersion) && value.synthetic === true;
}
function result(value: unknown, expected: AssetVersionSnapshot) {
  const source = (item: unknown) => shape(item, "sourceId status releaseId dataHash observedAtUtc code") && nonempty(item.sourceId) && oneOf(item.status, ["AVAILABLE", "EMPTY", "PARTIAL", "UNAVAILABLE", "UNAUTHORIZED"]) && item.releaseId === expected.releaseId && hash(item.dataHash) && timestamp(item.observedAtUtc) && nullableText(item.code);
  const temporal = (item: unknown) => shape(item, "fromUtc toUtc") && timestamp(item.fromUtc) && (item.toUtc === null || timestamp(item.toUtc));
  if (!shape(value, "status data candidates evidence snapshot subSources validTime observedAtUtc traceId limited diagnostics")) return false;
  return oneOf(value.status, queryStatuses) && list(value.data, datum) && (value.status !== "FOUND" || value.data.length > 0) && list(value.candidates, candidate) && list(value.evidence, item => evidence(item, expected)) && sameSnapshot(value.snapshot, expected) && list(value.subSources, source) && (value.validTime === null || temporal(value.validTime)) && timestamp(value.observedAtUtc) && text(value.traceId) && typeof value.limited === "boolean" && list(value.diagnostics, diagnostic);
}
function plan(value: unknown) { return shape(value, "capabilityId capabilityVersion assetId releaseId entityType entityIri externalId siteId relationshipIris depth maxRows timeoutMs") && nonempty(value.capabilityId) && nonempty(value.capabilityVersion) && nonempty(value.assetId) && nullableText(value.releaseId) && nullableText(value.entityType) && nullableText(value.entityIri) && nullableText(value.externalId) && nullableText(value.siteId) && strings(value.relationshipIris) && integer(value.depth, 1, 5) && integer(value.maxRows, 1, 100) && integer(value.timeoutMs, 100, 5000); }
/** 按eventType验证全部已知payload字段和字面量，未识别schema不提升为答案。 */
export function decodeExecutionEvent(data: string, runId: string, expected: AssetVersionSnapshot): ExecutionEvent {
  if (new TextEncoder().encode(data).byteLength > 131072) throw new Error("event_budget_exceeded");
  let event: unknown;
  try { event = JSON.parse(data); } catch { throw new Error("unsupported_event_schema"); }
  if (!validSnapshot(expected) || !shape(event, "runId seq eventId eventType schemaVersion occurredAtUtc snapshot payload") || event.runId !== runId || !integer(event.seq, 1, 512) || event.eventId !== `${runId}:${event.seq}` || event.schemaVersion !== 1 || !timestamp(event.occurredAtUtc) || !sameSnapshot(event.snapshot, expected)) throw new Error("unsupported_event_schema");
  const payload = event.payload;
  let valid = false;
  switch (event.eventType) {
    case "run.started": valid = shape(payload, "kind providerMode capabilityIds maxToolCalls timeoutMs") && oneOf(payload.providerMode, ["disabled", "deterministic", "approved_model"]) && strings(payload.capabilityIds) && integer(payload.maxToolCalls, 1, 3) && integer(payload.timeoutMs, 1, 30000); break;
    case "tool.started": valid = shape(payload, "kind invocationId capabilityId capabilityVersion plan") && nonempty(payload.invocationId) && nonempty(payload.capabilityId) && nonempty(payload.capabilityVersion) && plan(payload.plan); break;
    case "tool.completed": valid = shape(payload, "kind invocationId result durationMs") && nonempty(payload.invocationId) && typeof payload.durationMs === "number" && Number.isFinite(payload.durationMs) && payload.durationMs >= 0 && result(payload.result, expected); break;
    case "evidence.added": valid = shape(payload, "kind evidence") && evidence(payload.evidence, expected); break;
    case "message.delta": valid = shape(payload, "kind text") && text(payload.text) && payload.text.length <= 4096; break;
    case "approval.required": valid = shape(payload, "kind approvalId proposalId operation scope expiresAtUtc") && nonempty(payload.approvalId) && nonempty(payload.proposalId) && oneOf(payload.operation, ["PUBLISH", "ROLLBACK"]) && scope(payload.scope) && timestamp(payload.expiresAtUtc); break;
    case "run.completed": valid = shape(payload, "kind status totalToolCalls lastResultStatus") && payload.status === "COMPLETED" && integer(payload.totalToolCalls, 0, 3) && (payload.lastResultStatus === null || oneOf(payload.lastResultStatus, queryStatuses)); break;
    case "run.failed": valid = shape(payload, "kind status code totalToolCalls") && payload.status === "FAILED" && nonempty(payload.code) && integer(payload.totalToolCalls, 0, 3); break;
    case "run.cancelled": valid = shape(payload, "kind status code totalToolCalls") && payload.status === "CANCELLED" && payload.code === "cancelled" && integer(payload.totalToolCalls, 0, 3); break;
  }
  if (!valid || !payload || typeof payload !== "object" || !("kind" in payload) || payload.kind !== event.eventType) throw new Error("unsupported_event_schema");
  return event as ExecutionEvent;
}
