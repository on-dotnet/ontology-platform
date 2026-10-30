import type {
  GenerateImpactReportRequest, ImpactApprovalBinding, ImpactConclusion, ImpactEvidenceReference, ImpactReport,
  OntologyDraft, PublicationSemantics, ReleaseProposal, ReleaseSummary, SemanticAssessment, SemanticSupportProfile, VersionRef,
} from "../../lib/api/g2-generated";
import { assessmentEligibility } from "./semantic-status";
import { sameHashes } from "./vocabulary-model";
import { isGroundTriple, isSourceHashes, isVersionReference, sameScope, sameVersion, sourceHash, versionDiffMatches } from "./version-diff-model";

/** 当前草稿发布的明确基线；无active必须经真实列表读取确认。 */
export type PublicationBaseline = { kind: "INITIAL" | "VERSION_PAIR"; from: VersionRef; to: VersionRef; active: ReleaseSummary | null };
export function publicationBaseline(releases: ReleaseSummary[], draft: OntologyDraft): PublicationBaseline {
  const active = releases.filter(release => release.isActive && release.manifest.assetId === draft.assetId);
  if (active.length > 1 || active.some(release => !sameScope(release.manifest.scope, draft.scope))) throw new Error("impact_baseline_response_mismatch");
  const to: VersionRef = { kind: "DRAFT", id: draft.draftId, revision: draft.revision };
  return active.length === 0 ? { kind: "INITIAL", from: to, to, active: null }
    : { kind: "VERSION_PAIR", from: { kind: "RELEASE", id: active[0].manifest.releaseId, revision: null }, to, active: active[0] };
}
const object = (value: unknown): value is Record<string, unknown> => typeof value === "object" && value !== null && !Array.isArray(value);
const fields = (value: Record<string, unknown>, names: string[]) => names.every(name => Object.hasOwn(value, name));
const text = (value: unknown): value is string => typeof value === "string" && value.trim() !== "";
const hash = (value: unknown): value is string => typeof value === "string" && value.length === 64 && /^[0-9a-f]{64}$/.test(value);
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every(item => typeof item === "string");
const explicitTime = (value: unknown): value is string => text(value) && value.trim() === value && /(?:Z|[+-][0-9]{2}:[0-9]{2})$/.test(value) && Number.isFinite(Date.parse(value));
function semantics(value: unknown): value is PublicationSemantics {
  return object(value) && fields(value, ["profileVersion", "profileHash", "assessmentId", "assessmentHash"])
    && text(value.profileVersion) && hash(value.profileHash) && text(value.assessmentId) && hash(value.assessmentHash);
}
export function sameSemantics(left: PublicationSemantics | null | undefined, right: PublicationSemantics | null | undefined) {
  return Boolean(left && right && left.profileVersion === right.profileVersion && left.profileHash === right.profileHash
    && left.assessmentId === right.assessmentId && left.assessmentHash === right.assessmentHash);
}

/** 报告的每个证据必须绑定实际From或To及该版本精确源hash；未知位置不能被伪造默认值。 */
function evidenceValid(value: unknown, report: ImpactReport): value is ImpactEvidenceReference {
  if (!object(value) || !fields(value, ["version", "sourceId", "sourceHash", "triple", "focusIri", "path", "line", "column"])
    || !isVersionReference(value.version) || !text(value.sourceId) || !hash(value.sourceHash)) return false;
  const hashes = sameVersion(value.version, report.diff.from) ? report.diff.baseHashes
    : sameVersion(value.version, report.diff.to) ? report.diff.targetHashes : null;
  if (!hashes || value.sourceHash !== (value.sourceId === "bundle" ? hashes.bundleHash : sourceHash(hashes, value.sourceId))) return false;
  const position = (number: unknown) => number === null || Number.isSafeInteger(number) && (number as number) > 0;
  return (value.triple === null || isGroundTriple(value.triple)) && (value.focusIri === null || text(value.focusIri) && !value.focusIri.startsWith("_:"))
    && (value.path === null || text(value.path)) && position(value.line) && position(value.column);
}
function conclusionsValid(value: unknown, report: ImpactReport): value is ImpactConclusion[] {
  return Array.isArray(value) && value.every(item => object(item)
    && fields(item, ["code", "message", "blocking", "affectedIris", "assetReferences", "evidence"])
    && text(item.code) && text(item.message) && typeof item.blocking === "boolean" && strings(item.affectedIris) && strings(item.assetReferences)
    && Array.isArray(item.evidence) && item.evidence.length > 0 && item.evidence.every(evidence => evidenceValid(evidence, report)));
}

