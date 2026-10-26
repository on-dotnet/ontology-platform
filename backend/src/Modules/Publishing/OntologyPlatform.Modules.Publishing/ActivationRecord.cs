namespace OntologyPlatform.Modules.Publishing;

/// <summary>持久保留每次发布或回滚的完整事实。</summary>
public sealed class ActivationRecord
{
    /// <summary>激活事实主键。</summary>
    public string ActivationId { get; set; } = string.Empty;

    /// <summary>所属资产。</summary>
    public string AssetId { get; set; } = string.Empty;

    /// <summary>此资产单调激活修订。</summary>
    public long Revision { get; set; } = 0;

    /// <summary>此次完整版本。</summary>
    public string ReleaseId { get; set; } = string.Empty;

    /// <summary>包含审计和Trace的唯一合同回执。</summary>
    public string ResultJson { get; set; } = string.Empty;
}
