import { describe, expect, it } from "vitest";
import type {
  ImpactApprovalBinding, ImpactReport, OntologyDraft, ReleaseProposal, ReleaseSummary, SemanticAssessment, SemanticSupportProfile, VersionDiff,
} from "../../lib/api/g2-generated";
import { impactBindingMatches, impactBindingWellFormed, impactReportMatches, impactTechnicalBlocker, publicationBaseline, publicationImpactBlocker, proposalImpactBlocker } from "./impact-model";

const now = Date.parse("2026-10-31T02:00:00Z");
const hashes = { ontologyHash: "a".repeat(64), shapesHash: "b".repeat(64), vocabularyHash: null, dataHash: "c".repeat(64), bundleHash: "d".repeat(64) };
const scope = { organizationId: "org-a", siteIds: ["site-a"] };
const draft = { draftId: "draft", assetId: "asset", revision: 3, scope, hashes } as OntologyDraft;
const profile = { version: "4", hash: "e".repeat(64), reasoningMode: "ASSERTED_ONLY" } as SemanticSupportProfile;
const assessment: SemanticAssessment = { assessmentId: "assessment", assessmentHash: "f".repeat(64), validationReportId: "validation",
  draftId: "draft", revision: 3, hashes, profileVersion: "4", profileHash: profile.hash, executorVersion: "assessment/1",
  assessedAtUtc: "2026-10-31T01:00:00Z", expiresAtUtc: "2026-11-01T01:00:00Z", publishEligible: true, budgetStatus: "COMPLETE", diagnostics: [],
  stages: [...["PARSE", "SUPPORT", "SHACL_CORE", "GOVERNANCE"].map(name => ({ name, code: "pass", status: "PASS" as const })),
    { name: "OWL_REASONING", code: "not_run", status: "NOT_RUN" }] };
const semantics = { profileVersion: "4", profileHash: profile.hash, assessmentId: assessment.assessmentId, assessmentHash: assessment.assessmentHash };
const version = { kind: "DRAFT" as const, id: "draft", revision: 3 };
function report(): ImpactReport {
  const diff: VersionDiff = { assetId: "asset", scope, from: version, to: version, baseHashes: hashes, targetHashes: hashes,
    baseManifestHash: null, targetManifestHash: null, sources: ["ontology", "shapes", "vocabulary", "data"].map((sourceId, index) => ({
      sourceId, baseText: index === 2 ? null : "", targetText: index === 2 ? null : "", baseHash: [hashes.ontologyHash, hashes.shapesHash, null, hashes.dataHash][index],
      targetHash: [hashes.ontologyHash, hashes.shapesHash, null, hashes.dataHash][index], sourceChanged: false,
      graph: { status: "EQUIVALENT", code: "equivalent", visitedNodes: 0, elapsedMilliseconds: 0 }, baseTripleCount: 0, targetTripleCount: 0,
      addedTriples: [], removedTriples: [], tripleDeltaStatus: "EQUIVALENT",
    })) };
  return { schemaVersion: 1, reportId: "impact", inputFingerprint: "1".repeat(64), canonicalHash: "2".repeat(64),
    executorVersion: "ontology-platform/g3-m4-impact/1", budgetIdentity: "graph128-search100000-ms5000-triples5000-report256-bytes8388608/1",
    generatedAtUtc: "2026-10-31T01:00:00Z", expiresAtUtc: "2026-11-01T01:00:00Z", baselineKind: "INITIAL", diff,
    profileVersion: "4", profileHash: profile.hash, targetSemantics: semantics, changedIris: [], assetReferences: ["asset"], blockers: [],
    knownImpacts: [{ code: "initial_asset", message: "首次引入整个资产", blocking: false, affectedIris: [], assetReferences: ["asset"],
      evidence: [{ version, sourceId: "bundle", sourceHash: hashes.bundleHash, triple: null, focusIri: null, path: null, line: null, column: null }] }],
    unknownCoverage: [], publishEligible: true };
}
const baseline = publicationBaseline([], draft);
function binding(value = report()): ImpactApprovalBinding {
  return { reportId: value.reportId, canonicalHash: value.canonicalHash, inputFingerprint: value.inputFingerprint, baselineKind: value.baselineKind,
    from: value.diff.from, to: value.diff.to, baseHashes: value.diff.baseHashes, targetHashes: value.diff.targetHashes,
    baseManifestHash: value.diff.baseManifestHash, targetSemantics: semantics, generatedAtUtc: value.generatedAtUtc, expiresAtUtc: value.expiresAtUtc };
}
function proposal(): ReleaseProposal {
  return { kind: "PUBLISH", draftId: "draft", draftRevision: 3, hashes, semantics, impact: binding(), scope, assetId: "asset" } as ReleaseProposal;
}

