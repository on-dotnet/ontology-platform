using System.Reflection;
using System.Text.Json;
using MySqlConnector;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>显式提供本任务私有运行目录才可执行的真实Doris验证，缺fixture直接失败。</summary>
[TestClass]
[TestCategory("DorisFixture")]
[DoNotParallelize]
public sealed class DorisFixtureSecurityTests
{
    /// <summary>真实适配器必须完成五阶段及完整字段目录，不把探针原型当产品实现。</summary>
    [TestMethod]
    public async Task RealAdapterReadsSyntheticMetadata()
    {
        // 只读取本任务私有运行目录；不枚举用户认证材料。
        var runtime = Runtime();
        // 合成只读口令仅本次调用内存使用。
        var password = await File.ReadAllTextAsync(Path.Combine(runtime, "private", "reader.pass"));
        // 产品适配器使用同一私有CA，服务器证书SAN为localhost。
        var adapter = new DorisSourceAdapter(new DorisAdapterOptions { RootCertificatePath = Path.Combine(runtime, "tls", "ca.pem") });
        // 实际五阶段结果必须全部通过，失败时仅显示安全诊断码。
        var stages = await adapter.ProbeAsync(Profile(), password, CancellationToken.None);
        Assert.HasCount(5, stages);
        Assert.IsTrue(stages.All(stage => stage.Status == "PASS"), JsonSerializer.Serialize(stages));
        // 重读必须重新检查源ACL，不能使用Probe缓存。
        var objects = await adapter.DiscoverAsync(Profile(), password, CancellationToken.None);
        Assert.HasCount(1, objects);
        Assert.AreEqual("fixture", objects[0].Schema);
        Assert.AreEqual("metadata_sample", objects[0].Name);
        Assert.AreEqual("TABLE", objects[0].Kind);
        CollectionAssert.AreEqual(new[] { "id", "label" }, objects[0].Fields.Select(field => field.Name).ToArray());
        CollectionAssert.AreEqual(new[] { 1, 2 }, objects[0].Fields.Select(field => field.Ordinal).ToArray());
    }

    /// <summary>错误秘密或错误CA均不能产出目录，异常不携带原始驱动细节。</summary>
    /// <param name="badCa">为真验证错误CA，否则验证错误凭据。</param>
    [TestMethod]
    [DataRow(false)]
    [DataRow(true)]
    public async Task BadAuthenticationAndCaCannotReadCatalog(bool badCa)
    {
        // fixture路径由受控运行器提供。
        var runtime = Runtime();
        // 错误凭据使用独立固定合成文本，不记录有效秘密。
        var password = badCa ? await File.ReadAllTextAsync(Path.Combine(runtime, "private", "reader.pass")) : "invalid-synthetic-password";
        // 错误CA仅作用于本次适配器，不改全局信任。
        var adapter = new DorisSourceAdapter(new DorisAdapterOptions { RootCertificatePath = Path.Combine(runtime, "tls", badCa ? "wrong-ca.pem" : "ca.pem") });
        // 只接受产品安全异常，不把其他测试错误当PASS。
        var error = await Assert.ThrowsAsync<PgSourceException>(() => adapter.DiscoverAsync(Profile(), password, CancellationToken.None));
        Assert.AreEqual(badCa ? "connection_tls_untrusted" : "connection_auth_failed", error.Code);
        Assert.IsNull(error.InnerException);
        Assert.AreEqual("Source operation failed.", error.Message);
    }

    /// <summary>实际握手使用相同CA但错误主机名时必须拒绝，不能只在配置校验层模拟。</summary>
    [TestMethod]
    public async Task WrongSanIsRejectedByActualHandshake()
    {
        // 固定任务证书只含localhost，不包含127.0.0.1地址SAN。
        var runtime = Runtime();
        // 正确密码确保拒绝来自证书身份检查。
        var secret = await File.ReadAllTextAsync(Path.Combine(runtime, "private", "reader.pass"));
        // 测试使用实际产品工厂及同一验证器，仅改变握手TargetHost。
        var adapter = new DorisSourceAdapter(new DorisAdapterOptions { RootCertificatePath = Path.Combine(runtime, "tls", "ca.pem") });
        // 不新增产品公开目标入口。
        var create = typeof(DorisSourceAdapter).GetMethod("Create", BindingFlags.Instance | BindingFlags.NonPublic)!;
        await using var connection = (MySqlConnection)create.Invoke(adapter, [secret])!;
        // 修改未开启连接，保留产品严格回调。
        var builder = new MySqlConnectionStringBuilder(connection.ConnectionString) { Server = "127.0.0.1" };
        connection.ConnectionString = builder.ConnectionString;
        // 必须具有TLS认证原因，不能把任意连接失败当成功。
        var error = await Assert.ThrowsAsync<MySqlException>(() => connection.OpenAsync());
        Assert.IsInstanceOfType<System.Security.Authentication.AuthenticationException>(error.InnerException);
    }

