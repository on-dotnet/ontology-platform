"use client";
import { useState } from "react";
import { PlatformApiError } from "../../lib/api/client";
/** 只显示安全状态与关联标识，远端detail和异常原文不进入页面。 */
export function SemanticError({ error }: { error: unknown }) {
  const status = error instanceof PlatformApiError ? error.status : 0;
  const titles: Record<number, string> = { 401: "会话已失效，请重新登录", 403: "当前角色或完整厂区范围无权访问", 404: "资源不存在", 409: "版本冲突：本地未保存文本仍保留", 422: "源码、参数或支持子集未通过校验", 428: "请求缺少版本条件", 429: "已达到预算，请稍后重试", 503: "依赖暂时不可用，未返回成功结果" };
  return <div className="g2-notice error" role="alert"><strong>{titles[status] ?? "请求未完成，请检查连接并显式重试"}</strong>{status > 0 && <span> HTTP {status}</span>}{error instanceof PlatformApiError && error.traceId && <Trace traceId={error.traceId} />}{status === 401 && <a href="/auth/login?returnUrl=/ontologies" className="button">重新登录</a>}</div>;
}
/** 仅将非零32位十六进制TraceId编码为本地Tempo查询，不接受URL或额外查询参数。 */
function tempoTraceUrl(traceId: string): string | null {
  if (traceId.length !== 32 || !/^[0-9a-f]{32}$/i.test(traceId) || /^0{32}$/.test(traceId)) return null;
  const url = new URL("http://localhost:15330/explore");
  url.searchParams.set("schemaVersion", "1");
  url.searchParams.set("orgId", "1");
  url.searchParams.set("panes", JSON.stringify({
    trace: {
      datasource: "platform-tempo",
      queries: [{
        refId: "A",
        datasource: { uid: "platform-tempo", type: "tempo" },
        queryType: "traceql",
        query: traceId.toLowerCase(),
      }],
      range: { from: "now-24h", to: "now" },
    },
  }));
  return url.toString();
}

/** 关联标识来自实际响应；定位本地Grafana中的对应Trace，复制失败时保留手动恢复提示。 */
export function Trace({ traceId }: { traceId: string }) {
  const [copyStatus, setCopyStatus] = useState("");
  const traceUrl = tempoTraceUrl(traceId);
  /** 浏览器拒绝剪贴板时显示可恢复提示，不产生未处理Promise错误。 */
  async function copy() { try { await navigator.clipboard.writeText(traceId); setCopyStatus("已复制关联标识"); } catch { setCopyStatus("复制不可用，请手动选择上方标识"); } }
  return <span className="g2-trace">Trace <code>{traceId}</code> <button className="text-button" onClick={() => void copy()}>复制关联标识</button> {traceUrl ? <a href={traceUrl} target="_blank" rel="noreferrer">在本地 Grafana 定位此 Trace</a> : <small>关联标识格式无效，无法定位链路</small>}{copyStatus && <small role="status">{copyStatus}</small>}</span>;
}
