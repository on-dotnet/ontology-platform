import type { OntologyDraft, SemanticAssessment, SemanticSupportProfile } from "../../lib/api/g2-generated";

/** 客户端仅提示当前修订资格；服务器仍须执行权限、散列和事务绑定核验。 */
export function assessmentEligibility(
  assessment: SemanticAssessment | null,
  draft: OntologyDraft,
  profile: SemanticSupportProfile | null,
  dirty: boolean,
  now = Date.now(),
): string {
  if (dirty) return "STALE · 本地源码未保存";
  if (!assessment || !profile) return "UNKNOWN · 尚未取得当前评估与支持档案";
  if (assessment.draftId !== draft.draftId || assessment.revision !== draft.revision) return "STALE · 修订不匹配";
  const hashKeys = ["ontologyHash", "shapesHash", "vocabularyHash", "dataHash", "bundleHash"] as const;
  if (hashKeys.some(key => assessment.hashes[key] !== draft.hashes[key])) return "STALE · 源散列不匹配";
  if (assessment.profileVersion !== profile.version || assessment.profileHash !== profile.hash) return "STALE · 支持档案已变化";
  const expires = Date.parse(assessment.expiresAtUtc);
  if (!Number.isFinite(expires) || expires <= now) return "EXPIRED · 请重新评估";
  if (assessment.budgetStatus !== "COMPLETE") return "INDETERMINATE · 预算未完整完成";
  const required = ["PARSE", "SUPPORT", "SHACL_CORE", "GOVERNANCE"];
  if (required.some(name => assessment.stages.filter(stage => stage.name === name && stage.status === "PASS").length !== 1)) {
    return "BLOCKED · 必需阶段未全部通过";
  }
  const uncertainStage = assessment.stages.some(stage => stage.name === "OWL_REASONING"
    ? stage.status !== "NOT_RUN"
    : !required.includes(stage.name) || stage.status !== "PASS");
  if (uncertainStage) return "INDETERMINATE · 存在未知、失败或未确定阶段";
  if (!assessment.publishEligible) return "BLOCKED · 服务端判定不具备发布资格";
  return "ELIGIBLE";
}

/** 未确定和未知结果保持可见，禁止把预算耗尽显示成无差异。 */
export function comparisonLabel(status: string): string {
  if (status === "EQUIVALENT") return "EQUIVALENT · RDF图等价";
  if (status === "DIFFERENT") return "DIFFERENT · RDF图不同";
  if (status === "INDETERMINATE") return "INDETERMINATE · 图比较未确定，不能认定无差异";
  return "UNKNOWN · 未识别比较状态";
}
