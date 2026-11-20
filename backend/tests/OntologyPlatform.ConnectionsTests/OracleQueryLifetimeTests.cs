using System.Data;
using System.Data.Common;
using System.Diagnostics;
using System.Text.Json;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>以受控的 I/O 完成点验证正式 reader 的资源归还顺序和原截止，无需打开数据库。</summary>
[TestClass]
public sealed class OracleQueryLifetimeTests
{
    /// <summary>业务游标及命令返回后取消，原事务回滚，物理释放在截止内返回时应归还准确申请。</summary>
    [TestMethod]
    public async Task NaturalReadThenCancelReleasesOwnedSource()
    {
        // 原始 HTTP/MCP 的绝对期限与独占 Oracle 分支均使用正式范围。
        using var request = new G4RequestDeadline(TimeProvider.System, CancellationToken.None);
        using var lifetime = new G4OracleSourceLifetime("synthetic-oracle-natural");
        using var work = new CancellationTokenSource();
        // 夹具仅替代 I/O，各阶段顺序、清理窗口及确认取自产品方法。
        var order = new List<string>();
        var source = new Physical(() => order.Add("physical-disposed"));
        var tx = new Transaction(order);
        // 独立消费者需要驱动实际清理起点和最终原截止，两者绑定相同申请。
        var cleanup = new List<OracleQueryReader.CleanupObservation>();
        await Assert.ThrowsAsync<OperationCanceledException>(() => OracleQueryReader.ReadOwnedAsync(lifetime,
            () => Task.FromResult(source), _ => Task.FromResult(tx),
            (_, _, _, _) =>
            {
                order.Add("business-cursor-and-command-returned");
                work.Cancel();
                return Task.FromResult(new List<OracleMappingRow>());
            },
            _ => { order.Add("post-read"); return Task.CompletedTask; },
            () => order.Add("released"), work.Token, Stopwatch.GetTimestamp(), TimeSpan.FromSeconds(1), reportCleanup: cleanup.Add));
        Console.WriteLine(JsonSerializer.Serialize(new { order, lifetime.HasAcquired, lifetime.CleanupConfirmed }));
        Assert.IsTrue(lifetime.HasAcquired);
        CollectionAssert.AreEqual(new[] { "WORK_CANCELLED", "WORK_FAILURE", "RESOURCE_FAILURE", "PHYSICAL_DISPOSE", "FINAL" },
            cleanup.Select(point => point.Trigger).ToArray());
        Assert.AreEqual(1, cleanup.Select(point => point.Acquisition).Distinct().Count());
        Assert.AreEqual(cleanup.Min(point => point.DeadlineUtc), cleanup[^1].DeadlineUtc);
        Assert.IsTrue(cleanup.All(point => point.Utc.AddTicks(point.RemainingTicks) == point.DeadlineUtc
            && point.RemainingTicks > 0 && point.RemainingTicks <= TimeSpan.FromMilliseconds(250).Ticks));
        CollectionAssert.AreEqual(new[] { "business-cursor-and-command-returned", "rollback", "transaction-disposed", "physical-disposed", "released" }, order);
        Assert.IsTrue(lifetime.CleanupConfirmed, "The returned read and complete physical release must clear this acquisition.");
    }

