"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import type { ConnectionListPage } from "../../lib/api/g4-generated";
import { createConnectionsClient } from "./api";
import { connectionTypes, typeLabels } from "./form-model";
import { RequestError, stateLabels } from "./status";
const client = createConnectionsClient();
/** URL仅保存类型、生命周期和分页游标；每次查询都读取当前授权结果。 */
export function ConnectionList({ canManage }: { canManage: boolean }) {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const query = new URLSearchParams();
  for (const key of ["type", "state", "cursor"]) if (params.get(key)) query.set(key, params.get(key)!);
  const encoded = query.toString();
  const [result, setResult] = useState<{ query: string; data: ConnectionListPage } | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => { const controller = new AbortController(); client.list(encoded, controller.signal).then(response => { if (!controller.signal.aborted) { setResult({ query: encoded, data: response.data }); setError(null); } }).catch(cause => { if (!controller.signal.aborted) { setResult(null); setError(cause); } }); return () => controller.abort(); }, [encoded, refresh]);
  function filter(key: string, value: string) { const next = new URLSearchParams(encoded); if (value) next.set(key, value); else next.delete(key); if (key !== "cursor") next.delete("cursor"); setResult(null); setError(null); router.push(`${pathname}?${next}`); }
  return <div className="connections-workspace"><div className="connection-heading"><div><h1>数据源</h1><p>管理只读连接与可见目录，所有状态来自当前授权范围。</p></div>{canManage && <Link className="button primary" href="/data/connections/new">新建连接</Link>}</div>
    <div className="connection-actions"><label>类型<select value={params.get("type") ?? ""} onChange={event => filter("type", event.target.value)}><option value="">全部类型</option>{connectionTypes.map(type => <option key={type} value={type}>{typeLabels[type]}</option>)}</select></label><label>状态<select value={params.get("state") ?? ""} onChange={event => filter("state", event.target.value)}><option value="">全部状态</option>{["DRAFT", "ACTIVE", "DISABLED"].map(state => <option key={state} value={state}>{stateLabels[state]}</option>)}</select></label><button onClick={() => { setResult(null); setError(null); setRefresh(value => value + 1); }}>刷新列表</button></div>
    <RequestError error={error} retry={() => { setError(null); setRefresh(value => value + 1); }} />
    {!error && (!result || result.query !== encoded) && <p role="status">正在读取连接…</p>}
    {result?.query === encoded && <section className="connection-card">{!result.data.items.length ? <p role="status">当前筛选下暂无连接。{canManage && "可新建连接或调整筛选。"}</p> : <div className="connection-scroll" tabIndex={0} aria-label="连接列表，可横向滚动"><table><thead><tr><th>连接名称</th><th>类型</th><th>状态</th><th>最近测试</th><th>更新时间</th></tr></thead><tbody>{result.data.items.map(item => <tr key={item.id}><td><Link href={`/data/connections/${encodeURIComponent(item.id)}`}>{item.displayName}</Link></td><td>{typeLabels[item.config.type]}</td><td><span className={`tag ${item.state === "ACTIVE" ? "teal" : "amber"}`}>{stateLabels[item.state] ?? item.state}</span></td><td>{item.probeFresh ? "当前测试有效" : item.lastProbeId ? "需重新测试" : "尚未测试"}</td><td>{item.updatedAtUtc}</td></tr>)}</tbody></table></div>}{result.data.nextCursor && <button onClick={() => filter("cursor", result.data.nextCursor!)}>下一页</button>}</section>}
  </div>;
}
