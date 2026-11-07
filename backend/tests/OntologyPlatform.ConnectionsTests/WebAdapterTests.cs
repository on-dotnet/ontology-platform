using System.Net;
using System.Text.Json;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>Web网络与数据合同拒绝测试；真实TLS夹具另外显式准入。</summary>
[TestClass]
[DoNotParallelize]
public sealed class WebAdapterTests
{
    /// <summary>只允许完整DNS结果全部匹配精确合成地址，不允许混合、mapped或metadata绕过。</summary>
    [TestMethod]
    public void DnsRequiresEveryAddressToMatchIsolatedFixture()
    {
        // 本任务固定网络地址由可信运行器绑定，不是用户输入的网络白名单。
        var address = IPAddress.Parse("172.30.240.10");
        WebSourceAdapter.ValidateAddresses([address]);
        foreach (var candidate in new[] { "127.0.0.1", "169.254.169.254", "10.0.0.1", "192.168.1.1", "::1", "::ffff:172.30.240.10", "8.8.8.8" })
        {
            Assert.Throws<PgSourceException>(() => WebSourceAdapter.ValidateAddresses([address, IPAddress.Parse(candidate)]));
        }
        Assert.Throws<PgSourceException>(() => WebSourceAdapter.ValidateAddresses([]));
    }

    /// <summary>数据合同不将missing当null、不丢失精确数字、不猜测精度。</summary>
    [TestMethod]
    public void CatalogValidatesDeclaredContractWithoutInferringFromValues()
    {
        // 超出double精度的合法JSON整数必须按原生文本保真校验。
        var catalog = WebJsonCatalog.Parse("[{\"id\":9007199254740993123456789,\"label\":\"合成\",\"reading\":null}]"u8.ToArray());
        Assert.AreEqual(1, catalog.Length);
        Assert.AreEqual(3, catalog[0].Fields.Length);
        Assert.IsNull(catalog[0].Fields[0].Precision);
        foreach (var raw in new[] { "[{\"id\":1,\"label\":\"x\"}]", "[{\"id\":null,\"label\":\"x\",\"reading\":1}]", "[{\"id\":1,\"id\":2,\"label\":\"x\",\"reading\":1}]", "{\"next\":\"loop\",\"items\":[]}" })
        {
            Assert.Throws<PgSourceException>(() => WebJsonCatalog.Parse(System.Text.Encoding.UTF8.GetBytes(raw)));
        }
    }
    /// <summary>实际TLS/SNI、认证及目录成功；同时证明精确大数响应没有进入目录值。</summary>
    [TestMethod]
    [TestCategory("RealWebFixture")]
    public async Task RealProbeAndDiscoverUseTlsAndDeclaredMetadata()
    {
        // 只有当前任务显式fixture文件可准入真实网络测试。
        var input = Fixture();
        SetMode(input, "normal");
        // 当前任务独立CA与准确RunId，不接受系统证书例外。
        var adapter = Adapter(input);
        // 密钥仅从任务私有文件进入内存，断言不包含秘密内容。
        var key = File.ReadAllText(input.KeyPath).Trim();
        // 每次请求独立验证DNS、TCP和TLS，不复用历史Probe。
        var stages = await adapter.ProbeAsync(Profile(), key, CancellationToken.None);
        Assert.IsTrue(stages.All(value => value.Status == "PASS"), string.Join(',', stages.Select(value => value.Name + ":" + value.DiagnosticCode)));
        // 只返回声明的逻辑视图，不保存业务响应值。
        var catalog = await adapter.DiscoverAsync(Profile(), key, CancellationToken.None);
        Assert.AreEqual("VIEW", catalog.Single().Kind);
        Assert.IsFalse(JsonSerializer.Serialize(catalog).Contains("9007199254740993123456789", StringComparison.Ordinal));
        Assert.IsTrue(Stats(input).GetProperty("sni").EnumerateArray().Any(value => value.GetString() == "web-source"));
    }

    /// <summary>重定向首跳拒绝，不发生第二次源请求或向目标转发密钥。</summary>
    [TestMethod]
    [TestCategory("RealWebFixture")]
    public async Task RealRedirectIsNotFollowed()
    {
        // 精确记录源请求计数，不记录请求头。
        var input = Fixture();
        SetMode(input, "redirect");
        // 首跳计数应恰好增加一。
        var before = Stats(input).GetProperty("requests").GetInt32();
        // 固定服务器操作允许第一跳认证，但禁止跟随任意Location。
        var error = await Assert.ThrowsAsync<PgSourceException>(() => Adapter(input).DiscoverAsync(Profile(), File.ReadAllText(input.KeyPath).Trim(), CancellationToken.None));
        Assert.AreEqual("connection_network_forbidden", error.Code);
        Assert.AreEqual(before + 1, Stats(input).GetProperty("requests").GetInt32());
    }

