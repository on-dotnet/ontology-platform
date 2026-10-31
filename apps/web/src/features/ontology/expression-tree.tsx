"use client";
import { useCallback, useEffect, useState } from "react";
import type { OntologyDraft, OwlExpressionSnapshot, OwlExpressionSource, RdfTerm, SourceBundle } from "../../lib/api/g2-generated";
import { createG2Client } from "../../lib/api/g2-client";
import { SemanticError } from "../../components/ui/semantic-feedback";
import {
  buildExpressionTree, expressionLocation, expressionPredicateLabel, expressionSnapshotMatches,
  expressionTermLabel, ExpressionReadSession, type ExpressionBranch,
} from "./expression-model";
import "./expression-tree.css";

const client = createG2Client();
const kindLabels: Record<string, string> = {
  restriction: "限制表达式", intersection: "交集", union: "并集", complement: "补集",
  list: "有序 RDF List", axiom: "公理主体", term: "RDF 主体",
};
const sourceLabels: Record<string, string> = { ontology: "本体", shapes: "约束", vocabulary: "术语", data: "事实" };

/** 用原生details呈现有界展开，字面量和引用从不变成外部可执行链接。 */
function ExpressionBranchView({ branch }: { branch: ExpressionBranch }) {
  const label = expressionTermLabel(branch.term);
  if (branch.reference) {
    const reason = { shared: "共享引用（已在本源展示）", cycle: "循环路径引用（停止展开）", budget: "展示预算已达上限" }[branch.reference];
    return <span><strong>{reason}</strong> · <code>{label}</code></span>;
  }
  if (!branch.node) return <code>{label}</code>;
  return (
    <details>
      <summary>{kindLabels[branch.node.kind] ?? "未知结构标签"} · <code>{label}</code></summary>
      {branch.orderedItems.length > 0 && (
        <ol aria-label="有序 RDF List 成员">
          {branch.orderedItems.map((item, index) => <li key={index}><ExpressionBranchView branch={item} /></li>)}
        </ol>
      )}
      <ul aria-label="真实 RDF 谓词与值">
        {branch.properties.map((property, index) => (
          <li key={index}>
            <strong>{expressionPredicateLabel(property.predicateIri)}</strong> · <code>{property.predicateIri}</code>
            <ul>{property.values.map((value, valueIndex) => (
              <li key={valueIndex}><ExpressionBranchView branch={value} /></li>
            ))}</ul>
          </li>
        ))}
      </ul>
    </details>
  );
}

/** 每源状态与来源独立展示；损坏结构仍有真实源码后备，不推断可发布。 */
function ExpressionSourceTree({ source, onLocate }: {
  source: OwlExpressionSource; onLocate?: (source: OwlExpressionSource, focus: RdfTerm | null) => void;
}) {
  const tree = buildExpressionTree(source);
  const diagnosticLimit = 128;
  return (
    <details open className="g3-expression-tree" aria-label={`表达式源 ${source.sourceId}`}>
      <summary>{sourceLabels[source.sourceId] ?? source.sourceId} · {source.sourceId} · {source.status}</summary>
      <p className="g2-hash">source hash {source.sourceHash}</p>
      <dl className="g2-detail" aria-label={`${source.sourceId} 语义支持分级`}>
        <div><dt>源码保留 source-preserved</dt><dd>{source.sourcePreserved ? "是 · 原文保留" : "UNKNOWN · 未核实"}</dd></div>
        <div><dt>结构只读 read-only-structured</dt><dd>{source.readOnlyStructured ? "完整只读结构" : "INDETERMINATE · 结构不完整"}</dd></div>
        <div><dt>结构编辑 editable</dt><dd>不可编辑 · 此视图只读</dd></div>
        <div><dt>发布资格 publishEligible</dt><dd>{source.publishEligible === "BLOCKED" ? "BLOCKED · 支持策略阻断" : "NOT_ASSESSED · 未执行发布门禁"}</dd></div>
        <div><dt>推理 inferred</dt><dd>否 · OWL 推理 NOT_RUN</dd></div>
      </dl>
      <button className="button" disabled={!onLocate} onClick={() => onLocate?.(source, null)}>查看 {source.sourceId} 原始源码</button>
      <p className="muted">位置依据 sourceId / hash / RDF主体与谓词；没有可靠字符位置时行、列均为 UNKNOWN。</p>
      {tree.roots.length === 0 ? <p>此源没有可展示的 RDF 主体。</p> : (
        <ul aria-label={`${source.sourceId} 只读表达式树`}>
          {tree.roots.map((branch, index) => <li key={index}><ExpressionBranchView branch={branch} /></li>)}
        </ul>
      )}
      {tree.truncated && <p className="g2-notice">界面展示预算已达上限，部分结构未展开。此状态不代表完整支持，请查看原始源码与服务端诊断。</p>}
      {source.diagnostics.slice(0, diagnosticLimit).map((item, index) => (
        <article className="g2-notice" key={index} aria-label={`表达式诊断 ${source.sourceId} ${index + 1}`}>
          <strong>{item.code}</strong>
          <p>{item.message}</p>
          <p className="g2-hash">focusNode {item.focusNode ? expressionTermLabel(item.focusNode) : "UNKNOWN"}</p>
          <p className="g2-hash">predicate {item.predicateIri ?? "UNKNOWN"}</p>
          <p>行 {item.line ?? "UNKNOWN"} / 列 {item.column ?? "UNKNOWN"}</p>
          <button className="button" disabled={!onLocate} onClick={() => onLocate?.(source, item.focusNode)}>定位表达式诊断来源 {index + 1}</button>
        </article>
      ))}
      {source.diagnostics.length > diagnosticLimit && <p className="g2-notice">共有 {source.diagnostics.length} 条诊断，仅显示前 {diagnosticLimit} 条；请结合原始源码核对。</p>}
    </details>
  );
}

