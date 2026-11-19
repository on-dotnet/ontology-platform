using System.Text.Json;
using ModelContextProtocol.Protocol;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Agents;

namespace OntologyPlatform.AgentTests;

/// <summary>用可推进的单调时钟走正式 MCP 与 Run 分发，观测预留、源清理、绑定及编码的同一截止。</summary>
[TestClass]
public sealed class G4ToolDeadlineTests
{
    /// <summary>较早 Run、查询参数、外层核验截止各自可以最早，充足时仍使用五秒请求上限。</summary>
    [TestMethod]
    [DataRow(2200, 5000, 8000, 2200)]
    [DataRow(30000, 700, 8000, 700)]
    [DataRow(30000, 5000, 1400, 1400)]
    [DataRow(30000, 5000, 8000, 5000)]
    public async Task EarliestDeadlineCoversReserveCleanupBindAndWire(int runMs, int queryMs, int outerMs, int limitMs)
    {
        // 最早调用入口先于 Run 调度；后面的 90 毫秒不能延长 Query.TimeoutMs。
        var clock = new ProbeClock();
        // 保留 MCP 退出后仍可核对的最外层请求。
        using var root = new G4RequestDeadline(clock, default);
        // 当前时钟及其 UTC 对应点固定，可精确核对持久期限的投影值。
        var entry = clock.GetUtcNow();
        // 现有语义读操作可能比 Run 与 Query 都更早。
        using var outer = new SemanticReadDeadline(entry.AddMilliseconds(outerMs));
        clock.Advance(90);
        // 既有 Run 总期限仍是第一次建立的三十秒，持久预留使用相同身份。
        var run = new G4QueryRunReference(entry.AddMilliseconds(runMs).AddSeconds(-30));
        // 使用真实 MCP 的输入读取、分发和编码，仅将数据库与源 I/O 替换为界面观察。
        var probe = new Probe(clock, run);
        // 检查正式 MCP 返回的最终结果或拒绝。
        var output = await probe.CallAsync(queryMs);
        Assert.IsFalse(output.IsError == true);
        CollectionAssert.AreEqual(new[] { "reserve", "gateway", "cleanup", "bind" }, probe.Seen.Select(x => x.Stage).ToArray());
        Assert.IsTrue(probe.Seen.All(x => x.Deadline == entry.AddMilliseconds(limitMs)));
        Assert.AreEqual(entry.AddMilliseconds(limitMs), root.DeadlineUtc);
        Assert.AreEqual(Probe.Wire, output.StructuredContent!.Value.GetRawText());
        Assert.AreEqual(Probe.Wire, ((TextContentBlock)output.Content.Single()).Text);
    }

    /// <summary>刚过期的既有 Run 保留原截止，持久预留、源清理及绑定都不会发生。</summary>
    [TestMethod]
    public async Task ExpiredRunClosesParentBeforePersistence()
    {
        // 让运行在入口前刚过期，即使真实线程池尚未调度计时器也应立即拒绝。
        var clock = new ProbeClock();
        // 保留 MCP 退出后仍可核对的最外层请求。
        using var root = new G4RequestDeadline(clock, default);
        // 从服务器起始时刻重建该 Run 原有的三十秒期限。
        var run = new G4QueryRunReference(clock.GetUtcNow().AddSeconds(-30).AddTicks(-1));
        // 记录确切的预留、源及绑定边界。
        var probe = new Probe(clock, run);
        // 检查正式 MCP 返回的最终结果或拒绝。
        var output = await probe.CallAsync(5000);
        Assert.IsTrue(output.IsError);
        Assert.IsEmpty(probe.Seen);
        Assert.AreEqual(run.Deadline, root.DeadlineUtc);
        Assert.IsTrue(root.Token.IsCancellationRequested);
    }

    /// <summary>源工作跨过 Run 截止后实体释放不能据晚到确认腾出占位，引用也不能进入绑定。</summary>
    [TestMethod]
    public async Task OverdueSourceCleanupCannotUseTheFiveSecondParent()
    {
        // 在原 Run 截止的准确边界完成源工作，模拟回滚后的迟到确认。
        var clock = new ProbeClock();
        // 从服务器起始时刻重建该 Run 原有的三十秒期限。
        var run = new G4QueryRunReference(clock.GetUtcNow().AddSeconds(-28));
        // 记录确切的预留、源及绑定边界。
        var probe = new Probe(clock, run) { WorkMs = 2000 };
        // 检查正式 MCP 返回的最终结果或拒绝。
        var output = await probe.CallAsync(5000);
        Assert.IsTrue(output.IsError);
        Assert.IsFalse(probe.CleanupConfirmed);
        CollectionAssert.AreEqual(new[] { "reserve", "gateway", "cleanup" }, probe.Seen.Select(x => x.Stage).ToArray());
    }

