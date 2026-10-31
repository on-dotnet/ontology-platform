using Microsoft.AspNetCore.Mvc;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Api.G2;

/// <summary>沿用完整语义读取授权的固定版本高阶表达式路由，不提供结构写入。</summary>
public static class ExpressionEndpoints
{
    /// <summary>读取准确草稿修订或正式发布，安全拒绝保留共同guard的审计行为。</summary>
    /// <param name="endpoints">宿主路由集合。</param>
    /// <returns>原路由集合。</returns>
    public static IEndpointRouteBuilder MapExpressionEndpoints(this IEndpointRouteBuilder endpoints)
    {
        Describe(endpoints.MapGet("/api/v1/ontology-drafts/{id}/expressions", (HttpContext context, string id, long revision, [FromServices] IG3ExpressionService service) =>
            G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => service.ReadExpressionsAsync(actor,
                new VersionRef { Kind = VersionRefKind.Draft, Id = id, Revision = revision }, token)))
            .WithName("ReadFixedDraftExpressions"));
        Describe(endpoints.MapGet("/api/v1/releases/{id}/expressions", (HttpContext context, string id, [FromServices] IG3ExpressionService service) =>
            G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => service.ReadExpressionsAsync(actor,
                new VersionRef { Kind = VersionRefKind.Release, Id = id, Revision = null }, token)))
            .WithName("ReadFixedReleaseExpressions"));
        return endpoints;
    }

    /// <summary>统一声明真实响应和既有认证、范围、依赖及输入失败边界。</summary>
    /// <param name="endpoint">当前只读端点。</param>
    /// <returns>带明确权限和协议说明的端点。</returns>
    private static RouteHandlerBuilder Describe(RouteHandlerBuilder endpoint) => endpoint
        .RequireAuthorization("semantic.read").WithTags("Expressions").Produces<OwlExpressionSnapshot>()
        .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404)
        .ProducesProblem(409).ProducesProblem(422).ProducesProblem(503);
}
