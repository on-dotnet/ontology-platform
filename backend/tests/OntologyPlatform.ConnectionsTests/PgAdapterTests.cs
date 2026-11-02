using System.Text.Json;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>适配器安全入口负例及显式启用的隔离源实测，不以无网络单测代替数据库验收。</summary>
[TestClass]
public sealed class PgAdapterTests
{
    /// <summary>绕过HTTP时，两个适配器入口仍在网络操作之前拒绝目标、TLS或Schema注入。</summary>
    /// <param name="mutation">仅改变一个允许配置字段。</param>
    /// <param name="code">冻结拒绝分类。</param>
    [TestMethod]
    [DataRow("host", "connection_network_forbidden")]
    [DataRow("multi-host", "connection_network_forbidden")]
    [DataRow("port", "connection_network_forbidden")]
    [DataRow("database", "connection_network_forbidden")]
    [DataRow("username", "connection_network_forbidden")]
    [DataRow("tls", "connection_tls_untrusted")]
    [DataRow("schema", "catalog_access_forbidden")]
    [DataRow("schema-sql", "catalog_access_forbidden")]
    [DataRow("schema-empty", "catalog_access_forbidden")]
    [DataRow("schema-null", "catalog_access_forbidden")]
    [DataRow("schema-public", "catalog_access_forbidden")]
    [DataRow("schema-duplicate", "catalog_access_forbidden")]
    public async Task RejectsBypassedTargetPolicy(string mutation, string code)
    {
        // 缺失CA路径可证明拒绝在任何CA读取和网络握手之前发生。
        var adapter = CreateAdapter();
        // 各负例从同一合法配置改变单个安全字段。
        var profile = mutation switch
        {
            "host" => Profile() with { Host = "169.254.169.254" },
            "multi-host" => Profile() with { Host = "pg-source,other" },
            "port" => Profile() with { Port = 5433 },
            "database" => Profile() with { Database = "fixture;Options=-c statement_timeout=0" },
            "username" => Profile() with { Username = "postgres" },
            "tls" => Profile() with { SslMode = "Require" },
            "schema" => Profile() with { AllowedSchemas = ["maintenance"] },
            "schema-sql" => Profile() with { AllowedSchemas = ["production; SELECT pg_sleep(10)"] },
            "schema-empty" => Profile() with { AllowedSchemas = [] },
            "schema-null" => Profile() with { AllowedSchemas = null! },
            "schema-public" => Profile() with { AllowedSchemas = ["production", "public"] },
            _ => Profile() with { AllowedSchemas = ["production", "production"] }
        };
        // 两个入口都必须返回安全异常，原始输入不会出现在异常消息或InnerException。
        var probe = await Assert.ThrowsAsync<PgSourceException>(() => adapter.ProbeAsync(profile, "synthetic-not-a-real-password", CancellationToken.None));
        AssertSafe(probe, code);
        // 发现入口不能依赖曾经通过的Probe或HTTP校验。
        var discover = await Assert.ThrowsAsync<PgSourceException>(() => adapter.DiscoverAsync(profile, "synthetic-not-a-real-password", CancellationToken.None));
        AssertSafe(discover, code);
    }

    /// <summary>显式B服务器只允许精确A/B，且构造后修改原数组不能扩大权限。</summary>
    [TestMethod]
    public async Task ExplicitPublicPolicyIsBoundedAndFrozen()
    {
        // 服务器配置在构造时冻结，之后的外部数组变更不影响适配器。
        string[] upper = ["production", "public"];
        // 不存在的CA和预先取消使本测试只证明策略边界，不冒充真实源成功。
        var adapter = new PgSourceAdapter(new PgAdapterOptions { RootCertificatePath = "/nonexistent/g4-fixture-ca.pem", AllowedSchemas = upper });
        upper[1] = "maintenance";
        // 先取消以确认合法B越过目标策略并保留未执行阶段。
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        // B必须进入网络阶段的取消，而不是被当作任意Schema拒绝。
        var stages = await adapter.ProbeAsync(Profile() with { AllowedSchemas = ["production", "public"] }, "synthetic", cancellation.Token);
        Assert.AreEqual("connection_cancelled", stages[0].DiagnosticCode);
        Assert.IsTrue(stages.Skip(1).All(stage => stage.Status == "NOT_RUN"));
        // 逐项覆盖反序、第三Schema、重复以及单独public均不能借B授权扩大。
        string[][] rejected = [["public", "production"], ["production", "public", "maintenance"], ["production", "public", "public"], ["public"], ["production", "maintenance"]];
        foreach (var schemas in rejected)
        {
            AssertSafe(await Assert.ThrowsAsync<PgSourceException>(() => adapter.ProbeAsync(Profile() with { AllowedSchemas = schemas }, "synthetic", cancellation.Token)), "catalog_access_forbidden");
            AssertSafe(await Assert.ThrowsAsync<PgSourceException>(() => adapter.DiscoverAsync(Profile() with { AllowedSchemas = schemas }, "synthetic", cancellation.Token)), "catalog_access_forbidden");
        }
    }

