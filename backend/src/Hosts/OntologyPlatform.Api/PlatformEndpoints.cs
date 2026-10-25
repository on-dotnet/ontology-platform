using System.Diagnostics;
using System.Globalization;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authentication.OpenIdConnect;
using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Api.Contracts;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Modules.Governance;
using PlatformError = OntologyPlatform.Api.Contracts.PlatformProblem;

namespace OntologyPlatform.Api;

/// <summary>映射冻结的BFF身份、合成资源、审计及受保护技术探针。</summary>
public static class PlatformEndpoints
{
    /// <summary>注册正式API路由，所有数据访问由服务器实施身份及范围检查。</summary>
    /// <param name="app">已配置安全中间件的宿主。</param>
    /// <param name="security">已验证安全配置。</param>
    public static void MapPlatformEndpoints(this WebApplication app, PlatformSecurityOptions security)
    {
        app.MapGet("/auth/login", (HttpContext context, string? returnUrl) =>
        {
            // 跳转目的地只允许本站路径，OIDC外部回调另外由固定配置产生。
            var destination = returnUrl ?? "/";
            return SecurityBoundary.IsLocalReturnUrl(destination)
                ? Results.Challenge(new AuthenticationProperties { RedirectUri = destination }, [OpenIdConnectDefaults.AuthenticationScheme])
                : PlatformProblem.Create(context, 400, "invalid_request");
        }).Produces(302)
            .Produces<PlatformError>(400, contentType: "application/problem+json")
            .Produces<PlatformError>(500, contentType: "application/problem+json");
        app.MapGet("/auth/csrf", (HttpContext context, IAntiforgery antiforgery) =>
        {
            context.Response.Headers.CacheControl = "no-store";
            return Results.Ok(new CsrfResponse { RequestToken = antiforgery.GetAndStoreTokens(context).RequestToken! });
        }).Produces<CsrfResponse>()
            .Produces<PlatformError>(500, contentType: "application/problem+json");
        app.MapPost("/auth/logout", LogoutAsync)
            .Produces(302)
            .Produces<PlatformError>(401, contentType: "application/problem+json")
            .Produces<PlatformError>(403, contentType: "application/problem+json")
            .Produces<PlatformError>(500, contentType: "application/problem+json");
        app.MapGet("/signin-oidc", (HttpContext context) => PlatformProblem.Create(context, 400, "oidc_callback_invalid"))
            .Produces<PlatformError>(400, contentType: "application/problem+json")
            .Produces<PlatformError>(500, contentType: "application/problem+json");
        app.MapGet("/api/v1/platform/me", (HttpContext context) =>
            context.User.Identity?.IsAuthenticated == true
                ? Results.Ok(ToIdentity(context.User))
                : PlatformProblem.Create(context, 401, "unauthenticated"))
            .Produces<PlatformIdentity>()
            .Produces<PlatformError>(401, contentType: "application/problem+json")
            .Produces<PlatformError>(403, contentType: "application/problem+json")
            .Produces<PlatformError>(503, contentType: "application/problem+json")
            .Produces<PlatformError>(500, contentType: "application/problem+json");
        app.MapGet("/api/v1/platform/resources", ReadResourcesAsync)
            .Produces<PlatformResourceList>()
            .Produces<PlatformError>(401, contentType: "application/problem+json")
            .Produces<PlatformError>(403, contentType: "application/problem+json")
            .Produces<PlatformError>(503, contentType: "application/problem+json")
            .Produces<PlatformError>(500, contentType: "application/problem+json");
        app.MapGet("/api/v1/platform/resources/{id}", ReadResourceAsync)
            .Produces<PlatformResource>()
            .Produces<PlatformError>(401, contentType: "application/problem+json")
            .Produces<PlatformError>(403, contentType: "application/problem+json")
            .Produces<PlatformError>(404, contentType: "application/problem+json")
            .Produces<PlatformError>(503, contentType: "application/problem+json")
            .Produces<PlatformError>(500, contentType: "application/problem+json");
        app.MapGet("/api/v1/platform/audit", ReadAuditAsync)
            .Produces<PlatformAuditEntry[]>()
            .Produces<PlatformError>(400, contentType: "application/problem+json")
            .Produces<PlatformError>(401, contentType: "application/problem+json")
            .Produces<PlatformError>(403, contentType: "application/problem+json")
            .Produces<PlatformError>(503, contentType: "application/problem+json")
            .Produces<PlatformError>(500, contentType: "application/problem+json");
        app.MapGet("/health/live", (HttpContext context) => HasHealthKey(context, security)
            ? Results.Ok(new { status = "Healthy" }) : PlatformProblem.Create(context, 401, "unauthenticated"))
            .Produces(200)
            .Produces<PlatformError>(401, contentType: "application/problem+json")
            .Produces<PlatformError>(500, contentType: "application/problem+json");
        app.MapGet("/health/ready", async (HttpContext context, GovernanceDbContext database) =>
        {
            if (!HasHealthKey(context, security))
            {
                return PlatformProblem.Create(context, 401, "unauthenticated");
            }
            // 真实查询三张模块表，缺迁移或PG断开不能冒充就绪。
            await database.Sessions.AsNoTracking().Take(1).ToArrayAsync(context.RequestAborted);
            await database.AuditRecords.AsNoTracking().Take(1).ToArrayAsync(context.RequestAborted);
            await database.Resources.AsNoTracking().Take(1).ToArrayAsync(context.RequestAborted);
            return Results.Ok(new { status = "Healthy" });
        }).Produces(200)
            .Produces<PlatformError>(401, contentType: "application/problem+json")
            .Produces<PlatformError>(503, contentType: "application/problem+json")
            .Produces<PlatformError>(500, contentType: "application/problem+json");
    }

