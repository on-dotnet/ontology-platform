using System.Diagnostics;

namespace OntologyPlatform.Contracts;

/// <summary>仅为受控 HTTP 调用记录源阶段。投影不保存日志模板、参数、查询或异常对象。</summary>
public sealed class G4OracleQueryTrace : IDisposable
{
    /// <summary>当前真实请求的异步调用上下文，观察器与源工作共享同一缓冲。</summary>
    private static readonly AsyncLocal<G4OracleQueryTrace?> Scope = new();

    /// <summary>同一内存上限覆盖两个分支和全部取消通知。</summary>
    private readonly List<object> events = new(160);

    /// <summary>调用前的作用域，退出时原样恢复。</summary>
    private readonly G4OracleQueryTrace? previous = Scope.Value;

    /// <summary>首个已记录的失败或取消来源，后续清理裁决单列。</summary>
    private string? firstFailure;

    /// <summary>取消信号与最先观察到的异常分别保留。</summary>
    private string? firstSignal;

    /// <summary>每一条因缓冲已满而失去的事件均计数。</summary>
    private int dropped;

    /// <summary>当前执行绑定的服务端查询标识。</summary>
    private string? queryId;

    /// <summary>沿实际 API 进程的单调时钟记录本次调用，根预算在调用方先建立。</summary>
    public G4OracleQueryTrace() => Scope.Value = this;

    /// <summary>将服务端成功分配的查询关联到当前请求。</summary>
    public static void Bind(string id)
    {
        if (Scope.Value is { } trace && id.Length == 38 && id.StartsWith("query-", StringComparison.Ordinal)
            && Guid.TryParseExact(id[6..], "N", out _)) trace.queryId = id;
    }

    /// <summary>仅记录源代码定义的阶段、有限状态和同次执行号。序列与首个失败在同一锁内确定。</summary>
    public static void Mark(string stage, string outcome = "enter", Guid? acquisition = null, long? budgetTicks = null, long? originTick = null, ulong[]? session = null)
    {
        if (Scope.Value is not { } trace || session is not null && (stage != "session" || session.Length != 5)) return;
        if (stage is not ("http" or "initialLease" or "permit" or "permitCheck" or "tls" or "openCheck" or "open" or "permitReturn" or "sessionTag"
            or "readOnly" or "catalog" or "session" or "transaction" or "declareReadOnly" or "execute" or "commit"
            or "rollback" or "disposeTransaction" or "postcheck" or "disposeConnection" or "observer" or "cleanupStart" or "cleanup"
            or "workCutoff" or "readerCutoff" or "leaseTimeout" or "leaseException" or "formalCancel" or "leaseInactive"
            or "requestCancel" or "requestDeadline" or "branch" or "acquisition" or "source" or "EXECUTE" or "EOF" or "NATIVE_1013" or "CANCEL_ENTER" or "CANCEL_RETURN" or "CANCEL_REJECT" or "PHYSICAL_RELEASE")) return;
        if (outcome is not ("enter" or "returned" or "failed" or "cancelled" or "unconfirmed" or "confirmed" or "signal")) return;
        lock (trace.events)
        {
            if (outcome == "signal") trace.firstSignal ??= stage;
            if (outcome is "failed" or "cancelled") trace.firstFailure ??= stage + "." + outcome;
            if (trace.events.Count == 160) { trace.dropped++; return; }
            trace.events.Add(new { stage, outcome, tick = Stopwatch.GetTimestamp(),
                remainingTicks = G4RequestDeadline.Current?.Remaining.Ticks,
                cleanupTicks = G4OracleSourceLifetime.Current?.CleanupRemaining?.Ticks,
                execution = G4OracleSourceLifetime.Current?.ExecutionId, acquisition, budgetTicks, originTick, session });
        }
    }

    /// <summary>在原始操作内观察返回或首异常；异常按原类型继续传播。</summary>
    public static async Task<T> ObserveAsync<T>(string stage, Func<Task<T>> action)
    {
        if (Scope.Value is null) return await action();
        Mark(stage);
        try
        {
            // 只有操作真正返回才登记该阶段完成。
            var result = await action();
            Mark(stage, "returned");
            return result;
        }
        catch (Exception error)
        {
            Mark(stage, error is OperationCanceledException ? "cancelled" : "failed");
            throw;
        }
    }

    /// <summary>没有返回值的源操作与读取操作遵循同一事件约定。</summary>
    public static async Task ObserveAsync(string stage, Func<Task> action) =>
        await ObserveAsync(stage, async () => { await action(); return true; });

    /// <summary>响应后的外层阶段复制有界快照；时间戳均来自同一 API 进程。</summary>
    public object Snapshot()
    {
        lock (events) return new { queryId, firstFailure, firstSignal, dropped, frequency = Stopwatch.Frequency, events = events.ToArray() };
    }

    /// <summary>释放请求上下文，已经注册的响应后导出仍可读取本次快照。</summary>
    public void Dispose() => Scope.Value = previous;
}
