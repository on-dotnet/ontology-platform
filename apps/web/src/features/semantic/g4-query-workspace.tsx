"use client";
import { useEffect, useRef, useState } from "react";
import type { SemanticCapability } from "../../lib/api/g2-generated";
import type { G4QueryDatum, G4QueryResultV1, G4SemanticQuery, G4SourceEvidenceView } from "../../lib/api/g4-generated";
import { createG2Client } from "../../lib/api/g2-client";
import { createPlatformClient, PlatformApiError } from "../../lib/api/client";
import { SemanticError, Trace } from "../../components/ui/semantic-feedback";
import { createG4QueryClient, type QueryDelivery } from "./g4-query-api";
import { displayQueryValue, displayQueryCandidate, bindQuerySessionBoundary, queryStatusLabels } from "./g4-query-model";

const client = createG4QueryClient();

/** 源数据的四种判别形状分别展示，业务值和微秒词法始终按字符串保真。 */
function Datum({ datum }: { datum: G4QueryDatum }) {
  switch (datum.kind) {
    case "entity": return <article><h4>{datum.label ?? datum.identity.externalId}</h4><p>{datum.identity.organizationId} / {datum.identity.siteId}</p><p className="g2-hash">{datum.entityIri}</p>{datum.properties.map((property, index) => <p key={index}>{property.propertyIri}：<strong>{displayQueryValue(property.value)}</strong>{property.unit && <> · {property.unit.unitIri}</>}{property.eventTime && <> · {property.eventTime.lexical} ({property.eventTime.kind})</>}</p>)}<p>有效时间：{datum.validTime ? `${datum.validTime.from.lexical} 至 ${datum.validTime.to?.lexical ?? "结束时间未知"}` : "未知"}</p></article>;
    case "observation": return <article><h4>{datum.identity.externalId} · {datum.propertyIri}</h4><strong>{displayQueryValue(datum.value)}</strong><p>单位：{datum.unit?.unitIri ?? "未提供"}</p><p>事件时间：{datum.eventTime?.lexical ?? "未知"}；观察时间：{datum.observedAtUtc}</p></article>;
    case "relationship": return <article><h4>已发布关系</h4><p>{datum.source.identity.externalId} → {datum.relationshipIri} → {datum.target.identity.externalId}</p><p>基数：{datum.cardinality}</p></article>;
    case "ontology": return <article><h4>正式本体</h4><p>{datum.ontologyReleaseId}</p></article>;
  }
}

