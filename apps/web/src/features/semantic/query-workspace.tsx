"use client";
import { useEffect, useRef, useState } from "react";
import type { EvidenceRef, ReleaseSummary, SemanticCapability, SemanticQueryPlan, SemanticQueryResult } from "../../lib/api/g2-generated";
import { createG2Client } from "../../lib/api/g2-client";
import { SemanticError, Trace } from "../../components/ui/semantic-feedback";
import { RunWorkspace } from "../agent/run-workspace";
import "../ontology/workspace.css";
const client = createG2Client();
const statusTitles = { FOUND: "找到可信结果", EMPTY: "已成功查询，无匹配", PARTIAL: "部分结果：来源或预算不完整", UNAVAILABLE: "无可信结果：依赖不可用", UNAUTHORIZED: "能力或范围拒绝", AMBIGUOUS: "存在多个授权候选，需要消歧" };
/** 六态结果保留实际snapshot、来源与证据；所有文字通过React安全渲染。 */
export function QueryResult({ result }: { result: SemanticQueryResult }) {
  const [evidence, setEvidence] = useState<EvidenceRef | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [pending, setPending] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  /** 证据必须经endpoint再次授权，不把答案内的引用直接当原件。 */
  async function inspect(id: string) {
    controller.current?.abort(); const request = new AbortController(); controller.current = request;
    setPending(true); setError(null); setEvidence(null);
    try { const value = await client.evidence(id, request.signal); if (!request.signal.aborted) setEvidence(value); }
    catch (cause) { if (!request.signal.aborted) setError(cause); }
    finally { if (!request.signal.aborted) setPending(false); }
  }
  return <section className="g2-stack"><strong className="g2-status">{result.status} · {statusTitles[result.status]}</strong><p className="g2-hash">固定 release {result.snapshot.releaseId} · data {result.snapshot.dataHash}</p>{result.limited && <p className="g2-notice">已达到预算，结果不完整。</p>}<Trace traceId={result.traceId} />
    <div className="g2-list">{result.data.map((datum, index) => <article key={index}>{datum.kind === "ontology" ? <><h3>正式本体 Schema</h3><p>Class {datum.ontology.classIris.length} · ObjectProperty {datum.ontology.objectPropertyIris.length} · DatatypeProperty {datum.ontology.datatypePropertyIris.length}</p><pre className="g2-pre">{JSON.stringify(datum.ontology, null, 2)}</pre></> : datum.kind === "entity" ? <><h3>{datum.entity.label}</h3><p className="g2-hash">{datum.entity.iri}</p><p>{datum.entity.organizationId} / {datum.entity.siteId} · {datum.entity.externalId} · {datum.entity.synthetic ? "Synthetic" : "未标记Synthetic"}</p>{datum.entity.properties.map((property, p) => <p key={p} className="g2-hash">{property.predicateIri} = {property.value.value}</p>)}</> : <><h3>实际关系</h3><p className="g2-hash">{datum.relationship.sourceIri} → {datum.relationship.predicateIri} → {datum.relationship.targetIri}</p><p>证据 {datum.relationship.evidenceIds.join(" / ") || "未关联"}</p></>}</article>)}</div>
    {result.candidates.length > 0 && <section><h3>实际授权候选</h3>{result.candidates.map(candidate => <p className="g2-hash" key={candidate.entityIri}>{candidate.label} · {candidate.siteId} · {candidate.entityIri}</p>)}<p className="muted">使用明确实体IRI再次查询；不会按同外部号自动合并。</p></section>}
    {result.diagnostics.map((item, index) => <p className="g2-notice" key={index}>{item.code} · {item.message}</p>)}
    <details><summary>逐来源状态与业务有效时间</summary><pre className="g2-pre">{JSON.stringify({ subSources: result.subSources, validTime: result.validTime, observedAtUtc: result.observedAtUtc }, null, 2)}</pre></details>
    <h3>引用证据 · 再次授权读取</h3>{result.evidence.length === 0 ? <p className="muted">此次结果未返回证据引用。</p> : result.evidence.map(ref => <button key={ref.evidenceId} className="g2-asset" disabled={pending} onClick={() => void inspect(ref.evidenceId)}><strong>{ref.sourceId} / {ref.sourceRecordId}</strong><small>{ref.evidenceId}</small></button>)}{pending && <p role="status">正在核验证据…</p>}{error !== null && <SemanticError error={error} />}{evidence && <article className="g2-notice"><strong>已由服务端重新读取证据 · Synthetic {String(evidence.synthetic)}</strong><pre className="g2-pre">{JSON.stringify(evidence, null, 2)}</pre></article>}
  </section>;
}
/** 从真实能力目录和正式版本创建受控查询，不开放SQL/SPARQL/任意URL。 */
export function QueryWorkspace() {
  const [capabilities, setCapabilities] = useState<SemanticCapability[]>([]);
  const [releases, setReleases] = useState<ReleaseSummary[]>([]);
  const [capabilityId, setCapabilityId] = useState("");
  const [releaseId, setReleaseId] = useState("");
  const [externalId, setExternalId] = useState("");
  const [entityIri, setEntityIri] = useState("");
  const [siteId, setSiteId] = useState("");
  const [relationships, setRelationships] = useState("");
  const [depth, setDepth] = useState(2);
  const [maxRows, setMaxRows] = useState(50);
  const [timeoutMs, setTimeoutMs] = useState(3000);
  const [result, setResult] = useState<SemanticQueryResult | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const lifetime = useRef<AbortController | null>(null);
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    const controller = new AbortController(); lifetime.current = controller;
    Promise.all([client.capabilities(controller.signal), client.releases(controller.signal)]).then(([items, versions]) => { if (!controller.signal.aborted) { setCapabilities(items); setReleases(versions); setCapabilityId(items[0]?.id ?? ""); setReleaseId(versions.find(item => item.isActive)?.manifest.releaseId ?? versions[0]?.manifest.releaseId ?? ""); } }).catch(cause => { if (!controller.signal.aborted) setError(cause); }).finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => { controller.abort(); request.current?.abort(); };
  }, []);
  const capability = capabilities.find(item => item.id === capabilityId);
  const release = releases.find(item => item.manifest.releaseId === releaseId);
  const plan: SemanticQueryPlan | null = capability && release ? { capabilityId, capabilityVersion: capability.version, assetId: release.manifest.assetId, releaseId: release.isActive ? null : releaseId, entityType: null, entityIri: entityIri.trim() || null, externalId: externalId.trim() || null, siteId: siteId || null, relationshipIris: relationships.split(/\s+/).filter(Boolean), depth, maxRows, timeoutMs } : null;
  const validBudget = Number.isInteger(depth) && depth >= 1 && depth <= Math.min(5, capability?.budgets.maxDepth ?? 5) && Number.isInteger(maxRows) && maxRows >= 1 && maxRows <= Math.min(100, capability?.budgets.maxRows ?? 100) && Number.isInteger(timeoutMs) && timeoutMs >= 100 && timeoutMs <= Math.min(5000, capability?.budgets.timeoutMs ?? 5000);
  /** 显式取消只中止当前查询；取消不会伪造EMPTY结果。 */
  async function query(discover = false) {
    if (!plan || !validBudget) return;
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setBusy(true); setResult(null); setError(null);
    try { const value = discover ? await client.discover(plan.assetId, plan.releaseId, controller.signal) : await client.query(plan, controller.signal); if (!controller.signal.aborted) setResult(value); }
    catch (cause) { if (!controller.signal.aborted) setError(cause); }
    finally { if (!controller.signal.aborted) setBusy(false); }
  }
  return <div className="g2-workspace"><div className="g2-heading"><div><p className="eyebrow">SEMANTIC INTELLIGENCE</p><h1>统一语义查询与执行</h1><p>正式快照 · 受控能力 · 六态结果 · 可回读证据</p></div><span className="tag teal">Synthetic 数据</span></div>{error !== null && <SemanticError error={error} />}
    {loading ? <p role="status">正在读取正式版本与能力目录…</p> : <div className="g2-split"><section className="g2-panel g2-stack"><h2>受控查询计划</h2><label>正式版本<select aria-label="查询正式版本" value={releaseId} onChange={event => { setReleaseId(event.target.value); setResult(null); }} disabled={busy}><option value="">请选择正式版本</option>{releases.map(item => <option key={item.manifest.releaseId} value={item.manifest.releaseId}>{item.manifest.releaseId} {item.isActive ? "· Active（每次由服务端固定快照）" : "· 历史固定版本"}</option>)}</select></label><label>已登记能力<select aria-label="受控语义能力" value={capabilityId} onChange={event => { setCapabilityId(event.target.value); setResult(null); }} disabled={busy}>{capabilities.map(item => <option key={item.id} value={item.id}>{item.id} · {item.version}</option>)}</select></label>{capability && <p className="muted">{capability.meaning}</p>}<label>外部编号<input aria-label="实体外部编号" value={externalId} onChange={event => setExternalId(event.target.value)} disabled={busy} /></label><label>精确实体 IRI<input aria-label="精确实体IRI" value={entityIri} onChange={event => setEntityIri(event.target.value)} disabled={busy} /></label><label>厂区<select value={siteId} onChange={event => setSiteId(event.target.value)} disabled={busy}><option value="">正式版本完整范围</option>{release?.manifest.scope.siteIds.map(site => <option key={site}>{site}</option>)}</select></label><label>关系 IRI（空白分隔，必须在正式Schema内）<textarea aria-label="关系IRI路径" value={relationships} onChange={event => setRelationships(event.target.value)} disabled={busy} /></label><div className="g2-row"><label>深度 1–5<input type="number" min={1} max={5} value={depth} onChange={event => setDepth(Number(event.target.value))} disabled={busy} /></label><label>行数 1–100<input type="number" min={1} max={100} value={maxRows} onChange={event => setMaxRows(Number(event.target.value))} disabled={busy} /></label><label>超时 100–5000ms<input type="number" min={100} max={5000} value={timeoutMs} onChange={event => setTimeoutMs(Number(event.target.value))} disabled={busy} /></label></div><div className="g2-row"><button className="button primary" disabled={busy || !plan || !validBudget} onClick={() => void query()}>执行真实查询</button><button className="button" disabled={busy || !plan || !validBudget} onClick={() => void query(true)}>发现正式 Schema</button>{busy && <button className="button" onClick={() => { request.current?.abort(); setBusy(false); }}>取消当前查询</button>}</div>{releases.length === 0 && <p className="g2-notice">暂无正式发布版本，查询与Run等待真实发布完成。</p>}{capabilities.length === 0 && <p className="g2-notice">服务未返回已登记能力，无法执行。</p>}</section><section className="g2-panel g2-stack"><h2>查询结果与证据</h2>{busy ? <p role="status">正在等待真实语义网关…</p> : result ? <QueryResult key={result.traceId} result={result} /> : <p className="muted">执行后显示真实状态、固定snapshot与来源；无结果时不生成答案。</p>}</section></div>}
    <RunWorkspace plan={validBudget ? plan : null} />
  </div>;
}
