using OntologyPlatform.Contracts;

namespace OntologyPlatform.Api.G2;

/// <summary>M1支持策略、真实发布资格及固定版本比较的HTTP组合，不复制本体业务。</summary>
public static class G3Endpoints
{
    /// <summary>绑定前先执行既有认证策略，正文不接受客户端主体或发布资格。</summary>
    /// <param name="endpoints">真实宿主路由构建器。</param>
    /// <returns>同一路由构建器。</returns>
    public static IEndpointRouteBuilder MapG3Endpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapGet("/api/v1/semantic/support-profile", (HttpContext context, IG3OntologyService service) =>
            G2EndpointGuard.ReadAsync(context, "semantic.read", (_, _) => Task.FromResult(service.GetProfile())))
            .RequireAuthorization("semantic.read").WithName("ReadSemanticSupportProfile")
            .Produces<SemanticSupportProfile>().ProducesProblem(401).ProducesProblem(403);

        endpoints.MapPost("/api/v1/ontology-drafts/{id}/assessments", (HttpContext context, string id, ValidateDraftRequest request, IG3OntologyService service) =>
            G2EndpointGuard.WriteAsync(context, "ontology.edit", request.Command,
                (actor, token) => service.AssessAsync(actor, id, request, token), requiresRevision: true))
            .RequireAuthorization("ontology.edit").WithName("AssessOntologyDraft")
            .Accepts<ValidateDraftRequest>("application/json").Produces<SemanticAssessment>()
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404)
            .ProducesProblem(409).ProducesProblem(413).ProducesProblem(422).ProducesProblem(428)
            .ProducesProblem(429).ProducesProblem(503);

        endpoints.MapGet("/api/v1/semantic-assessments/{id}", (HttpContext context, string id, IG3OntologyService service) =>
            G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => service.ReadAssessmentAsync(actor, id, token)))
            .RequireAuthorization("semantic.read").WithName("ReadSemanticAssessment")
            .Produces<SemanticAssessment>().ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(503);

        endpoints.MapPost("/api/v1/ontology-comparisons", (HttpContext context, CompareVersionsRequest request, IG3OntologyService service) =>
            G2EndpointGuard.TransportAsync(context, "semantic.read", async (actor, token) =>
                Results.Ok(await service.CompareAsync(actor, request, token)), validateCsrf: true))
            .RequireAuthorization("semantic.read").WithName("CompareOntologyVersions")
            .Accepts<CompareVersionsRequest>("application/json").Produces<SourceComparison[]>()
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404)
            .ProducesProblem(413).ProducesProblem(422).ProducesProblem(429).ProducesProblem(503);
        return endpoints;
    }
}