    /// <summary>主机名及信任链错误都必须在HTTP密钥发送前失败。</summary>
    /// <param name="mode">任务内合成错误证书变体。</param>
    [TestMethod]
    [TestCategory("RealWebFixture")]
    [DataRow("wrong-san")]
    [DataRow("wrong-ca")]
    public async Task RealTlsFailureNeverSendsKey(string mode)
    {
        // 通过服务器SNI回调选择合成错误证书，不关闭客户端证书验证。
        var input = Fixture();
        SetMode(input, mode);
        // 只有TLS完成之后才会进入HTTP请求处理。
        var before = Stats(input).GetProperty("requests").GetInt32();
        // 错误报告不包含原异常或密钥。
        var stages = await Adapter(input).ProbeAsync(Profile(), File.ReadAllText(input.KeyPath).Trim(), CancellationToken.None);
        Assert.IsTrue(stages.Any(value => value.DiagnosticCode == "connection_tls_untrusted"), string.Join(',', stages.Select(value => value.Name + ":" + value.Status + ":" + value.DiagnosticCode)));
        Assert.AreEqual(before, Stats(input).GetProperty("requests").GetInt32());
    }

    /// <summary>无效Key不能产生认证成功或目录。</summary>
    [TestMethod]
    [TestCategory("RealWebFixture")]
    public async Task RealAuthenticationRejectsWrongKey()
    {
        // 任务源的真实认证逻辑检查准确Header和值。
        var input = Fixture();
        SetMode(input, "normal");
        // 负例只传固定合成错误值，不把实际Key放入断言。
        var error = await Assert.ThrowsAsync<PgSourceException>(() => Adapter(input).DiscoverAsync(Profile(), "synthetic-wrong-key", CancellationToken.None));
        Assert.AreEqual("connection_auth_failed", error.Code);
    }

    /// <summary>真实响应的预算与合同失败不得伪装为完整空目录。</summary>
    /// <param name="mode">源响应变体。</param>
    [TestMethod]
    [TestCategory("RealWebFixture")]
    [DataRow("oversize")]
    [DataRow("deep")]
    [DataRow("missing")]
    [DataRow("null-id")]
    [DataRow("duplicate")]
    public async Task RealInvalidBodyNeverBecomesEmptyVerified(string mode)
    {
        // fixture只改变响应，不变更任何用户URL或Header。
        var input = Fixture();
        SetMode(input, mode);
        await Assert.ThrowsAsync<PgSourceException>(() => Adapter(input).DiscoverAsync(Profile(), File.ReadAllText(input.KeyPath).Trim(), CancellationToken.None));
    }

    /// <summary>真实body阻塞时取消传至socket，源站观察到未完成响应关闭。</summary>
    [TestMethod]
    [TestCategory("RealWebFixture")]
    public async Task RealCancellationClosesResponseSocket()
    {
        // 源站已经写出正文前缀，然后等待取消。
        var input = Fixture();
        SetMode(input, "stall-body");
        // 记录源端实际观察值，不能以本地Task取消替代网络见证。
        var before = Stats(input).GetProperty("aborted").GetInt32();
        // 有界取消必须中断真实HTTP body read。
        using var cancellation = new CancellationTokenSource(TimeSpan.FromMilliseconds(500));
        // 错误码必须保留调用方取消语义。
        var error = await Assert.ThrowsAsync<PgSourceException>(() => Adapter(input).DiscoverAsync(Profile(), File.ReadAllText(input.KeyPath).Trim(), cancellation.Token));
        Assert.AreEqual("connection_cancelled", error.Code);
        // 只等待已发出的socket关闭事件，有界而非盲目重跑请求。
        for (var attempt = 0; attempt < 20 && Stats(input).GetProperty("aborted").GetInt32() == before; attempt++) await Task.Delay(50);
        Assert.IsTrue(Stats(input).GetProperty("aborted").GetInt32() > before);
    }

