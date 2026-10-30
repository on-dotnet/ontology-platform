"use client";
import { useState } from "react";
import type { RdfTriple, SourceVersionDiff, VersionDiff } from "../../lib/api/g2-generated";
import { comparisonLabel } from "./semantic-status";
import { termText } from "./vocabulary-model";
import { lineEnding, sourceLineChanges } from "./version-diff-model";

/** 原始typed RDF项逐字段显示；语言、datatype和空白作用域不从文本反建。 */
export function TripleDelta({ triples, title }: { triples: RdfTriple[]; title: string }) {
  return <details><summary>{title}（{triples.length}项）</summary>
    {triples.length === 0 ? <p>服务端本项无确定三元组差异；仍须结合图状态和未知覆盖判断。</p> : <ol className="g2-node-list">
      {triples.map((triple, index) => <li className="g2-hash" key={index}>
        {termText(triple.subject)} → {triple.predicate} → {termText(triple.object)}
      </li>)}
    </ol>}
  </details>;
}

function SourceDiffCard({ source }: { source: SourceVersionDiff }) {
  const [limit, setLimit] = useState(200);
  const changes = sourceLineChanges(source.baseText, source.targetText);
  /** 直接导出服务器原文，浏览器显示标记不进入Blob或改变原换行。 */
  function download(text: string | null, side: string) {
    if (text === null) return;
    const url = URL.createObjectURL(new Blob([text], { type: "text/turtle;charset=utf-8", endings: "transparent" }));
    const anchor = document.createElement("a");
    anchor.href = url; anchor.download = `${source.sourceId}-${side}.ttl`; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  }
  return <article className="g2-notice" aria-label={`${source.sourceId}四源差异`}>
    <h4>{source.sourceId} · {comparisonLabel(source.graph.status)}</h4>
    <p>原始字节：{source.sourceChanged ? "有变化" : "未变化"} · 图状态 {source.graph.code}</p>
    <p className="g2-hash">基准 hash {source.baseHash ?? "absent · 未提供"}</p>
    <p className="g2-hash">目标 hash {source.targetHash ?? "absent · 未提供"}</p>
    <p>已解析三元组：{source.baseTripleCount ?? "UNKNOWN"} → {source.targetTripleCount ?? "UNKNOWN"}</p>
    <p>Typed delta：{source.tripleDeltaStatus} · 搜索节点 {source.graph.visitedNodes} · {source.graph.elapsedMilliseconds} ms</p>
    {source.tripleDeltaStatus === "INDETERMINATE" && <p className="g2-notice">仅确定的地面三元组可展示；空白节点无法可靠对齐的部分保持未知。</p>}
    <details><summary>源码行级 Diff（{changes.length}行对照）</summary>
      <p className="muted">线性前后文行对照，非最小编辑脚本。BOM与行结束符单独标记；全部原文可在下方查看或导出。</p>
      {source.baseText === null || source.targetText === null ? <p>源存在性：{source.baseText === null ? "基准absent" : "基准存在"} →
        {source.targetText === null ? "目标absent" : "目标存在（空源也保留）"}</p> : null}
      <ol className="g2-node-list" aria-label={`${source.sourceId}源码行对照`}>{changes.slice(0, limit).map((line, index) => <li key={index}>
        <small>{line.kind === "removed" ? "−" : line.kind === "added" ? "+" : "="} 基准 {line.baseLine ?? "—"} / 目标 {line.targetLine ?? "—"}
          {line.text.startsWith("\uFEFF") ? " · BOM" : ""} · {lineEnding(line.text)}</small>
        <pre className="g2-pre">{line.text}</pre>
      </li>)}</ol>
      {changes.length > limit && <button className="button" onClick={() => setLimit(value => value + 200)}>继续显示源码行（剩余{changes.length - limit}行）</button>}
    </details>
    <div className="g2-row">
      <button className="button" disabled={source.baseText === null} onClick={() => download(source.baseText, "base")}>导出{source.sourceId}基准原文</button>
      <button className="button" disabled={source.targetText === null} onClick={() => download(source.targetText, "target")}>导出{source.sourceId}目标原文</button>
    </div>
    <details><summary>基准完整原文</summary><pre className="g2-pre">{source.baseText ?? "absent · 未提供"}</pre></details>
    <details><summary>目标完整原文</summary><pre className="g2-pre">{source.targetText ?? "absent · 未提供"}</pre></details>
    <TripleDelta triples={source.removedTriples} title="确定移除的typed三元组" />
    <TripleDelta triples={source.addedTriples} title="确定新增的typed三元组" />
  </article>;
}

/** 两个固定版本的四源字节/图/typed差异分别展示，不冒称完整OWL推理。 */
export function VersionDiffView({ diff }: { diff: VersionDiff }) {
  return <section className="g2-stack" aria-label="固定版本四源差异结果">
    <h3>固定版本与四源源码 Diff</h3>
    <p>{diff.from.kind} {diff.from.id} / {diff.from.revision ?? "固定Release"} →
      {diff.to.kind} {diff.to.id} / {diff.to.revision ?? "固定Release"}</p>
    <p className="g2-hash">资产 {diff.assetId} · {diff.scope.organizationId} / {diff.scope.siteIds.join(" / ")}</p>
    <p className="g2-hash">基准manifest {diff.baseManifestHash ?? "非Release"} · 目标manifest {diff.targetManifestHash ?? "非Release"}</p>
    <p className="muted">RDF图比较不等于完整OWL推理。未支持公理保留在每源完整原文中。</p>
    {diff.sources.map(source => <SourceDiffCard key={`${source.sourceId}/${source.baseHash}/${source.targetHash}`} source={source} />)}
  </section>;
}
