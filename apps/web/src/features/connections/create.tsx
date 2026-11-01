"use client";
import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import type { PlatformIdentity } from "../../lib/api/generated";
import type { ConnectionDraftProbeRequest, ConnectionProbeView, ConnectionCreateRequest } from "../../lib/api/g4-generated";
import { command } from "../../lib/api/g2-client";
import { createConnectionsClient } from "./api";
import { ConfigurationForm } from "./form";
import { configFromForm, newForm, validateForm } from "./form-model";
import { ProbeReport, RequestError } from "./status";
const client = createConnectionsClient();
/** 新建闭环：密码只交给专用入口，草稿测试与保存分别明确提交，失败重放原命令。 */
export function CreateConnection({ identity }: { identity: PlatformIdentity }) {
  const router = useRouter();
  const [form, setForm] = useState(newForm);
  const [site, setSite] = useState(identity.scopes[0]?.siteId ?? "");
  const [secret, setSecret] = useState("");
  const [secretRef, setSecretRef] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [probe, setProbe] = useState<ConnectionProbeView | null>(null);
  const [pendingProbe, setPendingProbe] = useState<ConnectionDraftProbeRequest | null>(null);
  const [pendingCreate, setPendingCreate] = useState<ConnectionCreateRequest | null>(null);
  const canManage = identity.roles.includes("operator");
  const selected = identity.scopes.find(scope => scope.siteId === site);
  const scope = selected ? { organizationId: selected.organizationId, siteIds: [selected.siteId] } : null;
  const runnable = form.type === "POSTGRESQL";
  function changed(next: typeof form) {
    if (next.type !== form.type) { setSecret(""); setSecretRef(""); }
    setForm(next); setProbe(null); setPendingProbe(null); setPendingCreate(null);
  }
  function valid() {
    const next = validateForm(form);
    if (!scope) next.scope = "请选择您有权访问的厂区。";
    setErrors(next);
    if (Object.keys(next).length) { requestAnimationFrame(() => document.querySelector<HTMLElement>('[aria-invalid="true"]')?.focus()); return false; }
    return true;
  }
  async function intake() {
    if (!scope || secret.length < 8 || secret.length > 4096) { setErrors({ ...errors, secret: "凭据长度须为 8–4096 字符。" }); return; }
    setBusy("secret"); setError(null);
    const value = secret; setSecret(""); setSecretRef(""); setPendingProbe(null); setPendingCreate(null); setProbe(null);
    try { const result = await client.intake({ secretValue: value, scopeSelection: scope, purpose: "POSTGRESQL_READONLY", command: command(0, "录入只读连接凭据") }); setSecretRef(result.data.secretRef); setErrors({}); }
    catch (cause) { setError(cause); }
    finally { setBusy(""); }
  }
  async function test(replay = false) {
    if (!scope || !runnable || !valid() || !secretRef) return;
    setBusy("probe"); setError(null);
    const body = replay && pendingProbe ? pendingProbe : { scopeSelection: scope, config: configFromForm(form), secretRef, command: command(0, "测试未保存连接") };
    setPendingProbe(body);
    try { setProbe((await client.draftProbe(body)).data); setPendingProbe(null); }
    catch (cause) { setError(cause); }
    finally { setBusy(""); }
  }
  async function save() {
    if (!scope || !runnable || !valid() || !secretRef) return;
    setBusy("save"); setError(null);
    const body = pendingCreate ?? { displayName: form.displayName, scopeSelection: scope, config: configFromForm(form), secretRef, command: command(0, "保存连接草稿") };
    setPendingCreate(body);
    try { const result = await client.create(body); setSecretRef(""); setPendingCreate(null); router.push(`/data/connections/${encodeURIComponent(result.data.id)}`); }
    catch (cause) { setError(cause); }
    finally { setBusy(""); }
  }
  return <div className="connections-workspace"><div className="connection-heading"><div><Link href="/data/connections">← 数据源</Link><h1>新建连接</h1><p>配置只读数据源，测试后保存草稿，再显式启用。</p></div></div>
    {!canManage && <div role="alert" className="connection-alert">您拥有只读访问权限，不能新建连接。</div>}
    <RequestError error={error} />
    <form className="connection-card" onSubmit={event => { event.preventDefault(); if (runnable) void test(); else valid(); }}>
      <ConfigurationForm value={form} onChange={changed} errors={errors} disabled={!!busy || !canManage} />
      <label className="connection-scope">所属厂区<select value={site} disabled={!!busy || !canManage} onChange={event => { setSite(event.target.value); setSecret(""); setSecretRef(""); setProbe(null); setPendingProbe(null); setPendingCreate(null); }}>{identity.scopes.map(item => <option value={item.siteId} key={`${item.organizationId}/${item.siteId}`}>{item.organizationId} / {item.siteId}</option>)}</select>{errors.scope && <span role="alert">{errors.scope}</span>}</label>
      {runnable && <fieldset className="connection-secret" disabled={!!busy || !canManage}><legend>只读账号凭据</legend><label>重新输入密码<input type="password" autoComplete="new-password" value={secret} onChange={event => setSecret(event.target.value)} aria-invalid={!!errors.secret} aria-describedby="secret-note" /></label><p id="secret-note">密码仅发送至安全凭据入口，录入后清空。刷新页面需重新录入。</p>{errors.secret && <p role="alert">{errors.secret}</p>}<button type="button" onClick={() => void intake()} disabled={!secret || !scope}>{busy === "secret" ? "正在录入…" : "安全录入凭据"}</button>{secretRef && <span className="tag teal">临时凭据已就绪</span>}</fieldset>}
      <div className="connection-actions"><button type="button" onClick={valid} disabled={!!busy}>校验配置</button><button type="submit" disabled={!!busy || !canManage || !runnable || !secretRef}>{busy === "probe" ? "正在测试…" : "测试草稿"}</button>{pendingProbe && !busy && <button type="button" onClick={() => void test(true)}>恢复上次测试结果</button>}<button type="button" className="button primary" onClick={() => void save()} disabled={!!busy || !canManage || !runnable || !secretRef}>{busy === "save" ? "正在保存…" : pendingCreate ? "恢复上次保存结果" : "保存为草稿"}</button></div>
      {!runnable && <p role="status">配置可校验；此类型尚未支持连接测试与保存。</p>}
      {!Object.keys(errors).length && <p className="connection-note">草稿测试不会启用连接；保存后需再次测试，才能启用。</p>}
    </form><ProbeReport probe={probe} running={busy === "probe"} />
  </div>;
}