    /// <summary>校验认证及内置CSRF后，先撤销服务器会话再完成OIDC退出。</summary>
    /// <param name="context">当前真实HTTP请求。</param>
    /// <param name="antiforgery">框架内置CSRF服务。</param>
    /// <param name="audit">PG安全审计服务。</param>
    /// <returns>标准OIDC重定向或准确的错误响应。</returns>
    private static async Task<IResult> LogoutAsync(HttpContext context, IAntiforgery antiforgery, AuditService audit)
    {
        if (context.User.Identity?.IsAuthenticated != true)
        {
            return PlatformProblem.Create(context, 401, "unauthenticated");
        }
        try
        {
            await antiforgery.ValidateRequestAsync(context);
        }
        catch (AntiforgeryValidationException)
        {
            await audit.WriteAsync(context, "csrf.denied", "/auth/logout", "denied");
            return PlatformProblem.Create(context, 403, "csrf_failed");
        }
        context.Response.Headers.CacheControl = "no-store";
        return Results.SignOut(new AuthenticationProperties { RedirectUri = "/signed-out" },
            [CookieAuthenticationDefaults.AuthenticationScheme, OpenIdConnectDefaults.AuthenticationScheme]);
    }

    /// <summary>查询实际PG资源并同时按角色、组织和厂区过滤。</summary>
    /// <param name="context">已验证身份的当前请求。</param>
    /// <param name="database">Governance专属上下文。</param>
    /// <param name="audit">真实PG审计服务。</param>
    /// <param name="siteId">可选的显式厂区。</param>
    /// <returns>实际授权资源及已提交审计标识。</returns>
    private static async Task<IResult> ReadResourcesAsync(HttpContext context, GovernanceDbContext database, AuditService audit, string? siteId)
    {
        if (context.User.Identity?.IsAuthenticated != true)
        {
            return PlatformProblem.Create(context, 401, "unauthenticated");
        }
        // 已签发组织及厂区范围只从服务器身份读取。
        var organization = context.User.FindFirstValue("organization_id");
        // 查询前先冻结可信厂区列表，客户端不能追加范围。
        var sites = context.User.FindAll("site_ids").Select(claim => claim.Value).ToArray();
        if (!SecurityBoundary.CanReadResources(context.User)
            || (siteId is not null && (organization is null || !SecurityBoundary.HasScope(context.User, organization, siteId))))
        {
            await audit.WriteAsync(context, "authorization.denied", "platform.resources", "denied");
            return PlatformProblem.Create(context, 403, "forbidden");
        }
        // 投影只包含公共DTO批准字段，不返回存储层细节。
        var resources = await database.Resources.AsNoTracking()
            .Where(resource => resource.OrganizationId == organization && sites.Contains(resource.SiteId)
                && (siteId == null || resource.SiteId == siteId))
            .OrderBy(resource => resource.Id)
            .Select(resource => new PlatformResource
            {
                Id = resource.Id,
                Name = resource.Name,
                OrganizationId = resource.OrganizationId,
                SiteId = resource.SiteId,
                Status = resource.Status
            })
            .ToArrayAsync(context.RequestAborted);
        // 只有实际审计提交后才返回成功结果和关联ID。
        var auditId = await audit.WriteAsync(context, "platform.resource.read", "platform.resources", "allowed", siteId);
        return Results.Ok(new PlatformResourceList
        {
            Items = resources,
            AuditId = auditId,
            TraceId = Activity.Current?.TraceId.ToString() ?? context.TraceIdentifier
        });
    }

