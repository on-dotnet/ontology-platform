"use client";
import { useEffect, useState } from "react";
import type {
  OntologyDraft, SemanticSupportProfile, SourceBundle, VocabularyChange, VocabularyEditSource, VocabularySnapshot,
} from "../../lib/api/g2-generated";
import { createG2Client } from "../../lib/api/g2-client";
import { SemanticError } from "../../components/ui/semantic-feedback";
import { DiagnosticCard } from "./diagnostic-card";
import { editAvailability } from "./workspace-state";
import { releaseProfile, semantic, snapshotMatches, termText } from "./vocabulary-model";
import {
  claimChanges, closeClaimChanges, eventChanges, identityDirectory, identityFields, identityTypes, time,
  type ClaimInput, type EventInput,
} from "./identity-time-model";
import { rdfType } from "./structural-edit";

const client = createG2Client();
const initialClaim = (siteId: string): ClaimInput => ({
  iri: "", siteId, sourceNamespace: "", externalIdentifier: "", targetIri: "", declarationSource: "", from: "", to: "",
});
const initialEvent: EventInput = { iri: "", timeIri: "", kind: "point", from: "", to: "", observed: "" };
const sourceLabels: Record<string, string> = { ontology: "本体", vocabulary: "术语", shapes: "约束", data: "实例" };

/** 真实四源的身份与时间目录逐IRI显示；所有多值、历史来源和未知端点保持可见。 */
export function IdentityTimeReadView({ snapshot, selected, onSelect }: {
  snapshot: VocabularySnapshot; selected: string; onSelect: (iri: string) => void;
}) {
  const [search, setSearch] = useState("");
  const directory = identityDirectory(snapshot, search);
  const rows = snapshot.triples.filter(row => row.triple.subject.kind === "iri" && row.triple.subject.value === selected);
  const references = snapshot.triples.filter(row => row.triple.object.kind === "iri" && row.triple.object.value === selected);
  return <section className="g2-stack" aria-label="身份时间目录与详情">
    <h3>显式身份与时间事实</h3>
    <p className="muted">同编号、同标签不自动合并。有效期采用 [from,to)；未知端点保持 UNKNOWN，不能当作永远有效。</p>
    <dl className="g2-detail">
      <div><dt>{snapshot.releaseId ? "固定正式 Release" : "草稿修订"}</dt>
        <dd>{snapshot.releaseId ?? snapshot.draftId} · revision {snapshot.revision}</dd></div>
      {snapshot.releaseId && <div><dt>不可变 manifest</dt><dd>{snapshot.manifestHash ?? "UNKNOWN"}</dd></div>}
      <div><dt>语义 profile</dt><dd>{releaseProfile(snapshot)}</dd></div>
      <div><dt>四源 bundle hash</dt><dd>{snapshot.hashes.bundleHash}</dd></div>
    </dl>
    <label>搜索身份编号 / 来源 / 时间 / IRI
      <input aria-label="身份时间目录搜索" value={search} onChange={event => setSearch(event.target.value)} />
    </label>
    {directory.length === 0 ? <p role="status">尚无匹配的显式身份或受控时间声明。</p> : <ul className="g2-node-list" aria-label="身份时间目录">
      {directory.map(item => <li key={item.iri}>
        <button className="g3-entity-button" aria-pressed={selected === item.iri} onClick={() => onSelect(item.iri)}>
          <strong>{item.rows.filter(row => row.triple.predicate === semantic + "externalIdentifier")
            .map(row => row.triple.object.value).join(" / ") || item.iri}</strong>
          <small>{item.iri}</small>
          <span>{item.rows.filter(row => row.triple.predicate === rdfType)
            .map(row => identityTypes.find(type => type.iri === row.triple.object.value)?.label ?? row.triple.object.value).join(" / ")}</span>
        </button>
      </li>)}
    </ul>}
    {selected && <section className="g2-stack" aria-label="选中身份时间事实">
      <h4>原始事实与真实来源</h4><p className="g2-hash">{selected}</p>
      {rows.length === 0 && <p>此IRI在当前四源没有声明，状态 UNKNOWN。</p>}
      <dl className="g2-detail">{rows.map((row, index) => <div key={index}>
        <dt>{identityFields[row.triple.predicate] ?? "原始RDF字段"} · {sourceLabels[row.sourceId] ?? row.sourceId}</dt>
        <dd>{row.triple.predicate}</dd><dd>{termText(row.triple.object)}</dd>
        {row.triple.object.kind === "iri" && <button className="text-button" onClick={() => onSelect(row.triple.object.value)}>查看时间或目标引用</button>}
      </div>)}</dl>
      {rows.some(row => row.triple.predicate === rdfType && row.triple.object.value === time + "Interval") && <p>
        起点 {rows.some(row => row.triple.predicate === time + "hasBeginning") ? "已引用（含）" : "UNKNOWN"} ·
        终点 {rows.some(row => row.triple.predicate === time + "hasEnd") ? "已引用（不含）" : "UNKNOWN"}
      </p>}
      <h4>四源显式引用位置</h4>
      {references.length === 0 ? <p>当前四源没有指向此IRI的显式引用；这不等于已证明没有其它影响。</p>
        : references.map((row, index) => <article className="g2-notice" key={index}>
          <p>{sourceLabels[row.sourceId] ?? row.sourceId} · 行 / 列 UNKNOWN</p>
          <p className="g2-hash">{termText(row.triple.subject)} → {row.triple.predicate}</p>
          <button className="text-button" onClick={() => onSelect(row.triple.subject.value)}>查看引用声明</button>
        </article>)}
    </section>}
  </section>;
}

