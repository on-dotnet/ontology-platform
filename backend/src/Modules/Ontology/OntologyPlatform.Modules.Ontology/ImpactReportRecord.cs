namespace OntologyPlatform.Modules.Ontology;

/// <summary>Ontology独有的不可变影响报告，唯一输入冻结首次生成事实。</summary>
public sealed class ImpactReportRecord
{
    /// <summary>服务器首次分配的报告主键。</summary>
    public string ReportId { get; set; } = string.Empty;

    /// <summary>所有固定输入及执行器预算的唯一身份。</summary>
    public string InputFingerprint { get; set; } = string.Empty;

    /// <summary>准确永久资产标识。</summary>
    public string AssetId { get; set; } = string.Empty;

    /// <summary>服务器授权组织。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>规范化且不可缩小的完整厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>目标为草稿时的不可变定位，正式版本分析为空。</summary>
    public string? TargetDraftId { get; set; }

    /// <summary>目标草稿的精确历史修订。</summary>
    public long? TargetRevision { get; set; }

    /// <summary>有真实目标评估时引用本模块自己的记录。</summary>
    public string? AssessmentId { get; set; }

    /// <summary>可从完整报告重算的canonical内容散列。</summary>
    public string ReportHash { get; set; } = string.Empty;

    /// <summary>严格唯一DTO序列化的完整不可变报告。</summary>
    public string ReportJson { get; set; } = string.Empty;

    /// <summary>首次实际完成时刻，不因命令重放刷新。</summary>
    public DateTimeOffset GeneratedAtUtc { get; set; }

    /// <summary>受真实评估期限限制的准确失效时刻。</summary>
    public DateTimeOffset ExpiresAtUtc { get; set; }
}
