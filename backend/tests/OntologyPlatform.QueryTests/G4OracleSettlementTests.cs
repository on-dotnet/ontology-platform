using System.Diagnostics;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.SemanticQuery;

namespace OntologyPlatform.QueryTests;

/// <summary>在正式 Oracle 分支执行和失败持有人结算入口验证原截止及准确源身份，替代 I/O 不接数据库。</summary>
[TestClass]
public sealed class G4OracleSettlementTests
{
    /// <summary>捕获服务器在响应发送完成时交给实际传输层的回调。</summary>
    private sealed class CompleteResponse : Microsoft.AspNetCore.Http.Features.HttpResponseFeature
    {
        /// <summary>测试驱动按服务器约定在响应后执行此回调。</summary>
        internal Func<Task>? Complete { get; private set; }

        /// <summary>保存响应结束后的一次性诊断导出。</summary>
        public override void OnCompleted(Func<object, Task> callback, object state) => Complete = () => callback(state);
    }

    /// <summary>以正式传输配置和响应回调导出请求内记录，丢失计数和原子发布均可离线重开。</summary>
    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public async Task NormalTransportExportsBoundedOriginal(bool overflow)
    {
        // 使用内存开发宿主，不监听端口或建立外部连接。
        var builder = Microsoft.AspNetCore.Builder.WebApplication.CreateBuilder(new Microsoft.AspNetCore.Builder.WebApplicationOptions { EnvironmentName = "Development" });
        builder.Services.AddSingleton(TimeProvider.System);
        builder.Services.AddAuthorization(options => options.AddPolicy("data.query.execute", policy => policy.RequireAuthenticatedUser()));
        var key = Guid.NewGuid().ToString("N"); // 受控测试的准确临时导出身份。
        builder.Configuration["G4:OracleDiagnosticKey"] = key;
        await using var app = builder.Build(); // 仅消费正式 DI 中的配置及环境。
        var context = new Microsoft.AspNetCore.Http.DefaultHttpContext { RequestServices = app.Services }; // 没有网络传输。
        var response = new CompleteResponse(); // 按真实服务器响应结束时序触发。
        context.Features.Set<Microsoft.AspNetCore.Http.Features.IHttpResponseFeature>(response);
        context.Request.Path = "/api/v1/data/semantic-queries";
        context.Request.Method = "POST";
        context.Request.Headers["Idempotency-Key"] = key;
        context.Items["CorrelationId"] = Guid.NewGuid().ToString("N");
        using var activity = new Activity("normal-http").SetIdFormat(ActivityIdFormat.W3C).Start();
        context.User = new System.Security.Claims.ClaimsPrincipal(new System.Security.Claims.ClaimsIdentity(
            [new("sub", "offline-reader"), new("organization_id", "org-demo")], "offline"));
        context.Response.Body = new MemoryStream();
        var result = await OntologyPlatform.Api.G4.QueryEndpoints.TransportAsync(context, "data.query.execute", async (_, token) =>
        {
            G4OracleQueryTrace.Bind("query-0123456789abcdef0123456789abcdef");
            if (overflow)
            {
                for (var i = 0; i < 161; i++) G4OracleQueryTrace.Mark("permit");
                return Microsoft.AspNetCore.Http.Results.Ok();
            }
            // 真实源适配器在读取不存在的测试 CA 时失败，尚未连接 socket。
            var executor = new G4QueryExecution(null!, null!, null!, null!, TimeProvider.System);
            var deadline = G4RequestDeadline.Current!.DeadlineUtc;
            var lease = new G4QueryRecord { Id = "query-0123456789abcdef0123456789abcdef", DeadlineAtUtc = deadline };
            var adapter = new OntologyPlatform.Modules.Connections.OracleSourceAdapter(new() { RootCertificatePath =
                Path.Combine(Path.GetTempPath(), key, "absent.pem"), WalletDirectory = Path.Combine(Path.GetTempPath(), key) });
            var open = adapter.GetType().GetMethod("OpenMappingAsync", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)!;
            await executor.ReadOracleAsync(lease, new(), deadline, token,
                (_, _) => Task.FromResult<G4QueryResultStore.OracleLeaseObservation?>(new() { Active = true }), async work =>
                {
                    await G4OracleQueryTrace.ObserveAsync("permit", () => Task.CompletedTask);
                    var lifetime = G4OracleSourceLifetime.Current!;
                    G4OracleQueryTrace.Mark("acquisition", "returned", lifetime.BeginSource());
                    await (Task)open.Invoke(adapter, ["offline", Guid.ParseExact(lifetime.ExecutionId, "N"), work, false])!;
                    throw new AssertFailedException("意外完成了使用缺失 CA 的源打开。");
                });
            return Microsoft.AspNetCore.Http.Results.Ok();
        }, false);
        await result.ExecuteAsync(context);
        var path = Path.Combine(Path.GetTempPath(), "omq-events-" + key + ".json"); // 单次正式导出目标。
        try
        {
            Assert.IsFalse(File.Exists(path));
            await response.Complete!();
            var document = System.Text.Json.JsonSerializer.Deserialize<System.Text.Json.JsonElement>(await File.ReadAllBytesAsync(path)); // 独立读取发布的最终字节。
            if (overflow) Assert.AreEqual(160, document.GetProperty("source").GetProperty("events").GetArrayLength());
            Assert.AreEqual(overflow ? 3 : 0, document.GetProperty("source").GetProperty("dropped").GetInt32());
            // 跨语言离线运行者指定私有临时目录，保留来自正式导出的原字节。
            if (Environment.GetEnvironmentVariable("OMQ_NORMAL_OFFLINE_EXPORT") is { } directory)
                File.Copy(path, Path.Combine(directory, (overflow ? "overflow-" : "failure-") + key + ".json"));
            Assert.AreEqual(key, document.GetProperty("generation").GetString());
        }
        finally
        {
            File.Delete(path);
        }
    }

