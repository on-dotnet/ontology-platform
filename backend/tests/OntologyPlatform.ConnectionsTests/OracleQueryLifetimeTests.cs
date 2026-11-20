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
        await Assert.ThrowsAsync<OperationCanceledException>(() => OracleQueryReader.ReadOwnedAsync(lifetime,
            () => Task.FromResult(source), _ => Task.FromResult(tx),
            (_, _) =>
            {
                order.Add("business-cursor-and-command-returned");
                work.Cancel();
                return Task.FromResult(new List<OracleMappingRow>());
            },
            _ => { order.Add("post-read"); return Task.CompletedTask; },
            () => order.Add("released"), work.Token, Stopwatch.GetTimestamp(), TimeSpan.FromSeconds(1)));
        Console.WriteLine(JsonSerializer.Serialize(new { order, lifetime.HasAcquired, lifetime.CleanupConfirmed }));
        Assert.IsTrue(lifetime.HasAcquired);
        CollectionAssert.AreEqual(new[] { "business-cursor-and-command-returned", "rollback", "transaction-disposed", "physical-disposed", "released" }, order);
        Assert.IsTrue(lifetime.CleanupConfirmed, "The returned read and complete physical release must clear this acquisition.");
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
    private sealed class Transaction(List<string> order) : DbTransaction
    {
        /// <summary>固定只读会话的隔离级别。</summary>
        public override IsolationLevel IsolationLevel => IsolationLevel.ReadCommitted;

        /// <summary>夹具事务不打开真实数据库连接。</summary>
        protected override DbConnection? DbConnection => null;

        /// <summary>只有未被取消的提交才会进入同步实现。</summary>
        public override void Commit() => order.Add("commit");

        /// <summary>记录独立清理令牌允许的回滚。</summary>
        public override void Rollback() => order.Add("rollback");

        /// <summary>在回滚后记录真正的事务释放返回点。</summary>
        public override ValueTask DisposeAsync()
        {
            order.Add("transaction-disposed");
            return ValueTask.CompletedTask;
        }
    }
}
