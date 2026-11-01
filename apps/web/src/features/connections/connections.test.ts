import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { configFromForm, formFromConfig, newForm, validateForm, type ConnectionForm, type ConnectionType } from "./form-model";
import { ConfigurationForm } from "./form";
import { ProbeReport, RequestError } from "./status";
import { CatalogSnapshot } from "./catalog";
import { createConnectionsClient } from "./api";
import { PlatformApiError } from "../../lib/api/client";
import type { CatalogSnapshotView, ConnectionProbeView } from "../../lib/api/g4-generated";

const validForms: Record<ConnectionType, ConnectionForm> = {
  POSTGRESQL: newForm("POSTGRESQL", "合成连接"),
  ORACLE: { ...newForm("ORACLE", "合成Oracle"), values: { host: "oracle", port: "1521", serviceName: "SERVICE", username: "reader", tls: "true", allowedOwners: "PRODUCTION" } },
  DORIS: { ...newForm("DORIS", "合成Doris"), values: { feHost: "doris", queryPort: "9030", catalog: "internal", database: "fixture", username: "reader", tls: "true" } },
  TDENGINE: { ...newForm("TDENGINE", "合成TD"), values: { wsUrl: "wss://td.example/ws", database: "fixture", timePrecision: "MILLISECOND", timeZone: "" } },
  WEB_API: { ...newForm("WEB_API", "合成API"), values: { baseOrigin: "https://api.example", operationId: "read-fixture", method: "GET", approvedPath: "/fixture", authentication: "NONE", pagination: "NONE", hostPolicyRef: "policy-fixture" } },
};
const cmd = { commandId: "test-command", idempotencyKey: "test-key", expectedRevision: 0, reason: "合成请求" };
const scope = { organizationId: "org", siteIds: ["site"] };

describe("五类受控配置与实际组件", () => {
  it.each(Object.keys(validForms) as ConnectionType[])("%s 正例投影仅type/profile并可往返", type => {
    const form = validForms[type];
    expect(validateForm(form)).toEqual({});
    const config = configFromForm(form);
    expect(Object.keys(config).sort()).toEqual(["profile", "type"]);
    expect(formFromConfig(form.displayName, config)).toEqual(form);
  });
  it.each([
    ["POSTGRESQL", "port", "1.5"], ["POSTGRESQL", "allowedSchemas", "production;DROP"], ["POSTGRESQL", "allowedSchemas", "public,public"], ["POSTGRESQL", "host", "pg;Password=x"], ["POSTGRESQL", "sslMode", "Prefer"],
    ["ORACLE", "port", "65536"], ["ORACLE", "serviceName", ""], ["ORACLE", "allowedOwners", "bad-name"], ["DORIS", "feHost", "https://host"], ["DORIS", "queryPort", "0"], ["DORIS", "tls", "yes"],
    ["TDENGINE", "wsUrl", "https://td.example"], ["TDENGINE", "wsUrl", "wss://user:secret@td.example"], ["TDENGINE", "timePrecision", "SECONDS"],
    ["WEB_API", "baseOrigin", "https://api.example/path"], ["WEB_API", "baseOrigin", "http://api.example"], ["WEB_API", "approvedPath", "//other.example"], ["WEB_API", "method", "POST"], ["WEB_API", "authentication", "BEARER"],
  ])("%s %s 拒绝非法值", (type, field, value) => {
    const form = validForms[type as ConnectionType];
    expect(validateForm({ ...form, values: { ...form.values, [field]: value } })).toHaveProperty(field);
  });
  it("可选时区空值投影null、端口数字、TLS布尔", () => {
    expect(configFromForm(validForms.TDENGINE).profile).toHaveProperty("timeZone", null);
    expect(configFromForm(validForms.ORACLE).profile).toHaveProperty("tls", true);
    expect(configFromForm(validForms.POSTGRESQL).profile).toHaveProperty("port", 5432);
  });
  it.each(Object.keys(validForms) as ConnectionType[])("%s 实际表单提供各自字段且无密码/引用", type => {
    const html = renderToStaticMarkup(createElement(ConfigurationForm, { value: validForms[type], onChange: () => undefined, errors: {} }));
    for (const name of Object.keys(validForms[type].values)) expect(html).toContain(`name="${name}"`);
    expect(html).not.toContain('type="password"'); expect(html).not.toContain("secretRef");
    if (type !== "POSTGRESQL") expect(html).toContain("连接测试与保存尚未开放");
  });
  it("字段错误与控件准确关联", () => {
    const html = renderToStaticMarkup(createElement(ConfigurationForm, { value: validForms.POSTGRESQL, onChange: () => undefined, errors: { host: "主机无效" } }));
    expect(html).toContain('aria-invalid="true"'); expect(html).toContain('aria-describedby="error-host"'); expect(html).toContain('id="error-host"');
  });
  it("切换类型只留下新类型profile", () => { const form = newForm("TDENGINE", "名称"); expect(form.values).not.toHaveProperty("username"); expect(form.values).not.toHaveProperty("secretRef"); });
});

