using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Agents;

namespace OntologyPlatform.AgentTests;

/// <summary>真实数据库、HTTP失败注入与租约预算边界，不伪造成功结果。</summary>
[TestClass]
public sealed class RunFaultTests
{
    /// <summary>治理审计插入失败必须回滚Run及命令；之后相同请求仍能成功。</summary>
    [TestMethod]
    public async Task AuditFailureRollsBackRunAndIdempotencyReceipt()
    {
        // 正式发布与临时数据库由当前测试独占组织。
        using var fixture = new AgentFixture();
        // 先完成正常发布，故障只针对execution.run.create。
        var release = await fixture.PublishAsync();
        // 固定请求用于失败后精确重试。
        var request = RunFlowTests.Request(fixture.Plan(release));
        // 故障函数名只由服务器Guid构成，不接收客户端SQL。
        var suffix = Guid.NewGuid().ToString("N");
        // 仅当前临时数据库注入治理写失败，不包装假的writer。
        await using var database = await fixture.RunFactory.CreateDbContextAsync();
        // SQL标识仅固定前缀与随机hex，组织由fixture生成，不允许外部输入。
        var injectSql = $"CREATE FUNCTION governance.fail_{suffix}() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.\"Action\" = 'execution.run.create' AND NEW.\"OrganizationId\" = '{fixture.Author.OrganizationId}' THEN RAISE EXCEPTION 'fixture audit failure'; END IF; RETURN NEW; END $$; CREATE TRIGGER fail_{suffix} BEFORE INSERT ON governance.\"audit_records\" FOR EACH ROW EXECUTE FUNCTION governance.fail_{suffix}()";
        await database.Database.ExecuteSqlRawAsync(injectSql);
        try
        {
            // 真实PG错误而非任意异常才证明故障位于审计提交。
            var failure = await Assert.ThrowsAsync<Exception>(() => fixture.Runs.CreateAsync(fixture.Author, request, default));
            Assert.IsInstanceOfType<PostgresException>(failure.GetBaseException());
            Assert.AreEqual(0, await database.Runs.CountAsync(value => value.OrganizationId == fixture.Author.OrganizationId));
            Assert.AreEqual(0, await database.Commands.Join(database.Runs.Where(value => value.OrganizationId == fixture.Author.OrganizationId), command => command.RunId, run => run.RunId, (command, run) => command).CountAsync());
        }
        finally
        {
            // 仅移除本测试刚创建的随机触发器与函数。
            var cleanupSql = $"DROP TRIGGER fail_{suffix} ON governance.\"audit_records\"; DROP FUNCTION governance.fail_{suffix}()";
            await database.Database.ExecuteSqlRawAsync(cleanupSql);
        }
        // 回滚不能遗留假幂等回执，同请求可以真正重试。
        var run = await fixture.Runs.CreateAsync(fixture.Author, request, default);
        await fixture.Runs.CancelAsync(fixture.Author, run.RunId, new CancelRunRequest { Command = AgentFixture.Command(0) }, default);
    }

    /// <summary>并发相同命令在不同物理连接只产生一个Run及回执。</summary>
    [TestMethod]
    public async Task ConcurrentCreateHasSingleCommittedRun()
    {
        // 同一真实发布用于并发幂等创建。
        using var fixture = new AgentFixture();
        // 每个调用均先真实解析正式目录。
        var release = await fixture.PublishAsync();
        // 两次完全相同的规范请求。
        var request = RunFlowTests.Request(fixture.Plan(release));
        // 不同HTTP请求拥有不同scope，PublishingCatalog自己的DbContext也不能共用。
        using var secondScope = fixture.Provider.CreateScope();
        // 两个独立scope实际竞争PG幂等事务锁。
        var results = await Task.WhenAll(fixture.Runs.CreateAsync(fixture.Author, request, default), secondScope.ServiceProvider.GetRequiredService<ExecutionRunService>().CreateAsync(fixture.Author, request, default));
        Assert.AreEqual(results[0].RunId, results[1].RunId);
        // 直接检查测试库实际业务事实。
        await using var database = await fixture.RunFactory.CreateDbContextAsync();
        Assert.AreEqual(1, await database.Runs.CountAsync(value => value.OrganizationId == fixture.Author.OrganizationId));
        await fixture.Runs.CancelAsync(fixture.Author, results[0].RunId, new CancelRunRequest { Command = AgentFixture.Command(0) }, default);
    }

