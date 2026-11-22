using System.Diagnostics;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Modules.Connections;
using OntologyPlatform.Modules.SemanticQuery;

namespace OntologyPlatform.AgentTests;

/// <summary>Oracle 实机测试子进程独占的源事件收集器。只在原 Gateway 单调表运行时保留白名单字段。</summary>
internal sealed class OracleRuntimeSourceEvents : ILoggerProvider
{
    /// <summary>原五秒区间内最多保留的结构化记录数。</summary>
    private const int Capacity = 128;

    /// <summary>共享同步边界保护源分支记录和溢出计数。</summary>
    private readonly object gate = new();

    /// <summary>仅包含两类生产日志的受控投影，不保留原始日志状态或异常。</summary>
    private readonly List<Dictionary<string, object?>> rows = new(Capacity);

    /// <summary>由调用方在正式查询前绑定的同一单调表。</summary>
    private Stopwatch? clock;

    /// <summary>满容量后未保存的事件数；非零即不能核定完整关联。</summary>
    private int dropped;

    /// <summary>同时供真实宿主和离线装配测试安装相同的类别过滤器。</summary>
    internal void Configure(ILoggingBuilder logging)
    {
        logging.AddProvider(this);
        // 正式宿主在回调返回后还会注册 OTel。最后处理全部过滤规则，其他提供器均不能格式化原始日志。
        logging.Services.PostConfigure<LoggerFilterOptions>(options =>
        {
            options.Rules.Clear();
            options.MinLevel = LogLevel.None;
            options.Rules.Add(new LoggerFilterRule(typeof(OracleRuntimeSourceEvents).FullName, null, null,
                (_, category, level) => level == LogLevel.Information &&
                    (category == typeof(OracleSourceAdapter).FullName || category == typeof(G4QueryExecution).FullName)));
        });
    }

    /// <summary>绑定本次 Gateway 实际使用的计时器，不建立新预算。</summary>
    internal void Bind(Stopwatch elapsed) => clock = elapsed;

    /// <summary>响应结束后一次性提取投影与丢失计数。</summary>
    internal void Export(Dictionary<string, object?> evidence)
    {
        lock (gate)
        {
            evidence["sourceEvents"] = rows.ToArray();
            evidence["sourceEventsDropped"] = dropped;
        }
    }

    /// <summary>只从生产事件模板和显式字段取值，从不格式化日志消息、作用域和异常。</summary>
    private void Capture(string category, IReadOnlyList<KeyValuePair<string, object?>> values)
    {
        if (values.Count == 0 || values[^1].Value is not string template || clock?.IsRunning != true) return;
        // 事件类别是原生产模板首个词，不解析格式化文本。
        var end = template.IndexOf(' ');
        if (end < 1) return;
        // 两个日志类别分别拥有固定事件集合，拒绝同名跨类别记录。
        var name = template[..end];
        if (category == typeof(G4QueryExecution).FullName)
        {
            if (name is not ("OracleBranchBegin" or "OracleBranchRelease" or "OracleCancelDispatch")) return;
        }
        else if (category != typeof(OracleSourceAdapter).FullName ||
            name is not ("OracleSourceSession" or "OracleSourceOwnership" or "OracleSourceEvent" or "OracleSourceCleanup")) return;
        lock (gate)
        {
            if (rows.Count == Capacity) { dropped++; return; }
            // 采集顺序与时间在同一锁内确定，源原 UTC 仍使用各事件自己的结构化字段。
            var row = new Dictionary<string, object?> { ["event"] = name, ["monotonicMs"] = clock.Elapsed.TotalMilliseconds };
            foreach (var field in values) // 只摘取任务公开字段；原 owner 和认证材料不进入投影。
            {
                if (field.Key is "QueryId" or "ExecutionId" or "Utc" or "ObservedUtc" or "WorkDeadlineUtc" or "BranchDeadlineUtc"
                    or "Fence" or "Confirmed" or "Phase" or "Trigger" or "Action" or "Instance" or "Sid" or "Audsid" or "Unified"
                    or "Con" or "DeadlineUtc" or "RemainingTicks" or "CleanupRemainingMs")
                    row[field.Key] = field.Value;
                else if (field.Key == "Acquisition" && field.Value is Guid acquisition)
                    row[field.Key] = acquisition.ToString("N");
            }
            rows.Add(row);
        }
    }

    /// <summary>绑定框架传来的真实日志类别；不拥有外部资源。</summary>
    public ILogger CreateLogger(string categoryName) => new Sink(this, categoryName);

    /// <summary>内存记录随测试进程释放。</summary>
    public void Dispose() { }

    /// <summary>仅接收本类别的结构化信息事件。</summary>
    private sealed class Sink(OracleRuntimeSourceEvents owner, string category) : ILogger
    {
        /// <summary>禁用作用域捕获，以免混入身份票据或正文。</summary>
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        /// <summary>只消费生产者已定义的信息级别。</summary>
        public bool IsEnabled(LogLevel level) => level == LogLevel.Information;

