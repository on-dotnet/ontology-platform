import type { CsrfResponse, PlatformAuditEntry, PlatformIdentity, PlatformProblem, PlatformResourceList } from "./generated";
/** 保留 HTTP 状态和安全关联标识，不将远端 detail 或异常原文直接交给页面。 */
export class PlatformApiError extends Error {
  constructor(public readonly status: number, public readonly code: string, public readonly traceId?: string) { super(`平台请求失败 (${status})`); this.name = "PlatformApiError"; }
}
/** 内置 fetch 适配层；生成类型和请求行为分离，支持 SSR Cookie 与取消。 */
export function createPlatformClient(options: { origin?: string; headers?: HeadersInit; fetch?: typeof fetch } = {}) {
  const fetcher = options.fetch ?? globalThis.fetch;
  async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
    const response = await fetcher(`${options.origin ?? ""}${path}`, { headers: { Accept: "application/json", ...options.headers }, credentials: "same-origin", cache: "no-store", redirect: "error", signal });
    if (!response.ok) {
      const problem: Partial<PlatformProblem> = await response.json().catch(() => ({}));
      throw new PlatformApiError(response.status, problem.code ?? "request_failed", problem.traceId);
    }
    const result = await response.json().catch(() => { throw new PlatformApiError(response.status, "invalid_response"); });
    if (result == null) throw new PlatformApiError(response.status, "invalid_response");
    return result as T;
  }
  return {
    me: (signal?: AbortSignal) => request<PlatformIdentity>("/api/v1/platform/me", signal),
    resources: (siteId?: string, signal?: AbortSignal) => request<PlatformResourceList>(`/api/v1/platform/resources${siteId ? `?siteId=${encodeURIComponent(siteId)}` : ""}`, signal),
    audit: (signal?: AbortSignal) => request<PlatformAuditEntry[]>("/api/v1/platform/audit?limit=20", signal),
    csrf: (signal?: AbortSignal) => request<CsrfResponse>("/auth/csrf", signal),
  };
}
