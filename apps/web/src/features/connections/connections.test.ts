import { createElement, isValidElement, type ReactNode } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import { configFromForm, formFromConfig, newForm, validateForm, type ConnectionForm, type ConnectionType } from "./form-model";
import { ConfigurationForm } from "./form";
import { CreateConnection } from "./create";
import ConnectionListPage from "../../app/data/connections/page";
import ConnectionDetailPage from "../../app/data/connections/[id]/page";
import type { PlatformIdentity } from "../../lib/api/generated";
import { ProbeReport, RequestError } from "./status";
import { CatalogPanel, CatalogSnapshot } from "./catalog";
import { createConnectionsClient } from "./api";
import { decodeDraft, encodeDraft, draftCacheKey } from "./draft-cache";
import { PlatformApiError } from "../../lib/api/client";
import type { CatalogDiscoveryJobView, CatalogSnapshotView, ConnectionProbeView, ConnectionView } from "../../lib/api/g4-generated";


/** 复用仓库 Node Hook 调度边界，实际组件事件与异常处理不被替换；不冒充浏览器验收。 */
const catalogHarness = vi.hoisted(() => {
  type Effect = { dependencies?: readonly unknown[]; cleanup?: void | (() => void) };
  const active: Host[] = [];
  class Host {
    slots: unknown[] = []; cursor = 0; effects: Array<() => void> = [];
    render<T>(component: () => T): T {
      active.push(this); this.cursor = 0; this.effects = [];
      let result: T;
      try { result = component(); } finally { active.pop(); }
      this.effects.forEach(effect => effect()); return result;
    }
    unmount() { for (const slot of this.slots) { const effect = slot as Effect | undefined; if (typeof effect?.cleanup === "function") effect.cleanup(); } }
  }
  function state<T>(initial: T | (() => T)): [T, (next: T | ((previous: T) => T)) => void] {
    const host = active.at(-1)!; const index = host.cursor++;
    if (!(index in host.slots)) host.slots[index] = typeof initial === "function" ? (initial as () => T)() : initial;
    return [host.slots[index] as T, next => { host.slots[index] = typeof next === "function" ? (next as (previous: T) => T)(host.slots[index] as T) : next; }];
  }
  function ref<T>(initial: T) { const [value] = state({ current: initial }); return value; }
  function effect(setup: () => void | (() => void), dependencies?: readonly unknown[]) {
    const host = active.at(-1)!; const index = host.cursor++; const previous = host.slots[index] as Effect | undefined;
    if (previous && dependencies && previous.dependencies?.length === dependencies.length && dependencies.every((value, offset) => Object.is(value, previous.dependencies![offset]))) return;
    const next: Effect = { dependencies }; host.slots[index] = next;
    host.effects.push(() => { if (typeof previous?.cleanup === "function") previous.cleanup(); next.cleanup = setup(); });
  }
  return { Host, state, ref, effect, active: () => active.length > 0, jobId: "", replace: vi.fn(), api: { get: vi.fn(), job: vi.fn(), catalogs: vi.fn(), catalog: vi.fn(), discover: vi.fn(), cancel: vi.fn() } };
});
vi.mock("react", async original => {
  const actual = await original<typeof import("react")>();
  return { ...actual,
    useState: <T,>(initial: T | (() => T)) => catalogHarness.active() ? catalogHarness.state(initial) : actual.useState(initial),
    useRef: <T,>(initial: T) => catalogHarness.active() ? catalogHarness.ref(initial) : actual.useRef(initial),
    useEffect: (setup: () => void | (() => void), dependencies?: readonly unknown[]) => catalogHarness.active() ? catalogHarness.effect(setup, dependencies) : actual.useEffect(setup, dependencies),
  };
});
vi.mock("./api", async original => {
  const actual = await original<typeof import("./api")>();
  return { ...actual, createConnectionsClient: (fetcher?: typeof fetch) => fetcher ? actual.createConnectionsClient(fetcher) : { ...actual.createConnectionsClient(), ...catalogHarness.api } };
});

// 仅提供路由 Hook 的组件测试边界；身份始终使用真实生成 DTO，不模拟 HTTP 授权通过。
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: catalogHarness.replace }),
  usePathname: () => "/data/connections",
  useSearchParams: () => new URLSearchParams(catalogHarness.jobId ? { job: catalogHarness.jobId } : {}),
  redirect: vi.fn(),
}));

