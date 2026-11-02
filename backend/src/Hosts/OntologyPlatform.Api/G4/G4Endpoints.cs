using System.Text.Json;
using OntologyPlatform.Api.G2;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.Api.G4;

/// <summary>只注册冻结的16个M1端点，复用既有真实认证与CSRF。</summary>
public static class G4Endpoints
{
    /// <summary>实际产品路由及OpenAPI共用同一映射，不另造Schema生成源。</summary>
    public static void MapG4Endpoints(this WebApplication app)
    {
        app.MapGet("/api/v1/connections", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "list", "connection.read", null))).Produces<ConnectionListPage>(200).WithTags("Connections").WithGroupName("g4");
        app.MapGet("/api/v1/connections/{id}", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "get", "connection.read", null))).Produces<ConnectionView>(200).WithTags("Connections").WithGroupName("g4");
        app.MapPost("/api/v1/connection-secrets", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "intake", "connection.secret.manage", typeof(ConnectionSecretIntakeRequest)))).Accepts<ConnectionSecretIntakeRequest>("application/json").Produces<SecretIntakeReceipt>(201).WithTags("Connections").WithGroupName("g4");
        app.MapPost("/api/v1/connections/tests", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "draft-test", "connection.test", typeof(ConnectionDraftProbeRequest)))).Accepts<ConnectionDraftProbeRequest>("application/json").Produces<ConnectionProbeView>(200).WithTags("Connections").WithGroupName("g4");
        app.MapPost("/api/v1/connections", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "create", "connection.manage", typeof(ConnectionCreateRequest)))).Accepts<ConnectionCreateRequest>("application/json").Produces<ConnectionView>(201).WithTags("Connections").WithGroupName("g4");
        app.MapPatch("/api/v1/connections/{id}", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "patch", "connection.manage", typeof(ConnectionPatchRequest)))).Accepts<ConnectionPatchRequest>("application/json").Produces<ConnectionView>(200).WithTags("Connections").WithGroupName("g4");
        app.MapPost("/api/v1/connections/{id}/rotate-secret", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "rotate", "connection.secret.manage", typeof(ConnectionRotateSecretRequest)))).Accepts<ConnectionRotateSecretRequest>("application/json").Produces<ConnectionView>(200).WithTags("Connections").WithGroupName("g4");
        app.MapPost("/api/v1/connections/{id}/test", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "test", "connection.test", typeof(ConnectionMutationCommand)))).Accepts<ConnectionMutationCommand>("application/json").Produces<ConnectionProbeView>(200).WithTags("Connections").WithGroupName("g4");
        app.MapGet("/api/v1/connections/{id}/probes/{probeId}", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "probe", "connection.read", null))).Produces<ConnectionProbeView>(200).WithTags("Connections").WithGroupName("g4");
        app.MapPost("/api/v1/connections/{id}/enable", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "enable", "connection.manage", typeof(ConnectionMutationCommand)))).Accepts<ConnectionMutationCommand>("application/json").Produces<ConnectionView>(200).WithTags("Connections").WithGroupName("g4");
        app.MapPost("/api/v1/connections/{id}/disable", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "disable", "connection.manage", typeof(ConnectionMutationCommand)))).Accepts<ConnectionMutationCommand>("application/json").Produces<ConnectionView>(200).WithTags("Connections").WithGroupName("g4");
        app.MapPost("/api/v1/connections/{id}/discoveries", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "discover", "schema.discover", typeof(ConnectionMutationCommand)))).Accepts<ConnectionMutationCommand>("application/json").Produces<CatalogDiscoveryJobView>(202).WithTags("Connections").WithGroupName("g4");
        app.MapGet("/api/v1/connections/{id}/discoveries/{jobId}", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "job", "schema.read", null))).Produces<CatalogDiscoveryJobView>(200).WithTags("Connections").WithGroupName("g4");
        app.MapPost("/api/v1/connections/{id}/discoveries/{jobId}/cancel", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "cancel", "schema.discover", typeof(ConnectionMutationCommand)))).Accepts<ConnectionMutationCommand>("application/json").Produces<CatalogDiscoveryJobView>(200).WithTags("Connections").WithGroupName("g4");
        app.MapGet("/api/v1/connections/{id}/catalogs", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "catalogs", "schema.read", null))).Produces<CatalogSnapshotListPage>(200).WithTags("Connections").WithGroupName("g4");
        app.MapGet("/api/v1/catalogs/{snapshotId}", (Func<HttpContext, Task<IResult>>)((HttpContext context) => ExecuteAsync(context, "catalog", "schema.read", null))).Produces<CatalogSnapshotView>(200).WithTags("Connections").WithGroupName("g4");
    }

    /// <summary>先可信身份/策略/CSRF，再严格正文和应用授权，错误只返回安全分类。</summary>
    private static Task<IResult> ExecuteAsync(HttpContext context, string operation, string policy, Type? requestType)
    {
        return G2EndpointGuard.TransportAsync(context, policy, async (actor, token) =>
        {
            if (context.Request.ContentLength is > 65536) throw new SemanticOperationException(413, "connection_profile_invalid");
            // 只有本路由登记的类型能被反序列化，禁止客户端指定类型。
            object? body = null;
            if (requestType is not null)
            {
                try
                {
                    // 多读一个字节用于判定超限；无长度头、分块和HTTP/2均在解析前限长。
                    var bytes = new byte[65537];
                    // 累计的是实际正文八位字节，不能相信客户端声明长度。
                    var count = 0;
                    while (count < bytes.Length)
                    {
                        // 每次只读取剩余预算，短读不能被误当正文结束。
                        var read = await context.Request.Body.ReadAsync(bytes.AsMemory(count), token);
                        if (read == 0) break;
                        count += read;
                    }
                    if (count > 65536) throw new SemanticOperationException(413, "connection_profile_invalid");
                    body = JsonSerializer.Deserialize(bytes.AsSpan(0, count), requestType, G4ConnectionJson.Options);
                    if (body is null) throw new JsonException();
                    G4ConnectionRules.Validate(body);
                }
                catch (JsonException)
                {
                    throw new SemanticOperationException(422, "connection_profile_invalid");
                }
            }
            // 会话引用由服务端票据加载设置，绝不从HTTP头或正文读取。
            var invocation = new ConnectionInvocation
            {
                Operation = operation,
                Actor = actor,
                Body = body,
                Id = context.Request.RouteValues["id"] as string,
                ChildId = context.Request.RouteValues["probeId"] as string ?? context.Request.RouteValues["jobId"] as string ?? context.Request.RouteValues["snapshotId"] as string,
                Etag = context.Request.Headers.IfMatch.Count == 0 ? null : context.Request.Headers.IfMatch.Count == 1 ? context.Request.Headers.IfMatch[0] : string.Empty,
                Cursor = context.Request.Query["cursor"],
                Type = context.Request.Query["type"],
                State = context.Request.Query["state"],
                SessionReference = context.Items["G4SessionReference"] as string ?? string.Empty
            };
            // 所有成功响应均等待应用事务提交，202仅表示持久任务受理。
            var reply = await context.RequestServices.GetRequiredService<IConnectionRequestHandler>().HandleAsync(invocation, token);
            if (reply.Etag is not null) context.Response.Headers.ETag = reply.Etag;
            return Results.Json(reply.Value, G4ConnectionJson.Options, statusCode: reply.StatusCode);
        }, requestType is not null);
    }
}
