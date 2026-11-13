using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>分发PG、Web、Doris和Oracle四项typed能力，保持其它公开类型不可执行。</summary>
public sealed class ConnectionSourceDispatcher
{
    /// <summary>冻结PG的既有真实实现。</summary>
    private readonly IPgSourceAdapter pg;

    /// <summary>固定HTTPS GET的真实实现。</summary>
    private readonly IWebSourceAdapter web;

    /// <summary>可选注入的Doris真实元数据能力，缺失时拒绝执行。</summary>
    private readonly IDorisSourceAdapter? doris;

    /// <summary>Oracle真实实现可选，缺失时在凭据消费前拒绝。</summary>
    private readonly IOracleSourceAdapter? oracle;

    /// <summary>由服务器明确批准的原PG空public例外。</summary>
    private readonly bool allowEmptyPublic;

    /// <summary>只读的服务器Web操作注册。</summary>
    private readonly WebOperationPolicy webPolicy;

    /// <summary>冻结现行PG策略并注入独立typed能力。</summary>
    public ConnectionSourceDispatcher(IPgSourceAdapter pg, IWebSourceAdapter web, PgAdapterOptions options, WebOperationPolicy webPolicy, IDorisSourceAdapter? doris = null, IOracleSourceAdapter? oracle = null)
    {
        this.doris = doris;
        this.oracle = oracle;
        this.pg = pg;
        this.web = web;
        this.webPolicy = webPolicy;
        allowEmptyPublic = options.AllowedSchemas?.ToArray() switch
        {
            ["production"] => false,
            ["production", "public"] => true,
            _ => throw new PgSourceException("connection_network_forbidden")
        };
    }

    /// <summary>服务端从类型化配置确定唯一凭据用途，未实现类型在消费前拒绝。</summary>
    public static string SecretPurpose(ConnectionConfig config) => config switch
    {
        PgConnectionConfig => "POSTGRESQL_READONLY",
        DorisConnectionConfig => "DORIS_READONLY",
        OracleConnectionConfig => "ORACLE_READONLY",
        WebApiConnectionConfig { Profile.Authentication: "API_KEY_REF", Profile.Pagination: "NONE", Profile.Method: "GET" } => "WEB_API_KEY",
        _ => throw new SemanticOperationException(422, "connector_not_enabled")
    };

    /// <summary>错误用途沿用固定秘密无效分类，不回显用途或秘密内容。</summary>
    public static void DemandPurpose(ConnectionConfig config, string purpose)
    {
        if (SecretPurpose(config) != purpose) throw new SemanticOperationException(422, "connection_secret_expired");
    }

    /// <summary>已有凭据不能随着编辑转移到另一类型或Web、Doris目标；需新建并重新签发。</summary>
    public static void DemandSameTarget(ConnectionConfig before, ConnectionConfig after)
    {
        if (before.GetType() != after.GetType() || before is WebApiConnectionConfig oldWeb
            && after is WebApiConnectionConfig newWeb && oldWeb.Profile != newWeb.Profile
            || before is DorisConnectionConfig oldDoris && after is DorisConnectionConfig newDoris && oldDoris.Profile != newDoris.Profile
            || before is OracleConnectionConfig oldOracle && after is OracleConnectionConfig newOracle
                && (oldOracle.Profile.Host != newOracle.Profile.Host || oldOracle.Profile.Port != newOracle.Profile.Port
                    || oldOracle.Profile.ServiceName != newOracle.Profile.ServiceName || oldOracle.Profile.Username != newOracle.Profile.Username
                    || oldOracle.Profile.Tls != newOracle.Profile.Tls
                    || !oldOracle.Profile.AllowedOwners.SequenceEqual(newOracle.Profile.AllowedOwners, StringComparer.Ordinal)))
            throw new SemanticOperationException(422, "connection_profile_invalid");
    }

