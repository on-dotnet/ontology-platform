using System.Text;
using System.Text.Json;
using System.Security.Cryptography;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>PG精确值与拒绝隐式转换；完整真实源由任务集成测试覆盖。</summary>
[TestClass]
public sealed class G4MappingSourceTests
{
    /// <summary>decimal保持精确字符串、整数不经过JavaScript或double。</summary>
    [TestMethod]
    public void ExactScalarsRetainPrecisionAndNull()
    {
        Assert.AreEqual("12345678901234567890.12345678", PgMappingSourceValidator.Scalar(12345678901234567890.12345678m, Field("numeric(28,8)", 28, 8)));
        Assert.AreEqual("9223372036854775807", PgMappingSourceValidator.Scalar(long.MaxValue, Field("bigint")));
        Assert.AreEqual("0", PgMappingSourceValidator.Scalar(-0m, Field("numeric(10,2)", 10, 2)));
        Assert.AreEqual("true", PgMappingSourceValidator.Scalar(true, Field("boolean")));
        Assert.IsNull(PgMappingSourceValidator.Scalar(DBNull.Value, Field("text")));
    }

    /// <summary>浮点、无界numeric及类型错配不能被容错转成有效映射。</summary>
    [TestMethod]
    public void UnsupportedOrMismatchedScalarTypesAreRejected()
    {
        Assert.Throws<SemanticOperationException>(() => PgMappingSourceValidator.Scalar(1.1d, Field("double precision")));
        Assert.Throws<SemanticOperationException>(() => PgMappingSourceValidator.Scalar(1m, Field("numeric")));
        Assert.Throws<SemanticOperationException>(() => PgMappingSourceValidator.Scalar("1", Field("integer")));
        Assert.Throws<SemanticOperationException>(() => PgMappingSourceValidator.Scalar(DBNull.Value, Field("uuid")));
    }

    /// <summary>时区身份与微秒边界必须由驱动类型证明。</summary>
    [TestMethod]
    public void TimestampKindsAndPrecisionAreNotGuessed()
    {
        // 精确UTC样本保留七位小数但最后一位必须为零，符合PG微秒。
        var utc = new DateTime(2026, 11, 14, 0, 0, 0, DateTimeKind.Utc).AddTicks(1234560);
        Assert.AreEqual("2026-11-14T00:00:00.1234560Z", PgMappingSourceValidator.Scalar(utc, Field("timestamp with time zone")));
        Assert.Throws<SemanticOperationException>(() => PgMappingSourceValidator.Scalar(DateTime.SpecifyKind(utc, DateTimeKind.Unspecified), Field("timestamp with time zone")));
        Assert.Throws<SemanticOperationException>(() => PgMappingSourceValidator.Scalar(utc.AddTicks(1), Field("timestamp with time zone")));
    }

