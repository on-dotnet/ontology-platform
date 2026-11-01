using System.Text.Json;
using Npgsql;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>仅在显式当前任务输入存在时对隔离合成PG执行TLS与真实ACL安全验收。</summary>
[TestClass]
public sealed class PgFixtureSecurityTests
{
    /// <summary>真实VerifyFull连接、只读五阶段及目录均成功，SELECT只验证权限且不读取业务行。</summary>
    /// <returns>隔离源检查任务。</returns>
    [TestMethod]
    [TestCategory("RealPgFixture")]
    public async Task VerifyFullAndAuthorizedSelectSucceed()
    {
        // 输入只从Master显式指定的当前任务文件读取，不搜索历史环境。
        var input = await ReadInputAsync();
        // 同一生产适配器实际核验链、主机名、角色与元数据。
        var adapter = new PgSourceAdapter(new PgAdapterOptions { RootCertificatePath = input.RootCertificate });
        // 密码只留在方法内存，不作为断言或日志输出。
        var stages = await adapter.ProbeAsync(Profile(), input.Secret, CancellationToken.None);
        Assert.AreEqual(5, stages.Length);
        Assert.IsTrue(stages.All(stage => stage.Status == "PASS"), string.Join(',', stages.Select(stage => stage.Name + ":" + stage.DiagnosticCode)));
        // 元数据读取只允许固定production，不返回其他Schema。
        var catalog = await adapter.DiscoverAsync(Profile(), input.Secret, CancellationToken.None);
        Assert.IsTrue(catalog.Length > 0 && catalog.All(item => item.Schema == "production"));
        // Npgsql自身也必须执行VerifyFull，不以适配器独立握手代替认证连接。
        await using var connection = Connection(input);
        await connection.OpenAsync();
        // 恒假条件不会读取任何业务样本行，但必须具有该表的真实SELECT权限。
        await using var command = new NpgsqlCommand("SELECT id FROM production.heat_event WHERE false", connection);
        await using var reader = await command.ExecuteReaderAsync();
        Assert.IsFalse(await reader.ReadAsync());
    }

    /// <summary>不受信根在认证之前拒绝，后续权限与目录保持未运行。</summary>
    /// <returns>真实TLS拒绝任务。</returns>
    [TestMethod]
    [TestCategory("RealPgFixture")]
    public async Task UntrustedRootIsRejectedBeforeAuthentication()
    {
        // 仅替换当前任务生成的错误CA，不访问系统证书或外部信任。
        var input = await ReadInputAsync();
        // 正确固定主机仍必须因根不受信而失败关闭。
        var adapter = new PgSourceAdapter(new PgAdapterOptions { RootCertificatePath = input.WrongRootCertificate });
        // 生产适配器只输出安全诊断，不保留原始TLS异常。
        var stages = await adapter.ProbeAsync(Profile(), input.Secret, CancellationToken.None);
        Assert.AreEqual("PASS", stages[0].Status);
        Assert.AreEqual("FAIL", stages[1].Status);
        Assert.AreEqual("connection_tls_untrusted", stages[1].DiagnosticCode);
        Assert.IsTrue(stages.Skip(2).All(stage => stage.Status == "NOT_RUN"));
    }

    /// <summary>错误密码不能因为TLS连通被当作成功，源权限与目录不得开始。</summary>
    /// <returns>真实身份拒绝任务。</returns>
    [TestMethod]
    [TestCategory("RealPgFixture")]
    public async Task WrongPasswordIsRejectedAfterVerifiedTls()
    {
        // 正确CA与真实源使失败阶段能够明确归属于认证。
        var input = await ReadInputAsync();
        // 使用真实Adapter，错误密码仅为当前内存合成值。
        var adapter = new PgSourceAdapter(new PgAdapterOptions { RootCertificatePath = input.RootCertificate });
        // 追加字符确保与同次生成的真实合成密码不同，不输出任一值。
        var stages = await adapter.ProbeAsync(Profile(), input.Secret + "-invalid", CancellationToken.None);
        Assert.AreEqual("PASS", stages[0].Status);
        Assert.AreEqual("PASS", stages[1].Status);
        Assert.AreEqual("connection_auth_failed", stages[2].DiagnosticCode);
        Assert.IsTrue(stages.Skip(3).All(stage => stage.Status == "NOT_RUN"));
    }