    /// <summary>Doris范围变更必须重新Intake，禁止以旧密文重新绑定组织或厂区。</summary>
    /// <param name="config">当前已绑定的类型化配置。</param>
    /// <param name="before">持久化凭据的原范围。</param>
    /// <param name="after">请求的新范围。</param>
    public static void DemandSameCredentialScope(ConnectionConfig config, ResourceScope before, ResourceScope after)
    {
        if (config is DorisConnectionConfig or OracleConnectionConfig && (before.OrganizationId != after.OrganizationId
            || !before.SiteIds.Order(StringComparer.Ordinal).SequenceEqual(after.SiteIds.Order(StringComparer.Ordinal))))
            throw new SemanticOperationException(422, "connection_profile_invalid");
    }

    /// <summary>每次绑定和网络调用前都核对服务器目标及当前scope。</summary>
    public ConnectionConfig Validate(ConnectionConfig config, ResourceScope scope)
    {
        G4ConnectionRules.Config(config);
        _ = SecretPurpose(config);
        if (config is WebApiConnectionConfig webConfig) webPolicy.Validate(webConfig.Profile, scope);
        else if (config is OracleConnectionConfig oracleConfig)
        {
            OracleAdapterOptions.Validate(oracleConfig.Profile, scope);
            if (oracle is null) throw new SemanticOperationException(422, "connector_not_enabled");
            _ = oracle.TrustFingerprint;
        }
        else if (config is DorisConnectionConfig dorisConfig)
        {
            DorisAdapterOptions.Validate(dorisConfig.Profile, scope);
            if (doris is null) throw new SemanticOperationException(422, "connector_not_enabled");
        }
        else if (config is PgConnectionConfig pgConfig)
        {
            // 保留M1精确目标和Schema规则，不能由Web上线扩大PG执行集合。
            var profile = pgConfig.Profile;
            if (profile.SslMode != "VerifyFull") throw new SemanticOperationException(422, "connection_tls_untrusted");
            if (profile.Host != "pg-source" || profile.Port != 5432 || profile.Database != "fixture"
                || profile.Username != "fixture_reader" || (profile.AllowedSchemas is not ["production"] && !(allowEmptyPublic && profile.AllowedSchemas is ["production", "public"])))
                throw new SemanticOperationException(403, "connection_network_forbidden");
        }
        return config;
    }

    /// <summary>Oracle绑定服务端信任材料；既有连接器不引入新的哈希字段。</summary>
    public string? TrustFingerprint(ConnectionConfig config) => config is OracleConnectionConfig
        ? (oracle ?? throw new SemanticOperationException(422, "connector_not_enabled")).TrustFingerprint : null;

    /// <summary>验证后调用准确typed探测入口，取消令牌原样传递。</summary>
    public Task<ConnectionProbeStage[]> ProbeAsync(ConnectionConfig config, ResourceScope scope, string secret, CancellationToken cancellationToken)
        => Validate(config, scope) switch
        {
            OracleConnectionConfig value => oracle!.ProbeAsync(value.Profile, secret, cancellationToken),
            DorisConnectionConfig value => doris!.ProbeAsync(value.Profile, secret, cancellationToken),
            PgConnectionConfig value => pg.ProbeAsync(value.Profile, secret, cancellationToken),
            WebApiConnectionConfig value => web.ProbeAsync(value.Profile, secret, cancellationToken),
            _ => throw new SemanticOperationException(422, "connector_not_enabled")
        };

    /// <summary>验证后调用准确typed发现入口，绝不把Web配置转换为PG。</summary>
    public Task<CatalogObject[]> DiscoverAsync(ConnectionConfig config, ResourceScope scope, string secret, CancellationToken cancellationToken)
        => Validate(config, scope) switch
        {
            OracleConnectionConfig value => oracle!.DiscoverAsync(value.Profile, secret, cancellationToken),
            DorisConnectionConfig value => doris!.DiscoverAsync(value.Profile, secret, cancellationToken),
            PgConnectionConfig value => pg.DiscoverAsync(value.Profile, secret, cancellationToken),
            WebApiConnectionConfig value => web.DiscoverAsync(value.Profile, secret, cancellationToken),
            _ => throw new SemanticOperationException(422, "connector_not_enabled")
        };
}
