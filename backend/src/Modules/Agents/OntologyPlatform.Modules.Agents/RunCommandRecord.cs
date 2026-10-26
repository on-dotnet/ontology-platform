namespace OntologyPlatform.Modules.Agents;

/// <summary>Agents模块独占的持久幂等命令回执。</summary>
public sealed class RunCommandRecord
{
    /// <summary>操作主体范围与幂等键的散列。</summary>
    public string Key { get; set; } = string.Empty;

    /// <summary>规范化完整请求的SHA256。</summary>
    public string PayloadHash { get; set; } = string.Empty;

    /// <summary>回执绑定的运行。</summary>
    public string RunId { get; set; } = string.Empty;

    /// <summary>提交时的真实运行回执。</summary>
    public string ReceiptJson { get; set; } = string.Empty;
}
