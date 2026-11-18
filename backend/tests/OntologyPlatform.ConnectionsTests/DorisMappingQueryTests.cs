using System.Diagnostics;
using System.Globalization;
using System.Reflection;
using System.Text.Json;
using System.Text.RegularExpressions;
using MySqlConnector;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>在当前任务两表夹具上用产品连接器核验源值、分支期限与 BE 取消见证。</summary>
[TestClass]
[TestCategory("DorisMappingQueryFixture")]
[DoNotParallelize]
public sealed class DorisMappingQueryTests
{
    /// <summary>从本轮测试入口唯一提供的位置读取合成夹具配置。</summary>
    private static string DirectoryPath => Environment.GetEnvironmentVariable("DMQ_S0_SOURCE")
        ?? throw new InvalidOperationException("S0 fixture required");

    /// <summary>直接调用产品分支执行器；内部执行计划不作为面向用户的 SQL 入口。</summary>
    private static Task<T> Branch<T>(Func<MySqlConnection, Task<T>> plan, DateTimeOffset deadline, CancellationToken token)
    {
        // 配置与秘密均来自当前任务的只读夹具。
        var adapter = new DorisSourceAdapter(new DorisAdapterOptions { RootCertificatePath = Path.Combine(DirectoryPath, "tls", "ca.pem") });
        // 产品校验器拒绝此精确目标以外的范围。
        var profile = new DorisConnectionProfile { FeHost = "localhost", QueryPort = 19030, Catalog = "internal", Database = "fixture", Username = "fixture_reader", Tls = true };
        // 测试沿用模块私有入口的既有反射约定，无需扩大产品可见性。
        var read = typeof(DorisSourceAdapter).GetMethod("ReadBranchAsync", BindingFlags.Instance | BindingFlags.NonPublic)!;
        return (Task<T>)read.MakeGenericMethod(typeof(T)).Invoke(adapter,
            [profile, File.ReadAllText(Path.Combine(DirectoryPath, "reader.pass")), deadline, TimeProvider.System, plan, token])!;
    }

    /// <summary>验证实际定点数、业务时间原始微秒、当前 upsert 行及两表原生 UNIQUE/MOW。</summary>
    [TestMethod]
    public async Task RealDriverReadsFixedSource()
    {
        // 每个独立查询均使用产品分支执行器；本测试没有平台事务或源快照。
        var amount = await Branch(async connection =>
        {
            await using var cmd = new MySqlCommand("SELECT amount,event_at FROM fixture.dmq_entity WHERE org_id='org-demo' AND site_id='site-a' AND entity_id='E1' LIMIT 2", connection);
            await using var rows = await cmd.ExecuteReaderAsync();
            Assert.IsTrue(await rows.ReadAsync());
            // 驱动直接读取精确十进制，无浮点中转。
            var actual = rows.GetDecimal(0);
            Assert.AreEqual("2026-11-17 12:00:00.123456", rows.GetDateTime(1).ToString("yyyy-MM-dd HH:mm:ss.ffffff", CultureInfo.InvariantCulture));
            Assert.IsFalse(await rows.ReadAsync());
            return actual;
        }, DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None);
        Assert.AreEqual(9007199254740993.20m, amount);
        // 两个表名由测试编译期固定，按各自三列复合主键核对目录。
        foreach (var (table, key) in new[] { ("dmq_entity", "entity_id"), ("dmq_target", "target_id") })
        {
            // DDL 列只来自已允许的合成库。
            var ddl = await Branch(async connection =>
            {
                await using var command = new MySqlCommand("SHOW CREATE TABLE fixture." + table, connection);
                await using var reader = await command.ExecuteReaderAsync();
                Assert.IsTrue(await reader.ReadAsync());
                return reader.GetString(1);
            }, DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None);
            StringAssert.Matches(ddl, new Regex(@"UNIQUE KEY\s*\(\s*`org_id`,\s*`site_id`,\s*`" + key + @"`\s*\)", RegexOptions.IgnoreCase));
            StringAssert.Contains(ddl, "\"enable_unique_key_merge_on_write\" = \"true\"");
        }
    }