const roleCases = [
  { label: "标准管理员", roles: ["platform.operator"], canManage: true },
  { label: "管理员兼审计", roles: ["platform.operator", "platform.auditor"], canManage: true },
  { label: "标准审计", roles: ["platform.auditor"], canManage: false },
  { label: "标准查看者", roles: ["platform.viewer"], canManage: false },
  { label: "不可信短角色名", roles: ["operator"], canManage: false },
  { label: "无角色", roles: [], canManage: false },
];

/** 与真实 /api/v1/platform/me 生成合同一致的合成身份。 */
function roleIdentity(roles: string[]): PlatformIdentity {
  return { subjectId: "synthetic-actor", displayName: "合成用户", roles, scopes: [{ organizationId: "org-demo", siteId: "site-a" }] };
}

describe("真实身份 DTO 的标准角色回归（组件检查，不替代 OIDC E2E）", () => {
  it.each(roleCases)("$label：列表入口与详情透传一致的管理权限", async ({ roles, canManage }) => {
    const identity = roleIdentity(roles);
    // 只调用路由的身份投影，不将 async Server Component 的完整渲染冒充浏览器验收。
    const list = ConnectionListPage().props.children(identity);
    const detail = (await ConnectionDetailPage({ params: Promise.resolve({ id: "synthetic-id" }) })).props.children(identity);
    expect(list.props.children.props.canManage).toBe(canManage);
    expect(detail.props.children.props.canManage).toBe(canManage);
    const html = renderToStaticMarkup(list);
    expect(html.includes('href="/data/connections/new"')).toBe(canManage);
  });
  it.each(roleCases)("$label：新建配置表单仅标准管理员可编辑", ({ roles, canManage }) => {
    const html = renderToStaticMarkup(createElement(CreateConnection, { identity: roleIdentity(roles) }));
    const configuration = html.match(/<fieldset\b[^>]*class="connection-fields"[^>]*>/)?.[0];
    expect(configuration).toBeDefined();
    expect(configuration?.includes('disabled=""')).toBe(!canManage);
    expect(html.includes("您拥有只读访问权限，不能新建连接。")).toBe(!canManage);
  });
});

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


describe("非敏草稿刷新隔离", () => {
  it("仅白名单表单输入往返，不序列化混入的密码/引用", () => {
    const form = { ...validForms.POSTGRESQL, values: { ...validForms.POSTGRESQL.values, secretValue: "never-store", secretRef: "never-ref" } };
    const encoded = encodeDraft(form); expect(encoded).not.toContain("never-"); expect(decodeDraft(encoded)).toEqual(validForms.POSTGRESQL);
  });
  it("无效URL中的内嵌凭据不能进入非敏缓存", () => {
    const form = { ...validForms.TDENGINE, values: { ...validForms.TDENGINE.values, wsUrl: "wss://user:private-password@host/ws" } };
    expect(encodeDraft(form)).not.toContain("private-password");
  });
  it("拒绝多余字段和未知类型的本地缓存", () => {
    expect(decodeDraft('{"type":"UNKNOWN","displayName":"x","values":{}}')).toBeNull();
    expect(decodeDraft(JSON.stringify({ ...validForms.POSTGRESQL, secretRef: "extra" }))).toBeNull();
  });
  it("身份、角色与scope变化不能读取原缓存键", () => {
    const identity = { subjectId: "user", displayName: "用户", roles: ["platform.operator"], scopes: [{ organizationId: "org", siteId: "one" }] };
    expect(draftCacheKey(identity)).not.toEqual(draftCacheKey({ ...identity, roles: ["platform.viewer"] }));
    expect(draftCacheKey(identity)).not.toEqual(draftCacheKey({ ...identity, scopes: [] }));
  });
});


