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
    /// <param name="siteId">本事件实际所属厂区，可空。</param>
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
    /// <param name="siteId">事件所属厂区。</param>
    /// <returns>尚未持久化的审计实体。</returns>
    public static AuditRecord Create(HttpContext? context, ClaimsPrincipal principal, string action, string resource, string outcome, string? siteId = null)
    {
        return new AuditRecord
        {
            Actor = principal.FindFirstValue("sub") ?? "anonymous",
            Action = action,
            Resource = resource,
            Outcome = outcome,
            OrganizationId = principal.FindFirstValue("organization_id"),
            SiteId = siteId ?? principal.FindAll("site_ids").Select(claim => claim.Value).FirstOrDefault(),
            TraceId = Activity.Current?.TraceId.ToString() ?? context?.TraceIdentifier ?? Guid.NewGuid().ToString("N"),
            CorrelationId = context?.Items["CorrelationId"] as string ?? Guid.NewGuid().ToString("N")
        };
    }
}
