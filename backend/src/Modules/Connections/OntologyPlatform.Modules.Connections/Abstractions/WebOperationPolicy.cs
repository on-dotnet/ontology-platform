using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>本切片唯一可信操作注册；客户端的HostPolicyRef只作索引，不能授予新目标。</summary>
public sealed class WebOperationPolicy
{
    /// <summary>唯一批准的合成HTTPS origin，不可由请求或配置覆盖。</summary>
    public const string Origin = "https://web-source:8443";

    /// <summary>唯一登记的只读数据操作。</summary>
    public const string Operation = "fixture-items";

    /// <summary>固定无查询参数路径，禁止相对路径解析扩大目标。</summary>
    public const string Path = "/v1/items";

    /// <summary>可信策略的固定引用。</summary>
    public const string PolicyReference = "g4-m2-web-01";

    /// <summary>API Key只注入此头，不接受用户模板、Cookie或Authorization。</summary>
    public const string KeyHeader = "X-Fixture-Api-Key";

    /// <summary>验证所有目标字段与当前资源范围，未实现认证/分页在绑定前拒绝。</summary>
    /// <param name="profile">不可信客户端或持久化配置。</param>
    /// <param name="scope">已通过Actor授权的资源范围。</param>
    public void Validate(WebApiConnectionProfile profile, ResourceScope scope)
    {
        G4ConnectionRules.Config(new WebApiConnectionConfig { Profile = profile });
        if (profile.Authentication != "API_KEY_REF" || profile.Pagination != "NONE")
            throw new SemanticOperationException(422, "connector_not_enabled");
        if (profile.BaseOrigin != Origin || profile.OperationId != Operation || profile.Method != "GET"
            || profile.ApprovedPath != Path || profile.HostPolicyRef != PolicyReference)
            throw new SemanticOperationException(403, "connection_network_forbidden");
        if (scope.OrganizationId != "org-demo" || scope.SiteIds is not ["site-a"])
            throw new SemanticOperationException(403, "connection_scope_forbidden");
    }
}

/// <summary>仅可信任务运行器在隔离Development环境提供的精确合成TLS身份。</summary>
public sealed class WebAdapterOptions
{
    /// <summary>精确任务身份，缺失时Web能力关闭。</summary>
    public string TaskId { get; init; } = string.Empty;

    /// <summary>已登记隔离资源的运行身份。</summary>
    public string RunId { get; init; } = string.Empty;

    /// <summary>服务器挂载的任务独立CA路径，不使用系统信任例外。</summary>
    public string RootCertificatePath { get; init; } = string.Empty;
}
