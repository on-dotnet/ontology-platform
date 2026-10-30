"use client";
import { useState } from "react";
import { PlatformApiError } from "../../lib/api/client";
/** 只显示安全状态与关联标识，远端detail和异常原文不进入页面。 */
export function SemanticError({ error }: { error: unknown }) {
  const status = error instanceof PlatformApiError ? error.status : 0;
  const titles: Record<number, string> = {
    401: "会话已失效，请重新登录",
    403: "当前角色或完整厂区范围无权访问",
    404: "资源不存在",
    409: "版本冲突：本地未保存文本仍保留",
    422: "源码、参数或支持子集未通过校验",
    428: "请求缺少版本条件",
    429: "已达到预算，请稍后重试",
    503: "依赖暂时不可用，未返回成功结果",
  };
  const explanations: Record<string, string> = {
    impact_required: "新发布审核须先生成绑定当前草稿与评估的影响报告。",
    impact_binding_conflict: "影响报告内容、hash或评估绑定不一致，请重新核对准确版本后生成报告。",
    impact_expired: "影响报告已过期，原报告保留供追溯；请更新评估输入后重新生成并提交审核。",
    impact_baseline_conflict: "活动发布基线已变化，请读取当前active版本并重新分析、提交异人审核。",
    impact_target_conflict: "影响报告目标与当前草稿修订不一致，请重新评估并生成准确目标报告。",
    impact_not_eligible: "影响报告存在技术阻断或未知覆盖，审核者不能覆盖；请查看报告证据并修正输入。",
    impact_reference_invalid: "版本引用无效：草稿须明确固定修订，正式Release不得携带草稿修订。",
    impact_report_not_found: "影响报告不存在，请从当前资产的准确固定版本重新读取或生成。",
    revision_source_binding_invalid: "历史修订原文与已存hash不一致，比较已停止，不能认定无差异。",
    comparison_asset_scope_conflict: "只能比较同一资产和相同完整范围内的两个固定版本。",
    identity_ambiguous: "AMBIGUOUS：同一组织、厂区和来源编号存在重叠身份声明。请保留历史并明确有效期，系统不会自动合并。",
    identity_relation_indeterminate: "INDETERMINATE：未知时间端点使身份关系无法确定，不能认定无冲突。请补充可验证的时间依据。",
    identity_history_immutable: "已保存的有效身份历史不能删除或改写；请关闭或收窄旧有效期，并以新IRI建立后续声明。",
    identity_scope_forbidden: "身份组织与厂区必须属于当前资产的完整授权范围。",
    identity_scope_conflict: "身份声明的组织或厂区与当前资产范围不一致。",
    time_timezone_required: "时间必须明确填写Z或±hh:mm时区，系统不会采用本机时区。",
    time_lexical_invalid: "时间不符合受控日期时间格式；请检查真实日期、时区及最多七位小数。",
    time_interval_reversed: "半开区间必须满足起点早于终点，终点不包含在有效期内。",
    time_reference_missing: "时间资源引用缺失或有多值；请登记明确的命名时间点或区间。",
    time_template_unsupported: "时间表达超出本轮受控点与区间模板；源码保留，结构编辑和发布将受阻。",
    identity_claim_invalid: "身份声明的组织、厂区、来源、编号、目标IRI或有效期不完整或有歧义。",
    event_time_invalid: "事件须引用明确的受控时间点或区间，观察时间另行记录。",
  };
  const explanation = error instanceof PlatformApiError && Object.hasOwn(explanations, error.code) ? explanations[error.code] : undefined;
  return <div className="g2-notice error" role="alert">
    <strong>{titles[status] ?? "请求未完成，请检查连接并显式重试"}</strong>
    {explanation && <p>{explanation}</p>}
    {status > 0 && <span> HTTP {status}</span>}
    {error instanceof PlatformApiError && error.traceId && <Trace traceId={error.traceId} />}
    {status === 401 && <a href="/auth/login?returnUrl=/ontologies" className="button">重新登录</a>}
  </div>;
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
  async function copy() {
    try {
      await navigator.clipboard.writeText(traceId);
      setCopyStatus("已复制关联标识");
    } catch { setCopyStatus("复制不可用，请手动选择上方标识"); }
  }
  return <span className="g2-trace">
    Trace <code>{traceId}</code>
    <button className="text-button" onClick={() => void copy()}>复制关联标识</button>
    {traceUrl ? <a href={traceUrl} target="_blank" rel="noreferrer">在本地 Grafana 定位此 Trace</a>
      : <small>关联标识格式无效，无法定位链路</small>}
    {copyStatus && <small role="status">{copyStatus}</small>}
  </span>;
}