/** G4源查询与旧G2入口并列，查询引用可刷新，结果从不进入浏览器持久缓存。 */
export function G4QueryWorkspace() {
  const [capabilities, setCapabilities] = useState<SemanticCapability[]>([]);
  const [capabilityId, setCapabilityId] = useState("");
  const [assetId, setAssetId] = useState("");
  const [ontologyReleaseId, setOntologyReleaseId] = useState("");
  const [mappingReleaseId, setMappingReleaseId] = useState("");
  const [externalId, setExternalId] = useState("");
  const [siteId, setSiteId] = useState("");
  const [sites, setSites] = useState<string[]>([]);
  const [maxRows, setMaxRows] = useState(50);
  const [depth, setDepth] = useState(1);
  const [relationships, setRelationships] = useState("");
  const [validFrom, setValidFrom] = useState("");
  const [validTo, setValidTo] = useState("");
  const [queryId, setQueryId] = useState("");
  const [delivery, setDelivery] = useState<QueryDelivery | null>(null);
  const [lastPlan, setLastPlan] = useState<G4SemanticQuery | null>(null);
  const [evidence, setEvidence] = useState<G4SourceEvidenceView | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(true);
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    const invalidate = () => {
      request.current?.abort(); request.current = null;
      setDelivery(null); setEvidence(null); setLastPlan(null); setError(null); setCapabilities([]); setSites([]); setBusy(false);
      setNotice("页面已离开或身份已失效。请核验当前身份后明确恢复查询。");
    };
    const verify = (restore = false) => {
      request.current?.abort(); const controller = new AbortController(); request.current = controller;
      setBusy(true);
      Promise.all([createG2Client().capabilities(controller.signal), createPlatformClient().me(controller.signal)]).then(async ([available, me]) => {
      if (controller.signal.aborted || request.current !== controller) return;
      const current = available.filter(item => item.id.startsWith("g4_"));
      setCapabilities(current); setCapabilityId(current[0]?.id ?? ""); setSites([...new Set(me.scopes.map(scope => scope.siteId))]);
      const saved = new URL(window.location.href).searchParams.get("query");
      if (restore && saved) {
        setQueryId(saved);
        const restored = await client.result(saved, controller.signal);
        if (!controller.signal.aborted && request.current === controller) setDelivery(restored);
      }
    }).catch(cause => { if (!controller.signal.aborted && request.current === controller) setError(cause); })
      .finally(() => { if (!controller.signal.aborted && request.current === controller) setBusy(false); });
    };
    const channel = typeof BroadcastChannel === "undefined" ? null : new BroadcastChannel("g4-query-session-invalidation");
    const sessionChanged = () => { invalidate(); verify(); };
    if (channel) channel.onmessage = sessionChanged;
    // 现有平台页脚的安全退出按钮在异步取CSRF前先废弃本页及其他查询页的结果。
    const logout = (event: Event) => {
      const button = event.target instanceof Element ? event.target.closest("footer button") : null;
      if (!button?.textContent?.includes("安全退出")) return;
      invalidate(); channel?.postMessage("invalidate");
    };
    document.addEventListener("click", logout, true);
    const unbind = bindQuerySessionBoundary(window, document, invalidate, () => verify());
    verify(true);
    return () => { request.current?.abort(); unbind(); channel?.close(); document.removeEventListener("click", logout, true); };
  }, []);
  /** 每次操作先移除旧数据，晚到响应只允许写入当前仍有效的请求。 */
  async function operate(operation: (signal: AbortSignal) => Promise<QueryDelivery>) {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setBusy(true); setDelivery(null); setEvidence(null); setError(null); setNotice("");
    try {
      const value = await operation(controller.signal);
      if (controller.signal.aborted || request.current !== controller) return;
      setDelivery(value); setQueryId(value.queryId);
      const url = new URL(window.location.href); url.searchParams.set("query", value.queryId);
      window.history.replaceState(null, "", url);
    } catch (cause) {
      if (!controller.signal.aborted && request.current === controller) {
        setError(cause);
        if (cause instanceof PlatformApiError && cause.status === 410) setNotice("结果已到期。需要数据时，请明确发起新查询。");
      }
    } finally { if (!controller.signal.aborted && request.current === controller) setBusy(false); }
  }
  /** 每个新请求使用新幂等键；候选选择保留原完整计划，只改变允许的site和IRI。 */
  async function execute(plan: G4SemanticQuery, selection?: string) {
    setLastPlan(plan);
    await operate(signal => client.execute(plan, crypto.randomUUID(), selection, signal));
  }
  /** 打开证据重新取得当前许可，拒绝后不继续展示之前取得的业务结果。 */
  async function inspect(id: string) {
    request.current?.abort(); const controller = new AbortController(); request.current = controller;
    setEvidence(null); setError(null); setBusy(true);
    try { const value = await client.evidence(id, controller.signal); if (!controller.signal.aborted && request.current === controller) setEvidence(value); }
    catch (cause) { if (!controller.signal.aborted && request.current === controller) { setDelivery(null); setError(cause); } }
    finally { if (!controller.signal.aborted && request.current === controller) setBusy(false); }
  }
  const capability = capabilities.find(item => item.id === capabilityId);
  const result: G4QueryResultV1 | null = delivery?.response.kind === "result" ? delivery.response.result : null;
  const valid = capability && assetId.trim() && ontologyReleaseId.trim() && mappingReleaseId.trim() && Number.isInteger(maxRows) && maxRows >= 2 && maxRows <= 100 && Number.isInteger(depth) && depth >= 1 && depth <= 5 && Boolean(validFrom) === Boolean(validTo);
  return <section className="g2-panel g2-stack" aria-label="业务源查询"><h2>业务源查询</h2><p>选择已发布映射，读取当前授权的业务数据。返回项保留源精度及可回读证据。</p>
    <div className="g2-row"><label>本体资产<input aria-label="源查询本体资产" value={assetId} disabled={busy} onChange={event => setAssetId(event.target.value)} /></label><label>本体发布<input aria-label="源查询本体发布" value={ontologyReleaseId} disabled={busy} onChange={event => setOntologyReleaseId(event.target.value)} /></label><label>映射发布<input aria-label="源查询映射发布" value={mappingReleaseId} disabled={busy} onChange={event => setMappingReleaseId(event.target.value)} /></label></div>
    <div className="g2-row"><label>查询能力<select aria-label="业务源查询能力" value={capabilityId} disabled={busy} onChange={event => setCapabilityId(event.target.value)}>{capabilities.map(item => <option key={item.id} value={item.id}>{item.meaning}</option>)}</select></label><label>业务外部号<input aria-label="源查询外部号" value={externalId} disabled={busy} onChange={event => setExternalId(event.target.value)} /></label><label>厂区<select aria-label="源查询厂区" value={siteId} disabled={busy} onChange={event => setSiteId(event.target.value)}><option value="">当前授权范围</option>{sites.map(site => <option key={site}>{site}</option>)}</select></label><label>最多返回项<input aria-label="源查询最多返回项" type="number" min={2} max={100} value={maxRows} disabled={busy} onChange={event => setMaxRows(Number(event.target.value))} /></label></div>
    <div className="g2-row"><label>关系路径（每行一个已发布 IRI，可留空）<textarea aria-label="源查询关系路径" value={relationships} disabled={busy} onChange={event => setRelationships(event.target.value)} /></label><label>遍历深度<input aria-label="源查询深度" type="number" min={1} max={5} value={depth} disabled={busy} onChange={event => setDepth(Number(event.target.value))} /></label><label>有效时间起点（UTC）<input aria-label="源查询有效时间起点" placeholder="2026-11-14T00:00:00.000000Z" value={validFrom} disabled={busy} onChange={event => setValidFrom(event.target.value)} /></label><label>有效时间终点（UTC，不包含）<input aria-label="源查询有效时间终点" value={validTo} disabled={busy} onChange={event => setValidTo(event.target.value)} /></label></div>
    <div className="g2-row"><button className="button primary" disabled={busy || !valid} onClick={() => {
      if (!capability) return;
      void execute({ assetId: assetId.trim(), ontologyReleaseId: ontologyReleaseId.trim(), mappingReleaseIds: [mappingReleaseId.trim()],
        capabilityId: capability.id, capabilityVersion: capability.version, relationshipIris: relationships.split("\n").map(value => value.trim()).filter(Boolean), depth, maxRows, timeoutMs: 5000,
        filters: { ...(siteId ? { siteId } : {}), ...(externalId ? { entityExternalId: externalId } : {}), ...(validFrom && validTo ? { validFrom, validTo } : {}) } });
    }}>查询业务源</button>{busy && <button className="button" onClick={() => { request.current?.abort(); setBusy(false); setDelivery(null); setEvidence(null); setNotice("已停止等待；尚未确认服务器执行状态。"); }}>停止等待</button>}</div>
    {!busy && capabilities.length === 0 && <p className="g2-notice">当前环境没有开放业务源查询能力。</p>}
    <div className="g2-row"><label>本人查询引用<input aria-label="恢复源查询引用" value={queryId} onChange={event => { setQueryId(event.target.value); setDelivery(null); setEvidence(null); setLastPlan(null); }} disabled={busy} /></label><button className="button" disabled={busy || !queryId} onClick={() => { setLastPlan(null); void operate(signal => client.result(queryId, signal)); }}>恢复查询结果</button><button className="button" disabled={busy || !queryId} onClick={() => void operate(signal => client.cancel(queryId, signal))}>请求取消执行</button></div>
    {busy && <p role="status">正在核验当前权限并读取…</p>}{notice && <p role="status">{notice}</p>}{error !== null && <SemanticError error={error} />}
    {delivery?.response.kind === "execution" && <p role="status">执行状态：{delivery.response.view.executionStatus}；到期时间：{delivery.response.view.expiresAtUtc}</p>}
    {result && <section aria-label="业务源查询结果" className="g2-stack"><h3>{result.status} · {queryStatusLabels[result.status]}</h3><Trace traceId={result.traceId} /><p>观察时间：{result.observedAtUtc}</p>{result.limited && <p className="g2-notice">已达到预算，仅显示已证实部分。</p>}
      <div className="g2-list">{result.data.map((datum, index) => <Datum key={index} datum={datum} />)}</div>
      {result.candidates.map(candidate => <button className="g2-asset" key={candidate.entityIri} disabled={busy || !lastPlan} onClick={() => {
        if (lastPlan) void execute({ ...lastPlan, filters: { ...lastPlan.filters, entityIri: candidate.entityIri, siteId: candidate.siteId } }, delivery!.queryId);
      }} style={{ overflowWrap: "anywhere" }}>{displayQueryCandidate(candidate)}</button>)}
      {result.candidates.length > 0 && !lastPlan && <p className="muted">已恢复原候选。选择新候选前，请重新提交完整查询条件。</p>}
      {result.diagnostics.map((item, index) => <p className="g2-notice" key={index}>{item.message}</p>)}
      <details><summary>固定版本与分支状态</summary><pre className="g2-pre">{JSON.stringify({ snapshot: result.snapshot, subSources: result.subSources }, null, 2)}</pre></details>
      <h4>来源证据</h4>{result.evidence.map(item => <button className="g2-asset" key={item.evidenceId} disabled={busy} onClick={() => void inspect(item.evidenceId)}>{item.precision} · {item.sourceDatasetRef}</button>)}
    </section>}
    {evidence && <section aria-label="业务源证据"><h3>已重新授权的来源证据</h3><pre className="g2-pre">{JSON.stringify(evidence, null, 2)}</pre></section>}
  </section>;
}
