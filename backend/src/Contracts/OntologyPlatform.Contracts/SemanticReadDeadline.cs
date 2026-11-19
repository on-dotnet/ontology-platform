namespace OntologyPlatform.Contracts;

/// <summary>将服务器已确定的绝对截止传过当前异步发布核验调用链；不同请求拥有各自的执行上下文。</summary>
public sealed class SemanticReadDeadline : IDisposable
{
    /// <summary>当前调用链的最早服务器截止，不携带权限、业务数据或已核验结果。</summary>
    private static readonly AsyncLocal<DateTimeOffset?> Deadline = new();

    /// <summary>进入当前范围前的截止，退出时恢复外层约束。</summary>
    private readonly DateTimeOffset? previous;

    /// <summary>嵌套核验只能缩短剩余期限。</summary>
    public SemanticReadDeadline(DateTimeOffset expiresAt)
    {
        previous = Deadline.Value;
        Deadline.Value = previous < expiresAt ? previous : expiresAt;
    }

    /// <summary>取得调用者设定的绝对截止；无外部范围时由语义引擎使用自身五秒预算。</summary>
    public static DateTimeOffset? Current => Deadline.Value;

    /// <summary>核验收尾后恢复父范围。</summary>
    public void Dispose() => Deadline.Value = previous;
}