        /// <summary>直接传递结构化键值，不调用可能含私密值的格式化函数。</summary>
        public void Log<TState>(LogLevel level, EventId id, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            if (IsEnabled(level) && state is IReadOnlyList<KeyValuePair<string, object?>> values)
                owner.Capture(category, values);
        }
    }
}

/// <summary>离线装配真实日志提供器，核对子进程允许的字段、类别与有限缓冲。</summary>
[TestClass]
public sealed class OracleRuntimeSourceEventsTests
{
    /// <summary>复现宿主后注册的外部日志出口；任何向它投递的原始状态都使隔离测试失败。</summary>
    private sealed class ForbiddenLogProvider : ILoggerProvider, ILogger
    {
        /// <summary>为所有类别提供同一个可探测的出口。</summary>
        public ILogger CreateLogger(string categoryName) => this;

        /// <summary>测试出口不持有外部资源。</summary>
        public void Dispose() { }

        /// <summary>该出口不需要链式作用域。</summary>
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        /// <summary>主动申请全部级别以检验宿主最终过滤。</summary>
        public bool IsEnabled(LogLevel level) => true;

        /// <summary>外部提供器收到任何原始事件即表明隔离被绕过。</summary>
        public void Log<TState>(LogLevel level, EventId id, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
            => throw new InvalidOperationException("测试日志被送入未获准的输出提供器。");
    }

    /// <summary>使用实际子进程提供器生成两组完整的合成结构化记录，供跨语言离线回归重开。</summary>
    [TestMethod]
    public void ExportTwoCompleteSourceBranchesForOfflineReopen()
    {
        // 键、时钟、两次独占执行均属于本离线夹具，无真实源连接。
        const string query = "query-aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa";
        // UTC 时间按不同 SQL 子段铺开，允许消费者检测跨段调换。
        var epoch = DateTimeOffset.Parse("2026-11-22T10:00:00Z", System.Globalization.CultureInfo.InvariantCulture);
        // 与实机子进程的类型过滤、字段投影和导出路径共用同一提供器。
        using var capture = new OracleRuntimeSourceEvents();
        using var factory = LoggerFactory.Create(capture.Configure); // 框架将类别映射到两个真实生产类型。
        var execution = factory.CreateLogger<G4QueryExecution>(); // 观察器完成由查询执行器发出。
        var source = factory.CreateLogger<OracleSourceAdapter>(); // 会话、申请与物理释放来自适配器类别。
        var elapsed = Stopwatch.StartNew(); // 单调采样在同一个原有查询计时器上。
        capture.Bind(elapsed);
        foreach (var index in new[] { 1, 2 }) // 两张独立表分别产生一套完整的分支身份。
        {
            var id = new string((char)('0' + index), 32); // 固定执行号同时用作 Oracle clientId。
            var acquisition = Guid.NewGuid(); // 模拟一次真实物理获取。
            var step = 0; // 每条结构化事件使用不同的 UTC 时刻。
            var start = epoch.AddMilliseconds(index * 30); // 分支时段不交叠。
            DateTimeOffset Next() => start.AddMilliseconds(step++); // 事件原生 UTC 的合成取样。
            void Phase(string phase) => source.LogInformation("OracleSourceOwnership phase={Phase} query={QueryId} execution={ExecutionId} acquisition={Acquisition:N} utc={Utc:O}",
                phase, query, id, acquisition, Next());
            void Action(string action) => source.LogInformation("OracleSourceEvent action={Action} query={QueryId} execution={ExecutionId} utc={Utc:O}",
                action, query, id, Next());
            void Cleanup(string trigger)
            {
                var now = Next(); // 剩余时间与截止使用同一采样，单位为100ns。
                var deadline = start.AddMilliseconds(240); // 两个清理采样沿相同绝对截止。
                source.LogInformation("OracleSourceCleanup trigger={Trigger} query={QueryId} execution={ExecutionId} acquisition={Acquisition:N} utc={Utc:O} deadlineUtc={DeadlineUtc:O} remainingTicks={RemainingTicks}",
                    trigger, query, id, acquisition, now, deadline, (deadline - now).Ticks);
            }
            execution.LogInformation("OracleBranchBegin query={QueryId} owner={Owner} fence={Fence} execution={ExecutionId} utc={Utc:O} workDeadlineUtc={WorkDeadlineUtc:O} branchDeadlineUtc={BranchDeadlineUtc:O}",
                query, "private-sentinel", 1, id, Next(), start.AddMilliseconds(750), start.AddSeconds(1));
            Phase("ACQUIRED");
            source.LogInformation("OracleSourceSession query={QueryId} execution={ExecutionId} instance={Instance} sid={Sid} audsid={Audsid} unified={Unified} con={Con} utc={Utc:O}",
                query, id, 1UL, (ulong)index, (ulong)index, (ulong)index, 3UL, Next());
            Action("EXECUTE");
            Action("EOF");
            foreach (var phase in new[] { "READ_RETURNED", "COMMITTED", "TX_DISPOSED", "POST_STARTED", "POST_RETURNED" }) // 正常读取路径经过事务结算和后验。
                Phase(phase);
            Cleanup("PHYSICAL_DISPOSE");
            Action("PHYSICAL_RELEASE");
            Phase("PHYSICAL_DISPOSED");
            Cleanup("FINAL");
            Phase("CONFIRMED");
            execution.LogInformation("OracleBranchRelease query={QueryId} execution={ExecutionId} confirmed={Confirmed} observedUtc={ObservedUtc:O}",
                query, id, true, Next());
        }
        elapsed.Stop();
        // 两个阶段标识及原截止与实机报告结构一致，时间不作实测产品资格。
        var evidence = new Dictionary<string, object?> { ["queryId"] = query, ["fence"] = 1, ["admittedAtUtc"] = epoch,
            ["deadlineAtUtc"] = epoch.AddSeconds(5), ["elapsedMs"] = elapsed.Elapsed.TotalMilliseconds,
            ["events"] = new[] { new { phase = "SOURCE_READ_COMPLETED", queryId = query, utc = epoch.AddMilliseconds(90) } } };
        capture.Export(evidence);
        Assert.AreEqual(32, ((Dictionary<string, object?>[])evidence["sourceEvents"]!).Length);
        // 跨语言离线运行器独占的系统临时目录；一般 MSTest 调用只检查内存结果。
        var directory = Environment.GetEnvironmentVariable("OMQ_OFFLINE_SOURCE_EVENTS_DIRECTORY");
        if (directory is null) return;
        Assert.AreEqual(Path.TrimEndingDirectorySeparator(Path.GetFullPath(Path.GetTempPath())), Path.GetDirectoryName(Path.GetFullPath(directory)));
        // 只创建固定新文件，不覆盖既有输出。
        using var stream = new FileStream(Path.Combine(directory, "oracle-offline-source-events.json"), FileMode.CreateNew, FileAccess.Write, FileShare.None);
        System.Text.Json.JsonSerializer.Serialize(stream, evidence, new System.Text.Json.JsonSerializerOptions(System.Text.Json.JsonSerializerDefaults.Web));
    }

