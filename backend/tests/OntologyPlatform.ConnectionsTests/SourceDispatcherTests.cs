using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>公共分发与凭据用途的无网络合同测试；不代表真实源验收。</summary>
[TestClass]
public sealed class SourceDispatcherTests
{
    /// <summary>Oracle信任材料更换使已保存配置失效，重新探测可绑定新信任版本。</summary>
    [TestMethod]
    public void OracleTrustRotationInvalidatesStoredConfiguration()
    {
        // 只使用可变非秘密摘要，不接触文件、网络或数据库。
        var oracle = new RecordingOracle();
        // 其它适配器不会在纯哈希测试中执行。
        var dispatcher = new ConnectionSourceDispatcher(new RecordingPg(), new RecordingWeb(), new PgAdapterOptions { RootCertificatePath = "/not-used" }, new WebOperationPolicy(), oracle: oracle);
        // 本测试只调用无存储依赖的配置栅栏。
        var service = new ConnectionApplicationService(null!, null!, dispatcher, null!, null!, TimeProvider.System);
        // 固定Oracle配置序列化使用公开合同。
        var row = new ConnectionRecord { DisplayName = "Oracle", OrganizationId = "org-demo", SiteIds = ["site-a"], ConfigJson = System.Text.Json.JsonSerializer.Serialize<ConnectionConfig>(new OracleConnectionConfig { Profile = new OracleConnectionProfile { Host = "oracle-source", Port = 2484, ServiceName = "FREEPDB1", Username = "FIXTURE_READER", Tls = true, AllowedOwners = ["PRODUCTION", "CaseOwner"] } }, G4ConnectionJson.Options) };
        // 反射避免为测试扩大公开应用接口。
        var rehash = typeof(ConnectionApplicationService).GetMethod("Rehash", System.Reflection.BindingFlags.Instance | System.Reflection.BindingFlags.Static | System.Reflection.BindingFlags.NonPublic)!;
        rehash.Invoke(service, [row]);
        // 捕获初始信任版本对应的哈希。
        var before = row.ConfigHash;
        oracle.TrustFingerprint = "rotated";
        rehash.Invoke(service, [row]);
        Assert.AreNotEqual(before, row.ConfigHash);
    }

    /// <summary>只提供信任版本的Oracle记录器，不构造成功报告。</summary>
    private sealed class RecordingOracle : IOracleSourceAdapter
    {
        /// <summary>模拟服务端CA或wallet更换后的内容摘要。</summary>
        public string TrustFingerprint { get; set; } = "initial";

        /// <summary>纯合同测试不执行探测。</summary>
        public Task<ConnectionProbeStage[]> ProbeAsync(OracleConnectionProfile profile, string secret, CancellationToken token) => throw new NotSupportedException();

        /// <summary>纯合同测试不执行目录发现。</summary>
        public Task<CatalogObject[]> DiscoverAsync(OracleConnectionProfile profile, string secret, CancellationToken token) => throw new NotSupportedException();
    }

