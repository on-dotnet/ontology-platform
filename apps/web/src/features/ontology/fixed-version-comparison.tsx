"use client";
import { useEffect, useRef, useState } from "react";
import type { OntologyDraft, VersionDiff, VersionRefKind } from "../../lib/api/g2-generated";
import { createG2Client } from "../../lib/api/g2-client";
import { fixedVersion, versionDiffMatches } from "./version-diff-model";
import { VersionDiffView } from "./version-diff-view";

const client = createG2Client();
/** 显式选择同资产两个固定草稿修订或Release，切换和取消后旧回复不能覆盖新选择。 */
export function FixedVersionComparison({ draft, busy, execute }: {
  draft: OntologyDraft; busy: boolean; execute: (action: (signal: AbortSignal) => Promise<void>) => Promise<void>;
}) {
  const [from, setFrom] = useState({ kind: "DRAFT" as VersionRefKind, id: draft.draftId, revision: "1" });
  const [to, setTo] = useState({ kind: "DRAFT" as VersionRefKind, id: draft.draftId, revision: String(draft.revision) });
  const [diff, setDiff] = useState<VersionDiff | null>(null);
  const [status, setStatus] = useState("UNKNOWN · 尚未读取两个固定版本");
  const [comparing, setComparing] = useState(false);
  const current = useRef<AbortController | null>(null);
  useEffect(() => () => { current.current?.abort(); current.current = null; }, []);
  const source = fixedVersion(from.kind, from.id, from.revision), target = fixedVersion(to.kind, to.id, to.revision);
  function reset() {
    current.current?.abort(); current.current = null; setDiff(null); setComparing(false); setStatus("UNKNOWN · 版本选择已变化，请重新读取");
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
  return <section className="g2-stack" aria-label="任意固定版本差异">
    <h3>任意两个固定版本</h3>
    <p className="muted">只能比较同一资产和完整范围。Release修订必须为空；草稿必须明确固定revision，不能使用latest。</p>
    {([{ label: "基准", value: from, update: setFrom }, { label: "目标", value: to, update: setTo }]).map(({ label, value, update }) =>
      <fieldset className="g3-identity-form" disabled={busy || comparing} key={label}><legend>{label}固定版本</legend>
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
      <button className="button" disabled={busy || comparing || !source || !target} onClick={compare}>比较固定版本四源源码</button>
      <button className="button" disabled={!comparing} onClick={() => current.current?.abort()}>取消固定版本比较</button>
    </div>
    <p className="g2-notice" role="status">{status}</p>
    {diff && <VersionDiffView diff={diff} />}
  </section>;
}
