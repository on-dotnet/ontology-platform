"use client";
import { useEffect, useRef, useState } from "react";
import type { PlatformIdentity } from "../../lib/api/generated";
import type { ReleaseActivation, ReleaseProposal, ReleaseSummary } from "../../lib/api/g2-generated";
import { command, createG2Client } from "../../lib/api/g2-client";
import { SemanticError, Trace } from "../../components/ui/semantic-feedback";
import "../ontology/workspace.css";
const client = createG2Client();
/** 发布提案绑定精确hash与修订，审核/激活/回滚均发送真实独立命令。 */
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
  const canApprove = identity.roles.includes("platform.auditor");
  const canActivate = identity.roles.includes("platform.operator");
  useEffect(() => {
    const controller = new AbortController(); lifetime.current = controller;
    const clock = setInterval(() => setNow(Date.now()), 1000);
    Promise.all([client.proposals(controller.signal), client.releases(controller.signal)]).then(([items, versions]) => { if (!controller.signal.aborted) { setProposals(items); setReleases(versions); } }).catch(cause => { if (!controller.signal.aborted) setError(cause); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { controller.abort(); clearInterval(clock); };
  }, []);
  /** 先完成真实响应，再刷新列表；失败不显示成功横幅。 */
  async function execute(action: (signal: AbortSignal) => Promise<void>) {
    setBusy(true); setError(null); setNotice("");
    const signal = lifetime.current?.signal ?? new AbortController().signal;
    try { await action(signal); const [items, versions] = await Promise.all([client.proposals(signal), client.releases(signal)]); if (!signal.aborted) { setProposals(items); setReleases(versions); } }
    catch (cause) { if (!signal.aborted) setError(cause); }
    finally { if (!signal.aborted) { setBusy(false); setLoading(false); } }
  }
  return <div className="g2-workspace"><div className="g2-heading"><div><p className="eyebrow">RELEASE GOVERNANCE</p><h1>审核与发布治理</h1><p>异人批准 · 不可变 Manifest · 激活 CAS · 独立回滚提案</p></div><button className="button" disabled={busy} onClick={() => void execute(async () => {})}>刷新真实状态</button></div>
    {error !== null && <SemanticError error={error} />}{notice && <p className="g2-notice" role="status">{notice}</p>}
    <section className="g2-panel"><label>审核 / 操作理由<input aria-label="审核操作理由" value={reason} onChange={event => setReason(event.target.value)} maxLength={500} disabled={busy} /></label></section>
    {loading ? <p role="status">正在读取审核与正式版本…</p> : <div className="g2-split"><section className="g2-panel g2-stack"><h2>待审与历史提案</h2>{proposals.length === 0 ? <p className="muted">当前授权范围没有提案。</p> : <div className="g2-list">{proposals.map(proposal => {
      const expired = Date.parse(proposal.expiresAtUtc) <= now;
      const own = proposal.submittedBy === identity.subjectId;
      const active = releases?.find(item => item.manifest.assetId === proposal.assetId && item.isActive);
      return <article key={proposal.proposalId}><div className="g2-row"><strong>{proposal.kind === "PUBLISH" ? "发布提案" : "回滚提案"}</strong><span className="tag violet">{proposal.status}</span></div><dl className="g2-detail"><div><dt>提案 / 修订</dt><dd>{proposal.proposalId} / {proposal.revision}</dd></div><div><dt>资产 / 授权范围</dt><dd>{proposal.assetId} · {proposal.scope.organizationId} / {proposal.scope.siteIds.join(" / ")}</dd></div><div><dt>提交主体 / 到期 UTC</dt><dd>{proposal.submittedBy} · {proposal.expiresAtUtc}</dd></div><div><dt>{proposal.kind === "PUBLISH" ? "绑定草稿 revision / bundle hash" : "绑定目标 release / manifest hash"}</dt><dd>{proposal.kind === "PUBLISH" ? `${proposal.draftId} / ${proposal.draftRevision} / ${proposal.hashes?.bundleHash}` : `${proposal.targetReleaseId} / ${proposal.targetManifestHash}`}</dd></div>{proposal.approval && <div><dt>真实审核决定</dt><dd>{proposal.approval.approvedBy} · {proposal.approval.decision} · {proposal.approval.bindingHash}</dd></div>}</dl>
        {own && <p className="g2-notice">当前主体是提交者，不能自批；请其他授权审核主体处理。</p>}{expired && <p className="g2-notice">此提案已到期，不能审核或激活。</p>}
        <div className="g2-row">{(["approve", "reject"] as const).map(decision => <button className="button" key={decision} disabled={busy || !reason.trim() || !canApprove || !now || own || expired || proposal.status !== "PENDING"} onClick={() => void execute(async signal => { const result = await client.decide(proposal.proposalId, { decision, command: command(proposal.revision, reason) }, signal); setNotice(`审核已提交：${result.status}`); })}>{decision === "approve" ? "异人批准" : "拒绝提案"}</button>)}<button className="button primary" disabled={busy || releases === null || !reason.trim() || !canActivate || !now || expired || proposal.status !== "APPROVED"} onClick={() => void execute(async signal => { const result = await client.activate({ proposalId: proposal.proposalId, expectedActivationRevision: active?.activationRevision ?? 0, expectedActiveReleaseId: active?.manifest.releaseId ?? null, command: command(proposal.revision, reason) }, signal); setActivation(result); setNotice("服务端已提交激活事务，Manifest、审计和Outbox标识见结果。"); })}>{proposal.kind === "ROLLBACK" ? "激活已批准回滚" : "激活已批准版本"}</button></div></article>;
    })}</div>}</section>
    <section className="g2-panel g2-stack"><h2>正式版本与激活记录</h2>{releases?.length === 0 ? <p className="muted">暂无正式版本。草稿验证通过并经异人批准后才能发布。</p> : <div className="g2-list">{releases?.map(release => <article key={release.manifest.releaseId}><div className="g2-row"><strong>{release.manifest.releaseId}</strong><span className={`tag ${release.isActive ? "teal" : "blue"}`}>{release.status}{release.isActive ? " · 当前 Active" : ""}</span></div><dl className="g2-detail"><div><dt>资产 / 源 revision / 激活 revision</dt><dd>{release.manifest.assetId} / {release.manifest.revision} / {release.activationRevision}</dd></div><div><dt>正式 Manifest SHA256</dt><dd>{release.manifestHash}</dd></div><div><dt>权威 bundle SHA256</dt><dd>{release.manifest.hashes.bundleHash}</dd></div><div><dt>不可变图</dt><dd>{release.manifest.ontologyGraphIri}<br />{release.manifest.dataGraphIri}</dd></div></dl><details><summary>查看真实 Manifest 与制品</summary><pre className="g2-pre">{JSON.stringify(release.manifest, null, 2)}</pre></details>{release.traceId ? <Trace traceId={release.traceId} /> : <p className="muted">Trace 未关联</p>}<button className="button" disabled={busy || !canActivate || !reason.trim() || release.isActive} onClick={() => void execute(async signal => { const proposal = await client.createProposal({ kind: "ROLLBACK", draftId: null, draftRevision: null, hashes: null, validationReportId: null, targetReleaseId: release.manifest.releaseId, targetManifestHash: release.manifestHash, command: command(release.activationRevision, reason) }, signal); setNotice(`已创建独立回滚提案 ${proposal.proposalId}，需异人审核后激活。`); })}>提出回滚至此版本</button></article>)}</div>}
      {activation && <article className="g2-notice"><strong>实际激活结果</strong><dl className="g2-detail"><div><dt>release / activation revision</dt><dd>{activation.releaseId} / {activation.activationRevision}</dd></div><div><dt>已提交审计 / Outbox</dt><dd>{activation.auditId} / {activation.outboxEventId}</dd></div><div><dt>Manifest hash</dt><dd>{activation.manifestHash}</dd></div></dl>{activation.traceId ? <Trace traceId={activation.traceId} /> : <p className="muted">Trace 未关联</p>}</article>}
      <p className="muted">提案或草稿变化会使旧批准失效。UI限制仅用于交互，最终授权、过期、hash与CAS由服务端复核。专业 Trace 关联只使用服务端实际持久字段，缺失时显示未关联。</p>
    </section></div>}
  </div>;
}
