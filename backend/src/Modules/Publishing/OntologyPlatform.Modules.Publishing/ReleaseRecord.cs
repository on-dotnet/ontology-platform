namespace OntologyPlatform.Modules.Publishing;

/// <summary>保存准备及正式版本的不可变字节绑定。</summary>
public sealed class ReleaseRecord
{
    /// <summary>服务端生成发布主键。</summary>
    public string ReleaseId { get; set; } = string.Empty;

    /// <summary>原始发布提案唯一键。</summary>
    public string ProposalId { get; set; } = string.Empty;

    /// <summary>永久资产标识。</summary>
    public string AssetId { get; set; } = string.Empty;

    /// <summary>授权组织。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整授权范围。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>固定序列化清单字节。</summary>
    public string ManifestJson { get; set; } = string.Empty;

    /// <summary>清单独立散列，避免自包含循环。</summary>
    public string ManifestHash { get; set; } = string.Empty;

    /// <summary>清单对象地址及独立散列。</summary>
    public string ManifestObjectJson { get; set; } = string.Empty;

    /// <summary>准备时固定完整源，用于真实回验。</summary>
    public string SourcesJson { get; set; } = string.Empty;

    /// <summary>实际准备阶段。</summary>
    public string State { get; set; } = "PREPARING";

    /// <summary>是否存在已提交激活事实。</summary>
    public bool Published { get; set; } = false;

    /// <summary>最近激活的真实Trace。</summary>
    public string TraceId { get; set; } = string.Empty;
}
