"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import type * as G4 from "../../lib/api/g4-generated";
import type { ReleaseSummary, VocabularySnapshot } from "../../lib/api/g2-generated";
import { command, createG2Client } from "../../lib/api/g2-client";
import { createConnectionsClient } from "../connections/api";
import { createMappingsClient, MappingApiError } from "./api";
import { mappingLabels, parseDefinition, useMappingWork, adoptCandidates } from "./model";
import { MappingError, MappingJobPanel, MappingNavigation } from "./assessment";
import { MappingReleaseHistory } from "./releases";
import "./mappings.css";
const client = createMappingsClient();
const connections = createConnectionsClient();
const semantic = createG2Client();
const emptyDefinition: G4.MappingDefinition = { entities: [], properties: [], relations: [], identitySpecs: [], temporalSpecs: [], conversions: [], unitSpecs: [] };

/** 映射列表只显示当前授权对象，分页失败不保留冒充新鲜的旧页。 */
export function MappingList() {
  const [page, setPage] = useState<G4.MappingPageOfMappingListItem | null>(null);
  const work = useMappingWork(() => setPage(null));
  useEffect(() => {
    const controller = new AbortController(); const generation = work.generation();
    client.list(undefined, controller.signal).then(result => { if (!controller.signal.aborted && work.current(generation)) setPage(result.data); })
      .catch(cause => { if (!controller.signal.aborted && work.current(generation)) work.fail(cause); });
    return () => controller.abort();
    // 初次GET只运行于本挂载；重试由显式按钮负责。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return <div className="mapping-workspace"><MappingNavigation /><header className="mapping-heading"><div><h1>源到本体映射</h1><p>固定正式词汇、验证业务语义、经独立审核后发布。</p></div><Link className="mapping-primary" href="/data/mappings/new">新建映射</Link></header>
    <MappingError error={work.error} retry={work.recoverable ? work.retry : undefined} />
    {!page && !work.error && <p role="status">正在读取当前可见映射…</p>}{page && <section className="mapping-card">{page.items.length === 0 ? <p>本页没有当前可见映射。可新建映射，或继续读取下一页。</p> : <div className="mapping-scroll" tabIndex={0}><table><thead><tr><th>映射</th><th>厂区</th><th>修订</th><th>草稿状态</th><th>当前发布</th></tr></thead><tbody>{page.items.map(item => <tr key={item.mappingId}><td><Link href={`/data/mappings/${encodeURIComponent(item.mappingId)}`}>{item.mappingId}</Link></td><td>{item.scope.siteIds.join("、")}</td><td>{item.revision}</td><td>{mappingLabels[item.status]}</td><td>{item.activeReleaseId ? <Link href={`/data/mapping-releases/${encodeURIComponent(item.activeReleaseId)}`}>读取发布</Link> : "尚未激活"}</td></tr>)}</tbody></table></div>}
      <div className="mapping-actions"><button disabled={work.busy} onClick={() => void work.run(() => client.list(), result => setPage(result.data))}>从首页刷新</button>{page.nextCursor && <button disabled={work.busy} onClick={() => void work.run(() => client.list(page.nextCursor!), result => setPage(result.data))}>下一页</button>}</div></section>}
  </div>;
}

/** U07显式选择真实固定目录和G3正式发布，人工确认绑定，不自动猜测字段。 */
export function MappingCreate({ canEdit, initialSnapshot }: { canEdit: boolean; initialSnapshot?: string }) {
  const router = useRouter();
  const [sources, setSources] = useState<G4.ConnectionView[]>([]);
  const [releases, setReleases] = useState<ReleaseSummary[]>([]);
  const [catalogs, setCatalogs] = useState<G4.CatalogSnapshotView[]>([]);
  const [snapshot, setSnapshot] = useState<G4.CatalogSnapshotView | null>(null);
  const [release, setRelease] = useState<ReleaseSummary | null>(null);
  const [vocabulary, setVocabulary] = useState<VocabularySnapshot | null>(null);
  const [connectionId, setConnectionId] = useState("");
  const [sites, setSites] = useState<string[]>([]);
  const [text, setText] = useState(JSON.stringify(emptyDefinition, null, 2));
  const [reason, setReason] = useState("");
  const work = useMappingWork(() => { setSources([]); setReleases([]); setCatalogs([]); setSnapshot(null); setRelease(null); setVocabulary(null); setText(""); setReason(""); });
  useEffect(() => {
    const controller = new AbortController(); const generation = work.generation();
    void Promise.all([connections.list("type=POSTGRESQL", controller.signal), semantic.releases(controller.signal), initialSnapshot ? connections.catalog(initialSnapshot, controller.signal) : Promise.resolve(null)])
      .then(([available, formal, selected]) => {
        if (controller.signal.aborted || !work.current(generation)) return;
        setSources(available.data.items.filter(item => item.config.type === "POSTGRESQL" && item.state === "ACTIVE"));
        setReleases(formal.filter(item => item.manifest.schemaVersion === 2));
        if (selected) { setSnapshot(selected.data); setCatalogs([selected.data]); setConnectionId(selected.data.connectionId); setSites(selected.data.scope.siteIds); }
      }).catch(cause => { if (!controller.signal.aborted && work.current(generation)) work.fail(cause); });
    return () => controller.abort();
    // 初始固定快照只从URL读取，不在刷新时创建新资源。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialSnapshot]);
  function chooseSource(id: string) {
    setConnectionId(id); setSnapshot(null); setText(JSON.stringify(emptyDefinition, null, 2));
    void work.run(() => connections.catalogs(id), result => setCatalogs(result.data.items));
  }
  function chooseRelease(id: string) {
    const selected = releases.find(item => item.manifest.releaseId === id) ?? null;
    setRelease(selected); setVocabulary(null);
    if (selected) void work.run(() => semantic.releasedVocabulary(id), setVocabulary);
  }
  function create() {
    if (!snapshot || !release || !sites.length || !reason.trim()) return;
    try {
      const body: G4.MappingDraftCreateRequest = { scope: { organizationId: snapshot.scope.organizationId, siteIds: sites },
        sourceConnectionId: snapshot.connectionId, sourceCatalogSnapshotId: snapshot.snapshotId, ontologyReleaseId: release.manifest.releaseId,
        ontologyManifestHash: release.manifestHash, mapping: parseDefinition(text), command: command(0, reason.trim()) };
      void work.run(() => client.create(body), result => router.push(`/data/mappings/${encodeURIComponent(result.data.mappingId)}`));
    } catch (cause) { work.fail(cause); }
  }
  return <div className="mapping-workspace"><MappingNavigation /><h1>创建人工映射</h1><MappingError error={work.error} retry={work.recoverable ? work.retry : undefined} />
    {!canEdit ? <p role="alert">当前角色不能创建映射。</p> : !work.denied && <>
      <section className="mapping-card"><h2>1. 固定来源和正式本体</h2><div className="mapping-grid"><label>已启用的 PostgreSQL 连接<select disabled={work.busy} value={connectionId} onChange={event => chooseSource(event.target.value)}><option value="">请选择</option>{sources.map(item => <option key={item.id} value={item.id}>{item.displayName}</option>)}</select></label>
        <label>完整目录快照<select disabled={work.busy} value={snapshot?.snapshotId ?? ""} onChange={event => { const item = catalogs.find(value => value.snapshotId === event.target.value) ?? null; setSnapshot(item); setSites(item?.scope.siteIds ?? []); }}><option value="">请选择</option>{catalogs.filter(item => item.status === "READY").map(item => <option key={item.snapshotId} value={item.snapshotId}>{item.capturedAtUtc} · 修订 {item.configRevision}</option>)}</select></label>
        <label>G3 正式发布<select disabled={work.busy} value={release?.manifest.releaseId ?? ""} onChange={event => chooseRelease(event.target.value)}><option value="">请选择</option>{releases.map(item => <option key={item.manifest.releaseId} value={item.manifest.releaseId}>{item.manifest.assetId} · {item.manifest.releaseId}</option>)}</select></label></div>
        {snapshot && <fieldset><legend>完整映射厂区</legend>{snapshot.scope.siteIds.map(site => <label className="mapping-check" key={site}><input type="checkbox" checked={sites.includes(site)} onChange={event => setSites(event.target.checked ? [...sites, site] : sites.filter(value => value !== site))} />{site}</label>)}<p>目录指纹：{snapshot.schemaFingerprint}</p></fieldset>}
        {release && <p className="mapping-hash">正式制品散列：{release.manifestHash}</p>}
      </section>
      {snapshot && vocabulary && <EntityBuilder snapshot={snapshot} vocabulary={vocabulary} accept={mapping => setText(JSON.stringify(mapping, null, 2))} />}
      <section className="mapping-card"><h2>2. 逐项确认映射定义</h2><p>实体、属性、关系、身份、时间和单位均须显式声明。可用上方字段选择器建立实体，再编辑完整定义；保存不代表验证通过。</p><label>完整映射定义<textarea className="mapping-source" spellCheck={false} rows={18} value={text} onChange={event => setText(event.target.value)} /></label><label>创建理由<input value={reason} maxLength={500} onChange={event => setReason(event.target.value)} /></label><button disabled={work.busy || !snapshot || !release || !sites.length || !reason.trim()} onClick={create}>保存第一修订</button></section>
    </>}
  </div>;
}

/** 字段选择只取固定目录，类IRI只取已回验G3正式词汇，不依据名称自动推断。 */
function EntityBuilder({ snapshot, vocabulary, accept }: { snapshot: G4.CatalogSnapshotView; vocabulary: VocabularySnapshot; accept: (value: G4.MappingDefinition) => void }) {
  const [tableId, setTableId] = useState(""); const [classIri, setClassIri] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [namespace, setNamespace] = useState("");
  const table = snapshot.objects.find(item => `${item.schema}.${item.name}` === tableId);
  const roles = [["organization", "组织字段"], ["site", "厂区字段"], ["key", "外部业务键"], ["from", "有效起点"], ["to", "有效终点"], ["event", "事件时间"], ["observed", "观察时间"]];
  const classes = [...new Set(vocabulary.triples.filter(item => item.triple.predicate === "http://www.w3.org/1999/02/22-rdf-syntax-ns#type" && item.triple.object.value === "http://www.w3.org/2002/07/owl#Class").map(item => item.triple.subject.value))];
  function build() {
    if (!table || !classIri || !namespace.trim() || roles.some(([role]) => !fields[role])) return;
    const dataset: G4.MappingDatasetRef = { snapshotId: snapshot.snapshotId, schema: table.schema, name: table.name, kind: "TABLE" };
    const ref = (role: string): G4.MappingFieldRef => { const field = table.fields.find(item => item.name === fields[role])!; return { datasetRef: dataset, name: field.name, ordinal: field.ordinal }; };
    accept({ entities: [{ id: "entity", entityClassIri: classIri, datasetRef: dataset, identitySpecId: "identity", temporalSpecId: "time", scopeFields: { organization: ref("organization"), site: ref("site") } }],
      identitySpecs: [{ id: "identity", organizationFieldRef: ref("organization"), siteFieldRef: ref("site"), sourceNamespace: namespace.trim(), externalIdFieldRefs: [ref("key")], validFromFieldRef: ref("from"), validToFieldRef: ref("to") }],
      temporalSpecs: [{ id: "time", eventTimeFieldRef: ref("event"), observedAtFieldRef: ref("observed"), validFromFieldRef: ref("from"), validToFieldRef: ref("to"), timezonePolicy: { kind: "UTC", zoneId: null }, precision: "MICROSECOND" }],
      properties: [], relations: [], unitSpecs: [], conversions: [] });
  }
  return <section className="mapping-card"><h2>实体绑定选择器</h2><div className="mapping-grid"><label>源表<select value={tableId} onChange={event => { setTableId(event.target.value); setFields({}); }}><option value="">请选择</option>{snapshot.objects.filter(item => item.kind === "TABLE" && item.fields.length <= 12).map(item => <option key={`${item.schema}.${item.name}`} value={`${item.schema}.${item.name}`}>{item.schema}.{item.name}</option>)}</select></label><label>正式类<select value={classIri} onChange={event => setClassIri(event.target.value)}><option value="">请选择</option>{classes.map(iri => <option key={iri} value={iri}>{iri}</option>)}</select></label><label>来源命名空间<input value={namespace} onChange={event => setNamespace(event.target.value)} /></label>
    {table && roles.map(([role, label]) => <label key={role}>{label}<select value={fields[role] ?? ""} onChange={event => setFields(current => ({ ...current, [role]: event.target.value }))}><option value="">明确选择字段</option>{table.fields.map(field => <option key={field.ordinal} value={field.name}>{field.name} · {field.nativeType}</option>)}</select></label>)}</div><p>时间策略：UTC、微秒精度；有效期采用半开区间。无时区源须在定义中显式改用已登记区域。</p><button disabled={!table || !classIri || !namespace.trim() || roles.some(([role]) => !fields[role])} onClick={build}>将明确选择写入待保存定义</button></section>;
}

/** 编辑冲突保留本页未保存文本，读取新头不会静默覆盖用户内容。 */
export function MappingEditor({ id, canEdit }: { id: string; canEdit: boolean }) {
  const params = useSearchParams(); const router = useRouter();
  const [draft, setDraft] = useState<G4.MappingDraftView | null>(null); const [etag, setEtag] = useState("");
  const [text, setText] = useState(""); const [reason, setReason] = useState("");
  const [server, setServer] = useState<G4.MappingDraftView | null>(null);
  const [reports, setReports] = useState<G4.MappingPageOfMappingAssessmentView | null>(null);
  const [suggestions, setSuggestions] = useState<G4.MappingSuggestionView | null>(null);
  const [selected, setSelected] = useState<number[]>([]);
  const work = useMappingWork(() => { setDraft(null); setServer(null); setText(""); setReason(""); setReports(null); setEtag(""); setSuggestions(null); setSelected([]); });
  useEffect(() => {
    const controller = new AbortController(); const generation = work.generation();
    client.draft(id, controller.signal).then(async result => {
      if (controller.signal.aborted || !work.current(generation)) return;
      setDraft(result.data); setText(JSON.stringify(result.data.mapping, null, 2)); setEtag(result.etag);
      const history = await client.assessments(id, result.data.revision, undefined, undefined, controller.signal);
      if (!controller.signal.aborted && work.current(generation)) setReports(history.data);
    }).catch(cause => { if (!controller.signal.aborted && work.current(generation)) work.fail(cause); });
    return () => controller.abort();
    // 固定mapping切换重新加载，普通重渲染不覆盖未保存文本。
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);
  function save() {
    if (!draft || !reason.trim()) return;
    try { const body = { mapping: parseDefinition(text), command: command(draft.revision, reason.trim()) };
      void work.run(() => client.patch(id, body, etag), result => { setDraft(result.data); setEtag(result.etag); setText(JSON.stringify(result.data.mapping, null, 2)); setServer(null); setReports(null); setSuggestions(null); setSelected([]); });
    } catch (cause) { work.fail(cause); }
  }
  function validate() {
    if (!draft) return;
    const body: G4.MappingValidateRequest = { target: { kind: "PUBLISH", draftRevision: draft.revision }, command: command(draft.revision, "验证固定映射修订") };
    void work.run(() => client.validate(id, body, etag), result => router.replace(`/data/mappings/${encodeURIComponent(id)}?job=${encodeURIComponent(result.data.jobId)}`));
  }
  function suggest() {
    if (!draft) return;
    const body: G4.MappingSuggestionRequest = { mode: "OFF", command: command(draft.revision, "读取固定词汇的确定性候选") };
    void work.run(() => client.suggest(id, body, etag), result => { setSuggestions(result.data); setSelected([]); });
  }
  function adopt() {
    if (!draft || !suggestions || suggestions.revision !== draft.revision) return;
    try { setText(JSON.stringify(adoptCandidates(parseDefinition(text), selected.map(index => suggestions.candidates[index])), null, 2)); setSelected([]); }
    catch (cause) { work.fail(cause); }
  }
  const dirty = !!draft && text !== JSON.stringify(draft.mapping, null, 2);
  return <div className="mapping-workspace"><MappingNavigation /><h1>映射编辑与验证</h1><MappingError error={work.error} retry={work.recoverable ? work.retry : undefined} />
    {!draft && !work.error && <p role="status">正在读取固定映射与当前权限…</p>}{draft && <>
      <section className="mapping-card"><div className="mapping-heading"><h2>修订 {draft.revision} · {mappingLabels[draft.status]}</h2><span className="tag">{dirty ? "本页有未保存内容" : "已保存"}</span></div><p>厂区：{draft.scope.siteIds.join("、")} · 正式本体：{draft.ontologyReleaseId}</p><label>完整映射定义<textarea className="mapping-source" rows={20} spellCheck={false} readOnly={!canEdit} value={text} onChange={event => setText(event.target.value)} /></label>
        {canEdit && <><label>修改理由<input value={reason} maxLength={500} onChange={event => setReason(event.target.value)} /></label><div className="mapping-actions"><button disabled={work.busy || !dirty || !reason.trim()} onClick={save}>保存新修订</button><button disabled={work.busy || dirty} onClick={validate}>验证已保存修订</button></div></>}
        <button disabled={work.busy} onClick={() => void work.run(() => client.draft(id), result => setServer(result.data))}>读取当前版本供比较</button>
        {server && <aside className="mapping-alert"><h3>服务器当前修订 {server.revision}</h3><pre>{JSON.stringify(server.mapping, null, 2)}</pre><button disabled={work.busy} onClick={() => { setDraft(server); setEtag(`"mapping:${server.revision}"`); setServer(null); }}>以此修订重新保存本页内容</button><button onClick={() => { setDraft(server); setText(JSON.stringify(server.mapping, null, 2)); setEtag(`"mapping:${server.revision}"`); setServer(null); }}>明确采用服务器内容</button></aside>}
      </section>
      {canEdit && <section className="mapping-card"><h2>确定性规则候选 · AI OFF</h2><p>仅使用固定目录和正式词汇。没有实样证据的候选不代表验证通过；采纳后还需保存、七项验证和独立审核。</p>
        <button disabled={work.busy || dirty} onClick={suggest}>读取规则候选</button>
        {suggestions && <><p>依据修订 {suggestions.revision} · 规则 mapping-candidate-rules-v1</p>{!suggestions.candidates.length && <p>没有匹配的规则候选。</p>}
          <ul>{suggestions.candidates.map((candidate, index) => <li key={`${candidate.fieldRef.name}:${candidate.targetIri}`}><label className="mapping-check"><input type="checkbox" disabled={work.busy || dirty || candidate.evidence !== "METADATA" || suggestions.revision !== draft.revision} checked={selected.includes(index)} onChange={event => setSelected(current => event.target.checked ? [...current, index] : current.filter(value => value !== index))} />{candidate.fieldRef.datasetRef.name}.{candidate.fieldRef.name} → {candidate.targetIri}</label><p>证据：{candidate.evidence} · 仅候选 · {candidate.evidence === "METADATA" ? "同名、唯一、直接标量；可明确勾选采纳" : "高风险或词义匹配，待逐项人工编辑，不能批量采纳"}</p></li>)}</ul>
          <button disabled={work.busy || dirty || selected.length === 0 || suggestions.revision !== draft.revision} onClick={adopt}>将勾选低风险候选写入待保存定义</button></>}
      </section>}
      {params.get("job") && <MappingJobPanel key={params.get("job")!} jobId={params.get("job")!} mappingId={id} canEdit={canEdit} onDenied={() => work.fail(new MappingApiError(403, "mapping_forbidden"))} />}
      {reports && <section className="mapping-card"><h2>本修订评估历史</h2>{!reports.items.length && <p>尚无评估报告。</p>}<ul>{reports.items.map(report => <li key={report.assessmentId}><Link href={`/data/mappings/${encodeURIComponent(id)}/assessments/${encodeURIComponent(report.assessmentId)}`}>{report.finishedAtUtc} · {mappingLabels[report.status]}</Link></li>)}</ul>{reports.nextCursor && <button disabled={work.busy} onClick={() => void work.run(() => client.assessments(id, draft.revision, undefined, reports.nextCursor!), result => setReports(result.data))}>下一页报告</button>}</section>}
      <MappingReleaseHistory mappingId={id} onDenied={() => work.fail(new MappingApiError(403, "mapping_forbidden"))} />
    </>}
  </div>;
}
