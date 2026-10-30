"use client";
import { useEffect, useRef, useState } from "react";
import { createG2Client } from "../../lib/api/g2-client";
import type { DraftDiff, OntologyDraft, SourceComparison } from "../../lib/api/g2-generated";
import { comparisonLabel } from "./semantic-status";
import { FixedVersionComparison } from "./fixed-version-comparison";

const client = createG2Client();

/** 固定修订的四源精确图比较；字节变化与RDF图变化分别展示。 */
export function VersionComparison({ draft, busy, execute }: {
  draft: OntologyDraft;
  busy: boolean;
  execute: (action: (signal: AbortSignal) => Promise<void>) => Promise<void>;
}) {
  const [comparing, setComparing] = useState(false);
  const [fromRevision, setFromRevision] = useState(1);
  const [diff, setDiff] = useState<DraftDiff | null>(null);
  const [comparison, setComparison] = useState<SourceComparison[] | null>(null);
  const [status, setStatus] = useState("UNKNOWN · 尚未执行精确比较");
  const cancellation = useRef<AbortController | null>(null);
  const validRevision = Number.isSafeInteger(fromRevision) && fromRevision >= 1 && fromRevision <= draft.revision;

  useEffect(() => () => cancellation.current?.abort(), []);

  /** 取消仅终止本次比较，不终止工作区的后续请求。 */
  function compare() {
    const controller = new AbortController();
    cancellation.current = controller;
    setComparison(null);
    setComparing(true);
    setStatus("正在比较四个原始源…");
    void execute(async lifetime => {
      const signal = AbortSignal.any([lifetime, controller.signal]);
      try {
        const result = await client.compareVersions({
          from: { kind: "DRAFT", id: draft.draftId, revision: fromRevision },
          to: { kind: "DRAFT", id: draft.draftId, revision: draft.revision },
        }, signal);
        if (!signal.aborted) {
          setComparison(result);
          setStatus(result.length === 4 ? "四源比较已返回；逐源查看状态。" : "UNKNOWN · 四源结果不完整，不能认定无差异");
        }
      } catch (cause) {
        if (signal.aborted) setStatus("INDETERMINATE · 比较已取消，不能认定无差异");
        else { setStatus("UNKNOWN · 比较请求失败，不能认定无差异"); throw cause; }
      } finally {
        if (cancellation.current === controller) { cancellation.current = null; setComparing(false); }
      }
    });
  }

  return (
    <section className="g2-stack" aria-label="版本源比较">
      <FixedVersionComparison draft={draft} busy={busy} execute={execute} />
      <h3>固定修订 Diff 与四源比较</h3>
      <label>基准修订
        <input type="number" min={1} max={draft.revision} value={fromRevision} disabled={busy} onChange={event => {
          setFromRevision(Number(event.target.value));
          setComparison(null);
          setDiff(null);
          setStatus("UNKNOWN · 基准已变化，请重新比较");
        }} />
      </label>
      <p className="muted">目标固定为已保存 revision {draft.revision}；未保存文本不参与比较。</p>
      <div className="g2-row">
        <button className="button" disabled={busy || !validRevision} onClick={compare}>精确比较四源</button>
        <button className="button" disabled={!comparing} onClick={() => cancellation.current?.abort()}>取消比较</button>
        <button className="button" disabled={busy || !validRevision} onClick={() => void execute(async signal => {
          setDiff(await client.diff(draft.draftId, fromRevision, signal));
        })}>读取真实 Diff</button>
      </div>
      <p className="g2-notice" role="status">{status}</p>
      {comparison?.map(item => (
        <article className="g2-notice" key={item.sourceId}>
          <h4>{item.sourceId} · {comparisonLabel(item.graph.status)}</h4>
          <p>原始字节：{item.sourceChanged ? "有变化" : "未变化"} · {item.graph.code}</p>
          <p className="g2-hash">左 {item.leftHash ?? "absent · 未提供"}</p>
          <p className="g2-hash">右 {item.rightHash ?? "absent · 未提供"}</p>
          <p>搜索节点 {item.graph.visitedNodes} · {item.graph.elapsedMilliseconds} ms</p>
        </article>
      ))}
      {diff && (
        <>
          <p>revision {diff.baseRevision} → {diff.targetRevision} · +{diff.addedTriples.length} / −{diff.removedTriples.length} triples</p>
          <p className="muted">此计数为原有三元组展示；图等价结论以上方四源精确比较为准。</p>
          <pre className="g2-pre">{diff.sourceDiff}</pre>
          {diff.unsupportedDiagnostics.map((item, index) => <p key={index}>{item.code} · {item.message}</p>)}
        </>
      )}
    </section>
  );
}