    /// <summary>以实际资源所属范围判定行级权限，区分跨厂区和未知ID。</summary>
    /// <param name="context">当前请求。</param>
    /// <param name="database">Governance模块上下文。</param>
    /// <param name="audit">真实审计服务。</param>
    /// <param name="id">受控资源标识。</param>
    /// <returns>获准资源或准确401/403/404。</returns>
    private static async Task<IResult> ReadResourceAsync(HttpContext context, GovernanceDbContext database, AuditService audit, string id)
    {
        if (context.User.Identity?.IsAuthenticated != true)
        {
            return PlatformProblem.Create(context, 401, "unauthenticated");
        }
        if (!SecurityBoundary.CanReadResources(context.User))
        {
            await audit.WriteAsync(context, "authorization.denied", "platform.resource", "denied");
            return PlatformProblem.Create(context, 403, "forbidden");
        }
        // 资源真实归属来自PG，不信任查询参数或权限请求头。
        var resource = await database.Resources.AsNoTracking().SingleOrDefaultAsync(value => value.Id == id, context.RequestAborted);
        if (resource is null)
        {
            return PlatformProblem.Create(context, 404, "resource_not_found");
        }
        if (!SecurityBoundary.HasScope(context.User, resource.OrganizationId, resource.SiteId))
        {
            await audit.WriteAsync(context, "authorization.denied", resource.Id, "denied");
            return PlatformProblem.Create(context, 403, "forbidden");
        }
        await audit.WriteAsync(context, "platform.resource.read", resource.Id, "allowed", resource.SiteId);
        return Results.Ok(new PlatformResource
        {
            Id = resource.Id,
            Name = resource.Name,
            OrganizationId = resource.OrganizationId,
            SiteId = resource.SiteId,
            Status = resource.Status
        });
    }

