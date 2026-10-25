using System.Diagnostics;
using System.Security.Claims;
using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Modules.Governance;

namespace OntologyPlatform.Api.Security;

/// <summary>把安全允许与拒绝持久提交到模块PG，不以运行日志替代事实。</summary>
public sealed class AuditService
{
    /// <summary>本请求拥有的模块上下文。</summary>
    private readonly GovernanceDbContext database;

    /// <summary>构造请求范围审计写入器。</summary>
    /// <param name="database">Governance模块上下文。</param>
    public AuditService(GovernanceDbContext database)
    {
        this.database = database;
    }

    /// <summary>提交安全审计后才向响应暴露审计标识。</summary>
    /// <param name="context">当前请求及可信身份。</param>
    /// <param name="action">受控事件代码。</param>
    /// <param name="resource">受控资源或路由。</param>
    /// <param name="outcome">固定允许或拒绝结果。</param>
    /// <param name="siteId">已授权显式厂区；为空时使用全部可信厂区。</param>
    /// <returns>成功提交的审计标识。</returns>
    public async Task<string> WriteAsync(HttpContext context, string action, string resource, string outcome, string? siteId = null)
    {
        // 从已验证身份构造模块审计，不接受客户端指定actor或组织。
        var record = Create(context, context.User, action, resource, outcome, siteId);
        database.AuditRecords.Add(record);
        await database.SaveChangesAsync(context.RequestAborted);
        context.Response.Headers["X-Audit-Id"] = record.Id;
        return record.Id;
    }

    /// <summary>构造可与会话变更在同一次SaveChanges中提交的审计实体。</summary>
    /// <param name="context">当前请求，无HTTP调用时可空。</param>
    /// <param name="principal">已经验证的身份。</param>
    /// <param name="action">受控事件代码。</param>
    /// <param name="resource">受控资源标识。</param>
    /// <param name="outcome">固定审计结果。</param>
    /// <param name="siteId">已授权显式厂区；为空时保留全部可信厂区。</param>
    /// <returns>尚未持久化的审计实体。</returns>
    public static AuditRecord Create(HttpContext? context, ClaimsPrincipal principal, string action, string resource, string outcome, string? siteId = null)
    {
        // 显式厂区已由调用方授权；其余事件保留全部可信范围，不能任意归入首厂。
        var sites = (siteId is null ? principal.FindAll("site_ids").Select(claim => claim.Value) : [siteId])
            .Where(value => !string.IsNullOrWhiteSpace(value)).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray();
        return new AuditRecord
        {
            Actor = principal.FindFirstValue("sub") ?? "anonymous",
            Action = action,
            Resource = resource,
            Outcome = outcome,
            OrganizationId = principal.FindFirstValue("organization_id"),
            ScopeSiteIds = sites,
            SiteId = sites.Length == 1 ? sites[0] : null,
            TraceId = Activity.Current?.TraceId.ToString() ?? context?.TraceIdentifier ?? Guid.NewGuid().ToString("N"),
            CorrelationId = context?.Items["CorrelationId"] as string ?? Guid.NewGuid().ToString("N")
        };
    }
}
