namespace OntologyPlatform.Modules.Connections;

/// <summary>Connections模块独占的CatalogJobRecord持久记录，不映射外部源业务表。</summary>
public sealed class CatalogJobRecord
{
    /// <summary>记录唯一标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>来源连接。</summary>
    public string ConnectionId { get; set; } = string.Empty;

    /// <summary>请求配置修订。</summary>
    public long Revision { get; set; } = 1;

    /// <summary>请求秘密版本。</summary>
    public long SecretVersion { get; set; } = 1;

    /// <summary>请求配置散列。</summary>
    public string ConfigHash { get; set; } = string.Empty;

    /// <summary>可信服务器主体快照。</summary>
    public string ActorJson { get; set; } = string.Empty;

    /// <summary>受保护会话的内部引用。</summary>
    public string SessionReference { get; set; } = string.Empty;

    /// <summary>持久任务状态。</summary>
    public string Status { get; set; } = "QUEUED";

    /// <summary>脱敏关联标识。</summary>
    public string TraceId { get; set; } = string.Empty;

    /// <summary>创建时刻。</summary>
    public DateTimeOffset CreatedAtUtc { get; set; } = default;

    /// <summary>终态时刻。</summary>
    public DateTimeOffset? CompletedAtUtc { get; set; } = null;

    /// <summary>租约到期时刻。</summary>
    public DateTimeOffset? LeaseUntil { get; set; } = null;

    /// <summary>阻止旧工作者提交的栅栏。</summary>
    public long Fence { get; set; } = 0;

    /// <summary>已尝试次数。</summary>
    public int Attempt { get; set; } = 0;

    /// <summary>持久取消意图。</summary>
    public bool CancelRequested { get; set; } = false;

    /// <summary>产生的不可变快照。</summary>
    public string? SnapshotId { get; set; } = null;

    /// <summary>固定安全故障分类。</summary>
    public string? DiagnosticCode { get; set; } = null;
}
