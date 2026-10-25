"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import type { PlatformIdentity, PlatformResourceList, PlatformAuditEntry } from "../../lib/api/generated";
import { createPlatformClient, PlatformApiError } from "../../lib/api/client";
import { Icon } from "../../components/ui/icon";
import { ResourceDialog } from "../../components/ui/resource-dialog";

/** 当前关口开放的三个平台视图，不包含尚未授权的业务入口。 */
type View = "resources" | "audit" | "scope";
const client = createPlatformClient();
const views = [{ id: "resources" as const, title: "平台资源", icon: "grid", note: "授权资源工作区" }, { id: "audit" as const, title: "访问审计", icon: "activity", note: "事件与 Trace 关联" }, { id: "scope" as const, title: "授权范围", icon: "shield", note: "身份与访问边界" }];
/** 仅保存真实请求结果；失败时清除旧数据并区分认证、无权和依赖故障。 */
export function Workspace({ identity }: { identity: PlatformIdentity }) {
  const [view, setView] = useState<View>("resources");
  const [sidebar, setSidebar] = useState(false);
  const [resources, setResources] = useState<PlatformResourceList | null>(null);
  const [audit, setAudit] = useState<PlatformAuditEntry[]>([]);
  const [pending, setPending] = useState(true);
  const [error, setError] = useState<{ status: number; traceId?: string } | null>(null);
  const [revision, setRevision] = useState(0);
  const [search, setSearch] = useState("");
  const [site, setSite] = useState("");
  const [csrf, setCsrf] = useState("");
  const [logoutError, setLogoutError] = useState(false);
  const logoutForm = useRef<HTMLFormElement>(null);
  const currentView = views.find(item => item.id === view)!;
  useEffect(() => {
    if (view === "scope") return;
    const controller = new AbortController();
    const request = view === "audit" ? client.audit(controller.signal) : client.resources(site || undefined, controller.signal);
    request.then(result => { if (controller.signal.aborted) return; if (Array.isArray(result)) setAudit(result); else setResources(result); }).catch(cause => {
      if (controller.signal.aborted) return;
      setError(cause instanceof PlatformApiError ? { status: cause.status, traceId: cause.traceId } : { status: 0 });
    }).finally(() => { if (!controller.signal.aborted) setPending(false); });
    return () => controller.abort();
  }, [view, site, revision]);
  useEffect(() => { if (csrf) logoutForm.current?.submit(); }, [csrf]);
  /** 先取得同源防伪令牌，再由原生表单完成顶层OIDC注销导航。 */
  async function prepareLogout() {
    setLogoutError(false);
    try { const result = await client.csrf(); setCsrf(result.requestToken); } catch { setLogoutError(true); }
  }
  function beginRequest() { setPending(true); setError(null); setResources(null); setAudit([]); }
  function refresh() { beginRequest(); setRevision(n => n + 1); }
  function changeView(next: View) { if (next !== view && next !== "scope") beginRequest(); setView(next); setSidebar(false); setSearch(""); }
  function toggleTheme() {
    const next = document.documentElement.dataset.theme === "light" ? "dark" : "light";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("ontology-theme", next); } catch { /* 存储不可用时保留本次会话主题。 */ }
  }
  const items = resources?.items.filter(item => `${item.name} ${item.id} ${item.siteId}`.toLowerCase().includes(search.toLowerCase())) ?? [];
  return <div className="shell">
    {sidebar && <button className="sidebar-overlay" aria-label="关闭导航" onClick={() => setSidebar(false)} />}
    <aside className={`sidebar ${sidebar ? "is-open" : ""}`} aria-label="主导航">
      <Link href="/" className="brand">
        <span className="brand-mark">O<span />
        </span>
        <span>Ontology<span className="brand-suffix">Platform</span>
        </span>
      </Link>
      <div className="workspace-label">
        <span className="workspace-logo">P</span>
        <div>
          <strong>平台治理空间</strong>
          <small>Development workspace</small>
        </div>
        <span className="tiny-dot" />
      </div>
      <p className="nav-caption">工作台</p>
      <nav>{views.map(item => <button key={item.id} className={`nav-item ${view === item.id ? "active" : ""}`} onClick={() => changeView(item.id)} aria-current={view === item.id ? "page" : undefined}>
        <Icon name={item.icon} />
        <span>{item.title}</span>{view === item.id && <span className="nav-indicator" />}</button>)}</nav>
      <div className="sidebar-bottom">
        <div className="boundary-card">
          <Icon name="shield" />
          <strong>可信访问边界</strong>
          <p>每次资源访问均由服务端校验，并关联审计记录。</p>
          <span className="tag teal">G1 · 开发合成资源</span>
        </div>
        <div className="sidebar-footer">
          <span className="status-dot" /> 本地开发环境 <span>WAVE 2</span>
        </div>
      </div>
    </aside>
    <div className="shell-body">
      <header className="topbar">
        <div className="topbar-left">
          <button className="icon-button mobile-menu" aria-label="打开导航" onClick={() => setSidebar(true)}>
            <Icon name="menu" />
          </button>
          <span className="breadcrumb">工作台</span>
          <span className="breadcrumb-separator">/</span>
          <strong>{currentView.title}</strong>
        </div>
        <div className="topbar-actions">
          <span className="environment">
            <span className="status-dot" /> Development</span>
          <span className="topbar-divider" />
          <button className="icon-button" aria-label="切换深浅主题" onClick={toggleTheme}>
            <Icon name="sun" />
          </button>
          <div className="user-avatar" aria-hidden="true">{identity.displayName.slice(0, 1).toUpperCase()}</div>
          <span className="user-name">{identity.displayName}</span>
        </div>
      </header>
      <main id="main" className="workspace-main">
        <div className="page-heading">
          <div>
            <p className="eyebrow">PLATFORM WORKSPACE</p>
            <h1>{currentView.title}<span className="heading-dot" />
            </h1>
            <p>{currentView.note}，让每一次访问清晰可见。</p>
          </div>
          <div className="heading-actions">{view !== "scope" && <button className="button" onClick={refresh} disabled={pending}>
            <Icon name="refresh" size={16} /> 刷新数据</button>}<span className="tag blue">只读工作区</span>
          </div>
        </div>
        <section className="welcome-banner">
          <div>
            <span className="banner-kicker">你好，{identity.displayName}</span>
            <h2>在可信范围内，连接每一份资源。</h2>
            <p>当前工作台仅展示平台开发合成数据。所有可见内容均遵循当前身份的授权边界。</p>
          </div>
          <div className="banner-art" aria-hidden="true">
            <span />
            <span />
            <Icon name="box" size={64} />
          </div>
        </section>
        <section className="stat-grid" aria-label="当前访问概况">
          <Stat icon="box" color="blue" title="可见平台资源" value={resources ? String(resources.items.length).padStart(2, "0") : "—"} note="来自本次服务端授权查询" />
          <Stat icon="shield" color="teal" title="授权厂区范围" value={String(identity.scopes.length).padStart(2, "0")} note="当前身份的组织与厂区边界" />
          <Stat icon="activity" color="violet" title="平台角色" value={String(identity.roles.length).padStart(2, "0")} note="身份服务认可的平台角色" />
        </section>
        {view === "scope" ? <section className="panel">
          <PanelHeading title="当前身份与访问边界" note="由平台身份服务验证" />
          <div className="scope-layout">
            <div className="identity-card">
              <span className="large-avatar">{identity.displayName.slice(0, 1).toUpperCase()}</span>
              <h2>{identity.displayName}</h2>
              <p className="muted">已认证平台身份</p>
              <div className="role-list">{identity.roles.length ? identity.roles.map(role => <span key={role} className="tag violet">{role}</span>) : <span className="tag amber">未分配平台角色</span>}</div>
            </div>
            <div className="scope-list">
              <h3>已授权作用域</h3>{identity.scopes.length ? identity.scopes.map(scope => <div className="scope-row" key={`${scope.organizationId}/${scope.siteId}`}>
                <span className="scope-icon">
                  <Icon name="shield" />
                </span>
                <div>
                  <strong>{scope.siteId}</strong>
                  <small>{scope.organizationId}</small>
                </div>
                <span className="tag teal">已授权范围</span>
              </div>) : <p>当前身份没有厂区作用域。</p>}<p className="scope-footnote">角色和作用域共同决定可见资源，最终授权以服务端每次请求的结果为准。</p>
            </div>
          </div>
        </section> : <section className="panel">
          <PanelHeading title={view === "resources" ? "受保护的平台资源" : "访问事件"} note={view === "resources" ? "仅显示当前组织与厂区的资源" : "审计事实由 PostgreSQL 持久化，当前请求需审计角色"} extra={view === "resources" && <span className="count-badge">{resources?.items.length ?? "—"} 项</span>} />
          {view === "resources" && <div className="table-toolbar">
            <label className="search-field">
              <Icon name="search" size={17} />
              <input value={search} onChange={event => setSearch(event.target.value)} placeholder="搜索资源名称、标识…" aria-label="搜索平台资源" />
            </label>
            <label className="site-filter">
              <span>厂区范围</span>
              <select value={site} onChange={event => { beginRequest(); setSite(event.target.value); }} aria-label="筛选授权厂区">
                <option value="">全部授权厂区</option>{identity.scopes.map(scope => <option value={scope.siteId} key={`${scope.organizationId}/${scope.siteId}`}>{scope.siteId}</option>)}</select>
            </label>
          </div>}
          {pending ? <div className="loading-state" role="status">
            <span className="spinner" />
            <strong>正在读取{view === "audit" ? "访问审计" : "授权资源"}…</strong>
            <p>正在等待平台服务响应</p>{[1, 2, 3].map(n => <div key={n} className="skeleton" />)}</div> : error ? <RequestError status={error.status} traceId={error.traceId} onRetry={refresh} /> : view === "resources" ? <>{items.length ? <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>资源名称</th>
                    <th>组织 / 厂区</th>
                    <th>数据性质</th>
                    <th>访问权限</th>
                    <th>
                      <span className="sr-only">操作</span>
                    </th>
                  </tr>
                </thead>
                <tbody>{items.map(item => <tr key={item.id}>
                  <td>
                    <div className="resource-cell">
                      <span className="resource-icon">
                        <Icon name="box" />
                      </span>
                      <div>
                        <strong>{item.name}</strong>
                        <small>{item.id}</small>
                      </div>
                    </div>
                  </td>
                  <td>
                    <strong>{item.siteId}</strong>
                    <small>{item.organizationId}</small>
                  </td>
                  <td>
                    <span className="tag amber">开发合成</span>
                  </td>
                  <td>
                    <span className="permission">
                      <Icon name="check" size={14} /> 可读取</span>
                  </td>
                  <td>
                    <ResourceDialog resource={item} traceId={resources!.traceId} auditId={resources!.auditId} />
                  </td>
                </tr>)}</tbody>
              </table>
            </div> : <Empty title={search ? "没有匹配的资源" : "当前范围内暂无资源"} description={search ? "尝试调整搜索关键词或厂区筛选。" : "服务端已完成查询，未返回可见资源。"} />}{resources && <div className="table-footer">
              <span>
                <span className="status-dot" /> 已完成服务端授权校验</span>
              <span>本次读取 {resources.items.length} 项</span>
            </div>}</> : audit.length ? <div className="audit-list">{audit.map(entry => <article key={entry.id} className="audit-event">
              <span className={`audit-dot ${entry.outcome.toLowerCase().includes("den") ? "denied" : ""}`} />
              <div>
                <div className="audit-event-heading">
                  <strong>{entry.action}</strong>
                  <span className="tag blue">{entry.outcome}</span>
                  <time>{new Date(entry.occurredAtUtc).toLocaleString("zh-CN")}</time>
                </div>
                <p>{entry.actor} <span className="muted">访问</span> {entry.resource}</p>
                <div className="trace-pair">
                  <span>审计 <code>{entry.id}</code>
                  </span>
                  <span>Trace <code>{entry.traceId || "未关联"}</code>
                  </span>
                </div>
              </div>
            </article>)}</div> : <Empty title="当前范围内暂无审计事件" description="事件仅在服务端真实发生并持久化后出现。" />}</section>}
        {resources && view === "resources" && <section className="trace-panel">
          <div className="trace-icon">
            <Icon name="activity" />
          </div>
          <div>
            <h3>这次访问，有迹可循</h3>
            <p>以下标识来自本次真实资源读取，可与访问审计和运维 Trace 交叉核验。</p>
            <div className="trace-pair">
              <span>审计 ID <code>{resources.auditId}</code>
              </span>
              <span>Trace ID <code>{resources.traceId}</code>
              </span>
            </div>
          </div>
        </section>}
        <footer className="workspace-footer">
          <span>Ontology Platform <span className="footer-dot">·</span> 可信语义，连接未来</span>
          <button className="text-button muted" onClick={prepareLogout}>
            <Icon name="logout" size={15} /> 安全退出</button>
        </footer>{logoutError && <p className="inline-error" role="alert">无法准备安全退出，请重试。当前会话未被注销。</p>}<form ref={logoutForm} action="/auth/logout" method="post" hidden>
          <input type="hidden" name="__RequestVerificationToken" value={csrf} />
        </form>
      </main>
    </div>
  </div>;
}
/** 显示本次真实请求与身份范围的计数，未返回数据时保留未知标记。 */
function Stat({ icon, color, title, value, note }: { icon: string; color: string; title: string; value: string; note: string }) {
  return <article className="stat-card">
    <div className="stat-top">
      <span>{title}</span>
      <span className={`stat-icon ${color}`}>
        <Icon name={icon} />
      </span>
    </div>
    <strong className="stat-value">{value}</strong>
    <p>{note}</p>
  </article>;
}
/** 统一工作区面板标题、数据范围说明和请求状态提示。 */
function PanelHeading({ title, note, extra }: { title: string; note: string; extra?: React.ReactNode }) {
  return <div className="panel-heading">
    <div>
      <h2>{title} {extra}</h2>
      <p>{note}</p>
    </div>
    <span className="panel-live">
      <span className="status-dot" /> 实时请求</span>
  </div>;
}
/** 区分合法空集合与搜索无结果，不把空数据当作服务故障。 */
function Empty({ title, description }: { title: string; description: string }) {
  return <div className="empty-state">
    <span className="empty-icon">
      <Icon name="box" size={30} />
    </span>
    <h3>{title}</h3>
    <p>{description}</p>
  </div>;
}
/** 按服务端状态提供会话恢复、权限拒绝或可重试的故障入口。 */
function RequestError({ status, traceId, onRetry }: { status: number; traceId?: string; onRetry: () => void }) {
  return <div className="empty-state error-state" role="alert">
    <span className="empty-icon">
      <Icon name={status === 403 ? "shield" : "activity"} size={30} />
    </span>
    <span className="eyebrow">{status === 403 ? "403 · ACCESS BOUNDARY" : status === 401 ? "401 · SESSION EXPIRED" : "CONNECTION UNAVAILABLE"}</span>
    <h3>{status === 403 ? "当前身份无权访问" : status === 401 ? "登录会话已结束" : "暂时无法读取数据"}</h3>
    <p>{status === 403 ? "身份已确认，但当前角色或厂区范围不允许访问此内容。" : status === 401 ? "请重新登录以继续访问平台资源。" : "平台服务或网络暂时不可用，请稍后重试。"}</p>{traceId && <code className="error-trace">Trace {traceId}</code>}{status === 401 ? <a className="button primary" href="/auth/login?returnUrl=/">重新登录</a> : status !== 403 && <button className="button" onClick={onRetry}>重新读取</button>}</div>;
}
