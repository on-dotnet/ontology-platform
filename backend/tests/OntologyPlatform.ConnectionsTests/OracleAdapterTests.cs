using System.Data;
using System.Reflection;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>Oracle真实元数据解析和固定目标合同；不冒充源端运行验收。</summary>
[TestClass]
public sealed class OracleAdapterTests
{
    /// <summary>Oracle指纹独立标记适配器版本，既有连接器保持原目录字节规则。</summary>
    [TestMethod]
    public void CatalogFingerprintSeparatesOracleWithoutChangingExistingConnectors()
    {
        // 固定空目录仅检查规范化算法，不作为真实发现结果。
        var method = typeof(ConnectionApplicationService).GetMethod("CanonicalCatalog", BindingFlags.Static | BindingFlags.NonPublic)!;
        // 目标值不参与此纯指纹计算。
        var profile = new OracleConnectionProfile { Host = "oracle-source", Port = 2484, ServiceName = "FREEPDB1", Username = "FIXTURE_READER", Tls = true, AllowedOwners = ["PRODUCTION", "CaseOwner"] };
        // Oracle应使用独立版本，不继承PG的标记。
        var result = ((CatalogObject[], string))method.Invoke(null, [Array.Empty<CatalogObject>(), new OracleConnectionConfig { Profile = profile }])!;
        Assert.AreEqual(Digest("{\"adapterVersion\":\"oracle-m2-v1\",\"objects\":[]}"), result.Item2);
        // Doris历史版本标记保持不变，不能随新增Oracle一起重写。
        var doris = new DorisConnectionConfig { Profile = new DorisConnectionProfile { FeHost = "localhost", QueryPort = 19030, Catalog = "internal", Database = "fixture", Username = "fixture_reader", Tls = true } };
        result = ((CatalogObject[], string))method.Invoke(null, [Array.Empty<CatalogObject>(), doris])!;
        Assert.AreEqual(Digest("{\"adapterVersion\":\"pg-m1-v1\",\"objects\":[]}"), result.Item2);
    }

