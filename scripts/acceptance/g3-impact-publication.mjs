/** 从真实服务读取唯一活动基线，生成绑定当前assessment的发布影响报告。 */
export async function generatePublicationImpact({ origin, user, draft, assessment, command, post, check }) {
  const response = await user.api.get(origin + "/api/v1/releases");
  check("impact_baseline_catalog_http", response.status() === 200, response.status());
  const releases = await response.json();
  const active = releases.filter(release => release.isActive && release.manifest.assetId === draft.assetId);
  check("impact_baseline_unique", active.length <= 1);
  if (active.length > 1) throw new Error("impact_baseline_ambiguous");
  const target = { kind: "DRAFT", id: draft.draftId, revision: draft.revision };
  const report = await post(user, "/api/v1/impact-reports", { from: active.length
    ? { kind: "RELEASE", id: active[0].manifest.releaseId, revision: null } : target,
    to: target, baselineKind: active.length ? "VERSION_PAIR" : "INITIAL", assessmentId: assessment.assessmentId,
    command: command(draft.revision) });
  check("impact_report_current_assessment_binding", report.publishEligible && report.diff.to.kind === "DRAFT"
    && report.diff.to.id === draft.draftId && report.diff.to.revision === draft.revision
    && report.diff.targetHashes.bundleHash === draft.hashes.bundleHash
    && report.targetSemantics?.assessmentHash === assessment.assessmentHash
    && report.blockers.length === 0 && report.unknownCoverage.every(item => !item.blocking)
    && /^[0-9a-f]{64}$/.test(report.canonicalHash));
  return report;
}