    /// <summary>对正式分支注入单个外部故障，确认实际观察器退出并保留源失败及最终保守裁决。</summary>
    [TestMethod]
    [DataRow("tls", null)]
    [DataRow("catalog", null)]
    [DataRow("disposeConnection", null)]
    [DataRow("leaseTimeout", "leaseTimeout")]
    [DataRow("leaseException", "leaseException")]
    [DataRow("workCutoff", "workCutoff")]
    public async Task NormalRequestPreservesFirstCause(string phase, string? expectedSignal)
    {
        // 根期限沿真实单调时钟运行，所有外部边界均在同次分支内等待。
        using var deadline = new G4RequestDeadline(TimeProvider.System, CancellationToken.None);
        using var trace = new G4OracleQueryTrace(); // 真实请求作用域的相同收集器。
        var id = "query-0123456789abcdef0123456789abcdef"; // 本夹具的唯一查询号。
        G4OracleQueryTrace.Bind(id);
        G4OracleQueryTrace.Mark("http");
        var execution = new G4QueryExecution(null!, null!, null!, null!, TimeProvider.System); // 只替换外部存储和源调用。
        var state = new G4QueryExecution.OracleExecution(); // 保留真实失败结算状态。
        var observations = 0; // 首次租约总是有效，故障进入原观察器。
        async Task<G4QueryResultStore.OracleLeaseObservation?> Observe(G4QueryRecord _, CancellationToken token)
        {
            if (++observations > 1)
            {
                if (phase == "leaseTimeout") await Task.Delay(Timeout.Infinite, token);
                if (phase == "leaseException") throw new IOException();
            }
            return new() { Active = true };
        }
        async Task<G4SourceQueryRead> Read(CancellationToken token)
        {
            G4OracleSourceLifetime.Current!.BeginSource();
            if (expectedSignal is not null) await Task.Delay(Timeout.Infinite, token);
            return await G4OracleQueryTrace.ObserveAsync<G4SourceQueryRead>(phase, () => throw new IOException());
        }
        // 分支外部结果保留 cleanup_unconfirmed，内存记录提供独立的首因。
        var lease = new G4QueryRecord { Id = id, DeadlineAtUtc = deadline.DeadlineUtc };
        await Assert.ThrowsAsync<SemanticOperationException>(() => execution.ReadOracleAsync(lease, state, deadline.DeadlineUtc,
            CancellationToken.None, Observe, Read));
        var output = System.Text.Json.JsonSerializer.SerializeToElement(trace.Snapshot()); // 按响应后消费者看到的原结构检查。
        Assert.AreEqual(id, output.GetProperty("queryId").GetString());
        Assert.AreEqual(expectedSignal, output.GetProperty("firstSignal").GetString());
        Assert.AreEqual(expectedSignal is null ? phase + ".failed" : "source.cancelled", output.GetProperty("firstFailure").GetString());
        var events = output.GetProperty("events").EnumerateArray().ToArray(); // 完整出口不得漏掉观察器和终判。
        Assert.IsTrue(events.Any(row => row.GetProperty("stage").GetString() == "observer" && row.GetProperty("outcome").GetString() == "returned"));
        Assert.AreEqual("unconfirmed", events[^1].GetProperty("outcome").GetString());
        Assert.IsFalse(state.Confirmed);
    }

