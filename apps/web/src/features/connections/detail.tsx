"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import type { ConnectionView, ConnectionProbeView } from "../../lib/api/g4-generated";
import { PlatformApiError } from "../../lib/api/client";
import { command } from "../../lib/api/g2-client";
import { createConnectionsClient } from "./api";
import { ConfigurationForm } from "./form";
import { configFromForm, formFromConfig, validateForm, type ConnectionForm } from "./form-model";
import { ProbeReport, RequestError, stateLabels } from "./status";
import { CatalogPanel } from "./catalog";
const client = createConnectionsClient();
/** 权威详情与用户编辑分离；409仅刷新服务器快照，不丢弃非秘密编辑。 */
export function ConnectionDetail({ id, canManage }: { id: string; canManage: boolean }) {
  const [view, setView] = useState<ConnectionView | null>(null);
  const [etag, setEtag] = useState("");
  const [form, setForm] = useState<ConnectionForm | null>(null);
  const [probe, setProbe] = useState<ConnectionProbeView | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState("");
  const [catalogBusy, setCatalogBusy] = useState(false);
  // 同步引用阻止同一渲染周期内的交叉事件；令牌防止旧面板释放新面板的锁。
  const catalogOwner = useRef<symbol | null>(null);
  const parentPending = useRef(false);
  const catalogBusyChanged = useCallback((owner: symbol, pending: boolean) => {
    if (pending) {
      if (parentPending.current || catalogOwner.current) return false;
      catalogOwner.current = owner; setCatalogBusy(true);
    }
    else if (catalogOwner.current === owner) { catalogOwner.current = null; setCatalogBusy(false); }
    return true;
  }, []);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [secret, setSecret] = useState("");
  const [confirmDisable, setConfirmDisable] = useState(false);
  const [catalogRevision, setCatalogRevision] = useState(0);
  const [loaded, setLoaded] = useState(false);
  const [replay, setReplay] = useState<(() => Promise<void>) | null>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  function failed(cause: unknown) {
    setError(cause); setSecret("");
    if (cause instanceof PlatformApiError && [401, 403].includes(cause.status)) { setView(null); setForm(null); setProbe(null); setEtag(""); setReplay(null); }
    requestAnimationFrame(() => alertRef.current?.querySelector<HTMLElement>('[role="alert"]')?.focus());
  }
  async function refresh(preserve = true) {
    const response = await client.get(id);
    setView(response.data); setEtag(response.etag);
    if (!preserve) setForm(formFromConfig(response.data.displayName, response.data.config));
    if (response.data.lastProbeId) setProbe((await client.probe(id, response.data.lastProbeId)).data); else setProbe(null);
    setCatalogRevision(value => value + 1);
  }
  useEffect(() => {
    const controller = new AbortController();
    client.get(id, controller.signal).then(async response => {
      if (controller.signal.aborted) return;
      setView(response.data); setEtag(response.etag); setForm(formFromConfig(response.data.displayName, response.data.config));
      if (response.data.lastProbeId) { const report = await client.probe(id, response.data.lastProbeId, controller.signal); if (!controller.signal.aborted) setProbe(report.data); }
    }).catch(cause => { if (!controller.signal.aborted) failed(cause); }).finally(() => { if (!controller.signal.aborted) setLoaded(true); });
    return () => controller.abort();
  }, [id]);
  async function perform(label: string, work: () => Promise<void>, retry = false) {
    if (parentPending.current || catalogOwner.current) return;
    parentPending.current = true;
    setBusy(label); setError(null); setSecret("");
    const action = retry && replay ? replay : work;
    setReplay(() => action);
    try { await action(); setReplay(null); }
    catch (cause) { failed(cause); }
    finally { parentPending.current = false; setBusy(""); }
  }
  function accept(response: { data: ConnectionView; etag: string }) { setView(response.data); setEtag(response.etag); setForm(formFromConfig(response.data.displayName, response.data.config)); setProbe(null); setCatalogRevision(value => value + 1); }
  function save() {
    if (parentPending.current || catalogOwner.current) return;
    if (!view || !form) return;
    const next = validateForm(form); setErrors(next);
    if (Object.keys(next).length) { requestAnimationFrame(() => document.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()); return; }
    const body = { displayName: form.displayName, config: configFromForm(form), command: command(view.configRevision, "修改连接配置") };
    void perform("保存配置", async () => { accept(await client.patch(id, body, etag)); await refresh(false); });
  }
  function test() {
    if (parentPending.current || catalogOwner.current) return;
    if (!view) return;
    setProbe(null);
    const body = { command: command(view.configRevision, "重新测试已保存连接") };
    void perform("测试连接", async () => { setProbe((await client.test(id, body, etag)).data); await refresh(); });
  }
  function transition(action: "enable" | "disable") {
    if (parentPending.current || catalogOwner.current || !view) return;
    const body = { command: command(view.configRevision, action === "enable" ? "明确启用连接" : "终止连接生命周期") };
    setConfirmDisable(false);
    void perform(action === "enable" ? "启用连接" : "禁用连接", async () => { accept(await client.transition(id, action, body, etag)); await refresh(false); });
  }
  function rotate() {
    if (parentPending.current || catalogOwner.current) return;
    if (!view || secret.length < 8 || secret.length > 4096) { setErrors({ secret: "新凭据长度须为 8–4096 字符。" }); return; }
    const value = secret;
    // intake失败要求重新录入，不保留闭包中的原秘密供一般重放。
    parentPending.current = true;
    setBusy("轮换凭据"); setError(null); setSecret(""); setReplay(null);
    void client.intake({ secretValue: value, scopeSelection: view.scope, purpose: "POSTGRESQL_READONLY", command: command(0, "录入轮换凭据") }).then(async result => {
      const body = { secretRef: result.data.secretRef, command: command(view.configRevision, "轮换连接凭据") };
      const action = async () => { accept(await client.rotate(id, body, etag)); await refresh(false); };
      setReplay(() => action);
      await action(); setReplay(null);
    }).catch(failed).finally(() => { parentPending.current = false; setBusy(""); });
  }
  const interactionBusy = !!busy || catalogBusy;
  const disabled = view?.state === "DISABLED";
  const dirty = !!view && !!form && JSON.stringify(form) !== JSON.stringify(formFromConfig(view.displayName, view.config));
  return <div className="connections-workspace"><Link href="/data/connections">← 数据源</Link><div ref={alertRef}><RequestError error={error} retry={interactionBusy ? undefined : () => void perform("刷新详情", () => refresh(!!form))} /></div>
    {!loaded && <p role="status">正在读取连接详情…</p>}
    {view && form && <><div className="connection-heading"><div><h1>{view.displayName}</h1><p><span className={`tag ${view.state === "ACTIVE" ? "teal" : "amber"}`}>{stateLabels[view.state] ?? view.state}</span> 修订 {view.configRevision} · {view.secretConfigured ? "凭据已配置" : "未配置凭据"}</p></div><button disabled={interactionBusy} onClick={() => void perform("刷新详情", () => refresh())}>刷新详情</button></div>
      {disabled ? <p className="connection-alert">此连接已禁用，生命周期已终止。如需再次连接，请新建连接并重新测试。</p> : <p className="connection-note">{view.probeFresh ? "当前测试有效，可按需启用或发现目录。" : "需重新测试。配置或凭据变更会使旧测试失效，并恢复为草稿。"}</p>}
      {busy && <p role="status">正在{busy}…</p>}
      <form className="connection-card" onSubmit={event => { event.preventDefault(); save(); }} onKeyDown={event => { if (event.key === "Escape") { setConfirmDisable(false); setSecret(""); } }}>
        <ConfigurationForm value={form} onChange={next => { setForm(next); setReplay(null); }} errors={errors} disabled={interactionBusy || disabled || !canManage} fixedType />
        {dirty && <details className="connection-alert" open={error instanceof PlatformApiError && error.status === 409}><summary>未保存编辑 · 与当前服务器版本比较</summary><div className="connection-comparison"><div><strong>服务器当前配置（修订 {view.configRevision}）</strong><pre>{JSON.stringify({ displayName: view.displayName, config: view.config }, null, 2)}</pre></div><div><strong>我的未保存配置</strong><pre>{JSON.stringify({ displayName: form.displayName, config: configFromForm(form) }, null, 2)}</pre></div></div><button type="button" disabled={interactionBusy} onClick={() => { if (parentPending.current || catalogOwner.current) return; setForm(formFromConfig(view.displayName, view.config)); setReplay(null); setErrors({}); }}>放弃编辑并使用服务器版本</button></details>}
        {canManage && <div className="connection-actions"><button type="submit" disabled={interactionBusy || disabled || !dirty || !etag}>保存配置</button><button type="button" onClick={test} disabled={interactionBusy || disabled || dirty || !etag}>重新测试</button><button type="button" onClick={() => transition("enable")} disabled={interactionBusy || disabled || dirty || view.state !== "DRAFT" || !view.probeFresh || !etag}>明确启用连接</button><button type="button" onClick={() => { if (!parentPending.current && !catalogOwner.current) setConfirmDisable(true); }} disabled={interactionBusy || disabled || !etag}>禁用连接</button></div>}
        {confirmDisable && <div role="alert" className="connection-alert"><p>禁用后不能重新启用，将取消正在进行的目录发现。确认终止此连接？</p><button type="button" disabled={interactionBusy} onClick={() => transition("disable")}>确认禁用</button><button type="button" autoFocus onClick={() => setConfirmDisable(false)}>取消</button></div>}
      </form>
      {canManage && !disabled && <section className="connection-card"><h2>轮换凭据</h2><label>新密码<input type="password" autoComplete="new-password" value={secret} disabled={interactionBusy} onChange={event => setSecret(event.target.value)} /></label><p className="connection-note">不显示现有密码。轮换成功后需重新测试并启用。</p>{errors.secret && <p role="alert">{errors.secret}</p>}<button disabled={interactionBusy || !secret || !etag || dirty} onClick={rotate}>安全录入并轮换</button></section>}
      {replay && !busy && <button disabled={interactionBusy} onClick={() => void perform("恢复上次操作结果", replay!, true)}>恢复上次操作结果</button>}
      <ProbeReport probe={probe} running={busy === "测试连接"} />
      <CatalogPanel key={`${id}:${catalogRevision}`} connection={view} etag={etag} canManage={canManage && !dirty} onDenied={failed} parentBusy={!!busy} onBusyChange={catalogBusyChanged} />
    </>}
  </div>;
}
