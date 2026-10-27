"use client";
import { useEffect, useState } from "react";
import { command, createG2Client } from "../../lib/api/g2-client";
import type { OntologyDraft, SemanticAssessment, SemanticSupportProfile, SemanticValidationReport, SourceBundle } from "../../lib/api/g2-generated";
import { Trace } from "../../components/ui/semantic-feedback";
import { DiagnosticCard } from "./diagnostic-card";
import { assessmentEligibility } from "./semantic-status";

const client = createG2Client();

/** 保留G2校验报告，同时用服务器assessment绑定当前修订的发布资格。 */
export function AssessmentPanel({ draft, profile, dirty, busy, canEdit, reason, execute, onNotice, onLocate }: {
  draft: OntologyDraft;
  profile: SemanticSupportProfile | null;
  dirty: boolean;
  busy: boolean;
  canEdit: boolean;
  reason: string;
  execute: (action: (signal: AbortSignal) => Promise<void>) => Promise<void>;
  onNotice: (message: string) => void;
  onLocate?: (field: keyof SourceBundle, focus: string | null) => void;
}) {
  const [report, setReport] = useState<SemanticValidationReport | null>(null);
  const [assessment, setAssessment] = useState<SemanticAssessment | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const eligibility = assessmentEligibility(assessment, draft, profile, dirty, now);
  const blocked = busy || dirty || !canEdit || !reason.trim();

  useEffect(() => {
    const interval = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(interval);
  }, []);

  /** 独立评估命令不接受客户端结论；响应带关联ValidationReportId供原发布提案复用。 */
  function assess() {
    void execute(async signal => {
      setAssessment(null);
      const result = await client.assessDraft(draft.draftId, {
        revision: draft.revision, hashes: draft.hashes, command: command(draft.revision, reason),
      }, signal);
      if (!signal.aborted) {
        setAssessment(result);
        setNow(Date.now());
      }
    });
  }

  return (
    <section className="g2-stack" aria-label="校验与发布资格">
      <section className="g3-model-status" aria-label="建模能力四状态">
        <h3>建模能力四状态</h3>
        <dl className="g2-detail">
          <div><dt>可保存</dt><dd>{!canEdit ? "只读 · 无编辑权限" : busy ? "请求处理中"
            : dirty ? "可提交保存 · 保存时由服务端解析校验" : "已保存 · 当前修订无需保存"}</dd></div>
          <div><dt>可结构编辑</dt><dd>{!profile ? "UNKNOWN · 支持档案未取得" : !canEdit ? "只读 · 无编辑权限"
            : !draft.projection.structuralEditAllowed ? "只读 · 原始图含未支持语义"
            : dirty ? "暂停 · 请先保存源码" : !profile.capabilities.some(item => item.edit === "BASIC")
              ? "UNKNOWN · 档案未提供基础编辑能力" : "BASIC · 依服务器投影与支持档案"}</dd></div>
          <div><dt>可发布</dt><dd>{eligibility}</dd></div>
          <div><dt>可推理</dt><dd>OWL_REASONING · NOT_RUN</dd></div>
        </dl>
      </section>
      <h3>SHACL 与支持子集</h3>
      <div className="g2-row">
        <button className="button" disabled={blocked} onClick={() => void execute(async signal => {
          setReport(await client.validateDraft(draft.draftId, {
            revision: draft.revision, hashes: draft.hashes, command: command(draft.revision, reason),
          }, signal));
        })}>验证已保存修订</button>
        <button className="button" disabled={blocked || !profile} onClick={assess}>评估发布资格</button>
      </div>
      {dirty && <p className="muted">保存后才能验证和评估当前文本。</p>}
      {report && (
        <>
          <strong>{report.kind} · {report.conforms ? "符合" : "不符合"} · revision {report.revision}</strong>
          <p className="g2-hash">{report.hashes.bundleHash}</p>
          {report.issues.map((issue, index) => (
            <article className="g2-notice" key={index}>
              <p>当前修订的已登记语义/数据约束返回诊断；源码已保留，请结合评估阶段与诊断原文判断。</p>
              <strong>{issue.severity} · {issue.message}</strong>
              <p>{issue.focusNode?.value} · {issue.path}</p>
              <small>{issue.constraintComponent} · {issue.sourceId}</small>
            </article>
          ))}
          <Trace traceId={report.traceId} />
        </>
      )}
      <p className="g2-notice" role="status">发布资格：{eligibility === "ELIGIBLE" ? "ELIGIBLE · 当前评估符合，提交时服务器再次核验" : eligibility}</p>
      <p className="muted">OWL 逻辑推理：NOT_RUN。校验符合不等于完整 OWL 推理通过。</p>
      {assessment && (
        <>
          <p>assessment {assessment.assessmentId} · revision {assessment.revision}</p>
          <p>预算 {assessment.budgetStatus} · 服务端 publishEligible {String(assessment.publishEligible)}</p>
          <p>评估于 {assessment.assessedAtUtc} · 到期 {assessment.expiresAtUtc} · executor {assessment.executorVersion}</p>
          <p className="g2-hash">profile v{assessment.profileVersion} · {assessment.profileHash}</p>
          <p className="g2-hash">assessment hash {assessment.assessmentHash}</p>
          <p className="g2-hash">bundle {assessment.hashes.bundleHash} · report {assessment.validationReportId}</p>
          <ul className="g2-node-list" aria-label="评估阶段">
            {assessment.stages.map(stage => <li key={stage.name}>{stage.name} · {stage.status} · {stage.code}</li>)}
          </ul>
          {assessment.diagnostics.map((item, index) => (
            <DiagnosticCard key={index} item={item} index={index} draft={draft} dirty={dirty} onLocate={onLocate} />
          ))}
          <button className="button" disabled={busy} onClick={() => void execute(async signal => {
            const result = await client.assessment(assessment.assessmentId, signal);
            if (!signal.aborted) { setAssessment(result); setNow(Date.now()); }
          })}>重读持久评估</button>
        </>
      )}
      <button className="button primary" disabled={blocked || eligibility !== "ELIGIBLE"} onClick={() => {
        if (!assessment || assessmentEligibility(assessment, draft, profile, dirty) !== "ELIGIBLE") return;
        void execute(async signal => {
          const proposal = await client.createProposal({
            kind: "PUBLISH", draftId: draft.draftId, draftRevision: draft.revision, hashes: draft.hashes,
            validationReportId: assessment.validationReportId, targetReleaseId: null, targetManifestHash: null,
            command: command(draft.revision, reason),
          }, signal);
          onNotice(`真实发布提案已提交 ${proposal.proposalId}，请由其他主体在发布治理中审核。`);
        });
      }}>提交异人发布审核</button>
    </section>
  );
}
