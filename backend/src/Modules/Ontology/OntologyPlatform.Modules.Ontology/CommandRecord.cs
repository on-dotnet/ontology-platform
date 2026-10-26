namespace OntologyPlatform.Modules.Ontology;

/// <summary>Ontology自有持久记录，不向其他模块暴露写入。</summary>
public sealed class CommandRecord
{
    /// <summary>完整scope操作及幂等键规范散列。</summary>
    public string Key { get; set; } = string.Empty;

    /// <summary>完整命令载荷散列，异载荷不得复用。</summary>
    public string PayloadHash { get; set; } = string.Empty;

    /// <summary>原始主体，禁止跨主体读取回执。</summary>
    public string SubjectId { get; set; } = string.Empty;

    /// <summary>已提交业务回执的固定JSON。</summary>
    public string ResultJson { get; set; } = string.Empty;
}
