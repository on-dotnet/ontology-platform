"use client";
import { useEffect, useRef, useState } from "react";
import type { PlatformIdentity } from "../../lib/api/generated";
import type { ImpactReport, ReleaseActivation, ReleaseProposal, ReleaseSummary } from "../../lib/api/g2-generated";
import { command, createG2Client } from "../../lib/api/g2-client";
import { SemanticError, Trace } from "../../components/ui/semantic-feedback";
import { proposalImpactBlocker } from "../ontology/impact-model";
import { ImpactReference } from "./impact-reference";
import "../ontology/workspace.css";

const client = createG2Client();
type Execute = (action: (signal: AbortSignal) => Promise<void>) => Promise<void>;

/** 提案先核验原影响报告；技术阻断、未知和缺绑定不能通过批准或激活按钮越过。 */
export function ProposalCard({ proposal, releases, identity, reason, busy, now, execute, onNotice, onActivation }: {
  proposal: ReleaseProposal; releases: ReleaseSummary[] | null; identity: PlatformIdentity; reason: string; busy: boolean; now: number;
  execute: Execute; onNotice: (message: string) => void; onActivation: (activation: ReleaseActivation) => void;
}) {
  const [report, setReport] = useState<ImpactReport | null>(null);
  const expiry = Date.parse(proposal.expiresAtUtc), expired = !Number.isFinite(expiry) || expiry <= now;
  const own = proposal.submittedBy === identity.subjectId;
  const active = releases?.find(item => item.manifest.assetId === proposal.assetId && item.isActive);
  const impactBlocker = proposalImpactBlocker(proposal, report, releases, now);
  const canReview = !busy && Boolean(reason.trim()) && identity.roles.includes("platform.auditor") && Boolean(now)
    && !own && !expired && proposal.status === "PENDING" && impactBlocker === null;
  const canActivate = !busy && releases !== null && Boolean(reason.trim()) && identity.roles.includes("platform.operator") && Boolean(now)
    && !expired && proposal.status === "APPROVED" && impactBlocker === null;
  function decide(decision: "approve" | "reject") {
    if (!canReview) return;
    void execute(async signal => {
      const result = await client.decide(proposal.proposalId, { decision, command: command(proposal.revision, reason) }, signal);
      if (!signal.aborted) onNotice(`审核已提交：${result.status}`);
    });
  }
  function activate() {
    if (!canActivate) return;
    void execute(async signal => {
      const result = await client.activate({ proposalId: proposal.proposalId, expectedActivationRevision: active?.activationRevision ?? 0,
        expectedActiveReleaseId: active?.manifest.releaseId ?? null, command: command(proposal.revision, reason) }, signal);
      if (!signal.aborted) { onActivation(result); onNotice("服务端已提交激活事务，Manifest、审计和Outbox标识见结果。"); }
    });
  }
  return <article aria-label={`提案${proposal.proposalId}`}>
    <div className="g2-row"><strong>{proposal.kind === "PUBLISH" ? "发布提案" : "回滚提案"}</strong>
      <span className="tag violet">{proposal.status}</span></div>
    <dl className="g2-detail">
      <div><dt>提案 / 修订</dt><dd>{proposal.proposalId} / {proposal.revision}</dd></div>
      <div><dt>资产 / 授权范围</dt><dd>{proposal.assetId} · {proposal.scope.organizationId} / {proposal.scope.siteIds.join(" / ")}</dd></div>
      <div><dt>提交主体 / 到期 UTC</dt><dd>{proposal.submittedBy} · {proposal.expiresAtUtc}</dd></div>
      <div><dt>{proposal.kind === "PUBLISH" ? "绑定草稿 revision / bundle hash" : "绑定目标 release / manifest hash"}</dt>
        <dd>{proposal.kind === "PUBLISH" ? `${proposal.draftId} / ${proposal.draftRevision} / ${proposal.hashes?.bundleHash}`
          : `${proposal.targetReleaseId} / ${proposal.targetManifestHash}`}</dd></div>
      {proposal.approval && <div><dt>真实审核决定</dt>
        <dd>{proposal.approval.approvedBy} · {proposal.approval.decision} · {proposal.approval.bindingHash}</dd></div>}
    </dl>
    {proposal.kind === "PUBLISH" && <ImpactReference binding={proposal.impact} assetId={proposal.assetId} scope={proposal.scope} auto onLoaded={setReport} />}
    {impactBlocker && <p className="g2-notice" role="status">{impactBlocker}</p>}
    {own && <p className="g2-notice">当前主体是提交者，不能自批；请其他授权审核主体处理。</p>}
    {expired && <p className="g2-notice">此提案已到期，不能审核或激活。</p>}
    <div className="g2-row">
      <button className="button" disabled={!canReview} onClick={() => decide("approve")}>异人批准</button>
      <button className="button" disabled={!canReview} onClick={() => decide("reject")}>拒绝提案</button>
      <button className="button primary" disabled={!canActivate} onClick={activate}>
        {proposal.kind === "ROLLBACK" ? "激活已批准回滚" : "激活已批准版本"}
      </button>
    </div>
    {proposal.kind === "PUBLISH" && <p className="muted">原报告、目标、源和profile由服务器在审核与激活时重新核验，审核者不能覆盖技术阻断。</p>}
  </article>;
}

