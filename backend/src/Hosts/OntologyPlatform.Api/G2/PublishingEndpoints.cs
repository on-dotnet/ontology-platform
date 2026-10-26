using OntologyPlatform.Contracts;

namespace OntologyPlatform.Api.G2;

/// <summary>发布HTTP路由只做共同安全绑定，不复制审批或事务业务。</summary>
public static class PublishingEndpoints
{
    /// <summary>映射真实唯一应用服务并提供OpenAPI强类型响应元数据。</summary>
    public static IEndpointRouteBuilder MapPublishingEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/api/v1/release-proposals", (HttpContext context, IPublishingService service) => G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => service.ListProposalsAsync(actor, token))).Produces<ReleaseProposal[]>();
        endpoints.MapPost("/api/v1/release-proposals", (HttpContext context, IPublishingService service, CreateProposalRequest request) => G2EndpointGuard.WriteAsync(context, "release.activate", request.Command, (actor, token) => service.CreateProposalAsync(actor, request, token))).Produces<ReleaseProposal>();
        endpoints.MapPost("/api/v1/approvals/{id}/decisions", (HttpContext context, IPublishingService service, string id, ApprovalDecisionRequest request) => G2EndpointGuard.WriteAsync(context, "release.approve", request.Command, (actor, token) => service.DecideAsync(actor, id, request, token), true)).Produces<ReleaseProposal>();
        endpoints.MapPost("/api/v1/release-activations", (HttpContext context, IPublishingService service, ActivateReleaseRequest request) => G2EndpointGuard.WriteAsync(context, "release.activate", request.Command, async (actor, token) =>
        {
            // 只有应用服务返回已提交回执，才公开真实审计标识。
            var result = await service.ActivateAsync(actor, request, token);
            context.Response.Headers["X-Audit-Id"] = result.AuditId;
            return result;
        }, true)).Produces<ReleaseActivation>();
        endpoints.MapGet("/api/v1/releases", (HttpContext context, IPublishingService service, string? assetId) => G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => service.ListReleasesAsync(actor, assetId, token))).Produces<ReleaseSummary[]>();
        endpoints.MapGet("/api/v1/releases/{id}", (HttpContext context, IReleaseCatalog catalog, string id) => G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => catalog.ReadAsync(actor, id, token))).Produces<ReleaseSummary>();
        return endpoints;
    }
}
