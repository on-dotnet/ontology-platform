import { describe, expect, it } from "vitest";
import type { AssetVersionSnapshot, SemanticQueryResult } from "../../lib/api/g2-generated";
import { readExecutionEvents } from "./event-stream";
const hash = "a".repeat(64);
const snapshot: AssetVersionSnapshot = { releaseId: "r", ontologyHash: hash, shapesHash: hash, vocabularyHash: null, dataHash: hash, ontologyGraphIri: "urn:r:ontology", dataGraphIri: "urn:r:data", mappingVersions: [], metricVersions: [], ruleVersions: [], capabilityVersions: [{ assetId: "resolve_entity", version: hash }] };
const evt = { runId: "r1", seq: 1, eventId: "r1:1", eventType: "message.delta", schemaVersion: 1, occurredAtUtc: "2026-10-26T00:00:00Z", snapshot, payload: { kind: "message.delta", text: "<script>中文</script>" } };
const result: SemanticQueryResult = { status: "FOUND", data: [{ kind: "ontology", ontology: { classIris: [], objectPropertyIris: [], datatypePropertyIris: [], labels: [], supportedAxioms: [], diagnostics: [] }, entity: null, relationship: null }], candidates: [], evidence: [], snapshot, subSources: [], validTime: null, observedAtUtc: "2026-10-26T00:00:00Z", traceId: "safe", limited: false, diagnostics: [] };
function body(parts: string[]) { const encoder = new TextEncoder(); return new ReadableStream<Uint8Array>({ start(c) { for (const part of parts) c.enqueue(encoder.encode(part)); c.close(); } }); }
function bytesBody(bytes: Uint8Array, size: number) { let offset = 0; return new ReadableStream<Uint8Array>({ pull(c) { if (offset >= bytes.length) { c.close(); return; } c.enqueue(bytes.subarray(offset, offset + size)); offset += size; } }); }
async function collect(stream: ReadableStream<Uint8Array>, expected = snapshot, signal?: AbortSignal) { const values = []; for await (const event of readExecutionEvents(stream, "r1", 0, signal, expected)) values.push(event); return values; }
describe("SSE解码", () => {
  it("跨chunk/CRLF/多行data并按run+seq去重", async () => {
    const json = JSON.stringify(evt); const at = json.indexOf('"payload"');
    const events = await collect(body(["id: r1:1\r", "\ndata: " + json.slice(0, at) + "\r\ndata: " + json.slice(at) + "\r\n\r\n", "data: " + json + "\n\n"]));
    expect(events).toHaveLength(1); expect(events[0].payload).toMatchObject({ text: "<script>中文</script>" });
  });
  it.each([{ ...evt, schemaVersion: 2 }, { ...evt, payload: { kind: "unknown" } }, { ...evt, runId: "another" }])("拒绝未知协议/错Run", async event => {
    await expect(collect(body(["data: " + JSON.stringify(event) + "\n\n"]))).rejects.toThrow();
  });
  it("已知eventType但载荷缺字段也拒绝", async () => {
    await expect(collect(body(["data: " + JSON.stringify({ ...evt, eventType: "tool.completed", payload: { kind: "tool.completed" } }) + "\n\n"]))).rejects.toThrow("unsupported_event_schema");
  });
  it("真正UTF8字节跨chunk仍保留中文", async () => {
    const events = await collect(bytesBody(new TextEncoder().encode("data: " + JSON.stringify(evt) + "\n\n"), 1));
    expect(events[0].payload).toMatchObject({ text: "<script>中文</script>" });
  });
  it("取消订阅释放读取器", async () => {
    const controller = new AbortController(); controller.abort();
    await expect(collect(body([]), snapshot, controller.signal)).rejects.toMatchObject({ name: "AbortError" });
  });
  it.each([
    { ...evt, snapshot: { releaseId: "r" } },
    { ...evt, snapshot: { ...snapshot, releaseId: "wrong-release" } },
    { ...evt, snapshot: { ...snapshot, dataHash: "b".repeat(64) } },
    { ...evt, eventType: "tool.completed", payload: { kind: "tool.completed", invocationId: "i", durationMs: 1, result: { ...result, data: [{ kind: "unknown" }] } } },
    { ...evt, eventType: "tool.completed", payload: { kind: "tool.completed", invocationId: "i", durationMs: 1, result: { ...result, snapshot: { ...snapshot, releaseId: "different-release" } } } },
    { ...evt, eventType: "tool.completed", payload: { kind: "tool.completed", invocationId: "i", durationMs: 1, result: { ...result, data: [{ kind: "entity", entity: { iri: "x" }, ontology: null, relationship: null }] } } },
    { ...evt, eventType: "tool.completed", payload: { kind: "tool.completed", invocationId: "i", durationMs: 1, result: { ...result, data: [{ kind: "ontology", ontology: result.data[0].ontology, entity: {}, relationship: null }] } } },
  ])("I1拒绝不完整/冲突snapshot与未知/不完整/非互斥SemanticDatum", async event => {
    await expect(collect(body(["data: " + JSON.stringify(event) + "\n\n"]))).rejects.toThrow("unsupported_event_schema");
  });
  it("I1合法完整tool.completed仍接受", async () => {
    const event = { ...evt, eventType: "tool.completed", payload: { kind: "tool.completed", invocationId: "i", durationMs: 1, result } };
    expect(await collect(body(["data: " + JSON.stringify(event) + "\n\n"]))).toHaveLength(1);
  });
  it("I2同一70帧流单字节/多chunk/单一大chunk结果一致", async () => {
    const text = Array.from({ length: 70 }, (_, index) => "data: " + JSON.stringify({ ...evt, seq: index + 1, eventId: `r1:${index + 1}`, payload: { kind: "message.delta", text: "a".repeat(4096) } }) + "\n\n").join("");
    const bytes = new TextEncoder().encode(text);
    const whole = await collect(bytesBody(bytes, bytes.length));
    const chunks = await collect(bytesBody(bytes, 37));
    const singles = await collect(bytesBody(bytes, 1));
    expect(whole).toHaveLength(70); expect(chunks).toEqual(whole); expect(singles).toEqual(whole);
  }, 30000);
  it("I2真正单事件超128KiB拒绝", async () => {
    const text = "data: " + JSON.stringify({ ...evt, payload: { kind: "message.delta", text: "a".repeat(140000) } }) + "\n\n";
    await expect(collect(body([text]))).rejects.toThrow("event_budget_exceeded");
    await expect(collect(body([text.slice(0, 90000), text.slice(90000)]))).rejects.toThrow("event_budget_exceeded");
  });
});
describe("完整事件合同合法分支", () => {
  const evidence = { evidenceId: "e1", releaseId: "r", scope: { organizationId: "org", siteIds: ["a"] }, graphIri: "urn:r:data", subjectIri: "urn:s", predicateIri: "urn:p", objectTerm: { kind: "literal", value: "中文", datatype: null, language: "zh" }, sourceId: "Synthetic", sourceRecordId: "record", sourceObjectKey: "immutable", contentHash: hash, validFromUtc: "2026-10-26T00:00:00Z", validToUtc: null, observedAtUtc: "2026-10-26T00:00:00Z", modelVersion: hash, mappingVersion: null, synthetic: true };
  const entity = { iri: "urn:s", typeIris: ["urn:Class"], label: "合成", externalId: "record", organizationId: "org", siteId: "a", synthetic: true, properties: [{ predicateIri: "urn:p", value: evidence.objectTerm, evidenceIds: ["e1"] }] };
  const plan = { capabilityId: "resolve_entity", capabilityVersion: hash, assetId: "asset", releaseId: "r", entityType: null, entityIri: null, externalId: "record", siteId: "a", relationshipIris: [], depth: 1, maxRows: 10, timeoutMs: 1000 };
  it.each([
    { kind: "run.started", providerMode: "deterministic", capabilityIds: ["resolve_entity"], maxToolCalls: 3, timeoutMs: 30000 },
    { kind: "tool.started", invocationId: "i", capabilityId: "resolve_entity", capabilityVersion: hash, plan },
    { kind: "tool.completed", invocationId: "i", durationMs: 1, result: { ...result, data: [{ kind: "entity", ontology: null, entity, relationship: null }], evidence: [evidence] } },
    { kind: "tool.completed", invocationId: "i", durationMs: 1, result: { ...result, data: [{ kind: "relationship", ontology: null, entity: null, relationship: { sourceIri: "urn:s", predicateIri: "urn:p", targetIri: "urn:t", evidenceIds: ["e1"] } }] } },
    { kind: "evidence.added", evidence },
    { kind: "approval.required", approvalId: "a", proposalId: "p", operation: "PUBLISH", scope: evidence.scope, expiresAtUtc: "2026-10-27T00:00:00Z" },
    { kind: "run.completed", status: "COMPLETED", totalToolCalls: 1, lastResultStatus: "FOUND" },
    { kind: "run.failed", status: "FAILED", code: "SourceUnavailable", totalToolCalls: 1 },
    { kind: "run.cancelled", status: "CANCELLED", code: "cancelled", totalToolCalls: 1 },
  ])("合法$kind完整字段接受", async payload => {
    const event = { ...evt, eventType: payload.kind, payload };
    expect(await collect(body(["data: " + JSON.stringify(event) + "\n\n"]))).toHaveLength(1);
  });
});
