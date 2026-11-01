namespace OntologyPlatform.Modules.Connections;

/// <summary>Connections模块独占的ConnectionRecord持久记录，不映射外部源业务表。</summary>
public sealed class ConnectionRecord
{
    /// <summary>记录唯一标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>连接名称。</summary>
    public string DisplayName { get; set; } = string.Empty;

    /// <summary>不含秘密的类型化配置。</summary>
    public string ConfigJson { get; set; } = string.Empty;

    /// <summary>规范化配置散列。</summary>
    public string ConfigHash { get; set; } = string.Empty;

    /// <summary>CAS资源修订。</summary>
    public long Revision { get; set; } = 1;

    /// <summary>内部凭据绑定引用。</summary>
    public string SecretId { get; set; } = string.Empty;

    /// <summary>绑定凭据版本。</summary>
    public long SecretVersion { get; set; } = 1;

    /// <summary>持久管理状态。</summary>
    public string State { get; set; } = "DRAFT";

    /// <summary>最近探测引用。</summary>
    public string? LastProbeId { get; set; } = null;

    /// <summary>最后变更时间。</summary>
    public DateTimeOffset UpdatedAtUtc { get; set; } = default;
}
