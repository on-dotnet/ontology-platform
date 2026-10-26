using System.Globalization;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Authorization;
using Microsoft.Extensions.Options;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Api.G2;

/// <summary>在业务调用之前执行共同HTTP边界，不替代模块资源授权及事务提交。</summary>
public static class G2EndpointGuard
{
    /// <summary>执行可信身份与具名角色检查后调用只读应用用例。</summary>
    /// <typeparam name="T">唯一合同定义的响应类型。</typeparam>
    /// <param name="context">原生请求上下文。</param>
    /// <param name="policy">服务器固定的具名策略。</param>
    /// <param name="operation">执行资源授权和业务读取的用例。</param>
    /// <returns>业务响应或安全Problem。</returns>
    public static Task<IResult> ReadAsync<T>(HttpContext context, string policy, Func<ActorContext, CancellationToken, Task<T>> operation)
    {
        return ExecuteAsync(context, policy, null, operation, false, false);
    }

    /// <summary>在原生防伪、来源及命令前置条件通过后才调用事务业务用例。</summary>
    /// <typeparam name="T">唯一合同定义的响应类型。</typeparam>
    /// <param name="context">原生请求上下文。</param>
    /// <param name="policy">服务器固定的具名策略。</param>
    /// <param name="command">严格绑定后的命令上下文。</param>
    /// <param name="operation">完成资源授权与原子提交的业务用例。</param>
    /// <param name="requiresRevision">是否要求强If-Match与命令修订一致。</param>
    /// <returns>提交完成后的业务响应或安全Problem。</returns>
    public static Task<IResult> WriteAsync<T>(HttpContext context, string policy, CommandContext command, Func<ActorContext, CancellationToken, Task<T>> operation, bool requiresRevision = false)
    {
        return ExecuteAsync(context, policy, command, operation, true, requiresRevision);
    }

    /// <summary>为原生MCP与SSE复用身份、角色和可选POST防伪，标准传输不伪造业务CommandContext。</summary>
    /// <param name="context">已认证宿主请求上下文。</param>
    /// <param name="policy">同一具名策略。</param>
    /// <param name="operation">返回原生传输结果的适配委托。</param>
    /// <param name="validateCsrf">MCP的POST/DELETE为真，SSE的GET为假。</param>
    /// <returns>保留原生媒体类型与状态的结果。</returns>
    public static Task<IResult> TransportAsync(HttpContext context, string policy, Func<ActorContext, CancellationToken, Task<IResult>> operation, bool validateCsrf)
    {
        return ExecuteAsync(context, policy, null, operation, validateCsrf, false, requiresCommand: false);
    }

    /// <summary>按身份、角色、来源、防伪、修订的顺序失败关闭，再映射受控业务结果。</summary>
    /// <typeparam name="T">应用响应类型。</typeparam>
    /// <param name="context">当前请求。</param>
    /// <param name="policy">固定策略。</param>
    /// <param name="command">写命令；读请求为空。</param>
    /// <param name="operation">业务委托。</param>
    /// <param name="write">是否为写边界。</param>
    /// <param name="requiresRevision">是否要求强修订条件。</param>
    /// <param name="requiresCommand">业务写入必须具备命令，标准只读传输仅复用身份和防伪。</param>
    /// <returns>未提前发送的最终响应。</returns>
    private static async Task<IResult> ExecuteAsync<T>(HttpContext context, string policy, CommandContext? command, Func<ActorContext, CancellationToken, Task<T>> operation, bool write, bool requiresRevision, bool requiresCommand = true)
    {
        context.Response.Headers.CacheControl = "no-store";
        context.RequestAborted.ThrowIfCancellationRequested();
        if (context.User.Identity?.IsAuthenticated != true)
        {
            return PlatformProblem.Create(context, 401, "authentication_required");
        }
        // 主体仅来自现有认证中间件投影；所有业务委托共享同一不可变值。
        var actor = G2Authorization.CreateActor(context);
        // 原生策略服务保证HTTP与其他传输使用相同策略语义。
        var authorization = context.RequestServices.GetRequiredService<IAuthorizationService>();
        if (!(await authorization.AuthorizeAsync(context.User, null, policy)).Succeeded
            || string.IsNullOrWhiteSpace(actor.SubjectId) || string.IsNullOrWhiteSpace(actor.OrganizationId))
        {
            return await DenyAsync(context, actor, "authorization.denied", "authorization_denied");
        }
        if (write)
        {
            if (!HasValidOrigin(context))
            {
                return await DenyAsync(context, actor, "csrf.denied", "origin_rejected");
            }
            try
            {
                await context.RequestServices.GetRequiredService<IAntiforgery>().ValidateRequestAsync(context);
            }
            catch (AntiforgeryValidationException)
            {
                return await DenyAsync(context, actor, "csrf.denied", "csrf_rejected");
            }
            if (requiresCommand && (command is null || !HasLength(command.CommandId, 64) || !HasLength(command.IdempotencyKey, 64)
                || !HasLength(command.Reason, 500) || command.ExpectedRevision < 0))
            {
                return PlatformProblem.Create(context, 400, "invalid_command");
            }
            if (requiresRevision)
            {
                // 多值、弱ETag和通配符不具有本切片所需的精确修订语义。
                var header = context.Request.Headers.IfMatch;
                if (header.Count == 0)
                {
                    return PlatformProblem.Create(context, 428, "revision_required");
                }
                if (header.Count != 1 || !TryRevision(header[0], out var revision))
                {
                    return PlatformProblem.Create(context, 400, "invalid_revision");
                }
                if (revision != command!.ExpectedRevision)
                {
                    return PlatformProblem.Create(context, 409, "revision_conflict");
                }
            }
        }
        try
        {
            // 只在业务委托完成事务提交后构造成功响应，绝不先写200或假审计标识。
            var result = await operation(actor, context.RequestAborted);
            if (result is OntologyDraft draft && TryRevision(draft.Etag, out var returnedRevision) && returnedRevision == draft.Revision)
            {
                context.Response.Headers.ETag = draft.Etag;
            }
            return result is IResult native ? native : Results.Ok(result);
        }
        catch (SemanticOperationException failure)
        {
            // 机器码只能输出有限安全字符；状态白名单与通用正文不包含异常或用户原文。
            var status = failure.Status is 400 or 401 or 403 or 404 or 409 or 410 or 413 or 422 or 428 or 429 or 503 ? failure.Status : 500;
            // 模块登记的固定机器码由调用方提供，异常Message永远不出现在响应。
            var code = status != 500 && HasLength(failure.Code, 64) && failure.Code.All(value => char.IsAsciiLetterLower(value) || char.IsAsciiDigit(value) || value == '_')
                ? failure.Code : "semantic_operation_failed";
            if (status == 403)
            {
                return await DenyAsync(context, actor, "authorization.denied", code);
            }
            return PlatformProblem.Create(context, status, code);
        }
    }

