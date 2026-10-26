import { describe, expect, it } from "vitest";
import { readExecutionEvents } from "./event-stream";
const evt = { runId: "r1", seq: 1, eventId: "r1:1", eventType: "message.delta", schemaVersion: 1, occurredAtUtc: "2026-10-26T00:00:00Z", snapshot: { releaseId: "r" }, payload: { kind: "message.delta", text: "<script>中文</script>" } };
function body(parts: string[]) { const encoder = new TextEncoder(); return new ReadableStream<Uint8Array>({ start(c) { for (const part of parts) c.enqueue(encoder.encode(part)); c.close(); } }); }
describe("SSE解码", () => {
  it("跨chunk/CRLF/多行data并按run+seq去重", async () => {
    const json = JSON.stringify(evt); const at = json.indexOf('"payload"');
    const stream = body(["id: r1:1\r", "\ndata: " + json.slice(0, at) + "\r\ndata: " + json.slice(at) + "\r\n\r\n", "data: " + json + "\n\n"]);
    const events = []; for await (const e of readExecutionEvents(stream, "r1", 0)) events.push(e);
    expect(events).toHaveLength(1); expect(events[0].payload).toMatchObject({ text: "<script>中文</script>" });
  });
  it.each([{ ...evt, schemaVersion: 2 }, { ...evt, payload: { kind: "unknown" } }, { ...evt, runId: "another" }])("拒绝未知协议/错Run", async event => {
    await expect((async () => { for await (const e of readExecutionEvents(body(["data: " + JSON.stringify(event) + "\n\n"]), "r1", 0)) void e; })()).rejects.toThrow();
  });
  it("已知eventType但载荷缺字段也拒绝", async () => {
    const event = { ...evt, eventType: "tool.completed", payload: { kind: "tool.completed" } };
    await expect((async () => { for await (const e of readExecutionEvents(body(["data: " + JSON.stringify(event) + "\n\n"]), "r1", 0)) void e; })()).rejects.toThrow("unsupported_event_schema");
  });
  it("真正UTF8字节跨chunk仍保留中文", async () => {
    const bytes = new TextEncoder().encode("data: " + JSON.stringify(evt) + "\n\n");
    const stream = new ReadableStream<Uint8Array>({ start(c) { for (const byte of bytes) c.enqueue(new Uint8Array([byte])); c.close(); } });
    const events = []; for await (const e of readExecutionEvents(stream, "r1", 0)) events.push(e);
    expect(events[0].payload).toMatchObject({ text: "<script>中文</script>" });
  });
  it("取消订阅释放读取器", async () => {
    const controller = new AbortController(); controller.abort();
    await expect((async () => { for await (const e of readExecutionEvents(body([]), "r1", 0, controller.signal)) void e; })()).rejects.toMatchObject({ name: "AbortError" });
  });
});
