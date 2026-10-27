"use client";
import type { AssessmentDiagnostic, OntologyDraft, SourceBundle } from "../../lib/api/g2-generated";
import { diagnosticLocation } from "./semantic-status";

/** 展示诊断原始证据与中文定位解释；不能可靠归属单源时保留UNKNOWN。 */
export function DiagnosticCard({ item, draft, dirty, index, onLocate }: {
  item: AssessmentDiagnostic; draft: OntologyDraft; dirty: boolean; index: number;
  onLocate?: (field: keyof SourceBundle, focus: string | null) => void;
}) {
  const location = diagnosticLocation(item, draft, dirty);
  const severity = { error: "错误", warning: "警告", info: "提示" }[item.diagnostic.severity];
  const shape = item.sourceShape;
  const explanation = item.diagnostic.code === "validation_issue" ? "SHACL 约束或支持检查返回诊断，请结合阶段与来源判断。"
    : "服务端语义诊断；源码保留，发布资格由完整 assessment 决定。";
  return (
    <article className="g2-notice" aria-label={`评估诊断${index + 1}`} data-source-current={Boolean(location)}>
      <strong>{severity} · {item.diagnostic.code}</strong>
      <p>{explanation}</p>
      <p>{item.diagnostic.message}</p>
      <p>来源 {item.sourceId} · 行 {location?.line ?? "UNKNOWN"} / 列 {location?.column ?? "UNKNOWN"}</p>
      <p className="g2-hash">source hash {item.sourceHash}</p>
      <p className="g2-hash">focusNode {item.diagnostic.focusNode?.value ?? "UNKNOWN"}</p>
      <p className="g2-hash">path {item.diagnostic.path ?? "UNKNOWN"}</p>
      <p className="g2-hash">sourceShape {shape ? `${shape.kind} · ${shape.value}` : "UNKNOWN"}</p>
      {shape?.kind === "blank" && <p>空白 shape 标识不代表稳定源码位置，行列保持 UNKNOWN。</p>}
      {shape?.kind === "iri" && <p>命名 shape 仅作来源证据；未取得源节点精确绑定时，不推测其行列。</p>}
      {location ? (
        <button className="button" disabled={!onLocate} onClick={() => onLocate?.(location.field, location.focus)}>
          定位诊断来源 {index + 1}
        </button>
      ) : <p>{dirty ? "本地文本已变化，诊断过期。" : "来源未匹配当前单源 hash，或属于合并图；不伪造源码位置。"}</p>}
    </article>
  );
}
