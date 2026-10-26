"use client";
import { useState } from "react";
import type { SemanticEdit, SemanticProjection, RdfTermKind } from "../../lib/api/g2-generated";
const rdfType = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
const rdfs = "http://www.w3.org/2000/01/rdf-schema#";
const standardPredicates = [{ iri: rdfType, title: "rdf:type" }, ...["subClassOf", "domain", "range", "label", "comment"].map(name => ({ iri: rdfs + name, title: `rdfs:${name}` }))];
/** 只发送精确新增/替换/删除三元组意图；完整RDF修改及支持子集由服务器处理。 */
export function StructuralForm({ projection, selected, blocked, onEdit }: { projection: SemanticProjection; selected: string; blocked: boolean; onEdit: (edit: SemanticEdit) => void }) {
  const [operation, setOperation] = useState("replace");
  const [tripleIndex, setTripleIndex] = useState("0");
  const [subject, setSubject] = useState("");
  const [predicate, setPredicate] = useState(rdfType);
  const [kind, setKind] = useState<RdfTermKind>("iri");
  const [value, setValue] = useState("");
  const [datatype, setDatatype] = useState("");
  const [language, setLanguage] = useState("");
  const triples = projection.triples.filter(triple => triple.subject.kind === "iri" && triple.object.kind !== "blank" && (!selected || triple.subject.value === selected));
  const triple = triples[Number(tripleIndex)];
  const predicates = [...standardPredicates, ...projection.nodes.filter(node => node.kind === "objectProperty" || node.kind === "datatypeProperty").map(node => ({ iri: node.id, title: node.label || node.id }))];
  const allowed = !blocked && projection.structuralEditAllowed && (operation === "add" ? Boolean(subject.trim() && predicate.trim() && value.trim()) : Boolean(triple && (operation === "remove" || value.trim()))) && !(kind === "literal" && datatype && language);
  /** 明确旧对象以便CAS精确删除；不从投影拼接/重建整个SourceBundle。 */
  function submit() {
    if (!allowed) return;
    onEdit({ subjectIri: operation === "add" ? subject.trim() : triple.subject.value, predicateIri: operation === "add" ? predicate : triple.predicate, oldObject: operation === "add" ? null : triple.object, newObject: operation === "remove" ? null : { kind, value, datatype: kind === "literal" ? datatype.trim() || null : null, language: kind === "literal" ? language.trim() || null : null } });
  }
  return <section className="g2-stack"><h3>结构表单</h3><p className="g2-hash">{selected || "选择图节点或具体三元组"}</p>{!projection.structuralEditAllowed && <p className="g2-notice">存在未知/复杂公理或空白节点；结构编辑已阻断，原始源完整保留。</p>}<label>结构操作<select aria-label="结构操作" value={operation} onChange={event => setOperation(event.target.value)} disabled={blocked}><option value="replace">替换精确对象</option><option value="add">新增标准声明 / 简单断言</option><option value="remove">删除精确三元组</option></select></label>
    {operation === "add" ? <><label>主体 IRI<input aria-label="主体IRI" value={subject} onChange={event => setSubject(event.target.value)} disabled={blocked} /></label><label>谓词<select aria-label="结构谓词" value={predicate} onChange={event => setPredicate(event.target.value)} disabled={blocked}>{predicates.map(item => <option key={item.iri} value={item.iri}>{item.title}</option>)}</select></label><label>标准声明快捷填入<select aria-label="标准声明快捷填入" defaultValue="" disabled={blocked} onChange={event => { if (event.target.value) { setPredicate(rdfType); setKind("iri"); setValue(event.target.value); } }}><option value="">选择类型声明（可选）</option>{["Class", "ObjectProperty", "DatatypeProperty", "NamedIndividual"].map(name => <option key={name} value={`http://www.w3.org/2002/07/owl#${name}`}>owl:{name}</option>)}</select></label></> : <label>已确认三元组<select aria-label="结构编辑三元组" value={tripleIndex} onChange={event => { setTripleIndex(event.target.value); const next = triples[Number(event.target.value)]; if (next) { setKind(next.object.kind); setValue(next.object.value); setDatatype(next.object.datatype ?? ""); setLanguage(next.object.language ?? ""); } }} disabled={blocked}>{triples.map((item, index) => <option key={index} value={index}>{item.subject.value} · {item.predicate} → {item.object.value}</option>)}</select></label>}
    {operation !== "remove" && <><label>新对象类型<select aria-label="新对象类型" value={kind} onChange={event => setKind(event.target.value as RdfTermKind)} disabled={blocked}><option value="iri">IRI</option><option value="literal">literal</option></select></label><label>新对象值<input aria-label="新对象值" value={value} onChange={event => setValue(event.target.value)} disabled={blocked} /></label>{kind === "literal" && <><label>datatype IRI<input aria-label="字面量datatypeIRI" value={datatype} onChange={event => { setDatatype(event.target.value); if (event.target.value) setLanguage(""); }} disabled={blocked} /></label><label>language<input aria-label="字面量language" value={language} onChange={event => { setLanguage(event.target.value); if (event.target.value) setDatatype(""); }} disabled={blocked} /></label></>}</>}
    <button className="button" disabled={!allowed} onClick={submit}>提交真实结构编辑</button><p className="muted">仅支持登记的RDF/OWL基本编辑。旧修订源码完整保留，结构修改的新格式通过Diff明示。</p></section>;
}
