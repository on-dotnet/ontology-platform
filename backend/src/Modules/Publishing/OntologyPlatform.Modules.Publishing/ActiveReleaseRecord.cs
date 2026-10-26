namespace OntologyPlatform.Modules.Publishing;

/// <summary>资产唯一活动指针及防ABA修订。</summary>
public sealed class ActiveReleaseRecord
{
    /// <summary>永久资产主键。</summary>
    public string AssetId { get; set; } = string.Empty;

    /// <summary>永久授权组织。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>永久完整厂区范围。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>已验证正式版本。</summary>
    public string ReleaseId { get; set; } = string.Empty;

    /// <summary>每次发布及回滚递增的修订。</summary>
    public long Revision { get; set; } = 0;
}
