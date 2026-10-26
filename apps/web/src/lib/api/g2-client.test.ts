import { describe, expect, it } from "vitest";
import { createG2Client } from "./g2-client";
import type { SaveDraftRequest } from "./g2-generated";
const payload: SaveDraftRequest = { name: "合成", sources: { ontologyTurtle: "original", shapesTurtle: "", vocabularyTurtle: null, dataTurtle: "" }, command: { commandId: "c", idempotencyKey: "i", expectedRevision: 2, reason: "测试" } };
describe("G2同源传输", () => {
  it("先CSRF、匹配If-Match，409不自动重试且保留payload", async () => {
    const calls: Array<{ url: string; init?: RequestInit }> = [];
    const client = createG2Client({ fetch: async (url, init) => { calls.push({ url: String(url), init }); return String(url) === "/auth/csrf" ? Response.json({ requestToken: "csrf" }) : Response.json({ code: "revision_conflict", traceId: "safe" }, { status: 409 }); } });
    await expect(client.saveDraft("draft/a", payload)).rejects.toMatchObject({ status: 409, traceId: "safe" });
    expect(calls).toHaveLength(2); expect(calls[1].url).toBe("/api/v1/ontology-drafts/draft%2Fa");
    expect(calls[1].init).toMatchObject({ credentials: "same-origin", redirect: "error", cache: "no-store", body: JSON.stringify(payload) });
    expect(new Headers(calls[1].init?.headers).get("If-Match")).toBe('"2"');
    expect(new Headers(calls[1].init?.headers).get("X-CSRF-TOKEN")).toBe("csrf");
  });
  it.each([401, 403, 422, 428, 503])("准确保留HTTP %s", async status => {
    const client = createG2Client({ fetch: async () => Response.json({ code: "safe_code", traceId: "t" }, { status }) });
    await expect(client.drafts()).rejects.toMatchObject({ status, code: "safe_code" });
  });
  it("传播取消且拒绝空JSON", async () => {
    const controller = new AbortController(); let observed: RequestInit | undefined;
    const client = createG2Client({ fetch: async (_url, init) => { observed = init; return new Response(null); } });
    await expect(client.drafts(controller.signal)).rejects.toMatchObject({ code: "invalid_response" }); expect(observed?.signal).toBe(controller.signal);
  });
});
describe("G2持久事件订阅", () => {
  it("用Last-Event-ID和真实fetch流续订，取消信号不变", async () => {
    const controller = new AbortController(); let observed: RequestInit | undefined;
    const stream = new ReadableStream<Uint8Array>({ start(c) { c.close(); } });
    const client = createG2Client({ fetch: async (_url, init) => { observed = init; return new Response(stream, { headers: { "Content-Type": "text/event-stream" } }); } });
    expect(await client.events("run-1", "run-1:7", controller.signal)).toBe(stream);
    expect(new Headers(observed?.headers).get("Last-Event-ID")).toBe("run-1:7");
    expect(observed).toMatchObject({ signal: controller.signal, credentials: "same-origin", cache: "no-store", redirect: "error" });
  });
});