describe("Probe、权限及目录组件", () => {
  it("无结果显示五项未验证，不能宣称通过", () => { const html = renderToStaticMarkup(createElement(ProbeReport, { probe: null, running: true })); expect(html.match(/未验证/g)).toHaveLength(5); expect(html).toContain("测试中"); expect(html).not.toContain("测试通过"); });
  it("TCP通过不提升整体，其余缺失阶段保持未验证", () => {
    const probe = { status: "PARTIAL", stages: [{ name: "NETWORK", status: "PASS", durationMs: 2, diagnosticCode: null }], stale: true, traceId: "safe-trace" } as ConnectionProbeView;
    const html = renderToStaticMarkup(createElement(ProbeReport, { probe })); expect(html).toContain("部分完成"); expect(html.match(/未验证/g)).toHaveLength(4); expect(html).toContain("需重新测试"); expect(html).not.toContain("测试通过");
  });
  it.each([[401, "重新登录"], [403, "没有访问权限"], [409, "已保留您的非敏感编辑"], [422, "未通过验证"], [503, "服务暂不可用"]])("HTTP %s 有独立恢复提示", (status, expected) => {
    const html = renderToStaticMarkup(createElement(RequestError, { error: new PlatformApiError(Number(status), "safe_code", "safe-trace") })); expect(html).toContain(expected); expect(html).toContain("safe-trace");
  });
  it("目录保真原生类型、精度与过期提醒", () => {
    const snapshot = { status: "STALE", capturedAtUtc: "2026-11-01", schemaFingerprint: "hash", objects: [{ schema: "production", name: "temperature", kind: "TABLE", fields: [{ name: "reading", nativeType: "numeric(8,2)", nullable: false, ordinal: 1, precision: 8, scale: 2 }] }] } as CatalogSnapshotView;
    const html = renderToStaticMarkup(createElement(CatalogSnapshot, { snapshot, stale: true })); expect(html).toContain("numeric(8,2)"); expect(html).toContain("不能用于证明当前目录完整"); expect(html).toContain('tabindex="0"');
  });
});

describe("真实传输边界适配（Mock仅验证请求行为）", () => {
  it("凭据只POST专用入口、同源CSRF且不入URL", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(Response.json({ requestToken: "csrf" })).mockResolvedValueOnce(Response.json({ secretRef: "temporary-ref" }, { status: 201 }));
    const client = createConnectionsClient(fetcher);
    await client.intake({ secretValue: "synthetic-password", scopeSelection: scope, purpose: "POSTGRESQL_READONLY", command: cmd });
    expect(fetcher.mock.calls[0][0]).toBe("/auth/csrf");
    const [url, options] = fetcher.mock.calls[1]; expect(url).toBe("/api/v1/connection-secrets"); expect(options?.method).toBe("POST"); expect(options?.credentials).toBe("same-origin"); expect(options?.cache).toBe("no-store"); expect(new Headers(options?.headers).get("X-CSRF-TOKEN")).toBe("csrf");
  });
  it("CAS发送完整服务器ETag，不转为纯修订", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(Response.json({ requestToken: "csrf" })).mockResolvedValueOnce(Response.json({ id: "id" }, { headers: { ETag: '"2-newhash"' } }));
    const result = await createConnectionsClient(fetcher).patch("a/b", { displayName: "新名称", command: { ...cmd, expectedRevision: 1 } }, '"1-oldhash"');
    expect(fetcher.mock.calls[1][0]).toBe("/api/v1/connections/a%2Fb"); expect(new Headers(fetcher.mock.calls[1][1]?.headers).get("If-Match")).toBe('"1-oldhash"'); expect(result.etag).toBe('"2-newhash"');
  });
  it("同命令显式重发正文完全相同，没有自动重试", async () => {
    const fetcher = vi.fn<typeof fetch>().mockImplementation(async url => String(url) === "/auth/csrf" ? Response.json({ requestToken: "csrf" }) : Response.json({ probeId: "same-probe" }));
    const client = createConnectionsClient(fetcher); const body = { scopeSelection: scope, config: configFromForm(validForms.POSTGRESQL), secretRef: "temporary-ref", command: cmd };
    await client.draftProbe(body); expect(fetcher).toHaveBeenCalledTimes(2); await client.draftProbe(body); expect(fetcher.mock.calls[1][1]?.body).toBe(fetcher.mock.calls[3][1]?.body);
  });
  it("403清晰保留HTTP状态且不传播远端detail", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(Response.json({ code: "connection_scope_forbidden", detail: "private-address", traceId: "trace" }, { status: 403 }));
    await expect(createConnectionsClient(fetcher).get("id")).rejects.toMatchObject({ status: 403, code: "connection_scope_forbidden", traceId: "trace" });
    await expect(createConnectionsClient(fetcher).get("id")).rejects.not.toThrow("private-address");
  });
});
