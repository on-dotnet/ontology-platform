using System.Collections.Concurrent;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
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

    /// <summary>在产品读分支记录独立查询号、源值、会话偏移、业务时区解释及实际读取窗口。</summary>
    private static async Task<(string Id, string Amount, string Instant, string Zone, DateTimeOffset Start, DateTimeOffset End)> ReadChangingEntity()
    {
        // 开始时间包住握手、实际读取及权限后验。
        var start = DateTimeOffset.UtcNow;
        // 由同一无池连接在数据查询之后立即读取其查询号。
        var read = await Branch(async connection =>
        {
            await using var cmd = new MySqlCommand("SELECT /*+ SET_VAR(enable_sql_cache=false) */ amount,event_at,@@session.time_zone FROM fixture.dmq_entity WHERE org_id='org-demo' AND site_id='site-a' AND entity_id='E1' LIMIT 2", connection);
            // 使用固定源精度保留两位定点数和六位微秒。
            string amount, local, zone;
            await using (var row = await cmd.ExecuteReaderAsync())
            {
                Assert.IsTrue(await row.ReadAsync());
                amount = row.GetDecimal(0).ToString("F2", CultureInfo.InvariantCulture);
                local = row.GetDateTime(1).ToString("yyyy-MM-dd HH:mm:ss.ffffff", CultureInfo.InvariantCulture);
                zone = row.GetString(2);
                Assert.IsFalse(await row.ReadAsync());
            }
            await using var last = new MySqlCommand("SELECT LAST_QUERY_ID()", connection);
            // 查询号仅用于因果关联合成源，不充当数据水位。
            var id = Convert.ToString(await last.ExecuteScalarAsync(), CultureInfo.InvariantCulture)!;
            Assert.IsTrue(Regex.IsMatch(id, @"\A[0-9a-f]{1,16}-[0-9a-f]{1,16}\z", RegexOptions.IgnoreCase));
            // 业务规则显式声明 UTC 和微秒精度，独立于上面实读的会话偏移。
            var spec = new MappingTemporalSpec { Id = "time", EventTimeFieldRef = null, ObservedAtFieldRef = null,
                ValidFromFieldRef = null, ValidToFieldRef = null, Precision = "MICROSECOND",
                TimezonePolicy = new MappingTimezonePolicy { Kind = "REGISTERED_ZONE", ZoneId = "Etc/UTC" } };
            // 测试沿用程序集私有方法，结果来自生产时间解释器。
            var interpret = typeof(DorisSourceAdapter).Assembly.GetType("OntologyPlatform.Modules.Connections.DorisMappingTypeRules", true)!
                .GetMethod("Instant", BindingFlags.NonPublic | BindingFlags.Static)!;
            // 显式时区才可获得业务瞬间，过低精度和未登记时区均被拒绝。
            var instant = (DateTimeOffset)interpret.Invoke(null, [local, spec])!;
            foreach (var invalid in new[] { spec with { Precision = "SECOND" }, spec with { TimezonePolicy = spec.TimezonePolicy with { ZoneId = "Asia/Shanghai" } } })
            {
                var failure = Assert.ThrowsExactly<TargetInvocationException>(() => interpret.Invoke(null, [local, invalid]));
                Assert.AreEqual("mapping_source_type_invalid", (failure.InnerException as SemanticOperationException)?.Code);
            }
            return (id, amount, instant.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'", CultureInfo.InvariantCulture), zone);
        }, start.AddSeconds(5), CancellationToken.None);
        return (read.id, read.amount, read.Item3, read.zone, start, DateTimeOffset.UtcNow);
    }

    /// <summary>独立控制面在两次已完成的正式源读取之间提交单键更新，最后复原并再次实读。</summary>
    [TestMethod]
    public async Task ControlledWriteBetweenSourceReads()
    {
        // 控制面凭据只出现在合成测试，产品实时验证自身只读账号。
        var options = new MySqlConnectionStringBuilder { Server = "localhost", Port = 19030, UserID = "root",
            Password = File.ReadAllText(Path.Combine(DirectoryPath, "root.pass")), Pooling = false,
            SslMode = MySqlSslMode.VerifyFull, SslCa = Path.Combine(DirectoryPath, "tls", "ca.pem"), DefaultCommandTimeout = 2 };
        await using var writer = new MySqlConnection(options.ConnectionString);
        await writer.OpenAsync();
        // 只允许修改原始 E1 的 amount，完整行的其他值冻结在首次建表夹具。
        async Task Write(bool restore)
        {
            await using var cmd = new MySqlCommand("INSERT INTO fixture.dmq_entity VALUES ('org-demo','site-a','E1',1.00,@amount,'K','2026-11-01','2026-12-01','2026-11-17 12:00:00.123456','2026-11-17 12:00:01.123456')", writer);
            cmd.Parameters.Add("@amount", MySqlDbType.Decimal).Value = restore ? 9007199254740993.20m : 9007199254740993.21m;
            await cmd.ExecuteNonQueryAsync();
        }
        // 各窗口记录无池读连接在同一源提交前后的事实。
        var observations = new List<object>();
        async Task<string> Check(string expected)
        {
            // 观测值包含当前 SELECT 的准确 QueryId。
            var actual = await ReadChangingEntity();
            observations.Add(new { actual.Id, actual.Amount, actual.Instant, actual.Zone, actual.Start, actual.End });
            Assert.AreEqual(expected, actual.Amount);
            Assert.AreEqual("+00:00", actual.Zone);
            Assert.AreEqual("2026-11-17T12:00:00.123456Z", actual.Instant);
            return actual.Id;
        }
        // 初值必须匹配，否则不得向控制面提交写入。
        var initial = await Check("9007199254740993.20");
        // 写入开始与提交确认分别记录，第二个读取只能发生在确认后。
        var writeStart = DateTimeOffset.UtcNow;
        DateTimeOffset committed;
        try
        {
            await Write(false);
            committed = DateTimeOffset.UtcNow;
            Assert.AreNotEqual(initial, await Check("9007199254740993.21"));
        }
        finally { await Write(true); }
        await Check("9007199254740993.20");
        // 原件只含本任务合成值、源查询号码与真实窗口。
        var path = Path.Combine(Environment.GetEnvironmentVariable("DMQ_S0_EVIDENCE")!, $"ac11-{Guid.NewGuid():N}.json");
        await using var file = new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read);
        await JsonSerializer.SerializeAsync(file, new { observations, writeStart, committed, watermarkKind = "UNKNOWN",
            watermark = (string?)null, fixtureWindow = "CONTROLLED_WRITE" });
    }

    /// <summary>通过正式关系固定计划验证同名表的模型或原生列类型变化会关闭该能力。</summary>
    [TestMethod]
    public async Task FixedTargetRejectsUnsupportedShape()
    {
        // 应在投影之前拒绝不兼容形状，不能把空表或驱动错误包装为通过。
        var error = await Assert.ThrowsExactlyAsync<SemanticOperationException>(() =>
            FixedPlan(true, DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None));
        Assert.AreEqual("mapping_source_shape_invalid", error.Code);
    }

    /// <summary>调用产品固定 SQL 生成和执行路径；主连接使用合成只读身份。</summary>
    private static Task<List<Dictionary<string, object?>>> FixedPlan(bool target, DateTimeOffset deadline, CancellationToken token)
    {
        // 构建与产品一致的固定目标、证书与范围。
        var adapter = new DorisSourceAdapter(new DorisAdapterOptions { RootCertificatePath = Path.Combine(DirectoryPath, "tls", "ca.pem") });
        // 配置中没有客户端指定 SQL、线程号或外部地址。
        var profile = new DorisConnectionProfile { FeHost = "localhost", QueryPort = 19030, Catalog = "internal", Database = "fixture", Username = "fixture_reader", Tls = true };
        // 标量选择代表已发布的根实体分支以及一个父实体的半开关系过滤。
        (decimal Key, DateTime Start, DateTime End)? parent = target ? (1.00m, new DateTime(2026, 11, 1), new DateTime(2026, 12, 1)) : null;
        // 测试不会向产品提交委托或自编 SQL。
        var read = typeof(DorisSourceAdapter).Assembly.GetType("OntologyPlatform.Modules.Connections.DorisQueryReader", true)!
            .GetMethod("ReadAsync", BindingFlags.Static | BindingFlags.NonPublic)!;
        return (Task<List<Dictionary<string, object?>>>)read.Invoke(null, [adapter, profile, File.ReadAllText(Path.Combine(DirectoryPath, "reader.pass")),
            new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a"] }, null, parent, deadline, token])!;
    }

    /// <summary>独立的夹具期望值验证两份固定投影的正常执行。</summary>
    [TestMethod]
    public async Task FixedPlansReturnScopedValues()
    {
        // 两张表均在正式目录发现前存在，测试按固定参数运行产品生成器。
        var entities = await FixedPlan(false, DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None);
        Assert.AreEqual(100, entities.Count);
        // 原始 E1 的值来自固定夹具约定，未由被测输出生成。
        var first = entities.Single(r => Equals(r["entity_id"], "E1"));
        Assert.AreEqual(9007199254740993.20m, first["amount"]);
        // T3 和其余窗口外或键不等的目标不会出现在此关系分支中。
        var targets = await FixedPlan(true, DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None);
        CollectionAssert.AreEqual(new[] { "T1", "T2" }, targets.Select(r => r["target_id"]).ToArray());
    }

    /// <summary>预先订阅本任务准确 BE 的日志流，只取 QueryId、原始时间及事件种类。</summary>
    private sealed class BackendEvents : IDisposable
    {
        /// <summary>只读追踪进程；不把未过滤的服务日志交给测试输出。</summary>
        private readonly Process stream;

        /// <summary>同一 QueryId 的源事件及宿主收取时刻，支持注销晚于工作完成的判别。</summary>
        internal readonly ConcurrentQueue<(string Query, string Kind, string Utc, long Received)> Seen = new();

        /// <summary>订阅动作只用于触发调用方产品令牌；不向源发命令。</summary>
        internal Action<string>? Registered { get; set; }

        /// <summary>正式计时前用独立观察者的真实查询绑定一次日志注册和结束，避免把未就绪当无活动。</summary>
        internal async Task DemandReadyAsync(MySqlConnection observer)
        {
            using var budget = new CancellationTokenSource(TimeSpan.FromSeconds(3));
            await using var scan = new MySqlCommand("SELECT /*+ SET_VAR(enable_sql_cache=false) */ COUNT(*) FROM fixture.dmq_target WHERE target_id='T3'", observer);
            Assert.AreEqual(1L, Convert.ToInt64(await scan.ExecuteScalarAsync(budget.Token), CultureInfo.InvariantCulture));
            await using var previous = new MySqlCommand("SELECT LAST_QUERY_ID()", observer);
            // QueryId 取自同一控制连接上一条 SQL；不能用时间接近的其他任务证明订阅就绪。
            var id = CanonicalId((string)(await previous.ExecuteScalarAsync(budget.Token))!);
            while (!Seen.Any(e => e.Query == id && e.Kind == "registered") || !Seen.Any(e => e.Query == id && e.Kind == "context_end"))
                await Task.Delay(1, budget.Token);
        }

        /// <summary>两段各自补足十六位；Doris 打印的无符号标识可省略前导零。</summary>
        internal static string CanonicalId(string raw)
        {
            if (!Regex.IsMatch(raw, @"\A[0-9a-fA-F]{1,16}-[0-9a-fA-F]{1,16}\z"))
                throw new InvalidDataException("DORIS_QUERY_ID");
            return string.Join("-", raw.Split('-').Select(part => part.PadLeft(16, '0').ToLowerInvariant()));
        }

        /// <summary>打开跟踪前核验来自当前任务运行器的准确 BE 身份。</summary>
        internal BackendEvents()
        {
            // 只接受完整 Docker 容器 ID，不能插入其他命令行参数。
            var id = Environment.GetEnvironmentVariable("DMQ_S0_BE_ID");
            Assert.IsTrue(id is not null && Regex.IsMatch(id, @"\A[0-9a-f]{64}\z"));
            // 两个流一律由同一白名单处理，不复制日志正文。
            var start = new ProcessStartInfo("docker") { RedirectStandardOutput = true, RedirectStandardError = true, UseShellExecute = false };
            foreach (var arg in new[] { "--context", "desktop-linux", "logs", "--since", DateTimeOffset.UtcNow.AddSeconds(-1).ToString("O"), "--follow", id })
                start.ArgumentList.Add(arg!);
            stream = new Process { StartInfo = start };
            stream.OutputDataReceived += Parse;
            stream.ErrorDataReceived += Parse;
            Assert.IsTrue(stream.Start());
            stream.BeginOutputReadLine();
            stream.BeginErrorReadLine();
        }

        /// <summary>匹配固定版本五类源位置及输出字段，其余消息直接丢弃。</summary>
        private void Parse(object sender, DataReceivedEventArgs args)
        {
            if (args.Data is not { } line) return;
            // 仅匹配精确源码位置与语义，互不替代。
            var kind = line switch
            {
                _ when line.Contains("fragment_mgr.cpp:729]") && line.Contains("total fragment num") => "registered",
                _ when line.Contains("internal_service.cpp:637]") && line.Contains("cancel query by user") => "cancel_arrived",
                _ when line.Contains("task_scheduler.cpp:84]") && line.Contains("[CANCELLED]") && line.Contains("cancel query by user") => "task_cancelled",
                _ when line.Contains("pipeline_fragment_context.cpp:142]") && line.Contains("~PipelineFragmentContext") => "fragment_end",
                _ when line.Contains("query_context.cpp:262]") && line.Contains("deconstructed") => "context_end",
                _ => null
            };
            if (kind is null) return;
            // 保留 BE 原时间及宿主读取时间；从不输出原行。
            var match = Regex.Match(line, @"^[IWE](\d{8} \d{2}:\d{2}:\d{2}\.\d+).*?\b([0-9a-fA-F]{1,16}-[0-9a-fA-F]{1,16})\b",
                RegexOptions.CultureInvariant);
            if (!match.Success) return;
            // 规范化后按完整数值等值匹配，不取 QueryId 前缀。
            var id = CanonicalId(match.Groups[2].Value);
            Seen.Enqueue((id, kind, match.Groups[1].Value, Stopwatch.GetTimestamp()));
            if (kind == "registered") Registered?.Invoke(id);
        }

        /// <summary>只结束并回收本测试的本机只读日志消费者。</summary>
        public void Dispose()
        {
            if (!stream.HasExited) stream.Kill();
            stream.WaitForExit(2000);
            stream.Dispose();
        }
    }

    /// <summary>实体读取的取消必须命中运行中的真实 BE 执行。</summary>
    [TestMethod]
    public Task FixedEntityCancellation() => ObserveFixedCancellation(false);

    /// <summary>等值和半开关系目标读取使用独立的执行中取消见证。</summary>
    [TestMethod]
    public Task FixedTargetCancellation() => ObserveFixedCancellation(true);

    /// <summary>两种固定计划各自尝试一次；自然完成、未捕获运行中及已证实取消分别保留。</summary>
    private static async Task ObserveFixedCancellation(bool target)
    {
        using var be = new BackendEvents();
        // 管理观察者仅查询 FE PROCESSLIST；产品固定计划和 KILL 使用 reader。
        var options = new MySqlConnectionStringBuilder { Server = "localhost", Port = 19030, UserID = "root",
            Password = File.ReadAllText(Path.Combine(DirectoryPath, "root.pass")), Pooling = false, CancellationTimeout = -1,
            SslMode = MySqlSslMode.VerifyFull, SslCa = Path.Combine(DirectoryPath, "tls", "ca.pem"), ConnectionTimeout = 2, DefaultCommandTimeout = 1 };
        await using var observer = new MySqlConnection(options.ConnectionString);
        await observer.OpenAsync();
        await be.DemandReadyAsync(observer);
        using var activity = new Activity("dmq.fixed.read").Start();
        // 单调原点同时约束分支、清理及旁路总见证。
        var start = Stopwatch.GetTimestamp();
        double TimeAt(long stamp) => Stopwatch.GetElapsedTime(start, stamp).TotalMilliseconds;
        using var total = new CancellationTokenSource(TimeSpan.FromSeconds(5) - Stopwatch.GetElapsedTime(start));
        using var cancel = new CancellationTokenSource();
        // 正式执行不因观察者错过任务而重跑。
        var work = FixedPlan(target, DateTimeOffset.UtcNow.AddSeconds(5), cancel.Token);
        // 跟踪产品实际返回值，不能用停止等待推断源端结束。
        string? result = null;
        // 产品分支完成时刻与源端结束分开记录。
        long returned = 0;
        async Task ObserveReturn()
        {
            try { await work; result = "NATURAL_COMPLETION"; }
            catch (SemanticOperationException error) { result = error.Code; }
            catch (OperationCanceledException) { result = "CANCELLED"; }
            finally { returned = Stopwatch.GetTimestamp(); }
        }
        // 在独立监测 SQL 的同时记录原主任务实际结束时间。
        var completion = ObserveReturn();
        // 旁路 FE 返回的身份和值参数化后实际 SQL 的摘要。
        string? query = null, observedSqlHash = null;
        // 原始 FE 文本随规范标识入证，不能将服务器线程号混作查询身份。
        string? rawQuery = null;
        // FE 主连接号必须与本次产品握手号相等。
        int thread = 0;
        // 首次取消触发时刻，零表示未观察到运行中的匹配任务。
        long request = 0;
        // FE 注册表的消失单独取证。
        bool feGone = false;
        // FE 首次缺席的实际采样接收时刻。
        long feGoneAt = 0;
        // 唯有这些固定文本才能把 FE 行归于本次正在运行的业务 SQL。
        var tableClause = target ? "FROM fixture.dmq_target" : "FROM fixture.dmq_entity";
        void RequestIfActive(string id)
        {
            if (id != Volatile.Read(ref query) || completion.IsCompleted ||
                be.Seen.Any(e => e.Query == id && e.Kind == "context_end")) return;
            // FE 或 BE 两方中较晚获知身份的一方立刻请求，仍须事后核验实际任务取消。
            var stamp = Stopwatch.GetTimestamp();
            if (TimeAt(stamp) < 740 && Interlocked.CompareExchange(ref request, stamp, 0) == 0)
                cancel.Cancel();
        }
        be.Registered = RequestIfActive;
        try
        {
            while (TimeAt(Stopwatch.GetTimestamp()) < 740 && !completion.IsCompleted && request == 0)
            {
                await using var cmd = new MySqlCommand("SHOW FULL PROCESSLIST", observer);
                await using var rows = await cmd.ExecuteReaderAsync(total.Token).WaitAsync(total.Token);
                while (await rows.ReadAsync(total.Token).WaitAsync(total.Token))
                {
                    if (!Equals(rows["User"], "fixture_reader") || rows["Info"] is not string sql ||
                        !sql.Contains(tableClause, StringComparison.OrdinalIgnoreCase)) continue;
                    rawQuery = Convert.ToString(rows["QueryId"], CultureInfo.InvariantCulture);
                    if (string.IsNullOrEmpty(rawQuery) || rawQuery == "N/A") continue;
                    thread = Convert.ToInt32(rows["Id"], CultureInfo.InvariantCulture);
                    observedSqlHash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(sql)));
                    Volatile.Write(ref query, BackendEvents.CanonicalId(rawQuery));
                    if (be.Seen.Any(e => e.Query == query && e.Kind == "registered")) RequestIfActive(query!);
                }
            }
            if (request != 0)
            {
                while (Stopwatch.GetElapsedTime(request).TotalMilliseconds < 250)
                {
                    await using var cmd = new MySqlCommand("SHOW FULL PROCESSLIST", observer);
                    await using var rows = await cmd.ExecuteReaderAsync(total.Token).WaitAsync(total.Token);
                    // FE 的移除与 BE 任务结束独立记录。
                    var present = false;
                    while (await rows.ReadAsync(total.Token).WaitAsync(total.Token))
                        present |= Equals(rows["QueryId"], rawQuery);
                    if (!present && !feGone) { feGone = true; feGoneAt = Stopwatch.GetTimestamp(); }
                    if (feGone && be.Seen.Any(e => e.Query == query && e.Kind == "context_end")) break;
                }
            }
            await completion.WaitAsync(total.Token);
        }
        finally
        {
            be.Registered = null;
            if (!completion.IsCompleted) cancel.Cancel();
            // 封存此时已实际收到的事件；对超窗观测不给通过。
            var events = be.Seen.Where(e => e.Query == query).ToArray();
            // 模板摘要和线程号均由产品在提交语句时记录，反向验证观测身份。
            var submitted = activity.Events.FirstOrDefault(e => e.Name == "doris.plan.submitted");
            // 区分源工作已经返回与仍可因本次取消终止。
            var rowsFinished = activity.Events.Any(e => e.Name == "doris.plan.rows_finished");
            // 分别提取源线程号与模板散列，核对实际消费者。
            var sourceThread = submitted.Tags?.FirstOrDefault(t => t.Key == "thread").Value as int?;
            // 模板摘要不携带实参或秘密。
            var templateHash = submitted.Tags?.FirstOrDefault(t => t.Key == "template.sha256").Value as string;
            // 两条物理连接须在同一预算内完成握手。
            var channels = activity.Events.FirstOrDefault(e => e.Name == "doris.cancel.ready");
            // 从产品自身的握手结果交叉核对身份。
            var primary = channels.Tags?.FirstOrDefault(t => t.Key == "source.thread").Value as int?;
            // 辅助连接 ID 必须不同于主连接。
            var auxiliary = channels.Tags?.FirstOrDefault(t => t.Key == "auxiliary.thread").Value as int?;
            // 四个事件按同一 BE 时钟排序，证明取消到达早于工作关闭。
            var cancelled = events.FirstOrDefault(e => e.Kind == "cancel_arrived");
            // 调度器须明确报告所观测执行任务因取消失败。
            var taskEnded = events.FirstOrDefault(e => e.Kind == "task_cancelled");
            // 部分 fragment 可先完成，最后的 fragment 及整查询须在实际取消任务之后关闭。
            var fragment = events.Where(e => e.Kind == "fragment_end").OrderBy(e => e.Utc, StringComparer.Ordinal).LastOrDefault();
            // 整查询收尾标记用于核算源终结的上界。
            var end = events.FirstOrDefault(e => e.Kind == "context_end");
            // 观察结束时间也必须在原五秒内。
            var endMs = TimeAt(Stopwatch.GetTimestamp());
            // 需要正向因果链、双方释放、同一身份及三个独立的时间界限。
            var passed = request != 0 && primary == thread && auxiliary.HasValue && auxiliary != primary &&
                sourceThread == thread && !rowsFinished && result == "query_source_unavailable" &&
                activity.Events.Any(e => e.Name == "doris.kill.acknowledged") && activity.Events.Any(e => e.Name == "doris.driver.ended") &&
                feGone && feGoneAt >= request && cancelled.Received >= request && taskEnded.Received >= request &&
                fragment.Received >= request && end.Received >= request && string.CompareOrdinal(cancelled.Utc, taskEnded.Utc) <= 0 &&
                string.CompareOrdinal(taskEnded.Utc, fragment.Utc) <= 0 && string.CompareOrdinal(fragment.Utc, end.Utc) <= 0 &&
                Stopwatch.GetElapsedTime(request, Math.Max(Math.Max(end.Received,feGoneAt),returned)).TotalMilliseconds <= 250 &&
                TimeAt(Math.Max(end.Received,returned)) <= 1000 && endMs <= 5000;
            // 新原件使用唯一文件名，保存自然结束或采样失败的真实结果。
            var name = (target ? "fixed-target-" : "fixed-entity-") + Guid.NewGuid().ToString("N") + ".json";
            await using var file = new FileStream(Path.Combine(Environment.GetEnvironmentVariable("DMQ_S0_EVIDENCE")!, name),
                FileMode.CreateNew, FileAccess.Write, FileShare.Read);
            await JsonSerializer.SerializeAsync(file, new { passed, result, rawQuery, query, thread, sourceThread, auxiliary, templateHash, observedSqlHash,
                requestedMs = request == 0 ? (double?)null : TimeAt(request), returnedMs = returned == 0 ? (double?)null : TimeAt(returned),
                feGoneMs = feGone ? (double?)TimeAt(feGoneAt) : null, endMs, rowsFinished,
                driverEvents = activity.Events.Select(e => new { e.Name, utc = e.Timestamp }),
                sourceEvents = events.Select(e => new { e.Kind, e.Utc, receivedMs = TimeAt(e.Received) }) });
            Assert.IsTrue(passed, request == 0 ? "ACTIVE_CANCELLATION_PRECONDITION_NOT_OBSERVED" : "FIXED_PLAN_SOURCE_TERMINATION_NOT_VERIFIED");
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