    /// <summary>同一查询分别记录取消、KILL 回执、驱动终止及源活动。窗口外样本单列。</summary>
    [TestMethod]
    public async Task ActiveBackendMustFinishInsideOriginalWindow()
    {
        // 管理员仅用于独立的源侧观测，与执行和取消的产品 reader 会话分离。
        var observerOptions = new MySqlConnectionStringBuilder
        {
            Server = "localhost", Port = 19030, UserID = "root", Password = File.ReadAllText(Path.Combine(DirectoryPath, "root.pass")),
            SslMode = MySqlSslMode.VerifyFull, SslCa = Path.Combine(DirectoryPath, "tls", "ca.pem"), Pooling = false,
            ConnectionTimeout = 2, CancellationTimeout = -1, DefaultCommandTimeout = 1
        };
        await using var observer = new MySqlConnection(observerOptions.ConnectionString);
        await observer.OpenAsync();
        // 标记只用于从独立连接定位这一次单行固定工作。
        var tag = "dmq_driver_" + Guid.NewGuid().ToString("N");
        using var cancel = new CancellationTokenSource();
        using var activity = new Activity("dmq.s0.branch").Start();
        // 秒表包含产品分支握手与权限核验，独立观察者的预连接不占用产品身份。
        var watch = Stopwatch.StartNew();
        // 观察者只在原五秒剩余时间内继续采样，包括 SQL 等待、行读取和轮询间隔。
        using var observation = new CancellationTokenSource(TimeSpan.FromSeconds(5) - watch.Elapsed);
        // 仅记录安全时序及固定诊断码。
        var samples = new List<(double At, long Fe, long Be, long? TaskTime)>();
        // 服务端连接号取自驱动握手；再由 PROCESSLIST 核对同账号、同操作。
        var thread = 0;
        // 精确查询 ID 必须取自执行中的 FE。
        string? query = null;
        // 各事件互不替代；未见证的值显式保留为空。
        double? requested = null, branchEnded = null;
        // 未完成任务不得被记录为产品取消成功。
        string? result = null;
        // 独立观察任务不向主连接传入驱动软取消令牌。
        var execution = Branch(async connection =>
        {
            Volatile.Write(ref thread, connection.ServerThread);
            await using var command = new MySqlCommand("SELECT SLEEP(CAST(IF(entity_id='E1',3,0) AS INT)) AS " + tag +
                " FROM fixture.dmq_entity WHERE org_id='org-demo' AND site_id='site-a' AND entity_id='E1'", connection);
            return await command.ExecuteScalarAsync(CancellationToken.None);
        }, DateTimeOffset.UtcNow.AddSeconds(5), cancel.Token);
        async Task CaptureCompletion()
        {
            try { await execution; result = "SUCCESS"; }
            catch (OperationCanceledException) when (cancel.IsCancellationRequested) { result = "CALLER_CANCELLED"; }
            catch (SemanticOperationException error) { result = error.Code; }
            catch (Exception error) { result = error.GetType().Name; }
            finally { branchEnded = watch.Elapsed.TotalMilliseconds; }
        }
        // 与源观察并发记录实际产品返回时刻。
        var completion = CaptureCompletion();
        try
        {
            while (query is null && watch.ElapsedMilliseconds < 710 && !completion.IsCompleted)
            {
                await using var cmd = new MySqlCommand("SHOW FULL PROCESSLIST", observer);
                await using var rows = await cmd.ExecuteReaderAsync(observation.Token).WaitAsync(observation.Token);
                while (await rows.ReadAsync(observation.Token).WaitAsync(observation.Token))
                {
                    if (Convert.ToInt64(rows["Id"], CultureInfo.InvariantCulture) == Volatile.Read(ref thread)
                        && Equals(rows["User"], "fixture_reader") && rows["Info"] is string sql && sql.Contains(tag, StringComparison.Ordinal))
                        query = Convert.ToString(rows["QueryId"], CultureInfo.InvariantCulture);
                }
                if (query is null) await Task.Delay(5, observation.Token);
            }
            Assert.IsTrue(query is not null && Regex.IsMatch(query, @"\A[0-9a-fA-F]{16}-[0-9a-fA-F]{16}\z"), "FE_QUERY_ID");
            do
            {
                // 每次打开新查询，统计表中的 finished 行可能短暂保留；同时观察 TASK_TIME_MS。
                await using var command = new MySqlCommand("SELECT (SELECT COUNT(*) FROM information_schema.active_queries WHERE query_id='" + query +
                    "'),COUNT(*),MAX(task_time_ms) FROM information_schema.backend_active_tasks WHERE query_id='" + query + "'", observer);
                await using var reader = await command.ExecuteReaderAsync(observation.Token).WaitAsync(observation.Token);
                Assert.IsTrue(await reader.ReadAsync(observation.Token).WaitAsync(observation.Token));
                // 时间记在数据库响应读回之后，绝不把超窗采样向前移动。
                var sample = (watch.Elapsed.TotalMilliseconds, reader.GetInt64(0), reader.GetInt64(1), reader.IsDBNull(2) ? (long?)null : reader.GetInt64(2));
                samples.Add(sample);
                if (requested is null && sample.Item2 > 0 && sample.Item3 > 0)
                {
                    Assert.IsTrue(sample.Item1 < 740, "ACTIVE_BE_PRECONDITION_TOO_LATE");
                    requested = watch.Elapsed.TotalMilliseconds;
                    cancel.Cancel();
                }
                if (requested.HasValue && sample.Item2 == 0 && sample.Item3 == 0) break;
                if (!requested.HasValue && (watch.ElapsedMilliseconds > 740 || completion.IsCompleted)) break;
                await Task.Delay(requested.HasValue && watch.Elapsed.TotalMilliseconds - requested.Value > 250 ? 120 : 8, observation.Token);
            } while (watch.ElapsedMilliseconds < 4580);
        }
        finally
        {
            cancel.Cancel();
            // 到达五秒后只封存已见证的字段，不再等待完成或接受较晚样本。
            try { await completion.WaitAsync(observation.Token); }
            catch (OperationCanceledException) when (observation.IsCancellationRequested) { }
            // 记录见证停止时刻，文件写入不参与产品或源侧预算。
            var observationEnd = watch.Elapsed.TotalMilliseconds;
            // 准确原件每个运行只有一份，失败也保留。不得输出口令、连接串或证书。
            var path = Path.Combine(Environment.GetEnvironmentVariable("DMQ_S0_EVIDENCE")!, tag + ".json");
            await using var output = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read);
            await JsonSerializer.SerializeAsync(output, new { tag, query, thread, driver = typeof(MySqlConnection).Assembly.GetCustomAttribute<AssemblyInformationalVersionAttribute>()?.InformationalVersion,
                requested, branchEnded, result, observationEndMs = observationEnd,
                events = activity.Events.Select(e => new { e.Name, utc = e.Timestamp, atMs = (e.Timestamp.UtcDateTime - activity.StartTimeUtc).TotalMilliseconds }),
                samples = samples.Select(s => new { atMs = s.At, fe = s.Fe, be = s.Be, taskTimeMs = s.TaskTime }) });
            Assert.IsTrue(observationEnd <= 5000, "SOURCE_OBSERVER_TOTAL_DEADLINE");
        }
        Assert.IsTrue(requested.HasValue && result == "query_source_unavailable" && branchEnded <= requested.Value + 250 && branchEnded <= 1000, "DRIVER_CLEANUP");
        Assert.IsTrue(activity.Events.Any(e => e.Name == "doris.kill.acknowledged") && activity.Events.Any(e => e.Name == "doris.driver.ended"), "ACK_AND_DRIVER_END");
        Assert.IsTrue(activity.Events.Any(e => e.Name == "doris.source.termination_unverified"), "SOURCE_UNCERTAINTY");
        Assert.IsTrue(samples.Any(s => s.At >= requested.Value && s.At <= requested.Value + 250 && s.Fe == 0 && s.Be == 0), "SOURCE_TERMINATION_NOT_VERIFIED_IN_250MS");
    }
}
