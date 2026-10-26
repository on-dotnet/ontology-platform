using OntologyPlatform.Contracts;
using PlatformError = OntologyPlatform.Api.Contracts.PlatformProblem;

namespace OntologyPlatform.Api.G2;

/// <summary>发布HTTP路由只做共同安全绑定，不复制审批或事务业务。</summary>
public static class PublishingEndpoints
{
    /// <summary>映射真实唯一应用服务，原生策略在JSON绑定前执行。</summary>
    /// <param name="endpoints">宿主真实路由组合根。</param>
    /// <returns>原路由构建器。</returns>
    public static IEndpointRouteBuilder MapPublishingEndpoints(this IEndpointRouteBuilder endpoints)
    {
        Describe(endpoints.MapGet("/api/v1/release-proposals", (HttpContext context, IPublishingService service) => G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => service.ListProposalsAsync(actor, token)))
            .RequireAuthorization("semantic.read").Produces<ReleaseProposal[]>());
        Describe(endpoints.MapPost("/api/v1/release-proposals", (HttpContext context, IPublishingService service, CreateProposalRequest request) => G2EndpointGuard.WriteAsync(context, "release.activate", request.Command, (actor, token) => service.CreateProposalAsync(actor, request, token)))
            .RequireAuthorization("release.activate").Produces<ReleaseProposal>(), 400, 404, 409, 422);
        Describe(endpoints.MapPost("/api/v1/approvals/{id}/decisions", (HttpContext context, IPublishingService service, string id, ApprovalDecisionRequest request) => G2EndpointGuard.WriteAsync(context, "release.approve", request.Command, (actor, token) => service.DecideAsync(actor, id, request, token), true))
            .RequireAuthorization("release.approve").Produces<ReleaseProposal>(), 400, 404, 409, 422, 428);
        Describe(endpoints.MapPost("/api/v1/release-activations", (HttpContext context, IPublishingService service, ActivateReleaseRequest request) => G2EndpointGuard.WriteAsync(context, "release.activate", request.Command, async (actor, token) =>
        {
            // 只有应用服务返回已提交回执，才公开真实审计标识。
            var result = await service.ActivateAsync(actor, request, token);
            context.Response.Headers["X-Audit-Id"] = result.AuditId;
            return result;
        }, true)).RequireAuthorization("release.activate").Produces<ReleaseActivation>(), 400, 404, 409, 413, 422, 428);
        Describe(endpoints.MapGet("/api/v1/releases", (HttpContext context, IPublishingService service, string? assetId) => G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => service.ListReleasesAsync(actor, assetId, token)))
            .RequireAuthorization("semantic.read").Produces<ReleaseSummary[]>());
        Describe(endpoints.MapGet("/api/v1/releases/{id}", (HttpContext context, IReleaseCatalog catalog, string id) => G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => catalog.ReadAsync(actor, id, token)))
            .RequireAuthorization("semantic.read").Produces<ReleaseSummary>(), 404);
        return endpoints;
    }

    /// <summary>将实际安全和业务失败关联到唯一平台Problem，保持运行时错误字段。</summary>
    /// <param name="endpoint">已映射且声明成功响应的生产端点。</param>
    /// <param name="operationErrors">本操作实际可能返回的额外错误。</param>
    private static void Describe(RouteHandlerBuilder endpoint, params int[] operationErrors)
    {
        // 每个状态直接描述真实guard或应用服务的可观察失败。
        foreach (var status in new[] { 401, 403, 500, 503 }.Concat(operationErrors))
        {
            endpoint.Produces<PlatformError>(status, "application/problem+json");
        }
    }
}
