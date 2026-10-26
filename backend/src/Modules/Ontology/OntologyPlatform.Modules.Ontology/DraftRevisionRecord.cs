namespace OntologyPlatform.Modules.Ontology;

/// <summary>Ontology自有持久记录，不向其他模块暴露写入。</summary>
public sealed class DraftRevisionRecord
{
    /// <summary>所属草稿。</summary>
    public string DraftId { get; set; } = string.Empty;

    /// <summary>不可变修订序号。</summary>
    public long Revision { get; set; } = 0;

    /// <summary>完整原始UTF8源码的无损JSON封装。</summary>
    public string SourcesJson { get; set; } = string.Empty;

    /// <summary>各源与组合散列。</summary>
    public string HashesJson { get; set; } = string.Empty;

    /// <summary>同修订真实Jena投影。</summary>
    public string ProjectionJson { get; set; } = string.Empty;
}
