using System.Text.Json;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>只在明确提供本任务私有runtime时执行的真实Oracle测试，不以跳过伪造通过。</summary>
[TestClass]
[TestCategory("RealOracleFixture")]
public sealed class OracleFixtureSecurityTests
{
    /// <summary>真实TCPS认证、原生只读限制和元数据必须全部成功。</summary>
    [TestMethod]
    public async Task ProbeRequiresAllFiveRealStages()
    {
        // 路径仅由任务控制器注入，秘密不进入断言输出。
        var fixture = Load();
        // 真实驱动使用独立信任wallet。
        var adapter = new OracleSourceAdapter(fixture.Options);
        // 精确阶段断言不输出秘密或底层异常消息。
        var stages = await adapter.ProbeAsync(Profile(), fixture.Secret, CancellationToken.None);
        Assert.AreEqual(5, stages.Length);
        foreach (var stage in stages) Assert.AreEqual("PASS", stage.Status, stage.Name + ":" + stage.DiagnosticCode);
    }

    /// <summary>真实字典读取保持大小写、NUMBER和时间类型，不读取LOB正文。</summary>
    [TestMethod]
    public async Task DiscoveryPreservesRealOracleMetadata()
    {
        // 真实合成fixture不与其它数据库共享凭据。
        var fixture = Load();
        // 直接调用产品实现，避免测试替身目录。
        var objects = await new OracleSourceAdapter(fixture.Options).DiscoverAsync(Profile(), fixture.Secret, CancellationToken.None);
        Assert.AreEqual(3, objects.Length);
        Assert.IsTrue(objects.Any(value => value.Schema == "CaseOwner" && value.Name == "MixedCase"));
        // 数据字典中的未声明NUMBER精度必须为null。
        var fields = objects.Single(value => value.Schema == "PRODUCTION" && value.Name == "METADATA_TYPES").Fields;
        Assert.IsNull(fields.Single(value => value.Name == "UNDECLARED_NUMBER").Precision);
        Assert.AreEqual(-2, fields.Single(value => value.Name == "NEGATIVE_SCALE").Scale);
        Assert.AreEqual("WITH_LOCAL_TIME_ZONE", fields.Single(value => value.Name == "LOCAL_TIME").OracleMetadata!.TimeZoneKind);
        Assert.AreEqual("METADATA_ONLY", fields.Single(value => value.Name == "LARGE_TEXT").OracleMetadata!.SupportStatus);
    }

    /// <summary>错误口令必须真实认证失败，错误信息保持安全码。</summary>
    [TestMethod]
    public async Task WrongPasswordCannotPassAuthentication()
    {
        // 仅改变本任务合成口令，不访问真实用户凭据。
        var fixture = Load();
        // 源端返回的错误不进入产品报告原文。
        var stages = await new OracleSourceAdapter(fixture.Options).ProbeAsync(Profile(), fixture.Secret + "wrong", CancellationToken.None);
        Assert.AreEqual("connection_auth_failed", stages.Single(value => value.Name == "AUTH").DiagnosticCode);
        Assert.IsFalse(stages.All(value => value.Status == "PASS"));
    }

    /// <summary>独立握手使用错误CA时拒绝连接，不能借正常wallet提升成功。</summary>
    [TestMethod]
    public async Task WrongCaRejectsRealTlsHandshake()
    {
        // 错误CA由控制器生成，只包含公开信任材料。
        var fixture = Load();
        // 仅替换CA，正常wallet保持不变。
        var options = new OracleAdapterOptions { RootCertificatePath = Path.Combine(Path.GetDirectoryName(fixture.Options.RootCertificatePath)!, "wrong-ca.pem"), WalletDirectory = fixture.Options.WalletDirectory };
        // 真实握手必须失败，不用异常替身。
        var stages = await new OracleSourceAdapter(options).ProbeAsync(Profile(), fixture.Secret, CancellationToken.None);
        Assert.IsTrue(stages.Any(value => value.DiagnosticCode == "connection_tls_untrusted"));
        Assert.IsFalse(stages.All(value => value.Status == "PASS"));
    }

