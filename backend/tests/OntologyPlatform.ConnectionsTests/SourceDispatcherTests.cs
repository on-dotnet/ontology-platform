using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>公共分发与凭据用途的无网络合同测试；不代表真实源验收。</summary>
[TestClass]
public sealed class SourceDispatcherTests
{
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
