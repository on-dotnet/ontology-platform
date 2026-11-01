namespace OntologyPlatform.Modules.Connections;

/// <summary>Connections模块独占的CatalogSnapshotRecord持久记录，不映射外部源业务表。</summary>
public sealed class CatalogSnapshotRecord
{
    /// <summary>记录唯一标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>来源连接。</summary>
    public string ConnectionId { get; set; } = string.Empty;

    /// <summary>捕获配置散列。</summary>
    public string ConfigHash { get; set; } = string.Empty;

    /// <summary>捕获凭据版本。</summary>
    public long SecretVersion { get; set; } = 1;

    /// <summary>不可变目录快照。</summary>
    public string ViewJson { get; set; } = string.Empty;

    /// <summary>捕获时刻。</summary>
    public DateTimeOffset CapturedAtUtc { get; set; } = default;
}