/** 受控表单只排队有限精确批次；历史身份不提供覆写或删除入口。 */
export function IdentityTimeEditForm({ draft, snapshot, blocked, busy, onCommit, onPending }: {
  draft: OntologyDraft; snapshot: VocabularySnapshot; blocked: string | null; busy: boolean;
  onCommit: (changes: VocabularyChange[]) => void; onPending: (pending: boolean) => void;
}) {
  const [source, setSource] = useState<VocabularyEditSource>("ontology");
  const [claim, setClaim] = useState(() => initialClaim(draft.scope.siteIds[0] ?? ""));
  const [event, setEvent] = useState<EventInput>({ ...initialEvent });
  const [closing, setClosing] = useState({ iri: "", to: "" });
  const [queue, setQueue] = useState<VocabularyChange[]>([]);
  const [message, setMessage] = useState("");
  const claims = identityDirectory(snapshot).filter(item => item.rows.some(row => row.triple.predicate === rdfType
    && row.triple.object.value === semantic + "IdentityClaim"));
  const targets = [...new Set(snapshot.triples.filter(row => row.triple.subject.kind === "iri" && row.triple.predicate === rdfType)
    .map(row => row.triple.subject.value))];
  const formPending = Object.entries(claim).some(([key, value]) => key !== "siteId" && value !== "")
    || Object.entries(event).some(([key, value]) => key !== "kind" && value !== "") || Boolean(closing.to);
  useEffect(() => onPending(formPending || queue.length > 0), [formPending, queue.length, onPending]);
  const setClaimField = (key: keyof ClaimInput, value: string) => { setClaim(current => ({ ...current, [key]: value })); };
  const setEventField = (key: keyof EventInput, value: string) => { setEvent(current => ({ ...current, [key]: value })); };
  function stage(build: () => VocabularyChange[], clear: () => void) {
    if (blocked) return;
    try {
      const changes = build();
      if (queue.length + changes.length > 64) throw new Error("单次最多64项精确变更，请先提交或取消当前批次。");
      if (changes.some(change => queue.some(old => old.edit.subjectIri === change.edit.subjectIri)))
        throw new Error("当前批次已经包含相同资源，请先提交，避免凭旧快照重复修改。");
      setQueue(current => [...current, ...changes]);
      clear(); setMessage("已排队，尚未写入服务器；请明确原子提交。");
    } catch (cause) { setMessage(cause instanceof Error ? cause.message : "无法构造受控批次。"); }
  }
  return <section className="g2-stack" aria-label="身份时间受控编辑">
    <h3>受控身份与时间编辑</h3>
    {blocked && <p role="status" className="g2-notice">{blocked}</p>}
    <p className="muted">所有时间填写带 Z 或 ±hh:mm 的 ISO 时间戳，例如 2026-01-01T08:00:00+08:00。空值表示未知，不采用本机时区。</p>
    <fieldset className="g3-identity-form" disabled={Boolean(blocked)}>
      <legend>写入目标</legend>
      <label>身份时间写入源<select aria-label="身份时间写入源" value={source} onChange={value => setSource(value.target.value as VocabularyEditSource)}>
        <option value="ontology">本体 ontology</option><option value="vocabulary">术语 vocabulary</option>
      </select></label>
    </fieldset>
    <form className="g2-stack" onSubmit={value => {
      value.preventDefault(); stage(() => claimChanges(snapshot, draft.scope, source, claim), () => setClaim(initialClaim(draft.scope.siteIds[0] ?? "")));
    }}>
      <fieldset className="g3-identity-form" disabled={Boolean(blocked)}><legend>新增身份声明</legend>
        <label>声明 IRI<input aria-label="身份声明IRI" value={claim.iri} onChange={value => setClaimField("iri", value.target.value)} /></label>
        <label>组织（资产权威范围）<input aria-label="身份组织" readOnly value={draft.scope.organizationId} /></label>
        <label>厂区<select aria-label="身份厂区" value={claim.siteId} onChange={value => setClaimField("siteId", value.target.value)}>
          {draft.scope.siteIds.map(site => <option key={site} value={site}>{site}</option>)}
        </select></label>
        <label>来源命名空间<input aria-label="身份来源命名空间" value={claim.sourceNamespace}
          onChange={value => setClaimField("sourceNamespace", value.target.value)} /></label>
        <label>外部编号<input aria-label="身份外部编号" value={claim.externalIdentifier}
          onChange={value => setClaimField("externalIdentifier", value.target.value)} /></label>
        <label>目标 IRI<input aria-label="身份目标IRI" list="identity-time-targets" value={claim.targetIri}
          onChange={value => setClaimField("targetIri", value.target.value)} /></label>
        <datalist id="identity-time-targets">{targets.map(iri => <option value={iri} key={iri} />)}</datalist>
        <label>声明来源 IRI<input aria-label="身份声明来源IRI" value={claim.declarationSource}
          onChange={value => setClaimField("declarationSource", value.target.value)} /></label>
        <label>有效起点（含；空为未知）<input aria-label="身份有效起点" value={claim.from}
          onChange={value => setClaimField("from", value.target.value)} /></label>
        <label>有效终点（不含；空为未知）<input aria-label="身份有效终点" value={claim.to}
          onChange={value => setClaimField("to", value.target.value)} /></label>
        <button className="button" type="submit">排队新增身份声明</button>
      </fieldset>
    </form>
    <form className="g2-stack" onSubmit={value => {
      value.preventDefault(); stage(() => closeClaimChanges(snapshot, closing.iri, closing.to), () => setClosing({ iri: "", to: "" }));
    }}>
      <fieldset className="g3-identity-form" disabled={Boolean(blocked)}><legend>关闭 / 收窄历史有效期</legend>
        <p className="muted">保留原组织、厂区、编号、目标、来源和起点；更换身份时建立新声明。共享区间不在表单中改写。</p>
        <label>已保存身份声明<select aria-label="关闭身份声明" value={closing.iri}
          onChange={value => setClosing(current => ({ ...current, iri: value.target.value }))}>
          <option value="">请选择固定声明IRI</option>
          {claims.map(item => <option key={item.iri} value={item.iri}>{item.iri}</option>)}
        </select></label>
        <label>新的终点（不含）<input aria-label="关闭身份有效终点" value={closing.to} onChange={value => {
          setClosing(current => ({ ...current, to: value.target.value }));
        }} /></label>
        <button className="button" type="submit">排队关闭或收窄有效期</button>
      </fieldset>
    </form>
    <form className="g2-stack" onSubmit={value => {
      value.preventDefault(); stage(() => eventChanges(snapshot, source, event), () => setEvent({ ...initialEvent }));
    }}>
      <fieldset className="g3-identity-form" disabled={Boolean(blocked)}><legend>新增 / 更新事件时间</legend>
        <p className="muted">更新事件引用全新时间IRI，旧时间事实原样保留。发生时间、观察时间与资产版本时间分别记录。</p>
        <label>事件 IRI<input aria-label="事件IRI" value={event.iri} onChange={value => setEventField("iri", value.target.value)} /></label>
        <label>新的时间资源 IRI<input aria-label="事件时间资源IRI" value={event.timeIri}
          onChange={value => setEventField("timeIri", value.target.value)} /></label>
        <label>受控时间模板<select aria-label="事件时间模板" value={event.kind} onChange={value => setEventField("kind", value.target.value)}>
          <option value="point">OWL-Time 时间点</option><option value="interval">OWL-Time 半开区间</option>
        </select></label>
        <label>{event.kind === "point" ? "事件时间点（空为未知）" : "事件区间起点（含；空为未知）"}
          <input aria-label="事件时间起点" value={event.from} onChange={value => setEventField("from", value.target.value)} /></label>
        {event.kind === "interval" && <label>事件区间终点（不含；空为未知）<input aria-label="事件时间终点" value={event.to}
          onChange={value => setEventField("to", value.target.value)} /></label>}
        <label>观察时间（独立记录；空为未知）<input aria-label="事件观察时间" value={event.observed}
          onChange={value => setEventField("observed", value.target.value)} /></label>
        <button className="button" type="submit">排队保存事件时间</button>
      </fieldset>
    </form>
    {message && <p role="status">{message}</p>}
    <h4>身份时间待提交批次 {queue.length} / 64</h4>
    {queue.map((change, index) => <article className="g2-notice" key={index}>
      <p className="g2-hash">{change.sourceId} · {change.edit.subjectIri} · {change.edit.predicateIri}</p>
      <p>{change.edit.oldObject ? termText(change.edit.oldObject) : "新增"} → {change.edit.newObject ? termText(change.edit.newObject) : "删除"}</p>
    </article>)}
    <div className="g2-row">
      <button className="button primary" disabled={Boolean(blocked) || queue.length === 0} onClick={() => onCommit(queue)}>原子提交身份时间</button>
      <button className="button" disabled={busy || !formPending && queue.length === 0} onClick={() => {
        setQueue([]); setClaim(initialClaim(draft.scope.siteIds[0] ?? "")); setEvent({ ...initialEvent });
        setClosing({ iri: "", to: "" }); setMessage("已取消本地身份时间编辑，服务器未改变。");
      }}>取消身份时间编辑</button>
    </div>
  </section>;
}