    /// <summary>源端新增写权限或撤销SELECT必须立即使后续发现失败，最后恢复原合成fixture。</summary>
    /// <param name="addWrite">为真增加写权限，否则撤销SELECT。</param>
    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public async Task PermissionChangesAreRechecked(bool addWrite)
    {
        // 私有fixture目录只由受控运行器提供。
        var runtime = Runtime();
        // 产品调用仅使用reader秘密。
        var password = await File.ReadAllTextAsync(Path.Combine(runtime, "private", "reader.pass"));
        // 仅fixture管理员改变当前合成账号权限，不用于产品查询或取消。
        var builder = new MySqlConnectionStringBuilder { Server = "localhost", Port = 19030, UserID = "root", Password = await File.ReadAllTextAsync(Path.Combine(runtime, "private", "root.pass")), SslMode = MySqlSslMode.VerifyFull, SslCa = Path.Combine(runtime, "tls", "ca.pem"), Pooling = false, ConnectionTimeout = 3, DefaultCommandTimeout = 3, CancellationTimeout = -1 };
        await using var admin = new MySqlConnection(builder.ConnectionString);
        await admin.OpenAsync();
        // 修改与恢复语句均为固定目标，不能从测试外输入SQL。
        var change = addWrite ? "GRANT LOAD_PRIV ON internal.fixture.* TO fixture_reader" : "REVOKE SELECT_PRIV ON internal.fixture.* FROM fixture_reader";
        // 即使断言失败也恢复原始只读授权。
        var restore = addWrite ? "REVOKE LOAD_PRIV ON internal.fixture.* FROM fixture_reader" : "GRANT SELECT_PRIV ON internal.fixture.* TO fixture_reader";
        try
        {
            // 只修改准确合成账号与fixture数据库。
            await using var command = new MySqlCommand(change, admin);
            await command.ExecuteNonQueryAsync();
            // 使用新的产品连接，验证不复用之前探测结果。
            var adapter = new DorisSourceAdapter(new DorisAdapterOptions { RootCertificatePath = Path.Combine(runtime, "tls", "ca.pem") });
            // 有效权限不匹配时，不能返回空目录冒充成功。
            var error = await Assert.ThrowsAsync<PgSourceException>(() => adapter.DiscoverAsync(Profile(), password, CancellationToken.None));
            Assert.AreEqual("connection_readonly_unverified", error.Code);
        }
        finally
        {
            // 恢复也是准确固定语句，任何恢复失败使测试失败。
            await using var command = new MySqlCommand(restore, admin);
            await command.ExecuteNonQueryAsync();
        }
        // 恢复后用实际产品路径确认fixture可供同一任务后续验证。
        var restored = new DorisSourceAdapter(new DorisAdapterOptions { RootCertificatePath = Path.Combine(runtime, "tls", "ca.pem") });
        Assert.HasCount(1, await restored.DiscoverAsync(Profile(), password, CancellationToken.None));
    }

