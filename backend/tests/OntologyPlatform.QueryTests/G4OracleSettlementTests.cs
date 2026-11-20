using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.SemanticQuery;

namespace OntologyPlatform.QueryTests;

/// <summary>在正式 Oracle 分支执行和失败持有人结算入口验证原截止及准确源身份，替代 I/O 不接数据库。</summary>
[TestClass]
public sealed class G4OracleSettlementTests
{
    /// <summary>读取抛错但物理已释放时，不应把该次执行的截止或关联身份当作健康分支清掉。</summary>
    [TestMethod]
    [DataRow("timely")]
    [DataRow("past-cleanup")]
    [DataRow("during-first-write")]
    [DataRow("past-branch")]
    [DataRow("healthy")]
    public async Task OriginalExecutionDeadlineGovernsSettlement(string scenario)
    {
        // 使用手动单调时间标记，使两个持久调用的开始时刻可确定而无计时器调度竞争。
        var clock = new ManualClock();
        using var request = new G4RequestDeadline(clock, CancellationToken.None);
        // 平台持久 I/O 与源行读取由当前夹具提供；真实分支门禁、观察及交回顺序保持。
        var execution = new G4QueryExecution(null!, null!, null!, null!, clock);
        var state = new G4QueryExecution.OracleExecution();
        var lease = new G4QueryRecord { Id = "synthetic-oracle-settlement", DeadlineAtUtc = request.DeadlineUtc,
            LeaseOwner = "oracle-execution-owner", Fence = 1 };
        var executionId = string.Empty;
        Task<G4SourceQueryRead> Read(CancellationToken _)
        {
            // 产品源真实返回前必须先完成准确物理申请；这里只控制已完成这一种源状态。
            var live = G4OracleSourceLifetime.Current!;
            executionId = live.ExecutionId;
            var acquired = live.BeginSource();
            if (scenario == "past-branch") clock.Advance(900);
            live.ConfirmReleased(acquired);
            if (scenario == "healthy") return Task.FromResult<G4SourceQueryRead>(null!);
            throw new IOException("reader-failed-after-release");
        }
        var branch = execution.ReadOracleAsync(lease, state, request.DeadlineUtc, CancellationToken.None,
            (_, _) => Task.FromResult<G4QueryResultStore.OracleLeaseObservation?>(new() { Active = true }), Read);
        if (scenario == "healthy")
        {
            await branch;
            Assert.IsTrue(state.Confirmed);
            Assert.IsNull(state.BranchLimit);
            Assert.IsNull(state.Lifetime);
            return;
        }
        await Assert.ThrowsAsync<IOException>(() => branch);
        // 原截止前/后以及第一笔结算已完成但第二笔已越限分别留有独立见证。
        if (scenario == "past-cleanup") clock.Advance(251);
        if (scenario == "past-branch") clock.Advance(101);
        var failed = 0;
        var confirmed = 0;
        await execution.FinishOracleFailureAsync(lease, state, CancellationToken.None, _ =>
        {
            failed++;
            if (scenario == "during-first-write") clock.Advance(251);
            return Task.CompletedTask;
        }, _ => { confirmed++; return Task.FromResult(true); });
        Console.WriteLine($"scenario={scenario} hasLifetime={state.Lifetime != null} branchBound={state.BranchLimit != null} fail={failed} cas={confirmed}");
        Assert.AreEqual(scenario is "timely" or "during-first-write" ? 1 : 0, failed);
        Assert.AreEqual(scenario == "timely" ? 1 : 0, confirmed);
        Assert.AreEqual(executionId, state.Lifetime?.ExecutionId);
        Assert.AreEqual(TimeSpan.FromSeconds(1), state.BranchLimit);
    }

    /// <summary>同时推进本地 UTC 和单调时基；测试不依赖系统定时器回调调度来发现过期。</summary>
    private sealed class ManualClock : TimeProvider
    {
        /// <summary>从夹具进入起使用的逻辑刻度。</summary>
        private long ticks;

        /// <summary>每秒采用固定的 TimeSpan 刻度。</summary>
        public override long TimestampFrequency => TimeSpan.TicksPerSecond;

        /// <summary>返回当前单调值。</summary>
        public override long GetTimestamp() => ticks;

        /// <summary>租约绝对时间与本地单调源使用同一夹具时基。</summary>
        public override DateTimeOffset GetUtcNow() => DateTimeOffset.UnixEpoch.AddTicks(ticks);

        /// <summary>定向模拟原窗口中已消费的毫秒。</summary>
        public void Advance(int milliseconds) => ticks += TimeSpan.FromMilliseconds(milliseconds).Ticks;
    }
}
