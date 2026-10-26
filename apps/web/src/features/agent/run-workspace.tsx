"use client";
import { useEffect, useRef, useState } from "react";
import type { ExecutionEvent, ExecutionRun, SemanticQueryPlan } from "../../lib/api/g2-generated";
import { command, createG2Client } from "../../lib/api/g2-client";
import { SemanticError } from "../../components/ui/semantic-feedback";
import { readExecutionEvents } from "./event-stream";
const client = createG2Client();
const terminal = (run: ExecutionRun) => ["COMPLETED", "FAILED", "CANCELLED"].includes(run.status);
/** 持久Run与订阅分别管理；断开SSE不等于取消业务运行。 */
export function RunWorkspace({ plan }: { plan: SemanticQueryPlan | null }) {
  const [runs, setRuns] = useState<ExecutionRun[]>([]);
  const [run, setRun] = useState<ExecutionRun | null>(null);
  const [events, setEvents] = useState<ExecutionEvent[]>([]);
  const [prompt, setPrompt] = useState("");
  const [harness, setHarness] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [connected, setConnected] = useState(false);
  const [subscribe, setSubscribe] = useState(true);
  const [reconnect, setReconnect] = useState(0);
  const [notice, setNotice] = useState("");
  const lifetime = useRef<AbortController | null>(null);
  const seq = useRef(0);
  const runId = run?.runId;
  useEffect(() => {
    const controller = new AbortController(); lifetime.current = controller;
    client.runs(controller.signal).then(items => { if (!controller.signal.aborted) setRuns(items); }).catch(cause => { if (!controller.signal.aborted) setError(cause); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!runId || !subscribe) return;
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout> | undefined;
    /** 每次续订从最后已接受seq读取，终态仍先重放历史再停止。 */
    async function listen() {
      try {
        const body = await client.events(runId!, seq.current > 0 ? `${runId}:${seq.current}` : null, controller.signal);
        if (!controller.signal.aborted) setConnected(true);
        for await (const event of readExecutionEvents(body, runId!, seq.current, controller.signal)) {
          seq.current = event.seq;
          setEvents(items => items.some(item => item.eventId === event.eventId) ? items : [...items, event]);
        }
        const snapshot = await client.run(runId!, controller.signal);
        if (controller.signal.aborted) return;
        setRun(snapshot); setConnected(false);
        if (!terminal(snapshot)) timer = setTimeout(() => void listen(), 1000);
      } catch (cause) {
        if (!controller.signal.aborted) {
          setConnected(false); setError(cause);
          client.run(runId!, controller.signal).then(snapshot => { if (!controller.signal.aborted) setRun(snapshot); }).catch(() => {});
        }
      }
    }
    void listen();
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [runId, subscribe, reconnect]);
  /** 读取持久快照后才选中Run，重新选择从seq0重放已有真实事件。 */
  function select(value: ExecutionRun) { seq.current = 0; setEvents([]); setRun(value); setSubscribe(true); setReconnect(value => value + 1); setError(null); }
  async function execute(action: (signal: AbortSignal) => Promise<void>) {
    setBusy(true); setError(null); setNotice("");
    const signal = lifetime.current?.signal ?? new AbortController().signal;
    try { await action(signal); const items = await client.runs(signal); if (!signal.aborted) setRuns(items); }
    catch (cause) { if (!signal.aborted) setError(cause); }
    finally { if (!signal.aborted) setBusy(false); }
  }
  return <section className="g2-panel g2-stack"><div className="g2-row"><h2>智能体执行工作区</h2><span className="tag amber">真实模型未配置 · 不调用付费模型</span></div><p className="g2-notice">确定性 harness 会实际驱动受控工具与持久事件，结果不是 LLM 推理。模型模式当前不可用。</p>{error !== null && <SemanticError error={error} />}{notice && <p role="status">{notice}</p>}<div className="g2-split"><div className="g2-stack"><label>运行说明<textarea aria-label="运行说明" value={prompt} maxLength={8000} onChange={event => setPrompt(event.target.value)} disabled={busy} /></label><label className="g2-row"><span>明确使用 deterministic harness</span><input type="checkbox" checked={harness} onChange={event => setHarness(event.target.checked)} disabled={busy} /></label><button className="button primary" disabled={busy || !harness || !plan || !prompt.trim()} onClick={() => void execute(async signal => { if (!plan) return; const created = await client.createRun({ prompt, plan, providerMode: "deterministic", command: command(0, "用户显式启动确定性受控工具运行") }, signal); select(created); setNotice(`已创建真实Run ${created.runId}`); })}>启动确定性工具运行</button><button className="button" disabled={busy} onClick={() => void execute(async () => {})}>刷新持久运行</button><div className="g2-assets">{runs.length === 0 ? <p className="muted">当前没有可见的持久Run。</p> : runs.map(item => <button key={item.runId} className="g2-asset" aria-current={runId === item.runId} disabled={busy} onClick={() => void execute(async signal => select(await client.run(item.runId, signal)))}><strong>{item.status} · {item.providerMode}</strong><small>{item.runId} · seq {item.lastSeq}</small></button>)}</div></div><div className="g2-stack">{run ? <><div className="g2-row"><h3>{run.status}</h3><span className="tag blue">{connected ? "SSE 已连接" : "SSE 未连接"}</span></div><p className="g2-hash">Run {run.runId} · 固定 release {run.snapshot.releaseId} · {run.scope.siteIds.join(" / ")}</p><div className="g2-row"><button className="button" onClick={() => { setSubscribe(false); setConnected(false); }}>仅断开订阅</button><button className="button" onClick={() => { setError(null); setSubscribe(true); setReconnect(value => value + 1); }}>按 Last-Event-ID 续订</button><button className="button" disabled={busy || terminal(run) || run.cancelRequested} onClick={() => void execute(async signal => { const result = await client.cancelRun(run.runId, { command: command(run.lastSeq, "用户明确请求持久取消运行") }, signal); setRun(result); setNotice("取消请求已持久化，等待唯一终态事件。"); })}>持久取消 Run</button></div><ol className="g2-list" aria-label="真实持久运行事件" aria-live="polite">{events.map(event => <li key={event.eventId}><strong>{event.seq} · {event.eventType}</strong>{event.eventType === "message.delta" ? <p>{event.payload.text}</p> : event.eventType === "tool.completed" ? <p>{event.payload.result.status} · {event.payload.durationMs}ms · release {event.payload.result.snapshot.releaseId}</p> : event.eventType === "evidence.added" ? <p className="g2-hash">证据 {event.payload.evidence.evidenceId}</p> : event.eventType === "approval.required" ? <p>真实待审提案 {event.payload.proposalId}，请至发布治理独立审核。</p> : <pre className="g2-pre">{JSON.stringify(event.payload, null, 2)}</pre>}</li>)}</ol><p className="muted">消息按文本渲染。未知协议停止答案接收并回读快照。卸载仅断开订阅；取消需要独立持久命令。</p></> : <p className="muted">选择或创建Run后，重放真实持久事件和固定快照。</p>}</div></div></section>;
}
