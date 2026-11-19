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

    /// <summary>平台观察与源清理共享的本地单调时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>上次收紧清理预算时的本地单调戳。</summary>
    private long cleanupStarted;

    /// <summary>从上次收紧至最早清理截止的长度，未设置则仍由调用方原截止约束。</summary>
    private TimeSpan? cleanupLimit;

    /// <summary>本分支是否确实经历物理申请，区别于尚未打开连接的取消。</summary>
    private bool acquired;

    /// <summary>无值表示此前所有物理申请已经证实释放。</summary>
    private Guid? outstanding;

    /// <summary>将固定平台 QueryId 与独占 Oracle ClientId 关联。</summary>
    /// <param name="queryId">当前已持久化的正式查询身份。</param>
    /// <param name="clock">与分支计量相同的服务器时钟。</param>
    public G4OracleSourceLifetime(string queryId, TimeProvider? clock = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(queryId);
        this.clock = clock ?? TimeProvider.System;
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

    /// <summary>成功读取必须实际申请过源资源，不能以从未开始工作的空状态代替。</summary>
    public bool HasAcquired
    {
        get { lock (gate) return acquired; }
    }

    /// <summary>已扣本地单调经过的最早清理余量，零表示原窗口已经关闭。</summary>
    public TimeSpan? CleanupRemaining
    {
        get { lock (gate) return RemainingLocked(); }
    }

    /// <summary>合并原分支余量或同库取消下界减去平台往返后的余量，只允许收紧。</summary>
    public void TightenCleanup(TimeSpan remaining)
    {
        lock (gate)
        {
            // 同一时间戳同时求旧窗口和设置新窗口，避免反复等长收紧产生延展。
            var now = clock.GetTimestamp();
            var candidate = remaining < TimeSpan.Zero ? TimeSpan.Zero : remaining;
            if (RemainingLocked(now) is { } current && current <= candidate) return;
            cleanupStarted = now;
            cleanupLimit = candidate;
        }
    }

    /// <summary>在锁内以同一单调时间戳扣减剩余量，保留未设置与零的区别。</summary>
    private TimeSpan? RemainingLocked(long? now = null)
    {
        if (cleanupLimit is not { } limit) return null;
        var elapsed = clock.GetElapsedTime(cleanupStarted, now ?? clock.GetTimestamp());
        return elapsed < limit ? limit - elapsed : TimeSpan.Zero;
    }

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
            if (RemainingLocked() == TimeSpan.Zero) throw new InvalidOperationException("Oracle 源分支期限已到。");
            var acquisition = Guid.NewGuid();
            acquired = true;
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
            if (RemainingLocked() == TimeSpan.Zero) throw new InvalidOperationException("Oracle 源释放已越过本次清理期限。");
            outstanding = null;
        }
    }

    /// <summary>退出异步范围；持久占位的释放仍由宿主按准确 owner/fence 原子确认。</summary>
    public void Dispose() => Scope.Value = previous;
}