    /// <summary>内层绑定正常完成后，在 MCP 最后一次编码交付检查跨过原 Run 截止仍须返回固定拒绝。</summary>
    [TestMethod]
    public async Task ExpiryDuringOuterEncodingRejectsCompletedDelivery()
    {
        // 绑定前与绑定后的内层时钟保持不变，仅推进外层编码的最后读钟。
        var clock = new ProbeClock();
        // 从服务器起始时刻重建该 Run 原有的三十秒期限。
        var run = new G4QueryRunReference(clock.GetUtcNow().AddSeconds(-28));
        // 记录确切的预留、源及绑定边界。
        var probe = new Probe(clock, run) { ExpireWhileEncoding = true };
        // 检查正式 MCP 返回的最终结果或拒绝。
        var output = await probe.CallAsync(5000, recover: true);
        Assert.IsTrue(output.IsError);
        Assert.IsTrue(probe.CleanupConfirmed);
        Assert.AreEqual("bind", probe.Seen.Last().Stage);
        Assert.AreEqual(2, clock.EncodingReads);
        Assert.IsNull(output.StructuredContent);
        Assert.AreEqual("semantic_tool_rejected", ((TextContentBlock)output.Content.Single()).Text);
    }

    /// <summary>提供受控单调时钟；编码测试只在已退出持久绑定范围后推进。</summary>
    private sealed class ProbeClock : TimeProvider
    {
        /// <summary>当前时间，按 TimeSpan tick 计量。</summary>
        private long ticks;

        /// <summary>绑定发生时的内层，供区分实际外层编码读取。</summary>
        public G4RequestDeadline? BoundScope { get; set; }

        /// <summary>外层编码已执行的读钟次数。</summary>
        public int EncodingReads { get; private set; }

        /// <summary>单调频率与手动推进的 tick 一致。</summary>
        public override long TimestampFrequency => TimeSpan.TicksPerSecond;

        /// <summary>将固定 UTC 锚点与单调进度保持一致。</summary>
        public override DateTimeOffset GetUtcNow() => DateTimeOffset.UnixEpoch.AddTicks(ticks);

        /// <summary>只在规定边界推进，避免用真实休眠撞时序。</summary>
        public void Advance(int milliseconds) => ticks += TimeSpan.FromMilliseconds(milliseconds).Ticks;

        /// <summary>返回当前单调位置，第二次编码读钟精确到达 Run 截止。</summary>
        public override long GetTimestamp()
        {
            if (BoundScope is not null && G4RequestDeadline.Current is { } scope && scope != BoundScope && ++EncodingReads == 2)
                Advance(2000);
            return ticks;
        }
    }

    /// <summary>只记录系统真实分发经过的 I/O 界面；本测试没有打开或模拟数据库事务。</summary>
    private sealed class Probe(ProbeClock clock, G4QueryRunReference run) : IG4QueryRunStore, ISemanticGateway
    {
        /// <summary>有意保留空格，确认传输复用原网关字节。</summary>
        public const string Wire = """{"status": "EMPTY"}""";

        /// <summary>源工作占用的合成时长。</summary>
        public int WorkMs { get; init; }

        /// <summary>只在限定用例的绑定结束后触发较早编码截止。</summary>
        public bool ExpireWhileEncoding { get; init; }

        /// <summary>正式分支物理生命周期是否接受了本次清理确认。</summary>
        public bool CleanupConfirmed { get; private set; }

        /// <summary>正式 Run 与 MCP 调用链中各个边界实际看到的截止。</summary>
        public List<(string Stage, DateTimeOffset Deadline)> Seen { get; } = [];

