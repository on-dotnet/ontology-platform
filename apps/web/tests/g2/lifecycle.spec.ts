import { expect, test } from "@playwright/test";
import type { AssetVersionSnapshot, EvidenceRef, ExecutionRun, ReleaseManifest, ReleaseProposal, ReleaseSummary, SemanticCapability, SemanticQueryResult } from "../../src/lib/api/g2-generated";
const hash = "b".repeat(64);
const scope = { organizationId: "org-demo", siteIds: ["site-a", "site-b"] };
const snapshot: AssetVersionSnapshot = { releaseId: "release-ui", ontologyHash: hash, shapesHash: hash, vocabularyHash: null, dataHash: hash, ontologyGraphIri: "urn:release:ontology", dataGraphIri: "urn:release:data", mappingVersions: [], metricVersions: [], ruleVersions: [], capabilityVersions: [{ assetId: "resolve_entity", version: hash }] };
const manifest: ReleaseManifest = { schemaVersion: 1, releaseId: "release-ui", assetId: "asset-ui", scope, draftId: "draft-ui", revision: 2, hashes: { ontologyHash: hash, shapesHash: hash, vocabularyHash: null, dataHash: hash, bundleHash: hash }, ontologyGraphIri: snapshot.ontologyGraphIri, dataGraphIri: snapshot.dataGraphIri, importLocks: [], snapshot, artifactObjects: [], createdAtUtc: "2026-10-26T00:00:00Z" };
const release: ReleaseSummary = { manifest, manifestHash: hash, isActive: true, activationRevision: 1, status: "ACTIVE" };
const capability: SemanticCapability = { id: "resolve_entity", version: hash, inputSchema: { schemaVersion: 1, type: "object", required: ["assetId"], properties: [], additionalProperties: false }, outputSchema: {}, meaning: "解析正式Synthetic实体", policy: "semantic.read", executorId: "registered", budgets: { maxDepth: 5, maxRows: 100, timeoutMs: 5000, maxToolCalls: 3 } };
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
    await page.route("**/api/v1/semantic/queries", route => route.fulfill({ json: { ...baseResult, status, subSources: baseResult.subSources.map(source => ({ ...source, status: status === "UNAVAILABLE" ? "UNAVAILABLE" : status === "UNAUTHORIZED" ? "UNAUTHORIZED" : status === "PARTIAL" ? "PARTIAL" : "AVAILABLE", code: status === "UNAVAILABLE" ? "SourceUnavailable" : null })), data: ["FOUND", "PARTIAL"].includes(status) ? baseResult.data : [], evidence: ["FOUND", "PARTIAL"].includes(status) ? [evidence] : [], limited: status === "PARTIAL", candidates: status === "AMBIGUOUS" ? [{ entityIri: "urn:synthetic:one", entityTypeIris: [], externalId: "same", organizationId: "org-demo", siteId: "site-a", label: "授权候选A", evidenceIds: [] }, { entityIri: "urn:synthetic:two", entityTypeIris: [], externalId: "same", organizationId: "org-demo", siteId: "site-b", label: "授权候选B", evidenceIds: [] }] : [] } }));
    await page.route("**/api/v1/evidence/evidence-ui", route => { evidenceReads++; return route.fulfill({ status: 403, json: { code: "forbidden" } }); });
    await page.goto("/analysis");
    await page.getByRole("textbox", { name: "实体外部编号" }).fill("record-ui"); await page.getByRole("button", { name: "执行真实查询" }).click();
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
  const events = [ { seq: 1, eventType: "run.started", payload: { kind: "run.started", providerMode: "deterministic", capabilityIds: ["resolve_entity"], maxToolCalls: 3, timeoutMs: 30000 } }, { seq: 2, eventType: "message.delta", payload: { kind: "message.delta", text: "<script>alert(1)</script> 合成真实事件文本" } }, { seq: 3, eventType: "run.completed", payload: { kind: "run.completed", status: "COMPLETED", totalToolCalls: 1, lastResultStatus: "FOUND" } } ].map(value => ({ ...value, runId: "run-ui", eventId: `run-ui:${value.seq}`, schemaVersion: 1, occurredAtUtc: "2026-10-26T00:00:00Z", snapshot }));
  await page.route("**/api/v1/execution-runs", route => { if (route.request().method() === "POST") { created = route.request().postDataJSON(); return route.fulfill({ json: baseRun }); } return route.fulfill({ json: created ? [baseRun] : [] }); });
  await page.route("**/api/v1/execution-runs/run-ui", route => route.fulfill({ json: { ...baseRun, status: "COMPLETED", lastSeq: 3 } }));
  await page.route("**/api/v1/execution-runs/run-ui/events", route => route.fulfill({ contentType: "text/event-stream", body: events.map(event => `id: ${event.eventId}\ndata: ${JSON.stringify(event)}\n\n`).join("") }));
  await page.goto("/analysis"); await expect(page.getByText(/真实模型未配置/)).toBeVisible(); await page.getByRole("textbox", { name: "运行说明" }).fill("解析合成实体"); await expect(page.getByRole("button", { name: "启动确定性工具运行" })).toBeDisabled();
  await page.getByLabel("明确使用 deterministic harness").check(); await page.getByRole("button", { name: "启动确定性工具运行" }).click();
  await expect.poll(() => created).toMatchObject({ providerMode: "deterministic", plan: { assetId: "asset-ui", releaseId: null } });
  await expect(page.getByText("<script>alert(1)</script> 合成真实事件文本", { exact: true })).toBeVisible(); await expect(page.getByRole("heading", { name: "COMPLETED", exact: true })).toBeVisible(); await expect(page.locator(".g2-panel script")).toHaveCount(0);
});
test("SSE续订发送持久游标且重复事件不重复展示", async ({ page }) => {
  const seenHeaders: Array<string | undefined> = [];
  let finished = false;
  await page.route("**/api/v1/execution-runs", route => route.fulfill({ json: [baseRun] }));
  await page.route("**/api/v1/execution-runs/run-ui", route => route.fulfill({ json: { ...baseRun, lastSeq: finished ? 2 : 1, status: finished ? "COMPLETED" : "RUNNING" } }));
  const first = { runId: "run-ui", seq: 1, eventId: "run-ui:1", eventType: "message.delta", schemaVersion: 1, occurredAtUtc: "2026-10-26T00:00:00Z", snapshot, payload: { kind: "message.delta", text: "唯一重放文本" } };
  const last = { ...first, seq: 2, eventId: "run-ui:2", eventType: "run.completed", payload: { kind: "run.completed", status: "COMPLETED", totalToolCalls: 1, lastResultStatus: "FOUND" } };
  await page.route("**/api/v1/execution-runs/run-ui/events", route => { const cursor = route.request().headers()["last-event-id"]; seenHeaders.push(cursor); if (cursor) finished = true; return route.fulfill({ contentType: "text/event-stream", body: (cursor ? [first, last] : [first]).map(event => `id: ${event.eventId}\ndata: ${JSON.stringify(event)}\n\n`).join("") }); });
  await page.goto("/analysis"); await page.getByRole("button", { name: /RUNNING · deterministic/ }).click();
  await expect(page.getByRole("heading", { name: "COMPLETED", exact: true })).toBeVisible();
  expect(seenHeaders).toEqual([undefined, "run-ui:1"]); await expect(page.getByText("唯一重放文本", { exact: true })).toHaveCount(1);
});
test("断开订阅不发送取消，独立持久取消才POST", async ({ page }) => {
  let cancels = 0;
  await page.route("**/api/v1/execution-runs", route => route.fulfill({ json: [baseRun] }));
  await page.route("**/api/v1/execution-runs/run-ui", route => route.fulfill({ json: baseRun }));
  await page.route("**/api/v1/execution-runs/run-ui/events", route => route.fulfill({ contentType: "text/event-stream", body: "" }));
  await page.route("**/api/v1/execution-runs/run-ui/cancel", route => { cancels++; return route.fulfill({ json: { ...baseRun, cancelRequested: true } }); });
  await page.goto("/analysis"); await page.getByRole("button", { name: /RUNNING · deterministic/ }).click();
  await page.getByRole("button", { name: "仅断开订阅" }).click(); expect(cancels).toBe(0);
  await page.getByRole("button", { name: "持久取消 Run" }).click(); await expect.poll(() => cancels).toBe(1);
  await expect(page.getByText("取消请求已持久化，等待唯一终态事件。")).toBeVisible();
});
test("不支持事件版本停止接收且回读Run快照", async ({ page }) => {
  let snapshotReads = 0;
  await page.route("**/api/v1/execution-runs", route => route.fulfill({ json: [baseRun] }));
  await page.route("**/api/v1/execution-runs/run-ui", route => { snapshotReads++; return route.fulfill({ json: { ...baseRun, status: "FAILED" } }); });
  await page.route("**/api/v1/execution-runs/run-ui/events", route => route.fulfill({ contentType: "text/event-stream", body: `data: ${JSON.stringify({ runId: "run-ui", seq: 1, eventId: "run-ui:1", schemaVersion: 2, eventType: "message.delta", snapshot, payload: { kind: "message.delta", text: "不可信答案不可出现" } })}\n\n` }));
  await page.goto("/analysis"); await page.getByRole("button", { name: /RUNNING · deterministic/ }).click();
  await expect(page.getByText("事件协议或序列不受支持，已停止答案接收并回读持久Run快照。")).toBeVisible();
  await expect(page.getByText("不可信答案不可出现", { exact: true })).toHaveCount(0); expect(snapshotReads).toBeGreaterThanOrEqual(2);
});
for (const width of [1440, 1280, 390]) {
  test(`${width}发布与查询Run工作区深浅主题/无溢出/键盘/水合`, async ({ page }) => {
    const errors: string[] = []; page.on("pageerror", error => errors.push(error.message)); page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    await page.setViewportSize({ width, height: 1000 });
    await page.route("**/api/v1/release-proposals", route => route.fulfill({ json: [] }));
    await page.route("**/api/v1/semantic/queries", route => route.fulfill({ json: baseResult }));
    for (const path of ["releases", "analysis"]) {
      await page.goto(`/${path}`);
      if (path === "releases") await expect(page.getByRole("heading", { name: "正式版本与激活记录" })).toBeVisible();
      else { await page.getByRole("textbox", { name: "实体外部编号" }).fill("record-ui"); await page.getByRole("button", { name: "执行真实查询" }).focus(); await page.keyboard.press("Enter"); await expect(page.locator(".g2-status")).toContainText("FOUND"); }
      for (const theme of ["dark", "light"]) {
        if (await page.locator("html").getAttribute("data-theme") !== theme) await page.getByRole("button", { name: "切换深浅主题" }).click();
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: `../../docs/evidence/G2-THIN-SLICE-001/FE/screenshots/${width}-${path}-${theme}.png`, fullPage: true, animations: "disabled" });
      }
    }
    expect(errors).toEqual([]);
  });
}
test("默认Active查询交由服务端固定当次快照，不锁旧Active ID", async ({ page }) => {
  let plan: unknown = null;
  await page.route("**/api/v1/semantic/queries", route => { plan = route.request().postDataJSON(); return route.fulfill({ json: baseResult }); });
  await page.goto("/analysis"); await page.getByRole("textbox", { name: "实体外部编号" }).fill("record-ui"); await page.getByRole("button", { name: "执行真实查询" }).click();
  await expect.poll(() => plan).toMatchObject({ assetId: "asset-ui", releaseId: null });
});
