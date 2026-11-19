namespace OntologyPlatform.Contracts;

/// <summary>单次 G4 HTTP 或工具调用的原始单调期限，覆盖授权、工作、物理释放与提交。</summary>
public sealed class G4RequestDeadline : IDisposable
{
    /// <summary>当前异步调用链独占的期限载体。</summary>
    private static readonly AsyncLocal<G4RequestDeadline?> Scope = new();

    /// <summary>前一个范围供嵌套调用结束时恢复。</summary>
    private readonly G4RequestDeadline? previous;

    /// <summary>原始入口的同一时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>建立原期限时的单调时间戳。</summary>
    private readonly long started;

    /// <summary>同一起点的 UTC 关联值，仅用于跨进程记录。</summary>
    private readonly DateTimeOffset enteredUtc;

    /// <summary>使用同一时间提供者的期限计时器。</summary>
    private readonly CancellationTokenSource timer;

    /// <summary>连接调用方取消、外层取消与原计时器。</summary>
    private readonly CancellationTokenSource linked;

    /// <summary>收紧与并发读取共享的绝对预算长度。</summary>
    private long limitTicks;

    /// <summary>请求进入 Guard 或 ReserveRun 之前建立，外层剩余时间优先。</summary>
    /// <param name="clock">当前请求宿主的时间提供者。</param>
    /// <param name="token">请求断开或外部取消。</param>
    public G4RequestDeadline(TimeProvider clock, CancellationToken token)
    {
        previous = Scope.Value;
        this.clock = previous?.clock ?? clock;
        started = previous?.started ?? this.clock.GetTimestamp();
        enteredUtc = previous?.enteredUtc ?? this.clock.GetUtcNow();
        // 初始上限始终从最早的入口起算。
        var maximum = previous?.DeadlineUtc ?? enteredUtc.AddSeconds(5);
        if (SemanticReadDeadline.Current is { } outer && outer < maximum) maximum = outer;
        previous?.Tighten(maximum);
        limitTicks = (maximum - enteredUtc).Ticks;
        timer = new CancellationTokenSource(Remaining, this.clock);
        linked = CancellationTokenSource.CreateLinkedTokenSource(token, previous?.Token ?? CancellationToken.None, timer.Token);
        Scope.Value = this;
    }

    /// <summary>本次调用的当前期限，非 G4 调用为空。</summary>
    public static G4RequestDeadline? Current => Scope.Value;

    /// <summary>入口 UTC 加原时长，仅用于持久化与跨实例对账。</summary>
    public DateTimeOffset DeadlineUtc => enteredUtc.AddTicks(Interlocked.Read(ref limitTicks));

    /// <summary>真实上游取消及原期限的组合令牌。</summary>
    public CancellationToken Token => linked.Token;

    /// <summary>当前进程内以单调时钟算出的剩余预算。</summary>
    public TimeSpan Remaining => TimeSpan.FromTicks(Math.Max(0,
        Interlocked.Read(ref limitTicks) - clock.GetElapsedTime(started).Ticks));

    /// <summary>读取到 Query.TimeoutMs 后从原入口收紧，禁止重新启动一段完整预算。</summary>
    /// <param name="timeoutMs">原始查询合法时限，单位毫秒。</param>
    public void Tighten(int timeoutMs)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(timeoutMs);
        Tighten(enteredUtc.AddMilliseconds(timeoutMs));
    }

    /// <summary>将已有 Run 或外层的绝对截止映射到最早入口的单调起点，并收紧全部父范围。</summary>
    /// <param name="deadline">同次调用已知的 UTC 截止；过去的时刻保持原值。</param>
    public void Tighten(DateTimeOffset deadline)
    {
        previous?.Tighten(deadline);
        lock (timer)
        {
            // 只允许缩短，外层约束或已经发生的取消持续有效。
            var ticks = (deadline - enteredUtc).Ticks;
            if (ticks >= Interlocked.Read(ref limitTicks)) return;
            Interlocked.Exchange(ref limitTicks, ticks);
            // 已过截止同步传播，尚未到期则缩短原计时器。
            var left = Remaining;
            if (left == TimeSpan.Zero) timer.Cancel();
            else timer.CancelAfter(left);
        }
    }

    /// <summary>在同步编码等边界读取原单调时钟，计时器尚未调度也不能交付逾期结果。</summary>
    public void ThrowIfExpired()
    {
        if (Remaining == TimeSpan.Zero) timer.Cancel();
        Token.ThrowIfCancellationRequested();
    }

    /// <summary>在整个调用链完成后恢复父范围并释放计时器。</summary>
    public void Dispose()
    {
        Scope.Value = previous;
        linked.Dispose();
        timer.Dispose();
    }
}