describe("冻结完整诊断码与误贴凭据拒绝回归", () => {
  const cases = [
    ["connection_tls_untrusted", "证书或服务器身份不可信", 422],
    ["connection_auth_failed", "源账号认证失败", 422],
    ["connection_readonly_unverified", "无法证明源账号仅有只读权限", 422],
    ["connection_source_unavailable", "源服务暂不可用", 503],
  ] as const;
  it.each(cases)("%s HTTP错误显示独立安全诊断", (code, expected, status) => {
    const html = renderToStaticMarkup(createElement(RequestError, { error: new PlatformApiError(status, code) }));
    expect(html).toContain(expected);
    expect(html).not.toContain("配置或凭据未通过验证");
  });
  it.each(cases)("%s 失败Probe不伪造通过或泄露原异常", (code, expected) => {
    const probe = { status: "TEST_FAILED", stages: [{ name: "AUTH", status: "FAIL", durationMs: 1, diagnosticCode: code }], stale: false } as ConnectionProbeView;
    const html = renderToStaticMarkup(createElement(ProbeReport, { probe }));
    expect(html).toContain(expected); expect(html).toContain("测试失败"); expect(html).not.toContain("测试通过");
    expect(html.match(/未验证/g)).toHaveLength(4);
  });
  it("未知诊断不回显任意异常正文", () => {
    const probe = { status: "TEST_FAILED", stages: [{ name: "AUTH", status: "FAIL", durationMs: 1, diagnosticCode: "Password=must-not-display" }], stale: false } as ConnectionProbeView;
    const html = renderToStaticMarkup(createElement(ProbeReport, { probe }));
    expect(html).not.toContain("must-not-display"); expect(html).toContain("此阶段未通过");
  });
  it.each([
    ["POSTGRESQL", "host", "Host=pg-source;Username=reader;Password=private-password"],
    ["ORACLE", "host", "Data Source=oracle;User Id=reader;Pwd=private-password"],
    ["DORIS", "feHost", "mysql://reader:private-password@doris"],
    ["POSTGRESQL", "database", "Password=private-password"],
  ])("%s %s误贴连接串不会写入或恢复", (type, key, value) => {
    const original = validForms[type as ConnectionType];
    const form = { ...original, values: { ...original.values, [key]: value } };
    expect(encodeDraft(form)).not.toContain("private-password");
    expect(decodeDraft(JSON.stringify(form))?.values[key]).toBe("");
  });
});


describe("URL草稿缓存不持久化查询参数或片段", () => {
  const cases = ["token", "access_token", "password"].flatMap(key => [
    `?${key}=synthetic-secret`, `?locale=zh&${key}=synthetic-secret`, `#${key}=synthetic-secret`,
  ]);
  it.each(cases)("TDengine %s仅留内存，读写缓存都拒绝", suffix => {
    const form = { ...validForms.TDENGINE, values: { ...validForms.TDENGINE.values, wsUrl: `wss://td.example/ws${suffix}` } };
    expect(validateForm(form)).toEqual({});
    expect(encodeDraft(form)).not.toContain("synthetic-secret");
    expect(decodeDraft(JSON.stringify(form))?.values.wsUrl).toBe("");
    expect(form.values.wsUrl).toContain(suffix);
  });
  it.each(["baseOrigin", "approvedPath"])("Web API %s所有query/fragment均不缓存", key => {
    for (const suffix of ["?token=synthetic-secret", "#password=synthetic-secret", "?locale=zh", "#section", "?", "#"]) {
      const form = { ...validForms.WEB_API, values: { ...validForms.WEB_API.values, [key]: `${key === "baseOrigin" ? "https://api.example" : "/fixture"}${suffix}` } };
      expect(JSON.parse(encodeDraft(form)).values[key]).toBe("");
      expect(decodeDraft(JSON.stringify(form))?.values[key]).toBe("");
      expect(form.values[key]).toContain(suffix);
    }
  });
  it("不含query/fragment/userinfo的URL可保留", () => {
    expect(decodeDraft(encodeDraft(validForms.TDENGINE))).toEqual(validForms.TDENGINE);
    expect(decodeDraft(encodeDraft(validForms.WEB_API))).toEqual(validForms.WEB_API);
  });
});

