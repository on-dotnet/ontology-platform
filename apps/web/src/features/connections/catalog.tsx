"use client";
import { useEffect, useRef, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { CatalogDiscoveryJobView, CatalogSnapshotListPage, CatalogSnapshotView, ConnectionView } from "../../lib/api/g4-generated";
import { PlatformApiError } from "../../lib/api/client";
import { command } from "../../lib/api/g2-client";
import { createConnectionsClient } from "./api";
import { RequestError, stateLabels } from "./status";
const client = createConnectionsClient();
/** 持久任务由jobId恢复；有界轮询、明确取消，历史每次读取都重新授权。 */
export function CatalogPanel({ connection, etag, canManage, onDenied }: { connection: ConnectionView; etag: string; canManage: boolean; onDenied: (error: unknown) => void }) {
  const router = useRouter(); const pathname = usePathname(); const params = useSearchParams();
  const jobId = params.get("job") ?? "";
  const [job, setJob] = useState<CatalogDiscoveryJobView | null>(null);
  const [history, setHistory] = useState<CatalogSnapshotListPage | null>(null);
  const [snapshot, setSnapshot] = useState<CatalogSnapshotView | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [paused, setPaused] = useState(false);
  const [replay, setReplay] = useState<(() => Promise<void>) | null>(null);
  const disabled = connection.state === "DISABLED";
  const access = useRef({ generation: 0, revoked: false });
  const [revalidating, setRevalidating] = useState(false);
  useEffect(() => {
    access.current = { generation: access.current.generation + 1, revoked: false };
    return () => { access.current = { generation: access.current.generation + 1, revoked: true }; };
  }, [connection.id, jobId, disabled]);
  function current(generation: number, signal?: AbortSignal) { return !signal?.aborted && !access.current.revoked && generation === access.current.generation; }
  function failure(cause: unknown) {
    setError(cause);
    if (cause instanceof PlatformApiError && [401, 403].includes(cause.status)) {
      access.current = { generation: access.current.generation + 1, revoked: true };
      setSnapshot(null); setHistory(null); setJob(null); setReplay(null); setBusy(false); setRevalidating(false); onDenied(cause);
    }
  }
  /** 源目录拒绝不等于任务拒绝；清空旧目录后重新验证连接和任务，绝不沿用旧投影。 */
  async function catalogFailure(cause: unknown, signal?: AbortSignal) {
    if (!(cause instanceof PlatformApiError) || cause.status !== 403 || cause.code !== "catalog_access_forbidden") { failure(cause); return; }
    const generation = ++access.current.generation;
    setError(cause); setSnapshot(null); setHistory(null); setJob(null); setReplay(null); setBusy(false); setRevalidating(true);
    try {
      const latest = await client.get(connection.id, signal);
      if (!current(generation, signal)) return;
      if (latest.data.state === "DISABLED") { failure(cause); return; }
      if (jobId) {
        const authorized = await client.job(connection.id, jobId, signal);
        if (current(generation, signal)) {
          setJob(authorized.data);
          // 撤销旧轮询后，仍在运行的任务提供显式继续入口，避免无声停在等待状态。
          setPaused(["QUEUED", "RUNNING"].includes(authorized.data.status));
        }
      }
    } catch (denied) { if (current(generation, signal)) failure(denied); }
    finally { if (current(generation, signal)) setRevalidating(false); }
  }
  /** 每次读取绑定当前代际，撤权、卸载或较新的拒绝发生后，旧响应不得恢复目录。 */
  async function readCatalogs(cursor = "", signal?: AbortSignal) {
    const generation = access.current.generation;
    try { const result = await client.catalogs(connection.id, cursor, signal); if (current(generation, signal)) { setHistory(result.data); setRevalidating(false); } }
    catch (cause) { if (current(generation, signal)) await catalogFailure(cause, signal); }
  }
  async function readSnapshot(snapshotId: string) {
    const generation = access.current.generation;
    try { const result = await client.catalog(snapshotId); if (current(generation)) setSnapshot(result.data); }
    catch (cause) { if (current(generation)) await catalogFailure(cause); }
  }
  useEffect(() => {
    if (disabled) return;
    const controller = new AbortController();
    void Promise.resolve().then(() => { if (!controller.signal.aborted) return readCatalogs("", controller.signal); });
    return () => controller.abort();
    // 身份拒绝回调由父级提供，不作为查询重启条件。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connection.id, jobId, disabled, refresh]);
  useEffect(() => {
    if (!jobId || disabled) return;
    const controller = new AbortController(); let timer: ReturnType<typeof setTimeout>; let attempts = 0;
    async function poll() {
      const generation = access.current.generation;
      try {
        const result = await client.job(connection.id, jobId, controller.signal);
        if (!current(generation, controller.signal)) return;
        setJob(result.data);
        if (["QUEUED", "RUNNING"].includes(result.data.status)) { if (++attempts < 20) timer = setTimeout(poll, 1500); else setPaused(true); }
        else await readCatalogs("", controller.signal);
      } catch (cause) { if (current(generation, controller.signal)) failure(cause); }
    }
    void poll(); return () => { controller.abort(); clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connection.id, jobId, disabled, refresh]);
  async function run(work: () => Promise<void>) {
    const generation = access.current.generation;
    setBusy(true); setError(null); setReplay(() => work);
    try { await work(); if (current(generation)) setReplay(null); }
    catch (cause) { if (current(generation)) failure(cause); }
    finally { if (current(generation)) setBusy(false); }
  }
  function discover() {
    const generation = access.current.generation;
    const body = { command: command(connection.configRevision, "发现只读源目录") };
    void run(async () => { const result = await client.discover(connection.id, body, etag); if (!current(generation)) return; setJob(result.data); const next = new URLSearchParams(params); next.set("job", result.data.jobId); router.replace(`${pathname}?${next}`); });
  }
  function cancel() {
    if (!job) return;
    const generation = access.current.generation;
    const body = { command: command(connection.configRevision, "取消目录发现") };
    void run(async () => { const result = await client.cancel(connection.id, job.jobId, body, etag); if (!current(generation)) return; setJob(result.data); setRefresh(value => value + 1); });
  }
  const running = !!job && ["QUEUED", "RUNNING"].includes(job.status);
  return <section className="connection-card"><div className="connection-heading"><div><h2>源目录</h2><p>仅包含当前允许的表、视图与字段，不读取业务行。</p></div>{canManage && <button disabled={disabled || busy || revalidating || running || connection.state !== "ACTIVE" || !connection.probeFresh || !etag} onClick={discover}>发现目录</button>}</div>
    <RequestError error={error} retry={() => { setError(null); setPaused(false); setRefresh(value => value + 1); }} />
    {disabled ? <p>连接已禁用，目录访问已停止。历史仍保留，但不能绕过当前访问控制。</p> : <>
      {!history && !error && <p role="status">正在读取目录历史…</p>}
      {job && <div className="connection-alert" role="status"><strong>目录发现：{stateLabels[job.status] ?? job.status}</strong><p>创建于 {job.createdAtUtc} · 关联标识 {job.traceId}</p>{["FAILED", "PARTIAL"].includes(job.status) && <p>发现未完整完成，不能将此结果视为没有对象。此前快照仅供历史参考。</p>}{running && canManage && <button disabled={busy} onClick={cancel}>取消发现</button>}{paused && <button onClick={() => { setPaused(false); setRefresh(value => value + 1); }}>继续读取任务状态</button>}</div>}
      {replay && !busy && <button onClick={() => void run(replay!)}>恢复上次目录操作结果</button>}
      {history && !history.items.length && <p>尚无目录快照。启用连接后可发现可见目录。</p>}
      {history && history.items.length > 0 && <><h3>目录快照历史</h3><ul className="catalog-history">{history.items.map(item => <li key={item.snapshotId}><button disabled={busy || revalidating} onClick={() => { void run(() => readSnapshot(item.snapshotId)); }}>{item.capturedAtUtc} · 修订 {item.configRevision} · {item.objects.length} 个对象</button><span className="tag">{stateLabels[item.status] ?? item.status}</span></li>)}</ul>{history.nextCursor && <button disabled={busy || revalidating} onClick={() => void run(() => readCatalogs(history.nextCursor!))}>下一页历史</button>}</>}
      {snapshot && <CatalogSnapshot snapshot={snapshot} stale={!!error || !["SUCCEEDED"].includes(job?.status ?? "SUCCEEDED")} />}
    </>}
  </section>;
}
/** 保真展示类型、空值及精度，不把历史快照状态提升为当前源状态。 */
export function CatalogSnapshot({ snapshot, stale }: { snapshot: CatalogSnapshotView; stale: boolean }) {
  return <section aria-label="目录快照详情"><h3>只读目录快照 <span className="tag">{stateLabels[snapshot.status] ?? snapshot.status}</span></h3>{(stale || snapshot.status === "STALE") && <p className="connection-alert">此快照可能已过期；不能用于证明当前目录完整或当前源可访问。</p>}<p className="connection-note">捕获时间：{snapshot.capturedAtUtc}<br />指纹：{snapshot.schemaFingerprint}</p>{snapshot.objects.map(object => <details key={`${object.schema}.${object.name}`} open><summary>{object.schema}.{object.name} · {object.kind === "VIEW" ? "视图" : "表"} · {object.fields.length} 个字段</summary><div className="connection-scroll" tabIndex={0} aria-label={`${object.name}字段，可横向滚动`}><table><thead><tr><th>字段</th><th>原生类型</th><th>可为空</th><th>精度</th><th>小数位</th></tr></thead><tbody>{object.fields.map(field => <tr key={`${field.ordinal}:${field.name}`}><td>{field.name}</td><td>{field.nativeType}</td><td>{field.nullable ? "是" : "否"}</td><td>{field.precision ?? "—"}</td><td>{field.scale ?? "—"}</td></tr>)}</tbody></table></div></details>)}</section>;
}
