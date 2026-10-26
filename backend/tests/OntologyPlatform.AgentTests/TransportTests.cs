using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using ModelContextProtocol.Client;
using ModelContextProtocol.Protocol;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.AgentTests;

/// <summary>真实SDK客户端和Kestrel传输，验证Cookie、防伪、MCP与Run SSE边界。</summary>
[TestClass]
public sealed class TransportTests
{
    /// <summary>SDK真实initialize/list/call取得正式Gateway结果及强输出Schema。</summary>
    [TestMethod]
    public async Task RealMcpSdkListsExactlyThreeAndCallsPublishedGateway()
    {
        // 所有工具数据来自真实PG/S3/Jena正式发布。
        using var fixture = new AgentFixture();
        // 完整发布后启动真实HTTP安全边界。
        var release = await fixture.PublishAsync();
        // 测试仅替代OIDC登录跳转，实际Cookie存储仍是PG。
        await using var http = await AgentHttpFixture.StartAsync(fixture);
        await http.LoginAsync();
        // 使用正式SDK的Streamable HTTP客户端，不手写JSONRPC成功回包。
        await using var transport = new HttpClientTransport(new HttpClientTransportOptions { Endpoint = new Uri(http.Client.BaseAddress!, "/api/v1/mcp"), TransportMode = HttpTransportMode.StreamableHttp }, http.Client, ownsHttpClient: false);
        // CreateAsync包含真实initialize握手。
        await using var client = await McpClient.CreateAsync(transport);
        // tools/list必须正好三项，没有actor、scope或写工具。
        var tools = await client.ListToolsAsync();
        CollectionAssert.AreEquivalent(new[] { "describe_ontology", "resolve_entity", "traverse_relationships" }, tools.Select(value => value.Name).ToArray());
        foreach (var tool in tools)
        {
            Assert.IsFalse(tool.JsonSchema.GetRawText().Contains("subjectId", StringComparison.Ordinal));
            Assert.IsNotNull(tool.ProtocolTool.OutputSchema);
        }
        // 同一正式计划字段由工具Schema验证，能力版本由服务器选择。
        var result = await client.CallToolAsync("resolve_entity", new Dictionary<string, object?> { ["assetId"] = release.Manifest.AssetId, ["externalId"] = "heat-1", ["siteId"] = "site-a", ["depth"] = 1, ["maxRows"] = 100, ["timeoutMs"] = 5000 });
        Assert.IsFalse(result.IsError == true);
        // 解码唯一真实DTO，合同回调验证数据分支与snapshot。
        var semantic = result.StructuredContent!.Value.Deserialize<SemanticQueryResult>(new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
        Assert.AreEqual(SemanticQueryStatus.Found, semantic.Status);
        Assert.AreEqual(release.Manifest.ReleaseId, semantic.Snapshot.ReleaseId);
        Assert.IsTrue(semantic.Evidence.Length > 0);
        // 实际传输OutputSchema必须逐字节等同唯一Registry，不接受适配器弱化版。
        var declared = tools.Single(value => value.Name == "resolve_entity").ProtocolTool.OutputSchema!.Value;
        Assert.AreEqual(fixture.Gateway.GetCapabilities().Single(value => value.Id == "resolve_entity").OutputSchema.GetRawText(), declared.GetRawText());
        // 仅Synthetic实际结果与公开Schema写入本次临时目录，供独立Ajv合同子集验证。
        var schemaOutput = Environment.GetEnvironmentVariable("G2_AI_SCHEMA_OUTPUT");
        if (schemaOutput is not null)
            await File.WriteAllTextAsync(schemaOutput, JsonSerializer.Serialize(new { schema = declared, result = result.StructuredContent!.Value }));
        // 其余两个工具也必须真正经过SDK与同一Gateway，而非只在list中存在。
        var description = await client.CallToolAsync("describe_ontology", new Dictionary<string, object?> { ["assetId"] = release.Manifest.AssetId, ["depth"] = 1, ["maxRows"] = 100, ["timeoutMs"] = 5000 });
        Assert.IsFalse(description.IsError == true);
        // 遍历使用正式关系与实际实体，不接受模型任意查询。
        var traversal = await client.CallToolAsync("traverse_relationships", new Dictionary<string, object?> { ["assetId"] = release.Manifest.AssetId, ["externalId"] = "heat-1", ["siteId"] = "site-a", ["depth"] = 5, ["maxRows"] = 100, ["timeoutMs"] = 5000 });
        Assert.IsFalse(traversal.IsError == true);
        Assert.IsTrue(http.McpMediaTypes.Any(value => value is "text/event-stream" or "application/json"));
        if (schemaOutput is not null)
            await File.WriteAllTextAsync(schemaOutput, JsonSerializer.Serialize(new { schema = declared, result = result.StructuredContent!.Value, additionalResults = new[] { description.StructuredContent!.Value, traversal.StructuredContent!.Value }, mediaTypes = http.McpMediaTypes.Distinct().Order().ToArray() }));
        // 未登记字段不能把身份、URL或查询文本带入工具。
        var injected = await client.CallToolAsync("resolve_entity", new Dictionary<string, object?> { ["assetId"] = release.Manifest.AssetId, ["depth"] = 1, ["maxRows"] = 100, ["timeoutMs"] = 5000, ["actor"] = "admin", ["sparql"] = "DROP ALL" });
        Assert.IsTrue(injected.IsError);
        // 未授权厂区实际走唯一Gateway并拒绝。
        var denied = await client.CallToolAsync("resolve_entity", new Dictionary<string, object?> { ["assetId"] = release.Manifest.AssetId, ["externalId"] = "heat-1", ["siteId"] = "other-site", ["depth"] = 1, ["maxRows"] = 100, ["timeoutMs"] = 5000 });
        Assert.IsTrue(denied.IsError);
    }

    /// <summary>原生授权在JSON绑定之前，MCP POST缺失防伪与恶意Origin均403。</summary>
    [TestMethod]
    public async Task HttpSecurityRejectsAnonymousCsrfOriginAndMalformedIdentity()
    {
        // 只需真实PG审计，无需虚构正式数据。
        using var fixture = new AgentFixture();
        // 每个测试新Kestrel和内存Cookie。
        await using var http = await AgentHttpFixture.StartAsync(fixture);
        // 匿名坏JSON也必须先401，而不是绑定400泄漏实现路径。
        using var anonymous = await http.Client.PostAsync("/api/v1/execution-runs", new StringContent("bad", Encoding.UTF8, "application/json"));
        Assert.AreEqual(HttpStatusCode.Unauthorized, anonymous.StatusCode);
        await http.LoginAsync();
        http.Client.DefaultRequestHeaders.Remove("X-CSRF-TOKEN");
        // 原生SDK入口仍需防伪，不因JSONRPC缺Command绕过。
        using var missing = await http.Client.PostAsync("/api/v1/mcp", new StringContent("{}", Encoding.UTF8, "application/json"));
        Assert.AreEqual(HttpStatusCode.Forbidden, missing.StatusCode);
        http.Client.DefaultRequestHeaders.Add("X-CSRF-TOKEN", http.Csrf);
        http.Client.DefaultRequestHeaders.Remove("Origin");
        http.Client.DefaultRequestHeaders.Add("Origin", "https://untrusted.invalid");
        // 即使拥有防伪令牌，来源错误仍明确拒绝。
        using var origin = await http.Client.PostAsync("/api/v1/mcp", new StringContent("{}", Encoding.UTF8, "application/json"));
        Assert.AreEqual(HttpStatusCode.Forbidden, origin.StatusCode);
    }

    /// <summary>真实PG事件经.NET原生SSE重放，断流不取消，注销停止旧连接且重连401。</summary>
    [TestMethod]
    public async Task SseReplaysAndLogoutRevokesExistingConnection()
    {
        // 正式发布与运行均真实。
        using var fixture = new AgentFixture();
        // 用无后台worker的运行控制流时序。
        var release = await fixture.PublishAsync();
        // 创建后手动claim产生一个真实持久事件。
        var run = await fixture.Runs.CreateAsync(fixture.Author, RunFlowTests.Request(fixture.Plan(release)), default);
        // 当前租约只用于确认断流没有取消业务。
        var claim = (await fixture.Runs.ClaimAsync("sse-worker", default))!;
        // 真实Cookie支持长连接跨请求撤销验证。
        await using var http = await AgentHttpFixture.StartAsync(fixture);
        await http.LoginAsync();
        // 以ResponseHeadersRead验证实时流，而非等终态buffer整个响应。
        using var response = await http.Client.GetAsync("/api/v1/execution-runs/" + run.RunId + "/events", HttpCompletionOption.ResponseHeadersRead);
        Assert.AreEqual(HttpStatusCode.OK, response.StatusCode);
        Assert.AreEqual("text/event-stream", response.Content.Headers.ContentType!.MediaType);
        // 有限读取一条已提交事件，验证稳定事件ID及原生media type。
        using var reader = new StreamReader(await response.Content.ReadAsStreamAsync());
        // 原生SSE行可能id/type顺序不同，按协议直到空行收一帧。
        var first = await ReadFrameAsync(reader);
        StringAssert.Contains(first, "id: " + run.RunId + ":1");
        StringAssert.Contains(first, "run.started");
        // 并发注销通过同一真实PostgresTicketStore原子撤销session。
        using var logout = await http.Client.PostAsync("/fixture/logout", null);
        Assert.AreEqual(HttpStatusCode.NoContent, logout.StatusCode);
        // 旧HTTP请求仍保留旧Cookie，必须依赖逐轮PG复验才能停止。
        var end = await reader.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(4));
        Assert.IsNull(end);
        Assert.IsFalse((await fixture.Runs.ReadAsync(fixture.Author, run.RunId, default)).CancelRequested);
        // 注销后的重新连接不能恢复旧流。
        using var reconnect = await http.Client.GetAsync("/api/v1/execution-runs/" + run.RunId + "/events");
        Assert.AreEqual(HttpStatusCode.Unauthorized, reconnect.StatusCode);
        // 新会话重放只从给定已持久seq后继续。
        http.Client.DefaultRequestHeaders.Remove("X-CSRF-TOKEN");
        http.Client.DefaultRequestHeaders.Remove("Origin");
        await http.LoginAsync();
        await fixture.Runs.CancelAsync(fixture.Author, run.RunId, new CancelRunRequest { Command = AgentFixture.Command(1) }, default);
        // 终态重放必须返回第二条，然后自然关闭。
        using var replayRequest = new HttpRequestMessage(HttpMethod.Get, "/api/v1/execution-runs/" + run.RunId + "/events");
        replayRequest.Headers.Add("Last-Event-ID", run.RunId + ":1");
        // response完整读取不会重新执行Gateway或修改Run。
        using var replay = await http.Client.SendAsync(replayRequest);
        // 只有cancel终态，不重复seq一。
        var text = await replay.Content.ReadAsStringAsync();
        StringAssert.Contains(text, "id: " + run.RunId + ":2");
        Assert.IsFalse(text.Contains("run.started", StringComparison.Ordinal));
    }

