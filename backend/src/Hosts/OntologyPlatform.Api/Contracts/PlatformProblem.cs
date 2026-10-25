using System.Text.Json.Serialization;

namespace OntologyPlatform.Api.Contracts;

/// <summary>描述平台标准ProblemDetails的必要公开字段，不承载异常或认证协议值。</summary>
public sealed class PlatformProblem
{
    /// <summary>稳定问题类型URI，默认遵循RFC的about:blank。</summary>
    [JsonRequired]
    public string Type { get; init; } = "about:blank";

    /// <summary>安全且固定的错误标题。</summary>
    [JsonRequired]
    public string Title { get; init; } = string.Empty;

    /// <summary>与实际HTTP响应相同的状态码。</summary>
    [JsonRequired]
    [JsonNumberHandling(JsonNumberHandling.Strict)]
    public int Status { get; init; }

    /// <summary>客户端分支判断使用的稳定平台错误码。</summary>
    [JsonRequired]
    public string Code { get; init; } = string.Empty;

    /// <summary>用于运维检索的当前分布式跟踪标识。</summary>
    [JsonRequired]
    public string TraceId { get; init; } = string.Empty;

    /// <summary>格式受限且由服务器确认的请求关联标识。</summary>
    [JsonRequired]
    public string CorrelationId { get; init; } = string.Empty;

    /// <summary>可选的安全错误说明，禁止放入原始异常。</summary>
    public string Detail { get; init; } = string.Empty;

    /// <summary>可选的问题实例引用，不包含请求查询或秘密。</summary>
    public string? Instance { get; init; }
}