    /// <summary>读取抛错但物理已释放时，不应把该次执行的截止或关联身份当作健康分支清掉。</summary>
    [TestMethod]
    [DataRow("timely")]
    [DataRow("past-cleanup")]
    [DataRow("during-first-write")]
    [DataRow("past-branch")]
    [DataRow("past-request")]
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
            if (scenario == "healthy") return Task.FromResult(new G4SourceQueryRead
            {
                EntityBindingId = "entity", Rows = [], StartedAtUtc = clock.GetUtcNow(), CompletedAtUtc = clock.GetUtcNow(),
                AdapterVersion = "oracle-query-v1", WatermarkKind = "UNKNOWN", Watermark = null, Indeterminate = false,
                Limited = false, RecordKeyFields = ["ROW_ID"], QueryPlanHash = new string('a', 64)
            });
            throw new IOException("reader-failed-after-release");
        }
        var branch = execution.ReadOracleAsync(lease, state, request.DeadlineUtc, CancellationToken.None,
            (_, _) => Task.FromResult<G4QueryResultStore.OracleLeaseObservation?>(new() { Active = true }), Read);
        if (scenario == "healthy")
        {
            Assert.AreEqual("entity", (await branch).EntityBindingId);
            Assert.IsTrue(state.Confirmed);
            Assert.AreEqual(TimeSpan.FromSeconds(1), state.BranchLimit);
            Assert.AreEqual(executionId, state.Lifetime?.ExecutionId);
            // 成功归还及观察器退出后，保留着该范围的代码也不能再申请一次源资源。
            Assert.ThrowsExactly<InvalidOperationException>(() => state.Lifetime!.BeginSource());
            return;
        }
        await Assert.ThrowsAsync<IOException>(() => branch);
        // 原截止前/后以及第一笔结算已完成但第二笔已越限分别留有独立见证。
        if (scenario == "past-request") request.Tighten(0);
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

    /// <summary>成功读取已经真正归还源资源；平台成功尚未提交时正式取消胜出，结算仍消费最后分支的准确原期限。</summary>
    [TestMethod]
    [DataRow(false)]
    [DataRow(true)]
    public async Task HealthyReaderThenWinningCancelUsesOriginalBranch(bool crossesBranch)
    {
        // 同一单调时基标记源读取完成、平台取消胜出与两笔持久操作。
        var clock = new ManualClock();
        using var request = new G4RequestDeadline(clock, CancellationToken.None);
        // 该用例替换数据库 I/O，保留正式源分支及失败结算的完整调用。
        var execution = new G4QueryExecution(null!, null!, null!, null!, clock);
        var branch = new G4QueryExecution.OracleExecution();
        var lease = new G4QueryRecord { Id = "query-healthy-before-cancel", LeaseOwner = "oracle-execution-test", Fence = 1,
            DeadlineAtUtc = request.DeadlineUtc };
        var identity = string.Empty;
        await execution.ReadOracleAsync(lease, branch, request.DeadlineUtc, CancellationToken.None,
            (_, _) => Task.FromResult<G4QueryResultStore.OracleLeaseObservation?>(new() { Active = true }), _ =>
            {
                // 读者成功并明确归还同一物理申请，随后停止观察器。
                var lifetime = G4OracleSourceLifetime.Current!;
                identity = lifetime.ExecutionId;
                var acquisition = lifetime.BeginSource();
                clock.Advance(100);
                lifetime.ConfirmReleased(acquisition);
                return Task.FromResult(new G4SourceQueryRead { EntityBindingId = "entity", Rows = [],
                    StartedAtUtc = clock.GetUtcNow(), CompletedAtUtc = clock.GetUtcNow(), AdapterVersion = "oracle-query-v1",
                    WatermarkKind = "UNKNOWN", Watermark = null, Indeterminate = false, Limited = false,
                    RecordKeyFields = ["ROW_ID"], QueryPlanHash = new string('a', 64) });
            });
        Assert.IsTrue(branch.Confirmed);
        // 原 1 秒分支还余 75ms 时取消赢得平台提交；5秒总预算仍有充足余量。
        clock.Advance(825);
        var fails = 0;
        var confirms = 0;
        await execution.FinishOracleFailureAsync(lease, branch, CancellationToken.None, _ =>
        {
            fails++;
            if (crossesBranch) clock.Advance(76);
            return Task.CompletedTask;
        }, _ => { confirms++; return Task.FromResult(true); });
        Console.WriteLine($"healthy-return-ms=100 cancel-ms=925 settled-ms={(crossesBranch ? 1001 : 925)} fail={fails} cas={confirms} " +
            $"same-execution={identity == branch.Lifetime?.ExecutionId} root-remaining-ms={request.Remaining.TotalMilliseconds}");
        Assert.AreEqual(1, fails);
        Assert.AreEqual(crossesBranch ? 0 : 1, confirms);
        Assert.AreEqual(identity, branch.Lifetime?.ExecutionId);
        Assert.IsTrue(request.Remaining > TimeSpan.FromSeconds(3));
    }

    /// <summary>真实 PG 行锁延迟写者，验证正式失败写与两种终态 CAS 都须在锁内服从更早源截止。</summary>
    [TestMethod]
    [DataRow("FAILED")]
    [DataRow("CANCELLED")]
    [DataRow("RUNNING")]
    public async Task OriginalCutoffIsCheckedAfterPostgresRowLock(string status)
    {
        // 复用既有临时 PG 所有权准入，拒绝连接正式平台库或任何未标识测试库。
        var connection = Environment.GetEnvironmentVariable("G4_QUERY_TEST_CONNECTION");
        Assert.IsFalse(string.IsNullOrWhiteSpace(connection));
        await G4QueryPersistenceTests.DemandIsolatedDatabaseAsync(connection!);
        await using var host = new ServiceCollection()
            .AddDbContextFactory<G4QueryDbContext>(o => o.UseNpgsql(connection, n => n.MigrationsHistoryTable("__EFMigrationsHistory", "semantic_query")))
            .AddDbContextFactory<GovernanceDbContext>(o => o.UseNpgsql(connection, n => n.MigrationsHistoryTable("__EFMigrationsHistory", "governance")))
            .BuildServiceProvider();
        // 仅该独立用例的随机行允许写，锁持有者和产品写者分别建连接。
        var queries = host.GetRequiredService<IDbContextFactory<G4QueryDbContext>>();
        var governance = host.GetRequiredService<IDbContextFactory<GovernanceDbContext>>();
        await using var locker = await queries.CreateDbContextAsync();
        await using var audits = await governance.CreateDbContextAsync();
        await locker.Database.MigrateAsync();
        await audits.Database.MigrateAsync();
        var id = "query-lock-" + Guid.NewGuid().ToString("N");
        var owner = G4QueryResultStore.OracleOwnerPrefix + Guid.NewGuid().ToString("N");
        var actor = new ActorContext { SubjectId = id, OrganizationId = "isolated-oracle", SiteIds = ["a"],
            Roles = ["platform.viewer"], TraceId = id, CorrelationId = id };
        var scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = actor.SiteIds };
        // 唯一输入的显式状态及 fence 使旧读者绝不能作用于别的申请。
        var seed = new G4QueryRecord { Id = id, LeaseOwner = owner, Fence = status == "RUNNING" ? 1 : 2,
            ExecutionStatus = status, CancelRequested = status == "CANCELLED", OrganizationId = actor.OrganizationId,
            SubjectId = id, IdempotencyKey = id, CreatedAtUtc = DateTimeOffset.UtcNow, DeadlineAtUtc = DateTimeOffset.UtcNow.AddSeconds(5),
            ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(1), LeaseUntilUtc = DateTimeOffset.UtcNow.AddSeconds(5) };
        locker.Queries.Add(seed);
        await locker.SaveChangesAsync();
        var store = new G4QueryResultStore(queries, null!, null!, new TransactionalAuditWriter(governance),
            new EphemeralDataProtectionProvider(), TimeProvider.System);
        try
        {
            // 在精确不存在的测试 ID 上准备数据库查询，避免一次性模型/命令编译消耗测量窗口。
            var missing = new G4QueryRecord { Id = "absent-" + id, LeaseOwner = owner, Fence = 1 };
            await store.FailOracleAsync(missing, scope, actor, () => TimeSpan.FromMilliseconds(250), CancellationToken.None);
            Assert.IsFalse(await store.ConfirmOracleCleanupAsync(missing.Id, owner, 1, 2, () => TimeSpan.FromMilliseconds(250), CancellationToken.None));
            await using var held = await locker.Database.BeginTransactionAsync();
            var pid = (await locker.Database.SqlQuery<int>($"""
                SELECT pg_backend_pid() AS "Value" FROM semantic_query."Queries" WHERE "Id" = {id} FOR UPDATE
                """).ToArrayAsync()).Single();
            // 正式取消本身给 250ms，同一行的原源分支另只余 100ms。两个量分开独立核验。
            if (status == "CANCELLED")
                await locker.Database.ExecuteSqlInterpolatedAsync($"""
                    UPDATE semantic_query."Queries" SET "LeaseUntilUtc" = clock_timestamp()+interval '250 milliseconds' WHERE "Id"={id}
                    """);
            // 锁在发起写操作前已经持有；测试令牌始终有效，排除线程计时器取消代替数据库期限检查。
            var start = Stopwatch.GetTimestamp();
            TimeSpan Remaining() => TimeSpan.FromMilliseconds(100) - Stopwatch.GetElapsedTime(start);
            async Task<bool> Write()
            {
                if (status != "RUNNING")
                    return await store.ConfirmOracleCleanupAsync(id, owner, 1, 2, Remaining, CancellationToken.None);
                await store.FailOracleAsync(seed, scope, actor, Remaining, CancellationToken.None);
                return false;
            }
            var write = Write();
            try
            {
                // 通过真实等待图绑定持锁者 PID，而不是仅依据任务已调度。
                var blocked = false;
                while (Stopwatch.GetElapsedTime(start) < TimeSpan.FromMilliseconds(90))
                {
                    blocked = (await locker.Database.SqlQuery<bool>($"""
                        SELECT EXISTS (SELECT 1 FROM pg_locks l WHERE NOT l.granted AND {pid}=ANY(pg_blocking_pids(l.pid))) AS "Value"
                        """).SingleAsync());
                    if (blocked) break;
                    await Task.Delay(1);
                }
                Assert.IsTrue(blocked, "The exact row lock must block the product writer before the source cutoff.");
                while (Remaining() > TimeSpan.Zero) await Task.Delay(1);
                if (status == "CANCELLED")
                    Assert.IsTrue(await locker.Database.SqlQuery<bool>($"""
                        SELECT "LeaseUntilUtc" > clock_timestamp() AS "Value" FROM semantic_query."Queries" WHERE "Id"={id}
                        """).SingleAsync());
            }
            finally
            {
                await held.CommitAsync();
                await write.WaitAsync(TimeSpan.FromSeconds(2));
            }
            Assert.IsFalse(await write);
            var saved = await locker.Queries.AsNoTracking().SingleAsync(row => row.Id == id);
            Assert.AreEqual(owner, saved.LeaseOwner);
            Assert.AreEqual(seed.Fence, saved.Fence);
            Assert.AreEqual(status, saved.ExecutionStatus);
            Assert.IsFalse(await audits.AuditRecords.AnyAsync(row => row.Resource == id));
        }
        finally
        {
            await locker.Queries.Where(row => row.Id == id).ExecuteDeleteAsync();
        }
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
