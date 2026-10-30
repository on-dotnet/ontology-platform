"use client";
import { useEffect, useRef, useState } from "react";
import type { GenerateImpactReportRequest, ImpactReport, OntologyDraft, VersionDiff, VersionRefKind } from "../../lib/api/g2-generated";
import { command, createG2Client } from "../../lib/api/g2-client";
import { fixedVersion, versionDiffMatches } from "./version-diff-model";
import { VersionDiffView } from "./version-diff-view";
import { impactReportMatches } from "./impact-model";
import { ImpactReportView } from "./impact-report-view";
import { sameHashes } from "./vocabulary-model";

const client = createG2Client();
/** 显式选择同资产两个固定草稿修订或Release，切换和取消后旧回复不能覆盖新选择。 */
export function FixedVersionComparison({ draft, busy, execute, canEdit = false, dirty = true, reason = "" }: {
  draft: OntologyDraft; busy: boolean; canEdit?: boolean; dirty?: boolean; reason?: string; execute: (action: (signal: AbortSignal) => Promise<void>) => Promise<void>;
}) {
  const [from, setFrom] = useState({ kind: "DRAFT" as VersionRefKind, id: draft.draftId, revision: "1" });
  const [to, setTo] = useState({ kind: "DRAFT" as VersionRefKind, id: draft.draftId, revision: String(draft.revision) });
  const [diff, setDiff] = useState<VersionDiff | null>(null);
  const [status, setStatus] = useState("UNKNOWN · 尚未读取两个固定版本");
  const [comparing, setComparing] = useState(false);
  const [assessmentId, setAssessmentId] = useState("");
  const [analysis, setAnalysis] = useState<ImpactReport | null>(null);
  const [generating, setGenerating] = useState(false);
  const retry = useRef<{ signature: string; request: GenerateImpactReportRequest } | null>(null);
  const current = useRef<AbortController | null>(null);
  useEffect(() => () => { current.current?.abort(); current.current = null; }, []);
  const source = fixedVersion(from.kind, from.id, from.revision), target = fixedVersion(to.kind, to.id, to.revision);
  function reset() {
    current.current?.abort(); current.current = null; setDiff(null); setAnalysis(null); retry.current = null; setGenerating(false); setComparing(false); setStatus("UNKNOWN · 版本选择已变化，请重新读取");
  }
  function compare() {
    if (!source || !target || busy) return;
    current.current?.abort();
    const controller = new AbortController(), request = { from: source, to: target };
    current.current = controller;
    setComparing(true); setDiff(null); setStatus("正在读取固定版本并比较四源…");
    void execute(async lifetime => {
      const signal = AbortSignal.any([lifetime, controller.signal]);
      try {
        const result = await client.versionDiff(request, signal);
        if (signal.aborted || current.current !== controller) return;
        if (!versionDiffMatches(result, request, draft.assetId, draft.scope)) throw new Error("version_diff_response_mismatch");
        setDiff(result); setStatus("四源固定版本结果已返回；未知状态保持可见。");
      } catch (cause) {
        if (current.current !== controller) return;
        if (signal.aborted) setStatus("INDETERMINATE · 本次比较已取消，不能认定无差异");
        else { setStatus("UNKNOWN · 读取或固定版本绑定失败"); throw cause; }
      } finally { if (current.current === controller) { setComparing(false); current.current = null; } }
    });
  }
  function generateAnalysis() {
    if (!source || !target || busy || dirty || !canEdit || !reason.trim()) return;
    const payload = { from: source, to: target, baselineKind: "VERSION_PAIR" as const,
      assessmentId: target.kind === "RELEASE" ? null : assessmentId.trim() || null };
    const signature = JSON.stringify({ ...payload, reason });
    if (retry.current?.signature !== signature) retry.current = { signature,
      request: { ...payload, command: command(target.kind === "DRAFT" ? target.revision! : 0, reason) } };
    const request = retry.current.request, controller = new AbortController();
    current.current?.abort(); current.current = controller;
    setAnalysis(null); setGenerating(true); setStatus("正在生成固定版本影响分析；缺评估或未知范围将保持阻断状态…");
    void execute(async lifetime => {
      const signal = AbortSignal.any([lifetime, controller.signal]);
      try {
        const result = await client.generateImpact(request, signal);
        if (signal.aborted || current.current !== controller) return;
        if (!impactReportMatches(result, payload, draft) || target.kind === "DRAFT" && target.id === draft.draftId
          && target.revision === draft.revision && !sameHashes(result.diff.targetHashes, draft.hashes)) throw new Error("impact_response_mismatch");
        setAnalysis(result); setStatus("固定版本影响报告已返回。当前发布仍须使用准确active基线与当前目标评估。");
      } catch (cause) {
        if (current.current !== controller) return;
        if (signal.aborted) setStatus("INDETERMINATE · 本次影响分析已取消");
        else { setStatus("UNKNOWN · 影响分析生成或输入绑定失败"); throw cause; }
      } finally { if (current.current === controller) { setGenerating(false); current.current = null; } }
    });
  }
  return <section className="g2-stack" aria-label="任意固定版本差异">
    <h3>任意两个固定版本</h3>
    <p className="muted">只能比较同一资产和完整范围。Release修订必须为空；草稿必须明确固定revision，不能使用latest。</p>
    {([{ label: "基准", value: from, update: setFrom }, { label: "目标", value: to, update: setTo }]).map(({ label, value, update }) =>
      <fieldset className="g3-identity-form" disabled={busy || comparing || generating} key={label}><legend>{label}固定版本</legend>
        <label>{label}版本类型<select aria-label={`${label}版本类型`} value={value.kind} onChange={event => {
          reset(); update(previous => ({ ...previous, kind: event.target.value as VersionRefKind }));
        }}><option value="DRAFT">固定草稿修订</option><option value="RELEASE">不可变Release</option></select></label>
        <label>{label}版本ID<input aria-label={`${label}版本ID`} value={value.id} onChange={event => {
          reset(); update(previous => ({ ...previous, id: event.target.value }));
        }} /></label>
        <label>{label}固定修订<input aria-label={`${label}固定修订`} value={value.kind === "RELEASE" ? "" : value.revision}
          disabled={value.kind === "RELEASE"} inputMode="numeric" onChange={event => {
            reset(); update(previous => ({ ...previous, revision: event.target.value }));
          }} /></label>
      </fieldset>)}
    <div className="g2-row">
      <button className="button" disabled={busy || comparing || generating || !source || !target} onClick={compare}>比较固定版本四源源码</button>
      <button className="button" disabled={!comparing} onClick={() => current.current?.abort()}>取消固定版本比较</button>
    </div>
    <p className="g2-notice" role="status">{status}</p>
    {diff && <VersionDiffView diff={diff} />}
    <section className="g2-stack" aria-label="任意固定版本影响分析">
      <h4>生成固定版本影响分析</h4>
      <p className="muted">VERSION_PAIR分析允许任意两个固定版本。目标Release从原manifest恢复评估，AssessmentId=null；
        目标草稿可明确提供持久评估ID，缺失时报告保持BLOCKED。新发布仍须准确active基线和当前评估。</p>
      <label>分析目标评估ID（可空）<input aria-label="分析评估ID" value={target?.kind === "RELEASE" ? "" : assessmentId}
        disabled={busy || generating || target?.kind === "RELEASE" || !canEdit} onChange={event => {
          reset(); setAssessmentId(event.target.value);
        }} /></label>
      <div className="g2-row">
        <button className="button" disabled={busy || generating || dirty || !canEdit || !reason.trim() || !source || !target}
          onClick={generateAnalysis}>生成所选版本影响分析</button>
        <button className="button" disabled={!generating} onClick={() => current.current?.abort()}>取消所选版本影响分析</button>
      </div>
      {dirty && <p className="g2-notice">请先提交或取消源码、身份或词汇编辑，再生成固定版本报告。</p>}
      {!canEdit && <p className="muted">当前角色可读取版本差异；生成持久报告需要ontology.edit权限。</p>}
      {analysis && <ImpactReportView report={analysis} />}
    </section>
  </section>;
}