    /// <summary>服务器配置也不能把固定隔离目标扩展到外部主机、管理员或其它Schema。</summary>
    /// <param name="mutation">拟扩大权限的服务器字段。</param>
    [TestMethod]
    [DataRow("host")]
    [DataRow("port")]
    [DataRow("database")]
    [DataRow("username")]
    [DataRow("schema")]
    public void RejectsExpandedServerPolicy(string mutation)
    {
        // 只更改一个服务器选项；不允许以可信配置名义绕过本阶段目标冻结。
        var options = new PgAdapterOptions
        {
            RootCertificatePath = "/nonexistent/g4-fixture-ca.pem",
            AllowedHost = mutation == "host" ? "localhost" : "pg-source",
            AllowedPort = mutation == "port" ? 5433 : 5432,
            AllowedDatabase = mutation == "database" ? "postgres" : "fixture",
            AllowedUsername = mutation == "username" ? "postgres" : "fixture_reader",
            AllowedSchemas = mutation == "schema" ? ["production", "maintenance"] : ["production"]
        };
        AssertSafe(Assert.Throws<PgSourceException>(() => new PgSourceAdapter(options)), "connection_network_forbidden");
    }

    /// <summary>拒绝缺失或相对CA路径，避免隐式依赖机器信任或工作目录。</summary>
    /// <param name="path">不合格CA配置。</param>
    [TestMethod]
    [DataRow("")]
    [DataRow("ca.pem")]
    public void RequiresExplicitServerTrust(string path)
    {
        AssertSafe(Assert.Throws<PgSourceException>(() => new PgSourceAdapter(new PgAdapterOptions { RootCertificatePath = path })), "connection_tls_untrusted");
    }

    /// <summary>无效凭据在连接前被安全拒绝，不能落入环境密码文件或驱动诊断。</summary>
    /// <param name="secret">边界测试凭据，仅为合成字符串。</param>
    [TestMethod]
    [DataRow("")]
    [DataRow("synthetic\0injection")]
    public async Task RejectsInvalidSecretBeforeNetwork(string secret)
    {
        // 两个入口使用相同的固定目标策略。
        var adapter = CreateAdapter();
        AssertSafe(await Assert.ThrowsAsync<PgSourceException>(() => adapter.ProbeAsync(Profile(), secret, CancellationToken.None)), "connection_auth_failed");
        AssertSafe(await Assert.ThrowsAsync<PgSourceException>(() => adapter.DiscoverAsync(Profile(), secret, CancellationToken.None)), "connection_auth_failed");
    }

    /// <summary>调用方预先取消时，探测不会把任何阶段误标PASS，发现返回统一取消分类。</summary>
    [TestMethod]
    public async Task CancellationPreservesUnobservedStages()
    {
        // 在任何网络操作之前取消，验证真实取消令牌传播而不依赖源服务。
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        // 固定配置避免把取消误测为策略拒绝。
        var adapter = CreateAdapter();
        // 首阶段取消，后续TLS/认证/只读/目录没有被观测。
        var stages = await adapter.ProbeAsync(Profile(), "synthetic", cancellation.Token);
        Assert.AreEqual("connection_cancelled", stages[0].DiagnosticCode);
        Assert.AreEqual("FAIL", stages[0].Status);
        Assert.IsTrue(stages.Skip(1).All(stage => stage.Status == "NOT_RUN"));
        AssertSafe(await Assert.ThrowsAsync<PgSourceException>(() => adapter.DiscoverAsync(Profile(), "synthetic", cancellation.Token)), "connection_cancelled");
    }