    /// <summary>工具次数跨持久事件累计，第四次不能进入Gateway；绝对deadline不因续租重置。</summary>
    [TestMethod]
    public async Task ToolAndAbsoluteTimeBudgetsFailClosed()
    {
        // 真实正式发布供预算用例固定snapshot。
        using var fixture = new AgentFixture();
        // 实际能力版本来自同一registry。
        var release = await fixture.PublishAsync();
        // 计划固定后测试纯运行预算，不假称这些预留完成了查询。
        var plan = fixture.Plan(release);
        // 第一运行测试三次持久工具预留上限。
        var run = await fixture.Runs.CreateAsync(fixture.Author, RunFlowTests.Request(plan), default);
        // 获得真实PG租约。
        var claim = (await fixture.Runs.ClaimAsync("tool-budget", default))!;
        for (var index = 0; index < 3; index++)
            Assert.IsTrue(await fixture.Runs.AppendAsync(run.RunId, "tool-budget", claim.FencingToken, new ToolStartedPayload { InvocationId = Guid.NewGuid().ToString("N"), CapabilityId = plan.CapabilityId, CapabilityVersion = plan.CapabilityVersion, Plan = plan }, default));
        Assert.IsFalse(await fixture.Runs.AppendAsync(run.RunId, "tool-budget", claim.FencingToken, new ToolStartedPayload { InvocationId = "fourth", CapabilityId = plan.CapabilityId, CapabilityVersion = plan.CapabilityVersion, Plan = plan }, default));
        Assert.IsTrue((await RunFlowTests.AllAsync(fixture, run.RunId)).Last().Payload is RunFailedPayload { Code: "tool_budget_exceeded", TotalToolCalls: 3 });
        // 第二运行验证接管仍保留首次deadline。
        var expired = await fixture.Runs.CreateAsync(fixture.Author, RunFlowTests.Request(plan), default);
        claim = (await fixture.Runs.ClaimAsync("time-budget", default))!;
        fixture.Clock.Offset = TimeSpan.FromSeconds(31);
        // 新claim可取得失效租约，但必须立即持久超时失败。
        Assert.IsTrue(await fixture.Executor.RunOneAsync("recovery", default));
        Assert.IsTrue((await RunFlowTests.AllAsync(fixture, expired.RunId)).Last().Payload is RunFailedPayload { Code: "run_timeout" });
    }

    /// <summary>大于128KiB的实际结果事件失败，不能静默截断为成功。</summary>
    [TestMethod]
    public async Task OversizedToolEventPersistsOnlySafeFailure()
    {
        // 正常Gateway结果仍来自真实正式图。
        using var fixture = new AgentFixture();
        // 先读取一份真实结果作为定点故障的基准。
        var release = await fixture.PublishAsync();
        // 真实查询的六态和snapshot由Gateway提供。
        var result = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default);
        // 只替换真实结果中的一条诊断为超限文本，明确这是边界故障注入。
        result = result with { Diagnostics = [new SemanticDiagnostic { Code = "fixture", Severity = DiagnosticSeverity.Warning, Message = new string('中', 128 * 1024) }] };
        // 当前运行正常创建并claim。
        var run = await fixture.Runs.CreateAsync(fixture.Author, RunFlowTests.Request(fixture.Plan(release)), default);
        // 当前fence保护事件append。
        var claim = (await fixture.Runs.ClaimAsync("byte-budget", default))!;
        Assert.IsFalse(await fixture.Runs.AppendAsync(run.RunId, "byte-budget", claim.FencingToken, new ToolCompletedPayload { InvocationId = "oversized", Result = result }, default));
        // 原始超大payload没有作为有效ToolCompleted持久化。
        var events = await RunFlowTests.AllAsync(fixture, run.RunId);
        Assert.IsFalse(events.Any(value => value.Payload is ToolCompletedPayload));
        Assert.IsTrue(events.Last().Payload is RunFailedPayload { Code: "event_budget_exceeded" });
    }

    /// <summary>持久POST取消被worker心跳观察并传播至正在等待的真实HTTP链路。</summary>
    [TestMethod]
    public async Task PersistentCancelPropagatesToDownstreamToken()
    {
        // 真实发布先完成，后续只在HTTP发送前注入延迟。
        using var fixture = new AgentFixture();
        // 当前运行的固定正式版本。
        var release = await fixture.PublishAsync();
        // 正常创建后再开启延迟，避免阻塞固定snapshot步骤。
        var run = await fixture.Runs.CreateAsync(fixture.Author, RunFlowTests.Request(fixture.Plan(release)), default);
        // 观察真实Gateway通过HttpClient发起读取的时刻。
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        // 观察取消确实到达下游token。
        var cancelled = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        fixture.Gate = async (_, token) =>
        {
            entered.TrySetResult();
            try { await Task.Delay(Timeout.InfiniteTimeSpan, token); }
            catch (OperationCanceledException) { cancelled.TrySetResult(); throw; }
        };
        // 真实MAF执行工具而不是测试直接调用Gateway。
        var execution = fixture.Executor.RunOneAsync("cancel-propagation", default);
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(5));
        // 查询当前已提交tool.started序号后发独立取消命令。
        var current = await fixture.Runs.ReadAsync(fixture.Author, run.RunId, default);
        await fixture.Runs.CancelAsync(fixture.Author, run.RunId, new CancelRunRequest { Command = AgentFixture.Command(current.LastSeq) }, default);
        await cancelled.Task.WaitAsync(TimeSpan.FromSeconds(4));
        await execution.WaitAsync(TimeSpan.FromSeconds(4));
        Assert.AreEqual(ExecutionStatus.Cancelled, (await fixture.Runs.ReadAsync(fixture.Author, run.RunId, default)).Status);
        Assert.IsTrue((await RunFlowTests.AllAsync(fixture, run.RunId)).Last().Payload is RunCancelledPayload);
    }
}