    /// <summary>健康读取完成原后验和物理释放，且重复确认不能影响下一次准确申请。</summary>
    [TestMethod]
    public async Task HealthyReadReturnsAfterEveryOwnedResource()
    {
        // 成功基线与失败回归通过同一个生产入口并共享原请求期限。
        using var request = new G4RequestDeadline(TimeProvider.System, CancellationToken.None);
        using var lifetime = new G4OracleSourceLifetime("synthetic-oracle-healthy");
        var order = new List<string>();
        var acquisition = Guid.Empty;
        var source = new Physical(() => order.Add("physical"));
        var tx = new Transaction(order);
        var rows = await OracleQueryReader.ReadOwnedAsync(lifetime, () => Task.FromResult(source), _ => Task.FromResult(tx),
            (_, _, _, _) => Task.FromResult(new List<OracleMappingRow>()),
            _ => { order.Add("post"); return Task.CompletedTask; },
            () => order.Add("released"), CancellationToken.None, Stopwatch.GetTimestamp(), TimeSpan.FromSeconds(1),
            (phase, id) => { acquisition = id; order.Add(phase); });
        Assert.IsEmpty(rows);
        CollectionAssert.AreEqual(new[] { "ACQUIRED", "READ_RETURNED", "commit", "COMMITTED", "transaction-disposed",
            "TX_DISPOSED", "POST_STARTED", "post", "POST_RETURNED", "physical", "released", "PHYSICAL_DISPOSED", "CONFIRMED" }, order);
        Assert.AreNotEqual(Guid.Empty, acquisition);
        Assert.IsTrue(lifetime.CleanupConfirmed);
        Assert.ThrowsExactly<InvalidOperationException>(() => lifetime.ConfirmReleased(acquisition));
        var next = lifetime.BeginSource();
        Assert.ThrowsExactly<InvalidOperationException>(() => lifetime.ConfirmReleased(acquisition));
        Assert.IsFalse(lifetime.CleanupConfirmed);
        lifetime.ConfirmReleased(next);
        Assert.IsTrue(lifetime.CleanupConfirmed);
    }

    /// <summary>只有 EOF 或任何一级资源收尾失败，都不能清除本次占位；已启动的后验失败同样封闭。</summary>
    [TestMethod]
    [DataRow("cursor-dispose")]
    [DataRow("command-dispose")]
    [DataRow("rollback")]
    [DataRow("transaction-dispose")]
    [DataRow("physical-dispose")]
    [DataRow("post-read")]
    public async Task IncompleteOwnedResourceRetainsAcquisition(string failure)
    {
        // 当前请求、工作令牌及真实生命周期保持和正式调用相同的嵌套关系。
        using var request = new G4RequestDeadline(TimeProvider.System, CancellationToken.None);
        using var lifetime = new G4OracleSourceLifetime("synthetic-oracle-unknown");
        using var work = new CancellationTokenSource();
        // 单一阶段抛出有辨识性的夹具异常，不增加等待或其他源请求。
        var order = new List<string>();
        void Stage(string stage)
        {
            order.Add(stage);
            if (stage == failure) throw new IOException(stage);
        }
        var connection = new Physical(() => Stage("physical-dispose"));
        var transaction = new Transaction(order, Stage);
        var error = await Assert.ThrowsAsync<IOException>(() => OracleQueryReader.ReadOwnedAsync(lifetime,
            () => Task.FromResult(connection), _ => Task.FromResult(transaction),
            (_, _, _, _) =>
            {
                Stage("eof");
                Stage("cursor-dispose");
                Stage("command-dispose");
                if (failure == "rollback") work.Cancel();
                return Task.FromResult(new List<OracleMappingRow>());
            },
            _ => { Stage("post-read"); return Task.CompletedTask; },
            () => order.Add("released"), work.Token, Stopwatch.GetTimestamp(), TimeSpan.FromSeconds(1)));
        Assert.AreEqual(failure, error.Message);
        Assert.IsTrue(lifetime.HasAcquired);
        Assert.IsFalse(lifetime.CleanupConfirmed);
        Assert.ThrowsExactly<InvalidOperationException>(() => lifetime.BeginSource());
        Assert.IsTrue(order.Contains("physical-dispose"));
    }

    /// <summary>已提交只读事务后、后验前收到取消，或整个后验已经返回，均按物理事实确认清理。</summary>
    [TestMethod]
    [DataRow("TX_DISPOSED")]
    [DataRow("POST_RETURNED")]
    public async Task CancelAtKnownBoundarySkipsUnstartedWork(string cancelAt)
    {
        // 使用生产阶段通知精确触发取消，真实运行没有此测试回调。
        using var request = new G4RequestDeadline(TimeProvider.System, CancellationToken.None);
        using var lifetime = new G4OracleSourceLifetime("synthetic-oracle-known");
        using var work = new CancellationTokenSource();
        var order = new List<string>();
        var ids = new List<Guid>();
        var connection = new Physical(() => order.Add("physical"));
        var transaction = new Transaction(order);
        await Assert.ThrowsAsync<OperationCanceledException>(() => OracleQueryReader.ReadOwnedAsync(lifetime,
            () => Task.FromResult(connection), _ => Task.FromResult(transaction), (_, _, _, _) => Task.FromResult(new List<OracleMappingRow>()),
            _ => { order.Add("metadata"); return Task.CompletedTask; }, () => order.Add("released"), work.Token,
            Stopwatch.GetTimestamp(), TimeSpan.FromSeconds(1), (phase, id) =>
            {
                order.Add(phase);
                ids.Add(id);
                if (phase == cancelAt) work.Cancel();
            }));
        Assert.AreEqual(cancelAt == "POST_RETURNED", order.Contains("metadata"));
        Assert.AreEqual(1, ids.Distinct().Count());
        Assert.AreEqual("CONFIRMED", order[^1]);
        Assert.IsTrue(lifetime.CleanupConfirmed);
    }

