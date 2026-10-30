"use client";
import { useEffect, useRef, useState } from "react";
import { createG2Client } from "../../lib/api/g2-client";
import type { VocabularySnapshot } from "../../lib/api/g2-generated";
import { SemanticError } from "../../components/ui/semantic-feedback";
import { IdentityTimeReadView } from "./identity-time-workbench";

const client = createG2Client();
/** 固定正式Release的身份时间必须来自已核验manifest，不以当前草稿替代。 */
export function ReleasedIdentityTime() {
  const [releaseId, setReleaseId] = useState("");
  const [snapshot, setSnapshot] = useState<VocabularySnapshot | null>(null);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const current = useRef<AbortController | null>(null);
  useEffect(() => () => current.current?.abort(), []);
  async function read() {
    current.current?.abort();
    const controller = new AbortController(), target = releaseId.trim();
    current.current = controller;
    setBusy(true); setSnapshot(null); setError(null); setSelected("");
    try {
      const result = await client.releasedIdentityTime(target, controller.signal);
      if (controller.signal.aborted) return;
      if (result.releaseId !== target || !result.manifestHash) throw new Error("正式身份时间回包未绑定固定Release与manifest，已拒绝。");
      setSnapshot(result);
    } catch (cause) { if (!controller.signal.aborted) setError(cause); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <details className="g2-stack"><summary>读取固定正式Release身份与时间</summary>
    <p className="muted">服务器核验不可变源对象及真实Jena图，历史profile与当时身份事实保持不变。</p>
    <label>固定身份时间 Release ID<input aria-label="固定身份时间Release ID" value={releaseId} onChange={value => {
      current.current?.abort(); setReleaseId(value.target.value); setSnapshot(null); setError(null); setBusy(false);
    }} /></label>
    <button className="button" disabled={busy || !releaseId.trim()} onClick={() => void read()}>读取固定Release身份时间</button>
    {busy && <p role="status">正在核验正式身份时间与来源…</p>}
    {error !== null && <SemanticError error={error} />}
    {snapshot && <IdentityTimeReadView snapshot={snapshot} selected={selected} onSelect={setSelected} />}
  </details>;
}
