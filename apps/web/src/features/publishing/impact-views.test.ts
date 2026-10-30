import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { PlatformIdentity } from "../../lib/api/generated";
import type { ImpactReport, OntologyDraft, ReleaseProposal, ReleaseSummary } from "../../lib/api/g2-generated";
import { ProposalCard, ReleaseCard } from "./review";
import { ImpactReportView } from "../ontology/impact-report-view";
import { FixedVersionComparison } from "../ontology/fixed-version-comparison";
import { PublicationImpactPanel } from "../ontology/publication-impact-panel";
const scope = { organizationId: "org-a", siteIds: ["site-a"] };
const identity = { subjectId: "reviewer", roles: ["platform.auditor", "platform.operator"] } as PlatformIdentity;
const draft = { draftId: "draft", assetId: "asset", revision: 3, scope, hashes: { bundleHash: "bundle" } } as OntologyDraft;
const proposal = { proposalId: "proposal-fixed", revision: 1, kind: "PUBLISH", assetId: "asset", scope,
  draftId: "draft", draftRevision: 3, hashes: { bundleHash: "bundle" }, submittedBy: "other", expiresAtUtc: "2026-11-01T00:00:00Z",
  status: "PENDING", impact: null } as ReleaseProposal;
const noop = () => undefined;
const execute = async () => undefined;

describe("M4真实审核组件的失败关闭展示", () => {
  it("旧缺impact发布提案明确重建，审核和激活按钮均禁用", () => {
    const html = renderToStaticMarkup(createElement(ProposalCard, { proposal, releases: [], identity, reason: "审核原因", busy: false,
      now: Date.parse("2026-10-31T00:00:00Z"), execute, onNotice: noop, onActivation: noop }));
    expect(html).toContain("重建发布提案");
    expect(html).toMatch(/disabled=""[^>]*>异人批准/);
    expect(html).toMatch(/disabled=""[^>]*>拒绝提案/);
    expect(html).toMatch(/disabled=""[^>]*>激活已批准版本/);
  });
  it("旧版本无impact仍保留独立回滚提案入口", () => {
    const release = { manifest: { releaseId: "release-fixed", assetId: "asset", scope, revision: 2,
      hashes: { bundleHash: "bundle" }, ontologyGraphIri: "urn:graph:ontology", dataGraphIri: "urn:graph:data" },
    manifestHash: "manifest", activationRevision: 2, isActive: false, status: "SUPERSEDED", traceId: "", impact: null } as ReleaseSummary;
    const html = renderToStaticMarkup(createElement(ReleaseCard, { release, reason: "恢复历史版本", busy: false, canActivate: true, execute, onNotice: noop }));
    expect(html).toContain("追溯正式版本原影响报告");
    expect(html).toContain("历史版本没有影响报告绑定");
    expect(html).toContain(">提出回滚至此版本</button>");
    expect(html).not.toMatch(/disabled=""[^>]*>提出回滚至此版本/);
  });
  it("任意版本分析只读禁持久写，版本读取仍可用，缺评估语义明确", () => {
    const html = renderToStaticMarkup(createElement(FixedVersionComparison, { draft, busy: false, canEdit: false, dirty: false, reason: "查看差异", execute }));
    expect(html).toContain("AssessmentId=null");
    expect(html).toContain("缺失时报告保持BLOCKED");
    expect(html).toMatch(/disabled=""[^>]*>生成所选版本影响分析/);
    expect(html).not.toMatch(/disabled=""[^>]*>比较固定版本四源源码/);
  });
  it("实际active基线和报告尚未读到时不允许生成或提交发布", () => {
    const html = renderToStaticMarkup(createElement(PublicationImpactPanel, { draft, assessment: null, profile: null,
      dirty: false, busy: false, canEdit: true, reason: "发布原因", execute, onNotice: noop }));
    expect(html).toContain("正在读取真实发布基线");
    expect(html).toMatch(/disabled=""[^>]*>生成发布影响报告/);
    expect(html).toMatch(/disabled=""[^>]*>提交异人发布审核/);
  });
  it("未知覆盖、技术阻断和证据版本/hash/UNKNOWN位置分别显示，不写全系统无影响", () => {
    const version = { kind: "DRAFT", id: "draft-fixed", revision: 3 };
    const conclusion = { code: "unresolved_import", message: "变化触及未解析依赖", blocking: true, affectedIris: ["urn:ref:a"], assetReferences: ["asset"],
      evidence: [{ version, sourceId: "bundle", sourceHash: "hash-fixed", triple: null, focusIri: null, path: null, line: null, column: null }] };
    const report = { reportId: "report-fixed", canonicalHash: "canonical-fixed", inputFingerprint: "input-fixed", baselineKind: "INITIAL",
      generatedAtUtc: "2026-10-31T00:00:00Z", expiresAtUtc: "2026-11-01T00:00:00Z", profileVersion: "4", profileHash: "profile-fixed",
      targetSemantics: null, executorVersion: "impact/1", budgetIdentity: "budget", publishEligible: false, changedIris: [], assetReferences: [],
      diff: { from: version, to: version, assetId: "asset", scope, sources: [], baseManifestHash: null, targetManifestHash: null },
      knownImpacts: [], blockers: [conclusion], unknownCoverage: [conclusion] } as unknown as ImpactReport;
    const html = renderToStaticMarkup(createElement(ImpactReportView, { report }));
    for (const value of ["技术阻断项", "未知与未覆盖范围", "变化触及未解析依赖", "hash-fixed", "draft-fixed", "UNKNOWN", "canonical-fixed", "INITIAL 首次引入整个资产"])
      expect(html).toContain(value);
    expect(html).not.toContain("全系统无影响。");
  });
});
