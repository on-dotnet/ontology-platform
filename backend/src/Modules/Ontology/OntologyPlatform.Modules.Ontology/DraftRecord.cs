namespace OntologyPlatform.Modules.Ontology;

/// <summary>Ontology自有持久记录，不向其他模块暴露写入。</summary>
public sealed class DraftRecord
{
    /// <summary>草稿稳定主键。</summary>
    public string DraftId { get; set; } = string.Empty;

    /// <summary>永久绑定此完整范围的资产。</summary>
    public string AssetId { get; set; } = string.Empty;

    /// <summary>资源所属组织。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>已规范化完整厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>可选基础正式版本。</summary>
    public string? BaseReleaseId { get; set; } = null;

    /// <summary>当前CAS修订。</summary>
    public long Revision { get; set; } = 1;

    /// <summary>受保护资产名称。</summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>最初创建主体。</summary>
    public string OwnerSubjectId { get; set; } = string.Empty;

    /// <summary>最近提交时间。</summary>
    public DateTimeOffset UpdatedAtUtc { get; set; } = default;
}