    /// <summary>系统代理环境变量不能截获已批准源请求。</summary>
    [TestMethod]
    [TestCategory("RealWebFixture")]
    public async Task RealProxyEnvironmentIsIgnored()
    {
        // 环境只影响当前测试进程，finally恢复原值。
        var previous = Environment.GetEnvironmentVariable("HTTPS_PROXY");
        // fixture地址保持固定，拒绝代理与Cookie由实际handler配置实现。
        var input = Fixture();
        SetMode(input, "normal");
        try
        {
            Environment.SetEnvironmentVariable("HTTPS_PROXY", "http://127.0.0.1:1");
            Assert.AreEqual(1, (await Adapter(input).DiscoverAsync(Profile(), File.ReadAllText(input.KeyPath).Trim(), CancellationToken.None)).Length);
        }
        finally { Environment.SetEnvironmentVariable("HTTPS_PROXY", previous); }
    }

    /// <summary>真实DNS被测试容器hosts覆盖为metadata时，连接前拒绝且源站无请求。</summary>
    [TestMethod]
    [TestCategory("RealWebDnsRejection")]
    public async Task RealDnsRejectsForbiddenResolvedHost()
    {
        // 仅专属负例容器运行本方法，不与正常fixture网络测试混淆。
        var input = Fixture();
        Assert.AreEqual("true", Environment.GetEnvironmentVariable("G4_WEB_DNS_REJECTION"));
        // DNS拒绝必须发生在HTTP请求之前。
        var before = Stats(input).GetProperty("requests").GetInt32();
        // 实际系统DNS/hosts路径进入生产ConnectCallback。
        var error = await Assert.ThrowsAsync<PgSourceException>(() => Adapter(input).DiscoverAsync(Profile(), File.ReadAllText(input.KeyPath).Trim(), CancellationToken.None));
        Assert.AreEqual("connection_network_forbidden", error.Code);
        Assert.AreEqual(before, Stats(input).GetProperty("requests").GetInt32());
    }

    /// <summary>读取当前fixture白名单输入，普通单测无输入时诚实NOT_RUN。</summary>
    private static FixtureInput Fixture()
    {
        // 不搜索或复用历史runtime文件。
        var path = Environment.GetEnvironmentVariable("G4_WEB_FIXTURE_INPUT");
        if (path is null) Assert.Inconclusive("NOT_RUN: explicit current-task HTTPS fixture required.");
        Assert.AreEqual("/fixture/input.json", path);
        // 只有公开CA路径及任务秘密文件路径，不把内容序列化到报告。
        var value = JsonSerializer.Deserialize<FixtureInput>(File.ReadAllText(path!))!;
        Assert.AreEqual("G4-M2-WEB-01", value.TaskId);
        Assert.AreEqual("/fixture/api-key", value.KeyPath);
        Assert.AreEqual("/fixture/ca.crt", value.RootCertificatePath);
        return value;
    }

    /// <summary>创建真实生产Adapter，不注入网络或TLS替身。</summary>
    private static WebSourceAdapter Adapter(FixtureInput input) => new(new WebAdapterOptions { TaskId = input.TaskId, RunId = input.RunId, RootCertificatePath = input.RootCertificatePath }, new WebOperationPolicy());

    /// <summary>完整固定操作配置。</summary>
    private static WebApiConnectionProfile Profile() => new() { BaseOrigin = WebOperationPolicy.Origin, OperationId = WebOperationPolicy.Operation, Method = "GET", ApprovedPath = WebOperationPolicy.Path, Authentication = "API_KEY_REF", Pagination = "NONE", HostPolicyRef = WebOperationPolicy.PolicyReference };

    /// <summary>控制文件只改变合成响应场景，无动态URL或业务数据。</summary>
    private static void SetMode(FixtureInput input, string mode) => File.WriteAllText("/fixture/control.json", JsonSerializer.Serialize(new { mode }));

    /// <summary>源端原子输出安全计数，不包含正文或Header。</summary>
    private static JsonElement Stats(FixtureInput input)
    {
        // 克隆后释放文档，避免轮询持有解析缓冲区。
        using var document = JsonDocument.Parse(File.ReadAllText("/fixture/stats.json"));
        return document.RootElement.Clone();
    }

    /// <summary>当前任务输入的最小形状，不包含密钥明文。</summary>
    private sealed record FixtureInput
    {
        /// <summary>准确任务身份。</summary>
        public required string TaskId { get; init; }

        /// <summary>准确运行身份。</summary>
        public required string RunId { get; init; }

        /// <summary>仅当前任务的API Key文件路径。</summary>
        public required string KeyPath { get; init; }

        /// <summary>仅当前任务的CA文件路径。</summary>
        public required string RootCertificatePath { get; init; }
    }

}
