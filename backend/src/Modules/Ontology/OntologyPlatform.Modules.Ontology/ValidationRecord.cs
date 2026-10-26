namespace OntologyPlatform.Modules.Ontology;

/// <summary>Ontology自有持久记录，不向其他模块暴露写入。</summary>
public sealed class ValidationRecord
{
    /// <summary>不可变报告主键。</summary>
    public string ReportId { get; set; } = string.Empty;

    /// <summary>绑定草稿。</summary>
    public string DraftId { get; set; } = string.Empty;

    /// <summary>绑定的精确修订。</summary>
    public long Revision { get; set; } = 0;

    /// <summary>完整源码组合散列。</summary>
    public string BundleHash { get; set; } = string.Empty;

    /// <summary>真实执行支持子集与SHACL是否均符合。</summary>
    public bool Conforms { get; set; } = false;

    /// <summary>完整标准定位报告。</summary>
    public string ReportJson { get; set; } = string.Empty;
}
