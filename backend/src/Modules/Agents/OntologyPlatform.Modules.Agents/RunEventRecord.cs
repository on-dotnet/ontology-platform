namespace OntologyPlatform.Modules.Agents;

/// <summary>Agents模块独占的持久事件重放记录。</summary>
public sealed class RunEventRecord
{
    /// <summary>事件所属运行。</summary>
    public string RunId { get; set; } = string.Empty;

    /// <summary>事务锁分配的单调序号。</summary>
    public long Seq { get; set; } = 0;

    /// <summary>运行加序号的稳定重放标识。</summary>
    public string EventId { get; set; } = string.Empty;

    /// <summary>唯一ExecutionEvent序列化字节文本。</summary>
    public string EnvelopeJson { get; set; } = string.Empty;
}
