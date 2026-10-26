using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Authorization.Policy;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Api.G2;

/// <summary>在最小API正文绑定之前输出统一授权错误，并先持久保存真实拒绝审计。</summary>
public sealed class G2AuthorizationResultHandler : IAuthorizationMiddlewareResultHandler
{
    /// <summary>允许结果继续原生管道，挑战输出安全401，禁止结果提交审计后才输出403。</summary>
    /// <param name="next">后续正文绑定与业务端点管道。</param>
    /// <param name="context">已经过G1身份验证的服务器请求。</param>
    /// <param name="policy">端点指定的共同具名授权策略。</param>
    /// <param name="authorizeResult">原生策略评估结果，不读取客户端身份声明。</param>
    /// <returns>结果处理或后续管道任务；取消与依赖异常继续传播给宿主。</returns>
    public async Task HandleAsync(RequestDelegate next, HttpContext context, AuthorizationPolicy policy, PolicyAuthorizationResult authorizeResult)
    {
        context.RequestAborted.ThrowIfCancellationRequested();
        context.Response.Headers.CacheControl = "no-store";
        if (authorizeResult.Succeeded)
        {
            await next(context);
            return;
        }
        if (authorizeResult.Challenged)
        {
            await PlatformProblem.Create(context, 401, "authentication_required").ExecuteAsync(context);
            return;
        }
        if (!authorizeResult.Forbidden)
        {
            throw new InvalidOperationException("授权中间件返回未登记结果。");
        }
        // 使用与端点guard相同的可信主体投影，完整范围不从请求正文或路由参数推测。
        var actor = G2Authorization.CreateActor(context);
        await context.RequestServices.GetRequiredService<IAuditTrail>().WriteAsync(actor, new AuditCommand
        {
            Action = "authorization.denied",
            Resource = "g2.api",
            Outcome = "denied",
            Scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = actor.SiteIds }
        }, context.RequestAborted);
        // 审计尚未提交或失败时不能提前启动403响应；异常由既有宿主安全边界处理。
        await PlatformProblem.Create(context, 403, "authorization_denied").ExecuteAsync(context);
    }
}
