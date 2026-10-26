using System.Diagnostics;
using System.Diagnostics.Metrics;
using System.Text;
using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.QueryTests;

/// <summary>独立审查发现的验证读取窗口、审计预算及六态遥测真实回归。</summary>
[TestClass]
public sealed class ReviewRegressionTests
{
    /// <summary>冻结预算99毫秒在依赖前拒绝，100毫秒可以进入真实目录并返回真实不存在。</summary>
    [TestMethod]
    [DataRow(99, 422)]
    [DataRow(100, 404)]
    public async Task TimeoutMinimumMatchesFrozenContract(int timeout, int expected)
    {
        // 隔离PG中不存在的资产避免把快速目录控制误作真实发布成功。
        using var fixture = new QueryFixture();
        // 使用真实registry的能力版本，只有预算边界与资产不存在是变量。
        var capability = fixture.Gateway.GetCapabilities().Single(value => value.Id == "describe_ontology");
        // 先完成真实连接与EF冷启动，再隔离100ms参数合法性而非首次JIT耗时。
        await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Gateway.ExecuteAsync(fixture.Author, new SemanticQueryPlan { AssetId = Guid.NewGuid().ToString("N"), CapabilityId = capability.Id, CapabilityVersion = capability.Version, Depth = 1, MaxRows = 100, TimeoutMs = 5000 }, default));
        // 正式Gateway仍完成真实有界失败审计。
        var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Gateway.ExecuteAsync(fixture.Author, new SemanticQueryPlan { AssetId = Guid.NewGuid().ToString("N"), CapabilityId = capability.Id, CapabilityVersion = capability.Version, Depth = 1, MaxRows = 100, TimeoutMs = timeout }, default));
        Assert.AreEqual(expected, failure.Status);
    }

    /// <summary>Catalog校验完成后真正覆盖当前图，Gateway不能消费另一批却附旧hash。</summary>
    [TestMethod]
    public async Task QueryRejectsGraphChangedAfterCatalogVerification()
    {
        // 整个正常发布使用本轮新建真实PG、Jena和RustFS。
        using var fixture = new QueryFixture();
        // 真实不可变发布必须先完整成功。
        var release = await fixture.PublishAsync();
        // 在Catalog成功与Gateway消费之间直接改真实图。
        var gateway = fixture.AfterResolve(() => ReplaceGraphAsync(release.Manifest.DataGraphIri));
        // 旧实现错误返回EMPTY和旧DataHash；正确实现必须明确不可用。
        var result = await gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default);
        Assert.AreEqual(SemanticQueryStatus.Unavailable, result.Status);
        Assert.IsEmpty(result.Data);
        Assert.IsEmpty(result.Evidence);
    }

    /// <summary>Evidence的Catalog后窗口同样必须绑定实际消费图，不能错报404。</summary>
    [TestMethod]
    public async Task EvidenceRejectsGraphChangedAfterCatalogVerification()
    {
        // 先从正式图取得真实且稳定的证据ID。
        using var fixture = new QueryFixture();
        // 发布与第一次查询没有故障。
        var release = await fixture.PublishAsync();
        // 真实标准来源用于验证后续重定位窗口。
        var found = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default);
        // 使用真实Catalog，成功后只改变真实Jena图。
        var evidence = fixture.AfterRead(() => ReplaceGraphAsync(release.Manifest.DataGraphIri));
        // 图不可用属于依赖503，而不是证据资源不存在404。
        var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => evidence.ReadAsync(fixture.Author, found.Evidence[0].EvidenceId, default));
        Assert.AreEqual(503, failure.Status);
    }

    /// <summary>真实PG成功审计延迟不能突破查询预算后仍返回FOUND。</summary>
    [TestMethod]
    public async Task SuccessfulAuditCannotOutliveQueryBudget()
    {
        // 触发器只匹配当前测试随机组织。
        using var fixture = new QueryFixture();
        // 发布提前完成，计时范围只有查询和审计。
        var release = await fixture.PublishAsync();
        await InstallDelayAsync(fixture);
        try
        {
            // 真实PG pg_sleep(3)必须被一秒预算取消。
            var watch = Stopwatch.StartNew();
            // 不用假审计计数，实际期望失败关闭。
            var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release) with { TimeoutMs = 1000 }, default));
            Assert.AreEqual(503, failure.Status);
            RecordTiming(nameof(SuccessfulAuditCannotOutliveQueryBudget), watch.ElapsedMilliseconds, failure.Status);
            Assert.IsTrue(watch.Elapsed < TimeSpan.FromMilliseconds(2500), "审计不得在预算后继续三秒等待。");
            // 取消的治理事务不能留下allowed事实。
            var allowed = await fixture.Database.Database.SqlQuery<int>($"SELECT COUNT(*)::int AS \"Value\" FROM governance.audit_records WHERE \"OrganizationId\"={fixture.Author.OrganizationId} AND \"Action\"='semantic.query' AND \"Outcome\"='allowed'").SingleAsync();
            Assert.AreEqual(0, allowed);
        }
        finally { await RemoveDelayAsync(fixture); }
    }

    /// <summary>依赖错误后的审计也必须有明确边界，审计失败不能被UNAVAILABLE吞掉。</summary>
    [TestMethod]
    public async Task FailureAuditIsBoundedAndNotHidden()
    {
        // 正常发布均真实，故障仅在正式快照后的HTTP发送。
        using var fixture = new QueryFixture();
        // 固定可信发布作为失败结果上下文。
        var release = await fixture.PublishAsync();
        await InstallDelayAsync(fixture);
        try
        {
            // 用真实传输抛错，审计触发器仍真正执行。
            var gateway = fixture.AfterResolve(() => { fixture.Gate = (_, _) => throw new HttpRequestException("isolated failure"); return Task.CompletedTask; });
            // 固定错误审计预算应比pg_sleep(3)更早失败。
            var watch = Stopwatch.StartNew();
            // 审计尚未成功时不能返回看似已审计的业务结果。
            var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => gateway.ExecuteAsync(fixture.Author, fixture.Plan(release) with { TimeoutMs = 1000 }, default));
            Assert.AreEqual(503, failure.Status);
            RecordTiming(nameof(FailureAuditIsBoundedAndNotHidden), watch.ElapsedMilliseconds, failure.Status);
            Assert.IsTrue(watch.Elapsed < TimeSpan.FromMilliseconds(2500));
        }
        finally { fixture.Gate = null; await RemoveDelayAsync(fixture); }
    }

    /// <summary>调用者在真实PG审计等待时取消必须保留OCE，不能改成业务不可用。</summary>
    [TestMethod]
    public async Task CallerCancellationDuringAuditPropagates()
    {
        // 真实发布在取消时钟启动前完成。
        using var fixture = new QueryFixture();
        // 本轮组织的审计使用真实pg_sleep(3)。
        var release = await fixture.PublishAsync();
        await InstallDelayAsync(fixture);
        try
        {
            // 早于三秒审计结束、晚于正常Catalog和源校验。
            using var caller = new CancellationTokenSource(TimeSpan.FromSeconds(1));
            await Assert.ThrowsAsync<OperationCanceledException>(() => fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), caller.Token));
        }
        finally { await RemoveDelayAsync(fixture); }
    }

    /// <summary>返回业务UNAVAILABLE的catch路径也计入相同六态低基数指标。</summary>
    [TestMethod]
    public async Task UnavailableResultIsCountedOnce()
    {
        // 真实运行后只测受控结果维度，不采集主体或输入。
        using var fixture = new QueryFixture();
        // 发布先完成，避免其他指标影响。
        var release = await fixture.PublishAsync();
        // 监听实际Meter，不替换生产遥测。
        using var listener = new MeterListener();
        // 记录唯一预期不可用状态计数。
        var count = 0L;
        listener.InstrumentPublished = (instrument, current) =>
        {
            if (instrument.Meter.Name == "OntologyPlatform.SemanticQuery" && instrument.Name == "semantic.query.count") current.EnableMeasurementEvents(instrument);
        };
        listener.SetMeasurementEventCallback<long>((_, value, tags, _) =>
        {
            // 标签只能是固定能力与结果，任何高基数键均应失败。
            var values = tags.ToArray();
            Assert.IsTrue(values.All(tag => tag.Key is "capability" or "status"));
            if (values.Any(tag => tag.Key == "status" && Equals(tag.Value, "Unavailable"))) count += value;
        });
        listener.Start();
        // 正式快照后真实依赖传输失败。
        var gateway = fixture.AfterResolve(() => { fixture.Gate = (_, _) => throw new HttpRequestException("isolated failure"); return Task.CompletedTask; });
        Assert.AreEqual(SemanticQueryStatus.Unavailable, (await gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default)).Status);
        Assert.AreEqual(1L, count);
    }

    /// <summary>只保存经过审核的计时与状态，不记录连接、令牌或请求输入。</summary>
    private static void RecordTiming(string test, long elapsedMilliseconds, int status)
    {
        // runner显式提供当前证据文件，不自行探测历史运行目录。
        var path = Environment.GetEnvironmentVariable("G2_QRY_TIMINGS");
        if (path is not null) File.AppendAllText(path, System.Text.Json.JsonSerializer.Serialize(new { test, elapsedMilliseconds, status }) + "\n");
    }

    /// <summary>向当前测试真实隔离Jena图写入无关断言，绝不访问保留卷。</summary>
    private static async Task ReplaceGraphAsync(string graph)
    {
        // 地址来自当前runner随机回环端口，图IRI由真实发布生成。
        using var client = new HttpClient(new HttpClientHandler { UseProxy = false });
        // 标准URL转义保证仅命中当前测试命名图。
        var target = Environment.GetEnvironmentVariable("G2_QRY_JENA") + "/ontology/data?graph=" + Uri.EscapeDataString(graph);
        // 真实HTTP覆盖后的字节不匹配原始已发布源。
        using var response = await client.PutAsync(target, new StringContent("<urn:changed> <urn:p> <urn:o> .", Encoding.UTF8, "text/turtle"));
        response.EnsureSuccessStatusCode();
    }

    /// <summary>真实审计延迟仅限当前fixture组织，标识全部服务器随机生成。</summary>
    private static async Task InstallDelayAsync(QueryFixture fixture)
    {
        Assert.IsTrue(fixture.Author.OrganizationId.All(character => char.IsAsciiLetterOrDigit(character) || character == '-'));
        // DDL不能参数化函数体，但值严格来自测试生成的安全标识。
        var ddl = "CREATE OR REPLACE FUNCTION governance.query_delay() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.\"OrganizationId\" = '" + fixture.Author.OrganizationId + "' AND NEW.\"Action\" = 'semantic.query' THEN PERFORM pg_sleep(3); END IF; RETURN NEW; END $$";
        await fixture.Database.Database.ExecuteSqlRawAsync(ddl);
        await fixture.Database.Database.ExecuteSqlRawAsync("CREATE TRIGGER query_delay BEFORE INSERT ON governance.audit_records FOR EACH ROW EXECUTE FUNCTION governance.query_delay()");
    }

    /// <summary>无论断言成功与否都移除本测试注入的延迟。</summary>
    private static async Task RemoveDelayAsync(QueryFixture fixture)
    {
        await fixture.Database.Database.ExecuteSqlRawAsync("DROP TRIGGER query_delay ON governance.audit_records");
        await fixture.Database.Database.ExecuteSqlRawAsync("DROP FUNCTION governance.query_delay()");
    }
}