/** 拒绝错版本、错源证据及不完整报告；canonical真实性与业务资格仍由服务器复核。 */
export function impactReportMatches(value: unknown, request: Pick<GenerateImpactReportRequest, "from" | "to" | "baselineKind">,
  draft: Pick<OntologyDraft, "assetId" | "scope">): value is ImpactReport {
  if (!object(value) || !fields(value, ["schemaVersion", "reportId", "inputFingerprint", "canonicalHash", "executorVersion", "budgetIdentity",
    "generatedAtUtc", "expiresAtUtc", "baselineKind", "diff", "profileVersion", "profileHash", "targetSemantics", "changedIris", "assetReferences",
    "knownImpacts", "blockers", "unknownCoverage", "publishEligible"])) return false;
  if (value.schemaVersion !== 1 || !text(value.reportId) || !hash(value.inputFingerprint) || !hash(value.canonicalHash)
    || value.executorVersion !== "ontology-platform/g3-m4-impact/1"
    || value.budgetIdentity !== "graph128-search100000-ms5000-triples5000-report256-bytes8388608/1"
    || !explicitTime(value.generatedAtUtc) || !explicitTime(value.expiresAtUtc) || value.baselineKind !== request.baselineKind
    || !["INITIAL", "VERSION_PAIR"].includes(value.baselineKind as string)
    || !versionDiffMatches(value.diff, request, draft.assetId, draft.scope) || !text(value.profileVersion) || !hash(value.profileHash)
    || value.targetSemantics !== null && !semantics(value.targetSemantics) || !strings(value.changedIris) || !strings(value.assetReferences)
    || typeof value.publishEligible !== "boolean") return false;
  const report = value as ImpactReport;
  return conclusionsValid(report.knownImpacts, report) && conclusionsValid(report.blockers, report) && conclusionsValid(report.unknownCoverage, report);
}

/** 过期、实际unknown或技术阻断不可由审核按钮覆盖；范围限制非阻断项仍明确展示。 */
export function impactTechnicalBlocker(report: ImpactReport | null, now = Date.now()): string | null {
  if (!report) return "UNKNOWN · 尚未核验影响报告";
  const generated = Date.parse(report.generatedAtUtc), expires = Date.parse(report.expiresAtUtc);
  if (!Number.isFinite(generated) || !Number.isFinite(expires) || generated > now || expires <= generated) return "UNKNOWN · 报告时间无法确认";
  if (expires <= now) return "EXPIRED · 影响报告已到期，不能继续使用旧绑定";
  if (!report.targetSemantics) return "BLOCKED · 报告缺少目标评估绑定";
  if (report.blockers.some(item => item.blocking) || report.unknownCoverage.some(item => item.blocking)
    || report.knownImpacts.some(item => item.blocking) || !report.publishEligible) return "BLOCKED · 存在技术阻断或阻断性未知，审核者不能覆盖";
  if (report.diff.sources.some(source => source.graph.status === "INDETERMINATE" || source.tripleDeltaStatus === "INDETERMINATE"))
    return "INDETERMINATE · 四源图或typed差异未确定";
  return null;
}

/** 当前报告必须逐项绑定草稿、完整评估、支持档案及真实active基线。 */
export function publicationImpactBlocker(report: ImpactReport | null, draft: OntologyDraft, assessment: SemanticAssessment | null,
  profile: SemanticSupportProfile | null, dirty: boolean, baseline: PublicationBaseline | null, now = Date.now()): string | null {
  const eligibility = assessmentEligibility(assessment, draft, profile, dirty, now);
  if (eligibility !== "ELIGIBLE") return eligibility;
  if (!baseline) return "UNKNOWN · 发布基线尚未真实读取";
  const technical = impactTechnicalBlocker(report, now);
  if (technical || !report) return technical;
  if (report.diff.assetId !== draft.assetId || !sameScope(report.diff.scope, draft.scope) || !sameVersion(report.diff.to, baseline.to)
    || !sameVersion(report.diff.from, baseline.from) || report.baselineKind !== baseline.kind || !sameHashes(report.diff.targetHashes, draft.hashes))
    return "STALE · 报告目标或发布基线已变化";
  if (baseline.active ? report.diff.baseManifestHash !== baseline.active.manifestHash
    || !sameHashes(report.diff.baseHashes, baseline.active.manifest.hashes) : report.diff.baseManifestHash !== null || !sameHashes(report.diff.baseHashes, draft.hashes))
    return "STALE · active Release或manifest已变化";
  if (!assessment || !profile || report.profileVersion !== profile.version || report.profileHash !== profile.hash
    || !sameSemantics(report.targetSemantics, { profileVersion: assessment.profileVersion, profileHash: assessment.profileHash,
      assessmentId: assessment.assessmentId, assessmentHash: assessment.assessmentHash })) return "STALE · 评估或profile已变化，请重建影响报告";
  return null;
}