    /// <summary>仅含原fixture只读授权的角色继承或额外跨库SELECT都必须被当前严格策略拒绝。</summary>
    /// <param name="inherited">为真创建无管理权限的合成角色，否则测试跨库SELECT。</param>
    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public async Task InheritedReadOnlyAndCrossDatabaseAreRejected(bool inherited)
    {
        // 只操作当前任务私有合成账号，绝不授予管理员权限。
        var runtime = Runtime();
        // 应用依旧只有reader凭据。
        var password = await File.ReadAllTextAsync(Path.Combine(runtime, "private", "reader.pass"));
        // fixture管理员只承担负例准备及恢复。
        var builder = new MySqlConnectionStringBuilder { Server = "localhost", Port = 19030, UserID = "root", Password = await File.ReadAllTextAsync(Path.Combine(runtime, "private", "root.pass")), SslMode = MySqlSslMode.VerifyFull, SslCa = Path.Combine(runtime, "tls", "ca.pem"), Pooling = false, ConnectionTimeout = 3, DefaultCommandTimeout = 3, CancellationTimeout = -1 };
        await using var admin = new MySqlConnection(builder.ConnectionString);
        await admin.OpenAsync();
        // 只有本次成功创建的角色才允许删除，已有同名角色会在CREATE处拒绝。
        var created = false;
        try
        {
            if (inherited)
            {
                await using var create = new MySqlCommand("CREATE ROLE doris_fixture_readonly_negative", admin);
                await create.ExecuteNonQueryAsync();
                created = true;
                await using var select = new MySqlCommand("GRANT SELECT_PRIV ON internal.fixture.* TO ROLE doris_fixture_readonly_negative", admin);
                await select.ExecuteNonQueryAsync();
            }
            // 两条固定语句不包含管理员权限；继承角色不扩大原fixture读取范围。
            await using var change = new MySqlCommand(inherited ? "GRANT 'doris_fixture_readonly_negative' TO fixture_reader" : "GRANT SELECT_PRIV ON internal.*.* TO fixture_reader", admin);
            await change.ExecuteNonQueryAsync();
            // 完整产品路径必须重新校验权限，不使用历史Probe。
            var adapter = new DorisSourceAdapter(new DorisAdapterOptions { RootCertificatePath = Path.Combine(runtime, "tls", "ca.pem") });
            Assert.AreEqual("connection_readonly_unverified", (await Assert.ThrowsAsync<PgSourceException>(() => adapter.DiscoverAsync(Profile(), password, CancellationToken.None))).Code);
        }
        finally
        {
            if (!inherited || created)
            {
                try
                {
                    await using var revoke = new MySqlCommand(inherited ? "REVOKE 'doris_fixture_readonly_negative' FROM fixture_reader" : "REVOKE SELECT_PRIV ON internal.*.* FROM fixture_reader", admin);
                    await revoke.ExecuteNonQueryAsync();
                }
                finally
                {
                    if (created)
                    {
                        await using var drop = new MySqlCommand("DROP ROLE doris_fixture_readonly_negative", admin);
                        await drop.ExecuteNonQueryAsync();
                    }
                }
            }
        }
        // 用实际元数据读取证明只读授权已恢复。
        var restored = new DorisSourceAdapter(new DorisAdapterOptions { RootCertificatePath = Path.Combine(runtime, "tls", "ca.pem") });
        Assert.HasCount(1, await restored.DiscoverAsync(Profile(), password, CancellationToken.None));
    }

    /// <summary>真实取消执行器必须在期限耗尽后仍清理源连接，管理员只承担见证。</summary>
    /// <param name="milliseconds">触发取消前的毫秒数。</param>
    /// <param name="rejectAuxiliary">故意使辅助认证失败并核对安全失败分类。</param>
    [TestMethod]
    [DataRow(250, false)]
    [DataRow(10000, false)]
    [DataRow(250, true)]
    public async Task CancellationClosesObservedSourceConnection(int milliseconds, bool rejectAuxiliary)
    {
        // 固定合成环境由调用器绑定。
        var runtime = Runtime();
        // 密码仅在进程内参与认证，不输出或断言正文。
        var password = await File.ReadAllTextAsync(Path.Combine(runtime, "private", "reader.pass"));
        // 实际产品取消执行器，不复制其算法作为测试替身。
        var adapter = new DorisSourceAdapter(new DorisAdapterOptions { RootCertificatePath = Path.Combine(runtime, "tls", "ca.pem") });
        // 反射仅让测试注入固定耗时查询，不对产品提供自由SQL入口。
        var create = typeof(DorisSourceAdapter).GetMethod("Create", BindingFlags.Instance | BindingFlags.NonPublic)!;
        await using var source = (MySqlConnection)create.Invoke(adapter, [password])!;
        await source.OpenAsync();
        // 源连接ID来自当前已认证连接。
        var sourceId = source.ServerThread;
        // root只执行PROCESSLIST观察，绝不用于取消。
        var observerBuilder = new MySqlConnectionStringBuilder(source.ConnectionString) { Password = await File.ReadAllTextAsync(Path.Combine(runtime, "private", "root.pass")), UserID = "root" };
        await using var observer = new MySqlConnection(observerBuilder.ConnectionString) { RemoteCertificateValidationCallback = source.RemoteCertificateValidationCallback };
        await observer.OpenAsync();
        // 等待源查询确实出现，再开始用户取消或十秒总期限模拟。
        using var cancellation = new CancellationTokenSource();
        // 反射目标为同一产品私有执行器，避免测试替身绕过真实清理。
        var execute = typeof(DorisSourceAdapter).GetMethod("ExecuteAsync", BindingFlags.Instance | BindingFlags.NonPublic)!.MakeGenericMethod(typeof(int));
        // 固定SLEEP只消耗时间，不读业务数据、不接收调用者SQL。
        Func<MySqlConnection, Task<int>> operation = async connection =>
        {
            // 禁用驱动命令超时，使断言确实覆盖产品总期限的独立清理。
            await using var command = new MySqlCommand("SELECT SLEEP(30)", connection) { CommandTimeout = 0 };
            await command.ExecuteScalarAsync();
            return 1;
        };
        // 错误辅助口令证明清理失败不能被误报为成功。
        var pending = (Task<int>)execute.Invoke(adapter, [source, rejectAuxiliary ? "invalid-synthetic-password" : password, operation, cancellation.Token])!;
        Assert.IsTrue(await ConnectionVisibleAsync(observer, sourceId, true), "Source query must be observed before cancellation.");
        cancellation.CancelAfter(milliseconds);
        // 捕获异常类型而不打印驱动原文或秘密。
        var cancelled = false;
        try { await pending.WaitAsync(TimeSpan.FromSeconds(15)); }
        catch (OperationCanceledException) when (!rejectAuxiliary) { cancelled = true; }
        catch (PgSourceException error) when (rejectAuxiliary && error.Code == "connection_source_unavailable") { cancelled = true; }
        Assert.IsTrue(cancelled);
        if (!rejectAuxiliary)
            Assert.IsFalse(await ConnectionVisibleAsync(observer, sourceId, false), "Source connection must disappear after successful cleanup.");
        else
        {
            // 产品已报告清理失败，不把客户端关闭冒充源端终止；测试以有效同reader连接收尾。
            await using var fixtureCleanup = (MySqlConnection)create.Invoke(adapter, [password])!;
            await fixtureCleanup.OpenAsync();
            if (await ConnectionVisibleAsync(observer, sourceId, false))
            {
                // 只删除本测试准确连接ID；root观察身份不承担清理。
                await using var kill = new MySqlCommand("KILL CONNECTION " + sourceId.ToString(System.Globalization.CultureInfo.InvariantCulture), fixtureCleanup);
                await kill.ExecuteNonQueryAsync();
            }
            Assert.IsFalse(await ConnectionVisibleAsync(observer, sourceId, false), "Fixture cleanup must remove its exact source connection.");
        }
    }

