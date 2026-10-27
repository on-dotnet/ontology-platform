namespace OntologyPlatform.Modules.Ontology;

/// <summary>Ontology独有的不可变真实评估，与报告一对一持久。</summary>
public sealed class AssessmentRecord
{
    /// <summary>服务器生成评估主键。</summary>
    public string AssessmentId { get; set; } = string.Empty;

    /// <summary>同事务生成的唯一验证报告。</summary>
    public string ValidationReportId { get; set; } = string.Empty;

    /// <summary>不可变草稿身份。</summary>
    public string DraftId { get; set; } = string.Empty;

    /// <summary>准确源修订。</summary>
    public long Revision { get; set; }

    /// <summary>完整可重新散列的评估事实JSON。</summary>
    public string AssessmentJson { get; set; } = string.Empty;
}
