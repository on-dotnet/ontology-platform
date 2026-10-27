"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useRef, useState } from "react";
import type { PlatformIdentity } from "../../lib/api/generated";
import type { OntologyDraft, SemanticSupportProfile, SourceBundle, SaveDraftRequest } from "../../lib/api/g2-generated";
import { command, createG2Client } from "../../lib/api/g2-client";
import { SemanticError } from "../../components/ui/semantic-feedback";
import { draftState, isDirty, updateSource, type DraftState } from "./draft-state";
import { StructuralForm } from "./structural-form";
import { SourceEditor } from "./source-editor";
import { SupportProfile } from "./support-profile";
import { AssessmentPanel } from "./assessment-panel";
import { VersionComparison } from "./version-comparison";
import "./workspace.css";

const client = createG2Client();
/** 浏览器专属图形模块在Client边界懒加载，SSR只显示明确加载状态。 */
const SemanticGraph = dynamic(() => import("./semantic-graph"), {
  ssr: false,
  loading: () => <p role="status">正在加载 RDF 图形…</p>,
});
const emptySources: SourceBundle = { ontologyTurtle: "", shapesTurtle: "", vocabularyTurtle: null, dataTurtle: "" };
const tabs = [{ id: "catalog", title: "资产" }, { id: "source", title: "源码" }, { id: "inspect", title: "图与校验" }];

