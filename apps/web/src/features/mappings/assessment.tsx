"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import type * as G4 from "../../lib/api/g4-generated";
import { command } from "../../lib/api/g2-client";
import { PlatformApiError } from "../../lib/api/client";
import { createMappingsClient, MappingApiError } from "./api";
import { mappingLabels, proposalRequest, useMappingWork } from "./model";
import "./mappings.css";
const client = createMappingsClient();

/** 本切片导航沿现有Shell，不提前展示M4业务查询。 */
export function MappingNavigation() {
  return <nav className="mapping-nav" aria-label="映射工作区"><Link href="/data/mappings">映射列表</Link><Link href="/data/mappings/new">新建映射</Link><Link href="/data/mapping-proposals">独立审核</Link><Link href="/data/connections">连接与目录</Link><span className="tag">人工模式 · AI OFF</span></nav>;
}

/** 错误保持安全代码，权限拒绝时不继续展示旧正文。 */
export function MappingError({ error, retry }: { error: unknown; retry?: () => void }) {
  if (!error) return null;
  const denied = error instanceof PlatformApiError && [401, 403].includes(error.status);
  const conflict = error instanceof PlatformApiError && error.status === 409;
  return <div role="alert" className="mapping-alert"><strong>{denied ? "当前身份无权读取或操作此映射" : conflict ? "输入版本或状态已变化" : "请求未完成"}</strong>
    <p>{error instanceof PlatformApiError ? error.code : error instanceof Error ? error.message : "请检查连接后重试。"}</p>
    {conflict && <p>未保存内容仍留在当前页面。请读取当前版本后比较；不要直接覆盖他人的修改。</p>}
    {error instanceof MappingApiError && error.checkId && <p>复核记录：{error.checkId}。刷新提案可读取已保存的检查结果。</p>}
    {!denied && retry && <button type="button" onClick={retry}>使用原命令恢复结果</button>}
    {denied && <Link href="/data/mappings">返回重新验证身份</Link>}</div>;
}

/** 七项逐项呈现，零测试、未运行和证据不足都不显示为成功。 */
export function AssessmentReport({ report }: { report: G4.MappingAssessmentView }) {
  return <section className="mapping-card" aria-label="七阶段评估"><h2>七阶段评估 <span className="tag">{mappingLabels[report.status] ?? report.status}</span></h2>
    <p>目标：{report.target.kind === "PUBLISH" ? `草稿修订 ${report.target.draftRevision}` : `历史发布 ${report.target.targetReleaseId}`}；到期：{report.expiresAtUtc}</p>
    <div className="mapping-scroll" tabIndex={0}><table><thead><tr><th>检查</th><th>结果</th><th>问题代码</th></tr></thead><tbody>{report.stages.map(stage => <tr key={stage.stage}><th>{mappingLabels[stage.stage]}</th><td data-state={stage.status}>{mappingLabels[stage.status]}</td><td>{stage.issueCodes.join("、") || "无"}</td></tr>)}</tbody></table></div>
    {!!report.issues.length && <ul>{report.issues.map((issue, index) => <li key={`${issue.code}:${index}`}>{issue.code} · {issue.bindingId ?? "整体"}{issue.fieldRef ? ` · ${issue.fieldRef.datasetRef.name}.${issue.fieldRef.name}` : ""}</li>)}</ul>}
    <details><summary>固定版本与证据</summary><dl className="mapping-facts">{Object.entries(report.binding).map(([name, value]) => <div key={name}><dt>{name}</dt><dd>{String(value)}</dd></div>)}</dl><p>语义不变量：{report.semanticResultHash}</p><p>本次观察：{report.evidenceHash}</p></details>
  </section>;
}