    /// <summary>来源若存在必须是配置的单一HTTP源，不允许路径、凭据或拼接值。</summary>
    /// <param name="context">当前写请求。</param>
    /// <returns>无Origin或精确同源时为真。</returns>
    private static bool HasValidOrigin(HttpContext context)
    {
        // 缺少Origin仍必须通过原生防伪，不能成为防伪旁路。
        var supplied = context.Request.Headers.Origin;
        if (supplied.Count == 0)
        {
            return true;
        }
        // PublicOrigin来自启动验证过的宿主配置，不读取Forwarded或客户端Host。
        var expected = context.RequestServices.GetRequiredService<IOptions<PlatformSecurityOptions>>().Value.PublicOrigin;
        return supplied.Count == 1 && Uri.TryCreate(supplied[0], UriKind.Absolute, out var origin)
            && origin.Scheme is "http" or "https" && string.IsNullOrEmpty(origin.UserInfo)
            && string.Equals(supplied[0], origin.GetLeftPart(UriPartial.Authority), StringComparison.Ordinal)
            && string.Equals(supplied[0], expected, StringComparison.Ordinal);
    }

    /// <summary>检查必填命令文本的实际字符边界，不向错误响应回显其内容。</summary>
    /// <param name="value">命令字段。</param>
    /// <param name="maximum">批准的最大长度。</param>
    /// <returns>非空白且长度有效时为真。</returns>
    private static bool HasLength(string? value, int maximum) => !string.IsNullOrWhiteSpace(value) && value.Length <= maximum;

    /// <summary>只接受带双引号的规范非负十进制强ETag。</summary>
    /// <param name="value">原始ETag。</param>
    /// <param name="revision">解析出的非负修订。</param>
    /// <returns>严格符合冻结格式时为真。</returns>
    private static bool TryRevision(string? value, out long revision)
    {
        revision = 0;
        return value is { Length: >= 3 } && value[0] == '"' && value[^1] == '"'
            && long.TryParse(value.AsSpan(1, value.Length - 2), NumberStyles.None, CultureInfo.InvariantCulture, out revision)
            && revision >= 0 && value == "\"" + revision.ToString(CultureInfo.InvariantCulture) + "\"";
    }

    /// <summary>拒绝事实持久成功后才返回403，不把审计失败伪装成安全成功。</summary>
    /// <param name="context">当前请求。</param>
    /// <param name="actor">可信完整主体范围。</param>
    /// <param name="action">固定拒绝事件。</param>
    /// <param name="code">固定公开错误码。</param>
    /// <returns>真实拒绝响应；审计依赖失败交宿主处理。</returns>
    private static async Task<IResult> DenyAsync(HttpContext context, ActorContext actor, string action, string code)
    {
        await context.RequestServices.GetRequiredService<IAuditTrail>().WriteAsync(actor, new AuditCommand
        {
            Action = action,
            Resource = "g2.api",
            Outcome = "denied",
            Scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = actor.SiteIds }
        }, context.RequestAborted);
        return PlatformProblem.Create(context, 403, code);
    }
}
