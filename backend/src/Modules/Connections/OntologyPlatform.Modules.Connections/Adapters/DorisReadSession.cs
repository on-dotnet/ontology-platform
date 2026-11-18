using System.Data;
using System.Diagnostics;
using System.Globalization;
using MySqlConnector;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>Doris 查询分支拥有一次无池连接、一次执行机会和原分支内的清理窗口。</summary>
internal static class DorisReadSession
{
    /// <summary>连接、授权、读取、取消与释放共用一份分支预算，返回前丢弃任何迟到结果。</summary>
    internal static async Task<T> ReadAsync<T>(Func<MySqlConnection> connect,
        Func<MySqlConnection, CancellationToken, Task<T>> read, TimeProvider clock, DateTimeOffset deadlineAtUtc,
        CancellationToken caller)
    {
        // 将上层 UTC 期限转换为单调剩余时间，最后五百毫秒留给平台。
        var start = clock.GetTimestamp();
        // 源分支最多一秒；保留最后二百五十毫秒用于包括辅助握手在内的全部清理。
        var branch = TimeSpan.FromMilliseconds(Math.Min(1000, (deadlineAtUtc - clock.GetUtcNow()).TotalMilliseconds - 500));
        // 同一预留也限制提前取消时能使用的尾部。
        var reserve = TimeSpan.FromMilliseconds(250);
        caller.ThrowIfCancellationRequested();
        if (branch <= reserve) throw new SemanticOperationException(503, "query_source_budget_exhausted");
        // 在通知工作等待者之前记录取消时刻，避免调度延迟重新开始计时。
        long? cancelAt = null;
        // 串行保护单调取消时刻，防止外部取消和分支计时器同时首次写入。
        var sync = new object();
        using var work = new CancellationTokenSource();
        void Cancel()
        {
            lock (sync) cancelAt ??= clock.GetTimestamp();
            work.Cancel();
        }
        using var registration = caller.Register(Cancel);
        // 开始工作计时之前扣除预算计算本身已经耗去的时间。
        var workLeft = branch - reserve - clock.GetElapsedTime(start);
        if (workLeft <= TimeSpan.Zero) throw new SemanticOperationException(503, "query_source_budget_exhausted");
        using var timer = new CancellationTokenSource(workLeft, clock);
        using var timedRegistration = timer.Token.Register(Cancel);
        // 本次连接永不回池，ServerThread 只取自本次真实握手。
        var connection = connect();
        // 仅在取消已开启的主连接时创建同配置辅助连接。
        MySqlConnection? auxiliary = null;
        // 开启和读取分别跟踪，能区分从未发出 SQL 与正在执行的命令。
        Task<T>? pending = null;
        // 驱动的异步握手同样受外层绝对期限约束。
        Task? opening = null;
        try
        {
            work.Token.ThrowIfCancellationRequested();
            opening = connection.OpenAsync(work.Token);
            await BoundAsync(opening, work.Token);
            work.Token.ThrowIfCancellationRequested();
            pending = read(connection, work.Token);
            // 主命令不调用驱动的软取消；由独立同账号连接显式终止服务端连接。
            var result = await pending.WaitAsync(work.Token);
            work.Token.ThrowIfCancellationRequested();
            return result;
        }
        catch (PgSourceException error) when (error.Code == "connection_readonly_unverified") { throw new SemanticOperationException(403, "query_source_forbidden"); }
        catch (SemanticOperationException) { throw; }
        catch (OperationCanceledException) when (caller.IsCancellationRequested) { throw; }
        catch (OperationCanceledException) { throw new SemanticOperationException(503, "query_source_timeout"); }
        catch (Exception) { throw new SemanticOperationException(503, "query_source_unavailable"); }
        finally
        {
            // 无论调用者提前取消或工作时限到期，都从真实触发点扣除已用时间。
            var left = TimeSpan.FromTicks(Math.Min(reserve.Ticks, (branch - clock.GetElapsedTime(start)).Ticks));
            lock (sync)
            {
                if (cancelAt is long at)
                    left = TimeSpan.FromTicks(Math.Min(left.Ticks, (reserve - clock.GetElapsedTime(at)).Ticks));
            }
            using var cleanup = new CancellationTokenSource(left > TimeSpan.Zero ? left : TimeSpan.Zero, clock);
            // 即便看门狗尚未调度，耗尽的分支也不能发起辅助命令。
            if (left <= TimeSpan.Zero) cleanup.Cancel();
            try
            {
                if (work.IsCancellationRequested && pending is not null && connection.State == ConnectionState.Open)
                {
                    cleanup.Token.ThrowIfCancellationRequested();
                    // 已握手的源端整数 ID 与新建同账号 TLS 会话组成唯一取消目标。
                    var thread = connection.ServerThread;
                    auxiliary = connect();
                    await BoundAsync(auxiliary.OpenAsync(cleanup.Token), cleanup.Token);
                    cleanup.Token.ThrowIfCancellationRequested();
                    using var kill = auxiliary.CreateCommand();
                    kill.CommandText = "KILL CONNECTION " + thread.ToString(CultureInfo.InvariantCulture);
                    await BoundAsync(kill.ExecuteNonQueryAsync(CancellationToken.None), cleanup.Token);
                    Activity.Current?.AddEvent(new ActivityEvent("doris.kill.acknowledged"));
                }
                if (pending is not null && work.IsCancellationRequested)
                {
                    try { await BoundAsync(pending, cleanup.Token); }
                    catch when (pending.IsCompleted && !cleanup.IsCancellationRequested) { }
                    if (pending.IsCompleted) Activity.Current?.AddEvent(new ActivityEvent("doris.driver.ended"));
                }
                if (opening is { IsCompleted: false }) await BoundAsync(opening, cleanup.Token);
            }
            catch (Exception) { throw new SemanticOperationException(503, "query_source_unavailable"); }
            finally
            {
                if (pending is not null) Observe(pending);
                // 两个释放均被发起并观察，任一个失败均关闭该能力。
                var primaryRelease = connection.DisposeAsync().AsTask();
                // 辅助释放与主连接使用同一个单调截止时间。
                var otherRelease = auxiliary?.DisposeAsync().AsTask() ?? Task.CompletedTask;
                try { await BoundAsync(Task.WhenAll(primaryRelease, otherRelease), cleanup.Token); }
                catch (Exception) { throw new SemanticOperationException(503, "query_source_unavailable"); }
            }
            if (cleanup.IsCancellationRequested || clock.GetElapsedTime(start) >= branch)
                throw new SemanticOperationException(503, "query_source_budget_exhausted");
            if (work.IsCancellationRequested && pending is not null)
            {
                // 源任务曾经启动。同账号 KILL 和本机驱动结束仍不能证明 BE 已终止。
                Activity.Current?.AddEvent(new ActivityEvent("doris.source.termination_unverified"));
                throw new SemanticOperationException(503, "query_source_unavailable");
            }
            caller.ThrowIfCancellationRequested();
            if (work.IsCancellationRequested) throw new SemanticOperationException(503, "query_source_timeout");
        }
    }

    /// <summary>有界等待驱动任务，同时观察任何窗口外异常；不能用本机等待充当源端证明。</summary>
    private static async Task BoundAsync(Task operation, CancellationToken token)
    {
        Observe(operation);
        await operation.WaitAsync(token);
    }

    /// <summary>即使调用者已返回，仍收取驱动故障，以免晚到任务无人观察。</summary>
    private static void Observe(Task operation)
    {
        _ = operation.ContinueWith(task => _ = task.Exception, CancellationToken.None,
            TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
    }
}