    /// <summary>仅向审计角色返回同组织且完整厂区范围均获授权的持久审计。</summary>
    /// <param name="context">当前请求及已验证身份。</param>
    /// <param name="database">模块PG上下文。</param>
    /// <param name="audit">允许及拒绝事实的持久写入器。</param>
    /// <returns>范围过滤后的真实审计或明确错误。</returns>
    private static async Task<IResult> ReadAuditAsync(HttpContext context, GovernanceDbContext database, AuditService audit)
    {
        if (context.User.Identity?.IsAuthenticated != true)
        {
            return PlatformProblem.Create(context, 401, "unauthenticated");
        }
        if (!context.User.IsInRole("platform.auditor"))
        {
            await audit.WriteAsync(context, "authorization.denied", "platform.audit", "denied");
            return PlatformProblem.Create(context, 403, "forbidden");
        }
        // 手动校验保留冻结ProblemDetails，避免框架绑定错误产生无合同空400。
        var limitText = context.Request.Query["limit"].FirstOrDefault() ?? "20";
        if (!int.TryParse(limitText, NumberStyles.None, CultureInfo.InvariantCulture, out var limit) || limit is < 1 or > 100)
        {
            return PlatformProblem.Create(context, 400, "invalid_request");
        }
        // 可信组织及厂区条件与资源查询使用同一语义。
        var organization = context.User.FindFirstValue("organization_id");
        // 没有合法范围的审计身份只能读取空列表。
        var sites = context.User.FindAll("site_ids").Select(claim => claim.Value)
            .Where(value => !string.IsNullOrWhiteSpace(value)).Distinct(StringComparer.Ordinal).ToArray();
        // 服务端投影避免公开数据库或认证票据字段。
        var records = await database.AuditRecords.AsNoTracking()
            .Where(record => !string.IsNullOrWhiteSpace(organization) && record.OrganizationId == organization
                && record.ScopeSiteIds != null && record.ScopeSiteIds.Length > 0
                && record.ScopeSiteIds.All(site => sites.Contains(site)))
            .OrderByDescending(record => record.OccurredAtUtc).Take(limit)
            .Select(record => new PlatformAuditEntry
            {
                Id = record.Id,
                OccurredAtUtc = record.OccurredAtUtc,
                Actor = record.Actor,
                Action = record.Action,
                Resource = record.Resource,
                Outcome = record.Outcome,
                TraceId = record.TraceId,
                CorrelationId = record.CorrelationId,
                OrganizationId = record.OrganizationId,
                SiteId = record.SiteId,
                ScopeSiteIds = record.ScopeSiteIds
            })
            .ToArrayAsync(context.RequestAborted);
        // 先物化读取快照再唯一提交成功事件：本次结果不包含自身，写入失败不能返回200。
        await audit.WriteAsync(context, "platform.audit.read", "platform.audit", "allowed");
        return Results.Ok(records);
    }

    /// <summary>映射向浏览器公开的最小身份，不返回令牌或任意远端声明。</summary>
    /// <param name="principal">经过OIDC验证并映射的服务器身份。</param>
    /// <returns>冻结公共身份DTO。</returns>
    private static PlatformIdentity ToIdentity(ClaimsPrincipal principal)
    {
        return new PlatformIdentity
        {
            SubjectId = principal.FindFirstValue("sub") ?? string.Empty,
            DisplayName = principal.FindFirstValue("name") ?? principal.FindFirstValue("preferred_username") ?? "平台用户",
            Roles = principal.FindAll(ClaimTypes.Role).Select(claim => claim.Value).Distinct().ToArray(),
            Scopes = principal.FindAll("site_ids").Select(claim => new PlatformScope
            { OrganizationId = principal.FindFirstValue("organization_id") ?? string.Empty, SiteId = claim.Value }).ToArray()
        };
    }

    /// <summary>以固定时间比较验证内部探针凭据，失败不透露比较细节。</summary>
    /// <param name="context">真实请求。</param>
    /// <param name="options">启动时验证的安全配置。</param>
    /// <returns>内部探针凭据有效时为真。</returns>
    private static bool HasHealthKey(HttpContext context, PlatformSecurityOptions options)
    {
        return CryptographicOperations.FixedTimeEquals(SHA256.HashData(Encoding.UTF8.GetBytes(options.HealthKey)),
            SHA256.HashData(Encoding.UTF8.GetBytes(context.Request.Headers["X-Health-Key"].ToString())));
    }
}
