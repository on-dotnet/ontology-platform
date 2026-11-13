using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>Doris目标策略和凭据隔离的无网络合同。</summary>
[TestClass]
public sealed class DorisAdapterTests
{
    /// <summary>同一持久Doris配置对审计角色脱敏，对操作员保留非秘密配置。</summary>
    [TestMethod]
    public async Task AuditorProjectionRedactsDorisTargetWithoutMutatingOperatorView()
    {
        // 无探针草稿只执行真实投影，不需要数据库访问。
        var service = new ConnectionApplicationService(null!, null!, null!, null!, null!, TimeProvider.System);
        // 直接调用读接口共用的投影，避免重复实现被测规则。
        var method = typeof(ConnectionApplicationService).GetMethod("ViewAsync", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!;
        // 固定合成配置用于验证字段不会通过审计视图泄漏。
        var config = new DorisConnectionConfig { Profile = new DorisConnectionProfile { FeHost = "localhost", QueryPort = 19030, Catalog = "internal", Database = "fixture", Username = "fixture_reader", Tls = true } };
        // 记录保留完整配置，投影不能修改持久值。
        var row = new ConnectionRecord { ConfigJson = System.Text.Json.JsonSerializer.Serialize<ConnectionConfig>(config, G4ConnectionJson.Options) };
        // 审计角色没有operator权限。
        var auditor = new ActorContext { Roles = ["platform.auditor"] };
        // 审计视图应隐藏目标和账户名称。
        var hidden = await (Task<ConnectionView>)method.Invoke(service, [null, auditor, row, CancellationToken.None])!;
        Assert.AreEqual(config.Profile with { FeHost = "redacted", Catalog = "redacted", Database = "redacted", Username = "redacted" }, ((DorisConnectionConfig)hidden.Config).Profile);
        // 同一原始记录仍能投影操作员所需的非秘密配置。
        var visible = await (Task<ConnectionView>)method.Invoke(service, [null, auditor with { Roles = ["platform.operator"] }, row, CancellationToken.None])!;
        Assert.AreEqual(config, visible.Config);
    }

    /// <summary>每一目标字段和完整scope都必须匹配服务端授权。</summary>
    [TestMethod]
    public void TargetAndScopeCannotBeExpanded()
    {
        // 固定合成目标，没有密码。
        var profile = new DorisConnectionProfile { FeHost = "localhost", QueryPort = 19030, Catalog = "internal", Database = "fixture", Username = "fixture_reader", Tls = true };
        // 当前任务批准的组织与厂区。
        var scope = new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a"] };
        DorisAdapterOptions.Validate(profile, scope);
        foreach (var changed in new[] { profile with { FeHost = "127.0.0.1" }, profile with { QueryPort = 9030 }, profile with { Catalog = "external" }, profile with { Database = "mysql" }, profile with { Username = "root" }, profile with { Tls = false } })
            Assert.Throws<SemanticOperationException>(() => DorisAdapterOptions.Validate(changed, scope));
        Assert.Throws<SemanticOperationException>(() => DorisAdapterOptions.Validate(profile, scope with { OrganizationId = "other" }));
        Assert.Throws<SemanticOperationException>(() => DorisAdapterOptions.Validate(profile, scope with { SiteIds = ["site-a", "site-b"] }));
    }

    /// <summary>三种凭据用途两两隔离，不以协议兼容借用PG密码。</summary>
    [TestMethod]
    public void DorisPurposeIsIndependent()
    {
        // 公开配置不包含秘密，只测试用途选择。
        var config = new DorisConnectionConfig { Profile = new DorisConnectionProfile { FeHost = "localhost", QueryPort = 19030, Catalog = "internal", Database = "fixture", Username = "fixture_reader", Tls = true } };
        Assert.AreEqual("DORIS_READONLY", ConnectionSourceDispatcher.SecretPurpose(config));
        foreach (var wrong in new[] { "POSTGRESQL_READONLY", "WEB_API_KEY" })
            Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.DemandPurpose(config, wrong));
    }

