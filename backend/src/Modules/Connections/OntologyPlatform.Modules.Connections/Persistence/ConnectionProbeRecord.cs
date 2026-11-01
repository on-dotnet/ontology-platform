namespace OntologyPlatform.Modules.Connections;

/// <summary>Connections模块独占的ConnectionProbeRecord持久记录，不映射外部源业务表。</summary>
public sealed class ConnectionProbeRecord
{
    /// <summary>开始时修订，阻止同内容编辑后的旧探测提交。</summary>
    public long Revision { get; set; }

    /// <summary>恢复使用的准确幂等键。</summary>
    public string CommandKey { get; set; } = string.Empty;

    /// <summary>用于原始操作恢复审计的可信主体快照。</summary>
    public string ActorJson { get; set; } = string.Empty;

    /// <summary>记录唯一标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>草稿为空的连接引用。</summary>
    public string? ConnectionId { get; set; } = null;

    /// <summary>探测操作者。</summary>
    public string Owner { get; set; } = string.Empty;

    /// <summary>不可变报告或RUNNING事实。</summary>
    public string ReportJson { get; set; } = string.Empty;

    /// <summary>配置版本绑定。</summary>
    public string ConfigHash { get; set; } = string.Empty;

    /// <summary>凭据版本绑定。</summary>
    public long SecretVersion { get; set; } = 1;

    /// <summary>有效性截止。</summary>
    public DateTimeOffset ExpiresAtUtc { get; set; } = default;

    /// <summary>运行总期限。</summary>
    public DateTimeOffset Deadline { get; set; } = default;
}
