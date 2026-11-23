using System.Diagnostics;

namespace OntologyPlatform.Contracts;

/// <summary>固定 Oracle 元数据命令的聚合驱动观察，只记录单调时间、数目与有限错误号。</summary>
public sealed class G4OracleMetadataSpan(string statement, bool post, int ordinal, string? execution, Guid? acquisition)
{
    /// <summary>固定的六种目录或权限操作之一。</summary>
    public string Statement { get; } = statement;

    /// <summary>当前调用是否属于后验。</summary>
    public bool Post { get; } = post;

    /// <summary>本投影内的调用序号。</summary>
    public int Ordinal { get; } = ordinal;

    /// <summary>平台分支或独立探针的执行号。</summary>
    public string? Execution { get; } = execution;

    /// <summary>唯一物理连接申请。</summary>
    public Guid? Acquisition { get; } = acquisition;

    /// <summary>首次创建固定命令时的单调戳。</summary>
    public long Begin { get; } = Stopwatch.GetTimestamp();

    /// <summary>命令释放实际结束时的单调戳。</summary>
    public long? End { get; set; }

    /// <summary>进入驱动 Execute 前的单调戳。</summary>
    public long? ExecuteBegin { get; set; }

    /// <summary>驱动 Execute 返回或抛出后的单调戳。</summary>
    public long? ExecuteEnd { get; set; }

    /// <summary>所有实际 Read 调用累计耗用的单调刻度。</summary>
    public long ReadTicks { get; set; }

    /// <summary>实际进入驱动的 Read 次数，包括失败调用。</summary>
    public int ReadCalls { get; set; }

    /// <summary>驱动实际返回 true 的次数。</summary>
    public int Rows { get; set; }

    /// <summary>首次成功取行时的单调戳。</summary>
    public long? FirstRow { get; set; }

    /// <summary>首次实际 Read 返回 false 的单调戳。</summary>
    public long? Eof { get; set; }

    /// <summary>游标异步释放起点。</summary>
    public long? CursorDisposeBegin { get; set; }

    /// <summary>游标异步释放终点。</summary>
    public long? CursorDisposeEnd { get; set; }

    /// <summary>命令同步释放起点。</summary>
    public long? CommandDisposeBegin { get; set; }

    /// <summary>驱动错误号或取消、其他异常的有限分类。</summary>
    public int? OperationError { get; set; }

    /// <summary>游标释放失败的独立错误类别。</summary>
    public int? CursorError { get; set; }

    /// <summary>命令释放失败的独立错误类别。</summary>
    public int? CommandError { get; set; }

    /// <summary>已有身份查询返回的五项数值会话标识。</summary>
    public ulong[]? Session { get; set; }
}