        /// <summary>用合法固定请求通过真正的工具输入校验、预留、绑定与 MCP 编码。</summary>
        public Task<CallToolResult> CallAsync(int timeoutMs, bool recover = false)
        {
            // 仅此用例的固定授权范围和合成请求，没有外部资源。
            var actor = new ActorContext { SubjectId = "q", OrganizationId = "org", SiteIds = ["s"], Roles = [], TraceId = "t", CorrelationId = "c" };
            // 执行和历史恢复都从同一 MCP 调用进入，恢复请求没有 Query.TimeoutMs 参数。
            var tools = new SemanticMcpTools(this, this, clock);
            if (recover)
            {
                return tools.CallAsync(actor, "g4_query_result", new Dictionary<string, JsonElement>
                {
                    ["queryId"] = JsonSerializer.SerializeToElement("query-fixture")
                }, default, new string('0', 64), run);
            }
            // 测试必须经过正式 Query.TimeoutMs 读取；不能直接把时长送给替身。
            var query = JsonSerializer.SerializeToElement(new { assetId = "asset", ontologyReleaseId = "release", mappingReleaseIds = new[] { "mapping" },
                capabilityId = "g4_resolve_entity", capabilityVersion = new string('a', 64), relationshipIris = Array.Empty<string>(),
                depth = 1, maxRows = 2, timeoutMs, filters = new { siteId = "s", entityExternalId = "entity" } });
            return tools.CallAsync(actor, "g4_resolve_entity", new Dictionary<string, JsonElement>
            {
                ["query"] = query, ["idempotencyKey"] = JsonSerializer.SerializeToElement("key"), ["selectionQueryId"] = JsonSerializer.SerializeToElement<string?>(null)
            }, default, new string('0', 64), run);
        }

        /// <summary>较短请求截止不应改变传给数据库的原运行身份及三十秒期限。</summary>
        public Task ReserveRunAsync(ActorContext actor, string sessionReference, string runId, DateTimeOffset deadline, CancellationToken token)
        {
            Assert.AreEqual(run.RunId, runId);
            Assert.AreEqual(run.Deadline, deadline);
            Seen.Add(("reserve", G4RequestDeadline.Current!.DeadlineUtc));
            return Task.CompletedTask;
        }

        /// <summary>模拟源工作与释放回调，实际使用相同的 G4 与 Oracle 期限合同。</summary>
        public Task<G4QueryDelivery> ExecuteG4Async(ActorContext actor, string sessionReference, G4SemanticQuery query,
            string idempotencyKey, string? selectionQueryId, CancellationToken token) => ReadSource(query.TimeoutMs, token);

        /// <summary>恢复工具沿原 Run 和 G4 缺省上限执行，不增加额外时间。</summary>
        public Task<G4QueryDelivery> ReadG4Async(ActorContext actor, string sessionReference, string queryId, bool includeResult,
            CancellationToken token) => ReadSource(5000, token);

        /// <summary>复用准确物理申请并在受控耗时后核验清理边界。</summary>
        private Task<G4QueryDelivery> ReadSource(int timeoutMs, CancellationToken token)
        {
            // 和真实 Gateway 一样在后续解析点再次收紧，不允许覆盖 Run 的更早绝对界。
            using var gateway = new G4RequestDeadline(clock, token);
            gateway.Tighten(timeoutMs);
            Seen.Add(("gateway", gateway.DeadlineUtc));
            // 物理申请与清理计量使用同一个测试单调时钟。
            using var physical = new G4OracleSourceLifetime("query-fixture", clock);
            // 准确申请身份只可在原清理窗口内确认。
            var acquired = physical.BeginSource();
            clock.Advance(WorkMs);
            Seen.Add(("cleanup", G4RequestDeadline.Current!.DeadlineUtc));
            physical.TightenCleanup(gateway.Remaining);
            physical.ConfirmReleased(acquired);
            CleanupConfirmed = physical.CleanupConfirmed;
            return Task.FromResult(new G4QueryDelivery
            {
                View = new G4QueryView { QueryId = "query-fixture", ExecutionStatus = "COMPLETED", CreatedAtUtc = "1970-01-01T00:00:00Z",
                    CompletedAtUtc = "1970-01-01T00:00:01Z", ExpiresAtUtc = "1970-01-02T00:00:00Z", ResultHash = null, ErrorCode = null },
                ResultBytes = System.Text.Encoding.UTF8.GetBytes(Wire)
            });
        }

        /// <summary>记录内层的准确期限，并仅在指定用例中启动外层编码边界。</summary>
        public Task BindRunQueryAsync(ActorContext actor, string sessionReference, string runId, string queryId, CancellationToken token)
        {
            Seen.Add(("bind", G4RequestDeadline.Current!.DeadlineUtc));
            if (ExpireWhileEncoding) clock.BoundScope = G4RequestDeadline.Current;
            return Task.CompletedTask;
        }

        /// <summary>提供唯一登记的合成 G4 查询版本。</summary>
        public SemanticCapability[] GetCapabilities() => [new() { Id = "g4_resolve_entity", Version = new string('a', 64) }];

        /// <summary>旧 G2 路径不应被此正式 G4 测试调用。</summary>
        public Task<SemanticQueryResult> ExecuteAsync(ActorContext actor, SemanticQueryPlan plan, CancellationToken cancellationToken) =>
            throw new AssertFailedException("G4 工具进入了 G2 路径。");
    }
}
