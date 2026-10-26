using System.Diagnostics;
using System.Security.Claims;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Api.G2;

/// <summary>集中登记HTTP、MCP和应用入口共用的角色策略及可信身份投影。</summary>
public static class G2Authorization
{
    /// <summary>注册批准的具名角色策略；资源完整范围仍由应用服务逐次检查。</summary>
    /// <param name="services">宿主服务集合。</param>
    /// <returns>原服务集合，便于宿主组合注册。</returns>
    public static IServiceCollection AddG2Authorization(this IServiceCollection services)
    {
        services.AddAuthorization(options =>
        {
            options.AddPolicy("semantic.read", policy => policy.RequireAuthenticatedUser().RequireRole("platform.viewer", "platform.operator", "platform.auditor"));
            options.AddPolicy("ontology.edit", policy => policy.RequireAuthenticatedUser().RequireRole("platform.operator"));
            options.AddPolicy("release.approve", policy => policy.RequireAuthenticatedUser().RequireRole("platform.auditor"));
            options.AddPolicy("release.activate", policy => policy.RequireAuthenticatedUser().RequireRole("platform.operator"));
        });
        return services;
    }

    /// <summary>只读取G1验证后服务器Claims及安全关联上下文，忽略所有身份请求头。</summary>
    /// <param name="context">已经过宿主认证管道的请求。</param>
    /// <returns>完整可信身份范围；本方法不表示资源授权已完成。</returns>
    public static ActorContext CreateActor(HttpContext context)
    {
        if (context.User.Identity?.IsAuthenticated != true)
        {
            throw new SemanticOperationException(401, "authentication_required");
        }
        return new ActorContext
        {
            SubjectId = context.User.FindFirstValue("sub") ?? string.Empty,
            OrganizationId = context.User.FindFirstValue("organization_id") ?? string.Empty,
            SiteIds = context.User.FindAll("site_ids").Select(claim => claim.Value)
                .Where(value => !string.IsNullOrWhiteSpace(value)).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray(),
            Roles = new[] { "platform.viewer", "platform.operator", "platform.auditor" }.Where(context.User.IsInRole).ToArray(),
            TraceId = Activity.Current?.TraceId.ToString() ?? context.TraceIdentifier,
            CorrelationId = context.Items["CorrelationId"] as string ?? context.TraceIdentifier
        };
    }
}