    /// <summary>取消信号与底层失败并发时，未知失败及清理失败不能被覆盖为取消成功。</summary>
    [TestMethod]
    public void ConcurrentCancellationDoesNotHideSourceFailure()
    {
        // 测试固定错误分类边界，不引入产品公开诊断入口。
        var classify = typeof(DorisSourceAdapter).GetMethod("SafeCode", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
        Assert.AreEqual("connection_source_unavailable", classify.Invoke(null, [new IOException("synthetic"), true]));
        Assert.AreEqual("connection_source_unavailable", classify.Invoke(null, [new PgSourceException("connection_source_unavailable"), true]));
        Assert.AreEqual("connection_cancelled", classify.Invoke(null, [new OperationCanceledException(), true]));
        Assert.AreEqual("connection_source_unavailable", classify.Invoke(null, [new OperationCanceledException(), false]));
    }

    /// <summary>真实适配器不能因公开合同可解析就访问未批准目标。</summary>
    [TestMethod]
    public async Task AdapterRejectsTargetBeforeOpeningConnection()
    {
        // 不存在的证书路径不应先于目标错误被读取。
        var adapter = new DorisSourceAdapter(new DorisAdapterOptions { RootCertificatePath = "/not-used/ca.pem" });
        // 拒绝根账号，不能用其通过只读检查。
        var profile = new DorisConnectionProfile { FeHost = "localhost", QueryPort = 19030, Catalog = "internal", Database = "fixture", Username = "root", Tls = true };
        await Assert.ThrowsAsync<SemanticOperationException>(() => adapter.DiscoverAsync(profile, "synthetic", CancellationToken.None));
    }

    /// <summary>直接驱动产品流式解析器验证对象、字段和字节边界，超限不得截断成功。</summary>
    [TestMethod]
    public async Task CatalogBudgetsRejectInsteadOfTruncating()
    {
        // 调用真实解析器；测试不复制预算算法。
        var parse = typeof(DorisSourceAdapter).GetMethod("ReadCatalogRowsAsync", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
        foreach (var scenario in new[] { (Objects: 100, Fields: 20, Fail: false), (Objects: 101, Fields: 1, Fail: true), (Objects: 1, Fields: 2001, Fail: true) })
        {
            // 八列保持实际固定SQL顺序；无需创建大型服务数据。
            var data = MetadataTable();
            for (var table = 0; table < scenario.Objects; table++)
                for (var field = 0; field < scenario.Fields; field++) data.Rows.Add("t" + table, "BASE TABLE", "f" + field, "int(11)", "YES", field + 1, DBNull.Value, DBNull.Value);
            using var reader = data.CreateDataReader();
            // 真实异步结果要么完整成功，要么安全预算异常。
            var pending = (Task<CatalogObject[]>)parse.Invoke(null, [reader])!;
            if (scenario.Fail) Assert.AreEqual("catalog_budget_exceeded", (await Assert.ThrowsAsync<PgSourceException>(() => pending)).Code);
            else Assert.HasCount(100, await pending);
        }
        // 以公开序列化合同计算恰好2MiB的字段名，使最终对象开销也被覆盖。
        var baseline = new[] { new CatalogObject { Schema = "fixture", Name = "t", Kind = "TABLE", Fields = [new CatalogField { Name = "", NativeType = "int(11)", Nullable = true, Ordinal = 1, Precision = null, Scale = null }] } };
        // ASCII字符每个恰好一个JSON字节，不受转义变化干扰。
        var capacity = 2 * 1024 * 1024 - System.Text.Json.JsonSerializer.SerializeToUtf8Bytes(baseline).Length;
        foreach (var extra in new[] { 0, 1 })
        {
            // 精确上限成功，上限加一拒绝，二者均走实际解析器。
            var data = MetadataTable();
            data.Rows.Add("t", "BASE TABLE", new string('a', capacity + extra), "int(11)", "YES", 1, DBNull.Value, DBNull.Value);
            using var reader = data.CreateDataReader();
            // 保留实际任务，确保不是仅测一个常量判断。
            var pending = (Task<CatalogObject[]>)parse.Invoke(null, [reader])!;
            if (extra == 1) Assert.AreEqual("catalog_budget_exceeded", (await Assert.ThrowsAsync<PgSourceException>(() => pending)).Code);
            else Assert.AreEqual(2 * 1024 * 1024, System.Text.Json.JsonSerializer.SerializeToUtf8Bytes(await pending).Length);
        }
    }

    /// <summary>实际权限解析拒绝管理员、继承和未知列，连接构造始终强制TLS并携严格验证回调。</summary>
    [TestMethod]
    public void GrantShapeAndTlsRemainFailClosed()
    {
        // 固定真实4.0.8格式，只供纯解析负例，不更改任何账号授权。
        var values = new Dictionary<string, string>
        {
            ["UserIdentity"] = "'fixture_reader'@'%'",
            ["Password"] = "Yes",
            ["Comment"] = "",
            ["RequireSan"] = "",
            ["Roles"] = "",
            ["GlobalPrivs"] = "",
            ["CatalogPrivs"] = "",
            ["DatabasePrivs"] = "internal.fixture: Select_priv; internal.information_schema: Select_priv; internal.mysql: Select_priv",
            ["TablePrivs"] = "",
            ["ColPrivs"] = "",
            ["ResourcePrivs"] = "",
            ["CloudClusterPrivs"] = "",
            ["CloudStagePrivs"] = "",
            ["StorageVaultPrivs"] = "",
            ["WorkloadGroupPrivs"] = "normal: Usage_priv",
            ["ComputeGroupPrivs"] = ""
        };
        // 直接调用产品解析方法，不能用测试自写权限判断替代。
        var validate = typeof(DorisSourceAdapter).GetMethod("ValidateGrantRow", System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
        foreach (var scenario in new[] { "baseline", "GlobalPrivs", "Roles", "UnknownPrivs" })
        {
            // 每个反例独立，防止上一个变更污染基线。
            var fields = new Dictionary<string, string>(values);
            if (scenario != "baseline") fields[scenario] = "Admin_priv";
            // 读取器与驱动返回相同列名和值的语义。
            var data = new System.Data.DataTable();
            foreach (var name in fields.Keys) data.Columns.Add(name, typeof(string));
            data.Rows.Add(fields.Values.Cast<object>().ToArray());
            using var reader = data.CreateDataReader();
            Assert.IsTrue(reader.Read());
            if (scenario == "baseline") validate.Invoke(null, [reader]);
            else Assert.AreEqual("connection_readonly_unverified", (Assert.Throws<System.Reflection.TargetInvocationException>(() => validate.Invoke(null, [reader])).InnerException as PgSourceException)?.Code);
        }
        // 仅检查未打开的产品连接，合成字符串不是有效凭据。
        var adapter = new DorisSourceAdapter(new DorisAdapterOptions { RootCertificatePath = "/synthetic/ca.pem" });
        // 工厂没有TLS可选分支或自动降级重试。
        var create = typeof(DorisSourceAdapter).GetMethod("Create", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.NonPublic)!;
        using var connection = (MySqlConnector.MySqlConnection)create.Invoke(adapter, ["synthetic"])!;
        // 用驱动解析实际产品连接串，不在断言中输出连接串。
        var builder = new MySqlConnector.MySqlConnectionStringBuilder(connection.ConnectionString);
        Assert.AreEqual(MySqlConnector.MySqlSslMode.Required, builder.SslMode);
        Assert.IsNotNull(connection.RemoteCertificateValidationCallback);
        Assert.AreEqual(string.Empty, builder.SslCa);
        Assert.IsFalse(builder.Pooling);
        Assert.IsFalse(builder.AllowLoadLocalInfile);
    }

    /// <summary>生成固定SQL列形态，不执行任何源SQL或读取业务数据。</summary>
    /// <returns>仅含元数据列定义的空表。</returns>
    private static System.Data.DataTable MetadataTable()
    {
        // 混合值类型对应源读取器GetString/GetValue约定。
        var table = new System.Data.DataTable();
        for (var index = 0; index < 8; index++) table.Columns.Add("c" + index, index < 5 ? typeof(string) : typeof(int));
        return table;
    }
}