    /// <summary>后验仍在途时不提前确认和释放；等待完成后，后验异常不能被业务 EOF 覆盖。</summary>
    [TestMethod]
    public async Task ActivePostReadKeepsOwnerUntilItActuallyReturns()
    {
        // 屏障只在夹具的后验 I/O 内，不改变正式 SQL 或源读取策略。
        using var request = new G4RequestDeadline(TimeProvider.System, CancellationToken.None);
        using var lifetime = new G4OracleSourceLifetime("synthetic-oracle-post");
        using var work = new CancellationTokenSource();
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var finish = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var order = new List<string>();
        var connection = new Physical(() => order.Add("physical"));
        var tx = new Transaction(order);
        var running = OracleQueryReader.ReadOwnedAsync(lifetime, () => Task.FromResult(connection), _ => Task.FromResult(tx),
            (_, _, _, _) => Task.FromResult(new List<OracleMappingRow>()), async _ =>
            {
                entered.SetResult();
                await finish.Task.WaitAsync(TimeSpan.FromSeconds(1));
                work.Token.ThrowIfCancellationRequested();
            }, () => order.Add("released"), work.Token, Stopwatch.GetTimestamp(), TimeSpan.FromSeconds(1));
        try
        {
            await entered.Task.WaitAsync(TimeSpan.FromSeconds(1));
            work.Cancel();
            Assert.IsFalse(running.IsCompleted);
            Assert.IsFalse(lifetime.CleanupConfirmed);
            Assert.IsFalse(order.Contains("physical"));
        }
        finally
        {
            finish.TrySetResult();
            await Assert.ThrowsAsync<OperationCanceledException>(() => running.WaitAsync(TimeSpan.FromSeconds(1)));
        }
        Assert.IsFalse(lifetime.CleanupConfirmed);
        Assert.IsTrue(order.Contains("physical"));
    }

    /// <summary>已实际返回的 Dispose 越过任一原截止都不确认，且错误申请不会改变状态。</summary>
    [TestMethod]
    [DataRow("cleanup")]
    [DataRow("branch")]
    [DataRow("request")]
    public async Task LatePhysicalReturnCannotReopenOriginalDeadline(string boundary)
    {
        // 只推进本测试的单调时钟，避免真实睡眠影响截止先后次序。
        var clock = new ManualClock();
        using var request = new G4RequestDeadline(clock, CancellationToken.None);
        using var lifetime = new G4OracleSourceLifetime("synthetic-oracle-late", clock);
        using var work = new CancellationTokenSource();
        lifetime.TightenCleanup(TimeSpan.FromSeconds(1));
        if (boundary == "request") request.Tighten(100);
        var order = new List<string>();
        var connection = new Physical(() => clock.Advance(boundary switch { "cleanup" => 251, "branch" => 1001, _ => 101 }));
        var transaction = new Transaction(order);
        // 记录真实申请，验证迟到的准确身份也不能把旧时限重新打开。
        var acquisition = Guid.Empty;
        var run = OracleQueryReader.ReadOwnedAsync(lifetime, () => Task.FromResult(connection), _ => Task.FromResult(transaction),
            (_, _, _, _) =>
            {
                if (boundary == "cleanup") work.Cancel();
                return Task.FromResult(new List<OracleMappingRow>());
            }, _ => Task.CompletedTask, () => order.Add("released"), work.Token, Stopwatch.GetTimestamp(), TimeSpan.FromSeconds(1),
            (_, id) => acquisition = id);
        if (boundary == "cleanup") await Assert.ThrowsAsync<OperationCanceledException>(() => run);
        else await run;
        Assert.IsTrue(order.Contains("released"));
        Assert.IsFalse(lifetime.CleanupConfirmed);
        Assert.AreNotEqual(Guid.Empty, acquisition);
        Assert.ThrowsExactly<InvalidOperationException>(() => lifetime.ConfirmReleased(acquisition));
        Assert.ThrowsExactly<InvalidOperationException>(() => lifetime.ConfirmReleased(Guid.NewGuid()));
        Assert.ThrowsExactly<InvalidOperationException>(() => lifetime.BeginSource());
    }

