using Microsoft.AspNetCore.Authorization;
using ModelContextProtocol.AspNetCore;
using ModelContextProtocol.Protocol;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Agents;

namespace OntologyPlatform.Api.G2;

/// <summary>真实SDK Streamable HTTP入口；原生传输保留，身份和防伪统一复用。</summary>
public static class McpEndpoints
{
    /// <summary>注册显式工具处理器，不扫描程序集或接受模型提供的身份。</summary>
    public static IServiceCollection AddSemanticMcpEndpoints(this IServiceCollection services)
    {
        services.AddHttpContextAccessor();
        services.AddScoped<SemanticMcpTools>();
        services.AddMcpServer().WithHttpTransport(options => options.SessionMode = HttpServerSessionMode.Stateless)
            .WithListToolsHandler((request, token) =>
            {
                // 当前HTTP请求已通过统一Guard，服务从请求scope取得。
                var context = request.Services!.GetRequiredService<IHttpContextAccessor>().HttpContext ?? throw new InvalidOperationException("缺少受保护HTTP上下文。");
                return ValueTask.FromResult(new ListToolsResult { Tools = context.RequestServices.GetRequiredService<SemanticMcpTools>().List() });
            })
            .WithCallToolHandler(async (request, token) =>
            {
                // 每一次工具调用读取当前请求，而不是initialize时缓存的主体。
                var context = request.Services!.GetRequiredService<IHttpContextAccessor>().HttpContext ?? throw new InvalidOperationException("缺少受保护HTTP上下文。");
                // 服务器认证Principal经唯一投影产生actor，不读取arguments里的身份。
                var actor = G2Authorization.CreateActor(context);
                if (!(await context.RequestServices.GetRequiredService<IAuthorizationService>().AuthorizeAsync(context.User, null, "semantic.read")).Succeeded)
                    throw new SemanticOperationException(403, "authorization_denied");
                return await context.RequestServices.GetRequiredService<SemanticMcpTools>().CallAsync(actor, request.Params!.Name, request.Params.Arguments, token);
            });
        return services;
    }

    /// <summary>在SDK请求委托之前执行同源、防伪及授权，保持SDK原生响应媒体类型。</summary>
    public static void MapMcpEndpoints(this IEndpointRouteBuilder endpoints)
    {
        // SDK自己处理initialize/list/call及Streamable HTTP协商。
        var route = endpoints.MapMcp("/api/v1/mcp").RequireAuthorization("semantic.read");
        route.Add(builder =>
        {
            // 包装原生传输而不使用Results.Ok破坏流或JSON-RPC响应。
            var original = builder.RequestDelegate!;
            builder.RequestDelegate = context => InvokeAsync(context, original);
        });
    }

    /// <summary>先完成安全检查再运行原生传输，非泛型Task避免结果被路由丢弃。</summary>
    private static async Task InvokeAsync(HttpContext context, RequestDelegate original)
    {
        // POST及DELETE使用真实Antiforgery；GET只读流不伪造Command。
        var result = await G2EndpointGuard.TransportAsync(context, "semantic.read", (_, _) => Task.FromResult<IResult>(new NativeTransportResult(original)),
            HttpMethods.IsPost(context.Request.Method) || HttpMethods.IsDelete(context.Request.Method));
        await result.ExecuteAsync(context);
    }

    /// <summary>透明保留SDK的HTTP/SSE写入协议。</summary>
    private sealed class NativeTransportResult : IResult
    {
        /// <summary>SDK生成的实际路由委托。</summary>
        private readonly RequestDelegate transport;

        /// <summary>固定实际传输，不改变响应Schema。</summary>
        internal NativeTransportResult(RequestDelegate transport) => this.transport = transport;

        /// <summary>通过安全边界后才允许SDK发送响应。</summary>
        public Task ExecuteAsync(HttpContext httpContext) => transport(httpContext);
    }
}
