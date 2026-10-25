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

    /// <summary>仅观察PAR推送参数是否完整，不记录任何协议值。</summary>
    /// <param name="logger">正式宿主日志器。</param>
    /// <param name="code">是否使用授权码响应。</param>
    /// <param name="pkceS256">是否要求S256挑战。</param>
    /// <param name="hasChallenge">挑战是否存在。</param>
    /// <param name="hasState">受保护状态是否存在。</param>
    /// <param name="hasNonce">随机关联值是否存在。</param>
    [LoggerMessage(1002, LogLevel.Information, "PAR协议 code={Code} pkceS256={PkceS256} hasChallenge={HasChallenge} hasState={HasState} hasNonce={HasNonce}")]
    public static partial void AuthorizationPushed(ILogger logger, bool code, bool pkceS256, bool hasChallenge, bool hasState, bool hasNonce);

    /// <summary>只记录固定路由和关联标识，不写URL查询、请求头或正文。</summary>
    /// <param name="logger">宿主结构化日志器。</param>
    /// <param name="route">固定路由模板。</param>
    /// <param name="status">HTTP状态。</param>
    /// <param name="traceId">当前跟踪标识，作为结构化字段而非索引标签。</param>
    /// <param name="auditId">已提交PG审计标识，可空。</param>
    /// <param name="outcome">固定完成结果，不能由请求输入提供。</param>
    [LoggerMessage(1001, LogLevel.Information, "平台请求 route={Route} status={Status} traceId={TraceId} auditId={AuditId} outcome={Outcome}")]
    public static partial void RequestCompleted(ILogger logger, string route, int status, string traceId, string? auditId, string outcome);

    /// <summary>记录受控请求故障，不接受原异常对象或任何异常原文。</summary>
    /// <param name="logger">宿主结构化日志器。</param>
    /// <param name="route">固定路由模板。</param>
    /// <param name="exceptionCategory">白名单故障类别。</param>
    /// <param name="outcome">固定失败完成结果。</param>
    /// <param name="status">实际响应状态或受控取消状态。</param>
    /// <param name="traceId">与实际请求Activity关联的跟踪标识。</param>
    [LoggerMessage(1003, LogLevel.Error, "平台故障 route={Route} exceptionCategory={ExceptionCategory} outcome={Outcome} status={Status} traceId={TraceId}", EventName = "PlatformRequestFault")]
    public static partial void PlatformRequestFault(ILogger logger, string route, string exceptionCategory, string outcome, int status, string traceId);
}