/** 已授权任务与源目录分别返回，测试仅验证真实组件在这些输入下的状态清理。 */
describe("目录拒绝后的任务诊断与权限重验（组件回归）", () => {
  const connection = { id: "connection", state: "ACTIVE", probeFresh: true } as ConnectionView;
  const job = { jobId: "job", connectionId: "connection", status: "PARTIAL", createdAtUtc: "2026-11-01", traceId: "safe-trace" } as CatalogDiscoveryJobView;
  const snapshot = { snapshotId: "snapshot", status: "SUCCEEDED", capturedAtUtc: "2026-11-01", configRevision: 1, schemaFingerprint: "safe-hash", objects: [{ schema: "production", name: "old-private-table", kind: "TABLE", fields: [] }] } as unknown as CatalogSnapshotView;
  async function settle() { for (let index = 0; index < 30; index++) await Promise.resolve(); }
  function elements(node: ReactNode): Array<React.ReactElement<Record<string, unknown>>> {
    if (Array.isArray(node)) return node.flatMap(elements);
    if (!isValidElement<Record<string, unknown>>(node)) return [];
    return [node, ...elements(node.props.children as ReactNode)];
  }
  function setup(jobId = "job") {
    catalogHarness.jobId = jobId; catalogHarness.replace.mockReset();
    for (const mock of Object.values(catalogHarness.api)) mock.mockReset();
    catalogHarness.api.get.mockResolvedValue({ data: connection });
    catalogHarness.api.job.mockResolvedValue({ data: job });
    catalogHarness.api.catalogs.mockRejectedValue(new PlatformApiError(403, "catalog_access_forbidden"));
    const host = new catalogHarness.Host(); const onDenied = vi.fn();
    const render = () => host.render(() => CatalogPanel({ connection, etag: '"1"', canManage: true, onDenied }));
    return { host, onDenied, render, html: () => renderToStaticMarkup(render()) };
  }
  it("源目录403后重新授权连接和任务，显示PARTIAL但不恢复目录", async () => {
    const view = setup(); view.render(); await settle();
    const html = view.html();
    expect(catalogHarness.api.get).toHaveBeenCalledWith("connection", expect.any(AbortSignal));
    expect(catalogHarness.api.job.mock.calls.length).toBeGreaterThan(1);
    expect(html).toContain("发现未完整完成"); expect(html).not.toContain("目录快照历史");
    expect(view.onDenied).not.toHaveBeenCalled(); view.host.unmount();
  });
  it("重验任务仍RUNNING时保留显式继续入口，不假称PARTIAL", async () => {
    const view = setup(); catalogHarness.api.job.mockResolvedValue({ data: { ...job, status: "RUNNING" } });
    view.render(); await settle(); const html = view.html();
    expect(html).toContain("继续读取任务状态"); expect(html).not.toContain("发现未完整完成");
    expect(view.onDenied).not.toHaveBeenCalled(); view.host.unmount();
  });
  it.each(["connection", "job"])("%s 重验403必须全清并向父页拒绝", async kind => {
    const view = setup();
    if (kind === "connection") catalogHarness.api.get.mockRejectedValue(new PlatformApiError(403, "connection_scope_forbidden"));
    else catalogHarness.api.job.mockResolvedValueOnce({ data: job }).mockRejectedValue(new PlatformApiError(403, "connection_scope_forbidden"));
    view.render(); await settle();
    expect(view.onDenied).toHaveBeenCalled(); expect(view.html()).not.toContain("发现未完整完成"); view.host.unmount();
  });
  it.each([[401, "authentication_required"], [403, "connection_scope_forbidden"], [403, "unknown_forbidden"]])("目录HTTP %s/%s不能降级为源ACL拒绝", async (status, code) => {
    const view = setup(); catalogHarness.api.catalogs.mockRejectedValue(new PlatformApiError(Number(status), String(code)));
    view.render(); await settle();
    expect(view.onDenied).toHaveBeenCalled(); expect(catalogHarness.api.get).not.toHaveBeenCalled();
    expect(view.html()).not.toContain("发现未完整完成"); view.host.unmount();
  });
  it.each([true, false])("无jobId时仍重验连接，授权结果=%s", async allowed => {
    const view = setup("");
    if (!allowed) catalogHarness.api.get.mockRejectedValue(new PlatformApiError(403, "connection_scope_forbidden"));
    view.render(); await settle();
    expect(catalogHarness.api.get).toHaveBeenCalledTimes(1); expect(catalogHarness.api.job).not.toHaveBeenCalled();
    expect(view.onDenied.mock.calls.length > 0).toBe(!allowed); view.host.unmount();
  });
  it("重验发现连接已禁用时不能保留任务或目录", async () => {
    const view = setup(); catalogHarness.api.get.mockResolvedValue({ data: { ...connection, state: "DISABLED" } });
    view.render(); await settle(); expect(view.onDenied).toHaveBeenCalled(); expect(view.html()).not.toContain("发现未完整完成"); view.host.unmount();
  });
  it("目录被拒绝后立即清空此前成功显示的快照和历史", async () => {
    const view = setup(""); catalogHarness.api.catalogs.mockResolvedValue({ data: { items: [snapshot], nextCursor: null } });
    catalogHarness.api.catalog.mockResolvedValueOnce({ data: snapshot }).mockRejectedValue(new PlatformApiError(403, "catalog_access_forbidden"));
    view.render(); await settle();
    const clickSnapshot = () => { const button = elements(view.render()).find(element => element.type === "button" && String(element.props.children).includes("个对象")); expect(button).toBeDefined(); (button!.props.onClick as () => void)(); };
    clickSnapshot(); await settle(); expect(view.html()).toContain("old-private-table");
    clickSnapshot(); await settle(); const html = view.html();
    expect(html).not.toContain("old-private-table"); expect(html).not.toContain("目录快照历史"); expect(view.onDenied).not.toHaveBeenCalled(); view.host.unmount();
  });
  it("卸载后迟到的连接重验响应不得触发任务读取或恢复投影", async () => {
    const view = setup(); let complete!: (value: unknown) => void;
    catalogHarness.api.get.mockReturnValue(new Promise(resolve => { complete = resolve; }));
    view.render(); await settle(); const jobCalls = catalogHarness.api.job.mock.calls.length;
    view.host.unmount(); const slots = [...view.host.slots]; complete({ data: connection }); await settle();
    expect(catalogHarness.api.job).toHaveBeenCalledTimes(jobCalls); expect(view.host.slots).toEqual(slots); expect(view.onDenied).not.toHaveBeenCalled();
  });
  it.each(["discover", "cancel"])("%s旧命令晚于目录401返回时不得恢复任务或路由", async operation => {
    const view = setup(operation === "discover" ? "" : "job");
    let rejectCatalog!: (cause: Error) => void; let completeCommand!: (value: unknown) => void;
    catalogHarness.api.catalogs.mockReturnValue(new Promise((_, reject) => { rejectCatalog = reject; }));
    catalogHarness.api.job.mockResolvedValue({ data: { ...job, status: "RUNNING" } });
    catalogHarness.api[operation as "discover" | "cancel"].mockReturnValue(new Promise(resolve => { completeCommand = resolve; }));
    view.render(); await settle();
    const label = operation === "discover" ? "发现目录" : "取消发现";
    const button = elements(view.render()).find(element => element.type === "button" && element.props.children === label)!;
    expect(button.props.disabled).toBe(false); (button.props.onClick as () => void)();
    rejectCatalog(new PlatformApiError(401, "authentication_required")); await settle();
    completeCommand({ data: job }); await settle();
    const html = view.html(); expect(html).not.toContain("发现未完整完成"); expect(html).not.toContain("恢复上次目录操作结果");
    expect(view.onDenied).toHaveBeenCalled(); expect(catalogHarness.replace).not.toHaveBeenCalled(); view.host.unmount();
  });
  it("旧发现失败晚于源目录拒绝重验时不得覆盖新的权限错误", async () => {
    const view = setup(""); let rejectCatalog!: (cause: Error) => void; let rejectCommand!: (cause: Error) => void;
    catalogHarness.api.catalogs.mockReturnValue(new Promise((_, reject) => { rejectCatalog = reject; }));
    catalogHarness.api.discover.mockReturnValue(new Promise((_, reject) => { rejectCommand = reject; }));
    view.render(); await settle();
    const button = elements(view.render()).find(element => element.type === "button" && element.props.children === "发现目录")!;
    (button.props.onClick as () => void)(); rejectCatalog(new PlatformApiError(403, "catalog_access_forbidden")); await settle();
    rejectCommand(new PlatformApiError(503, "request_failed")); await settle();
    const html = view.html(); expect(html).toContain("没有访问权限"); expect(html).not.toContain("服务暂不可用");
    expect(view.onDenied).not.toHaveBeenCalled(); expect(catalogHarness.replace).not.toHaveBeenCalled(); view.host.unmount();
  });
  it("目录401后迟到的旧任务成功不得重新恢复诊断", async () => {
    const view = setup(); let complete!: (value: unknown) => void;
    catalogHarness.api.catalogs.mockRejectedValue(new PlatformApiError(401, "authentication_required"));
    catalogHarness.api.job.mockReturnValue(new Promise(resolve => { complete = resolve; }));
    view.render(); await settle(); complete({ data: job }); await settle();
    expect(view.onDenied).toHaveBeenCalled(); expect(view.html()).not.toContain("发现未完整完成"); view.host.unmount();
  });
});