    /// <summary>Oracle独立用途与逐字段目标绑定不接受数组引用或scope替换。</summary>
    [TestMethod]
    public void OraclePurposeAndCredentialTargetAreExact()
    {
        // 配置只参与合同比较，不建立网络连接。
        var profile = new OracleConnectionProfile { Host = "oracle-source", Port = 2484, ServiceName = "FREEPDB1", Username = "FIXTURE_READER", Tls = true, AllowedOwners = ["PRODUCTION", "CaseOwner"] };
        // 独立数组但同序同字节的owner列表是相同目标。
        var original = new OracleConnectionConfig { Profile = profile };
        Assert.AreEqual("ORACLE_READONLY", ConnectionSourceDispatcher.SecretPurpose(original));
        ConnectionSourceDispatcher.DemandSameTarget(original, original with { Profile = profile with { AllowedOwners = ["PRODUCTION", "CaseOwner"] } });
        foreach (var changed in new[]
        {
            profile with { Host = "other" }, profile with { Port = 1521 }, profile with { ServiceName = "OTHER" },
            profile with { Username = "OTHER" }, profile with { Tls = false },
            profile with { AllowedOwners = ["CaseOwner", "PRODUCTION"] }, profile with { AllowedOwners = ["PRODUCTION", "CASEOWNER"] }
        })
        {
            Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.DemandSameTarget(original, original with { Profile = changed }));
        }
        Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.DemandPurpose(original, "DORIS_READONLY"));
        Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.DemandSameCredentialScope(original, Scope(), Scope() with { SiteIds = ["site-b"] }));
    }

    /// <summary>Web仅准入API Key及无分页固定操作，PG与Web用途不能互换。</summary>
    [TestMethod]
    public void PurposeIsTypedAndUnsupportedModesFailBeforeBinding()
    {
        // 测试从唯一受控Web配置逐项改变未实现能力。
        var config = Web();
        Assert.AreEqual("WEB_API_KEY", ConnectionSourceDispatcher.SecretPurpose(config));
        Assert.AreEqual("POSTGRESQL_READONLY", ConnectionSourceDispatcher.SecretPurpose(Pg()));
        foreach (var mode in new[] { "NONE", "OAUTH_CLIENT_CREDENTIALS_REF" })
        {
            Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.SecretPurpose(config with { Profile = config.Profile with { Authentication = mode } }));
        }
        Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.SecretPurpose(config with { Profile = config.Profile with { Pagination = "CURSOR" } }));
        Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.DemandPurpose(config, "POSTGRESQL_READONLY"));
        Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.DemandPurpose(Pg(), "WEB_API_KEY"));
    }

    /// <summary>策略引用字符串不授予目标或scope，服务端逐字段核对。</summary>
    [TestMethod]
    public void PolicyRejectsWrongOriginOperationPathAndScope()
    {
        // 策略仅批准本任务固定合成源，不由调用方配置决定。
        var policy = new WebOperationPolicy();
        policy.Validate(Web().Profile, Scope());
        foreach (var profile in new[]
        {
            Web().Profile with { BaseOrigin = "https://attacker.invalid" },
            Web().Profile with { OperationId = "other" },
            Web().Profile with { ApprovedPath = "/v1/items?redirect=other" },
            Web().Profile with { HostPolicyRef = "other" }
        })
        {
            Assert.Throws<SemanticOperationException>(() => policy.Validate(profile, Scope()));
        }
        Assert.Throws<SemanticOperationException>(() => policy.Validate(Web().Profile, Scope() with { SiteIds = ["site-b"] }));
        Assert.Throws<SemanticOperationException>(() => policy.Validate(Web().Profile, Scope() with { OrganizationId = "other" }));
    }

    /// <summary>两个类型进入各自typed入口，未实现类型完全不触碰适配器。</summary>
    [TestMethod]
    public async Task DispatchPreservesTypedPgAndWebBoundaries()
    {
        // 记录器只验证路由和参数，不伪造网络PASS阶段。
        var pg = new RecordingPg();
        // Web记录器不会接收PG profile。
        var web = new RecordingWeb();
        // 原PG服务器策略保持生产Schema默认值。
        var dispatcher = new ConnectionSourceDispatcher(pg, web, new PgAdapterOptions { RootCertificatePath = "/not-used" }, new WebOperationPolicy());
        await dispatcher.ProbeAsync(Pg(), Scope(), "synthetic", CancellationToken.None);
        await dispatcher.DiscoverAsync(Web(), Scope(), "synthetic", CancellationToken.None);
        Assert.AreEqual(1, pg.Calls);
        Assert.AreEqual(1, web.Calls);
        // Oracle仍然是公开可解析但不可运行的配置。
        var oracle = new OracleConnectionConfig { Profile = new OracleConnectionProfile { Host = "oracle", Port = 1521, ServiceName = "fixture", Username = "reader", Tls = true, AllowedOwners = ["OWNER"] } };
        await Assert.ThrowsAsync<SemanticOperationException>(() => dispatcher.ProbeAsync(oracle, Scope(), "synthetic", CancellationToken.None));
        Assert.AreEqual(1, pg.Calls);
        Assert.AreEqual(1, web.Calls);
    }

    /// <summary>等值配置保持原绑定，目标或类型变化必须拒绝旧凭据复用。</summary>
    [TestMethod]
    public void ExistingCredentialCannotChangeTargetOrType()
    {
        // 单一注册操作只允许保留完全相同的Web配置。
        var original = Web();
        ConnectionSourceDispatcher.DemandSameTarget(original, Web());
        foreach (var changed in new[]
        {
            original.Profile with { BaseOrigin = "https://other.invalid" },
            original.Profile with { OperationId = "other" },
            original.Profile with { HostPolicyRef = "other" },
            original.Profile with { Authentication = "NONE" }
        })
        {
            Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.DemandSameTarget(original, original with { Profile = changed }));
        }
        Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.DemandSameTarget(original, Pg()));
        Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.DemandSameTarget(Pg(), original));
    }

    /// <summary>Doris六个目标字段必须全部保持一致，避免旧凭据被送到新目标。</summary>
    [TestMethod]
    public void DorisExistingCredentialCannotChangeAnyTargetField()
    {
        // 配置只用于比较，未调用任何网络适配器。
        var profile = new DorisConnectionProfile { FeHost = "localhost", QueryPort = 19030, Catalog = "internal", Database = "fixture", Username = "fixture_reader", Tls = true };
        // 不同对象但相同字段应被视为同一目标。
        var original = new DorisConnectionConfig { Profile = profile };
        ConnectionSourceDispatcher.DemandSameTarget(original, new DorisConnectionConfig { Profile = profile with { } });
        // 逐个目标字段变更，验证任何一项都不能转移旧凭据。
        foreach (var changed in new[]
        {
            profile with { FeHost = "other.invalid" },
            profile with { QueryPort = 19031 },
            profile with { Catalog = "external" },
            profile with { Database = "other" },
            profile with { Username = "admin" },
            profile with { Tls = false }
        })
        {
            Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.DemandSameTarget(original, new DorisConnectionConfig { Profile = changed }));
        }
        Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.DemandSameTarget(original, Pg()));
        Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.DemandSameTarget(original, Web()));
    }

    /// <summary>Doris旧凭据的范围只能等值重排，不能转移组织或增减厂区。</summary>
    [TestMethod]
    public void DorisCredentialScopeCannotBeRebound()
    {
        // 固定Doris配置，不进行网络调用。
        var config = new DorisConnectionConfig { Profile = new DorisConnectionProfile { FeHost = "localhost", QueryPort = 19030, Catalog = "internal", Database = "fixture", Username = "fixture_reader", Tls = true } };
        // 比较范围按现有规范排序，不把顺序变化误认为迁移。
        var scope = Scope() with { SiteIds = ["site-b", "site-a"] };
        ConnectionSourceDispatcher.DemandSameCredentialScope(config, scope, scope with { SiteIds = ["site-a", "site-b"] });
        Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.DemandSameCredentialScope(config, scope, Scope()));
        Assert.Throws<SemanticOperationException>(() => ConnectionSourceDispatcher.DemandSameCredentialScope(config, scope, scope with { OrganizationId = "other" }));
        // 既有PG范围编辑合同不由Doris扩展改变。
        ConnectionSourceDispatcher.DemandSameCredentialScope(Pg(), scope, Scope());
    }

    /// <summary>合成Web operation，不含密钥。</summary>
    private static WebApiConnectionConfig Web() => new() { Profile = new WebApiConnectionProfile { BaseOrigin = "https://web-source:8443", OperationId = "fixture-items", Method = "GET", ApprovedPath = "/v1/items", Authentication = "API_KEY_REF", Pagination = "NONE", HostPolicyRef = "g4-m2-web-01" } };

    /// <summary>冻结PG合成目标。</summary>
    private static PgConnectionConfig Pg() => new() { Profile = new PgConnectionProfile { Host = "pg-source", Port = 5432, Database = "fixture", Username = "fixture_reader", SslMode = "VerifyFull", AllowedSchemas = ["production"] } };

    /// <summary>固定服务端批准的完整scope。</summary>
    private static ResourceScope Scope() => new() { OrganizationId = "org-demo", SiteIds = ["site-a"] };

    /// <summary>PG调用计数器。</summary>
    private sealed class RecordingPg : IPgSourceAdapter
    {
        /// <summary>实际被调用次数。</summary>
        public int Calls { get; private set; }

        /// <summary>记录探测调用而不声称阶段通过。</summary>
        public Task<ConnectionProbeStage[]> ProbeAsync(PgConnectionProfile profile, string secret, CancellationToken cancellationToken) { Calls++; return Task.FromResult(Array.Empty<ConnectionProbeStage>()); }

        /// <summary>记录发现调用，不生成目录。</summary>
        public Task<CatalogObject[]> DiscoverAsync(PgConnectionProfile profile, string secret, CancellationToken cancellationToken) { Calls++; return Task.FromResult(Array.Empty<CatalogObject>()); }
    }

    /// <summary>Web调用计数器。</summary>
    private sealed class RecordingWeb : IWebSourceAdapter
    {
        /// <summary>实际被调用次数。</summary>
        public int Calls { get; private set; }

        /// <summary>记录typed探测调用。</summary>
        public Task<ConnectionProbeStage[]> ProbeAsync(WebApiConnectionProfile profile, string secret, CancellationToken cancellationToken) { Calls++; return Task.FromResult(Array.Empty<ConnectionProbeStage>()); }

        /// <summary>记录typed发现调用。</summary>
        public Task<CatalogObject[]> DiscoverAsync(WebApiConnectionProfile profile, string secret, CancellationToken cancellationToken) { Calls++; return Task.FromResult(Array.Empty<CatalogObject>()); }
    }
}
