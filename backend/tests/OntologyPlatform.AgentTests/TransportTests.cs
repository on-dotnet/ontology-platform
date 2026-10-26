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
