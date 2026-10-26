using OntologyPlatform.Contracts;

namespace OntologyPlatform.Api.G2;

/// <summary>REST与MCP/Agent共用唯一正式Gateway和证据服务，不复制查询执行。</summary>
public static class SemanticEndpoints
{
    /// <summary>映射受信服务器身份、明确强类型合同和安全只读入口。</summary>
    public static IEndpointRouteBuilder MapSemanticEndpoints(this IEndpointRouteBuilder endpoints)
    {
        Secure(endpoints.MapGet("/api/v1/capabilities", (HttpContext context, ISemanticGateway gateway) => G2EndpointGuard.ReadAsync(context, "semantic.read", (_, _) => Task.FromResult(gateway.GetCapabilities()))).Produces<SemanticCapability[]>());
        Secure(endpoints.MapPost("/api/v1/semantic/queries", (HttpContext context, ISemanticGateway gateway, SemanticQueryPlan plan) => G2EndpointGuard.TransportAsync(context, "semantic.read", async (actor, token) => Results.Ok(await gateway.ExecuteAsync(actor, plan, token)), validateCsrf: true)).Produces<SemanticQueryResult>())
            .ProducesProblem(400).ProducesProblem(404).ProducesProblem(409).ProducesProblem(422);
        Secure(endpoints.MapGet("/api/v1/semantic/discover", (HttpContext context, ISemanticGateway gateway, string assetId, string? releaseId) => G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) =>
        {
            // 发现能力版本取自同一实际Registry，绝不写死v1。
            var capability = gateway.GetCapabilities().Single(value => value.Id == "describe_ontology");
            return gateway.ExecuteAsync(actor, new SemanticQueryPlan { CapabilityId = capability.Id, CapabilityVersion = capability.Version, AssetId = assetId, ReleaseId = releaseId, Depth = 1, MaxRows = 100, TimeoutMs = 5000 }, token);
        })).Produces<SemanticQueryResult>()).ProducesProblem(400).ProducesProblem(404).ProducesProblem(409).ProducesProblem(422);
        Secure(endpoints.MapGet("/api/v1/evidence/{id}", (HttpContext context, IEvidenceService evidence, string id) => G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => evidence.ReadAsync(actor, id, token))).Produces<EvidenceRef>()).ProducesProblem(404);
        return endpoints;
    }

    /// <summary>原生授权在JSON绑定之前执行，同一策略与实际安全Problem一起进入OpenAPI元数据。</summary>
    private static RouteHandlerBuilder Secure(RouteHandlerBuilder endpoint) => endpoint.RequireAuthorization("semantic.read").ProducesProblem(401).ProducesProblem(403).ProducesProblem(503);
}