    /// <summary>真实PG TLS、只读ACL、同事务完整行和101行哨兵；缺源不能当PASS。</summary>
    [TestMethod]
    public async Task RealSourceReadsCompleteScopedRowsAndRejectsBudgetTruncation()
    {
        // 仅本任务测试容器提供自己的合成只读凭据文件。
        var passwordFile = Environment.GetEnvironmentVariable("MAPPING_SOURCE_PASSWORD_FILE");
        // 信任根来自本任务新建证书，不使用TrustServerCertificate。
        var certificate = Environment.GetEnvironmentVariable("MAPPING_SOURCE_CA");
        if (passwordFile is null || certificate is null)
        {
            Assert.Inconclusive("需要本任务真实只读源夹具，缺失不算PASS。");
        }
        // 合成密码只留内存且不进入断言输出。
        var password = await File.ReadAllTextAsync(passwordFile!);
        // 固定目标不能被测试放宽成任意连接串。
        var profile = new PgConnectionProfile { Host = "pg-source", Port = 5432, Database = "fixture", Username = "fixture_reader", SslMode = "VerifyFull", AllowedSchemas = ["production"] };
        // 沿生产同一目录发现路径建立真实快照。
        var options = new PgAdapterOptions { RootCertificatePath = certificate! };
        // 短五阶段探测只返回固定诊断码，避免原始源异常泄漏到测试日志。
        var probe = await new PgSourceAdapter(options).ProbeAsync(profile, password, CancellationToken.None);
        Assert.IsTrue(probe.All(stage => stage.Status == "PASS"), string.Join(",", probe.Select(stage => stage.Name + ":" + stage.Status + ":" + stage.DiagnosticCode)));
        // 当前目录必须真实完整，字段名及类型不由测试手填冒充。
        var objects = (await new PgSourceAdapter(options).DiscoverAsync(profile, password, CancellationToken.None))
            .OrderBy(item => item.Schema, StringComparer.Ordinal).ThenBy(item => item.Name, StringComparer.Ordinal).ThenBy(item => item.Kind, StringComparer.Ordinal)
            .Select(item => item with { Fields = item.Fields.OrderBy(field => field.Ordinal).ThenBy(field => field.Name, StringComparer.Ordinal).ToArray() }).ToArray();
        // 指纹沿旧目录字节算法，不采用mapping-c14n替代。
        var fingerprint = Convert.ToHexStringLower(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(new { AdapterVersion = "pg-m1-v1", Objects = objects }, G4ConnectionJson.Options)));
        // 合成snapshot为实际目录结果的传输模型，不宣称持久CatalogJob已经运行。
        var snapshot = new CatalogSnapshotView
        {
            SnapshotId = "source-test",
            ConnectionId = "source",
            ConfigRevision = 1,
            SecretVersion = 1,
            Scope = new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a", "site-b"] },
            SchemaFingerprint = fingerprint,
            CapturedAtUtc = DateTimeOffset.UtcNow,
            Status = "READY",
            Objects = objects
        };
        // 生产读取器必须自己再次回源验证快照和当前ACL。
        var validator = new PgMappingSourceValidator(options);
        // 单厂集合应完整得到两行，不能包含另一个厂区同号业务身份。
        var observed = await validator.ReadAsync(profile, password, snapshot, SourceDefinition("readings"),
            snapshot.Scope with { SiteIds = ["site-a"] }, CancellationToken.None);
        Assert.IsTrue(observed.SecurityVerified);
        Assert.AreEqual(2, observed.Tables.Single().Rows.Length);
        Assert.IsTrue(observed.Tables.Single().Rows.All(row => row["site_id"].Value == "site-a"));
        Assert.IsTrue(observed.Tables.Single().Rows.Any(row => row["temperature"].Value == "20.125"));
        Assert.AreEqual(fingerprint, observed.CatalogFingerprint);
        // 保留完整scope时跨厂同号均可读取，身份是否冲突由后续语义评估决定。
        var both = await validator.ReadAsync(profile, password, snapshot, SourceDefinition("readings"), snapshot.Scope, CancellationToken.None);
        Assert.AreEqual(3, both.Tables.Single().Rows.Length);
        // 完整源集合101行必须拒绝，不返回前100行冒充成功。
        await Assert.ThrowsAsync<SemanticOperationException>(() => validator.ReadAsync(profile, password, snapshot,
            SourceDefinition("readings_overflow"), snapshot.Scope, CancellationToken.None));
        // 四MiB单值必须由源端预算哨兵拒绝，不能先在客户端完整物化。
        var oversized = await Assert.ThrowsAsync<SemanticOperationException>(() => validator.ReadAsync(profile, password, snapshot,
            SourceDefinition("readings_oversized"), snapshot.Scope, CancellationToken.None));
        Assert.AreEqual("mapping_source_budget_exceeded", oversized.Code);
        // varchar不能漏过同一源端预算哨兵。
        var varchar = await Assert.ThrowsAsync<SemanticOperationException>(() => validator.ReadAsync(profile, password, snapshot,
            SourceDefinition("readings_varchar"), snapshot.Scope, CancellationToken.None));
        Assert.AreEqual("mapping_source_budget_exceeded", varchar.Code);
        // 历史正文的ACL检查只核LIMIT 0，不会读取上述超大业务值。
        await validator.VerifyAccessAsync(profile, password, snapshot, SourceDefinition("readings_varchar"), snapshot.Scope, CancellationToken.None);
        // 同一源对象当前指纹不等已绑定指纹，旧snapshot必须拒绝。
        await Assert.ThrowsAsync<SemanticOperationException>(() => validator.ReadAsync(profile, password, snapshot with { SchemaFingerprint = new string('0', 64) },
            SourceDefinition("readings"), snapshot.Scope, CancellationToken.None));
    }

    /// <summary>按固定真实夹具字段构造闭合定义，不生成任何本体事实。</summary>
    private static MappingDefinition SourceDefinition(string table)
    {
        // 首切片注册表精确身份，不拼接SQL。
        var dataset = new MappingDatasetRef { SnapshotId = "source-test", Schema = "production", Name = table, Kind = "TABLE" };
        // 组织与厂区字段为真实text列。
        var organization = new MappingFieldRef { DatasetRef = dataset, Ordinal = 1, Name = "organization_id" };
        // 同一表的厂区字段与身份声明保持一致。
        var site = organization with { Ordinal = 2, Name = "site_id" };
        // 业务时间上下界明确来自源列。
        var from = organization with { Ordinal = 5, Name = "valid_from" };
        // 半开时间终点不能使用默认无穷。
        var to = organization with { Ordinal = 6, Name = "valid_to" };
        return new MappingDefinition
        {
            Entities = [new MappingEntityBinding { Id = "reading", EntityClassIri = "https://example.org/Reading", DatasetRef = dataset,
                IdentitySpecId = "identity", TemporalSpecId = "time", ScopeFields = new MappingScopeFields { Organization = organization, Site = site } }],
            IdentitySpecs = [new MappingIdentitySpec { Id = "identity", OrganizationFieldRef = organization, SiteFieldRef = site, SourceNamespace = "fixture",
                ExternalIdFieldRefs = [organization with { Ordinal = 3, Name = "reading_id" }], ValidFromFieldRef = from, ValidToFieldRef = to }],
            TemporalSpecs = [new MappingTemporalSpec { Id = "time", EventTimeFieldRef = from, ObservedAtFieldRef = organization with { Ordinal = 7, Name = "observed_at" },
                ValidFromFieldRef = from, ValidToFieldRef = to, TimezonePolicy = new MappingTimezonePolicy { Kind = "UTC", ZoneId = null }, Precision = "MICROSECOND" }],
            Properties = [],
            Relations = [],
            Conversions = [],
            UnitSpecs = []
        };
    }

    /// <summary>只构造已记录目录类型，真实目录校验由适配器另证。</summary>
    private static CatalogField Field(string type, int? precision = null, int? scale = null) => new()
    {
        Name = "value",
        NativeType = type,
        Nullable = true,
        Ordinal = 1,
        Precision = precision,
        Scale = scale
    };
}
