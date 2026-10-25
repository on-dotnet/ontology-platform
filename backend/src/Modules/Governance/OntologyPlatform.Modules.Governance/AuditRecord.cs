namespace OntologyPlatform.Modules.Governance;

/// <summary>持久保存Governance模块的安全事实及关联标识。</summary>
public sealed class AuditRecord
{
    /// <summary>不可变事件标识。</summary>
    public string Id { get; set; } = Guid.NewGuid().ToString("N");

    /// <summary>事件发生的UTC时刻。</summary>
    public DateTimeOffset OccurredAtUtc { get; set; } = DateTimeOffset.UtcNow;

    /// <summary>已验证主体或anonymous。</summary>
    public string Actor { get; set; } = string.Empty;

    /// <summary>固定安全事件操作代码。</summary>
    public string Action { get; set; } = string.Empty;

    /// <summary>受控资源标识或路由。</summary>
    public string Resource { get; set; } = string.Empty;

    /// <summary>允许或拒绝的固定结果。</summary>
    public string Outcome { get; set; } = string.Empty;

    /// <summary>关联分布式跟踪的标识。</summary>
    public string TraceId { get; set; } = string.Empty;

    /// <summary>经验证的请求关联标识。</summary>
    public string CorrelationId { get; set; } = string.Empty;

    /// <summary>事件所属组织，匿名时为空。</summary>
    public string? OrganizationId { get; set; } = null;

    /// <summary>事件所属厂区，无单厂范围时为空。</summary>
    public string? SiteId { get; set; } = null;
}
