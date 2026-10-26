using System.Net.ServerSentEvents;
using System.Runtime.CompilerServices;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Agents;

namespace OntologyPlatform.Api.G2;

/// <summary>持久Run的薄REST与原生SSE适配，业务与版本真相位于模块PG。</summary>
public static class ExecutionEndpoints
{
    /// <summary>统一原生授权中间件在JSON绑定之前拒绝未认证请求。</summary>
    public static void MapExecutionEndpoints(this IEndpointRouteBuilder endpoints)
    {
        // 全组共享原生认证策略，具体owner/scope仍由每个应用用例检查。
        var group = endpoints.MapGroup("/api/v1/execution-runs").RequireAuthorization("semantic.read");
        group.MapGet("", (HttpContext context, ExecutionRunService service) => G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => service.ListAsync(actor, token)));
        group.MapGet("/{id}", (HttpContext context, string id, ExecutionRunService service) => G2EndpointGuard.ReadAsync(context, "semantic.read", (actor, token) => service.ReadAsync(actor, id, token)));
        group.MapPost("", (HttpContext context, CreateRunRequest request, ExecutionRunService service) => G2EndpointGuard.WriteAsync(context, "semantic.read", request.Command, (actor, token) => service.CreateAsync(actor, request, token)));
        group.MapPost("/{id}/cancel", (HttpContext context, string id, CancelRunRequest request, ExecutionRunService service) => G2EndpointGuard.WriteAsync(context, "semantic.read", request.Command, (actor, token) => service.CancelAsync(actor, id, request, token), requiresRevision: true));
        group.MapGet("/{id}/events", (HttpContext context, string id, ExecutionRunService service) => G2EndpointGuard.TransportAsync(context, "semantic.read", async (actor, token) =>
        {
            // 初始授权及游标错误必须在发送任何SSE头之前形成准确HTTP状态。
            actor = await G2StreamSession.RefreshAsync(context);
            if (context.Request.Headers["Last-Event-ID"].Count > 1) throw new SemanticOperationException(400, "cursor_invalid");
            // 解析固定Run的规范游标，PG再次判断是否超前。
            var cursor = ExecutionRunService.ParseCursor(id, context.Request.Headers["Last-Event-ID"].FirstOrDefault());
            await service.EventsAsync(actor, id, cursor, token);
            await context.RequestServices.GetRequiredService<IAuditTrail>().WriteAsync(actor, new AuditCommand { Action = "execution.events.read", Resource = id, Outcome = "allowed", Scope = (await service.ReadAsync(actor, id, token)).Scope }, token);
            context.Response.Headers["X-Accel-Buffering"] = "no";
            return TypedResults.ServerSentEvents(StreamAsync(context, service, id, cursor, token));
        }, validateCsrf: false));
    }

    /// <summary>每批真实复验会话与完整scope，读PG分页无订阅丢窗；断流只取消枚举。</summary>
    private static async IAsyncEnumerable<SseItem<ExecutionEvent>> StreamAsync(HttpContext context, ExecutionRunService service, string id, long cursor, [EnumeratorCancellation] CancellationToken token)
    {
        // 每条连接最多25秒，后续可用最后已收到的eventId继续重放。
        using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(token);
        lifetime.CancelAfter(TimeSpan.FromSeconds(25));
        while (!lifetime.IsCancellationRequested)
        {
            // 仅本批快照事件，数组最多16项，发送时不持有数据库事务。
            ExecutionEvent[] events;
            // 终态在该批次之后决定关闭，最后一批必须发完。
            ExecutionRun run;
            try
            {
                // 每轮取实际PG票据，撤销后不沿用旧Principal。
                var actor = await G2StreamSession.RefreshAsync(context);
                events = await service.EventsAsync(actor, id, cursor, lifetime.Token);
                run = await service.ReadAsync(actor, id, lifetime.Token);
            }
            catch (Exception failure) when (failure is SemanticOperationException or OperationCanceledException)
            {
                yield break;
            }
            foreach (var value in events)
            {
                if (lifetime.IsCancellationRequested) yield break;
                cursor = value.Seq;
                yield return new SseItem<ExecutionEvent>(value, value.EventType) { EventId = value.EventId };
            }
            if (cursor >= run.LastSeq && run.Status is ExecutionStatus.Completed or ExecutionStatus.Failed or ExecutionStatus.Cancelled) yield break;
            try { await Task.Delay(TimeSpan.FromMilliseconds(200), lifetime.Token); }
            catch (OperationCanceledException) { yield break; }
        }
    }
}
