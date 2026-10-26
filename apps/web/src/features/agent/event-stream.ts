import type { AssetVersionSnapshot, ExecutionEvent } from "../../lib/api/g2-generated";
import { decodeExecutionEvent } from "./event-schema";
/** 解码跨网络chunk的UTF8/CRLF/多行data；只对单帧和未完整帧应用预算，退出仅取消订阅。 */
export async function* readExecutionEvents(body: ReadableStream<Uint8Array>, runId: string, afterSeq: number, signal: AbortSignal | undefined, expectedSnapshot: AssetVersionSnapshot): AsyncGenerator<ExecutionEvent> {
  const reader = body.getReader();
  const decoder = new TextDecoder("utf-8", { fatal: true });
  const encoder = new TextEncoder();
  let buffer = "";
  let lastSeq = afterSeq;
  const abort = () => { void reader.cancel(); };
  signal?.addEventListener("abort", abort, { once: true });
  try {
    while (true) {
      signal?.throwIfAborted();
      const { value, done } = await reader.read();
      signal?.throwIfAborted();
      try { buffer += decoder.decode(value, { stream: !done }); } catch { throw new Error("unsupported_event_schema"); }
      let boundary: RegExpExecArray | null;
      while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
        const block = buffer.slice(0, boundary.index); buffer = buffer.slice(boundary.index + boundary[0].length);
        // 帧传输开销另设有界上限；JSON事件仍严格限制128KiB，不能按整个网络chunk误判。
        if (encoder.encode(block).byteLength > 262144) throw new Error("event_budget_exceeded");
        const data = block.split(/\r?\n/).filter(line => line.startsWith("data:")).map(line => line.slice(5).replace(/^ /, "")).join("\n");
        if (!data) continue;
        const event = decodeExecutionEvent(data, runId, expectedSnapshot);
        if (event.seq <= lastSeq) continue;
        if (event.seq !== lastSeq + 1) throw new Error("event_sequence_gap");
        lastSeq = event.seq; yield event;
      }
      if (encoder.encode(buffer).byteLength > 262144) throw new Error("event_budget_exceeded");
      if (done) { if (buffer.trim()) throw new Error("incomplete_event_stream"); break; }
    }
  } finally { signal?.removeEventListener("abort", abort); await reader.cancel().catch(() => {}); reader.releaseLock(); }
}