export function ReleaseCard({ release, reason, busy, canActivate, execute, onNotice }: {
  release: ReleaseSummary; reason: string; busy: boolean; canActivate: boolean; execute: Execute; onNotice: (message: string) => void;
}) {
  function rollback() {
    if (busy || !canActivate || !reason.trim() || release.isActive) return;
    void execute(async signal => {
      const proposal = await client.createProposal({ kind: "ROLLBACK", draftId: null, draftRevision: null, hashes: null, validationReportId: null,
        targetReleaseId: release.manifest.releaseId, targetManifestHash: release.manifestHash,
        command: command(release.activationRevision, reason) }, signal);
      if (!signal.aborted) onNotice(`已创建独立回滚提案 ${proposal.proposalId}，需异人审核后激活。`);
    });
  }
  return <article aria-label={`正式版本${release.manifest.releaseId}`}>
    <div className="g2-row"><strong>{release.manifest.releaseId}</strong>
      <span className={`tag ${release.isActive ? "teal" : "blue"}`}>{release.status}{release.isActive ? " · 当前 Active" : ""}</span></div>
    <dl className="g2-detail">
      <div><dt>资产 / 源 revision / 激活 revision</dt><dd>{release.manifest.assetId} / {release.manifest.revision} / {release.activationRevision}</dd></div>
      <div><dt>正式 Manifest SHA256</dt><dd>{release.manifestHash}</dd></div>
      <div><dt>权威 bundle SHA256</dt><dd>{release.manifest.hashes.bundleHash}</dd></div>
      <div><dt>不可变图</dt><dd>{release.manifest.ontologyGraphIri}<br />{release.manifest.dataGraphIri}</dd></div>
    </dl>
    <details><summary>查看真实 Manifest 与制品</summary><pre className="g2-pre">{JSON.stringify(release.manifest, null, 2)}</pre></details>
    <details><summary>追溯正式版本原影响报告</summary>
      <ImpactReference binding={release.impact} assetId={release.manifest.assetId} scope={release.manifest.scope} />
    </details>
    {release.traceId ? <Trace traceId={release.traceId} /> : <p className="muted">Trace 未关联</p>}
    <button className="button" disabled={busy || !canActivate || !reason.trim() || release.isActive} onClick={rollback}>提出回滚至此版本</button>
  </article>;
}

