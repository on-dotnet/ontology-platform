using System.Data.Common;
using System.Diagnostics;
using System.Diagnostics.Metrics;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>查询层只接受受信身份、有限计划和正式发布范围。</summary>
internal static class QueryRules
{
    /// <summary>宿主统一订阅的查询跟踪源。</summary>
    internal static readonly ActivitySource Activities = new("OntologyPlatform.SemanticQuery");

    /// <summary>宿主统一订阅的低基数查询度量。</summary>
    private static readonly Meter Meter = new("OntologyPlatform.SemanticQuery");

    /// <summary>仅按三能力和六态记录次数，不记录主体、厂区或正文。</summary>
    internal static readonly Counter<long> Queries = Meter.CreateCounter<long>("semantic.query.count");

    /// <summary>完整平台只读角色，简写角色不能获得任何权限。</summary>
    internal static void DemandActor(ActorContext actor)
    {
        if (string.IsNullOrWhiteSpace(actor.SubjectId) || string.IsNullOrWhiteSpace(actor.OrganizationId) || !actor.Roles.Any(role => role is "platform.viewer" or "platform.operator" or "platform.auditor")) throw new SemanticOperationException(403, "role_denied");
    }

    /// <summary>授权集合要求组织相同且资源全部厂区可访问。</summary>
    internal static bool Covers(ActorContext actor, ResourceScope scope) => scope.OrganizationId == actor.OrganizationId && scope.SiteIds.Length > 0 && scope.SiteIds.All(site => actor.SiteIds.Contains(site, StringComparer.Ordinal));

    /// <summary>在任何依赖访问前验证已声明厂区和有界参数。</summary>
    internal static void Validate(ActorContext actor, SemanticQueryPlan plan)
    {
        DemandActor(actor);
        if (plan.SiteId is not null && !actor.SiteIds.Contains(plan.SiteId, StringComparer.Ordinal)) throw new SemanticOperationException(403, "scope_denied");
        if (string.IsNullOrWhiteSpace(plan.AssetId) || plan.AssetId.Length > 128 || plan.Depth is < 1 or > 5 || plan.MaxRows is < 1 or > 100 || plan.TimeoutMs is < 1 or > 5000 || plan.RelationshipIris is null || plan.RelationshipIris.Length > 16 || plan.ExternalId?.Length > 256 || plan.SiteId?.Length > 128 || plan.ReleaseId?.Length > 64) throw new SemanticOperationException(422, "query_budget_invalid");
        if (plan.EntityIri is not null && !IsIri(plan.EntityIri) || plan.EntityType is not null && !IsIri(plan.EntityType) || plan.RelationshipIris.Any(value => !IsIri(value))) throw new SemanticOperationException(422, "query_iri_invalid");
        if (plan.CapabilityId != "describe_ontology" && string.IsNullOrWhiteSpace(plan.EntityIri) && string.IsNullOrWhiteSpace(plan.ExternalId)) throw new SemanticOperationException(422, "query_identity_required");
    }

    /// <summary>IRI仅用于图内等值匹配，从不拼接SPARQL；拒绝控制符和非法IRI标点。</summary>
    private static bool IsIri(string value) => value.Length is > 0 and <= 2048 && Uri.TryCreate(value, UriKind.Absolute, out _) && !value.Any(character => char.IsWhiteSpace(character) || char.IsControl(character) || "<>\"{}|^`\\".Contains(character));

    /// <summary>固定诊断不回显输入、源正文或依赖异常。</summary>
    internal static SemanticDiagnostic Diagnostic(string code) => new() { Code = code, Severity = DiagnosticSeverity.Warning, Message = code switch { "evidence_missing" => "部分事实缺少可验证来源。", "query_limited" => "结果达到批准预算。", "scope_denied" => "目标不在可访问范围内。", _ => "正式语义依赖暂不可用。" } };

    /// <summary>所有读取和拒绝通过Governance独立持久审计，失败不得返回成功。</summary>
    internal static async Task<string> AuditAsync(IAuditTrail audit, ActorContext actor, string action, string outcome, CancellationToken token)
    {
        try
        {
            return await audit.WriteAsync(actor, new AuditCommand { Action = action, Resource = "semantic.gateway", Outcome = outcome, Scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = actor.SiteIds } }, token);
        }
        catch (Exception failure) when (failure is DbException || failure.InnerException is DbException)
        {
            // 模块不依赖EF/Npgsql实现类型；仅处理标准数据库故障，不能透出原始正文。
            throw new SemanticOperationException(503, "audit_unavailable");
        }
    }
}
