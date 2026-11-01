namespace OntologyPlatform.Modules.Connections;

/// <summary>Connections模块独占的ConnectionSecretRecord持久记录，不映射外部源业务表。</summary>
public sealed class ConnectionSecretRecord
{
    /// <summary>记录唯一标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>签发操作者。</summary>
    public string Owner { get; set; } = string.Empty;

    /// <summary>固定用途。</summary>
    public string Purpose { get; set; } = "POSTGRESQL_READONLY";

    /// <summary>认证密文字节。</summary>
    public string Ciphertext { get; set; } = string.Empty;

    /// <summary>随机AEAD nonce。</summary>
    public string Nonce { get; set; } = string.Empty;

    /// <summary>AEAD认证标签。</summary>
    public string Tag { get; set; } = string.Empty;

    /// <summary>密钥版本。</summary>
    public long Version { get; set; } = 1;

    /// <summary>服务器KEK版本。</summary>
    public string KeyVersion { get; set; } = "dev-v1";

    /// <summary>未绑定到期时间。</summary>
    public DateTimeOffset ExpiresAtUtc { get; set; } = default;

    /// <summary>唯一绑定时间。</summary>
    public DateTimeOffset? UsedAtUtc { get; set; } = null;

    /// <summary>绑定的连接。</summary>
    public string? ConnectionId { get; set; } = null;
}
