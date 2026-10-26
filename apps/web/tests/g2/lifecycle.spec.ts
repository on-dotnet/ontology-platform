import { expect, test } from "@playwright/test";
import type { AssetVersionSnapshot, EvidenceRef, ExecutionRun, ReleaseManifest, ReleaseProposal, ReleaseSummary, SemanticCapability, SemanticQueryResult } from "../../src/lib/api/g2-generated";
const hash = "b".repeat(64);
const scope = { organizationId: "org-demo", siteIds: ["site-a"] };
const snapshot: AssetVersionSnapshot = { releaseId: "release-ui", ontologyHash: hash, shapesHash: hash, vocabularyHash: null, dataHash: hash, ontologyGraphIri: "urn:release:ontology", dataGraphIri: "urn:release:data", mappingVersions: [], metricVersions: [], ruleVersions: [], capabilityVersions: [{ assetId: "describe_ontology", version: hash }] };
const manifest: ReleaseManifest = { schemaVersion: 1, releaseId: "release-ui", assetId: "asset-ui", scope, draftId: "draft-ui", revision: 2, hashes: { ontologyHash: hash, shapesHash: hash, vocabularyHash: null, dataHash: hash, bundleHash: hash }, ontologyGraphIri: snapshot.ontologyGraphIri, dataGraphIri: snapshot.dataGraphIri, importLocks: [], snapshot, artifactObjects: [], createdAtUtc: "2026-10-26T00:00:00Z" };
const release: ReleaseSummary = { manifest, manifestHash: hash, isActive: true, activationRevision: 1, status: "ACTIVE" };
const capability: SemanticCapability = { id: "describe_ontology", version: hash, inputSchema: { schemaVersion: 1, type: "object", required: ["assetId"], properties: [], additionalProperties: false }, outputSchema: {}, meaning: "读取正式本体Schema", policy: "semantic.read", executorId: "registered", budgets: { maxDepth: 5, maxRows: 100, timeoutMs: 5000, maxToolCalls: 3 } };
const evidence: EvidenceRef = { evidenceId: "evidence-ui", releaseId: "release-ui", scope, graphIri: "urn:release:data", subjectIri: "urn:synthetic:entity", predicateIri: "urn:synthetic:value", objectTerm: { kind: "literal", value: "Synthetic", datatype: null, language: null }, sourceId: "Synthetic", sourceRecordId: "record-ui", sourceObjectKey: "immutable-key", contentHash: hash, validFromUtc: "2026-10-25T00:00:00Z", validToUtc: null, observedAtUtc: "2026-10-26T00:00:00Z", modelVersion: hash, mappingVersion: null, synthetic: true };
const baseResult: SemanticQueryResult = { status: "FOUND", data: [{ kind: "entity", ontology: null, relationship: null, entity: { iri: "urn:synthetic:entity", typeIris: ["urn:synthetic:Class"], label: "<img src=x onerror=alert(1)>", externalId: "record-ui", organizationId: "org-demo", siteId: "site-a", synthetic: true, properties: [] } }], candidates: [], evidence: [evidence], snapshot, subSources: [{ sourceId: "Synthetic", status: "AVAILABLE", releaseId: "release-ui", dataHash: hash, observedAtUtc: "2026-10-26T00:00:00Z", code: null }], validTime: null, observedAtUtc: "2026-10-26T00:00:00Z", traceId: "fixture-safe-trace", limited: false, diagnostics: [] };
const baseRun: ExecutionRun = { runId: "run-ui", ownerSubjectId: "g2-ui-fixture", scope, snapshot, status: "RUNNING", providerMode: "deterministic", createdAtUtc: "2026-10-26T00:00:00Z", updatedAtUtc: "2026-10-26T00:00:00Z", lastSeq: 0, cancelRequested: false, leaseOwner: null, leaseUntil: null, fencingToken: 1 };
test.beforeEach(async ({ page }) => {
  await page.route("**/auth/csrf", route => route.fulfill({ json: { requestToken: "bounded-ui" } }));
  await page.route("**/api/v1/releases", route => route.fulfill({ json: [release] }));
  await page.route("**/api/v1/capabilities", route => route.fulfill({ json: [capability] }));
  await page.route("**/api/v1/execution-runs", route => route.fulfill({ json: [] }));
});
for (const status of ["FOUND", "EMPTY", "PARTIAL", "UNAVAILABLE", "UNAUTHORIZED", "AMBIGUOUS"] as const) {
  test(`真实展示六态 ${status}，不执行HTML且证据再次授权`, async ({ page }) => {
    let evidenceReads = 0;
    await page.route("**/api/v1/semantic/queries", route => route.fulfill({ json: { ...baseResult, status, data: ["FOUND", "PARTIAL"].includes(status) ? baseResult.data : [], evidence: ["FOUND", "PARTIAL"].includes(status) ? [evidence] : [], limited: status === "PARTIAL", candidates: status === "AMBIGUOUS" ? [{ entityIri: "urn:synthetic:one", entityTypeIris: [], externalId: "same", organizationId: "org-demo", siteId: "site-a", label: "授权候选A", evidenceIds: [] }, { entityIri: "urn:synthetic:two", entityTypeIris: [], externalId: "same", organizationId: "org-demo", siteId: "site-b", label: "授权候选B", evidenceIds: [] }] : [] } }));
    await page.route("**/api/v1/evidence/evidence-ui", route => { evidenceReads++; return route.fulfill({ status: 403, json: { code: "forbidden" } }); });
    await page.goto("/analysis");
    await page.getByRole("button", { name: "执行真实查询" }).click();
    await expect(page.locator(".g2-status")).toContainText(status);
    await expect(page.locator(".g2-panel img")).toHaveCount(0);
    if (["FOUND", "PARTIAL"].includes(status)) { await expect(page.getByRole("heading", { name: "<img src=x onerror=alert(1)>" })).toBeVisible(); await page.getByRole("button", { name: /Synthetic \/ record-ui/ }).click(); await expect(page.locator(".g2-notice[role=alert]")).toContainText("HTTP 403"); expect(evidenceReads).toBe(1); }
    if (status === "AMBIGUOUS") { await expect(page.getByText(/授权候选A/)).toBeVisible(); await expect(page.getByText(/授权候选B/)).toBeVisible(); }
  });
}
test("提案自批禁止/异人批准/激活固定当前CAS", async ({ page }) => {
  const proposal: ReleaseProposal = { proposalId: "proposal-other", kind: "PUBLISH", assetId: "asset-ui", scope, draftId: "draft-ui", draftRevision: 2, hashes: manifest.hashes, validationReportId: "report-ui", targetReleaseId: null, targetManifestHash: null, submittedBy: "other-subject", submittedAtUtc: "2026-10-26T00:00:00Z", expiresAtUtc: "2099-01-01T00:00:00Z", status: "PENDING", revision: 1, approval: null };
  const own = { ...proposal, proposalId: "proposal-own", submittedBy: "g2-ui-fixture" };
  let decision: unknown = null; let activation: unknown = null;
  await page.route("**/api/v1/release-proposals", route => route.fulfill({ json: [proposal, own] }));
  await page.route("**/api/v1/approvals/proposal-other/decisions", route => { decision = route.request().postDataJSON(); proposal.status = "APPROVED"; proposal.revision = 2; return route.fulfill({ json: proposal }); });
  await page.route("**/api/v1/release-activations", route => { activation = route.request().postDataJSON(); return route.fulfill({ json: { activationId: "a-ui", activationRevision: 2, releaseId: "release-next", previousReleaseId: "release-ui", manifestHash: hash, manifest, auditId: "audit-ui", outboxEventId: "outbox-ui", activatedAtUtc: "2026-10-26T00:00:00Z" } }); });
  await page.goto("/releases"); await page.getByRole("textbox", { name: "审核操作理由" }).fill("合成异人审核");
  const other = page.locator("article").filter({ hasText: "proposal-other / 1" }); const self = page.locator("article").filter({ hasText: "proposal-own / 1" });
  await expect(self.getByRole("button", { name: "异人批准" })).toBeDisabled(); await other.getByRole("button", { name: "异人批准" }).click();
  await expect.poll(() => decision).toMatchObject({ decision: "approve", command: { expectedRevision: 1 } });
  await page.locator("article").filter({ hasText: "proposal-other / 2" }).getByRole("button", { name: "激活已批准版本" }).click();
  await expect.poll(() => activation).toMatchObject({ proposalId: "proposal-other", expectedActivationRevision: 1, expectedActiveReleaseId: "release-ui" });
  await expect(page.getByText("audit-ui / outbox-ui")).toBeVisible();
});
test("持久Run重放文本事件与终态，显示harness标识", async ({ page }) => {
  let created: unknown = null;
  const events = [ { seq: 1, eventType: "run.started", payload: { kind: "run.started", providerMode: "deterministic", capabilityIds: ["describe_ontology"], maxToolCalls: 3, timeoutMs: 30000 } }, { seq: 2, eventType: "message.delta", payload: { kind: "message.delta", text: "<script>alert(1)</script> 合成真实事件文本" } }, { seq: 3, eventType: "run.completed", payload: { kind: "run.completed", status: "COMPLETED", totalToolCalls: 1, lastResultStatus: "FOUND" } } ].map(value => ({ ...value, runId: "run-ui", eventId: `run-ui:${value.seq}`, schemaVersion: 1, occurredAtUtc: "2026-10-26T00:00:00Z", snapshot }));
  await page.route("**/api/v1/execution-runs", route => { if (route.request().method() === "POST") { created = route.request().postDataJSON(); return route.fulfill({ json: baseRun }); } return route.fulfill({ json: created ? [baseRun] : [] }); });
  await page.route("**/api/v1/execution-runs/run-ui", route => route.fulfill({ json: { ...baseRun, status: "COMPLETED", lastSeq: 3 } }));
  await page.route("**/api/v1/execution-runs/run-ui/events", route => route.fulfill({ contentType: "text/event-stream", body: events.map(event => `id: ${event.eventId}\ndata: ${JSON.stringify(event)}\n\n`).join("") }));
  await page.goto("/analysis"); await expect(page.getByText(/真实模型未配置/)).toBeVisible(); await page.getByRole("textbox", { name: "运行说明" }).fill("查看正式Schema"); await expect(page.getByRole("button", { name: "启动确定性工具运行" })).toBeDisabled();
  await page.getByLabel("明确使用 deterministic harness").check(); await page.getByRole("button", { name: "启动确定性工具运行" }).click();
  await expect.poll(() => created).toMatchObject({ providerMode: "deterministic", plan: { assetId: "asset-ui", releaseId: "release-ui" } });
  await expect(page.getByText("<script>alert(1)</script> 合成真实事件文本", { exact: true })).toBeVisible(); await expect(page.getByRole("heading", { name: "COMPLETED", exact: true })).toBeVisible(); await expect(page.locator(".g2-panel script")).toHaveCount(0);
});
