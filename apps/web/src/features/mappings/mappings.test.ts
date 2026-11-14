import { describe, expect, it, vi } from "vitest";
import { createMappingsClient, MappingApiError } from "./api";
import { parseDefinition, proposalRequest, adoptCandidates } from "./model";
import type * as G4 from "../../lib/api/g4-generated";

const definition = { entities: [{ id: "entity" }], properties: [], relations: [], identitySpecs: [], temporalSpecs: [], conversions: [], unitSpecs: [] };
/** 这里只测试浏览器输入与传输边界，完整语义由真实后端验收。 */
describe("人工映射输入", () => {
  it("拒绝重复键而不是静默用最后一个值", () => {
    expect(() => parseDefinition(JSON.stringify(definition).replace('"id":"entity"', '"id":"one","id":"two"'))).toThrow("重复");
    expect(() => parseDefinition(JSON.stringify(definition).replace('"id":"entity"', '"id":"one","\\u0069d":"two"'))).toThrow("重复");
  });
  it("保留用户字符串中的标点而不误判结构", () => {
    const value = { ...definition, entities: [{ id: 'literal, { "id": "not a key" }' }] };
    expect(parseDefinition(JSON.stringify(value)).entities[0].id).toBe(value.entities[0].id);
  });
  it("不把浮点、负零或超安全整数重写成看似合法整数", () => {
    for (const value of ["1.0", "1e0", "-0", "9007199254740993"])
      expect(() => parseDefinition(JSON.stringify(definition).replace('"id":"entity"', `"id":"entity","ordinal":${value}`))).toThrow("安全整数");
  });
  it("缺失集合、超大正文和空实体都不能提交", () => {
    expect(() => parseDefinition("{}")).toThrow("完整");
    expect(() => parseDefinition(JSON.stringify({ ...definition, entities: [] }))).toThrow("实体绑定");
    expect(() => parseDefinition(" ".repeat(1048577))).toThrow("1 MiB");
  });
});

/** 必须保留原Assessment目标，不能以当前草稿字段污染回滚分支。 */
describe("固定提案目标", () => {
  const draft = { draftId: "current-draft", revision: 9, scope: { organizationId: "org", siteIds: ["A"] } } as G4.MappingDraftView;
  const report = { target: { kind: "ROLLBACK", targetReleaseId: "old-release", manifestHash: "a".repeat(64) }, binding: {},
    expectedActive: { releaseId: "current-release", activationRevision: 7 }, expiresAtUtc: "2026-11-14T01:00:00.0000000Z" } as G4.MappingAssessmentView;
  const command: G4.CommandContext = { commandId: "command", idempotencyKey: "key", expectedRevision: 0, reason: "人工提交" };
  it("回滚严格固定旧制品且省略所有draft字段", () => {
    const value = proposalRequest(report, draft, command);
    expect(value).toMatchObject({ kind: "ROLLBACK", targetReleaseId: "old-release", manifestHash: "a".repeat(64), expectedActive: report.expectedActive });
    expect(value).not.toHaveProperty("draftId"); expect(value).not.toHaveProperty("draftRevision");
  });
  it("发布引用报告受审修订而不是当前头", () => {
    const value = proposalRequest({ ...report, target: { kind: "PUBLISH", draftRevision: 2 } }, draft, command);
    expect(value).toMatchObject({ kind: "PUBLISH", draftId: "current-draft", draftRevision: 2 });
    expect(value).not.toHaveProperty("targetReleaseId");
  });
});

/** 真实fetch适配不会自动重试写入；网络未知时调用方保留原命令供恢复。 */
describe("映射传输", () => {
  it("保留完整ETag、防伪和同源/no-store，写入只发送一次", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValueOnce(new Response(JSON.stringify({ requestToken: "test-csrf" }), { status: 200 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ proposalId: "proposal" }), { status: 200, headers: { ETag: '"proposal:2"' } }));
    const body: G4.MappingDecisionRequest = { decision: "APPROVE", bindingHash: "a".repeat(64), command: { commandId: "c", idempotencyKey: "k", expectedRevision: 1, reason: "异人审核" } };
    const result = await createMappingsClient(fetcher).decide("proposal", body, '"proposal:1"');
    expect(result.etag).toBe('"proposal:2"');
    const call = fetcher.mock.calls[1];
    expect(call[0]).toBe("/api/v1/mapping-proposals/proposal/decisions");
    expect(call[1]).toMatchObject({ method: "POST", credentials: "same-origin", cache: "no-store", redirect: "error", body: JSON.stringify(body) });
    expect(new Headers(call[1]?.headers).get("If-Match")).toBe('"proposal:1"');
    expect(new Headers(call[1]?.headers).get("X-CSRF-TOKEN")).toBe("test-csrf");
    expect(fetcher).toHaveBeenCalledTimes(2);
  });
  it("刷新固定ID只有GET，不获取防伪或触发POST", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ proposalId: "proposal" }), { status: 200 }));
    await createMappingsClient(fetcher).proposal("proposal");
    expect(fetcher).toHaveBeenCalledTimes(1); expect(fetcher.mock.calls[0][1]?.method).toBe("GET");
  });
  it("403和失败检查保留准确安全状态，不能转为空列表成功", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(new Response(JSON.stringify({ code: "mapping_forbidden" }), { status: 403 }));
    await expect(createMappingsClient(fetcher).proposal("proposal")).rejects.toMatchObject({ status: 403, code: "mapping_forbidden" });
    const error = new MappingApiError(409, "mapping_activation_check_failed", "trace", "check-id");
    expect(error.checkId).toBe("check-id");
  });
});

/** 批采纳只改内存定义，高风险和歧义不自动越过人工决定。 */
describe("规则候选显式采纳", () => {
  const dataset = { snapshotId: "snapshot", schema: "production", name: "assets", kind: "TABLE" } as const;
  const mapping: G4.MappingDefinition = { ...definition, entities: [{ id: "entity", datasetRef: dataset, entityClassIri: "urn:Entity", identitySpecId: "identity", temporalSpecId: "time",
    scopeFields: { organization: { datasetRef: dataset, name: "org", ordinal: 1 }, site: { datasetRef: dataset, name: "site", ordinal: 2 } } }] };
  const candidate: G4.MappingSuggestionCandidate = { fieldRef: { datasetRef: dataset, name: "label", ordinal: 6 }, targetIri: "urn:label", evidence: "METADATA", status: "CANDIDATE_ONLY" };
  it("只产生待保存属性且保留原定义", () => {
    const result = adoptCandidates(mapping, [candidate]);
    expect(mapping.properties).toEqual([]);
    expect(result.properties).toHaveLength(1);
    expect(result.properties[0]).toMatchObject({ propertyIri: "urn:label", conversionId: null, unitSpecId: null, nullPolicy: "REJECT_NULL" });
  });
  it("高风险、重复和歧义实体不能批量采纳", () => {
    expect(() => adoptCandidates(mapping, [{ ...candidate, evidence: "TERM" }])).toThrow("高风险");
    expect(() => adoptCandidates(mapping, [candidate, candidate])).toThrow("不一致");
    expect(() => adoptCandidates({ ...mapping, entities: [mapping.entities[0], { ...mapping.entities[0], id: "other" }] }, [candidate])).toThrow("不一致");
  });
});