    /// <summary>源端ACL实际拒绝DML、DDL、临时表及跨Schema；每项在独立事务内并始终回滚。</summary>
    /// <param name="operation">固定合成库操作标识，不接收用户SQL。</param>
    /// <returns>真实权限拒绝任务。</returns>
    [TestMethod]
    [TestCategory("RealPgFixture")]
    [DataRow("insert")]
    [DataRow("update")]
    [DataRow("delete")]
    [DataRow("create-table")]
    [DataRow("create-schema")]
    [DataRow("temporary")]
    [DataRow("maintenance")]
    [DataRow("otherplant")]
    public async Task SourceAclRejectsEveryUnapprovedOperation(string operation)
    {
        // 只有标记为本任务且固定pg-source/fixture/fixture_reader的输入才能执行。
        var input = await ReadInputAsync();
        // 独立连接保证前一拒绝不会让本项误因事务已中止而通过。
        await using var connection = Connection(input);
        await connection.OpenAsync();
        // 所有意外成功均只发生在此事务，finally回滚保证不留下合成测试副作用。
        await using var transaction = await connection.BeginTransactionAsync();
        try
        {
            // 主动取消默认只读会话模式，必须证明真实ACL拒绝，不能用25006替代42501。
            await using var mode = new NpgsqlCommand("SET TRANSACTION READ WRITE", connection, transaction);
            await mode.ExecuteNonQueryAsync();
            // 固定SQL全部只涉及当前无业务行的合成数据库。
            var sql = operation switch
            {
                "insert" => "INSERT INTO production.heat_event(id) VALUES (1)",
                "update" => "UPDATE production.heat_event SET tap_temp = 1 WHERE false",
                "delete" => "DELETE FROM production.heat_event WHERE false",
                "create-table" => "CREATE TABLE production.denied_fixture(id integer)",
                "create-schema" => "CREATE SCHEMA denied_fixture",
                "temporary" => "CREATE TEMP TABLE denied_fixture(id integer)",
                "maintenance" => "SELECT id FROM maintenance.private_event WHERE false",
                "otherplant" => "SELECT id FROM otherplant.private_event WHERE false",
                _ => throw new InvalidOperationException("Unknown fixed synthetic operation.")
            };
            // 不把Npgsql异常正文或SQL记录进断言，仅读取受控SQLSTATE。
            await using var command = new NpgsqlCommand(sql, connection, transaction);
            // 捕获到的错误必须明确为ACL权限不足；连接或语法错误均不能冒充通过。
            string? sqlState = null;
            try
            {
                await command.ExecuteNonQueryAsync();
            }
            catch (PostgresException failure)
            {
                sqlState = failure.SqlState;
            }
            Assert.AreEqual(PostgresErrorCodes.InsufficientPrivilege, sqlState, "必须由源端ACL拒绝固定合成操作。");
        }
        finally
        {
            await transaction.RollbackAsync();
        }
    }

    /// <summary>仅在Master另行启动错误SAN服务后运行，正常夹具不能假称主机名负例已测。</summary>
    /// <returns>错误服务证书的真实拒绝任务。</returns>
    [TestMethod]
    [TestCategory("RealPgWrongSanFixture")]
    public async Task WrongServerNameIsRejectedBeforeAuthentication()
    {
        if (Environment.GetEnvironmentVariable("G4_PG_WRONG_SAN_FIXTURE") != "G4-M1-RECOVERY-001")
            Assert.Inconclusive("NOT_RUN: requires explicit current-task wrong-SAN server configuration.");
        // 使用正确CA，唯一预期差异是服务器已换成本任务错误SAN叶证书。
        var input = await ReadInputAsync();
        // 生产适配器不能接受与固定pg-source不匹配的证书身份。
        var adapter = new PgSourceAdapter(new PgAdapterOptions { RootCertificatePath = input.RootCertificate });
        // 认证前必须已经失败，不能静默退回非验证TLS模式。
        var stages = await adapter.ProbeAsync(Profile(), input.Secret, CancellationToken.None);
        Assert.AreEqual("PASS", stages[0].Status);
        Assert.AreEqual("FAIL", stages[1].Status);
        Assert.AreEqual("connection_tls_untrusted", stages[1].DiagnosticCode);
        Assert.IsTrue(stages.Skip(2).All(stage => stage.Status == "NOT_RUN"));
    }

