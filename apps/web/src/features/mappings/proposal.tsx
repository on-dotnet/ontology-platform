"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import type * as G4 from "../../lib/api/g4-generated";
import { command } from "../../lib/api/g2-client";
import { createMappingsClient } from "./api";
import { mappingLabels, useMappingWork } from "./model";
import { AssessmentReport, MappingError, MappingNavigation } from "./assessment";
import "./mappings.css";
const client = createMappingsClient();

/** 跨用户队列由mapping.review服务端授权，前端角色只能决定展示。 */
export function MappingProposalList() {
  const [page, setPage] = useState<G4.MappingPageOfMappingProposalView | null>(null);
  const [status, setStatus] = useState("PENDING");
  const work = useMappingWork(() => setPage(null));
  useEffect(() => {
    const controller = new AbortController(); const generation = work.generation();
    client.proposals(status || undefined, undefined, controller.signal).then(result => { if (!controller.signal.aborted && work.current(generation)) setPage(result.data); })
      .catch(cause => { if (!controller.signal.aborted && work.current(generation)) { setPage(null); work.fail(cause); } });
    return () => controller.abort();
    // 切换筛选从首屏开始，旧游标不带到新筛选。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);
  return <div className="mapping-workspace"><MappingNavigation /><h1>独立审核队列</h1><label>提案状态<select value={status} disabled={work.busy || work.denied} onChange={event => { setPage(null); setStatus(event.target.value); }}><option value="">全部</option>{["PENDING", "APPROVED", "EXPIRED", "STALE", "REJECTED", "CANCELLED"].map(value => <option key={value} value={value}>{mappingLabels[value]}</option>)}</select></label>
    <MappingError error={work.error} retry={work.recoverable ? work.retry : undefined} />{!page && !work.error && <p role="status">正在读取当前有权审核的提案…</p>}
    {page && <section className="mapping-card">{!page.items.length ? <p>本页没有可见提案。</p> : <div className="mapping-scroll" tabIndex={0}><table><thead><tr><th>提案</th><th>操作</th><th>提交者</th><th>当前状态</th><th>截止</th></tr></thead><tbody>{page.items.map(item => <tr key={item.proposalId}><td><Link href={`/data/mapping-proposals/${encodeURIComponent(item.proposalId)}`}>{item.proposalId}</Link></td><td>{item.kind === "PUBLISH" ? "发布" : "回滚"}</td><td>{item.submittedBy}</td><td>{mappingLabels[item.status]}</td><td>{item.expiresAtUtc}</td></tr>)}</tbody></table></div>}
      {page.nextCursor && <button disabled={work.busy} onClick={() => void work.run(() => client.proposals(status || undefined, page.nextCursor!), result => setPage(result.data))}>下一页</button>}</section>}
  </div>;
}

/** 审核固定原文、原报告及hash；刷新永不自动POST批准或激活。 */
export function MappingProposalPage({ id, subjectId, canReview, canActivate }: { id: string; subjectId: string; canReview: boolean; canActivate: boolean }) {
  const [proposal, setProposal] = useState<G4.MappingProposalView | null>(null); const [etag, setEtag] = useState("");
  const [assessment, setAssessment] = useState<G4.MappingAssessmentView | null>(null);
  const [definition, setDefinition] = useState<G4.MappingDefinition | null>(null);
  const [checks, setChecks] = useState<G4.MappingPageOfMappingActivationCheck | null>(null);
  const [reason, setReason] = useState(""); const [refresh, setRefresh] = useState(0);
  const work = useMappingWork(() => { setProposal(null); setAssessment(null); setDefinition(null); setChecks(null); setReason(""); setEtag(""); });
  useEffect(() => {
    const controller = new AbortController(); const generation = work.generation();
    async function read() {
      try {
        const result = await client.proposal(id, controller.signal);
        if (controller.signal.aborted || !work.current(generation)) return;
        const fixed = result.data;
        const [report, target, history] = await Promise.all([client.assessment(fixed.binding.assessmentId, controller.signal),
          fixed.kind === "PUBLISH" ? client.revision(fixed.mappingId, fixed.draftRevision, controller.signal).then(value => value.data.mapping)
            : client.release(fixed.targetReleaseId, controller.signal).then(value => value.data.manifest.mapping), client.checks(id, undefined, controller.signal)]);
        if (controller.signal.aborted || !work.current(generation)) return;
        setProposal(fixed); setEtag(result.etag); setAssessment(report.data); setDefinition(target); setChecks(history.data);
      } catch (cause) { if (!controller.signal.aborted && work.current(generation)) work.fail(cause); }
    }
    void read(); return () => controller.abort();
    // 恢复只GET同一固定ID，迟到响应由代际和abort共同拦截。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id, refresh]);
  function decide(decision: "APPROVE" | "REJECT") {
    if (!proposal || !reason.trim()) return;
    const body: G4.MappingDecisionRequest = { decision, bindingHash: proposal.bindingHash, command: command(proposal.proposalRevision, reason.trim()) };
    void work.run(() => client.decide(id, body, etag), result => { setProposal(result.data); setEtag(result.etag); });
  }
  function activate() {
    if (!proposal || !reason.trim()) return;
    const body: G4.MappingActivationRequest = { bindingHash: proposal.bindingHash, expectedActive: proposal.expectedActive,
      command: command(proposal.proposalRevision, reason.trim()) };
    void work.run(() => client.activate(id, body, etag), receipt => { setProposal(current => current ? { ...current, activation: receipt.data } : null); setRefresh(value => value + 1); });
  }
  function cancel() {
    if (!proposal || !reason.trim()) return;
    const body = { command: command(proposal.proposalRevision, reason.trim()) };
    void work.run(() => client.cancelProposal(id, body, etag), result => { setProposal(result.data); setEtag(result.etag); });
  }
  return <div className="mapping-workspace"><MappingNavigation /><h1>固定映射提案</h1><MappingError error={work.error} retry={work.recoverable ? work.retry : undefined} />
    {!proposal && !work.error && <p role="status">正在重新核验权限并读取受审原文…</p>}{proposal && <>
      <section className="mapping-card"><h2>{proposal.kind === "PUBLISH" ? "发布" : "回滚"} · {mappingLabels[proposal.status]}</h2><dl className="mapping-facts"><div><dt>固定目标</dt><dd>{proposal.kind === "PUBLISH" ? `${proposal.draftId} / 修订 ${proposal.draftRevision}` : proposal.targetReleaseId}</dd></div><div><dt>提交主体</dt><dd>{proposal.submittedBy}</dd></div><div><dt>截止</dt><dd>{proposal.expiresAtUtc}</dd></div><div><dt>审核绑定散列</dt><dd>{proposal.bindingHash}</dd></div><div><dt>当前指针预期</dt><dd>{proposal.expectedActive.releaseId ?? "首次激活"} / 版本 {proposal.expectedActive.activationRevision}</dd></div></dl>
        {proposal.decision && <p>原审核决定：{proposal.decision.decision} · {proposal.decision.decidedBy} · {proposal.decision.decidedAtUtc} · {proposal.decision.reason}</p>}
        {proposal.submittedBy === subjectId && <p>当前主体是提交者，不能审核自己的提案。</p>}
        {definition && <details><summary>完整受审定义（固定原文）</summary><pre>{JSON.stringify(definition, null, 2)}</pre></details>}
        <button disabled={work.busy} onClick={() => setRefresh(value => value + 1)}>只读刷新当前状态与复核历史</button>
      </section>
      {assessment && <AssessmentReport report={assessment} />}
      {proposal.activation ? <section className="mapping-card"><h2>已原子提交</h2><p>激活版本 {proposal.activation.activationRevision} · 审计 {proposal.activation.auditId}</p><Link href={`/data/mapping-releases/${encodeURIComponent(proposal.activation.mappingReleaseId)}`}>读取实际发布与当前可用性</Link></section> : <section className="mapping-card"><h2>人工操作</h2><label>决定或操作理由<input value={reason} maxLength={500} onChange={event => setReason(event.target.value)} /></label><div className="mapping-actions">
        {canReview && subjectId !== proposal.submittedBy && proposal.status === "PENDING" && <><button disabled={work.busy || !reason.trim()} onClick={() => decide("APPROVE")}>批准固定提案</button><button disabled={work.busy || !reason.trim()} onClick={() => decide("REJECT")}>拒绝提案</button></>}
        {canActivate && proposal.status === "APPROVED" && <button disabled={work.busy || !reason.trim()} onClick={activate}>重新核验并{proposal.kind === "PUBLISH" ? "激活发布" : "回滚到固定发布"}</button>}
        {subjectId === proposal.submittedBy && ["PENDING", "APPROVED"].includes(proposal.status) && <button disabled={work.busy || !reason.trim()} onClick={cancel}>取消未激活提案</button>}</div>
        {["STALE", "EXPIRED"].includes(proposal.status) && <p>此提案不能继续激活。请重新评估并提交新提案；历史决定保持不变。</p>}</section>}
      <section className="mapping-card"><h2>激活前独立复核历史</h2>{checks && !checks.items.length && <p>尚无复核；读取页面不会启动复核。</p>}{checks?.items.map(check => <details key={check.checkId}><summary>{check.checkedAtUtc} · {check.stages.every(stage => stage.status === "PASS") ? "七项通过" : "未通过"}</summary><p>检查ID：{check.checkId}；截止：{check.expiresAtUtc}</p><ul>{check.stages.map(stage => <li key={stage.stage}>{mappingLabels[stage.stage]}：{mappingLabels[stage.status]} {stage.issueCodes.join("、")}</li>)}</ul></details>)}{checks?.nextCursor && <button disabled={work.busy} onClick={() => void work.run(() => client.checks(id, checks.nextCursor!), result => setChecks(result.data))}>下一页检查</button>}</section>
    </>}
  </div>;
}