    /// <summary>预握手成功也不能掩盖真正ODP连接的错误wallet。</summary>
    [TestMethod]
    public async Task WrongWalletRejectsActualDriverConnection()
    {
        // 正常CA使独立握手先通过，错误wallet只作用于实际ODP连接。
        var fixture = Load();
        // 客户端wallet只信任另一张不相关的CA。
        var options = new OracleAdapterOptions { RootCertificatePath = fixture.Options.RootCertificatePath, WalletDirectory = Path.Combine(Path.GetDirectoryName(fixture.Options.WalletDirectory)!, "wrong-wallet") };
        // 前置握手本身成功，不代表真正ODP连接已经验证。
        var adapter = new OracleSourceAdapter(options);
        await (Task)typeof(OracleSourceAdapter).GetMethod("VerifyTlsAsync", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!.Invoke(adapter, [CancellationToken.None])!;
        // 真正驱动失败时公开TLS阶段不能保持PASS。
        var stages = await adapter.ProbeAsync(Profile(), fixture.Secret, CancellationToken.None);
        Assert.AreEqual("FAIL", stages.Single(value => value.Name == "TLS").Status);
        Assert.IsTrue(stages.Any(value => value.DiagnosticCode == "connection_tls_untrusted"));
        Assert.IsFalse(stages.All(value => value.Status == "PASS"));
    }

    /// <summary>加载固定runtime合同；缺失时明确失败而非skip。</summary>
    internal static (OracleAdapterOptions Options, string Secret) Load()
    {
        // 环境只传外置路径，不包含认证秘密。
        var path = Environment.GetEnvironmentVariable("G4_ORACLE_TEST_RUNTIME");
        Assert.IsFalse(string.IsNullOrWhiteSpace(path), "Oracle fixture runtime is required");
        // 解析本任务控制器创建的非公开路径合同。
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        // TaskId阻止借用其它任务runtime。
        var root = document.RootElement;
        Assert.AreEqual("G4-M2-ORACLE-01", root.GetProperty("taskId").GetString());
        return (new OracleAdapterOptions { RootCertificatePath = root.GetProperty("rootCertificatePath").GetString()!, WalletDirectory = root.GetProperty("walletDirectory").GetString()! }, File.ReadAllText(root.GetProperty("secretFile").GetString()!));
    }

    /// <summary>本轮唯一批准的目标，不接受环境注入连接串。</summary>
    internal static OracleConnectionProfile Profile() => new() { Host = "oracle-source", Port = 2484, ServiceName = "FREEPDB1", Username = "FIXTURE_READER", Tls = true, AllowedOwners = ["PRODUCTION", "CaseOwner"] };
}

/// <summary>控制面启用有界等待并独立见证源会话时执行，不混入普通探测。</summary>
[TestClass]
[TestCategory("RealOracleCancellation")]
public sealed class OracleCancellationTests
{
    /// <summary>取消必须贯通真正进行中的Oracle命令，源端结束由独立控制器另证。</summary>
    [TestMethod]
    public async Task ActualCommandCancellationReturnsBoundedFailure()
    {
        // 控制器事先使证明视图等待十秒，产品本身不发送延迟SQL。
        var fixture = OracleFixtureSecurityTests.Load();
        // 早于五秒命令超时，以便区分真实调用方取消。
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(2));
        // 记录实际调用耗时，不把Task取消等同源端结束。
        var clock = System.Diagnostics.Stopwatch.StartNew();
        // 无任何可发布的部分目录。
        var error = await Assert.ThrowsAsync<PgSourceException>(() => new OracleSourceAdapter(fixture.Options).DiscoverAsync(OracleFixtureSecurityTests.Profile(), fixture.Secret, cancellation.Token));
        Assert.AreEqual("connection_cancelled", error.Code);
        Assert.IsTrue(clock.Elapsed < TimeSpan.FromSeconds(5));
    }
}

/// <summary>控制面主动施加精确权限负例时执行，恢复由控制器finally负责。</summary>
[TestClass]
[TestCategory("RealOraclePermissionNegative")]
public sealed class OraclePermissionNegativeTests
{
    /// <summary>当前源权限不满足时，探测与目录均失败关闭，不产生部分可信目录。</summary>
    [TestMethod]
    public async Task ProbeAndDiscoveryRejectChangedSourcePrivileges()
    {
        // 控制器只允许两种已冻结错误分类，不接受任意成功预期。
        var expected = Environment.GetEnvironmentVariable("G4_ORACLE_EXPECTED_FAILURE");
        Assert.IsTrue(expected is "connection_readonly_unverified" or "catalog_permission_limited");
        // 使用同一个产品适配器但每次调用独立无池连接。
        var fixture = OracleFixtureSecurityTests.Load();
        // 不替换源调用或模拟字典返回值。
        var adapter = new OracleSourceAdapter(fixture.Options);
        // 五阶段不能全成功，至少一项给出准确受控分类。
        var stages = await adapter.ProbeAsync(OracleFixtureSecurityTests.Profile(), fixture.Secret, CancellationToken.None);
        Assert.IsFalse(stages.All(value => value.Status == "PASS"));
        Assert.IsTrue(stages.Any(value => value.DiagnosticCode == expected));
        // 撤权后目录不能静默缩减再当作完整结果。
        var error = await Assert.ThrowsAsync<PgSourceException>(() => adapter.DiscoverAsync(OracleFixtureSecurityTests.Profile(), fixture.Secret, CancellationToken.None));
        Assert.AreEqual(expected, error.Code);
    }
}

/// <summary>控制器切换同一源端的合成证书后，验证产品实际握手拒绝。</summary>
[TestClass]
[TestCategory("RealOracleTlsNegative")]
public sealed class OracleTlsNegativeTests
{
    /// <summary>过期和错误SAN均由真实Oracle监听器提供，不替换TLS回调。</summary>
    [TestMethod]
    public async Task ChangedServerCertificateIsRejected()
    {
        // 正常CA和wallet保持不变，只由源控制面改变服务端叶证书。
        var fixture = OracleFixtureSecurityTests.Load();
        // 真正产品握手应拒绝且没有任何成功认证阶段。
        var stages = await new OracleSourceAdapter(fixture.Options).ProbeAsync(OracleFixtureSecurityTests.Profile(), fixture.Secret, CancellationToken.None);
        Assert.AreEqual("FAIL", stages.Single(value => value.Name == "TLS").Status);
        Assert.AreEqual("connection_tls_untrusted", stages.Single(value => value.Name == "TLS").DiagnosticCode);
        Assert.AreEqual("NOT_RUN", stages.Single(value => value.Name == "AUTH").Status);
    }
}
