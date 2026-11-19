namespace OntologyPlatform.Contracts;

/// <summary>将查询模块的跨实例准入锁传到当前 Oracle 分支的唯一物理打开点。</summary>
public sealed class G4OracleSourceOpen
{
    /// <summary>查询模块拥有数据库事务，源模块只获得重检和释放的技术合同。</summary>
    public interface IPermit : IAsyncDisposable
    {
        /// <summary>在同一事务中重新检查已流逝的租约和绝对截止。</summary>
        Task CheckAsync(CancellationToken token);
    }

    /// <summary>当前调用上下文的封闭边界；独立 Mapping 评估没有查询容量参与者。</summary>
    private static readonly AsyncLocal<G4OracleSourceOpen?> Current = new();

    /// <summary>锁在成功打开物理会话后交还；异常路径在源调用退出时交还。</summary>
    private IPermit? permit;

    /// <summary>单个源读者调用最多申请一个物理会话。</summary>
    private int started;

    /// <summary>仅由已经取得平台共享容量锁的查询调用建立。</summary>
    private G4OracleSourceOpen(IPermit permit) => this.permit = permit;

    /// <summary>在持锁后进入源访问，确保在源读者接手前就拒绝已封闭的连接。</summary>
    public static async Task<T> RunAsync<T>(IPermit permit, Func<Task<T>> access)
    {
        // 返回上层调用原来的异步作用域。
        var previous = Current.Value;
        // 该次租用与另一次分支的物理打开互不混淆。
        var current = new G4OracleSourceOpen(permit);
        Current.Value = current;
        try
        {
            return await access();
        }
        finally
        {
            Current.Value = previous;
            await current.ReleaseAsync();
        }
    }

    /// <summary>在 TLS 探测和 Oracle 原生连接之前确认当前受保护调用只有一个打开点。</summary>
    public static async Task BeforePhysicalOpenAsync(CancellationToken token)
    {
        if (Current.Value is not { } current) return;
        if (Interlocked.Exchange(ref current.started, 1) != 0 || current.permit is null)
            throw new InvalidOperationException("一次来源读取不能重复打开 Oracle 会话。");
        await current.permit.CheckAsync(token);
    }

    /// <summary>物理打开完成立即释放平台锁，使正式取消能在源 SQL 仍执行时提交。</summary>
    public static ValueTask AfterPhysicalOpenAsync() => Current.Value?.ReleaseAsync() ?? ValueTask.CompletedTask;

    /// <summary>成功和失败路径只交还同一事务一次。</summary>
    private ValueTask ReleaseAsync() => Interlocked.Exchange(ref permit, null)?.DisposeAsync() ?? ValueTask.CompletedTask;
}
