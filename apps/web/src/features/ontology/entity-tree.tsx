"use client";
import type { KeyboardEvent } from "react";
import type { SemanticProjection } from "../../lib/api/g2-generated";

const groups = [
  { kind: "class", title: "类" }, { kind: "objectProperty", title: "对象属性" },
  { kind: "datatypeProperty", title: "数据属性" }, { kind: "individual", title: "个体" },
];

/** 原生details与button提供键盘后备；只呈现服务投影，不从树重建RDF。 */
export function EntityTree({ projection, selected, onSelect }: {
  projection: SemanticProjection; selected: string; onSelect: (iri: string) => void;
}) {
  /** 方向键沿可见实体循环，Enter/Space沿用原生button选择语义。 */
  function navigate(event: KeyboardEvent<HTMLElement>) {
    if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
    const buttons = [...event.currentTarget.querySelectorAll<HTMLButtonElement>("details[open] button")];
    const current = buttons.indexOf(event.target as HTMLButtonElement);
    if (current < 0 || buttons.length === 0) return;
    event.preventDefault();
    const next = event.key === "Home" ? 0 : event.key === "End" ? buttons.length - 1
      : (current + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) % buttons.length;
    buttons[next].focus();
  }

  return (
    <section className="g2-stack g3-entity-tree" aria-label="本体实体树" onKeyDown={navigate}>
      <h2>本体实体</h2>
      <p className="muted">revision {projection.revision} · 方向键移动，Enter 选择</p>
      {groups.map(group => {
        const nodes = projection.nodes.filter(node => node.kind === group.kind);
        return (
          <details open key={group.kind}>
            <summary>{group.title} · {nodes.length}</summary>
            <ul className="g2-node-list" aria-label={group.title}>
              {nodes.map(node => (
                <li key={node.id}>
                  <button className="g3-entity-button" aria-pressed={selected === node.id} title={node.id}
                    onClick={() => onSelect(node.id)}>{node.label || node.id}</button>
                  <small className="g2-hash">{node.id}</small>
                </li>
              ))}
              {nodes.length === 0 && <li className="muted">暂无{group.title}</li>}
            </ul>
          </details>
        );
      })}
    </section>
  );
}

/** 属性检查器保留当前对象词法和语言/datatype，结构操作复用精确命令。 */
export function EntityProperties({ projection, selected }: { projection: SemanticProjection; selected: string }) {
  const node = projection.nodes.find(item => item.id === selected);
  const triples = projection.triples.filter(item => item.subject.kind === "iri" && item.subject.value === selected);
  return (
    <section className="g2-stack" aria-label="所选实体属性">
      <h2>所选实体属性</h2>
      {node ? (
        <>
          <strong>{node.label || node.id}</strong>
          <p className="g2-hash">{node.id}</p>
          <p className="muted">{node.kind} · {triples.length} 条已确认三元组</p>
          <dl className="g2-detail">
            {triples.map((item, index) => (
              <div key={index}>
                <dt>{item.predicate}</dt>
                <dd>{item.object.value}</dd>
                <dd>{item.object.kind} · datatype {item.object.datatype ?? "无"} · language {item.object.language ?? "无"}</dd>
              </div>
            ))}
          </dl>
        </>
      ) : <p className="muted">在左侧实体树或图中选择节点，查看当前修订属性。</p>}
    </section>
  );
}
