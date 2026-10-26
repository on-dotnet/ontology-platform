import type { ExecutionEvent } from "../../lib/api/g2-generated";
/** 事件判别只接受唯一冻结协议；未知事件必须回读Run快照。 */
function decode(data: string, runId: string): ExecutionEvent {
  if (new TextEncoder().encode(data).byteLength > 131072) throw new Error("event_budget_exceeded");
  const event = JSON.parse(data) as ExecutionEvent;
  const known = ["run.started", "tool.started", "tool.completed", "evidence.added", "message.delta", "approval.required", "run.completed", "run.failed", "run.cancelled"];
  if (!event || event.runId !== runId || event.schemaVersion !== 1 || !Number.isSafeInteger(event.seq) || event.seq < 1 || event.eventId !== `${runId}:${event.seq}` || !known.includes(event.eventType) || event.payload?.kind !== event.eventType || !event.snapshot?.releaseId) throw new Error("unsupported_event_schema");
  let valid = false;
  switch (event.eventType) {
    case "run.started": valid = ["disabled", "deterministic", "approved_model"].includes(event.payload.providerMode) && Array.isArray(event.payload.capabilityIds) && event.payload.capabilityIds.every(id => typeof id === "string") && Number.isSafeInteger(event.payload.maxToolCalls) && event.payload.maxToolCalls <= 3 && Number.isSafeInteger(event.payload.timeoutMs); break;
    case "tool.started": valid = typeof event.payload.invocationId === "string" && typeof event.payload.capabilityId === "string" && typeof event.payload.capabilityVersion === "string" && !!event.payload.plan && typeof event.payload.plan.assetId === "string"; break;
    case "tool.completed": valid = typeof event.payload.invocationId === "string" && Number.isFinite(event.payload.durationMs) && event.payload.durationMs >= 0 && !!event.payload.result && ["FOUND", "EMPTY", "PARTIAL", "UNAVAILABLE", "UNAUTHORIZED", "AMBIGUOUS"].includes(event.payload.result.status) && !!event.payload.result.snapshot?.releaseId && Array.isArray(event.payload.result.data); break;
    case "evidence.added": valid = !!event.payload.evidence && typeof event.payload.evidence.evidenceId === "string" && event.payload.evidence.synthetic === true; break;
    case "message.delta": valid = typeof event.payload.text === "string" && event.payload.text.length <= 4096; break;
    case "approval.required": valid = typeof event.payload.approvalId === "string" && typeof event.payload.proposalId === "string" && ["PUBLISH", "ROLLBACK"].includes(event.payload.operation) && !!event.payload.scope && Array.isArray(event.payload.scope.siteIds) && Number.isFinite(Date.parse(event.payload.expiresAtUtc)); break;
    case "run.completed": valid = event.payload.status === "COMPLETED" && Number.isSafeInteger(event.payload.totalToolCalls) && (event.payload.lastResultStatus === null || ["FOUND", "EMPTY", "PARTIAL", "UNAVAILABLE", "UNAUTHORIZED", "AMBIGUOUS"].includes(event.payload.lastResultStatus)); break;
    case "run.failed": valid = event.payload.status === "FAILED" && typeof event.payload.code === "string" && Number.isSafeInteger(event.payload.totalToolCalls); break;
    case "run.cancelled": valid = event.payload.status === "CANCELLED" && event.payload.code === "cancelled" && Number.isSafeInteger(event.payload.totalToolCalls); break;
  }
  if (!valid || event.seq > 512) throw new Error("unsupported_event_schema");
  return event;
}
/** 解码跨网络chunk的UTF8/CRLF/多行data，有界缓存；退出只取消订阅。 */
export async function* readExecutionEvents(body: ReadableStream<Uint8Array>, runId: string, afterSeq: number, signal?: AbortSignal): AsyncGenerator<ExecutionEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let lastSeq = afterSeq;
  const abort = () => { void reader.cancel(); };
  signal?.addEventListener("abort", abort, { once: true });
  try {
    while (true) {
      signal?.throwIfAborted();
      const { value, done } = await reader.read();
      signal?.throwIfAborted();
      buffer += decoder.decode(value, { stream: !done });
      if (buffer.length > 262144) throw new Error("event_budget_exceeded");
      let boundary: RegExpExecArray | null;
      while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
        const block = buffer.slice(0, boundary.index); buffer = buffer.slice(boundary.index + boundary[0].length);
        const data = block.split(/\r?\n/).filter(line => line.startsWith("data:")).map(line => line.slice(5).replace(/^ /, "")).join("\n");
        if (!data) continue;
        const event = decode(data, runId);
        if (event.seq <= lastSeq) continue;
        if (event.seq !== lastSeq + 1) throw new Error("event_sequence_gap");
        lastSeq = event.seq; yield event;
      }
      if (done) { if (buffer.trim()) throw new Error("incomplete_event_stream"); break; }
    }
  } finally { signal?.removeEventListener("abort", abort); await reader.cancel().catch(() => {}); reader.releaseLock(); }
}
