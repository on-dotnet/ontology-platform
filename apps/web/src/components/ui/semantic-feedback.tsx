"use client";
import { PlatformApiError } from "../../lib/api/client";
/** 只显示安全状态与关联标识，远端detail和异常原文不进入页面。 */
export function SemanticError({ error }: { error: unknown }) {
  const status = error instanceof PlatformApiError ? error.status : 0;
  const titles: Record<number, string> = { 401: "会话已失效，请重新登录", 403: "当前角色或完整厂区范围无权访问", 404: "资源不存在", 409: "版本冲突：本地未保存文本仍保留", 422: "源码、参数或支持子集未通过校验", 428: "请求缺少版本条件", 429: "已达到预算，请稍后重试", 503: "依赖暂时不可用，未返回成功结果" };
  return <div className="g2-notice error" role="alert"><strong>{titles[status] ?? "请求未完成，请检查连接并显式重试"}</strong>{status > 0 && <span> HTTP {status}</span>}{error instanceof PlatformApiError && error.traceId && <Trace traceId={error.traceId} />}{status === 401 && <a href="/auth/login?returnUrl=/ontologies" className="button">重新登录</a>}</div>;
}
/** 关联标识来自实际响应；审计入口保持服务端重新授权。 */
export function Trace({ traceId }: { traceId: string }) { return <span className="g2-trace">Trace <code>{traceId}</code> <button className="text-button" onClick={() => void navigator.clipboard.writeText(traceId)}>复制关联标识</button> <a href="http://localhost:15330" target="_blank" rel="noreferrer">打开本地 Grafana</a></span>; }
