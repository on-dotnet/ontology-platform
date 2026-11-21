using System.Diagnostics;
using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.SemanticQuery;

namespace OntologyPlatform.QueryTests;

/// <summary>健康源返回后，在已准入的独立 PostgreSQL 中复核准确行的提交、取消和锁等待。</summary>
public sealed partial class G4QueryRaceTests
{
    /// <summary>取消先赢、取消后同一行越过分支截止，以及原总期限内的正常成功都走正式存储。</summary>
    [TestMethod]
    [DataRow("cancel-timely")]
    [DataRow("cancel-lock-late")]
    [DataRow("success-after-branch")]
    [DataRow("final-403")]
    [DataRow("final-409")]
    [DataRow("final-audit-fault")]
    [DataRow("final-wrong-owner")]
    [DataRow("final-wrong-fence")]
    [DataRow("final-lock-expired")]
    [DataRow("final-cancel-won")]
    [DataRow("final-unconfirmed")]
    [DataRow("final-late")]
    [DataRow("final-wrong-origin")]
    public Task HealthyReaderThenPostgresRace(string path) => VerifyCapacityAsync(true, path);

    /// <summary>使用驱动已核身份的测试库与真实治理会话，受控空读者仅提供源观察的确定顺序。</summary>
    private static async Task VerifyPostReadRaceAsync(string path, G4QueryResultStore store, G4QueryResultStore other,
        G4QueryRecord lease, MappingAuthorizationProof session, MappingAuthorizationProof proof, G4QueryDbContext locker, GovernanceDbContext audits)
    {
        // 与产品 Gateway 相同的单调根截止，从本次已准入行继续收紧。
        using var root = new G4RequestDeadline(TimeProvider.System, CancellationToken.None);
        root.Tighten(lease.DeadlineAtUtc);
        // 在任何结算测时前准备 SQL 模型及数据库路径，避免将其首调成本计入行锁窗口。
        var missing = new G4QueryRecord { Id = "absent-" + lease.Id, LeaseOwner = lease.LeaseOwner, Fence = 1 };
        await store.FailOracleAsync(missing, session.Scope, session.Actor, () => TimeSpan.FromMilliseconds(250), CancellationToken.None);
        Assert.IsFalse(await store.ConfirmOracleCleanupAsync(missing.Id, missing.LeaseOwner, 1, 2, () => TimeSpan.FromMilliseconds(250), CancellationToken.None));
        // 生产入口用独立平台连接重验租约，准确的物理申请与归还只在测试 reader 中发生。
        var execution = new G4QueryExecution(null!, null!, null!, store, TimeProvider.System);
        var branch = new G4QueryExecution.OracleExecution();
        var identity = string.Empty;
        var query = G4QueryResultStore.ReadRequest(lease);
        var state = G4QueryResultStore.ReadState(lease);
        var read = await execution.ReadOracleAsync(lease, branch, lease.DeadlineAtUtc, CancellationToken.None, store.ObserveOracleAsync, _ =>
        {
            // 保存同一次物理 scope 的身份，后续不能换成新生成的 execution。
            var lifetime = G4OracleSourceLifetime.Current!;
            identity = lifetime.ExecutionId;
            var acquired = lifetime.BeginSource();
            lifetime.ConfirmReleased(acquired);
            return Task.FromResult(new G4SourceQueryRead { EntityBindingId = "entity", Rows = [], StartedAtUtc = DateTimeOffset.UtcNow,
                CompletedAtUtc = DateTimeOffset.UtcNow, AdapterVersion = "oracle-query-v1", WatermarkKind = "UNKNOWN", Watermark = null,
                Indeterminate = false, Limited = false, RecordKeyFields = ["ROW_ID"], QueryPlanHash = new string('a', 64) });
        });
        Assert.IsTrue(branch.Confirmed);
        Assert.AreEqual(identity, branch.Lifetime?.ExecutionId);
        // 数据与回执严格对应这一次受控空读取，不把模拟空行登记为真实 Oracle 观察。
        var time = read.CompletedAtUtc.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'", System.Globalization.CultureInfo.InvariantCulture);
        var receipt = new G4SourceReadReceipt { SchemaVersion = "g4.read-receipt.v1", QueryId = lease.Id, ReceiptId = "empty-1",
            Binding = state.Binding, TraceId = session.Actor.TraceId, Scope = state.Scope, SourceDatasetRef = "dataset-1", Status = "EMPTY",
            AdapterVersion = read.AdapterVersion, QueryPlanHash = read.QueryPlanHash, RowCount = 0, Limited = false, WatermarkKind = "UNKNOWN", Watermark = null,
            Precision = "DATASET", SourceRecordRef = null, ValidTime = null, ReadStartedAtUtc = time, ReadCompletedAtUtc = time,
            ResultHash = G4QueryCanonical.Hash(G4QueryCanonical.Projection([])) };
        var result = new G4QueryResultV1 { SchemaVersion = "g4.query-result.v1", Status = "EMPTY", TraceId = session.Actor.TraceId,
            ObservedAtUtc = time, ValidTime = null, Diagnostics = [], Evidence = [], Data = [], Candidates = [], Limited = false,
            Snapshot = new G4QuerySnapshot { CapabilityId = query.CapabilityId, CapabilityVersion = query.CapabilityVersion,
                OntologyReleaseId = state.Binding.OntologyReleaseId, MappingReleaseIds = [state.Binding.MappingReleaseId],
                SourceCatalogSnapshotIds = [state.Binding.CurrentCatalogSnapshotId] },
            SubSources = [new G4QuerySubSource { ConnectionId = state.Binding.ConnectionId, Status = "EMPTY", Limited = false, ObservedAtUtc = time,
                SourceReadReceiptId = receipt.ReceiptId, WatermarkKind = "UNKNOWN" }] };
        Task Complete() => store.CompleteAsync(lease, session, [proof], query, state, result,
            [new G4QueryStoredReceipt { Receipt = receipt, ReceiptHash = G4QueryCanonical.Hash(G4QueryCanonical.Serialize(receipt)) }], CancellationToken.None);
        // 独立计时源和生产分支使用相同的 System 单调时基。
        TimeSpan Elapsed() => Stopwatch.GetElapsedTime(branch.Started);
        if (path.StartsWith("final-", StringComparison.Ordinal))
        {
            // 第二实际源未确认或晚释放时，首个健康分支不能为整次读取背书。
            if (path is "final-unconfirmed" or "final-late")
            {
                await Assert.ThrowsAsync<SemanticOperationException>(() => execution.ReadOracleAsync(lease, branch,
                    lease.DeadlineAtUtc, CancellationToken.None, store.ObserveOracleAsync, async _ =>
                    {
                        // 此分支确实开始，待归还的独立申请与第一个健康范围分离。
                        var lifetime = G4OracleSourceLifetime.Current!;
                        var acquisition = lifetime.BeginSource();
                        if (path == "final-late")
                        {
                            await Task.Delay(1010);
                            Assert.ThrowsExactly<InvalidOperationException>(() => lifetime.ConfirmReleased(acquisition));
                        }
                        return read;
                    }));
            }
            // 源截止已经过去，普通最终授权或绑定拒绝的根预算仍然有效。
            while (Elapsed() <= TimeSpan.FromSeconds(1)) await Task.Delay(4);
            if (path == "final-403")
            {
                // 更新仅属本夹具、该主体与连接的真实 grant，使最终治理复核拒绝。
                var grant = await audits.MappingAuthorizationGrants.SingleAsync(g => g.SubjectId == session.Actor.SubjectId &&
                    g.OrganizationId == session.Actor.OrganizationId && g.ConnectionId == state.Binding.ConnectionId);
                grant.RevokedAtUtc = DateTimeOffset.UtcNow;
                await audits.SaveChangesAsync();
            }
            // 使用生产完成事务的参与者及显式回滚，不能把构造的同名异常冒充最终拒绝。
            var rejected = await Assert.ThrowsAsync<SemanticOperationException>(() => other.CompleteAsync(lease, session,
                [proof], query, state, result, [new G4QueryStoredReceipt { Receipt = receipt,
                    ReceiptHash = G4QueryCanonical.Hash(G4QueryCanonical.Serialize(receipt)) }], root.Token, branch));
            Assert.AreEqual(path == "final-403" ? (403, "query_forbidden") : (409, "query_binding_stale"), (rejected.Status, rejected.Code));
            if (path == "final-wrong-owner")
                await locker.Queries.Where(q => q.Id == lease.Id).ExecuteUpdateAsync(update => update.SetProperty(q => q.LeaseOwner, lease.LeaseOwner + "-other"));
            if (path == "final-wrong-fence")
                await locker.Queries.Where(q => q.Id == lease.Id).ExecuteUpdateAsync(update => update.SetProperty(q => q.Fence, lease.Fence + 1));
            if (path == "final-cancel-won") await store.CancelAsync(lease.Id, session, [proof], CancellationToken.None);
            // 结算实例也使用本例的审计故障注入；生产入口收到同一个回滚异常对象。
            var finalExecution = new G4QueryExecution(null!, null!, null!, other, TimeProvider.System);
            Task Settle() => finalExecution.SettleOracleOwnerAsync(lease, branch, session, root.Token,
                path == "final-wrong-origin" ? new SemanticOperationException(rejected.Status, rejected.Code) : rejected);
            if (path == "final-lock-expired")
            {
                await using var held = await locker.Database.BeginTransactionAsync();
                // 先从 PG 取持锁者 PID，再证明生产结算确实在该行锁上等待。
                var pid = (await locker.Database.SqlQuery<int>($"""
                    SELECT pg_backend_pid() AS "Value" FROM semantic_query."Queries" WHERE "Id"={lease.Id} FOR UPDATE
                    """).ToArrayAsync()).Single();
                var settling = Settle();
                try
                {
                    var waiting = false;
                    while (!waiting && root.Remaining > TimeSpan.FromMilliseconds(100))
                    {
                        waiting = await locker.Database.SqlQuery<bool>($"""
                            SELECT EXISTS (SELECT 1 FROM pg_locks l WHERE NOT l.granted AND {pid}=ANY(pg_blocking_pids(l.pid))) AS "Value"
                            """).SingleAsync();
                        if (!waiting) await Task.Delay(2);
                    }
                    Assert.IsTrue(waiting);
                    await Task.Delay(root.Remaining + TimeSpan.FromMilliseconds(10));
                }
                finally
                {
                    await held.CommitAsync();
                    await settling.WaitAsync(TimeSpan.FromSeconds(2));
                }
            }
            else await Settle();
            // 新数据库读取同时核行、准确 fence、两租约列、成功副作用及一次失败审计。
            var after = await locker.Queries.AsNoTracking().SingleAsync(q => q.Id == lease.Id);
            var released = path is "final-403" or "final-409";
            Assert.AreEqual(released ? "FAILED" : path == "final-cancel-won" ? "CANCELLED" : "RUNNING", after.ExecutionStatus);
            Assert.AreEqual(released || path is "final-cancel-won" or "final-wrong-fence" ? lease.Fence + 1 : lease.Fence, after.Fence);
            Assert.AreEqual(released ? null : path == "final-wrong-owner" ? lease.LeaseOwner + "-other" : lease.LeaseOwner, after.LeaseOwner);
            Assert.AreEqual(released, after.LeaseUntilUtc is null);
            Assert.AreEqual(0, after.ResultCiphertext.Length);
            Assert.IsNull(after.ResultHash);
            Assert.AreEqual(0, after.ResultSize);
            Assert.AreEqual(0, G4QueryResultStore.ReadState(after).Receipts.Length);
            Assert.AreEqual(released ? 1 : 0, await audits.AuditRecords.CountAsync(a => a.Resource == lease.Id && a.Action == "data.query.execute" && a.Outcome == "failure"));
            Assert.IsFalse(await audits.AuditRecords.AnyAsync(a => a.Resource == lease.Id && a.Action == "data.query.execute" && a.Outcome == "allowed"));
            return;
        }
        if (path == "success-after-branch")
        {
            // 确认释放完成后，成功提交只受五秒总期限限制。
            while (Elapsed() <= TimeSpan.FromSeconds(1)) await Task.Delay(4);
            await Complete();
            Assert.AreEqual("query_already_finished", (await Assert.ThrowsAsync<SemanticOperationException>(() =>
                other.CancelAsync(lease.Id, session, [proof], CancellationToken.None))).Code);
        }
        else
        {
            if (path == "cancel-lock-late")
            {
                // 在原分支约剩 140ms 时提交取消。数据库给出的准确清理截止仍单独核验。
                while (Elapsed() < TimeSpan.FromMilliseconds(860)) await Task.Delay(1);
            }
            var cancelled = await other.CancelAsync(lease.Id, session, [proof], CancellationToken.None);
            Assert.AreEqual(lease.LeaseOwner, cancelled.LeaseOwner);
            Assert.AreEqual(lease.Fence + 1, cancelled.Fence);
            if (path == "cancel-timely")
            {
                await execution.SettleOracleOwnerAsync(lease, branch, session, CancellationToken.None);
            }
            else
            {
                // 由真实 PG FOR UPDATE 取得该 query 的准确行锁；数据库等待图证明生产写者已经到达。
                await using var hold = await locker.Database.BeginTransactionAsync();
                var pid = (await locker.Database.SqlQuery<int>($"""
                    SELECT pg_backend_pid() AS "Value" FROM semantic_query."Queries" WHERE "Id"={lease.Id} FOR UPDATE
                    """).ToArrayAsync()).Single();
                var settling = execution.SettleOracleOwnerAsync(lease, branch, session, CancellationToken.None);
                try
                {
                    var waited = false;
                    while (Elapsed() < TimeSpan.FromSeconds(1))
                    {
                        waited = await locker.Database.SqlQuery<bool>($"""
                            SELECT EXISTS (SELECT 1 FROM pg_locks l WHERE NOT l.granted AND {pid}=ANY(pg_blocking_pids(l.pid))) AS "Value"
                            """).SingleAsync();
                        if (waited) break;
                        await Task.Delay(1);
                    }
                    Assert.IsTrue(waited, "生产结算须在原分支截止前等待准确行锁。");
                    while (Elapsed() <= TimeSpan.FromSeconds(1)) await Task.Delay(1);
                    Assert.IsTrue(await locker.Database.SqlQuery<bool>($"""
                        SELECT clock_timestamp() < LEAST("DeadlineAtUtc","LeaseUntilUtc") AS "Value" FROM semantic_query."Queries" WHERE "Id"={lease.Id}
                        """).SingleAsync(), "行锁释放时，原总期限和已持久化取消期限都应仍在未来。");
                }
                finally
                {
                    await hold.CommitAsync();
                    await settling.WaitAsync(TimeSpan.FromSeconds(2));
                }
            }
            Assert.AreEqual("query_execution_stale", (await Assert.ThrowsAsync<SemanticOperationException>(Complete)).Code);
        }
        // 由新的非跟踪读取和治理原表确认胜者及副作用。
        var saved = await locker.Queries.AsNoTracking().SingleAsync(q => q.Id == lease.Id);
        var wonSuccess = path == "success-after-branch";
        Assert.AreEqual(wonSuccess ? "COMPLETED" : "CANCELLED", saved.ExecutionStatus);
        Assert.AreEqual(wonSuccess ? lease.Fence : lease.Fence + 1, saved.Fence);
        Assert.AreEqual(path == "cancel-lock-late" ? lease.LeaseOwner : null, saved.LeaseOwner);
        Assert.AreEqual(wonSuccess, saved.ResultHash is not null && saved.ResultCiphertext.Length > 0);
        Assert.AreEqual(wonSuccess ? 1 : 0, G4QueryResultStore.ReadState(saved).Receipts.Length);
        Assert.AreEqual(wonSuccess ? 0 : 1, await audits.AuditRecords.CountAsync(a => a.Resource == lease.Id && a.Action == "data.query.cancel" && a.Outcome == "allowed"));
        Assert.AreEqual(wonSuccess ? 1 : 0, await audits.AuditRecords.CountAsync(a => a.Resource == lease.Id && a.Action == "data.query.execute" && a.Outcome == "allowed"));
        Console.WriteLine($"post-read={path} query={lease.Id} execution={identity} phaseMs={Elapsed().TotalMilliseconds:F3} " +
            $"state={saved.ExecutionStatus} fence={saved.Fence} held={saved.LeaseOwner is not null}");
    }
}
