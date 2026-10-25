import { describe, expect, it } from "vitest";
import { createPlatformClient, PlatformApiError } from "./client";
describe("平台契约客户端", () => {
  it("转发取消信号、同源凭证并禁用缓存", async () => {
    const controller = new AbortController();
    let observed: RequestInit | undefined;
    const client = createPlatformClient({ fetch: async (_url, init) => { observed = init; return Response.json({ items: [], auditId: "a", traceId: "t" }); } });
    const result = await client.resources(undefined, controller.signal);
    expect(result.items).toEqual([]);
    expect(observed).toMatchObject({ signal: controller.signal, cache: "no-store", credentials: "same-origin" });
  });
  it.each([401, 403, 503])("保留真实 %s ProblemDetails 与关联字段", async status => {
    const client = createPlatformClient({ fetch: async () => Response.json({ status, code: "forbidden", traceId: "safe-trace" }, { status }) });
    await expect(client.me()).rejects.toMatchObject({ status, traceId: "safe-trace" });
  });
  it("区分网络故障，不捏造成功数据", async () => {
    const client = createPlatformClient({ fetch: async () => { throw new TypeError("offline"); } });
    await expect(client.me()).rejects.toThrow(TypeError);
  });
  it("编码厂区查询并拒绝空响应", async () => {
    let url = "";
    const client = createPlatformClient({ fetch: async input => { url = String(input); return new Response(null, { status: 200 }); } });
    await expect(client.resources("a&b")).rejects.toBeInstanceOf(PlatformApiError);
    expect(url).toBe("/api/v1/platform/resources?siteId=a%26b");
  });
});
