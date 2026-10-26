import { createPlatformClient, PlatformApiError } from "./client";
import type { PlatformProblem } from "./generated";
import type * as G2 from "./g2-generated";
/** 复用已验证BFF身份和CSRF；所有业务载荷来自唯一生成合同。 */
export function createG2Client(options: { fetch?: typeof fetch } = {}) {
  const fetcher = options.fetch ?? globalThis.fetch;
  const platform = createPlatformClient({ fetch: fetcher });
  /** 同源请求保留真实ProblemDetails状态；不重试任何业务写入。 */
  async function response(path: string, init: RequestInit = {}) {
    const result = await fetcher(`/api/v1${path}`, { ...init, credentials: "same-origin", cache: "no-store", redirect: "error" });
    if (!result.ok) {
      const problem: Partial<PlatformProblem> = await result.json().catch(() => ({}));
      throw new PlatformApiError(result.status, problem.code ?? "request_failed", problem.traceId);
    }
    return result;
  }
  /** 解析非空JSON，禁止把源故障或空响应当作成功。 */
  async function read<T>(path: string, signal?: AbortSignal): Promise<T> {
    const result = await response(path, { signal, headers: { Accept: "application/json" } });
    const data = await result.json().catch(() => { throw new PlatformApiError(result.status, "invalid_response"); });
    if (data == null) throw new PlatformApiError(result.status, "invalid_response");
    return data as T;
  }
  /** 每次显式写入取得原防伪令牌；CAS直接取同一Command.expectedRevision。 */
  async function write<T>(path: string, body: object, method = "POST", revision?: number, signal?: AbortSignal): Promise<T> {
    const csrf = await platform.csrf(signal);
    const headers = new Headers({ Accept: "application/json", "Content-Type": "application/json", "X-CSRF-TOKEN": csrf.requestToken });
    if (revision !== undefined) headers.set("If-Match", `"${revision}"`);
    const result = await response(path, { method, headers, body: JSON.stringify(body), signal });
    const data = await result.json().catch(() => { throw new PlatformApiError(result.status, "invalid_response"); });
    if (data == null) throw new PlatformApiError(result.status, "invalid_response");
    return data as T;
  }
  const id = encodeURIComponent;
  return {
    drafts: (signal?: AbortSignal) => read<G2.OntologyDraft[]>("/ontology-drafts", signal),
    draft: (draftId: string, signal?: AbortSignal) => read<G2.OntologyDraft>(`/ontology-drafts/${id(draftId)}`, signal),
    createDraft: (body: G2.CreateDraftRequest, signal?: AbortSignal) => write<G2.OntologyDraft>("/ontology-drafts", body, "POST", undefined, signal),
    saveDraft: (draftId: string, body: G2.SaveDraftRequest, signal?: AbortSignal) => write<G2.OntologyDraft>(`/ontology-drafts/${id(draftId)}`, body, "PUT", body.command.expectedRevision, signal),
    editDraft: (draftId: string, body: G2.EditDraftRequest, signal?: AbortSignal) => write<G2.OntologyDraft>(`/ontology-drafts/${id(draftId)}/edits`, body, "POST", body.command.expectedRevision, signal),
    validateDraft: (draftId: string, body: G2.ValidateDraftRequest, signal?: AbortSignal) => write<G2.SemanticValidationReport>(`/ontology-drafts/${id(draftId)}/validations`, body, "POST", undefined, signal),
    diff: (draftId: string, fromRevision: number, signal?: AbortSignal) => read<G2.DraftDiff>(`/ontology-drafts/${id(draftId)}/diff?fromRevision=${fromRevision}`, signal),
    proposals: (signal?: AbortSignal) => read<G2.ReleaseProposal[]>("/release-proposals", signal),
    createProposal: (body: G2.CreateProposalRequest, signal?: AbortSignal) => write<G2.ReleaseProposal>("/release-proposals", body, "POST", undefined, signal),
    decide: (proposalId: string, body: G2.ApprovalDecisionRequest, signal?: AbortSignal) => write<G2.ReleaseProposal>(`/approvals/${id(proposalId)}/decisions`, body, "POST", body.command.expectedRevision, signal),
    releases: (signal?: AbortSignal) => read<G2.ReleaseSummary[]>("/releases", signal),
    release: (releaseId: string, signal?: AbortSignal) => read<G2.ReleaseSummary>(`/releases/${id(releaseId)}`, signal),
    activate: (body: G2.ActivateReleaseRequest, signal?: AbortSignal) => write<G2.ReleaseActivation>("/release-activations", body, "POST", body.command.expectedRevision, signal),
    capabilities: (signal?: AbortSignal) => read<G2.SemanticCapability[]>("/capabilities", signal),
    discover: (assetId: string, releaseId: string | null, signal?: AbortSignal) => read<G2.SemanticQueryResult>(`/semantic/discover?assetId=${id(assetId)}${releaseId ? `&releaseId=${id(releaseId)}` : ""}`, signal),
    query: (body: G2.SemanticQueryPlan, signal?: AbortSignal) => write<G2.SemanticQueryResult>("/semantic/queries", body, "POST", undefined, signal),
    evidence: (evidenceId: string, signal?: AbortSignal) => read<G2.EvidenceRef>(`/evidence/${id(evidenceId)}`, signal),
    runs: (signal?: AbortSignal) => read<G2.ExecutionRun[]>("/execution-runs", signal),
    run: (runId: string, signal?: AbortSignal) => read<G2.ExecutionRun>(`/execution-runs/${id(runId)}`, signal),
    createRun: (body: G2.CreateRunRequest, signal?: AbortSignal) => write<G2.ExecutionRun>("/execution-runs", body, "POST", undefined, signal),
    cancelRun: (runId: string, body: G2.CancelRunRequest, signal?: AbortSignal) => write<G2.ExecutionRun>(`/execution-runs/${id(runId)}/cancel`, body, "POST", body.command.expectedRevision, signal),
    events: async (runId: string, lastEventId: string | null, signal: AbortSignal) => {
      const headers = new Headers({ Accept: "text/event-stream" });
      if (lastEventId) headers.set("Last-Event-ID", lastEventId);
      const result = await response(`/execution-runs/${id(runId)}/events`, { headers, signal });
      if (!result.headers.get("Content-Type")?.includes("text/event-stream") || !result.body) throw new PlatformApiError(200, "invalid_event_stream");
      return result.body;
    },
  };
}
/** 新命令仅在用户触发时创建；明确重试时复用原完整请求对象。 */
export function command(expectedRevision: number, reason: string): G2.CommandContext {
  return { commandId: crypto.randomUUID(), idempotencyKey: crypto.randomUUID(), expectedRevision, reason };
}