describe("M4发布报告与真实active基线", () => {
  it("真实列表无active时明确INITIAL，有active时必须准确Release及manifest", () => {
    expect(baseline).toMatchObject({ kind: "INITIAL", from: version, to: version, active: null });
    const active = { isActive: true, manifestHash: "3".repeat(64), manifest: { assetId: "asset", scope, releaseId: "release-active", hashes } } as ReleaseSummary;
    expect(publicationBaseline([active], draft)).toMatchObject({ kind: "VERSION_PAIR", from: { kind: "RELEASE", id: "release-active", revision: null }, active });
    expect(() => publicationBaseline([active, active], draft)).toThrow("impact_baseline_response_mismatch");
    expect(() => publicationBaseline([{ ...active, manifest: { ...active.manifest, scope: { ...scope, siteIds: ["site-b"] } } }], draft)).toThrow();
  });
  it("报告只有全部当前输入相符才可提交，来源或assessment/profile/修订变化阻断", () => {
    expect(publicationImpactBlocker(report(), draft, assessment, profile, false, baseline, now)).toBeNull();
    for (const [changedDraft, changedAssessment, changedProfile] of [
      [{ ...draft, revision: 4 }, assessment, profile], [draft, { ...assessment, assessmentHash: "0".repeat(64) }, profile],
      [draft, assessment, { ...profile, hash: "0".repeat(64) }], [{ ...draft, hashes: { ...hashes, dataHash: "0".repeat(64) } }, assessment, profile],
    ] as const) expect(publicationImpactBlocker(report(), changedDraft, changedAssessment, changedProfile, false, baseline, now)).not.toBeNull();
    expect(publicationImpactBlocker(report(), draft, assessment, profile, true, baseline, now)).toMatch(/STALE/);
    expect(publicationImpactBlocker(report(), draft, assessment, profile, false, null, now)).toMatch(/UNKNOWN/);
  });
  it("过期、未来时间、blocking unknown、比较预算未定都不能由eligible掩盖", () => {
    expect(impactTechnicalBlocker({ ...report(), expiresAtUtc: "2026-10-31T01:30:00Z" }, now)).toMatch(/EXPIRED/);
    expect(impactTechnicalBlocker({ ...report(), generatedAtUtc: "2026-10-31T03:00:00Z" }, now)).toMatch(/UNKNOWN/);
    const value = report();
    value.unknownCoverage = [{ ...value.knownImpacts[0], code: "unresolved_import", blocking: true }];
    expect(impactTechnicalBlocker(value, now)).toMatch(/BLOCKED/);
    value.unknownCoverage[0].blocking = false;
    expect(impactTechnicalBlocker(value, now)).toBeNull();
    value.diff.sources[0].graph.status = "INDETERMINATE";
    expect(impactTechnicalBlocker(value, now)).toMatch(/INDETERMINATE/);
  });
});

describe("M4报告回复与逐结论证据", () => {
  const request = { from: version, to: version, baselineKind: "INITIAL" as const };
  it("完整持久报告保留首次引入结论和bundle证据", () => {
    expect(impactReportMatches(report(), request, draft)).toBe(true);
  });
  it.each(["source", "version", "missing-evidence", "blank", "missing-diff", "bad-hash", "bad-time"])("拒绝畸形/错绑定报告 %s", mode => {
    const value = report();
    if (mode === "source") value.knownImpacts[0].evidence[0].sourceHash = "0".repeat(64);
    if (mode === "version") value.knownImpacts[0].evidence[0].version = { ...version, revision: 1 };
    if (mode === "missing-evidence") value.knownImpacts[0].evidence = [];
    if (mode === "blank") value.knownImpacts[0].evidence[0].focusIri = "_:not-stable";
    if (mode === "missing-diff") value.diff.sources = [];
    if (mode === "bad-time") value.generatedAtUtc += "\n";
    if (mode === "bad-hash") value.canonicalHash = "2".repeat(64) + "\n";
    expect(impactReportMatches(value, request, draft)).toBe(false);
  });
});

describe("M4提案冻结报告不能被后来输入替换", () => {
  it("报告hash、时间、版本或assessment任一变化都不再匹配原绑定", () => {
    expect(impactBindingWellFormed(binding())).toBe(true);
    expect(impactBindingWellFormed({ ...binding(), targetSemantics: null })).toBe(false);
    expect(impactBindingWellFormed({ ...binding(), baseHashes: {} })).toBe(false);
    expect(impactBindingMatches(binding(), report())).toBe(true);
    expect(impactBindingMatches({ ...binding(), from: undefined } as unknown as ImpactApprovalBinding, report())).toBe(false);
    for (const patch of [{ canonicalHash: "0".repeat(64) }, { expiresAtUtc: "2026-11-01T00:00:00Z" },
      { to: { ...version, revision: 2 } }, { targetSemantics: { ...semantics, assessmentId: "different" } }])
      expect(impactBindingMatches({ ...binding(), ...patch }, report())).toBe(false);
  });
  it("旧缺impact发布不能审核激活，回滚继续原契约", () => {
    expect(proposalImpactBlocker({ ...proposal(), impact: null }, null, [], now)).toMatch(/重建/);
    expect(proposalImpactBlocker({ ...proposal(), kind: "ROLLBACK", impact: null }, null, null, now)).toBeNull();
    expect(proposalImpactBlocker(proposal(), report(), [], now)).toBeNull();
    const otherAsset = report(); otherAsset.diff.assetId = "other-asset";
    expect(proposalImpactBlocker(proposal(), otherAsset, [], now)).toMatch(/STALE/);
  });
  it("active新出现使INITIAL批准失效，报告未读不能当可审核", () => {
    const active = { isActive: true, manifestHash: "3".repeat(64), manifest: { assetId: "asset", scope, releaseId: "release-new", hashes } } as ReleaseSummary;
    expect(proposalImpactBlocker(proposal(), report(), [active], now)).toMatch(/STALE/);
    expect(proposalImpactBlocker(proposal(), null, [], now)).toMatch(/UNKNOWN/);
    expect(proposalImpactBlocker(proposal(), report(), null, now)).toMatch(/UNKNOWN/);
  });
});