    /// <summary>没有外部取消令牌时，工作失败开始的 250ms 也由回滚和持有人结算共同消费。</summary>
    [TestMethod]
    public async Task OriginalRollbackWindowSurvivesSourceFailure()
    {
        // 让实际回滚步骤消费 200ms；物理释放返回时只能剩下 50ms，不能从执行器重新起算。
        var clock = new ManualClock();
        using var request = new G4RequestDeadline(clock, CancellationToken.None);
        using var lifetime = new G4OracleSourceLifetime("synthetic-oracle-rollback-start", clock);
        lifetime.TightenCleanup(TimeSpan.FromSeconds(1));
        var order = new List<string>();
        var connection = new Physical(() => order.Add("physical"));
        var tx = new Transaction(order, stage => { if (stage == "rollback") clock.Advance(200); });
        await Assert.ThrowsAsync<IOException>(() => OracleQueryReader.ReadOwnedAsync(lifetime,
            () => Task.FromResult(connection), _ => Task.FromResult(tx),
            (_, _, _, _) => throw new IOException("source-failure"), _ => Task.CompletedTask,
            () => order.Add("released"), CancellationToken.None, Stopwatch.GetTimestamp(), TimeSpan.FromSeconds(1)));
        Console.WriteLine($"rollbackMs=200 remainingMs={lifetime.CleanupRemaining?.TotalMilliseconds}");
        Assert.IsTrue(lifetime.CleanupRemaining is { } left && left > TimeSpan.Zero && left <= TimeSpan.FromMilliseconds(50));
        Assert.IsFalse(lifetime.CleanupConfirmed);
    }

    /// <summary>仅为截止反例提供可同步推进的单调时间，不改变宿主时钟。</summary>
    private sealed class ManualClock : TimeProvider
    {
        /// <summary>从测试开始累计的时钟刻度。</summary>
        private long ticks;

        /// <summary>采用 TimeSpan 刻度，使 250 毫秒边界可精确表示。</summary>
        public override long TimestampFrequency => TimeSpan.TicksPerSecond;

        /// <summary>返回当前夹具的单调时间。</summary>
        public override long GetTimestamp() => ticks;

        /// <summary>模拟物理资源在原期限后才返回。</summary>
        public void Advance(int milliseconds) => ticks += TimeSpan.FromMilliseconds(milliseconds).Ticks;
    }

    /// <summary>由测试控制完成或失败的物理释放回调。</summary>
    private sealed class Physical(Action dispose) : IAsyncDisposable
    {
        /// <summary>将物理释放的返回点交给当前夹具记录。</summary>
        public ValueTask DisposeAsync()
        {
            dispose();
            return ValueTask.CompletedTask;
        }
    }

    /// <summary>使用既有 ADO 事务行为在取消时拒绝提交，回滚和释放均能独立观察。</summary>
    private sealed class Transaction(List<string> order, Action<string>? stage = null) : DbTransaction
    {
        /// <summary>固定只读会话的隔离级别。</summary>
        public override IsolationLevel IsolationLevel => IsolationLevel.ReadCommitted;

        /// <summary>夹具事务不打开真实数据库连接。</summary>
        protected override DbConnection? DbConnection => null;

        /// <summary>只有未被取消的提交才会进入同步实现。</summary>
        public override void Commit() => order.Add("commit");

        /// <summary>记录独立清理令牌允许的回滚。</summary>
        public override void Rollback()
        {
            order.Add("rollback");
            stage?.Invoke("rollback");
        }

        /// <summary>在回滚后记录真正的事务释放返回点。</summary>
        public override ValueTask DisposeAsync()
        {
            order.Add("transaction-disposed");
            stage?.Invoke("transaction-dispose");
            return ValueTask.CompletedTask;
        }
    }
}