/** jobId是唯一恢复入口；刷新只GET，最多20轮，不重新调度任务。 */
export function MappingJobPanel({ jobId, mappingId, canEdit, onDenied }: { jobId: string; mappingId: string; canEdit: boolean; onDenied?: () => void }) {
  const [job, setJob] = useState<G4.MappingJobView | null>(null);
  const [etag, setEtag] = useState("");
  const [paused, setPaused] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const work = useMappingWork(() => { setJob(null); setEtag(""); onDenied?.(); });
  useEffect(() => {
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>; let count = 0;
    const generation = work.generation();
    async function poll() {
      try {
        const result = await client.job(jobId, controller.signal);
        if (controller.signal.aborted || !work.current(generation)) return;
        setJob(result.data); setEtag(result.etag);
        if (["QUEUED", "RUNNING"].includes(result.data.status)) {
          if (++count < 20) timer = setTimeout(poll, 1500); else setPaused(true);
        }
      } catch (cause) { if (!controller.signal.aborted && work.current(generation)) work.fail(cause); }
    }
    void poll(); return () => { controller.abort(); clearTimeout(timer); };
    // 同一job的恢复只由显式刷新触发，权限代际由work检查。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, refresh]);
  function cancel() {
    if (!job) return;
    const body = { command: command(job.revision, "取消映射验证") };
    void work.run(() => client.cancelJob(jobId, body, etag), result => { setJob(result.data); setEtag(result.etag); });
  }
  return <section className="mapping-card"><h2>验证任务</h2><MappingError error={work.error} retry={work.recoverable ? work.retry : undefined} />
    {!job && !work.error && <p role="status">正在读取持久任务…</p>}
    {job && <><p role="status">{mappingLabels[job.status]} · {job.jobId}</p>{job.issueCodes.length > 0 && <p>{job.issueCodes.join("、")}</p>}
      {job.assessmentId && <Link href={`/data/mappings/${encodeURIComponent(mappingId)}/assessments/${encodeURIComponent(job.assessmentId)}`}>打开固定评估报告</Link>}
      {canEdit && ["QUEUED", "RUNNING"].includes(job.status) && <button type="button" disabled={work.busy} onClick={cancel}>取消验证</button>}</>}
    {paused && !work.denied && <button type="button" onClick={() => { setPaused(false); setRefresh(value => value + 1); }}>继续读取任务状态</button>}</section>;
}

/** 固定报告深链可恢复并创建严格PUBLISH/ROLLBACK提案，不自动批准。 */
export function MappingAssessmentPage({ mappingId, assessmentId, canEdit }: { mappingId: string; assessmentId: string; canEdit: boolean }) {
  const [report, setReport] = useState<G4.MappingAssessmentView | null>(null);
  const [draft, setDraft] = useState<Pick<G4.MappingDraftView, "scope" | "draftId"> | null>(null);
  const [created, setCreated] = useState<G4.MappingProposalView | null>(null);
  const [reason, setReason] = useState("");
  const work = useMappingWork(() => { setReport(null); setDraft(null); setCreated(null); setReason(""); });
  useEffect(() => {
    const controller = new AbortController(); const generation = work.generation();
    void client.assessment(assessmentId, controller.signal).then(async assessment => {
      if (assessment.data.mappingId !== mappingId) throw new MappingApiError(403, "mapping_forbidden");
      const target = assessment.data.target;
      const fixed = target.kind === "PUBLISH"
        ? (await client.revision(mappingId, target.draftRevision, controller.signal)).data
        : (await client.release(target.targetReleaseId, controller.signal)).data.manifest;
      const identity = { scope: fixed.scope, draftId: "draftId" in fixed ? fixed.draftId : fixed.originDraftId };
      if (!controller.signal.aborted && work.current(generation)) { setReport(assessment.data); setDraft(identity); }
    })
      .catch(cause => { if (!controller.signal.aborted && work.current(generation)) work.fail(cause); });
    return () => controller.abort();
    // 固定深链切换时重新授权；不会POST。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mappingId, assessmentId]);
  function submit() {
    if (!report || !draft || !reason.trim()) return;
    const body = proposalRequest(report, draft, command(0, reason.trim()));
    void work.run(() => client.propose(mappingId, body), result => setCreated(result.data));
  }
  return <div className="mapping-workspace"><MappingNavigation /><h1>固定评估报告</h1><MappingError error={work.error} retry={work.recoverable ? work.retry : undefined} />
    {!report && !work.error && <p role="status">正在读取报告与当前权限…</p>}{report && <AssessmentReport report={report} />}
    {created ? <section className="mapping-card"><h2>已提交独立审核</h2><Link href={`/data/mapping-proposals/${encodeURIComponent(created.proposalId)}`}>打开提案</Link></section> : canEdit && report && draft && <section className="mapping-card"><h2>提交审核</h2><label>提交理由<input value={reason} maxLength={500} onChange={event => setReason(event.target.value)} /></label><p>固定目标与全部输入版本提交后不会随草稿变化。审核者必须是另一主体。</p><button disabled={work.busy || !reason.trim() || report.status !== "READY_FOR_PROPOSAL"} onClick={submit}>提交固定提案</button></section>}
  </div>;
}
