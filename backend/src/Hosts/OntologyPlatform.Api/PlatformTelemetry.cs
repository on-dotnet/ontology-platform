using System.Diagnostics;
using System.Diagnostics.Metrics;

namespace OntologyPlatform.Api;

/// <summary>记录真实请求的低基数指标和安全结构化日志。</summary>
public static partial class PlatformTelemetry
{
    /// <summary>与已批准遥测合同一致的跟踪源。</summary>
    public static readonly ActivitySource Activities = new("OntologyPlatform.Api");

    /// <summary>由正式API明确注册导出的指标源。</summary>
    public static readonly Meter Meter = new("OntologyPlatform.Api");

    /// <summary>真实请求次数，不携带主体或厂区标签。</summary>
    public static readonly Counter<long> Requests = Meter.CreateCounter<long>("platform.requests");

    /// <summary>请求耗时秒数，标签只使用固定模板及状态类别。</summary>
    public static readonly Histogram<double> Duration = Meter.CreateHistogram<double>("platform.request.duration", "s");

    /// <summary>可由监控以时间差判断API停机的UTC心跳，无身份标签。</summary>
    public static readonly ObservableGauge<double> Heartbeat = Meter.CreateObservableGauge<double>(
        "platform.heartbeat", () => DateTimeOffset.UtcNow.ToUnixTimeSeconds());

    /// <summary>只记录固定路由和关联标识，不写URL查询、请求头或正文。</summary>
    /// <param name="logger">宿主结构化日志器。</param>
    /// <param name="route">固定路由模板。</param>
    /// <param name="status">HTTP状态。</param>
    /// <param name="traceId">当前跟踪标识，作为结构化字段而非索引标签。</param>
    /// <param name="auditId">已提交PG审计标识，可空。</param>
    [LoggerMessage(1001, LogLevel.Information, "平台请求 route={Route} status={Status} traceId={TraceId} auditId={AuditId}")]
    public static partial void RequestCompleted(ILogger logger, string route, int status, string traceId, string? auditId);
}
