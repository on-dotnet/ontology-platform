"use client";
import { useState } from "react";
import { decodeSourceBytes } from "./source-bytes";
import type { SourceBundle } from "../../lib/api/g2-generated";
/** 四个原始权威文档；备用编辑与高级编辑器使用同一草稿接口。 */
export const sourceFields: Array<{ key: keyof SourceBundle; title: string; file: string }> = [{ key: "ontologyTurtle", title: "本体 · OWL", file: "ontology.ttl" }, { key: "shapesTurtle", title: "约束 · SHACL", file: "shapes.ttl" }, { key: "vocabularyTurtle", title: "术语 · SKOS", file: "vocabulary.ttl" }, { key: "dataTurtle", title: "事实 · Synthetic", file: "data.ttl" }];
/** 保留UTF8文本，上传和导出不经过浏览器RDF重建。 */
export function SourceEditor({ sources, field, onField, onChange, readOnly = false }: { sources: SourceBundle; field: keyof SourceBundle; onField: (field: keyof SourceBundle) => void; onChange: (field: keyof SourceBundle, value: string) => void; readOnly?: boolean }) {
  const [loadError, setLoadError] = useState("");
  const current = sourceFields.find(item => item.key === field)!;
  const value = sources[field] ?? "";
  /** 源文档直接下载；浏览器生成的临时URL在触发后释放。 */
  function download() { if (sources[field] === null) return; const url = URL.createObjectURL(new Blob([value], { type: "text/turtle;charset=utf-8" })); const link = document.createElement("a"); link.href = url; link.download = current.file; link.click(); setTimeout(() => URL.revokeObjectURL(url), 0); }
  return <section className="g2-source"><div className="g2-row"><label>源文档<select aria-label="选择源文档" value={field} onChange={event => onField(event.target.value as keyof SourceBundle)}>{sourceFields.map(item => <option key={item.key} value={item.key}>{item.title}</option>)}</select></label><button className="button" onClick={download} disabled={sources[field] === null}>导出原始源</button></div>{loadError && <p className="g2-notice error" role="alert">{loadError}</p>}{sources[field] === null && <p className="muted">可选术语源未提供（absent），不会视为空文件。</p>}<p className="g2-notice">高级编辑器 Monaco 已由人工暂停；当前使用真实原生编辑备用方案，无高级补全。</p><label className="g2-upload">载入 {current.file}（≤256 KiB）<input type="file" accept=".ttl,text/turtle,text/plain" disabled={readOnly} aria-label={`载入${current.file}`} onChange={async event => { const input = event.currentTarget; const file = input.files?.[0]; if (!file) return; setLoadError(""); if (file.size > 262144) { setLoadError("源文件超过256 KiB，未载入。"); input.value = ""; return; } try { const value = decodeSourceBytes(await file.arrayBuffer()); onChange(field, value); } catch { setLoadError("源文件不是有效UTF8或无法读取，未载入且原始缓冲保持不变。"); } finally { input.value = ""; } }} /></label><textarea className="g2-code" aria-label={`${current.title}源码`} spellCheck={false} value={value} onChange={event => onChange(field, event.target.value)} readOnly={readOnly} /><p className="muted">UTF8 原始 Turtle · {new TextEncoder().encode(value).length} 字节 · 服务端 RIOT 解析后方可保存</p></section>;
}
