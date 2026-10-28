"use client";
import { useEffect, useRef, useState } from "react";
import { createG2Client } from "../../lib/api/g2-client";
import type { VocabularySnapshot } from "../../lib/api/g2-generated";
import { SemanticError } from "../../components/ui/semantic-feedback";
import { VocabularyReadView } from "./vocabulary-workbench";

const client = createG2Client();
/** 按用户明确选择的固定Release读取已验证词汇；历史profile由manifest决定。 */
export function ReleasedVocabulary() {
  const [releaseId, setReleaseId] = useState("");
  const [snapshot, setSnapshot] = useState<VocabularySnapshot | null>(null);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const current = useRef<AbortController | null>(null);
  useEffect(() => () => current.current?.abort(), []);
  async function read() {
    current.current?.abort();
    const controller = new AbortController();
    current.current = controller;
    const target = releaseId.trim();
    setBusy(true); setSnapshot(null); setError(null); setSelected("");
    try {
      const result = await client.releasedVocabulary(target, controller.signal);
      if (controller.signal.aborted) return;
      if (result.releaseId !== target || !result.manifestHash) throw new Error("正式词汇回包未绑定所选Release及manifest，拒绝用草稿替代。");
      setSnapshot(result);
    } catch (cause) { if (!controller.signal.aborted) setError(cause); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <section className="g2-stack" aria-label="固定Release词汇读取">
    <h3>历史正式词汇与来源</h3>
    <p className="muted">在发布与审批工作区复制固定 Release ID。服务端校验不可变对象与真实 Jena 同批图，再按历史 manifest profile 读回。</p>
    <label>固定 Release ID<input aria-label="固定词汇Release ID" value={releaseId} onChange={event => { current.current?.abort(); setReleaseId(event.target.value); setSnapshot(null); setError(null); setBusy(false); }} /></label>
    <button className="button" disabled={busy || !releaseId.trim()} onClick={() => void read()}>读取固定Release词汇</button>
    {busy && <p role="status">正在核验固定正式图与来源…</p>}
    {error !== null && <SemanticError error={error} />}
    {snapshot && <VocabularyReadView snapshot={snapshot} selected={selected} onSelect={setSelected} />}
  </section>;
}