    /// <summary>对固定黄金字节计算摘要，不复制产品规范化逻辑。</summary>
    private static string Digest(string value) => Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(value)));

    /// <summary>实际流读取超过预算或读取中失效时只返回固定信任错误。</summary>
    [TestMethod]
    public void TrustReadIsBoundedAndNormalizesIoFailure()
    {
        // 测试真实读取边界，避免FileInfo检查后文件增长绕过上限。
        var method = typeof(OracleSourceAdapter).GetMethod("ReadTrustBytes", BindingFlags.NonPublic | BindingFlags.Static);
        Assert.IsNotNull(method);
        // 超限正文必须在边界拒绝，不能全部读入。
        using var oversized = new MemoryStream(new byte[1024 * 1024 + 1]);
        // 关闭的流模拟打开后读取失败，不依赖竞态时序。
        var unavailable = new MemoryStream([1]);
        unavailable.Dispose();
        foreach (var stream in new Stream[] { oversized, unavailable })
        {
            // 私有边界异常由反射包装，检查实际业务错误而非包装异常。
            var error = Assert.Throws<TargetInvocationException>(() => method.Invoke(null, [stream]));
            Assert.IsInstanceOfType<PgSourceException>(error.InnerException);
            Assert.AreEqual("connection_tls_untrusted", ((PgSourceException)error.InnerException!).Code);
        }
    }

    /// <summary>独立大小写owner及逐项目标、scope变化均受服务端固定规则约束。</summary>
    [TestMethod]
    public void FixedTargetRejectsDescriptorAndScopeChanges()
    {
        // 固定开发目标只用于纯校验，无网络调用。
        var profile = new OracleConnectionProfile { Host = "oracle-source", Port = 2484, ServiceName = "FREEPDB1", Username = "FIXTURE_READER", Tls = true, AllowedOwners = ["PRODUCTION", "CaseOwner"] };
        // 唯一批准的合成范围。
        var scope = new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a"] };
        OracleAdapterOptions.Validate(profile, scope);
        foreach (var changed in new[] { profile with { Host = "(DESCRIPTION=x)" }, profile with { ServiceName = "FREE" }, profile with { Port = 1521 }, profile with { Username = "SYS" }, profile with { Tls = false }, profile with { AllowedOwners = ["PRODUCTION", "CASEOWNER"] } })
            Assert.Throws<SemanticOperationException>(() => OracleAdapterOptions.Validate(changed, scope));
        Assert.Throws<SemanticOperationException>(() => OracleAdapterOptions.Validate(profile, scope with { SiteIds = ["site-a", "site-b"] }));
    }

    /// <summary>实际驱动连接禁用池和pipelining，密码不能注入目标描述符。</summary>
    [TestMethod]
    public void ActualConnectionUsesFixedTcpsAndIndependentWallet()
    {
        // 构造仅检查连接参数，不打开网络或读取不存在的信任文件。
        var type = typeof(IOracleSourceAdapter).Assembly.GetType("OntologyPlatform.Modules.Connections.OracleSourceAdapter")!;
        // 宿主固定的路径不能来自公开DTO。
        var options = new OracleAdapterOptions { WalletDirectory = "/synthetic/wallet", RootCertificatePath = "/synthetic/ca.pem" };
        // 调用真实构造器和连接工厂，避免测试另造连接串。
        var adapter = Activator.CreateInstance(type, options)!;
        // 固定私有工厂只接收秘密，目标无法由其参数改变。
        var create = type.GetMethod("Create", BindingFlags.Instance | BindingFlags.NonPublic)!;
        using var connection = (Oracle.ManagedDataAccess.Client.OracleConnection)create.Invoke(adapter, ["p;Data Source=attacker"] )!;
        // 让官方builder再次解析，检查分号仍属于密码。
        var parsed = new Oracle.ManagedDataAccess.Client.OracleConnectionStringBuilder(connection.ConnectionString);
        Assert.IsFalse(parsed.Pooling);
        Assert.IsFalse(connection.Pipelining);
        Assert.AreEqual("p;Data Source=attacker", parsed.Password);
        StringAssert.Contains(parsed.DataSource, "(PROTOCOL=TCPS)");
        StringAssert.Contains(parsed.DataSource, "(HOST=oracle-source)");
        StringAssert.Contains(parsed.DataSource, "(SERVICE_NAME=FREEPDB1)");
        Assert.AreEqual("/synthetic/wallet", connection.WalletLocation);
        Assert.IsTrue(connection.SSLServerDNMatch);
    }

    /// <summary>数据字典的原名、未声明精度、负scale及日期时区语义不可被猜测替换。</summary>
    [TestMethod]
    public async Task DictionaryTypesPreserveUnknownPrecisionAndOracleSemantics()
    {
        // 行列形状与固定字典SQL完全一致，避免测试另写解析器。
        var data = Table();
        data.Rows.Add("CaseOwner", "Quoted", "TABLE", "N", "NUMBER", "Y", 1, DBNull.Value, -2, 22, DBNull.Value, DBNull.Value, DBNull.Value);
        data.Rows.Add("CaseOwner", "Quoted", "TABLE", "At", "DATE", "N", 2, DBNull.Value, DBNull.Value, 7, DBNull.Value, DBNull.Value, DBNull.Value);
        data.Rows.Add("CaseOwner", "Quoted", "TABLE", "T", "TIMESTAMP(9) WITH LOCAL TIME ZONE", "Y", 3, DBNull.Value, 9, 11, DBNull.Value, DBNull.Value, DBNull.Value);
        data.Rows.Add("CaseOwner", "Quoted", "TABLE", "Text", "NVARCHAR2", "Y", 4, DBNull.Value, DBNull.Value, 48, 24, "C", DBNull.Value);
        data.Rows.Add("CaseOwner", "Quoted", "TABLE", "Large", "CLOB", "Y", 5, DBNull.Value, DBNull.Value, 4000, DBNull.Value, DBNull.Value, DBNull.Value);
        // 产品解析器消费真实DbDataReader，不触发服务。
        using var reader = data.CreateDataReader();
        // 实际反射调用仅避免为测试开放内部解析API。
        var result = await Parse(reader, CancellationToken.None);
        Assert.AreEqual("CaseOwner", result.Single().Schema);
        Assert.IsNull(result[0].Fields[0].Precision);
        Assert.AreEqual(-2, result[0].Fields[0].Scale);
        Assert.AreEqual("DATE", result[0].Fields[1].NativeType);
        Assert.AreEqual("WITH_LOCAL_TIME_ZONE", result[0].Fields[2].OracleMetadata!.TimeZoneKind);
        Assert.AreEqual(9, result[0].Fields[2].OracleMetadata!.FractionalSecondsPrecision);
        Assert.AreEqual("CHAR", result[0].Fields[3].OracleMetadata!.CharSemantics);
        Assert.AreEqual(48, result[0].Fields[3].OracleMetadata!.ByteLength);
        Assert.AreEqual(24, result[0].Fields[3].OracleMetadata!.CharLength);
        Assert.AreEqual("METADATA_ONLY", result[0].Fields[4].OracleMetadata!.SupportStatus);
    }

    /// <summary>超对象/列预算、未知类型、空目录和已取消调用不能发布可信快照。</summary>
    [TestMethod]
    public async Task IncompleteUnknownAndOversizedCatalogsFailClosed()
    {
        foreach (var scenario in new[] { (Objects: 101, Fields: 1, Type: "NUMBER"), (Objects: 1, Fields: 2001, Type: "NUMBER"), (Objects: 1, Fields: 1, Type: "MYSTERY"), (Objects: 0, Fields: 0, Type: "NUMBER") })
        {
            // 合成字典行只表达元数据，不存业务数据。
            var data = Table();
            for (var table = 0; table < scenario.Objects; table++)
                for (var column = 0; column < scenario.Fields; column++)
                    data.Rows.Add("PRODUCTION", "T" + table, "TABLE", "C" + column, scenario.Type, "Y", column + 1, DBNull.Value, DBNull.Value, 22, DBNull.Value, DBNull.Value, DBNull.Value);
            using var reader = data.CreateDataReader();
            await Assert.ThrowsAsync<PgSourceException>(() => Parse(reader, CancellationToken.None));
        }
        // 真实令牌在开始读取前即取消，应直接传播取消。
        using var cancelled = new CancellationTokenSource();
        cancelled.Cancel();
        using var empty = Table().CreateDataReader();
        await Assert.ThrowsAsync<OperationCanceledException>(() => Parse(empty, cancelled.Token));
    }

    /// <summary>调用实际产品解析器，缺实现时测试明确失败。</summary>
    private static Task<CatalogObject[]> Parse(System.Data.Common.DbDataReader reader, CancellationToken token)
    {
        // 查真实模块类型，不在测试内实现替代路径。
        var type = typeof(IOracleSourceAdapter).Assembly.GetType("OntologyPlatform.Modules.Connections.OracleSourceAdapter");
        Assert.IsNotNull(type, "Oracle真实适配器必须存在。");
        // 冻结输入为实际reader与取消令牌。
        var method = type.GetMethod("ReadCatalogRowsAsync", BindingFlags.Static | BindingFlags.NonPublic)!;
        return (Task<CatalogObject[]>)method.Invoke(null, [reader, token])!;
    }

    /// <summary>生成与固定Oracle数据字典查询同序的十三列。</summary>
    private static DataTable Table()
    {
        // 允许DBNull和Oracle数值包装，以验证Convert而非强制Int32假设。
        var table = new DataTable();
        foreach (var name in new[] { "owner", "table", "kind", "column", "type", "nullable", "ordinal", "precision", "scale", "bytes", "chars", "charUsed", "typeOwner" })
            table.Columns.Add(name, typeof(object));
        return table;
    }
}
