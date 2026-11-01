import { createPlatformClient, PlatformApiError } from "../../lib/api/client";
import type { PlatformProblem } from "../../lib/api/generated";
import type * as G4 from "../../lib/api/g4-generated";
/** G4独立传输适配，DTO仅从真实OpenAPI生成，完整ETag保持原样。 */
export function createConnectionsClient(fetcher: typeof fetch = globalThis.fetch) {
  const platform = createPlatformClient({ fetch: fetcher });
  async function request<T>(path: string, body?: object, etag?: string, method = "POST", signal?: AbortSignal): Promise<{ data: T; etag: string }> {
    const headers = new Headers({ Accept: "application/json" });
    if (body) {
      const csrf = await platform.csrf(signal);
      headers.set("Content-Type", "application/json");
      headers.set("X-CSRF-TOKEN", csrf.requestToken);
      if (etag) headers.set("If-Match", etag);
    }
    const response = await fetcher(`/api/v1${path}`, { method: body ? method : "GET", headers, body: body ? JSON.stringify(body) : undefined, credentials: "same-origin", cache: "no-store", redirect: "error", signal });
    if (!response.ok) {
      const problem: Partial<PlatformProblem> = await response.json().catch(() => ({}));
      throw new PlatformApiError(response.status, problem.code ?? "request_failed", problem.traceId);
    }
    const data: T = await response.json().catch(() => { throw new PlatformApiError(response.status, "invalid_response"); });
    if (!data) throw new PlatformApiError(response.status, "invalid_response");
    return { data, etag: response.headers.get("ETag") ?? "" };
  }
  const id = encodeURIComponent;
  return {
    list: (query: string, signal?: AbortSignal) => request<G4.ConnectionListPage>(`/connections${query ? `?${query}` : ""}`, undefined, undefined, undefined, signal),
    get: (connectionId: string, signal?: AbortSignal) => request<G4.ConnectionView>(`/connections/${id(connectionId)}`, undefined, undefined, undefined, signal),
    intake: (body: G4.ConnectionSecretIntakeRequest) => request<G4.SecretIntakeReceipt>("/connection-secrets", body),
    draftProbe: (body: G4.ConnectionDraftProbeRequest) => request<G4.ConnectionProbeView>("/connections/tests", body),
    create: (body: G4.ConnectionCreateRequest) => request<G4.ConnectionView>("/connections", body),
    patch: (connectionId: string, body: G4.ConnectionPatchRequest, etag: string) => request<G4.ConnectionView>(`/connections/${id(connectionId)}`, body, etag, "PATCH"),
    rotate: (connectionId: string, body: G4.ConnectionRotateSecretRequest, etag: string) => request<G4.ConnectionView>(`/connections/${id(connectionId)}/rotate-secret`, body, etag),
    test: (connectionId: string, body: G4.ConnectionMutationCommand, etag: string) => request<G4.ConnectionProbeView>(`/connections/${id(connectionId)}/test`, body, etag),
    probe: (connectionId: string, probeId: string, signal?: AbortSignal) => request<G4.ConnectionProbeView>(`/connections/${id(connectionId)}/probes/${id(probeId)}`, undefined, undefined, undefined, signal),
    transition: (connectionId: string, action: "enable" | "disable", body: G4.ConnectionMutationCommand, etag: string) => request<G4.ConnectionView>(`/connections/${id(connectionId)}/${action}`, body, etag),
    discover: (connectionId: string, body: G4.ConnectionMutationCommand, etag: string) => request<G4.CatalogDiscoveryJobView>(`/connections/${id(connectionId)}/discoveries`, body, etag),
    job: (connectionId: string, jobId: string, signal?: AbortSignal) => request<G4.CatalogDiscoveryJobView>(`/connections/${id(connectionId)}/discoveries/${id(jobId)}`, undefined, undefined, undefined, signal),
    cancel: (connectionId: string, jobId: string, body: G4.ConnectionMutationCommand, etag: string) => request<G4.CatalogDiscoveryJobView>(`/connections/${id(connectionId)}/discoveries/${id(jobId)}/cancel`, body, etag),
    catalogs: (connectionId: string, cursor = "", signal?: AbortSignal) => request<G4.CatalogSnapshotListPage>(`/connections/${id(connectionId)}/catalogs${cursor ? `?cursor=${id(cursor)}` : ""}`, undefined, undefined, undefined, signal),
    catalog: (snapshotId: string, signal?: AbortSignal) => request<G4.CatalogSnapshotView>(`/catalogs/${id(snapshotId)}`, undefined, undefined, undefined, signal),
  };
}
