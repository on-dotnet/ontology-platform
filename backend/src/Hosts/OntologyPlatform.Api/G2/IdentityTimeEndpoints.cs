using Microsoft.AspNetCore.Mvc;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Api.G2;

/// <summary>身份与时间接口仅适配HTTP，复用本体应用服务及原身份、作用域和防伪门禁。</summary>
public static class IdentityTimeEndpoints
{
    /// <summary>注册当前草稿读取、原子精确编辑及经过真实Jena核验的正式身份时间读取。</summary>
    /// <param name="endpoints">正式宿主路由组合根。</param>
    /// <returns>原始路由构建器。</returns>
    public static IEndpointRouteBuilder MapIdentityTimeEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/api/v1/ontology-drafts/{id}/identity-time", (HttpContext context, string id, [FromServices] IG3IdentityTimeService service) =>
            G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => service.ReadIdentityTimeAsync(actor, id, token)))
            .RequireAuthorization("semantic.read").WithTags("IdentityTime").WithName("ReadDraftIdentityTime").Produces<VocabularySnapshot>()
            .ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(413).ProducesProblem(422).ProducesProblem(429).ProducesProblem(503);
        endpoints.MapPost("/api/v1/ontology-drafts/{id}/identity-time-edits", (HttpContext context, string id, IdentityTimeEditsRequest request, [FromServices] IG3IdentityTimeService service) =>
            G2EndpointGuard.WriteAsync(context, "ontology.edit", request.Command, (actor, token) => service.EditIdentityTimeAsync(actor, id, request, token), requiresRevision: true))
            .RequireAuthorization("ontology.edit").WithTags("IdentityTime").WithName("EditDraftIdentityTime").Accepts<IdentityTimeEditsRequest>("application/json").Produces<OntologyDraft>()
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(409).ProducesProblem(413).ProducesProblem(422).ProducesProblem(428).ProducesProblem(429).ProducesProblem(503);
        endpoints.MapGet("/api/v1/releases/{id}/identity-time", (HttpContext context, string id, [FromServices] IG3IdentityTimeService service) =>
            G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => service.ReadReleaseIdentityTimeAsync(actor, id, token)))
            .RequireAuthorization("semantic.read").WithTags("IdentityTime").WithName("ReadReleasedIdentityTime").Produces<VocabularySnapshot>()
            .ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(409).ProducesProblem(413).ProducesProblem(422).ProducesProblem(429).ProducesProblem(503);
        return endpoints;
    }
}
