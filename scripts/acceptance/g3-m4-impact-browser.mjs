/** M4真实影响报告、幂等、证据、陈旧/伪造发布绑定；不访问生产。 */
import { readFile, writeFile } from "node:fs/promises";
import { resolve } from "node:path";
import { randomUUID } from "node:crypto";
import { evidenceDirectory } from "./evidence-paths.mjs";

const version = draft => ({ kind: "DRAFT", id: draft.draftId, revision: draft.revision });
const sourceHash = (report, evidence) => {
  const side = JSON.stringify(evidence.version) === JSON.stringify(report.diff.to) ? "targetHash"
    : JSON.stringify(evidence.version) === JSON.stringify(report.diff.from) ? "baseHash" : null;
  if (!side) return null;
  if (evidence.sourceId === "bundle") return (side === "targetHash" ? report.diff.targetHashes : report.diff.baseHashes).bundleHash;
  return report.diff.sources.find(source => source.sourceId === evidence.sourceId)?.[side];
};
export async function runM4ImpactChecks({ root, origin, operator, viewer, single, check, command, setPhase, publicationChecks = false }) {
  const checks = [], startedAtUtc = new Date().toISOString(), started = performance.now();
  let status = "FAIL", phase = "create", identifiers = {};
  const observe = (name, condition, observedStatus) => {
    checks.push({ name, status: condition ? "PASS" : "FAIL", ...(observedStatus === undefined ? {} : { observedStatus }) });
    check("m4_impact_" + name, Boolean(condition), observedStatus);
  };
  const step = value => { phase = value; setPhase("m4_impact_" + value); };
  async function request(user, method, path, data, label, expected = 200) {
    const response = await user.api[method](origin + path, { headers: { ...user.headers,
      ...(data?.command ? { "If-Match": '"' + data.command.expectedRevision + '"' } : {}) }, ...(data ? { data } : {}) });
    observe(label + "_http", response.status() === expected, response.status());
    return response.json();
  }
  const sources = {};
  for (const [key, file] of [["ontologyTurtle", "ontology.ttl"], ["shapesTurtle", "shapes.ttl"], ["vocabularyTurtle", "vocabulary.ttl"], ["dataTurtle", "data.ttl"]]) {
    sources[key] = await readFile(resolve(root, "samples/g2", file), "utf8");
  }
  try {
    const first = await request(operator, "post", "/api/v1/ontology-drafts", { name: "Synthetic M4 Impact " + randomUUID().slice(0, 8),
      sources, baseReleaseId: null, scope: { organizationId: "org-demo", siteIds: ["site-a", "site-b"] }, command: command(0) }, "create");
    identifiers = { assetId: first.assetId, draftId: first.draftId };
    const path = "/api/v1/ontology-drafts/" + first.draftId;
    const assess = draft => request(operator, "post", path + "/assessments", { revision: draft.revision, hashes: draft.hashes,
      command: command(draft.revision) }, "assess_revision_" + draft.revision);
    const assessment = await assess(first);
    observe("real_initial_assessment", assessment.publishEligible && assessment.stages.some(item => item.name === "SHACL_CORE" && item.status === "PASS"));
    const initial = { from: version(first), to: version(first), baselineKind: "INITIAL", assessmentId: assessment.assessmentId, command: command(first.revision) };
    step("initial_report_and_idempotency");
    const report = await request(operator, "post", "/api/v1/impact-reports", initial, "initial_generate");
    identifiers.reportId = report.reportId;
    observe("initial_introduction_not_no_impact", report.publishEligible && report.baselineKind === "INITIAL" && report.knownImpacts.length > 0
      && report.diff.sources.every(item => !item.sourceChanged) && report.targetSemantics.assessmentHash === assessment.assessmentHash
      && report.diff.targetHashes.bundleHash === first.hashes.bundleHash && /^[0-9a-f]{64}$/.test(report.canonicalHash));
    observe("all_conclusions_have_real_source_evidence", [...report.knownImpacts, ...report.blockers, ...report.unknownCoverage].every(item => item.evidence.length > 0
      && item.evidence.every(evidence => sourceHash(report, evidence) === evidence.sourceHash && (evidence.line === null || evidence.line > 0) && (evidence.column === null || evidence.column > 0))));
    observe("uncovered_scope_explicit", report.unknownCoverage.length > 0 && report.unknownCoverage.every(item => !item.blocking));
    const replay = await request(operator, "post", "/api/v1/impact-reports", initial, "exact_replay");
    const concurrent = await Promise.all([0, 1].map(index => request(operator, "post", "/api/v1/impact-reports",
      { ...initial, command: command(first.revision) }, "same_input_independent_key_" + index)));
    const read = await request(viewer, "get", "/api/v1/impact-reports/" + report.reportId, null, "report_read");
    observe("same_input_first_immutable_envelope", [replay, ...concurrent, read].every(item => item.reportId === report.reportId
      && item.canonicalHash === report.canonicalHash && item.inputFingerprint === report.inputFingerprint
      && item.generatedAtUtc === report.generatedAtUtc && item.expiresAtUtc === report.expiresAtUtc));
    const conflict = await request(operator, "post", "/api/v1/impact-reports", { ...initial, baselineKind: "VERSION_PAIR" }, "same_key_different_payload", 409);
    observe("changed_payload_idempotency_conflict", conflict.code === "idempotency_conflict");
    await request(viewer, "post", "/api/v1/impact-reports", { ...initial, command: command(first.revision) }, "viewer_cannot_generate", 403);
    await request(single, "get", "/api/v1/impact-reports/" + report.reportId, null, "partial_scope_report_denied", 403);
    if (!publicationChecks) {
      step("report_ui");
      await operator.page.goto(origin + "/ontologies");
      await operator.page.getByRole("button").filter({ has: operator.page.locator("strong", { hasText: first.name }) }).click();
      await operator.page.getByRole("textbox", { name: "变更理由", exact: true }).fill("Synthetic M4 real impact report UI checkpoint");
      const assessed = operator.page.waitForResponse(response => response.url() === origin + path + "/assessments" && response.request().method() === "POST");
      await operator.page.getByRole("button", { name: "评估发布资格", exact: true }).click();
      observe("ui_real_assessment", (await assessed).status() === 200);
      const panel = operator.page.getByRole("region", { name: "发布影响与审批绑定", exact: true });
      const generated = operator.page.waitForResponse(response => response.url() === origin + "/api/v1/impact-reports" && response.request().method() === "POST");
      await panel.getByRole("button", { name: "生成发布影响报告", exact: true }).click();
      const response = await generated;
      observe("ui_real_report", response.status() === 200, response.status());
      const rendered = await response.json();
      await panel.getByText(rendered.reportId, { exact: false }).first().waitFor();
      observe("ui_exact_report_and_technical_eligibility", (await panel.innerText()).includes(rendered.canonicalHash)
        && await panel.getByRole("button", { name: "提交异人发布审核", exact: true }).isEnabled());
      // 发布调用链尚在下一增量实现，首报告联调只确认按钮绑定，不触发旧发布路径。
      status = "PASS";
      return;
    }
    step("proposal_technical_binding");
    const proposalBody = (draft, selectedAssessment, selectedReport) => ({ kind: "PUBLISH", draftId: draft.draftId, draftRevision: draft.revision,
      hashes: draft.hashes, validationReportId: selectedAssessment.validationReportId, targetReleaseId: null, targetManifestHash: null,
      impactReportId: selectedReport.reportId, impactHash: selectedReport.canonicalHash, command: command(draft.revision) });
    const body = proposalBody(first, assessment, report);
    await request(operator, "post", "/api/v1/release-proposals", { ...body, impactReportId: null, impactHash: null }, "missing_impact_blocked", 422);
    const forged = await request(operator, "post", "/api/v1/release-proposals", { ...body, impactHash: "f".repeat(64), command: command(first.revision) }, "forged_impact_hash", 409);
    observe("forged_hash_conflict", forged.code === "impact_binding_conflict");
    const second = await request(operator, "put", path, { name: first.name,
      sources: { ...first.sources, ontologyTurtle: first.sources.ontologyTurtle + '\n<urn:synthetic:m4:impact:Second> a <http://www.w3.org/2002/07/owl#Class> .\n' },
      command: command(first.revision) }, "save_source_changed");
    const assessment2 = await assess(second);
    await request(operator, "post", "/api/v1/release-proposals", proposalBody(second, assessment2, report), "old_report_new_source_blocked", 409);
    const pair = await request(operator, "post", "/api/v1/impact-reports", { from: version(first), to: version(second), baselineKind: "VERSION_PAIR",
      assessmentId: assessment2.assessmentId, command: command(second.revision) }, "arbitrary_fixed_pair_report");
    observe("changed_source_changes_report_identity", pair.canonicalHash !== report.canonicalHash && pair.inputFingerprint !== report.inputFingerprint
      && pair.changedIris.includes("urn:synthetic:m4:impact:Second") && pair.diff.sources.some(item => item.sourceChanged));
    await request(operator, "post", "/api/v1/release-proposals", proposalBody(second, assessment2, pair), "draft_pair_is_analysis_not_publication_baseline", 422);
    step("unknown_dependency");
    const unknownDraft = await request(operator, "put", path, { name: second.name,
      sources: { ...second.sources, ontologyTurtle: second.sources.ontologyTurtle + '\n<urn:synthetic:m4:impact:ontology> <http://www.w3.org/2002/07/owl#imports> <urn:synthetic:unresolved:dependency> .\n' },
      command: command(second.revision) }, "save_unresolved_import");
    const unknownAssessment = await assess(unknownDraft);
    const unknown = await request(operator, "post", "/api/v1/impact-reports", { from: version(second), to: version(unknownDraft), baselineKind: "VERSION_PAIR",
      assessmentId: unknownAssessment.assessmentId, command: command(unknownDraft.revision) }, "unresolved_dependency_report");
    observe("unknown_never_no_impact_or_publishable", !unknown.publishEligible
      && (unknown.blockers.some(item => item.blocking) || unknown.unknownCoverage.some(item => item.blocking))
      && [...unknown.blockers, ...unknown.unknownCoverage].every(item => item.evidence.length > 0));
    status = "PASS";
  } finally {
    await writeFile(resolve(evidenceDirectory(root), "m4-impact.json"), JSON.stringify({ taskId: "G3-M4-001", slice: "B-Impact", publicationChecks, status, phase,
      startedAtUtc, completedAtUtc: new Date().toISOString(), durationMs: performance.now() - started, identifiers, checks,
      notRun: [...(publicationChecks ? [] : ["proposal/approval/activation binding: next backend slice"]), "expiry/time/provider/profile/activation races: native real module tests", "Windows native", "paid LLM"] }, null, 2) + "\n");
  }
}
