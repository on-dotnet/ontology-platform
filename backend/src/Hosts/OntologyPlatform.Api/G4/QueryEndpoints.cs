using OntologyPlatform.Api.G2;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Api.G4;

/// <summary>G4查询只适配原生HTTP传输，实际授权与执行均复用同一个SemanticGateway。</summary>
public static class QueryEndpoints
{
    /// <summary>执行入口必需的幂等请求头，供运行解析与正式文档共用。</summary>
    internal const string IdempotencyHeader = "Idempotency-Key";

    /// <summary>候选选择时关联原查询的可选请求头。</summary>
    internal const string SelectionHeader = "X-Selection-Query-Id";

    /// <summary>执行、状态、恢复及取消从同一路由声明导出正式DTO。</summary>
    public static void MapQueryEndpoints(this WebApplication app)
    {
        app.MapPost("/api/v1/data/semantic-queries", (Func<HttpContext, Task<IResult>>)ExecuteAsync)
            .Accepts<G4SemanticQuery>("application/json").Produces<G4QueryResultV1>(200).Produces<G4QueryView>(202)
            .WithTags("Semantic queries").WithGroupName("g4");
        app.MapGet("/api/v1/data/semantic-queries/{queryId}", (Func<HttpContext, Task<IResult>>)(context => ReadAsync(context, false)))
            .Produces<G4QueryView>(200).WithTags("Semantic queries").WithGroupName("g4");
        app.MapGet("/api/v1/data/semantic-queries/{queryId}/result", (Func<HttpContext, Task<IResult>>)(context => ReadAsync(context, true)))
            .Produces<G4QueryResultV1>(200).Produces<G4QueryView>(202).WithTags("Semantic queries").WithGroupName("g4");
        app.MapPost("/api/v1/data/semantic-queries/{queryId}/cancel", (Func<HttpContext, Task<IResult>>)CancelAsync)
            .Produces<G4QueryView>(200).WithTags("Semantic queries").WithGroupName("g4");
        app.MapGet("/api/v1/data/source-evidence/{id}", (Func<HttpContext, Task<IResult>>)EvidenceAsync)
            .Produces<G4SourceEvidenceView>(200).WithTags("Semantic queries").WithGroupName("g4");
    }

    /// <summary>先身份与CSRF，再有界严格JSON；不把客户端header当作会话引用。</summary>
    private static Task<IResult> ExecuteAsync(HttpContext context) => G2EndpointGuard.TransportAsync(context, "data.query.execute", async (actor, token) =>
    {
        // 读取额外一字节用于证明超界，而不是截断后执行一个不同请求。
        var bytes = new byte[65537];
        // 只接受JSON媒体类型，不隐式解码其他传输格式。
        if (!context.Request.HasJsonContentType()) throw new SemanticOperationException(400, "query_payload_invalid");
        // HTTP流可以没有Content-Length，实际读取长度仍强制受控。
        var count = 0;
        while (count < bytes.Length)
        {
            // 每次读取继续传播当前请求取消。
            var read = await context.Request.Body.ReadAsync(bytes.AsMemory(count), token);
            if (read == 0) break;
            count += read;
        }
        if (count > 65536) throw new SemanticOperationException(413, "query_payload_too_large");
        // 选择上下文进入幂等hash，不拼进body或隐藏在用户身份中。
        var selection = Header(context, SelectionHeader, false);
        // 原始字节先拒绝重复键、未知字段及非法UTF8，再生成正式类型。
        var query = G4QueryRules.ReadQuery(bytes[..count], selection);
        // 网关是REST、MCP和Run共享的唯一正式执行边界。
        var delivery = await context.RequestServices.GetRequiredService<ISemanticGateway>().ExecuteG4Async(actor,
            Session(context), query, Header(context, IdempotencyHeader, true)!, selection, token);
        return Delivery(context, delivery, true);
    }, true);