    /// <summary>只按准确连接ID观测，不读取或输出其他会话SQL。</summary>
    private static async Task<bool> ConnectionVisibleAsync(MySqlConnection observer, int sourceId, bool requireQuery)
    {
        // 单次观测窗口不超过两秒。
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(2));
        for (var attempt = 0; attempt < 20; attempt++)
        {
            // SHOW只在测试观察身份上执行，不进入产品路径。
            await using var command = new MySqlCommand("SHOW FULL PROCESSLIST", observer);
            await using var rows = await command.ExecuteReaderAsync(timeout.Token);
            while (await rows.ReadAsync(timeout.Token))
                if (Convert.ToInt32(rows["Id"]) == sourceId && (!requireQuery || Convert.ToString(rows["Info"])?.Contains("SLEEP(30)", StringComparison.Ordinal) == true)) return true;
            if (!requireQuery) return false;
            await rows.DisposeAsync();
            await Task.Delay(50, timeout.Token);
        }
        return false;
    }

    /// <summary>运行目录必须来自显式fixture绑定，缺失不跳过测试。</summary>
    private static string Runtime()
    {
        // 仅接收任务运行器设置的路径。
        var path = Environment.GetEnvironmentVariable("G4_DORIS_TEST_RUNTIME");
        Assert.IsNotNull(path, "Doris fixture is required.");
        Assert.IsTrue(Path.IsPathFullyQualified(path));
        return path;
    }

    /// <summary>测试只使用已批准本机合成目标。</summary>
    private static DorisConnectionProfile Profile() => new() { FeHost = "localhost", QueryPort = 19030, Catalog = "internal", Database = "fixture", Username = "fixture_reader", Tls = true };
}


/// <summary>仅在固定FE已由有界运行器换为过期合成证书时执行，不能混入正常fixture测试。</summary>
[TestClass]
[TestCategory("DorisExpiredCertificate")]
public sealed class DorisExpiredTlsTests
{
    /// <summary>真实FE端口过期证书必须被产品VerifyFull拒绝，不使用客户端时间替身。</summary>
    [TestMethod]
    public async Task ExpiredServerCertificateIsRejected()
    {
        // 独立入口明确提供本任务私有运行目录。
        var runtime = Environment.GetEnvironmentVariable("G4_DORIS_TEST_RUNTIME") ?? throw new InvalidOperationException("Doris fixture required.");
        // CA仍是正确CA，仅服务证书过期。
        var adapter = new DorisSourceAdapter(new DorisAdapterOptions { RootCertificatePath = Path.Combine(runtime, "tls", "ca.pem") });
        // 固定本机合成目标不变化。
        var profile = new DorisConnectionProfile { FeHost = "localhost", QueryPort = 19030, Catalog = "internal", Database = "fixture", Username = "fixture_reader", Tls = true };
        // 使用正确reader密码，防止认证失败冒充证书拒绝。
        var secret = await File.ReadAllTextAsync(Path.Combine(runtime, "private", "reader.pass"));
        Assert.AreEqual("connection_tls_untrusted", (await Assert.ThrowsAsync<PgSourceException>(() => adapter.DiscoverAsync(profile, secret, CancellationToken.None))).Code);
    }
}