/** 草稿目录、源缓冲、投影与真实服务命令保持同一修订边界。 */
export function OntologyWorkspace({ identity }: { identity: PlatformIdentity }) {
  const [drafts, setDrafts] = useState<OntologyDraft[] | null>(null);
  const [state, setState] = useState<DraftState | null>(null);
  const [remote, setRemote] = useState<OntologyDraft | null>(null);
  const [sources, setSources] = useState<SourceBundle>({ ...emptySources });
  const [name, setName] = useState("");
  const [scopeIndex, setScopeIndex] = useState("0");
  const [extraSites, setExtraSites] = useState<string[]>([]);
  const [field, setField] = useState<keyof SourceBundle>("ontologyTurtle");
  const [tab, setTab] = useState("catalog");
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [profile, setProfile] = useState<SemanticSupportProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileFailed, setProfileFailed] = useState(false);
  const [selected, setSelected] = useState("");
  const [reason, setReason] = useState("");
  const [retry, setRetry] = useState<SaveDraftRequest | null>(null);
  const lifetime = useRef<AbortController | null>(null);
  const dirty = state ? isDirty(state) : Boolean(name || Object.values(sources).some(Boolean));
  const canEdit = identity.roles.includes("platform.operator");
  const selectedScope = identity.scopes[Number(scopeIndex)];
  const chooseNode = useCallback((iri: string) => setSelected(iri), []);

  useEffect(() => {
    const controller = new AbortController();
    lifetime.current = controller;
    client.drafts(controller.signal)
      .then(items => { if (!controller.signal.aborted) setDrafts(items); })
      .catch(cause => { if (!controller.signal.aborted) setError(cause); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    void loadProfile(controller.signal);
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!dirty) return;
    const beforeUnload = (event: BeforeUnloadEvent) => { event.preventDefault(); };
    /** Next客户端导航不触发beforeunload；捕获同源导航以保留本地缓冲。 */
    const beforeNavigate = (event: MouseEvent) => {
      const anchor = event.target instanceof Element ? event.target.closest<HTMLAnchorElement>("a[href]") : null;
      if (!anchor || anchor.download || anchor.target === "_blank" || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
      const target = new URL(anchor.href, location.href);
      if (target.origin === location.origin && target.pathname !== location.pathname) {
        event.preventDefault();
        event.stopPropagation();
        setNotice("当前草稿有未保存内容，已保留本地文本。请先保存或显式丢弃，再切换工作区。");
      }
    };
    window.addEventListener("beforeunload", beforeUnload);
    document.addEventListener("click", beforeNavigate, true);
    return () => {
      window.removeEventListener("beforeunload", beforeUnload);
      document.removeEventListener("click", beforeNavigate, true);
    };
  }, [dirty]);

  /** 档案失败保持UNKNOWN，不能从投影或本地常量推断能力。 */
  async function loadProfile(signal: AbortSignal) {
    setProfileLoading(true);
    setProfileFailed(false);
    setProfile(null);
    try {
      const result = await client.supportProfile(signal);
      if (!signal.aborted) setProfile(result);
    } catch {
      if (!signal.aborted) setProfileFailed(true);
    } finally {
      if (!signal.aborted) setProfileLoading(false);
    }
  }

  /** 用户显式操作才发送写请求；卸载传播取消，不创建重复命令。 */
  async function execute(action: (signal: AbortSignal) => Promise<void>) {
    setBusy(true);
    setError(null);
    setNotice("");
    const signal = lifetime.current?.signal ?? new AbortController().signal;
    try {
      await action(signal);
    } catch (cause) {
      if (!signal.aborted) setError(cause);
    } finally {
      if (!signal.aborted) setBusy(false);
    }
  }

  /** 仅接受服务器已提交的修订；子面板按草稿ID和revision重置验证状态。 */
  function accept(draft: OntologyDraft) {
    setState(draftState(draft));
    setRemote(null);
    setRetry(null);
    setDrafts(items => [draft, ...(items ?? []).filter(item => item.draftId !== draft.draftId)]);
    setSelected("");
  }

  /** dirty草稿切换需显式丢弃，避免覆盖本地权威源缓冲。 */
  function open(draft: OntologyDraft) {
    if (dirty) {
      setNotice("当前草稿有未保存内容。请先保存，或显式丢弃后打开其他草稿。");
      return;
    }
    void execute(async signal => {
      accept(await client.draft(draft.draftId, signal));
      setTab("source");
    });
  }

  /** 保存冲突时state保持原样；显式重试才复用同一完整payload和幂等键。 */
  function save(explicitRetry = false) {
    if (!state) return;
    const payload = explicitRetry && retry ? retry : {
      name: state.name, sources: state.sources, command: command(state.draft.revision, reason),
    };
    setRetry(payload);
    void execute(async signal => {
      const saved = await client.saveDraft(state.draft.draftId, payload, signal);
      accept(saved);
      setNotice(`已保存 revision ${saved.revision}`);
    });
  }

  return (
    <div className="g2-workspace">
      <div className="g2-heading">
        <div>
          <p className="eyebrow">ONTOLOGY STUDIO</p>
          <h1>本体资产与草稿</h1>
          <p>原始 Turtle 是权威源 · 真实 RIOT / SHACL · Synthetic 开发事实</p>
        </div>
        <span className="tag violet">G3 M1 · 源码与支持</span>
      </div>
      {error !== null && <SemanticError error={error} />}
      {notice && <p role="status" className="g2-notice">{notice}</p>}
      <div className="g2-tabs g2-mobile-tabs" aria-label="移动工作区面板">
        {tabs.map(item => (
          <button className="button" key={item.id} aria-pressed={tab === item.id} onClick={() => setTab(item.id)}>{item.title}</button>
        ))}
      </div>
      <div className="g2-grid">
        <aside className={`g2-panel g2-stack ${tab !== "catalog" ? "g2-mobile-hidden" : ""}`} aria-label="资产目录">
          <div className="g2-row">
            <h2>草稿目录</h2>
            <button className="text-button" disabled={busy} onClick={() => void execute(async signal => {
              setDrafts(await client.drafts(signal));
              setLoading(false);
            })}>刷新</button>
          </div>
          {loading ? <p role="status">正在加载授权资产…</p> : drafts === null ? (
            <p className="muted">目录尚未成功读取，请刷新重试。</p>
          ) : drafts.length === 0 ? <p className="muted">当前授权范围暂无草稿。</p> : (
            <div className="g2-assets">
              {drafts.map(draft => (
                <button
                  className="g2-asset" key={draft.draftId} aria-current={state?.draft.draftId === draft.draftId}
                  disabled={busy} onClick={() => open(draft)}
                >
                  <strong>{draft.name}</strong>
                  <small>{draft.scope.siteIds.join(" / ")}</small>
                  <span className="tag blue">revision {draft.revision}</span>
                </button>
              ))}
            </div>
          )}
          <button className="button" disabled={busy} onClick={() => {
            if (dirty) { setNotice("未保存草稿仍保留，请先保存或显式丢弃。"); return; }
            setState(null);
            setRemote(null);
            setTab("source");
          }}>新建 / 导入资产</button>
        </aside>
        <section className={`g2-panel g2-stack ${tab !== "source" ? "g2-mobile-hidden" : ""}`} aria-label="草稿源码">
          <div className="g2-row">
            <h2>{state ? "源文档编辑" : "新建与导入"}</h2>
            <span className={`tag ${dirty ? "amber" : "teal"}`}>
              {state ? dirty ? "未保存 · 投影过期" : `revision ${state.draft.revision}` : "待创建"}
            </span>
          </div>
          <label>资产名称
            <input
              aria-label="资产名称" value={state?.name ?? name} disabled={busy || !canEdit} maxLength={200}
              onChange={event => {
                if (state) setState({ ...state, name: event.target.value });
                else setName(event.target.value);
                setRetry(null);
              }}
            />
          </label>
          {!state ? (
            <>
              <label>授权组织 / 默认单厂范围
                <select aria-label="创建资产作用域" value={scopeIndex} disabled={busy || !canEdit} onChange={event => {
                  setScopeIndex(event.target.value);
                  setExtraSites([]);
                }}>
                  {identity.scopes.map((scope, index) => (
                    <option key={`${scope.organizationId}/${scope.siteId}`} value={index}>{scope.organizationId} / {scope.siteId}</option>
                  ))}
                </select>
              </label>
              {selectedScope && identity.scopes
                .filter(scope => scope.organizationId === selectedScope.organizationId && scope.siteId !== selectedScope.siteId)
                .map(scope => (
                  <label key={scope.siteId} className="g2-row">
                    <span>额外授权厂区 {scope.siteId}</span>
                    <input
                      type="checkbox" checked={extraSites.includes(scope.siteId)} disabled={busy || !canEdit}
                      onChange={event => setExtraSites(items => event.target.checked ? [...items, scope.siteId] : items.filter(site => site !== scope.siteId))}
                    />
                  </label>
                ))}
              <p className="muted">载入四份 .ttl 原文件，或直接输入合成源。额外厂区须明确勾选，服务端再次校验。</p>
            </>
          ) : (
            <>
              <p className="g2-hash">{state.draft.assetId} · {state.draft.scope.organizationId} / {state.draft.scope.siteIds.join(" / ")}</p>
              <p className="g2-hash">bundle {state.draft.hashes.bundleHash}</p>
            </>
          )}
          <SourceEditor
            sources={state?.sources ?? sources} field={field} onField={setField} readOnly={busy || !canEdit}
            onAbsent={() => {
              if (state) setState({ ...state, sources: { ...state.sources, vocabularyTurtle: null } });
              else setSources(current => ({ ...current, vocabularyTurtle: null }));
              setRetry(null);
            }}
            onChange={(key, value) => {
              if (state) setState(updateSource(state, key, value));
              else setSources(current => ({ ...current, [key]: value }));
              setRetry(null);
            }}
          />
          <label>变更理由（必填，≤500字符）
            <input aria-label="变更理由" value={reason} maxLength={500} disabled={busy || !canEdit} onChange={event => {
              setReason(event.target.value);
              setRetry(null);
            }} />
          </label>
          {dirty && (
            <button className="button" disabled={busy} onClick={() => {
              if (state) setState(draftState(state.draft));
              else { setName(""); setSources({ ...emptySources }); }
              setRemote(null);
              setRetry(null);
              setNotice("已显式丢弃未保存修改；服务端草稿未改变。");
            }}>丢弃未保存修改</button>
          )}
          <div className="g2-row">
            {state ? (
              <>
                <button className="button primary" disabled={busy || !dirty || !reason.trim() || !canEdit} onClick={() => save()}>保存新修订</button>
                {retry && <button className="button" disabled={busy || !canEdit} onClick={() => save(true)}>重试原保存命令</button>}
                <button className="button" disabled={busy} onClick={() => void execute(async signal => {
                  const next = await client.draft(state.draft.draftId, signal);
                  if (dirty) {
                    setRemote(next);
                    setNotice("远端版本已加载供对比，本地文本保留。仅显式丢弃才覆盖。");
                  } else accept(next);
                })}>读取远端版本</button>
              </>
            ) : (
              <button
                className="button primary" disabled={busy || !name.trim() || !reason.trim() || !selectedScope || !canEdit}
                onClick={() => void execute(async signal => {
                  const draft = await client.createDraft({
                    name, sources,
                    scope: { organizationId: selectedScope.organizationId, siteIds: [selectedScope.siteId, ...extraSites].sort() },
                    baseReleaseId: null, command: command(0, reason),
                  }, signal);
                  accept(draft);
                  setName("");
                  setSources({ ...emptySources });
                  setNotice("草稿已创建并通过服务端解析");
                })}
              >创建真实草稿</button>
            )}
          </div>
          {!canEdit && <p className="g2-notice">当前身份仅可读取。编辑要求 platform.operator，最终授权由服务端执行。</p>}
          {remote && (
            <section className="g2-stack">
              <h3>远端 revision {remote.revision} 与本地文本对比</h3>
              <p className="g2-hash">远端 bundle {remote.hashes.bundleHash}</p>
              <pre className="g2-pre">{remote.sources[field] ?? "absent · 未提供"}</pre>
              <button className="button" disabled={busy} onClick={() => {
                accept(remote);
                setNotice("已显式丢弃本地内容并载入远端版本");
              }}>丢弃本地内容并载入此远端版本</button>
            </section>
          )}
        </section>
        <section className={`g2-panel g2-stack g2-inspector ${tab !== "inspect" ? "g2-mobile-hidden" : ""}`} aria-label="结构与验证">
          <SupportProfile profile={profile} loading={profileLoading} failed={profileFailed} onRefresh={() => {
            const signal = lifetime.current?.signal;
            if (signal) void loadProfile(signal);
          }} />
          {state ? (
            <>
              <SemanticGraph projection={state.draft.projection} stale={dirty} onSelect={chooseNode} />
              {state.draft.projection.diagnostics.map((diagnostic, index) => (
                <p className="g2-notice" key={index}>{diagnostic.code} · {diagnostic.message}</p>
              ))}
              <StructuralForm
                projection={state.draft.projection} selected={selected} blocked={busy || dirty || !canEdit || !reason.trim()}
                onEdit={edit => void execute(async signal => {
                  accept(await client.editDraft(state.draft.draftId, { edit, command: command(state.draft.revision, reason) }, signal));
                  setNotice("结构编辑已由服务端保存为新修订");
                })}
              />
              <AssessmentPanel
                key={`assessment/${state.draft.draftId}/${state.draft.revision}`}
                draft={state.draft} profile={profile} dirty={dirty} busy={busy} canEdit={canEdit}
                reason={reason} execute={execute} onNotice={setNotice}
              />
              <VersionComparison
                key={`comparison/${state.draft.draftId}/${state.draft.revision}`}
                draft={state.draft} busy={busy} execute={execute}
              />
            </>
          ) : (
            <>
              <h2>语义检查器</h2>
              <p className="muted">选择或创建真实草稿后，显示相同 revision / hash 的投影、结构表单、SHACL 与 Diff。</p>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