/** 审核、激活、历史报告与回滚继续使用真实独立命令及服务器CAS。 */
export function ReleaseReview({ identity }: { identity: PlatformIdentity }) {
  const [proposals, setProposals] = useState<ReleaseProposal[]>([]);
  const [releases, setReleases] = useState<ReleaseSummary[] | null>(null);
  const [activation, setActivation] = useState<ReleaseActivation | null>(null);
  const [reason, setReason] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [now, setNow] = useState(0);
  const lifetime = useRef<AbortController | null>(null);
  const canActivate = identity.roles.includes("platform.operator");
  useEffect(() => {
    const controller = new AbortController(); lifetime.current = controller;
    const clock = setInterval(() => setNow(Date.now()), 1000);
    Promise.all([client.proposals(controller.signal), client.releases(controller.signal)]).then(([items, versions]) => {
      if (!controller.signal.aborted) { setProposals(items); setReleases(versions); }
    }).catch(cause => { if (!controller.signal.aborted) setError(cause); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { controller.abort(); clearInterval(clock); };
  }, []);
  async function execute(action: (signal: AbortSignal) => Promise<void>) {
    setBusy(true); setError(null); setNotice("");
    const signal = lifetime.current?.signal ?? new AbortController().signal;
    try {
      await action(signal);
      const [items, versions] = await Promise.all([client.proposals(signal), client.releases(signal)]);
      if (!signal.aborted) { setProposals(items); setReleases(versions); }
    } catch (cause) { if (!signal.aborted) setError(cause); }
    finally { if (!signal.aborted) { setBusy(false); setLoading(false); } }
  }
  return <div className="g2-workspace">
    <div className="g2-heading"><div><p className="eyebrow">RELEASE GOVERNANCE</p><h1>审核与发布治理</h1>
      <p>异人批准 · 准确ImpactReport · 不可变Manifest · 激活CAS · 独立回滚提案</p></div>
      <button className="button" disabled={busy} onClick={() => void execute(async () => {})}>刷新真实状态</button>
    </div>
    {error !== null && <SemanticError error={error} />}
    {notice && <p className="g2-notice" role="status">{notice}</p>}
    <section className="g2-panel"><label>审核 / 操作理由
      <input aria-label="审核操作理由" value={reason} onChange={event => setReason(event.target.value)} maxLength={500} disabled={busy} />
    </label></section>
    {loading ? <p role="status">正在读取审核与正式版本…</p> : <div className="g2-split">
      <section className="g2-panel g2-stack"><h2>待审与历史提案</h2>
        {proposals.length === 0 ? <p className="muted">当前授权范围没有提案。</p> : <div className="g2-list">{proposals.map(proposal =>
          <ProposalCard key={`${proposal.proposalId}/${proposal.revision}/${proposal.impact?.canonicalHash ?? "legacy"}`}
            proposal={proposal} releases={releases} identity={identity} reason={reason} busy={busy} now={now}
            execute={execute} onNotice={setNotice} onActivation={setActivation} />)}</div>}
      </section>
      <section className="g2-panel g2-stack"><h2>正式版本与激活记录</h2>
        {releases?.length === 0 ? <p className="muted">暂无正式版本。草稿验证通过并经异人批准后才能发布。</p>
          : <div className="g2-list">{releases?.map(release => <ReleaseCard key={release.manifest.releaseId} release={release}
            reason={reason} busy={busy} canActivate={canActivate} execute={execute} onNotice={setNotice} />)}</div>}
        {activation && <article className="g2-notice"><strong>实际激活结果</strong>
          <dl className="g2-detail">
            <div><dt>release / activation revision</dt><dd>{activation.releaseId} / {activation.activationRevision}</dd></div>
            <div><dt>已提交审计 / Outbox</dt><dd>{activation.auditId} / {activation.outboxEventId}</dd></div>
            <div><dt>Manifest hash</dt><dd>{activation.manifestHash}</dd></div>
          </dl>
          {activation.traceId ? <Trace traceId={activation.traceId} /> : <p className="muted">Trace 未关联</p>}
        </article>}
        <p className="muted">提案或草稿输入变化使旧批准失效。最终权限、期限、报告、hash、baseline和CAS由服务器复核；
          缺失Trace显示未关联，历史Run始终保持原固定snapshot。</p>
      </section>
    </div>}
  </div>;
}