    /// <summary>恢复只传查询ID，不接受客户端传回旧结果或授权证明。</summary>
    private static Task<IResult> ReadAsync(HttpContext context, bool includeResult) => G2EndpointGuard.TransportAsync(context, "data.query.result.read", async (actor, token) =>
    {
        // ID来自路由；未知与异主体由应用层一致返回404。
        var id = context.Request.RouteValues["queryId"]?.ToString() ?? string.Empty;
        // 相同当前授权边界决定返回七字段执行状态或原规范结果。
        var delivery = await context.RequestServices.GetRequiredService<ISemanticGateway>().ReadG4Async(actor, Session(context), id, includeResult, token);
        return Delivery(context, delivery, includeResult);
    }, false);

    /// <summary>取消复用防伪及当前权限，禁止任何隐藏命令body。</summary>
    private static Task<IResult> CancelAsync(HttpContext context) => G2EndpointGuard.TransportAsync(context, "data.query.execute", async (actor, token) =>
    {
        // 无body协议必须检查实际流，不能信任缺席的Content-Length。
        var probe = new byte[1];
        if (await context.Request.Body.ReadAsync(probe, token) != 0) throw new SemanticOperationException(400, "query_payload_invalid");
        // 只取当前路由的本人queryId，不允许跨主体传actor。
        var id = context.Request.RouteValues["queryId"]?.ToString() ?? string.Empty;
        // 成功状态已经与取消审计同事务提交。
        var view = await context.RequestServices.GetRequiredService<ISemanticGateway>().CancelG4Async(actor, Session(context), id, token);
        return Results.Json(view, G4QueryJson.Options);
    }, true);

    /// <summary>证据打开额外要求来源读取许可，不让UI把结果读取许可升级成证据许可。</summary>
    private static Task<IResult> EvidenceAsync(HttpContext context) => G2EndpointGuard.TransportAsync(context, "data.query.evidence.read", async (actor, token) =>
    {
        // 只使用服务器证据ID，应用层重新找到本人原查询和回执。
        var id = context.Request.RouteValues["id"]?.ToString() ?? string.Empty;
        // 响应类型是封闭安全视图，不含内部Binding或源配置。
        var evidence = await context.RequestServices.GetRequiredService<ISemanticGateway>().ReadG4EvidenceAsync(actor, Session(context), id, token);
        return Results.Json(evidence, G4QueryJson.Options);
    }, false);

    /// <summary>响应原规范字节，不再次经过宽松Web序列化；状态响应与业务六态互斥。</summary>
    private static IResult Delivery(HttpContext context, G4QueryDelivery delivery, bool includeResult)
    {
        context.Response.Headers.CacheControl = "no-store";
        context.Response.Headers.Location = "/api/v1/data/semantic-queries/" + Uri.EscapeDataString(delivery.View.QueryId);
        context.Response.Headers["X-Query-Id"] = delivery.View.QueryId;
        return includeResult && delivery.ResultBytes is not null ? Results.Bytes(delivery.ResultBytes, "application/json")
            : Results.Json(delivery.View, G4QueryJson.Options, statusCode: includeResult && delivery.View.ExecutionStatus == "RUNNING" ? 202 : 200);
    }

    /// <summary>头部只接受单一原始值，禁止逗号拼接或多值身份。</summary>
    private static string? Header(HttpContext context, string name, bool required)
    {
        // StringValues的单值判别避免ToString默默拼接多个header。
        var values = context.Request.Headers[name];
        if (values.Count == 0 && !required) return null;
        if (values.Count != 1 || string.IsNullOrWhiteSpace(values[0])) throw new SemanticOperationException(400, "query_header_invalid");
        return values[0];
    }

    /// <summary>服务器票据中间件的内部引用是唯一会话来源。</summary>
    private static string Session(HttpContext context) => context.Items["G4SessionReference"] as string
        ?? throw new SemanticOperationException(403, "query_forbidden");
}
