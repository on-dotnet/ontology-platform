"use client";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { SemanticProjection } from "../../lib/api/g2-generated";
/** 主题订阅仅观察已存在的Design Tokens切换，不建立第二套主题状态。 */
function subscribeTheme(listener: () => void) { const observer = new MutationObserver(listener); observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] }); return () => observer.disconnect(); }
/** Cytoscape只消费服务端RDF投影；位置和布局不写回语义修订。 */
export default function SemanticGraph({ projection, stale, onSelect }: { projection: SemanticProjection; stale: boolean; onSelect: (iri: string) => void }) {
  const container = useRef<HTMLDivElement>(null);
  const theme = useSyncExternalStore(subscribeTheme, () => document.documentElement.dataset.theme ?? "dark", () => "dark");
  const [failure, setFailure] = useState(false);
  const [layout, setLayout] = useState(0);
  useEffect(() => {
    let disposed = false;
    let destroy: (() => void) | undefined;
    import("cytoscape").then(({ default: cytoscape }) => {
      if (disposed || !container.current) return;
      const style = getComputedStyle(document.documentElement);
      const graph = cytoscape({ container: container.current, elements: [...projection.nodes.map(node => ({ data: { id: node.id, label: node.label || node.id, kind: node.kind } })), ...projection.edges.filter(edge => projection.nodes.some(node => node.id === edge.source) && projection.nodes.some(node => node.id === edge.target)).map(edge => ({ data: { id: edge.id, source: edge.source, target: edge.target, label: edge.label } }))], style: [{ selector: "node", style: { "background-color": style.getPropertyValue("--primary").trim(), label: "data(label)", color: style.getPropertyValue("--text").trim(), "font-size": 11, "text-wrap": "ellipsis", "text-max-width": "110px" } }, { selector: "edge", style: { width: 1.5, "line-color": style.getPropertyValue("--teal").trim(), "target-arrow-color": style.getPropertyValue("--teal").trim(), "target-arrow-shape": "triangle", "curve-style": "bezier" } }], layout: { name: "cose", animate: false }, wheelSensitivity: 0.2 });
      graph.on("tap", "node", event => onSelect(String(event.target.id())));
      destroy = () => graph.destroy();
    }).catch(() => { if (!disposed) setFailure(true); });
    return () => { disposed = true; destroy?.(); };
  }, [projection, layout, onSelect, theme]);
  return <section><div className="g2-row"><h3>RDF 结构投影</h3><button className="button" onClick={() => setLayout(value => value + 1)}>重新布局</button></div><p className="muted">revision {projection.revision} · {projection.nodes.length} 节点 / {projection.edges.length} 关系</p>{stale && <p className="g2-notice">本地源码未保存，下图保留上次服务器确认版本。</p>}{failure && <p role="alert">图形加载失败；下方可访问节点列表仍可使用。</p>}<div ref={container} className="g2-graph" aria-hidden="true" /><details open={failure}><summary>键盘访问节点与关系</summary><ul className="g2-node-list">{projection.nodes.map(node => <li key={node.id}><button className="text-button" onClick={() => onSelect(node.id)}>{node.label || node.id}</button><small>{node.kind}</small></li>)}</ul><ul>{projection.edges.map(edge => <li key={edge.id}>{edge.source} → {edge.predicateIri} → {edge.target}</li>)}</ul></details></section>;
}
