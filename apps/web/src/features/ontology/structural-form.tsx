"use client";
import { useState } from "react";
import type { SemanticEdit, SemanticProjection, RdfTerm } from "../../lib/api/g2-generated";
import { exactEdit, namedAxiomCandidates, namedAxioms, owl, rdfType, rdfs, structuralContext } from "./structural-edit";

const standardPredicates = [
  { iri: rdfType, title: "rdf:type" },
  ...["subClassOf", "domain", "range", "label", "comment"].map(name => ({ iri: rdfs + name, title: `rdfs:${name}` })),
  ...["equivalentClass", "disjointWith", "inverseOf"].map(name => ({ iri: owl + name, title: `owl:${name}` })),
];
const emptyObject: RdfTerm = { kind: "iri", value: "", datatype: null, language: null };
type Props = { projection: SemanticProjection; selected: string; blocked: boolean; onEdit: (edit: SemanticEdit) => void };

/** 实例键覆盖revision、hash和节点，切换上下文时销毁旧表单状态。 */
export function StructuralForm(props: Props) {
  const context = structuralContext(props.projection, props.selected);
  return <BoundStructuralForm key={JSON.stringify(context)} {...props} />;
}

/** 仅发送精确三元组意图；结构只读时保留完整源码保存与原文导出入口。 */
function BoundStructuralForm({ projection, selected, blocked, onEdit }: Props) {
  const triples = projection.triples.filter(triple => triple.subject.kind === "iri" && triple.object.kind !== "blank"
    && (!selected || triple.subject.value === selected));
  const [operation, setOperation] = useState<"add" | "replace" | "remove">("replace");
  const [tripleIndex, setTripleIndex] = useState("0");
  const [subject, setSubject] = useState(selected);
  const [predicate, setPredicate] = useState(rdfType);
  const [object, setObject] = useState<RdfTerm>(() => ({ ...(triples[0]?.object ?? emptyObject) }));
  const triple = triples[Number(tripleIndex)];
  const activePredicate = operation === "add" ? predicate : triple?.predicate ?? predicate;
  const controlled = namedAxioms.includes(activePredicate);
  const candidates = namedAxiomCandidates(projection, activePredicate);
  const disabled = blocked || !projection.structuralEditAllowed;
  const predicates = [...standardPredicates, ...projection.nodes.filter(node => node.kind === "objectProperty"
    || node.kind === "datatypeProperty").map(node => ({ iri: node.id, title: node.label || node.id }))];
  const edit = exactEdit(projection, structuralContext(projection, selected), { operation, subject, predicate, triple, object });

  /** 改谓词时清除旧对象，受控公理必须重新明确选择正确类型的两端。 */
  function changePredicate(next: string) {
    setPredicate(next);
    setObject({ ...emptyObject, kind: next === rdfs + "label" || next === rdfs + "comment" ? "literal" : "iri" });
  }

  return (
    <section className="g2-stack" aria-label="精确结构编辑">
      <h3>结构表单</h3>
      <p className="g2-hash">{selected || "选择图节点或具体三元组"}</p>
      {!projection.structuralEditAllowed && (
        <p className="g2-notice">存在未知/复杂公理或空白节点；结构只读。源码保存和原文导出仍可使用。</p>
      )}
      <label>结构操作
        <select aria-label="结构操作" value={operation} disabled={disabled} onChange={event => {
          setOperation(event.target.value as typeof operation);
          setSubject(selected);
          setObject({ ...(event.target.value === "add" ? emptyObject : triple?.object ?? emptyObject) });
        }}>
          <option value="replace">替换精确对象</option>
          <option value="add">新增标准声明 / 简单断言</option>
          <option value="remove">删除精确三元组</option>
        </select>
      </label>
      {operation === "add" ? (
        <>
          <label>主体 IRI
            {controlled ? (
              <select aria-label="主体IRI" value={subject} disabled={disabled} onChange={event => setSubject(event.target.value)}>
                <option value="">选择显式声明主体</option>
                {candidates.map(iri => <option key={iri} value={iri}>{iri}</option>)}
              </select>
            ) : <input aria-label="主体IRI" value={subject} disabled={disabled} onChange={event => setSubject(event.target.value)} />}
          </label>
          <label>谓词
            <select aria-label="结构谓词" value={predicate} disabled={disabled} onChange={event => changePredicate(event.target.value)}>
              {predicates.map(item => <option key={item.iri} value={item.iri}>{item.title}</option>)}
            </select>
          </label>
          <label>标准声明快捷填入
            <select aria-label="标准声明快捷填入" value="" disabled={disabled} onChange={event => {
              if (!event.target.value) return;
              setPredicate(rdfType);
              setObject({ ...emptyObject, value: event.target.value });
            }}>
              <option value="">选择类型声明（可选）</option>
              {["Class", "ObjectProperty", "DatatypeProperty", "NamedIndividual"].map(name => (
                <option key={name} value={owl + name}>owl:{name}</option>
              ))}
            </select>
          </label>
        </>
      ) : (
        <label>已确认三元组
          <select aria-label="结构编辑三元组" value={tripleIndex} disabled={disabled} onChange={event => {
            setTripleIndex(event.target.value);
            setObject({ ...(triples[Number(event.target.value)]?.object ?? emptyObject) });
          }}>
            {triples.map((item, index) => (
              <option key={index} value={index}>{item.subject.value} · {item.predicate} → {item.object.value}</option>
            ))}
          </select>
        </label>
      )}
      {operation !== "remove" && (
        <>
          <label>新对象类型
            <select aria-label="新对象类型" value={object.kind} disabled={disabled || controlled} onChange={event => {
              setObject({ ...emptyObject, kind: event.target.value as "iri" | "literal" });
            }}>
              <option value="iri">IRI</option>
              <option value="literal">literal</option>
            </select>
          </label>
          <label>新对象值
            {controlled ? (
              <select aria-label="新对象值" value={object.value} disabled={disabled} onChange={event => {
                setObject({ ...emptyObject, value: event.target.value });
              }}>
                <option value="">选择显式声明对象</option>
                {candidates.map(iri => <option key={iri} value={iri}>{iri}</option>)}
              </select>
            ) : <input aria-label="新对象值" value={object.value} disabled={disabled}
              onChange={event => setObject({ ...object, value: event.target.value })} />}
          </label>
          {object.kind === "literal" && (
            <>
              <label>datatype IRI
                <input aria-label="字面量datatypeIRI" value={object.datatype ?? ""} disabled={disabled} onChange={event => {
                  setObject({ ...object, datatype: event.target.value || null, language: null });
                }} />
              </label>
              <label>language
                <input aria-label="字面量language" value={object.language ?? ""} disabled={disabled} onChange={event => {
                  setObject({ ...object, language: event.target.value || null, datatype: null });
                }} />
              </label>
            </>
          )}
        </>
      )}
      <button className="button" disabled={disabled || !edit} onClick={() => { if (!disabled && edit) onEdit(edit); }}>
        提交真实结构编辑
      </button>
      <details>
        <summary>简单命名公理与语义说明</summary>
        <ul>{standardPredicates.map(item => <li key={item.iri}>{item.title} · {item.iri}</li>)}</ul>
        <p>equivalentClass / disjointWith 两端须显式为 Class，inverseOf 两端须显式为 ObjectProperty。</p>
        <p>domain/range 不是必填约束；多个 domain 不是任选其一。prefix / BASE 继续在源码中编辑。</p>
      </details>
      <p className="muted">旧修订源码完整保留，结构修改的新格式通过 Diff 明示；服务端最终核验类型和完整原图。</p>
    </section>
  );
}