    /// <summary>只有Master显式提供本任务私有输入时才在隔离Compose中验真实TLS、目录及类型保真。</summary>
    [TestMethod]
    [TestCategory("RealPgFixture")]
    public async Task RealFixturePreservesAuthorizedMetadata()
    {
        // 该路径由本任务测试容器注入，不搜索或读取历史runtime。
        var inputPath = Environment.GetEnvironmentVariable("G4_PG_ADAPTER_TEST_INPUT");
        if (string.IsNullOrEmpty(inputPath))
        {
            Assert.Inconclusive("NOT_RUN: requires explicit current-task isolated PostgreSQL fixture input.");
        }
        // 私有输入只包含本任务CA路径与密码文件路径，不把秘密放入命令行。
        using var input = JsonDocument.Parse(await File.ReadAllTextAsync(inputPath));
        // 每次从当前任务私有文件读取，驱动连接池关闭。
        var secret = await File.ReadAllTextAsync(input.RootElement.GetProperty("secretFile").GetString()!);
        // CA来自隔离容器挂载，不依赖宿主全局证书。
        var adapter = new PgSourceAdapter(new PgAdapterOptions { RootCertificatePath = input.RootElement.GetProperty("rootCertificatePath").GetString()! });
        // 五阶段必须全部由真实源操作通过。
        var stages = await adapter.ProbeAsync(Profile(), secret, CancellationToken.None);
        Assert.AreEqual(5, stages.Length);
        Assert.IsTrue(stages.All(stage => stage.Status == "PASS"), string.Join(',', stages.Select(stage => stage.Name + ":" + stage.DiagnosticCode)));
        // 发现只允许production且不带业务行。
        var catalog = await adapter.DiscoverAsync(Profile(), secret, CancellationToken.None);
        Assert.IsTrue(catalog.Length > 0 && catalog.All(item => item.Schema == "production"));
        // 合成主表提供全部必须保真的原生类型。
        var fields = catalog.Single(item => item.Name == "heat_event").Fields.ToDictionary(field => field.Name, StringComparer.Ordinal);
        Assert.AreEqual("numeric(8,2)", fields["tap_temp"].NativeType);
        Assert.AreEqual(8, fields["tap_temp"].Precision);
        Assert.AreEqual(2, fields["tap_temp"].Scale);
        Assert.AreEqual("timestamp without time zone", fields["tap_ts"].NativeType);
        Assert.AreEqual("timestamp with time zone", fields["event_time"].NativeType);
        Assert.AreEqual("jsonb", fields["payload"].NativeType);
        Assert.AreEqual("text[]", fields["tags"].NativeType);
        Assert.IsTrue(fields["nullable"].Nullable);
        // 错误密码仍能证明网络与TLS，认证失败后的权限及目录阶段必须未执行。
        var rejected = await adapter.ProbeAsync(Profile(), "deliberately-wrong-synthetic-password", CancellationToken.None);
        Assert.AreEqual("PASS", rejected[0].Status);
        Assert.AreEqual("PASS", rejected[1].Status);
        Assert.AreEqual("connection_auth_failed", rejected[2].DiagnosticCode);
        Assert.IsTrue(rejected.Skip(3).All(stage => stage.Status == "NOT_RUN"));
    }

    /// <summary>创建不依赖实际网络的负例适配器。</summary>
    /// <returns>仅固定目标与不存在的显式CA路径。</returns>
    private static PgSourceAdapter CreateAdapter() => new(new PgAdapterOptions { RootCertificatePath = "/nonexistent/g4-fixture-ca.pem" });

    /// <summary>所有用例唯一的合法类型化配置基线。</summary>
    /// <returns>固定合成目标配置。</returns>
    private static PgConnectionProfile Profile() => new() { Host = "pg-source", Port = 5432, Database = "fixture", Username = "fixture_reader", SslMode = "VerifyFull", AllowedSchemas = ["production"] };

    /// <summary>断言异常只传递冻结分类与安全常量。</summary>
    /// <param name="exception">实际捕获的适配器异常。</param>
    /// <param name="code">预期固定码。</param>
    private static void AssertSafe(PgSourceException exception, string code)
    {
        Assert.AreEqual(code, exception.Code);
        Assert.AreEqual("Source operation failed.", exception.Message);
        Assert.IsNull(exception.InnerException);
    }
}
