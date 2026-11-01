import Link from "next/link";
import { PlatformApiError } from "../../lib/api/client";
import type { ConnectionProbeView } from "../../lib/api/g4-generated";
const diagnostics: Record<string, string> = { connection_tls_untrusted: "证书或服务器身份不可信，请联系管理员核验证书。", tls_untrusted: "证书或服务器身份不可信，请联系管理员核验证书。", auth_failed: "源账号认证失败，请重新录入正确凭据。", readonly_unverified: "无法证明源账号仅有只读权限，请核验账号权限。", source_unavailable: "源服务暂不可用，请检查服务后重试。", connection_secret_expired: "临时凭据已失效，请重新输入。", connection_test_stale: "测试已过期或配置发生变化，请重新测试。", connector_not_enabled: "此数据源的连接测试与保存尚未开放。", catalog_access_forbidden: "没有目录访问权限。" };
export const stateLabels: Record<string, string> = { DRAFT: "草稿", ACTIVE: "已启用", DISABLED: "已禁用", RUNNING: "运行中", QUEUED: "等待执行", SUCCEEDED: "已完成", PARTIAL: "部分完成", FAILED: "失败", CANCELLED: "已取消", TEST_OK: "测试通过", TEST_FAILED: "测试失败", EXPIRED: "已过期", READY: "可用", STALE: "已过期", PASS: "通过", FAIL: "失败", NOT_VERIFIED: "未验证", NOT_RUN: "未执行" };
/** 只展示安全白名单诊断，不回显服务端异常或用户输入。 */
export function RequestError({ error, retry }: { error: unknown; retry?: () => void }) {
  if (!error) return null;
  const issue = error instanceof PlatformApiError ? error : null;
  const text = issue?.status === 401 ? "登录已过期，请重新登录。" : issue?.status === 403 ? "没有访问权限。请联系管理员确认授权范围。" : issue?.status === 409 ? "连接已被修改，或测试已失效。已保留您的非敏感编辑，请读取最新版本后核对。" : issue?.status === 422 ? diagnostics[issue.code] ?? "配置或凭据未通过验证，请检查输入后重试。" : diagnostics[issue?.code ?? ""] ?? "服务暂不可用或网络中断，结果尚未确认。请恢复连接后重试。";
  return <div role="alert" tabIndex={-1} className="connection-alert"><strong>{text}</strong>{issue?.traceId && <p>关联标识：{issue.traceId}</p>}{issue?.status === 401 ? <Link href="/auth/login?returnUrl=/data/connections">重新登录</Link> : retry && <button type="button" onClick={retry}>重新读取</button>}</div>;
}
/** 五个固定探测阶段逐项展示，缺失阶段始终保持未验证。 */
export function ProbeReport({ probe, running = false }: { probe: ConnectionProbeView | null; running?: boolean }) {
  const labels = { NETWORK: "网络连接", TLS: "证书与主机身份", AUTH: "账号认证", READ_ONLY: "只读权限", METADATA: "目录访问" };
  return <section className="connection-card" aria-label="连接测试报告" aria-live="polite"><h2>连接测试 <span className="tag">{running ? "测试中" : probe ? stateLabels[probe.status] ?? probe.status : "尚未测试"}</span></h2>{probe?.stale && <p className="connection-alert">此测试已过期，需重新测试。</p>}
    <ol className="probe-stages">{Object.entries(labels).map(([name, label]) => { const stage = probe?.stages.find(item => item.name === name); return <li key={name}><strong>{label}</strong><span className={`tag ${stage?.status === "PASS" ? "teal" : "amber"}`}>{stateLabels[stage?.status ?? "NOT_VERIFIED"] ?? stage?.status}</span><small>{stage ? `${stage.durationMs} ms` : "等待实际结果"}</small>{stage?.diagnosticCode && <p>{diagnostics[stage.diagnosticCode] ?? "此阶段未通过，请核验配置和源权限。"}</p>}</li>; })}</ol>
    {probe && <p className="connection-note">开始：{probe.startedAtUtc} · 有效至：{probe.expiresAtUtc}<br />关联标识：{probe.traceId}</p>}
  </section>;
}
