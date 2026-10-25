using System.Text.Json.Serialization;

namespace OntologyPlatform.Api.Contracts;

/// <summary>
/// 表示可信身份可读取的单一组织与厂区范围。
/// </summary>
public sealed class PlatformScope
{
    /// <summary>
    /// 组织范围标识。
    /// </summary>
    [JsonRequired]
    public string OrganizationId { get; init; } = string.Empty;

    /// <summary>
    /// 厂区范围标识。
    /// </summary>
    [JsonRequired]
    public string SiteId { get; init; } = string.Empty;
}

/// <summary>
/// 公开给同源Web的最小已认证身份，不包含认证票据或令牌。
/// </summary>
public sealed class PlatformIdentity
{
    /// <summary>
    /// 身份提供者验证通过的主体标识。
    /// </summary>
    [JsonRequired]
    public string SubjectId { get; init; } = string.Empty;

    /// <summary>
    /// 界面显示名，不承载秘密声明。
    /// </summary>
    [JsonRequired]
    public string DisplayName { get; init; } = string.Empty;

    /// <summary>
    /// 服务器认可的平台角色集合。
    /// </summary>
    [JsonRequired]
    public string[] Roles { get; init; } = [];

    /// <summary>
    /// 服务器认可的组织与厂区范围。
    /// </summary>
    [JsonRequired]
    public PlatformScope[] Scopes { get; init; } = [];
}

/// <summary>
/// 表示用于G1真实授权验证的已标记合成平台资源。
/// </summary>
public sealed class PlatformResource
{
    /// <summary>
    /// 资源稳定标识。
    /// </summary>
    [JsonRequired]
    public string Id { get; init; } = string.Empty;

    /// <summary>
    /// 资源中文显示名称。
    /// </summary>
    [JsonRequired]
    public string Name { get; init; } = string.Empty;

    /// <summary>
    /// 资源所属组织。
    /// </summary>
    [JsonRequired]
    public string OrganizationId { get; init; } = string.Empty;

    /// <summary>
    /// 资源所属厂区。
    /// </summary>
    [JsonRequired]
    public string SiteId { get; init; } = string.Empty;

    /// <summary>
    /// 明确说明资源为开发合成样例的状态。
    /// </summary>
    [JsonRequired]
    public string Status { get; init; } = "SyntheticDevelopment";
}

/// <summary>
/// 返回经过服务端作用域过滤且关联PG审计的资源列表。
/// </summary>
public sealed class PlatformResourceList
{
    /// <summary>
    /// 本次真正获准读取的资源。
    /// </summary>
    [JsonRequired]
    public PlatformResource[] Items { get; init; } = [];

    /// <summary>
    /// 已经提交的PG访问审计标识。
    /// </summary>
    [JsonRequired]
    public string AuditId { get; init; } = string.Empty;

    /// <summary>
    /// 当前请求的分布式跟踪标识。
    /// </summary>
    [JsonRequired]
    public string TraceId { get; init; } = string.Empty;
}

/// <summary>
/// 公开给有权限审计员的最小审计关联数据。
/// </summary>
public sealed class PlatformAuditEntry
{
    /// <summary>
    /// 不可变审计事件标识。
    /// </summary>
    [JsonRequired]
    public string Id { get; init; } = string.Empty;

    /// <summary>
    /// 审计发生的UTC时间。
    /// </summary>
    [JsonRequired]
    public DateTimeOffset OccurredAtUtc { get; init; } = default;

    /// <summary>
    /// 服务端解析的主体或anonymous标识。
    /// </summary>
    [JsonRequired]
    public string Actor { get; init; } = string.Empty;

    /// <summary>
    /// 固定语义的审计操作代码。
    /// </summary>
    [JsonRequired]
    public string Action { get; init; } = string.Empty;

    /// <summary>
    /// 被访问的平台资源标识或受控路径。
    /// </summary>
    [JsonRequired]
    public string Resource { get; init; } = string.Empty;

    /// <summary>
    /// 允许、拒绝或失败的固定结果代码。
    /// </summary>
    [JsonRequired]
    public string Outcome { get; init; } = string.Empty;

    /// <summary>
    /// 与运行日志和Trace关联的标识。
    /// </summary>
    [JsonRequired]
    public string TraceId { get; init; } = string.Empty;

    /// <summary>
    /// 经过格式验证的请求关联标识。
    /// </summary>
    [JsonRequired]
    public string CorrelationId { get; init; } = string.Empty;

    /// <summary>
    /// 事件适用的组织范围，匿名时可空。
    /// </summary>
    [JsonRequired]
    public string? OrganizationId { get; init; } = null;

    /// <summary>
    /// 完整事件厂区集合；历史未知为null，空数组不能授予组织范围访问。
    /// </summary>
    [JsonRequired]
    public string[]? ScopeSiteIds { get; init; }

    /// <summary>
    /// 兼容的唯一厂区；多厂区和无厂区时为空。
    /// </summary>
    [JsonRequired]
    public string? SiteId { get; init; } = null;
}

/// <summary>
/// 返回内置Antiforgery请求令牌，不作为身份认证令牌。
/// </summary>
public sealed class CsrfResponse
{
    /// <summary>
    /// 同源写请求需要回传的CSRF请求值。
    /// </summary>
    [JsonRequired]
    public string RequestToken { get; init; } = string.Empty;
}