    /// <summary>两条分支的真实类型日志经同一提供器按执行号关联，忽略其他类别及非公开字段。</summary>
    [TestMethod]
    public void CaptureTwoTypedBranchesWithoutRenderingOwnerOrExceptions()
    {
        // 与实机子进程采用同一注册入口。
        using var capture = new OracleRuntimeSourceEvents();
        // 收集器只接受此工厂分发给指定类型的结构化日志。
        using var factory = LoggerFactory.Create(logging =>
        {
            capture.Configure(logging);
            // 模拟正式宿主在扩展回调之后注册 OTel 和其他出口，均不得收到原日志。
            logging.AddOpenTelemetry();
            logging.AddProvider(new ForbiddenLogProvider());
            logging.SetMinimumLevel(LogLevel.Trace);
        });
        // 同一单调起点贯穿两条模拟分支。
        var elapsed = Stopwatch.StartNew();
        capture.Bind(elapsed);
        // 实际 ILogger 泛型类别分别属于源适配器与查询执行器。
        var source = factory.CreateLogger<OracleSourceAdapter>();
        // 分支释放来自查询执行器在观察者结束后的日志。
        var execution = factory.CreateLogger<G4QueryExecution>();
        foreach (var id in new[] { Guid.NewGuid().ToString("N"), Guid.NewGuid().ToString("N") }) // 独立分支各有唯一的执行和申请身份。
        {
            execution.LogInformation("OracleBranchBegin query={QueryId} owner={Owner} execution={ExecutionId}", "q", "private-sentinel", id);
            source.LogInformation("OracleSourceOwnership phase={Phase} query={QueryId} execution={ExecutionId} acquisition={Acquisition:N}",
                "ACQUIRED", "q", id, Guid.NewGuid());
            execution.LogInformation("OracleBranchRelease query={QueryId} execution={ExecutionId} confirmed={Confirmed}", "q", id, true);
        }
        factory.CreateLogger("other").LogInformation("OracleSourceEvent action={Action}", "ignored");
        // 响应后的同一出口没有保留 Owner、异常或格式化日志文本。
        var evidence = new Dictionary<string, object?>();
        capture.Export(evidence);
        // 直接检查真实字典投影而不依赖文本模糊匹配。
        var rows = (Dictionary<string, object?>[])evidence["sourceEvents"]!;
        Assert.AreEqual(6, rows.Length);
        Assert.AreEqual(2, rows.GroupBy(row => row["ExecutionId"]).Count(group => group.Count() == 3));
        Assert.IsTrue(rows.All(row => !row.ContainsKey("Owner")));
        for (var index = 0; index < 128; index++) // 明确触发容量上限，丢弃可见。
            execution.LogInformation("OracleBranchRelease query={QueryId}", "q");
        capture.Export(evidence);
        Assert.AreEqual(6, evidence["sourceEventsDropped"]);
        Assert.AreEqual(128, ((Dictionary<string, object?>[])evidence["sourceEvents"]!).Length);
    }
}