/** 快照可取消并绑定完整revision/hash；真实API保存后交父工作区统一接受修订。 */
export function IdentityTimeWorkbench({ draft, selected, onSelect, dirty, busy, canEdit, reason, profile, onPending, pending, onCommit, onLocate }: {
  draft: OntologyDraft; selected: string; onSelect: (iri: string) => void; dirty: boolean; busy: boolean; canEdit: boolean; reason: string;
  profile: SemanticSupportProfile | null; onPending: (pending: boolean) => void; pending: boolean;
  onCommit: (changes: VocabularyChange[], snapshot: VocabularySnapshot) => void;
  onLocate: (field: keyof SourceBundle, focus: string | null) => void;
}) {
  const [load, setLoad] = useState<{ snapshot: VocabularySnapshot | null; error: unknown; loading: boolean }>({ snapshot: null, error: null, loading: true });
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    client.identityTime(draft.draftId, controller.signal).then(snapshot => {
      if (controller.signal.aborted) return;
      if (!snapshotMatches(snapshot, draft)) throw new Error("身份时间快照未绑定当前草稿的完整修订和四源散列，请刷新远端。");
      setLoad({ snapshot, error: null, loading: false });
    }).catch(error => { if (!controller.signal.aborted) setLoad({ snapshot: null, error, loading: false }); });
    return () => controller.abort();
  }, [draft, refresh]);
  const snapshot = load.snapshot && snapshotMatches(load.snapshot, draft) ? load.snapshot : null;
  const blocked = editAvailability({ canEdit, busy, dirty, failed: load.error !== null })
    ?? (!snapshot ? "正在等待当前修订身份时间快照" : !profile || snapshot.profileVersion !== profile.version || snapshot.profileHash !== profile.hash
      || !["20", "23"].every(id => profile.capabilities.some(item => item.id === id && item.edit === "BASIC"))
      ? "身份时间编辑能力 UNKNOWN，请刷新当前语义档案" : !draft.projection.structuralEditAllowed
        ? "原始图包含未支持结构；请保留源码编辑" : !reason.trim() ? "请先填写变更理由" : null);
  return <section className="g2-stack" aria-label="身份与时间工作区">
    <div className="g2-row"><h2>身份 / 有效期 / 事件时间</h2>
      <button className="button" disabled={busy || pending} onClick={() => setRefresh(value => value + 1)}>刷新身份时间快照</button></div>
    {load.error !== null && <SemanticError error={load.error} />}
    {!snapshot ? <p role="status">{load.loading ? "正在读取真实四源身份时间…" : "身份时间快照不可用；原始源码仍保留。"}</p> : <>
      {dirty && <p className="g2-notice">源码未保存，当前快照属于已保存修订；结构编辑已暂停。</p>}
      <IdentityTimeReadView snapshot={snapshot} selected={selected} onSelect={onSelect} />
      <IdentityTimeEditForm key={`${draft.draftId}/${draft.revision}`} draft={draft} snapshot={snapshot} blocked={blocked}
        busy={busy} onPending={onPending} onCommit={changes => onCommit(changes, snapshot)} />
      <h3>身份与时间治理诊断</h3>
      {snapshot.diagnostics.length === 0 ? <p>当前快照暂无治理诊断。发布仍需完整评估和异人审批。</p>
        : snapshot.diagnostics.map((item, index) => <DiagnosticCard key={index} item={item} draft={draft}
          dirty={dirty} index={index} onLocate={onLocate} />)}
      <p><a href="/releases">前往发布与异人审批</a> · 有界模板校验不等于通用时间推理。</p>
    </>}
  </section>;
}
