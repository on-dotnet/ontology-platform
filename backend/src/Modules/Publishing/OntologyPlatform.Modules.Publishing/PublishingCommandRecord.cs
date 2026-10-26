namespace OntologyPlatform.Modules.Publishing;

/// <summary>同完整范围及操作绑定的幂等预留和真实回执。</summary>
public sealed class PublishingCommandRecord
{
    /// <summary>范围操作幂等键的结构化散列。</summary>
    public string Key { get; set; } = string.Empty;

    /// <summary>完整规范载荷散列。</summary>
    public string PayloadHash { get; set; } = string.Empty;

    /// <summary>可信命令提交者。</summary>
    public string SubjectId { get; set; } = string.Empty;

    /// <summary>激活准备固定版本。</summary>
    public string? ReleaseId { get; set; } = null;

    /// <summary>仅事务提交后的唯一真实回执。</summary>
    public string? ResultJson { get; set; } = null;
}
