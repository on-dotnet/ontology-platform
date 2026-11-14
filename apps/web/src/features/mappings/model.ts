import { useEffect, useRef, useState } from "react";
import { PlatformApiError } from "../../lib/api/client";
import type * as G4 from "../../lib/api/g4-generated";

/** 中文状态只映射已知服务端事实，未知状态原样呈现且不能推定成功。 */
export const mappingLabels: Record<string, string> = {
  DRAFT: "草稿", NEEDS_REVIEW: "需要重新评估", VALIDATING: "验证中", READY_FOR_PROPOSAL: "可提交审核", BLOCKED: "验证未通过",
  QUEUED: "排队中", RUNNING: "运行中", SUCCEEDED: "任务已完成", FAILED: "失败", CANCELLED: "已取消",
  PENDING: "待独立审核", APPROVED: "已批准", REJECTED: "已拒绝", STALE: "输入已变化", EXPIRED: "已过期",
  PASS: "通过", FAIL: "失败", INDETERMINATE: "证据不足", NOT_RUN: "未执行",
  SCHEMA: "结构与正式词汇", IDENTITY: "身份与有效期", TIME_UNIT: "时间、单位与精度", SECURITY: "当前授权与只读边界",
  EXECUTABILITY: "实际有界执行", RECONCILIATION: "逐值与数量对账", IMPACT: "依赖影响与当前指针",
};

/** 浏览器编辑也拒绝重复键，不能在JSON.parse后静默只保留最后一个审批输入。 */
export function parseDefinition(text: string): G4.MappingDefinition {
  if (new TextEncoder().encode(text).length > 1048576) throw new Error("映射定义超过 1 MiB。");
  const value: unknown = JSON.parse(text);
  const stack: Array<{ object: boolean; keys: Set<string>; key: boolean }> = [];
  const tokens = text.match(/"(?:\\.|[^"\\])*"|[{}\[\]:,]|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?|true|false|null/g) ?? [];
  for (const token of tokens) {
    const current = stack.at(-1);
    if (token === "{" || token === "[") {
      stack.push({ object: token === "{", keys: new Set(), key: token === "{" });
      if (stack.length > 48) throw new Error("映射定义嵌套过深。");
    } else if (token === "}" || token === "]") stack.pop();
    else if (token === "," && current?.object) current.key = true;
    else if (token.startsWith('"') && current?.object && current.key) {
      const name: string = JSON.parse(token);
      if (current.keys.has(name)) throw new Error("映射定义含重复字段。");
      current.keys.add(name); current.key = false;
    } else if (/^-?\d/.test(token) && (/[.eE]/.test(token) || token === "-0" || !Number.isSafeInteger(Number(token)))) throw new Error("数值须为安全整数；精确小数使用字符串。");
  }
  const required = ["entities", "properties", "relations", "identitySpecs", "temporalSpecs", "conversions", "unitSpecs"];
  if (!value || typeof value !== "object" || Array.isArray(value) || Object.keys(value).length !== required.length
    || required.some(key => !Array.isArray((value as Record<string, unknown>)[key]))) throw new Error("请提供完整的实体、属性、关系、身份、时间、转换和单位集合。");
  const mapping = value as G4.MappingDefinition;
  if (!mapping.entities.length || mapping.entities.length > 2) throw new Error("本路径需要 1–2 个实体绑定。");
  return mapping;
}

/** 审核只能使用原评估目标；回滚分支绝不注入当前Draft字段。 */
export function proposalRequest(report: G4.MappingAssessmentView, draft: Pick<G4.MappingDraftView, "scope" | "draftId">, command: G4.CommandContext): G4.MappingProposalCreateRequest {
  const common = { schemaVersion: "g4.mapping.v1" as const, scope: draft.scope, binding: report.binding,
    expectedActive: report.expectedActive, expiresAtUtc: report.expiresAtUtc, command };
  if (report.target.kind === "ROLLBACK") return { ...common, kind: "ROLLBACK", targetReleaseId: report.target.targetReleaseId, manifestHash: report.target.manifestHash };
  return { ...common, kind: "PUBLISH", draftId: draft.draftId, draftRevision: report.target.draftRevision };
}

/** 撤权时清除内存并提升代际，迟到成功响应不能把旧字段重新显示出来。 */
export function useMappingWork(clear: () => void) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [recoverable, setRecoverable] = useState(false);
  const state = useRef({ generation: 0, revoked: false, locked: false });
  const clearRef = useRef(clear); clearRef.current = clear;
  const retry = useRef<(() => Promise<void>) | null>(null);
  useEffect(() => {
    const current = state.current;
    current.generation++; current.revoked = false;
    return () => { current.generation++; current.revoked = true; retry.current = null; };
  }, []);
  function fail(cause: unknown) {
    if (state.current.revoked) return;
    setError(cause);
    if (cause instanceof PlatformApiError && [401, 403].includes(cause.status)) {
      state.current.generation++; state.current.revoked = true;
      retry.current = null; setRecoverable(false); clearRef.current();
    }
  }
  async function run<T>(work: () => Promise<T>, accept: (value: T) => void) {
    if (state.current.locked || state.current.revoked) return;
    const generation = state.current.generation;
    state.current.locked = true; setBusy(true); setError(null);
    retry.current = () => run(work, accept); setRecoverable(true);
    try {
      const value = await work();
      if (generation === state.current.generation && !state.current.revoked) { accept(value); retry.current = null; setRecoverable(false); }
    } catch (cause) { if (generation === state.current.generation) fail(cause); }
    finally { state.current.locked = false; setBusy(false); }
  }
  return { busy, error, recoverable, run, fail, retry: () => retry.current?.(),
    current: (generation: number) => generation === state.current.generation && !state.current.revoked,
    generation: () => state.current.generation, denied: state.current.revoked };
}

/** 只将用户明确勾选的唯一低风险候选写入未保存内容；不验证、不发布、不忽略待决项。 */
export function adoptCandidates(mapping: G4.MappingDefinition, candidates: G4.MappingSuggestionCandidate[]): G4.MappingDefinition {
  const next = structuredClone(mapping);
  for (const candidate of candidates) {
    if (candidate.status !== "CANDIDATE_ONLY" || candidate.evidence !== "METADATA") throw new Error("高风险候选需要逐项人工编辑和验证。");
    const entities = next.entities.filter(entity => entity.datasetRef.snapshotId === candidate.fieldRef.datasetRef.snapshotId && entity.datasetRef.schema === candidate.fieldRef.datasetRef.schema && entity.datasetRef.name === candidate.fieldRef.datasetRef.name && entity.datasetRef.kind === candidate.fieldRef.datasetRef.kind);
    if (entities.length !== 1 || next.properties.some(property => property.entityBindingId === entities[0].id && property.fieldRef.name === candidate.fieldRef.name)) throw new Error("候选与当前定义不一致，请重新读取候选。");
    let suffix = next.properties.length + 1;
    while (next.properties.some(property => property.id === "suggested-" + suffix)) suffix++;
    next.properties.push({ id: "suggested-" + suffix, entityBindingId: entities[0].id, propertyIri: candidate.targetIri,
      fieldRef: candidate.fieldRef, conversionId: null, unitSpecId: null, nullPolicy: "REJECT_NULL" });
  }
  return next;
}
