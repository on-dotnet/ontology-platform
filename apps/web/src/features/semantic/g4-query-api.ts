import { createPlatformClient, PlatformApiError } from "../../lib/api/client";
import type { G4SemanticQuery, G4SourceEvidenceView } from "../../lib/api/g4-generated";
import { decodeQueryResponse, type QueryResponse } from "./g4-query-model";

/** 查询引用和判别响应只保留在当前页面内存，刷新由服务器重新授权恢复。 */
export type QueryDelivery = { queryId: string; response: QueryResponse };

/** REST与MCP消费相同正式网关；此适配器只负责会话、防伪和封闭HTTP传输。 */
export function createG4QueryClient(fetcher: typeof fetch = globalThis.fetch) {
  const platform = createPlatformClient({ fetch: fetcher });
  async function request(path: string, method: "GET" | "POST", signal?: AbortSignal, body?: G4SemanticQuery, key?: string, selection?: string): Promise<Response> {
    const headers = new Headers({ Accept: "application/json" });
    if (method === "POST") {
      headers.set("X-CSRF-TOKEN", (await platform.csrf(signal)).requestToken);
      if (body) headers.set("Content-Type", "application/json");
    }
    if (key) headers.set("Idempotency-Key", key);
    if (selection) headers.set("X-Selection-Query-Id", selection);
    const response = await fetcher("/api/v1/data" + path, { method, headers, body: body ? JSON.stringify(body) : undefined,
      credentials: "same-origin", cache: "no-store", redirect: "error", signal });
    if (!response.ok) {
      const problem = await response.json().catch(() => ({})) as { code?: string; traceId?: string };
      throw new PlatformApiError(response.status, problem.code ?? "query_failed", problem.traceId);
    }
    return response;
  }
  async function delivery(response: Response): Promise<QueryDelivery> {
    const decoded = decodeQueryResponse(await response.json());
    const queryId = decoded.kind === "execution" ? decoded.view.queryId : response.headers.get("X-Query-Id");
    if (!queryId || !/^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/.test(queryId)) throw new PlatformApiError(502, "query_response_invalid");
    return { queryId, response: decoded };
  }
  return {
    execute: async (query: G4SemanticQuery, key: string, selection?: string, signal?: AbortSignal) =>
      delivery(await request("/semantic-queries", "POST", signal, query, key, selection)),
    result: async (queryId: string, signal?: AbortSignal) => delivery(await request(`/semantic-queries/${encodeURIComponent(queryId)}/result`, "GET", signal)),
    status: async (queryId: string, signal?: AbortSignal) => delivery(await request(`/semantic-queries/${encodeURIComponent(queryId)}`, "GET", signal)),
    cancel: async (queryId: string, signal?: AbortSignal) => delivery(await request(`/semantic-queries/${encodeURIComponent(queryId)}/cancel`, "POST", signal)),
    evidence: async (evidenceId: string, signal?: AbortSignal): Promise<G4SourceEvidenceView> => {
      const response = await request(`/source-evidence/${encodeURIComponent(evidenceId)}`, "GET", signal);
      const value = await response.json() as G4SourceEvidenceView;
      if (value?.schemaVersion !== "g4.source-evidence.v1" || !value.evidence || !value.receipt) throw new PlatformApiError(502, "query_response_invalid");
      return value;
    },
  };
}
