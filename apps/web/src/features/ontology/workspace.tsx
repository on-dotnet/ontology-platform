"use client";
import dynamic from "next/dynamic";
import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import type { PlatformIdentity } from "../../lib/api/generated";
import type { OntologyDraft, SemanticSupportProfile, SourceBundle, SaveDraftRequest, DraftDiff, VocabularyChange, VocabularySnapshot } from "../../lib/api/g2-generated";
import { command, createG2Client } from "../../lib/api/g2-client";
import { SemanticError } from "../../components/ui/semantic-feedback";
import { draftState, isDirty, isNewDraftDirty, updateSource, type DraftState } from "./draft-state";
import { EntityTree, EntityProperties } from "./entity-tree";
import { StructuralForm } from "./structural-form";
import { SourceEditor } from "./source-editor";
import { SourceImportSession, type SourceImportHandle } from "./source-import";
import { SupportProfile } from "./support-profile";
import { AssessmentPanel } from "./assessment-panel";
import { VersionComparison } from "./version-comparison";
import { initialWorkspaceView, workspaceView } from "./workspace-state";
import { VocabularyWorkbench } from "./vocabulary-workbench";
import { snapshotMatches } from "./vocabulary-model";
import { ReleasedVocabulary } from "./released-vocabulary";
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
  const [vocabularyOpened, setVocabularyOpened] = useState(false);
  const [vocabularyMode, setVocabularyMode] = useState(false);
  const [vocabularyPending, setVocabularyPending] = useState(false);
  const [structuralDiff, setStructuralDiff] = useState<DraftDiff | null>(null);
  const [remote, setRemote] = useState<OntologyDraft | null>(null);
  const [sources, setSources] = useState<SourceBundle>({ ...emptySources });
  const [name, setName] = useState("");
  const [scopeIndex, setScopeIndex] = useState("0");
  const [extraSites, setExtraSites] = useState<string[]>([]);
  const [field, setField] = useState<keyof SourceBundle>("ontologyTurtle");
  const [view, dispatchView] = useReducer(workspaceView, initialWorkspaceView);
  const { panel: tab, centerView, selected } = view;
  const setTab = (panel: string) => dispatchView({ type: "panel", panel });
  const setCenterView = (next: "source" | "graph") => dispatchView({ type: "view", view: next });
  const setSelected = (iri: string) => dispatchView({ type: "select", iri });
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [profile, setProfile] = useState<SemanticSupportProfile | null>(null);
  const [profileLoading, setProfileLoading] = useState(true);
  const [profileFailed, setProfileFailed] = useState(false);
  const [reason, setReason] = useState("");
  const [retry, setRetry] = useState<SaveDraftRequest | null>(null);
  const lifetime = useRef<AbortController | null>(null);
  const sourceImports = useRef(new SourceImportSession());
  const dirty = state ? isDirty(state) : isNewDraftDirty(name, sources);
  const hasUnsaved = dirty || vocabularyPending;
  const canEdit = identity.roles.includes("platform.operator");
  const selectedScope = identity.scopes[Number(scopeIndex)];
  const chooseNode = useCallback((iri: string) => dispatchView({ type: "select", iri }), []);

  useEffect(() => {
    const controller = new AbortController();
    const imports = sourceImports.current;
    lifetime.current = controller;
    client.drafts(controller.signal)
      .then(items => { if (!controller.signal.aborted) setDrafts(items); })
      .catch(cause => { if (!controller.signal.aborted) setError(cause); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    void loadProfile(controller.signal);
    return () => { imports.invalidate(); controller.abort(); };
  }, []);

  useEffect(() => {
    sourceImports.current.invalidate();
  }, [identity.subjectId]);

  useEffect(() => {
    if (!hasUnsaved) return;
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
  }, [hasUnsaved]);

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
    sourceImports.current.invalidate();
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
    sourceImports.current.invalidate();
    setState(draftState(draft));
    setStructuralDiff(null);
    setRemote(null);
    setRetry(null);
    setDrafts(items => [draft, ...(items ?? []).filter(item => item.draftId !== draft.draftId)]);
    setSelected("");
    setVocabularyPending(false);
  }

  /** dirty草稿切换需显式丢弃，避免覆盖本地权威源缓冲。 */
  function open(draft: OntologyDraft) {
    if (hasUnsaved) {
      setNotice("当前草稿有未保存内容。请先保存，或显式丢弃后打开其他草稿。");
      return;
    }
    void execute(async signal => {
      accept(await client.draft(draft.draftId, signal));
      setVocabularyMode(false);
      setVocabularyOpened(false);
      dispatchView({ type: "open" });
    });
  }

  /** 冻结读取目标，完成时按当前缓冲合并；不同源/名称的新修改不会被旧闭包覆盖。 */
  function beginImport(field: keyof SourceBundle): SourceImportHandle {
    const imports = sourceImports.current;
    const ticket = imports.begin(field, { draftId: state?.draft.draftId ?? null, revision: state?.draft.revision ?? null });
    return {
      isCurrent: () => imports.isCurrent(ticket),
      commit: value => {
        if (!imports.isCurrent(ticket)) return;
        if (ticket.draftId === null) {
          setSources(current => imports.isCurrent(ticket) ? { ...current, [field]: value } : current);
        } else {
          setState(current => {
            if (!imports.isCurrent(ticket) || !current || current.draft.draftId !== ticket.draftId
              || current.draft.revision !== ticket.revision) return current;
            return updateSource(current, field, value);
          });
        }
        setRetry(null);
      },
    };
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
        <span className="tag violet">G3 M3 · 术语与单位</span>
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
            if (hasUnsaved) { setNotice("未保存草稿仍保留，请先保存或显式丢弃。"); return; }
            sourceImports.current.invalidate();
            setState(null);
            setVocabularyMode(false);
            setVocabularyOpened(false);
            setVocabularyPending(false);
            setRemote(null);
            dispatchView({ type: "new" });
          }}>新建 / 导入资产</button>
          {state && <EntityTree projection={state.draft.projection} selected={selected} onSelect={chooseNode} />}
        </aside>
        <section className={`g2-panel g2-stack ${tab !== "source" ? "g2-mobile-hidden" : ""}`} aria-label="草稿源码">
          <div className="g2-row">
            <h2>{state ? "源文档编辑" : "新建与导入"}</h2>
            <span className={`tag ${dirty ? "amber" : "teal"}`}>
              {state ? dirty ? "未保存 · 投影过期" : `revision ${state.draft.revision}` : "待创建"}
            </span>
          </div>
          <label>变更理由（必填，≤500字符）
            <input aria-label="变更理由" value={reason} maxLength={500} disabled={busy || !canEdit} onChange={event => {
              setReason(event.target.value);
              setRetry(null);
            }} />
          </label>
          {state && (
            <div className="g2-tabs" aria-label="中间建模视图">
              <button className="button" aria-pressed={centerView === "graph"} onClick={() => { setVocabularyMode(false); setCenterView("graph"); }}>图视图</button>
              <button className="button" aria-pressed={centerView === "source" && !vocabularyMode} onClick={() => { setVocabularyMode(false); setCenterView("source"); }}>源码视图</button>
              <button className="button" aria-pressed={vocabularyMode} onClick={() => { setVocabularyOpened(true); setVocabularyMode(true); setCenterView("source"); }}>术语与单位</button>
            </div>
          )}
          {state && centerView === "graph" && (
            <SemanticGraph projection={state.draft.projection} selected={selected} stale={dirty} onSelect={chooseNode} />
          )}
          <div hidden={!vocabularyMode}>{state && vocabularyOpened && <VocabularyWorkbench
            key={`vocabulary/${state.draft.draftId}/${state.draft.revision}`} draft={state.draft} selected={selected} onSelect={chooseNode}
            dirty={dirty} busy={busy} canEdit={canEdit} reason={reason} onPending={setVocabularyPending} pending={vocabularyPending} profile={profile}
            onLocate={(nextField, focus) => { setField(nextField); setSelected(focus ?? ""); setVocabularyMode(false); setCenterView("source"); setTab("source"); }}
            onCommit={(changes: VocabularyChange[], snapshot: VocabularySnapshot) => void execute(async signal => {
              if (dirty || !snapshotMatches(snapshot, state.draft)) throw new Error("词汇批次已过期，请先保存源码并刷新词汇快照。");
              const previousRevision = state.draft.revision;
              const next = await client.editVocabulary(state.draft.draftId, { hashes: snapshot.hashes, changes, command: command(previousRevision, reason) }, signal);
              if (signal.aborted) return;
              accept(next);
              setSelected(selected);
              setVocabularyMode(true);
              setNotice(`词汇批次已原子保存为 revision ${next.revision}；需重新运行完整评估与异人审批。`);
              const diff = await client.diff(next.draftId, previousRevision, signal);
              if (!signal.aborted && diff.targetRevision === next.revision && diff.targetHashes.bundleHash === next.hashes.bundleHash) setStructuralDiff(diff);
            })}
          />}</div>
          {vocabularyPending && <p className="g2-notice">词汇批次尚未提交。切换视图保留批次；请先原子提交或取消批次，再修改源码或打开其它资产。</p>}
          <div className="g2-stack" hidden={Boolean(state && (centerView !== "source" || vocabularyMode))}>
            <label>资产名称
              <input
                aria-label="资产名称" value={state?.name ?? name} disabled={busy || !canEdit || vocabularyPending} maxLength={200}
                onChange={event => {
                  const nextName = event.target.value;
                  if (state) setState(current => current ? { ...current, name: nextName } : current);
                  else setName(nextName);
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
              sources={state?.sources ?? sources} field={field} onField={setField} readOnly={busy || !canEdit || vocabularyPending}
              onBeginImport={beginImport}
              onAbsent={() => {
                sourceImports.current.invalidate("vocabularyTurtle");
                if (state) setState(current => current ? { ...current, sources: { ...current.sources, vocabularyTurtle: null } } : current);
                else setSources(current => ({ ...current, vocabularyTurtle: null }));
                setRetry(null);
              }}
              onChange={(key, value) => {
                sourceImports.current.invalidate(key);
                if (state) setState(current => current ? updateSource(current, key, value) : current);
                else setSources(current => ({ ...current, [key]: value }));
                setRetry(null);
              }}
            />

            {dirty && (
              <button className="button" disabled={busy} onClick={() => {
                sourceImports.current.invalidate();
                if (state) setState(current => current ? draftState(current.draft) : current);
                else { setName(""); setSources({ ...emptySources }); }
                setRemote(null);
                setRetry(null);
                setNotice("已显式丢弃未保存修改；服务端草稿未改变。");
              }}>丢弃未保存修改</button>
            )}
            <div className="g2-row">
              {state ? (
                <>
                  <button className="button primary" disabled={busy || vocabularyPending || !dirty || !reason.trim() || !canEdit} onClick={() => save()}>保存新修订</button>
                  {retry && <button className="button" disabled={busy || !canEdit} onClick={() => save(true)}>重试原保存命令</button>}
                  <button className="button" disabled={busy} onClick={() => void execute(async signal => {
                    const next = await client.draft(state.draft.draftId, signal);
                    if (hasUnsaved) {
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
          </div>
        </section>
        <section className={`g2-panel g2-stack g2-inspector ${tab !== "inspect" ? "g2-mobile-hidden" : ""}`} aria-label="结构与验证">
          {state ? (
            <>
              <EntityProperties projection={state.draft.projection} selected={selected} />
              {state.draft.projection.diagnostics.map((diagnostic, index) => (
                <p className="g2-notice" key={index}>{diagnostic.code} · {diagnostic.message}</p>
              ))}
              <StructuralForm
                key={`structure/${state.draft.draftId}/${state.draft.revision}`}
                projection={state.draft.projection} selected={selected}
                blocked={busy || dirty || vocabularyPending || !canEdit || !reason.trim() || !profile?.capabilities.some(item => item.edit === "BASIC")}
                onEdit={edit => void execute(async signal => {
                  const previousRevision = state.draft.revision;
                  const next = await client.editDraft(state.draft.draftId, { edit, command: command(previousRevision, reason) }, signal);
                  accept(next);
                  setNotice(`结构编辑已由服务端保存为新修订 revision ${next.revision}；正在读取真实 Diff。`);
                  const diff = await client.diff(next.draftId, previousRevision, signal);
                  if (signal.aborted) return;
                  if (diff.targetRevision === next.revision && diff.targetHashes.bundleHash === next.hashes.bundleHash) {
                    setStructuralDiff(diff);
                    setNotice(`结构编辑已由服务端保存为新修订 revision ${next.revision}，已展示真实源码 Diff。`);
                  } else setNotice("结构编辑已保存；远端 Diff 已对应其他修订，请在版本比较中读取固定修订。");
                })}
              />
              {structuralDiff && (
                <section className="g2-stack" aria-label="结构编辑 Diff">
                  <h3>本次结构编辑源码 Diff</h3>
                  <p>revision {structuralDiff.baseRevision} → {structuralDiff.targetRevision}</p>
                  <pre className="g2-pre">{structuralDiff.sourceDiff}</pre>
                </section>
              )}
              <AssessmentPanel
                key={`assessment/${state.draft.draftId}/${state.draft.revision}`}
                draft={state.draft} profile={profile} dirty={hasUnsaved} busy={busy} canEdit={canEdit}
                reason={reason} execute={execute} onNotice={setNotice}
                onLocate={(nextField, focus) => {
                  setVocabularyMode(false);
                  setField(nextField);
                  setSelected(focus ?? "");
                  setCenterView("source");
                  setTab("source");
                  setNotice("已选择当前 hash 对应源码；未知行列保持 UNKNOWN。请依据 focusNode / path / sourceShape 查看原文。");
                }}
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
          <ReleasedVocabulary />
          <SupportProfile profile={profile} loading={profileLoading} failed={profileFailed} onRefresh={() => {
            const signal = lifetime.current?.signal;
            if (signal) void loadProfile(signal);
          }} />
        </section>
      </div>
    </div>
  );
}
