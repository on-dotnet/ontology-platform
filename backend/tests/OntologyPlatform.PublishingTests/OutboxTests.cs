using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Modules.Publishing;

namespace OntologyPlatform.PublishingTests;

/// <summary>真实持久Outbox的后台运行、重启恢复、重复消费和过期fence矩阵。</summary>
[TestClass]
public sealed class OutboxTests
{
    /// <summary>实际BackgroundService接管过期租约，成功回验后唯一消费，重派不重复回执。</summary>
    [TestMethod]
    public async Task BackgroundRestartAndDuplicateConsume()
    {
        // 当前fixture提供真实三服务和实际发布事务。
        using var fixture = new PublishingFixture();
        // 合法提案和批准产生待派发持久事件。
        var item = await fixture.ProposalAsync();
        // 活动事务确实提交事件。
        var activation = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(await fixture.ApproveAsync(item.Proposal)), default);
        // 模拟进程在持久租约之后退出；数据而非内存状态决定恢复。
        await fixture.Database.Outbox.Where(row => row.EventId == activation.OutboxEventId).ExecuteUpdateAsync(update => update.SetProperty(row => row.LeaseOwner, "terminated-worker").SetProperty(row => row.LeaseUntilUtc, DateTimeOffset.UtcNow.AddMinutes(-1)).SetProperty(row => row.FencingToken, 7));
        // 真正调用BackgroundService生命周期，而不是仅直接调用私有逻辑。
        using var worker = new ReleaseOutboxDispatcher(fixture.Provider.GetRequiredService<IServiceScopeFactory>(), fixture.Clock);
        await worker.StartAsync(default);
        // 有界等待真实数据库回执，未成功必须明确测试失败。
        var deadline = DateTimeOffset.UtcNow.AddSeconds(30);
        while (!await fixture.Database.Receipts.AnyAsync(row => row.EventId == activation.OutboxEventId) && DateTimeOffset.UtcNow < deadline) await Task.Delay(100);
        await worker.StopAsync(default);
        Assert.AreEqual(1, await fixture.Database.Receipts.CountAsync(row => row.EventId == activation.OutboxEventId));
        // 已消费事件再次可见模拟至少一次重派，唯一eventId防止重复持久消费。
        await fixture.Database.Outbox.Where(row => row.EventId == activation.OutboxEventId).ExecuteUpdateAsync(update => update.SetProperty(row => row.DispatchedAtUtc, (DateTimeOffset?)null).SetProperty(row => row.NextAttemptAtUtc, DateTimeOffset.UtcNow.AddSeconds(-1)));
        // 新worker实例体现进程重启后的持久去重，而不是内存记忆。
        using var restarted = new ReleaseOutboxDispatcher(fixture.Provider.GetRequiredService<IServiceScopeFactory>(), fixture.Clock);
        Assert.IsTrue(await restarted.DispatchOnceAsync(default));
        Assert.AreEqual(1, await fixture.Database.Receipts.CountAsync(row => row.EventId == activation.OutboxEventId));
        // 接管及重派均递增fence，旧worker不能再提交。
        Assert.IsTrue((await fixture.Database.Outbox.AsNoTracking().SingleAsync(row => row.EventId == activation.OutboxEventId)).FencingToken >= 9);
    }

    /// <summary>调和中途租约被新worker接管时，旧fence无法标记派发成功。</summary>
    [TestMethod]
    public async Task StaleFenceCannotCommitConsumption()
    {
        // 真实发布事件作为调和对象。
        using var fixture = new PublishingFixture();
        // 准备当前测试合法发布。
        var item = await fixture.ProposalAsync();
        // 取得实际Outbox主键。
        var activation = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(await fixture.ApproveAsync(item.Proposal)), default);
        // 清空其他测试已经到期的待派发项，当前事件按唯一时间优先供本worker领取。
        await fixture.Database.Outbox.Where(row => row.EventId == activation.OutboxEventId).ExecuteUpdateAsync(update => update.SetProperty(row => row.CreatedAtUtc, DateTimeOffset.UnixEpoch));
        // 门只阻塞当前固定版本的真实GET，不伪造响应。
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        // 控制在实际IO期间接管租约。
        var releaseGate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        fixture.Gate = async (request, token) =>
        {
            if (request.Method == HttpMethod.Get && request.RequestUri!.AbsolutePath.Contains(activation.ReleaseId, StringComparison.Ordinal))
            {
                entered.TrySetResult();
                await releaseGate.Task.WaitAsync(token);
            }
        };
        // 独立worker领取真实租约并进入外部回验。
        using var worker = new ReleaseOutboxDispatcher(fixture.Provider.GetRequiredService<IServiceScopeFactory>(), fixture.Clock);
        // 暂不等待完成，先实际修改数据库fence。
        var running = worker.DispatchOnceAsync(default);
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(10));
        await fixture.Database.Outbox.Where(row => row.EventId == activation.OutboxEventId).ExecuteUpdateAsync(update => update.SetProperty(row => row.FencingToken, row => row.FencingToken + 1).SetProperty(row => row.LeaseOwner, "replacement-worker"));
        releaseGate.TrySetResult();
        Assert.IsTrue(await running);
        Assert.AreEqual(0, await fixture.Database.Receipts.CountAsync(row => row.EventId == activation.OutboxEventId));
        Assert.IsNull((await fixture.Database.Outbox.AsNoTracking().SingleAsync(row => row.EventId == activation.OutboxEventId)).DispatchedAtUtc);
        fixture.Gate = null;
        await fixture.Database.Outbox.Where(row => row.EventId == activation.OutboxEventId).ExecuteUpdateAsync(update => update.SetProperty(row => row.LeaseUntilUtc, DateTimeOffset.UtcNow.AddSeconds(-1)));
        Assert.IsTrue(await worker.DispatchOnceAsync(default));
        Assert.AreEqual(1, await fixture.Database.Receipts.CountAsync(row => row.EventId == activation.OutboxEventId));
    }
}
