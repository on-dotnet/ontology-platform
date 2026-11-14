namespace OntologyPlatform.Modules.Governance;

/// <summary>显式映射权限；不从历史角色自动推导授权。</summary>
public sealed class MappingAuthorizationGrant
{
    /// <summary>授权记录永久标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>经过身份提供方验证的主体。</summary>
    public string SubjectId { get; set; } = string.Empty;

    /// <summary>授权所属组织。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>单条授权覆盖的完整厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>注册映射操作。</summary>
    public string Permission { get; set; } = string.Empty;

    /// <summary>仅源验证许可绑定的连接。</summary>
    public string? ConnectionId { get; set; }

    /// <summary>源许可中的精确数据集身份。</summary>
    public string[] ObjectRefs { get; set; } = [];

    /// <summary>源许可中的精确字段身份。</summary>
    public string[] FieldRefs { get; set; } = [];

    /// <summary>授权绝对截止时间。</summary>
    public DateTimeOffset ExpiresAtUtc { get; set; }

    /// <summary>撤销时间，非空即不可用。</summary>
    public DateTimeOffset? RevokedAtUtc { get; set; }

}
