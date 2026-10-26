namespace OntologyPlatform.Modules.Publishing;

/// <summary>保存精确提案绑定与单次消费事实。</summary>
public sealed class ProposalRecord
{
    /// <summary>提案主键。</summary>
    public string ProposalId { get; set; } = string.Empty;

    /// <summary>永久资产标识。</summary>
    public string AssetId { get; set; } = string.Empty;

    /// <summary>授权组织。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整排序厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>唯一合同序列化的完整审批内容。</summary>
    public string ProposalJson { get; set; } = string.Empty;

    /// <summary>审核CAS修订。</summary>
    public long Revision { get; set; } = 1;

    /// <summary>是否已被成功激活命令消费。</summary>
    public bool Activated { get; set; } = false;
}