    /// <summary>会话仍有效但完整厂区撤销，旧连接停止且新连接403。</summary>
    [TestMethod]
    public async Task SseRechecksChangedScopeAndAbsoluteSessionExpiry()
    {
        // 正式版本含双厂区，缺任一厂区都不能重放。
        using var fixture = new AgentFixture();
        // 原始owner有完整双厂区权限。
        var release = await fixture.PublishAsync();
        // 创建持久Run并先存一条事件。
        var run = await fixture.Runs.CreateAsync(fixture.Author, RunFlowTests.Request(fixture.Plan(release)), default);
        await fixture.Runs.ClaimAsync("scope-stream", default);
        // 服务器固定Synthetic身份登录，后续撤权用原生同session更新。
        await using var http = await AgentHttpFixture.StartAsync(fixture);
        await http.LoginAsync();
        // 原始流已开始并返回真实事件。
        using var response = await http.Client.GetAsync("/api/v1/execution-runs/" + run.RunId + "/events", HttpCompletionOption.ResponseHeadersRead);
        using var reader = new StreamReader(await response.Content.ReadAsStreamAsync());
        await ReadFrameAsync(reader);
        // 同一个PG会话只剩site-a，旧stream必须在下一轮看到变化。
        using var restricted = await http.Client.PostAsync("/fixture/restrict", null);
        Assert.AreEqual(HttpStatusCode.NoContent, restricted.StatusCode);
        Assert.IsNull(await reader.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(4)));
        using var denied = await http.Client.GetAsync("/api/v1/execution-runs/" + run.RunId + "/events");
        Assert.AreEqual(HttpStatusCode.Forbidden, denied.StatusCode);
        // 再次登录恢复同一测试用户范围，随后推进PG会话时钟至绝对过期。
        http.Client.DefaultRequestHeaders.Remove("X-CSRF-TOKEN");
        http.Client.DefaultRequestHeaders.Remove("Origin");
        await http.LoginAsync();
        using var second = await http.Client.GetAsync("/api/v1/execution-runs/" + run.RunId + "/events", HttpCompletionOption.ResponseHeadersRead);
        using var secondReader = new StreamReader(await second.Content.ReadAsStreamAsync());
        await ReadFrameAsync(secondReader);
        fixture.Clock.Offset = TimeSpan.FromMinutes(31);
        Assert.IsNull(await secondReader.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(4)));
        using var expired = await http.Client.GetAsync("/api/v1/execution-runs/" + run.RunId + "/events");
        Assert.AreEqual(HttpStatusCode.Unauthorized, expired.StatusCode);
        await fixture.Runs.CancelAsync(fixture.Author, run.RunId, new CancelRunRequest { Command = AgentFixture.Command(1) }, default);
    }

    /// <summary>未读取12MiB事件的慢客户端也在25秒内释放服务器请求，断流不取消业务。</summary>
    [TestMethod]
    public async Task SlowSseConnectionIsBoundedAndDisconnectDoesNotCancel()
    {
        // 大批事件保存在当前临时PG，不能以本地数组替代持久重放。
        using var fixture = new AgentFixture();
        // 正式版本和运行保持正常授权。
        var release = await fixture.PublishAsync();
        // 当前运行在流断开后仍应保持RUNNING。
        var run = await fixture.Runs.CreateAsync(fixture.Author, RunFlowTests.Request(fixture.Plan(release)), default);
        // 首次租约生成开始事件。
        var claim = (await fixture.Runs.ClaimAsync("slow-stream", default))!;
        for (var index = 0; index < 510; index++)
            Assert.IsTrue(await fixture.Runs.AppendAsync(run.RunId, "slow-stream", claim.FencingToken, new MessageDeltaPayload { Text = new string('中', 4096) }, default));
        // Kestrel真实网络写入会因本测试不消费响应体产生背压。
        await using var http = await AgentHttpFixture.StartAsync(fixture);
        await http.LoginAsync();
        // 独立观察服务器请求退出，不能只把客户端超时当成功。
        var timer = System.Diagnostics.Stopwatch.StartNew();
        using var response = await http.Client.GetAsync("/api/v1/execution-runs/" + run.RunId + "/events", HttpCompletionOption.ResponseHeadersRead);
        Assert.AreEqual(HttpStatusCode.OK, response.StatusCode);
        await http.StreamStopped.WaitAsync(TimeSpan.FromSeconds(28));
        Assert.IsTrue(timer.Elapsed >= TimeSpan.FromSeconds(24));
        Assert.IsTrue(timer.Elapsed < TimeSpan.FromSeconds(28));
        Assert.IsFalse((await fixture.Runs.ReadAsync(fixture.Author, run.RunId, default)).CancelRequested);
        await fixture.Runs.CancelAsync(fixture.Author, run.RunId, new CancelRunRequest { Command = AgentFixture.Command(511) }, default);
    }

    /// <summary>HTTP游标错误在发送任何事件之前返回400/409，不转成200流。</summary>
    [TestMethod]
    public async Task SseHttpCursorErrorsAreAccurate()
    {
        // 真实零事件运行提供明确lastSeq边界。
        using var fixture = new AgentFixture();
        // 正式目录真实解析。
        var release = await fixture.PublishAsync();
        // 尚未启动worker，lastSeq为零。
        var run = await fixture.Runs.CreateAsync(fixture.Author, RunFlowTests.Request(fixture.Plan(release)), default);
        // 原生Cookie与授权保持正常，专门测试游标边界。
        await using var http = await AgentHttpFixture.StartAsync(fixture);
        await http.LoginAsync();
        foreach (var pair in new[] { ("other:0", HttpStatusCode.BadRequest), (run.RunId + ":1", HttpStatusCode.Conflict) })
        {
            // 每个请求独立头，不污染后续重放。
            using var request = new HttpRequestMessage(HttpMethod.Get, "/api/v1/execution-runs/" + run.RunId + "/events");
            request.Headers.Add("Last-Event-ID", pair.Item1);
            // 错误应是原生ProblemDetails而非text/event-stream。
            using var response = await http.Client.SendAsync(request);
            Assert.AreEqual(pair.Item2, response.StatusCode);
            Assert.AreEqual("application/problem+json", response.Content.Headers.ContentType!.MediaType);
        }
        await fixture.Runs.CancelAsync(fixture.Author, run.RunId, new CancelRunRequest { Command = AgentFixture.Command(0) }, default);
    }

    /// <summary>读取一帧完整SSE，保留协议分行，不按网络chunk猜事件边界。</summary>
    private static async Task<string> ReadFrameAsync(StreamReader reader)
    {
        // 仅当前帧有界文本，用于测试断言。
        var lines = new List<string>();
        while (true)
        {
            // 四秒内应发送已提交事件，不等待25秒连接换新。
            var line = await reader.ReadLineAsync().WaitAsync(TimeSpan.FromSeconds(4));
            if (line is null || line.Length == 0) return string.Join("\n", lines);
            lines.Add(line);
        }
    }
}
