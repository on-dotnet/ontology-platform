"use client";
import { useEffect, useRef, useState } from "react";
import type {
  GenerateImpactReportRequest, ImpactReport, OntologyDraft, SemanticAssessment, SemanticSupportProfile,
} from "../../lib/api/g2-generated";
import { command, createG2Client } from "../../lib/api/g2-client";
import { SemanticError } from "../../components/ui/semantic-feedback";
import { assessmentEligibility } from "./semantic-status";
import { impactReportMatches, publicationBaseline, publicationImpactBlocker, type PublicationBaseline } from "./impact-model";
import { ImpactReportView, versionText } from "./impact-report-view";

const client = createG2Client();
type Props = {
  draft: OntologyDraft; assessment: SemanticAssessment | null; profile: SemanticSupportProfile | null;
  dirty: boolean; busy: boolean; canEdit: boolean; reason: string;
  execute: (action: (signal: AbortSignal) => Promise<void>) => Promise<void>; onNotice: (message: string) => void;
};

/** 每个输入身份拥有独立状态，旧报告不会跨修订或评估状态复用。 */
function BoundPublicationImpactPanel({ draft, assessment, profile, dirty, busy, canEdit, reason, execute, onNotice }: Props) {
  const [baseline, setBaseline] = useState<PublicationBaseline | null>(null);
  const [baselineError, setBaselineError] = useState<unknown>(null);
  const [baselineLoading, setBaselineLoading] = useState(true);
  const [refresh, setRefresh] = useState(0);
  const [report, setReport] = useState<ImpactReport | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const current = useRef<AbortController | null>(null);
  const retry = useRef<{ signature: string; request: GenerateImpactReportRequest } | null>(null);
  const assessmentStatus = assessmentEligibility(assessment, draft, profile, dirty, now);
  const blocker = publicationImpactBlocker(report, draft, assessment, profile, dirty, baseline, now);
  const blocked = busy || dirty || !canEdit || !reason.trim();
  useEffect(() => {
    const clock = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(clock);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    current.current?.abort(); current.current = controller;
    retry.current = null;
    client.releases(controller.signal).then(releases => {
      if (!controller.signal.aborted) { setBaseline(publicationBaseline(releases, draft)); setBaselineLoading(false); }
    }).catch(error => {
      if (!controller.signal.aborted) { setBaselineError(error); setBaselineLoading(false); }
    });
    return () => { controller.abort(); if (current.current === controller) current.current = null; };
  }, [draft, refresh]);

  function generate() {
    if (blocked || !baseline || !assessment || assessmentStatus !== "ELIGIBLE") return;
    const expected = baseline, selectedAssessment = assessment;
    void execute(async lifetime => {
      const controller = current.current;
      if (!controller) return;
      const signal = AbortSignal.any([lifetime, controller.signal]);
      const payload = { from: expected.from, to: expected.to, baselineKind: expected.kind, assessmentId: selectedAssessment.assessmentId };
      const signature = JSON.stringify({ ...payload, reason });
      if (retry.current?.signature !== signature) retry.current = { signature,
        request: { ...payload, command: command(draft.revision, reason) } };
      setReport(null);
      const result = await client.generateImpact(retry.current.request, signal);
      if (signal.aborted || current.current !== controller) return;
      if (!impactReportMatches(result, payload, draft)) throw new Error("impact_response_mismatch");
      if (result.diff.to.id !== draft.draftId || result.diff.to.revision !== draft.revision) throw new Error("impact_target_conflict");
      setReport(result); setNow(Date.now());
      onNotice(`持久影响报告 ${result.reportId} 已返回；请检查已知、技术阻断和未知范围。`);
    });
  }
  function propose() {
    if (blocked || !report || !assessment || publicationImpactBlocker(report, draft, assessment, profile, dirty, baseline) !== null) return;
    const selected = report, selectedAssessment = assessment;
    void execute(async signal => {
      const proposal = await client.createProposal({ kind: "PUBLISH", draftId: draft.draftId, draftRevision: draft.revision, hashes: draft.hashes,
        validationReportId: selectedAssessment.validationReportId, targetReleaseId: null, targetManifestHash: null,
        impactReportId: selected.reportId, impactHash: selected.canonicalHash, command: command(draft.revision, reason) }, signal);
      if (!signal.aborted) onNotice(`真实发布提案已提交 ${proposal.proposalId}，已绑定影响报告 ${selected.reportId}；请其他主体审核。`);
    });
  }
  return <section className="g2-stack" aria-label="发布影响与审批绑定">
    <h3>发布影响与审批绑定</h3>
    <p className="muted">先评估当前已保存修订，再生成准确报告。首次发布是INITIAL资产引入；已有active必须使用其固定Release作为基线。</p>
    {baselineError !== null && <SemanticError error={baselineError} />}
    <p role="status">{baselineLoading ? "正在读取真实发布基线…" : baseline ? `${baseline.kind} · ${versionText(baseline.from)} → ${versionText(baseline.to)}`
      : "UNKNOWN · 发布基线读取失败，不能猜测首次发布"}</p>
    {baseline?.active && <p className="g2-hash">active manifest {baseline.active.manifestHash}</p>}
    <div className="g2-row">
      <button className="button" disabled={busy} onClick={() => {
        current.current?.abort(); setBaseline(null); setBaselineLoading(true); setBaselineError(null); setReport(null);
        retry.current = null; setRefresh(value => value + 1);
      }}>刷新发布影响基线</button>
      <button className="button" disabled={blocked || !baseline || assessmentStatus !== "ELIGIBLE"} onClick={generate}>生成发布影响报告</button>
    </div>
    {report && <ImpactReportView report={report} />}
    <p className="g2-notice" role="status">影响审批资格：{blocker ?? "READY · 报告与当前修订/评估/基线匹配，提交时服务器重验"}</p>
    <p className="muted">输入变化、未保存源码或身份/词汇编辑会清除旧报告的可提交绑定。报告过期不通过重试自动刷新。</p>
    <button className="button primary" disabled={blocked || blocker !== null} onClick={propose}>提交异人发布审核</button>
  </section>;
}


/** 当前评估→准确active基线→持久报告→新提案；任一输入或未保存状态变化都会销毁旧本地绑定。 */
export function PublicationImpactPanel(props: Props) {
  const { draft, assessment, profile, dirty } = props;
  const key = JSON.stringify({ draftId: draft.draftId, assetId: draft.assetId, scope: draft.scope, revision: draft.revision, hashes: draft.hashes,
    assessmentId: assessment?.assessmentId, assessmentHash: assessment?.assessmentHash,
    profileVersion: profile?.version, profileHash: profile?.hash, reasoningMode: profile?.reasoningMode, dirty });
  return <BoundPublicationImpactPanel key={key} {...props} />;
}
