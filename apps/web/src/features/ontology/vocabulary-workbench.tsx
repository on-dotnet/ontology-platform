"use client";
import { useEffect, useState } from "react";
import { createG2Client } from "../../lib/api/g2-client";
import type { OntologyDraft, SemanticSupportProfile, RdfTerm, SourceBundle, VocabularyChange, VocabularyEditSource, VocabularySnapshot, VocabularySourceTriple } from "../../lib/api/g2-generated";
import { SemanticError } from "../../components/ui/semantic-feedback";
import { DiagnosticCard } from "./diagnostic-card";
import { rdfType, owl, rdfs, langString } from "./structural-edit";
import { editAvailability } from "./workspace-state";
import { predicates, resourceTypes, releaseProfile, semantic, skos, snapshotMatches, termText, vocabularyChange, vocabularyDirectory, xsd } from "./vocabulary-model";

const client = createG2Client();
const named = (value: string): RdfTerm => ({ kind: "iri", value, datatype: null, language: null });
const iriValid = (value: string) => /^[A-Za-z][A-Za-z0-9+.-]*:[^<>"{}|^`\\\s]+$/.test(value);
const sourceNames: Record<string, string> = { ontology: "本体", vocabulary: "术语", shapes: "约束", data: "实例" };

/** 真实四源快照的目录、字段和引用；同名、多值和未知字段均不合并丢弃。 */
export function VocabularyReadView({ snapshot, selected, onSelect }: {
  snapshot: VocabularySnapshot; selected: string; onSelect: (iri: string) => void;
}) {
  const [search, setSearch] = useState("");
  const directory = vocabularyDirectory(snapshot, search);
  const rows = snapshot.triples.filter(row => row.triple.subject.kind === "iri" && row.triple.subject.value === selected);
  const references = snapshot.triples.filter(row => row.triple.object.kind === "iri" && row.triple.object.value === selected);
  return <section className="g2-stack" aria-label="术语单位目录与详情">
    <h3>术语与 Synthetic 单位</h3>
    <p className="muted">原始标准、版本、IRI 与来源随四源 RDF 保存。精度和身份不确定保持 UNKNOWN；不提供通用单位换算。</p>
    <dl className="g2-detail">
      <div><dt>{snapshot.releaseId ? "固定正式 Release" : "草稿"}</dt><dd>{snapshot.releaseId ?? snapshot.draftId} · revision {snapshot.revision}</dd></div>
      {snapshot.releaseId && <div><dt>不可变 manifest</dt><dd>{snapshot.manifestHash ?? "UNKNOWN"}</dd></div>}
      <div><dt>语义 profile</dt><dd>{releaseProfile(snapshot)}</dd></div>
      {Object.entries(snapshot.hashes).map(([name, hash]) => <div key={name}><dt>{name}</dt><dd>{hash ?? "absent / UNKNOWN"}</dd></div>)}
    </dl>
    <label>目录搜索（名称 / 别名 / 编码 / IRI）<input aria-label="词汇目录搜索" value={search} onChange={event => setSearch(event.target.value)} /></label>
    {directory.length === 0 ? <p role="status">尚无匹配词汇。创建或载入已保存的四源 RDF 后刷新。</p> : <ul className="g2-node-list" aria-label="词汇目录">
      {directory.map(item => <li key={item.iri}><button className="g3-entity-button" aria-pressed={item.iri === selected} onClick={() => onSelect(item.iri)}>
        <strong>{item.labels.length ? item.labels.map(row => row.triple.object.value).join(" / ") : item.iri}</strong>
        <small>{item.iri}</small><span>{item.deprecated ? "已废弃 · 历史保留" : "显式登记"} · {Array.from(new Set(item.rows.map(row => sourceNames[row.sourceId] ?? row.sourceId))).join(" / ")}</span>
      </button></li>)}
    </ul>}
    {selected ? <section className="g2-stack" aria-label="选中词汇详情">
      <h4>词汇身份与原始字段</h4><p className="g2-hash">{selected}</p>
      {rows.length === 0 && <p>当前快照没有此 IRI 的声明 · UNKNOWN。可在批次内创建，或选择已登记资源。</p>}
      <dl className="g2-detail">{rows.map((row, index) => <div key={index}>
        <dt>{predicates.find(item => item.iri === row.triple.predicate)?.label ?? "原始 RDF 字段"} · {sourceNames[row.sourceId] ?? row.sourceId}</dt>
        <dd>{row.triple.predicate}</dd><dd>{termText(row.triple.object)}</dd>
        {row.triple.object.kind === "iri" && <button className="text-button" onClick={() => onSelect(row.triple.object.value)}>查看引用 {row.triple.object.value}</button>}
      </div>)}</dl>
      <p className="muted">未声明的版本、精度、来源与量纲均为 UNKNOWN；多个值全部保留，由真实评估判断冲突。</p>
      <h4>引用位置（全部四源的显式事实）</h4>
      {references.length === 0 ? <p>当前四源没有指向此 IRI 的显式引用。</p> : references.map((row, index) => <article className="g2-notice" key={index}>
        <p>{sourceNames[row.sourceId] ?? row.sourceId} · 行 / 列 UNKNOWN</p>
        <p className="g2-hash">{termText(row.triple.subject)} → {row.triple.predicate}</p>
        <button className="text-button" onClick={() => onSelect(row.triple.subject.value)}>查看引用资源</button>
      </article>)}
    </section> : <p>选择术语、术语集、单位版本、量类型、七维量纲、标准来源或属性单位绑定。</p>}
  </section>;
}

/** 单批最多64项；旧值和源不可脱离服务快照，排队后仍需明确提交。 */
export function VocabularyEditForm({ snapshot, selected, blocked, onCommit, onPending, busy = false }: {
  snapshot: VocabularySnapshot; selected: string; blocked: string | null; onCommit: (changes: VocabularyChange[]) => void;
  onPending?: (pending: boolean) => void;
  busy?: boolean;
}) {
  const [source, setSource] = useState<VocabularyEditSource>("vocabulary");
  const [subject, setSubject] = useState(selected);
  const [predicate, setPredicate] = useState(skos + "prefLabel");
  const [kind, setKind] = useState<"iri" | "literal">("literal");
  const [value, setValue] = useState("");
  const [language, setLanguage] = useState("zh");
  const [datatype, setDatatype] = useState("");
  const [resourceType, setResourceType] = useState(resourceTypes[0].iri);
  const [queue, setQueue] = useState<VocabularyChange[]>([]);
  const [editing, setEditing] = useState<VocabularySourceTriple | null>(null);
  const [message, setMessage] = useState("");
  const subjectIri = subject || selected;
  const rows = snapshot.triples.filter(row => row.triple.subject.value === selected);
  useEffect(() => { onPending?.(queue.length > 0); }, [queue.length, onPending]);
  const disabled = Boolean(blocked);

  function stage(change: VocabularyChange | null) {
    if (disabled) return;
    if (!change) { setMessage("该事实只读：源不支持结构写入或含空白节点。请使用原始源码保留语义。"); return; }
    if (queue.length >= 64) { setMessage("批次上限为64项，请先提交当前批次。"); return; }
    if (queue.some(item => item.sourceId === change.sourceId && item.edit.subjectIri === change.edit.subjectIri
      && item.edit.predicateIri === change.edit.predicateIri && JSON.stringify(item.edit.oldObject) === JSON.stringify(change.edit.oldObject)
      && JSON.stringify(item.edit.newObject) === JSON.stringify(change.edit.newObject))) {
      setMessage("此精确变更已在批次中。"); return;
    }
    setQueue(items => [...items, change]);
    setEditing(null);
    setMessage("已加入待提交批次；尚未改变服务端 RDF。");
  }

  function addField() {
    const iri = editing?.triple.subject.value ?? subjectIri.trim();
    if (!iriValid(iri) || !iriValid(predicate) || (kind === "iri" && !iriValid(value.trim()))
      || (datatype && !iriValid(datatype)) || (language && datatype && datatype !== langString)) {
      setMessage("请填写绝对 IRI。语言字面量不能同时指定其它 datatype；合法语言与语义由服务端裁决。"); return;
    }
    const next: RdfTerm = { kind, value: kind === "iri" ? value.trim() : value, language: kind === "literal" ? language || null : null,
      datatype: kind === "literal" ? datatype || null : null };
    stage(editing ? vocabularyChange(editing, next) : { sourceId: source, edit: { subjectIri: iri, predicateIri: predicate, oldObject: null, newObject: next } });
  }

  return <section className="g2-stack" aria-label="词汇精确批量编辑">
    <h3>创建 / 编辑 / 废弃</h3>
    {blocked && <p role="status" className="g2-notice">{blocked}</p>}
    <p className="muted">表单只排队显式事实。创建单位需完整登记版本、量类型、量纲、符号、精度、标准来源及 Synthetic；量纲需七项整数指数。真实治理评估决定发布资格。</p>
    <label>写入源<select aria-label="词汇写入源" value={source} disabled={disabled || Boolean(editing)} onChange={event => setSource(event.target.value as VocabularyEditSource)}>
      <option value="vocabulary">术语 vocabulary</option><option value="ontology">本体 ontology</option>
    </select></label>
    <label>资源身份 IRI<input aria-label="词汇资源IRI" value={subjectIri} disabled={disabled || Boolean(editing)} onChange={event => setSubject(event.target.value)} /></label>
    <button className="text-button" disabled={disabled || !selected} onClick={() => { setSubject(selected); setEditing(null); }}>使用选中IRI填写表单</button>
    <label>新资源类型<select aria-label="词汇新资源类型" value={resourceType} disabled={disabled} onChange={event => setResourceType(event.target.value)}>
      {resourceTypes.map(type => <option key={type.iri} value={type.iri}>{type.label}</option>)}
    </select></label>
    <button className="button" disabled={disabled || !iriValid(subjectIri.trim())} onClick={() => stage({ sourceId: source,
      edit: { subjectIri: subjectIri.trim(), predicateIri: rdfType, oldObject: null, newObject: named(resourceType) } })}>排队登记资源类型</button>
    <label>语义字段<select aria-label="词汇语义字段" value={predicate} disabled={disabled || Boolean(editing)} onChange={event => {
      const next = event.target.value;
      setPredicate(next);
      setKind(predicates.find(item => item.iri === next)?.kind === "iri" ? "iri" : "literal");
      setLanguage([skos + "prefLabel", skos + "altLabel", skos + "hiddenLabel", skos + "definition", rdfs + "label"].includes(next) ? "zh" : "");
      setDatatype(next.endsWith("Exponent") ? xsd + "integer" : [owl + "deprecated", semantic + "synthetic"].includes(next) ? xsd + "boolean" : "");
    }}>{predicates.map(item => <option key={item.iri} value={item.iri}>{item.label}</option>)}</select></label>
    {editing && !predicates.some(item => item.iri === predicate) && <p className="g2-hash">原始谓词 {predicate}</p>}
    <label>RDF对象类型<select aria-label="词汇RDF类型" value={kind} disabled={disabled} onChange={event => setKind(event.target.value as "iri" | "literal")}><option value="literal">literal 字面量</option><option value="iri">IRI 引用</option></select></label>
    <label>RDF值<textarea aria-label="词汇RDF值" value={value} disabled={disabled} rows={2} onChange={event => setValue(event.target.value)} /></label>
    {kind === "literal" && <><label>RDF语言（如 zh / en / zh-Hans；无语言保持空）<input aria-label="词汇RDF语言" value={language} disabled={disabled} onChange={event => setLanguage(event.target.value)} /></label>
      <label>RDF datatype IRI<input aria-label="词汇RDF数据类型" value={datatype} disabled={disabled} onChange={event => setDatatype(event.target.value)} /></label></>}
    <div className="g2-row"><button className="button" disabled={disabled} onClick={addField}>{editing ? "排队精确替换" : "排队添加字段"}</button>
      {editing && <button className="button" onClick={() => setEditing(null)}>取消替换</button>}
      <button className="button" disabled={disabled || !selected} onClick={() => {
        setSubject(selected);
        const old = rows.filter(row => row.sourceId === source && row.triple.predicate === owl + "deprecated");
        const next: RdfTerm = { kind: "literal", value: "true", language: null, datatype: xsd + "boolean" };
        stage(old.length === 1 ? vocabularyChange(old[0], next) : { sourceId: source, edit: { subjectIri: selected, predicateIri: owl + "deprecated", oldObject: null, newObject: next } });
      }}>排队废弃选中IRI</button>
    </div>
    <details><summary>精确替换 / 删除已保存字段（{rows.length}项）</summary><div className="g2-stack">{rows.map((row, index) => {
      const editable = !disabled && Boolean(vocabularyChange(row, null)) && predicates.some(item => item.iri === row.triple.predicate);
      return <article className="g2-notice" key={index}><p className="g2-hash">{row.sourceId} · {row.triple.predicate} · {termText(row.triple.object)}</p>
        <div className="g2-row"><button className="button" disabled={!editable} onClick={() => {
          setEditing(row); setSource(row.sourceId as VocabularyEditSource); setSubject(row.triple.subject.value); setPredicate(row.triple.predicate);
          setKind(row.triple.object.kind === "iri" ? "iri" : "literal"); setValue(row.triple.object.value); setLanguage(row.triple.object.language ?? ""); setDatatype(row.triple.object.datatype ?? "");
        }}>编辑字段 {index + 1}</button><button className="button" disabled={!editable} onClick={() => stage(vocabularyChange(row, null))}>排队删除字段 {index + 1}</button></div>
      </article>;
    })}</div></details>
    {message && <p role="status">{message}</p>}
    <h4>待提交批次 {queue.length} / 64</h4>
    {queue.map((change, index) => <article className="g2-notice" key={index}>
      <p className="g2-hash">{change.sourceId} · {change.edit.subjectIri} · {change.edit.predicateIri}</p>
      <p>{change.edit.oldObject ? termText(change.edit.oldObject) : "新增"} → {change.edit.newObject ? termText(change.edit.newObject) : "删除"}</p>
      <button className="text-button" disabled={busy} onClick={() => setQueue(items => items.filter((_, row) => row !== index))}>移除此变更 {index + 1}</button>
    </article>)}
    <div className="g2-row"><button className="button primary" disabled={disabled || queue.length === 0} onClick={() => onCommit(queue)}>批量原子提交</button>
      <button className="button" disabled={busy || queue.length === 0} onClick={() => { setQueue([]); setMessage("已取消待提交批次，服务端草稿未改变。"); }}>取消待提交批次</button></div>
    <p className="muted">四源 hash + revision CAS；不丢弃未知 RDF。提交后需重新评估，再经发布工作区异人审批。</p>
  </section>;
}

/** 快照读取可取消且严格匹配当前四源修订；保存后由父工作区统一接受新草稿。 */
export function VocabularyWorkbench({ draft, selected, onSelect, dirty, busy, canEdit, reason, onCommit, onLocate, onPending, pending, profile }: {
  draft: OntologyDraft; selected: string; onSelect: (iri: string) => void; dirty: boolean; busy: boolean; canEdit: boolean; reason: string;
  onCommit: (changes: VocabularyChange[], snapshot: VocabularySnapshot) => void;
  onLocate: (field: keyof SourceBundle, focus: string | null) => void;
  onPending: (pending: boolean) => void;
  pending: boolean;
  profile: SemanticSupportProfile | null;
}) {
  const [load, setLoad] = useState<{ snapshot: VocabularySnapshot | null; error: unknown; loading: boolean }>({ snapshot: null, error: null, loading: true });
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    client.vocabulary(draft.draftId, controller.signal).then(snapshot => {
      if (controller.signal.aborted) return;
      if (!snapshotMatches(snapshot, draft)) throw new Error("词汇快照与当前草稿四源 revision/hash 不符，请刷新远端草稿。");
      setLoad({ snapshot, error: null, loading: false });
    }).catch(error => { if (!controller.signal.aborted) setLoad({ snapshot: null, error, loading: false }); });
    return () => controller.abort();
  }, [draft, refresh]);
  const snapshot = load.snapshot && snapshotMatches(load.snapshot, draft) ? load.snapshot : null;
  const blocked = editAvailability({ canEdit, busy, dirty, failed: load.error !== null })
    ?? (snapshot && (!profile || snapshot.profileVersion !== profile.version || snapshot.profileHash !== profile.hash
      || !profile.capabilities.some(item => ["21", "22"].includes(item.id) && item.edit === "BASIC")) ? "词汇编辑能力 UNKNOWN，请刷新当前语义档案"
    : !draft.projection.structuralEditAllowed ? "原始图包含未支持结构；请保留源码编辑" : !reason.trim() ? "请先填写变更理由" : !snapshot ? "正在等待当前修订词汇快照" : null);
  return <section className="g2-stack" aria-label="术语与单位工作区">
    <div className="g2-row"><h2>术语 / 标准 / 单位量纲</h2><button className="button" disabled={busy || pending} onClick={() => setRefresh(value => value + 1)}>刷新词汇快照</button></div>
    {load.error !== null && <SemanticError error={load.error} />}
    {!snapshot ? <p role="status">{load.loading ? "正在读取真实四源词汇快照…" : "快照不可用；源码仍保留，请刷新重试。"}</p> : <>
      {dirty && <p className="g2-notice">当前源码未保存，以下快照对应已保存修订；结构编辑已暂停。</p>}
      <VocabularyReadView snapshot={snapshot} selected={selected} onSelect={onSelect} />
      <VocabularyEditForm key={`${draft.draftId}/${draft.revision}`} snapshot={snapshot} selected={selected} blocked={blocked} onPending={onPending} busy={busy} onCommit={changes => onCommit(changes, snapshot)} />
      <h3>词汇治理诊断</h3>
      {snapshot.diagnostics.length === 0 ? <p>快照暂无词汇诊断。发布资格仍须运行完整真实评估。</p> : snapshot.diagnostics.map((item, index) => <DiagnosticCard key={index} item={item} draft={draft} dirty={dirty} index={index} onLocate={onLocate} />)}
      <p><a href="/releases">前往发布与异人审批</a> · 历史差异使用右侧版本比较。</p>
    </>}
  </section>;
}
