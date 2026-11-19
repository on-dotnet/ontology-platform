namespace OntologyPlatform.Contracts;

/// <summary>一个 Oracle 源分支的物理资源所有权。未获确认的申请始终占用容量。</summary>
public sealed class G4OracleSourceLifetime : IDisposable
{
    /// <summary>当前异步执行链中的唯一分支。</summary>
    private static readonly AsyncLocal<G4OracleSourceLifetime?> Scope = new();

    /// <summary>嵌套范围结束后恢复的原分支。</summary>
    private readonly G4OracleSourceLifetime? previous;

    /// <summary>准确物理申请身份的互斥保护。</summary>
    private readonly object gate = new();

    /// <summary>无值表示此前所有物理申请已经证实释放。</summary>
    private Guid? outstanding;

    /// <summary>将固定平台 QueryId 与独占 Oracle ClientId 关联。</summary>
    /// <param name="queryId">当前已持久化的正式查询身份。</param>
    public G4OracleSourceLifetime(string queryId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(queryId);
        QueryId = queryId;
        ExecutionId = Guid.NewGuid().ToString("N");
        previous = Scope.Value;
        Scope.Value = this;
    }

    /// <summary>当前分支；其他源和独立 Mapping 评估没有此范围。</summary>
    public static G4OracleSourceLifetime? Current => Scope.Value;

    /// <summary>平台侧查询身份。</summary>
    public string QueryId { get; }

    /// <summary>不因连接轮换而重用到另一分支的源观察身份。</summary>
    public string ExecutionId { get; }

    /// <summary>赋给驱动会话的三十二个小写十六进制字符。</summary>
    public string ClientId => ExecutionId;

    /// <summary>尚未申请或最后一次物理申请已获准确确认。</summary>
    public bool CleanupConfirmed
    {
        get { lock (gate) return outstanding is null; }
    }

    /// <summary>在尝试打开物理连接前登记，尚未确认的申请禁止覆盖。</summary>
    /// <returns>当前物理申请的唯一确认凭据。</returns>
    public Guid BeginSource()
    {
        lock (gate)
        {
            if (outstanding.HasValue) throw new InvalidOperationException("Oracle 源分支仍有未确认的物理申请。");
            // 晚到的确认不能清除后续另一物理申请。
            var acquisition = Guid.NewGuid();
            outstanding = acquisition;
            return acquisition;
        }
    }

    /// <summary>只接受准确物理申请的清理证明，重复或错身份不能改变状态。</summary>
    /// <param name="acquisition">本次打开前由 BeginSource 产生的身份。</param>
    public void ConfirmReleased(Guid acquisition)
    {
        lock (gate)
        {
            if (outstanding != acquisition) throw new InvalidOperationException("Oracle 源释放身份不匹配。");
            outstanding = null;
        }
    }

    /// <summary>退出异步范围；持久占位的释放仍由宿主按准确 owner/fence 原子确认。</summary>
    public void Dispose() => Scope.Value = previous;
}
