using OntologyPlatform.Contracts;

namespace OntologyPlatform.Api.G2;

/// <summary>仅绑定HTTP与唯一合同，身份/防伪/修订前置条件复用共同guard。</summary>
public static class OntologyEndpoints
{
    /// <summary>注册草稿目录、源修订、精确编辑、差异与真实校验的受保护REST入口。</summary>
    /// <param name="endpoints">宿主端点组合根。</param>
    /// <returns>原始路由构建器。</returns>
    public static IEndpointRouteBuilder MapOntologyEndpoints(this IEndpointRouteBuilder endpoints)
    {
        // 唯一固定路由前缀，业务规则都留在IOntologyService中。
        var group = endpoints.MapGroup("/api/v1/ontology-drafts").WithTags("Ontology");
        group.MapGet("", (HttpContext context, IOntologyService service) =>
            G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => service.ListAsync(actor, token)))
            .WithName("ListOntologyDrafts").Produces<OntologyDraft[]>().ProducesProblem(401).ProducesProblem(403).ProducesProblem(503);
        group.MapPost("", (HttpContext context, CreateDraftRequest request, IOntologyService service) =>
            G2EndpointGuard.WriteAsync(context, "ontology.edit", request.Command, (actor, token) => service.CreateAsync(actor, request, token)))
            .WithName("CreateOntologyDraft").Accepts<CreateDraftRequest>("application/json").Produces<OntologyDraft>()
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(409).ProducesProblem(413).ProducesProblem(422).ProducesProblem(429).ProducesProblem(503);
        group.MapGet("/{id}", (HttpContext context, string id, IOntologyService service) =>
            G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => service.ReadAsync(actor, id, token)))
            .WithName("ReadOntologyDraft").Produces<OntologyDraft>().ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(503);
        group.MapPut("/{id}", (HttpContext context, string id, SaveDraftRequest request, IOntologyService service) =>
            G2EndpointGuard.WriteAsync(context, "ontology.edit", request.Command, (actor, token) => service.SaveAsync(actor, id, request, token), requiresRevision: true))
            .WithName("SaveOntologyDraft").Accepts<SaveDraftRequest>("application/json").Produces<OntologyDraft>()
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(409).ProducesProblem(413).ProducesProblem(422).ProducesProblem(428).ProducesProblem(429).ProducesProblem(503);
        group.MapPost("/{id}/edits", (HttpContext context, string id, EditDraftRequest request, IOntologyService service) =>
            G2EndpointGuard.WriteAsync(context, "ontology.edit", request.Command, (actor, token) => service.EditAsync(actor, id, request, token), requiresRevision: true))
            .WithName("EditOntologyDraft").Accepts<EditDraftRequest>("application/json").Produces<OntologyDraft>()
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(409).ProducesProblem(413).ProducesProblem(422).ProducesProblem(428).ProducesProblem(429).ProducesProblem(503);
        group.MapGet("/{id}/diff", (HttpContext context, string id, long fromRevision, IOntologyService service) =>
            G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => service.DiffAsync(actor, id, fromRevision, token)))
            .WithName("DiffOntologyDraft").Produces<DraftDiff>().ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(503);
        group.MapPost("/{id}/validations", (HttpContext context, string id, ValidateDraftRequest request, IOntologyService service) =>
            G2EndpointGuard.WriteAsync(context, "ontology.edit", request.Command, (actor, token) => service.ValidateAsync(actor, id, request, token)))
            .WithName("ValidateOntologyDraft").Accepts<ValidateDraftRequest>("application/json").Produces<SemanticValidationReport>()
            .ProducesProblem(400).ProducesProblem(401).ProducesProblem(403).ProducesProblem(404).ProducesProblem(409).ProducesProblem(413).ProducesProblem(422).ProducesProblem(429).ProducesProblem(503);
        return endpoints;
    }
}