/** 精确版本的四源只读树；源保留、结构支持和发布推理分别报告。 */
export function ExpressionReadView({ snapshot, onLocate }: {
  snapshot: OwlExpressionSnapshot; onLocate?: (source: OwlExpressionSource, focus: RdfTerm | null) => void;
}) {
  return (
    <section className="g2-stack" aria-label="高阶表达式只读视图">
      <h3>高阶 OWL 只读表达式与公理</h3>
      <p>{snapshot.version.kind === "DRAFT" ? "固定草稿" : "固定正式 Release"} {snapshot.version.id} · revision {snapshot.version.revision ?? "不适用"}</p>
      <p className="g2-hash">{snapshot.scope.organizationId} / {snapshot.scope.siteIds.join(" / ")} · bundle {snapshot.hashes.bundleHash}</p>
      <p className="g2-hash">profile {snapshot.profileId} · v{snapshot.profileVersion} · {snapshot.profileHash}</p>
      <p className="muted">此视图不修改源、修订或批准。解析成功不等于可发布，SHACL 通过不证明 OWL 逻辑一致性。</p>
      <p className="muted">allValuesFrom 不保证存在关系；Functional 不等于数据库唯一键；属性链保留顺序，导航不等于推理。</p>
      <p className="muted">imports 只显示引用，不联网加载；空白节点标识仅在本源 hash / 版本内有效，不按名称推断 sameAs。</p>
      {snapshot.sources.map(source => <ExpressionSourceTree key={source.sourceId} source={source} onLocate={onLocate} />)}
    </section>
  );
}

/** 挂载时读取真实保存修订；切换/刷新取消旧请求，不让旧结果绑定新缓冲。 */
export function DraftExpressions({ draft, dirty, onLocate }: {
  draft: OntologyDraft; dirty: boolean; onLocate: (field: keyof SourceBundle, focus: string | null) => void;
}) {
  const [session] = useState(() => new ExpressionReadSession());
  const [snapshot, setSnapshot] = useState<OwlExpressionSnapshot | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(true);
  const read = useCallback(() => {
    const controller = session.begin();
    // 以真实请求完成事件更新React；非法参数也进入异步失败分支，不在effect同步setState。
    return Promise.resolve().then(() => client.draftExpressions(draft.draftId, draft.revision, controller.signal))
      .then(result => {
        if (!session.isCurrent(controller)) return;
        const target = { version: { kind: "DRAFT" as const, id: draft.draftId, revision: draft.revision }, hashes: draft.hashes, scope: draft.scope };
        if (!expressionSnapshotMatches(result, target)) throw new Error("只读表达式未绑定准确修订、范围与四源hash，已拒绝。");
        setSnapshot(result);
      })
      .catch(cause => { if (session.isCurrent(controller)) setError(cause); })
      .finally(() => { if (session.isCurrent(controller)) setLoading(false); });
  }, [draft, session]);
  useEffect(() => {
    void read();
    return () => session.invalidate();
  }, [read, session]);
  return (
    <section className="g2-stack" aria-label="草稿高阶表达式">
      <button className="button" disabled={loading} onClick={() => {
        setLoading(true); setSnapshot(null); setError(null); void read();
      }}>刷新高阶表达式</button>
      {loading && <p role="status">正在读取准确修订的高阶表达式…</p>}
      {error !== null && <SemanticError error={error} />}
      {dirty && <p className="g2-notice">本地缓冲已修改，以下仅对应已保存 revision {draft.revision}；来源定位已禁用，请保存或丢弃后刷新。</p>}
      {snapshot && <ExpressionReadView snapshot={snapshot} onLocate={dirty ? undefined : (source, focus) => {
        const field = expressionLocation(source, draft, dirty);
        if (field) onLocate(field, focus?.kind === "iri" ? focus.value : null);
      }} />}
    </section>
  );
}

/** 固定Release只读来源由服务端核验，不用当前草稿源或相同blank名称替代。 */
export function ReleasedExpressions() {
  const [session] = useState(() => new ExpressionReadSession());
  const [releaseId, setReleaseId] = useState("");
  const [snapshot, setSnapshot] = useState<OwlExpressionSnapshot | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => () => session.invalidate(), [session]);
  async function read() {
    const id = releaseId.trim();
    const controller = session.begin();
    setLoading(true); setSnapshot(null); setError(null);
    try {
      const result = await client.releasedExpressions(id, controller.signal);
      if (!session.isCurrent(controller)) return;
      if (!expressionSnapshotMatches(result, { version: { kind: "RELEASE", id, revision: null } }))
        throw new Error("表达式未绑定固定正式版本与权威源，已拒绝。");
      setSnapshot(result);
    } catch (cause) {
      if (session.isCurrent(controller)) setError(cause);
    } finally {
      if (session.isCurrent(controller)) setLoading(false);
    }
  }
  return (
    <details className="g2-stack">
      <summary>读取固定正式Release高阶表达式</summary>
      <label>表达式 Release ID
        <input aria-label="表达式Release ID" value={releaseId} onChange={event => {
          session.invalidate(); setReleaseId(event.target.value); setSnapshot(null); setError(null); setLoading(false);
        }} />
      </label>
      <button className="button" disabled={loading || !releaseId.trim()} onClick={() => void read()}>读取固定Release表达式</button>
      {loading && <p role="status">正在核验固定正式版本高阶表达式…</p>}
      {error !== null && <SemanticError error={error} />}
      {snapshot && <ExpressionReadView snapshot={snapshot} />}
    </details>
  );
}
