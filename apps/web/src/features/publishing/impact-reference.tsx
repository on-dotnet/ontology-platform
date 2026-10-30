"use client";
import { useEffect, useRef, useState } from "react";
import type { ImpactApprovalBinding, ImpactReport, ResourceScope } from "../../lib/api/g2-generated";
import { createG2Client } from "../../lib/api/g2-client";
import { SemanticError } from "../../components/ui/semantic-feedback";
import { impactBindingMatches, impactBindingWellFormed, impactReportMatches } from "../ontology/impact-model";
import { ImpactBindingView, ImpactReportView } from "../ontology/impact-report-view";

const client = createG2Client();
type Props = { binding: ImpactApprovalBinding | null | undefined; assetId: string; scope: ResourceScope; auto?: boolean;
  onLoaded?: (report: ImpactReport | null) => void };
async function readOriginal(binding: ImpactApprovalBinding, assetId: string, scope: ResourceScope, signal: AbortSignal) {
  if (!impactBindingWellFormed(binding)) throw new Error("impact_response_mismatch");
  const result = await client.impactReport(binding.reportId, signal);
  if (!impactReportMatches(result, { from: binding.from, to: binding.to, baselineKind: binding.baselineKind }, { assetId, scope })
    || !impactBindingMatches(binding, result)) throw new Error("impact_binding_conflict");
  return result;
}
function BoundImpactReference({ binding, assetId, scope, auto = false, onLoaded }: Props) {
  const [report, setReport] = useState<ImpactReport | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [loading, setLoading] = useState(auto);
  const request = useRef<AbortController | null>(null);
  useEffect(() => {
    if (!auto || !binding || !impactBindingWellFormed(binding)) return;
    const controller = new AbortController(); request.current = controller;
    readOriginal(binding, assetId, scope, controller.signal).then(result => {
      if (!controller.signal.aborted && request.current === controller) { setReport(result); setLoading(false); onLoaded?.(result); }
    }).catch(cause => {
      if (!controller.signal.aborted && request.current === controller) { setError(cause); setLoading(false); onLoaded?.(null); }
    });
    return () => { controller.abort(); if (request.current === controller) request.current = null; };
  }, [binding, assetId, scope, auto, onLoaded]);
  useEffect(() => {
    return () => request.current?.abort();
  }, []);
  async function read() {
    if (!binding || !impactBindingWellFormed(binding)) return;
    request.current?.abort();
    const controller = new AbortController(); request.current = controller;
    setReport(null); setError(null); setLoading(true); onLoaded?.(null);
    try {
      const result = await readOriginal(binding, assetId, scope, controller.signal);
      if (!controller.signal.aborted && request.current === controller) { setReport(result); onLoaded?.(result); }
    } catch (cause) { if (!controller.signal.aborted && request.current === controller) { setError(cause); onLoaded?.(null); } }
    finally { if (!controller.signal.aborted && request.current === controller) setLoading(false); }
  }
  if (!binding) return <p className="g2-notice">历史版本没有影响报告绑定，保持历史事实；新发布提案必须重建，不影响原版本回滚。</p>;
  if (!impactBindingWellFormed(binding)) return <p className="g2-notice">UNKNOWN · 冻结影响绑定字段不完整，禁止以此进行新发布。</p>;
  return <section className="g2-stack" aria-label="原影响报告追溯">
    <ImpactBindingView binding={binding} />
    <button className="button" disabled={loading} onClick={() => void read()}>读取原影响报告</button>
    {loading && <p role="status">正在核验原持久影响报告与冻结绑定…</p>}
    {error !== null && <SemanticError error={error} />}
    {report && <ImpactReportView report={report} />}
  </section>;
}

/** 绑定改变时销毁旧请求与报告，历史正式版本始终读取原报告ID和hash。 */
export function ImpactReference(props: Props) {
  return <BoundImpactReference key={JSON.stringify({ binding: props.binding, assetId: props.assetId, scope: props.scope })} {...props} />;
}
