using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Http.Features;
using Microsoft.Extensions.Options;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Api.G2;

/// <summary>长连接逐轮通过同一PG票据存储复验撤销和绝对过期，不调用请求缓存认证。</summary>
public static class G2StreamSession
{
    /// <summary>与官方ASP.NET Core v10 CookieAuthenticationHandler固定内部引用claim一致。</summary>
    private const string SessionClaim = "Microsoft.AspNetCore.Authentication.Cookies-SessionId";

    /// <summary>按官方CookieManager/TicketDataFormat路径解密引用，真实重新读取PG并更新当前Principal。</summary>
    public static async Task<ActorContext> RefreshAsync(HttpContext context)
    {
        // 选项来自原认证scheme，不能另建会话或自行解释浏览器身份字段。
        var options = context.RequestServices.GetRequiredService<IOptionsMonitor<CookieAuthenticationOptions>>().Get(CookieAuthenticationDefaults.AuthenticationScheme);
        // 浏览器Cookie仅为受保护随机引用，永远不写日志、事件或Schema。
        var cookie = options.CookieManager.GetRequestCookie(context, options.Cookie.Name!);
        if (string.IsNullOrEmpty(cookie) || options.SessionStore is not PostgresTicketStore store) throw new SemanticOperationException(401, "authentication_required");
        // 与官方v10源完全相同的TLS绑定目的，普通Kestrel无绑定时为null。
        var binding = context.Features.Get<ITlsTokenBindingFeature>()?.GetProvidedTokenBindingId();
        // 只恢复受保护引用票据，不把它当实际授权票据。
        var reference = options.TicketDataFormat.Unprotect(cookie, binding is null ? null : Convert.ToBase64String(binding));
        // SessionIdClaim来源已核实官方v10 CookieAuthenticationHandler.cs第22及135至178行。
        var key = reference?.Principal.FindFirst(SessionClaim)?.Value;
        if (string.IsNullOrEmpty(key)) throw new SemanticOperationException(401, "authentication_required");
        // 此方法每次直接查询PG撤销与绝对期限，没有AuthenticateAsync请求缓存。
        var ticket = await store.RetrieveAsync(key);
        if (ticket?.Principal.Identity?.IsAuthenticated != true || ticket.Properties.ExpiresUtc is null
            || ticket.Properties.ExpiresUtc <= context.RequestServices.GetRequiredService<TimeProvider>().GetUtcNow()) throw new SemanticOperationException(401, "authentication_required");
        context.User = ticket.Principal;
        return G2Authorization.CreateActor(context);
    }
}
