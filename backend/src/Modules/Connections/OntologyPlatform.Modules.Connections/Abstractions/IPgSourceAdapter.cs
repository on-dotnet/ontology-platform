using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>仅受控合成PostgreSQL的只读探测与目录发现，不接受自由SQL。</summary>
public interface IPgSourceAdapter
{
    /// <summary>执行网络、TLS、认证、只读角色及元数据五阶段真实验证。</summary>
    /// <param name="profile">已经过目标策略检查的配置。</param>
    /// <param name="secret">仅当前调用内存中的凭据，不允许日志或持久化。</param>
    /// <param name="cancellationToken">有界总期限与取消信号。</param>
    /// <returns>五阶段实测报告，只有五项PASS可启用。</returns>
    Task<ConnectionProbeStage[]> ProbeAsync(PgConnectionProfile profile, string secret, CancellationToken cancellationToken);

    /// <summary>只读取授权metadata，不访问业务行；上限100对象、2000字段、2MiB和20秒。</summary>
    /// <param name="profile">已经过目标策略检查的配置。</param>
    /// <param name="secret">仅内存的当前版本凭据。</param>
    /// <param name="cancellationToken">任务取消及总期限。</param>
    /// <returns>受限对象元数据；权限不充分或预算截断必须抛出固定安全错误。</returns>
    Task<CatalogObject[]> DiscoverAsync(PgConnectionProfile profile, string secret, CancellationToken cancellationToken);
}

/// <summary>由服务器提供的信任与准确目标配置，不能从HTTP请求覆盖。</summary>
public sealed class PgAdapterOptions
{
    /// <summary>固定Compose服务名称。</summary>
    public string AllowedHost { get; init; } = "pg-source";

    /// <summary>唯一批准端口。</summary>
    public int AllowedPort { get; init; } = 5432;

    /// <summary>服务器挂载的可信CA文件。</summary>
    public required string RootCertificatePath { get; init; }

    /// <summary>允许的精确合成数据库。</summary>
    public string AllowedDatabase { get; init; } = "fixture";

    /// <summary>唯一批准只读角色。</summary>
    public string AllowedUsername { get; init; } = "fixture_reader";

    /// <summary>服务器允许Schema，源ACL仍须再次验证。</summary>
    public string[] AllowedSchemas { get; init; } = ["production"];
}

/// <summary>源适配器只允许传递固定诊断码，不携原始异常、SQL或网络地址。</summary>
public sealed class PgSourceException : Exception
{
    /// <summary>允许跨Adapter边界的完整安全分类。</summary>
    private static readonly HashSet<string> Allowed = new(StringComparer.Ordinal)
    {
        "connection_network_forbidden", "connection_tls_untrusted", "connection_auth_failed",
        "connection_readonly_unverified", "catalog_access_forbidden", "catalog_permission_limited",
        "catalog_budget_exceeded", "connection_source_unavailable", "connection_cancelled"
    };

    /// <summary>拒绝未知分类，异常正文永远为安全常量。</summary>
    /// <param name="code">冻结的机器码。</param>
    public PgSourceException(string code) : base("Source operation failed.")
    {
        if (!Allowed.Contains(code))
        {
            throw new ArgumentException("Unknown source diagnostic.", nameof(code));
        }
        Code = code;
    }

    /// <summary>可供Host映射到固定HTTP或业务状态的诊断码。</summary>
    public string Code { get; }
}
