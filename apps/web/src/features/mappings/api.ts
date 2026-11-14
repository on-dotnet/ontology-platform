import { createPlatformClient, PlatformApiError } from "../../lib/api/client";
import type * as G4 from "../../lib/api/g4-generated";

/** 复核失败携带当前有权用户可读取的固定checkId，不包含源异常。 */
export class MappingApiError extends PlatformApiError {
  constructor(status: number, code: string, traceId?: string, public readonly checkId?: string) {
    super(status, code, traceId);
  }
}

/** DTO只来自实际Host OpenAPI；会话、防伪与ETag沿平台既有边界。 */
export function createMappingsClient(fetcher: typeof fetch = globalThis.fetch) {
  const platform = createPlatformClient({ fetch: fetcher });
  async function request<T>(path: string, body?: object, etag?: string, method = "POST", signal?: AbortSignal): Promise<{ data: T; etag: string }> {
    const headers = new Headers({ Accept: "application/json" });
    if (body) {
      const csrf = await platform.csrf(signal);
      headers.set("Content-Type", "application/json");
      headers.set("X-CSRF-TOKEN", csrf.requestToken);
      if (etag) headers.set("If-Match", etag);
    }
    const response = await fetcher(`/api/v1${path}`, { method: body ? method : "GET", headers,
      body: body ? JSON.stringify(body) : undefined, credentials: "same-origin", cache: "no-store", redirect: "error", signal });
    if (!response.ok) {
      const problem = await response.json().catch(() => ({})) as { code?: string; traceId?: string; checkId?: string };
      throw new MappingApiError(response.status, problem.code ?? "mapping_request_failed", problem.traceId, problem.checkId);
    }
    const data = await response.json() as T;
    if (!data) throw new MappingApiError(502, "mapping_response_invalid");
    return { data, etag: response.headers.get("ETag") ?? "" };
  }
  const id = encodeURIComponent;
  const query = (values: Record<string, string | number | undefined>) => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(values)) if (value !== undefined) params.set(key, String(value));
    return params.size ? `?${params}` : "";
  };
  return {
    list: (cursor?: string, signal?: AbortSignal) => request<G4.MappingPageOfMappingListItem>(`/mappings${query({ cursor })}`, undefined, undefined, undefined, signal),
    create: (body: G4.MappingDraftCreateRequest) => request<G4.MappingDraftView>("/mappings", body),
    draft: (mappingId: string, signal?: AbortSignal) => request<G4.MappingDraftView>(`/mappings/${id(mappingId)}`, undefined, undefined, undefined, signal),
    revision: (mappingId: string, revision: number, signal?: AbortSignal) => request<G4.MappingDraftView>(`/mappings/${id(mappingId)}/revisions/${revision}`, undefined, undefined, undefined, signal),
    patch: (mappingId: string, body: G4.MappingDraftPatchRequest, etag: string) => request<G4.MappingDraftView>(`/mappings/${id(mappingId)}`, body, etag, "PATCH"),
    suggest: (mappingId: string, body: G4.MappingSuggestionRequest, etag: string) => request<G4.MappingSuggestionView>(`/mappings/${id(mappingId)}/suggestions`, body, etag),
    validate: (mappingId: string, body: G4.MappingValidateRequest, etag: string) => request<G4.MappingJobView>(`/mappings/${id(mappingId)}/validate`, body, etag),
    job: (jobId: string, signal?: AbortSignal) => request<G4.MappingJobView>(`/mapping-jobs/${id(jobId)}`, undefined, undefined, undefined, signal),
    cancelJob: (jobId: string, body: G4.MappingCommandRequest, etag: string) => request<G4.MappingJobView>(`/mapping-jobs/${id(jobId)}/cancel`, body, etag),
    assessment: (assessmentId: string, signal?: AbortSignal) => request<G4.MappingAssessmentView>(`/mapping-assessments/${id(assessmentId)}`, undefined, undefined, undefined, signal),
    assessments: (mappingId: string, revision?: number, targetReleaseId?: string, cursor?: string, signal?: AbortSignal) => request<G4.MappingPageOfMappingAssessmentView>(`/mappings/${id(mappingId)}/assessments${query({ revision, targetReleaseId, cursor })}`, undefined, undefined, undefined, signal),
    propose: (mappingId: string, body: G4.MappingProposalCreateRequest) => request<G4.MappingProposalView>(`/mappings/${id(mappingId)}/proposals`, body),
    proposals: (status?: string, cursor?: string, signal?: AbortSignal) => request<G4.MappingPageOfMappingProposalView>(`/mapping-proposals${query({ status, cursor })}`, undefined, undefined, undefined, signal),
    proposal: (proposalId: string, signal?: AbortSignal) => request<G4.MappingProposalView>(`/mapping-proposals/${id(proposalId)}`, undefined, undefined, undefined, signal),
    decide: (proposalId: string, body: G4.MappingDecisionRequest, etag: string) => request<G4.MappingProposalView>(`/mapping-proposals/${id(proposalId)}/decisions`, body, etag),
    cancelProposal: (proposalId: string, body: G4.MappingCommandRequest, etag: string) => request<G4.MappingProposalView>(`/mapping-proposals/${id(proposalId)}/cancel`, body, etag),
    activate: (proposalId: string, body: G4.MappingActivationRequest, etag: string) => request<G4.MappingActivationReceipt>(`/mapping-proposals/${id(proposalId)}/activate`, body, etag),
    checks: (proposalId: string, cursor?: string, signal?: AbortSignal) => request<G4.MappingPageOfMappingActivationCheck>(`/mapping-proposals/${id(proposalId)}/activation-checks${query({ cursor })}`, undefined, undefined, undefined, signal),
    releases: (mappingId: string, cursor?: string, signal?: AbortSignal) => request<G4.MappingPageOfMappingReleaseView>(`/mapping-releases${query({ mappingId, cursor })}`, undefined, undefined, undefined, signal),
    release: (releaseId: string, signal?: AbortSignal) => request<G4.MappingReleaseView>(`/mapping-releases/${id(releaseId)}`, undefined, undefined, undefined, signal),
    active: (mappingId: string, signal?: AbortSignal) => request<G4.MappingActiveView>(`/mappings/${id(mappingId)}/active`, undefined, undefined, undefined, signal),
    diff: (mappingId: string, fromRevision: number, toRevision: number, signal?: AbortSignal) => request<G4.MappingDiffView>(`/mappings/${id(mappingId)}/diff${query({ fromRevision, toRevision })}`, undefined, undefined, undefined, signal),
    releaseDiff: (mappingId: string, fromReleaseId: string, toReleaseId: string, signal?: AbortSignal) => request<G4.MappingDiffView>(`/mappings/${id(mappingId)}/release-diff${query({ fromReleaseId, toReleaseId })}`, undefined, undefined, undefined, signal),
  };
}
