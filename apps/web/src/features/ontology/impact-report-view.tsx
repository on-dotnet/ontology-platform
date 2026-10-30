"use client";
import type { ImpactApprovalBinding, ImpactConclusion, ImpactEvidenceReference, ImpactReport, VersionRef } from "../../lib/api/g2-generated";
import { termText } from "./vocabulary-model";
import { VersionDiffView } from "./version-diff-view";

export const versionText = (version: VersionRef) => `${version.kind} ${version.id} / ${version.revision ?? "固定Release"}`;

/** 每条结论的真实证据绑定固定版本与来源散列，不推断缺失行列或业务观察时间。 */
function EvidenceView({ evidence }: { evidence: ImpactEvidenceReference }) {
  return <article className="g2-notice" aria-label="影响结论证据">
    <p>{versionText(evidence.version)} · 来源 {evidence.sourceId}</p>
    <p className="g2-hash">source hash {evidence.sourceHash}</p>
    <p className="g2-hash">focus {evidence.focusIri ?? "UNKNOWN / bundle-level"} · path {evidence.path ?? "UNKNOWN"}</p>
    <p>行 {evidence.line ?? "UNKNOWN"} / 列 {evidence.column ?? "UNKNOWN"}</p>
    {evidence.triple ? <p className="g2-hash">{termText(evidence.triple.subject)} → {evidence.triple.predicate} → {termText(evidence.triple.object)}</p>
      : <p>此结论以来源或命名资源证据定位，未声称具有稳定空白节点三元组或精确行列。</p>}
  </article>;
}
function Conclusions({ title, values }: { title: string; values: ImpactConclusion[] }) {
  return <section className="g2-stack" aria-label={title}>
    <h4>{title}（{values.length}项）</h4>
    {values.length === 0 ? <p>报告本栏未列出结论；这不等于已覆盖或排除其它系统影响。</p> : values.map((item, index) =>
      <article className="g2-notice" key={`${item.code}/${index}`}>
        <strong>{item.code} · {item.blocking ? "阻断" : "有界结论 / 范围说明"}</strong>
        <p>{item.message}</p>
        <p className="g2-hash">影响IRI：{item.affectedIris.join(" / ") || "未列出"}</p>
        <p className="g2-hash">资产引用：{item.assetReferences.join(" / ") || "未列出"}</p>
        <details><summary>查看结论证据（{item.evidence.length}项）</summary>
          <div className="g2-stack">{item.evidence.map((evidence, evidenceIndex) => <EvidenceView key={evidenceIndex} evidence={evidence} />)}</div>
        </details>
      </article>)}
  </section>;
}

/** 影响报告区分已知、技术阻断和未知范围，不把未覆盖内容归为无影响。 */
export function ImpactReportView({ report }: { report: ImpactReport }) {
  return <section className="g2-stack" aria-label="影响报告详情">
    <h3>可追溯 ImpactReport</h3>
    <dl className="g2-detail">
      <div><dt>持久报告 ID</dt><dd>{report.reportId}</dd></div>
      <div><dt>Canonical hash</dt><dd>{report.canonicalHash}</dd></div>
      <div><dt>输入 fingerprint</dt><dd>{report.inputFingerprint}</dd></div>
      <div><dt>基线模式 / 固定版本</dt><dd>{report.baselineKind}<br />{versionText(report.diff.from)} → {versionText(report.diff.to)}</dd></div>
      <div><dt>生成 / 到期 UTC</dt><dd>{report.generatedAtUtc} / {report.expiresAtUtc}</dd></div>
      <div><dt>Profile / assessment</dt><dd>{report.profileVersion} / {report.profileHash}<br />
        {report.targetSemantics?.assessmentId ?? "UNKNOWN"} / {report.targetSemantics?.assessmentHash ?? "UNKNOWN"}</dd></div>
      <div><dt>执行器 / 预算</dt><dd>{report.executorVersion}<br />{report.budgetIdentity}</dd></div>
      <div><dt>服务器有界技术资格</dt><dd>{report.publishEligible ? "有界技术资格符合；仍须当前绑定、异人审批和激活重验" : "BLOCKED / INDETERMINATE"}</dd></div>
      <div><dt>变化IRI</dt><dd>{report.changedIris.join(" / ") || "未列出；不代表全系统无影响"}</dd></div>
      <div><dt>资产引用</dt><dd>{report.assetReferences.join(" / ") || "未列出"}</dd></div>
    </dl>
    {report.baselineKind === "INITIAL" && <p className="g2-notice">INITIAL 首次引入整个资产。源自比的no-op不表示首次发布没有影响。</p>}
    <Conclusions title="已知影响" values={report.knownImpacts} />
    <Conclusions title="技术阻断项" values={report.blockers} />
    <Conclusions title="未知与未覆盖范围" values={report.unknownCoverage} />
    <p className="muted">报告只覆盖本资产四源显式事实与已知引用。未执行完整OWL推理；未知不等于无影响，审核者不能覆盖技术阻断。</p>
    <details><summary>查看报告绑定的四源差异</summary><VersionDiffView diff={report.diff} /></details>
  </section>;
}

/** 提案和正式版本显示服务端冻结的原始引用，不能用后来生成的报告替代。 */
export function ImpactBindingView({ binding }: { binding: ImpactApprovalBinding }) {
  return <section className="g2-stack" aria-label="冻结影响审批绑定">
    <h4>准确报告与审批绑定</h4>
    <dl className="g2-detail">
      <div><dt>原报告 / hash</dt><dd>{binding.reportId}<br />{binding.canonicalHash}</dd></div>
      <div><dt>输入 fingerprint</dt><dd>{binding.inputFingerprint}</dd></div>
      <div><dt>原基线与目标</dt><dd>{binding.baselineKind}<br />{versionText(binding.from)} → {versionText(binding.to)}</dd></div>
      <div><dt>原active manifest</dt><dd>{binding.baseManifestHash ?? "INITIAL / 无active"}</dd></div>
      <div><dt>原profile / assessment</dt><dd>{binding.targetSemantics.profileVersion} / {binding.targetSemantics.profileHash}<br />
        {binding.targetSemantics.assessmentId} / {binding.targetSemantics.assessmentHash}</dd></div>
      <div><dt>生成 / 到期 UTC</dt><dd>{binding.generatedAtUtc} / {binding.expiresAtUtc}</dd></div>
    </dl>
    <details><summary>查看冻结四源 Base / Target hashes</summary>
      <pre className="g2-pre">{JSON.stringify({ base: binding.baseHashes, target: binding.targetHashes }, null, 2)}</pre>
    </details>
  </section>;
}
