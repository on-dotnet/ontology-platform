using Microsoft.AspNetCore.Mvc;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Api.G2;

/// <summary>版本差异和影响报告仅适配HTTP，复用完整授权与幂等应用边界。</summary>
public static class ImpactEndpoints
{
    /// <summary>注册固定版本四源比较、真实报告生成及可审计读取。</summary>
    /// <param name="endpoints">正式宿主的真实路由组合根。</param>
    /// <returns>同一个路由构建器。</returns>
    public static IEndpointRouteBuilder MapImpactEndpoints(this IEndpointRouteBuilder endpoints)
    {
        endpoints.MapPost("/api/v1/ontology-version-diffs", (HttpContext context, CompareVersionsRequest request, [FromServices] IG3ImpactService service) =>
            G2EndpointGuard.TransportAsync(context, "semantic.read", async (actor, token) => Results.Ok(await service.DiffAsync(actor, request, token)), validateCsrf: true))
            .RequireAuthorization("semantic.read").WithTags("Impact").WithName("DiffFixedOntologyVersions")
            .Accepts<CompareVersionsRequest>("application/json").Produces<VersionDiff>()
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404)
            .ProducesProblem(409).ProducesProblem(413).ProducesProblem(422).ProducesProblem(429).ProducesProblem(503);
        endpoints.MapPost("/api/v1/impact-reports", (HttpContext context, GenerateImpactReportRequest request, [FromServices] IG3ImpactService service) =>
            G2EndpointGuard.WriteAsync(context, "ontology.edit", request.Command, (actor, token) => service.GenerateImpactAsync(actor, request, token)))
            .RequireAuthorization("ontology.edit").WithTags("Impact").WithName("GenerateOntologyImpactReport")
            .Accepts<GenerateImpactReportRequest>("application/json").Produces<ImpactReport>()
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404)
            .ProducesProblem(409).ProducesProblem(413).ProducesProblem(422).ProducesProblem(429).ProducesProblem(503);
        endpoints.MapGet("/api/v1/impact-reports/{id}", (HttpContext context, string id, [FromServices] IG3ImpactService service) =>
            G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => service.ReadImpactAsync(actor, id, token)))
            .RequireAuthorization("semantic.read").WithTags("Impact").WithName("ReadOntologyImpactReport")
            .Produces<ImpactReport>().ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(409).ProducesProblem(503);
        return endpoints;
    }
}