/** 冻结引用的结构和版本判别必须完整，才能展示或请求原报告。 */
export function impactBindingWellFormed(binding: unknown): binding is ImpactApprovalBinding {
  if (!object(binding) || !fields(binding, ["reportId", "canonicalHash", "inputFingerprint", "baselineKind", "from", "to", "baseHashes", "targetHashes",
    "baseManifestHash", "targetSemantics", "generatedAtUtc", "expiresAtUtc"]) || !isVersionReference(binding.from) || !isVersionReference(binding.to)
    || !isSourceHashes(binding.baseHashes) || !isSourceHashes(binding.targetHashes) || !semantics(binding.targetSemantics)
    || !text(binding.reportId) || !hash(binding.canonicalHash) || !hash(binding.inputFingerprint)
    || !explicitTime(binding.generatedAtUtc) || !explicitTime(binding.expiresAtUtc)
    || !["INITIAL", "VERSION_PAIR"].includes(binding.baselineKind as string)) return false;
  if (binding.from.kind === "DRAFT" ? binding.baseManifestHash !== null : !hash(binding.baseManifestHash)) return false;
  return binding.baselineKind !== "INITIAL" || binding.from.kind === "DRAFT" && sameVersion(binding.from, binding.to);
}

/** 审批使用服务端冻结引用，读取报告时所有输入和时间都必须与原绑定相同。 */
export function impactBindingMatches(binding: ImpactApprovalBinding, report: ImpactReport): boolean {
  if (!impactBindingWellFormed(binding)) return false;
  return binding.reportId === report.reportId && binding.canonicalHash === report.canonicalHash && binding.inputFingerprint === report.inputFingerprint
    && binding.baselineKind === report.baselineKind && sameVersion(binding.from, report.diff.from) && sameVersion(binding.to, report.diff.to)
    && sameHashes(binding.baseHashes, report.diff.baseHashes) && sameHashes(binding.targetHashes, report.diff.targetHashes)
    && binding.baseManifestHash === report.diff.baseManifestHash && sameSemantics(binding.targetSemantics, report.targetSemantics)
    && binding.generatedAtUtc === report.generatedAtUtc && binding.expiresAtUtc === report.expiresAtUtc;
}

/** 新发布提案缺旧impact必须重建；回滚沿原合同，不套用新发布报告要求。 */
export function proposalImpactBlocker(proposal: ReleaseProposal, report: ImpactReport | null, releases: ReleaseSummary[] | null,
  now = Date.now()): string | null {
  if (proposal.kind === "ROLLBACK") return null;
  const binding = proposal.impact;
  if (!binding) return "BLOCKED · 历史提案缺少影响绑定，请回到草稿重建发布提案";
  if (!impactBindingWellFormed(binding)) return "UNKNOWN · 冻结影响绑定字段不完整，请重建发布提案";
  const technical = impactTechnicalBlocker(report, now);
  if (technical || !report) return technical;
  if (report.diff.assetId !== proposal.assetId || !sameScope(report.diff.scope, proposal.scope)
    || !impactBindingMatches(binding, report) || !proposal.hashes || !sameHashes(proposal.hashes, binding.targetHashes)
    || binding.to.kind !== "DRAFT" || binding.to.id !== proposal.draftId || binding.to.revision !== proposal.draftRevision
    || !sameSemantics(proposal.semantics, binding.targetSemantics)) return "STALE · 提案、报告或评估绑定不匹配，请重建提案";
  if (!releases) return "UNKNOWN · active版本状态尚未取得";
  const active = releases.filter(release => release.isActive && release.manifest.assetId === proposal.assetId);
  if (active.length > 1 || active.some(release => !sameScope(release.manifest.scope, proposal.scope))) return "UNKNOWN · active范围不确定";
  if (binding.baselineKind === "INITIAL" ? active.length !== 0 : active.length !== 1 || binding.from.kind !== "RELEASE"
    || binding.from.id !== active[0].manifest.releaseId || binding.baseManifestHash !== active[0].manifestHash
    || !sameHashes(binding.baseHashes, active[0].manifest.hashes)) return "STALE · 发布active基线已变化，请重建提案";
  return null;
}