    /// <summary>只读取显式当前任务文件并验证固定容器内挂载路径。</summary>
    /// <returns>仅在当前进程内存保留的合成输入。</returns>
    private static async Task<FixtureInput> ReadInputAsync()
    {
        // 缺环境输入必须明确NOT_RUN，绝不探测或复用历史私有环境。
        var path = Environment.GetEnvironmentVariable("G4_PG_ADAPTER_TEST_INPUT");
        if (string.IsNullOrWhiteSpace(path))
            Assert.Inconclusive("NOT_RUN: requires explicit current-task isolated PostgreSQL input.");
        // 不输出原文件内容；身份标记阻止误用旧任务配置。
        using var document = JsonDocument.Parse(await File.ReadAllTextAsync(path));
        // 预期挂载位置来自冻结夹具，而非任意宿主私有文件路径。
        var root = document.RootElement;
        Assert.AreEqual("G4-M1-RECOVERY-001", root.GetProperty("fixtureIdentity").GetString());
        Assert.AreEqual("/run/secrets/reader-password", root.GetProperty("secretFile").GetString());
        Assert.AreEqual("/run/secrets/ca.crt", root.GetProperty("rootCertificatePath").GetString());
        Assert.AreEqual("/run/secrets/wrong-ca.crt", root.GetProperty("wrongRootCertificatePath").GetString());
        return new FixtureInput(await File.ReadAllTextAsync("/run/secrets/reader-password"), "/run/secrets/ca.crt", "/run/secrets/wrong-ca.crt");
    }

    /// <summary>构造与生产Adapter一致的固定目标VerifyFull连接，不允许任意SQL目标或池复用。</summary>
    /// <param name="input">当前任务内存中的信任与凭据。</param>
    /// <returns>尚未打开的隔离源连接。</returns>
    private static NpgsqlConnection Connection(FixtureInput input)
    {
        // 固定安全参数，诊断不包含秘密与原始源错误细节。
        var builder = new NpgsqlConnectionStringBuilder
        {
            Host = "pg-source", Port = 5432, Database = "fixture", Username = "fixture_reader", Password = input.Secret,
            SslMode = SslMode.VerifyFull, RootCertificate = input.RootCertificate, Pooling = false,
            Timeout = 3, CommandTimeout = 3, IncludeErrorDetail = false, LogParameters = false,
            GssEncryptionMode = GssEncryptionMode.Disable, SearchPath = "pg_catalog"
        };
        return new NpgsqlConnection(builder.ConnectionString);
    }

    /// <summary>唯一固定类型化源配置，不接受外部主机、管理员或Schema。</summary>
    /// <returns>当前任务批准的只读PG配置。</returns>
    private static PgConnectionProfile Profile() => new()
    {
        Host = "pg-source", Port = 5432, Database = "fixture", Username = "fixture_reader",
        SslMode = "VerifyFull", AllowedSchemas = ["production"]
    };

    /// <summary>合成输入只在内存保存，不参与自动记录或公开响应。</summary>
    /// <param name="Secret">当前任务读取角色密码。</param>
    /// <param name="RootCertificate">正确的固定CA挂载。</param>
    /// <param name="WrongRootCertificate">用于失败关闭验证的独立CA挂载。</param>
    private sealed record FixtureInput(string Secret, string RootCertificate, string WrongRootCertificate);
}
