using System.Globalization;
using System.Text;
using System.Text.Json;
using OntologyPlatform.Api.G2;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.Api.G4;

/// <summary>映射专用严格传输边界，沿原认证、CSRF与ProblemDetails，不提供M4查询。</summary>
public static class MappingEndpoints
{
    /// <summary>真实路由和唯一OpenAPI从同一组声明导出。</summary>
    public static void MapMappingEndpoints(this WebApplication app)
    {
        app.MapGet("/api/v1/mappings", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "list", "mapping.read", null, 200))).Produces<MappingPage<MappingListItem>>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapPost("/api/v1/mappings", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "create", "mapping.edit", typeof(MappingDraftCreateRequest), 201))).Accepts<MappingDraftCreateRequest>("application/json").Produces<MappingDraftView>(201).WithTags("Mappings").WithGroupName("g4");
        app.MapGet("/api/v1/mappings/{id}", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "draft", "mapping.read", null, 200))).Produces<MappingDraftView>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapPatch("/api/v1/mappings/{id}", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "patch", "mapping.edit", typeof(MappingDraftPatchRequest), 200))).Accepts<MappingDraftPatchRequest>("application/json").Produces<MappingDraftView>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapGet("/api/v1/mappings/{id}/revisions/{revision}", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "revision", "mapping.read", null, 200))).Produces<MappingDraftView>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapGet("/api/v1/mappings/{id}/diff", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "diff", "mapping.read", null, 200))).Produces<MappingDiffView>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapGet("/api/v1/mappings/{id}/release-diff", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "release-diff", "mapping.read", null, 200))).Produces<MappingDiffView>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapPost("/api/v1/mappings/{id}/suggestions", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "suggestions", "mapping.edit", typeof(MappingSuggestionRequest), 200))).Accepts<MappingSuggestionRequest>("application/json").Produces<MappingSuggestionView>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapPost("/api/v1/mappings/{id}/validate", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "validate", "mapping.validate", typeof(MappingValidateRequest), 202))).Accepts<MappingValidateRequest>("application/json").Produces<MappingJobView>(202).WithTags("Mappings").WithGroupName("g4");
        app.MapGet("/api/v1/mapping-jobs/{id}", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "job", "mapping.read", null, 200))).Produces<MappingJobView>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapPost("/api/v1/mapping-jobs/{id}/cancel", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "cancel-job", "mapping.validate", typeof(MappingCommandRequest), 200))).Accepts<MappingCommandRequest>("application/json").Produces<MappingJobView>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapGet("/api/v1/mappings/{id}/assessments", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "assessments", "mapping.read", null, 200))).Produces<MappingPage<MappingAssessmentView>>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapGet("/api/v1/mapping-assessments/{id}", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "assessment", "mapping.read", null, 200))).Produces<MappingAssessmentView>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapPost("/api/v1/mappings/{id}/proposals", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "propose", "mapping.submit", typeof(MappingProposalCreateRequest), 201))).Accepts<MappingProposalCreateRequest>("application/json").Produces<MappingProposalView>(201).WithTags("Mappings").WithGroupName("g4");
        app.MapGet("/api/v1/mapping-proposals", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "proposals", "mapping.review", null, 200))).Produces<MappingPage<MappingProposalView>>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapGet("/api/v1/mapping-proposals/{id}", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "proposal", "mapping.read", null, 200))).Produces<MappingProposalView>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapPost("/api/v1/mapping-proposals/{id}/decisions", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "decide", "mapping.approve", typeof(MappingDecisionRequest), 200))).Accepts<MappingDecisionRequest>("application/json").Produces<MappingProposalView>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapPost("/api/v1/mapping-proposals/{id}/cancel", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "cancel-proposal", "mapping.submit", typeof(MappingCommandRequest), 200))).Accepts<MappingCommandRequest>("application/json").Produces<MappingProposalView>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapPost("/api/v1/mapping-proposals/{id}/activate", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "activate", "mapping.activate", typeof(MappingActivationRequest), 200))).Accepts<MappingActivationRequest>("application/json").Produces<MappingActivationReceipt>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapGet("/api/v1/mapping-proposals/{id}/activation-checks", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "checks", "mapping.read", null, 200))).Produces<MappingPage<MappingActivationCheck>>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapGet("/api/v1/mapping-activation-checks/{id}", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "check", "mapping.read", null, 200))).Produces<MappingActivationCheck>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapGet("/api/v1/mapping-releases", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "releases", "mapping.read", null, 200))).Produces<MappingPage<MappingReleaseView>>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapGet("/api/v1/mapping-releases/{id}", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "release", "mapping.read", null, 200))).Produces<MappingReleaseView>(200).WithTags("Mappings").WithGroupName("g4");
        app.MapGet("/api/v1/mappings/{id}/active", (Func<HttpContext, Task<IResult>>)(context => ExecuteAsync(context, "active", "mapping.read", null, 200))).Produces<MappingActiveView>(200).WithTags("Mappings").WithGroupName("g4");
    }

    /// <summary>先可信认证和CSRF，再严格解析及应用授权；事务提交之前不返回成功。</summary>
    private static Task<IResult> ExecuteAsync(HttpContext context, string operation, string policy, Type? requestType, int status)
    {
        return G2EndpointGuard.TransportAsync(context, policy, async (actor, token) =>
        {
            // 同一会话引用仅由实际票据存储设置，不能从请求头伪造。
            var session = context.Items["G4SessionReference"] as string ?? string.Empty;
            if (string.IsNullOrEmpty(session))
            {
                throw new SemanticOperationException(403, "mapping_session_stale");
            }
            // 只解析当前固定端点登记的类型，禁止开放泛型请求入口。
            var body = requestType is null ? null : await ReadAsync(context, requestType, token);
            // 强ETag不接受多头或弱值，具体资源kind由应用层核对。
            var etag = context.Request.Headers.IfMatch.Count == 0 ? null : context.Request.Headers.IfMatch.Count == 1 ? context.Request.Headers.IfMatch[0] : string.Empty;
            // 路由ID均来自注册模板，仍由应用守卫校验形状和归属。
            var id = context.Request.RouteValues["id"] as string ?? string.Empty;
            // 服务解析保持scope，不用另一个HTTP endpoint模拟业务调用。
            var service = context.RequestServices.GetRequiredService<MappingApplicationService>();
            // 列表选择完整请求scope，不能静默裁剪成actor交集。
            var scope = new ResourceScope
            {
                OrganizationId = actor.OrganizationId,
                SiteIds = context.Request.Query["siteId"].Count == 0
                ? actor.SiteIds : context.Request.Query["siteId"].Select(value => value!).ToArray()
            };
            // 缺limit才用20，错误数字必须400而不是默认值。
            var limit = Number(context.Request.Query["limit"], false) ?? 20;
            if (limit > 50)
            {
                throw new SemanticOperationException(400, "mapping_payload_invalid");
            }
            // 生命周期单请求有界；七评估30秒加两个短平台事务，不无限等待。
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
            deadline.CancelAfter(TimeSpan.FromSeconds(45));
            token = deadline.Token;
            try
            {
                // 只返回登记公共模型，不把EF实体或内部会话证明序列化。
                object result = operation switch
                {
                    "create" => await service.CreateAsync(actor, session, (MappingDraftCreateRequest)body!, token),
                    "draft" => await service.ReadDraftAsync(actor, session, id, null, token),
                    "revision" => await service.ReadDraftAsync(actor, session, id, Number(context.Request.RouteValues["revision"]?.ToString(), true), token),
                    "patch" => await service.PatchAsync(actor, session, id, (MappingDraftPatchRequest)body!, etag, token),
                    "suggestions" => await service.SuggestionsAsync(actor, session, id, (MappingSuggestionRequest)body!, etag, token),
                    "validate" => await service.ValidateAsync(actor, session, id, (MappingValidateRequest)body!, etag, token),
                    "job" => await service.ReadJobAsync(actor, session, id, token),
                    "cancel-job" => await service.CancelJobAsync(actor, session, id, (MappingCommandRequest)body!, etag, token),
                    "assessment" => await service.ReadAssessmentAsync(actor, session, id, token),
                    "propose" => await service.ProposeAsync(actor, session, id, (MappingProposalCreateRequest)body!, token),
                    "proposal" => await service.ReadProposalAsync(actor, session, id, token),
                    "decide" => await service.DecideAsync(actor, session, id, (MappingDecisionRequest)body!, etag, token),
                    "cancel-proposal" => await service.CancelProposalAsync(actor, session, id, (MappingCommandRequest)body!, etag, token),
                    "activate" => await context.RequestServices.GetRequiredService<MappingActivationService>().ActivateAsync(actor, session, id, (MappingActivationRequest)body!, etag, token),
                    "check" => await context.RequestServices.GetRequiredService<MappingActivationService>().ReadCheckAsync(actor, session, id, token),
                    "release" => await service.ReadReleaseAsync(actor, session, id, token),
                    "active" => await service.ReadActiveAsync(actor, session, id, token),
                    "diff" => await service.DiffAsync(actor, session, id, Number(Query(context, "fromRevision"), true), Number(Query(context, "toRevision"), true), null, null, token),
                    "release-diff" => await service.DiffAsync(actor, session, id, null, null, Query(context, "fromReleaseId"), Query(context, "toReleaseId"), token),
                    "list" => await service.ListAsync<MappingListItem>(actor, session, scope, "mappings", null, Query(context, "status"), Query(context, "connectionId"), null, null, null, Query(context, "cursor"), (int)limit, token),
                    "proposals" => await service.ListAsync<MappingProposalView>(actor, session, scope, "proposals", Query(context, "mappingId"), Query(context, "status"), null, null, null, null, Query(context, "cursor"), (int)limit, token),
                    "releases" => await service.ListAsync<MappingReleaseView>(actor, session, scope, "releases", Query(context, "mappingId"), null, null, null, null, null, Query(context, "cursor"), (int)limit, token),
                    "assessments" => await service.ListAsync<MappingAssessmentView>(actor, session, scope, "assessments", id, null, null, Number(Query(context, "revision"), false), Query(context, "targetReleaseId"), null, Query(context, "cursor"), (int)limit, token),
                    "checks" => await service.ListAsync<MappingActivationCheck>(actor, session, scope, "checks", null, null, null, null, null, id, Query(context, "cursor"), (int)limit, token),
                    _ => throw new SemanticOperationException(400, "mapping_payload_invalid")
                };
                context.Response.Headers.ETag = result switch
                {
                    MappingDraftView draft => $"\"mapping:{draft.Revision}\"",
                    MappingJobView job => $"\"job:{job.Revision}\"",
                    MappingProposalView proposal => $"\"proposal:{proposal.ProposalRevision}\"",
                    _ => (string?)null
                };
                if (status is 201 or 202)
                {
                    context.Response.Headers.Location = result switch
                    {
                        MappingDraftView draft => "/api/v1/mappings/" + draft.MappingId,
                        MappingJobView job => "/api/v1/mapping-jobs/" + job.JobId,
                        MappingProposalView proposal => "/api/v1/mapping-proposals/" + proposal.ProposalId,
                        _ => (string?)null
                    };
                }
                // 抽象提案响应显式使用基类，以保留kind判别字段。
                return result is MappingProposalView proposalView
                    ? Results.Json<MappingProposalView>(proposalView, G4MappingJson.Options, statusCode: status)
                    : Results.Json(result, G4MappingJson.Options, statusCode: status);
            }
            catch (MappingActivationCheckException failure)
            {
                // checkId只在应用层已经核验当前权限后产生，不附源内容。
                return Results.Problem(statusCode: 409, title: "映射激活复核未通过。", extensions: new Dictionary<string, object?>
                {
                    ["code"] = failure.Code,
                    ["checkId"] = failure.CheckId,
                    ["traceId"] = context.TraceIdentifier,
                    ["correlationId"] = context.TraceIdentifier
                });
            }
            catch (OperationCanceledException) when (!context.RequestAborted.IsCancellationRequested)
            {
                throw new SemanticOperationException(503, "mapping_operation_timeout");
            }
            catch (Microsoft.EntityFrameworkCore.DbUpdateConcurrencyException)
            {
                throw new SemanticOperationException(409, "mapping_version_conflict");
            }
        }, requestType is not null);
    }

    /// <summary>正文以实际八位字节限长，拒绝重复键、额外字段与非法UTF8。</summary>
    private static async Task<object> ReadAsync(HttpContext context, Type type, CancellationToken token)
    {
        if (context.Request.ContentLength > G4MappingRules.MaximumBytes)
        {
            throw new SemanticOperationException(413, "mapping_payload_too_large");
        }
        try
        {
            // 多读一个字节作为超限哨兵，分块请求不能绕过。
            var bytes = new byte[G4MappingRules.MaximumBytes + 1];
            // 只累计实际读取数，不相信Content-Length。
            var count = 0;
            while (count < bytes.Length)
            {
                // 短读继续读取，只有零字节表示结束。
                var read = await context.Request.Body.ReadAsync(bytes.AsMemory(count), token);
                if (read == 0)
                {
                    break;
                }
                count += read;
            }
            if (count > G4MappingRules.MaximumBytes)
            {
                throw new SemanticOperationException(413, "mapping_payload_too_large");
            }
            // 严格UTF8拒绝无效序列，不能用替代字符改变原审批输入。
            var json = new UTF8Encoding(false, true).GetString(bytes, 0, count);
            // 重复键在反序列化前拒绝，保留null与缺字段差异。
            using var document = G4MappingRules.ReadDocument(json);
            return JsonSerializer.Deserialize(document.RootElement, type, G4MappingJson.Options)
                ?? throw new SemanticOperationException(400, "mapping_payload_invalid");
        }
        catch (Exception error) when (error is JsonException or DecoderFallbackException or InvalidOperationException or FormatException)
        {
            throw new SemanticOperationException(400, "mapping_payload_invalid");
        }
    }

    /// <summary>查询键禁止多值歧义，缺席与空字符串分开。</summary>
    private static string? Query(HttpContext context, string key)
    {
        // 只有siteId可以显式重复，其他查询字段必须单值。
        var values = context.Request.Query[key];
        if (values.Count > 1 || values.Count == 1 && string.IsNullOrWhiteSpace(values[0]))
        {
            throw new SemanticOperationException(400, "mapping_payload_invalid");
        }
        return values.Count == 0 ? null : values[0];
    }

    /// <summary>只接受安全正整数，不用解析失败时的默认值。</summary>
    private static long? Number(string? value, bool required)
    {
        if (string.IsNullOrEmpty(value) && !required)
        {
            return null;
        }
        if (!long.TryParse(value, NumberStyles.None, CultureInfo.InvariantCulture, out var number)
            || number is < 1 or > G4MappingRules.MaximumRevision || number.ToString(CultureInfo.InvariantCulture) != value)
        {
            throw new SemanticOperationException(400, "mapping_payload_invalid");
        }
        return number;
    }
}
