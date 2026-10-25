using System.Security.Claims;
using System.Security.Cryptography;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Modules.Governance;

namespace OntologyPlatform.Api.Security;

/// <summary>跨实例共享的加密PG身份票据；浏览器仅得到受保护的随机引用。</summary>
public sealed class PostgresTicketStore : ITicketStore
{
    /// <summary>创建短生命周期模块上下文的工厂。</summary>
    private readonly IDbContextFactory<GovernanceDbContext> factory;

    /// <summary>使用共享证书keyring的票据加密器。</summary>
    private readonly IDataProtector protector;

    /// <summary>读取当前请求关联信息，不缓存身份。</summary>
    private readonly IHttpContextAccessor accessor;

    /// <summary>提供可测试且统一的UTC时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>构造无本地会话缓存的服务器票据存储器。</summary>
    /// <param name="factory">PG模块上下文工厂。</param>
    /// <param name="protection">共享持久加密提供者。</param>
    /// <param name="accessor">请求上下文访问器。</param>
    /// <param name="clock">UTC时间提供者。</param>
    public PostgresTicketStore(IDbContextFactory<GovernanceDbContext> factory, IDataProtectionProvider protection, IHttpContextAccessor accessor, TimeProvider clock)
    {
        this.factory = factory;
        protector = protection.CreateProtector("OntologyPlatform.Governance.ServerTicket.v1");
        this.accessor = accessor;
        this.clock = clock;
    }

    /// <summary>加密票据并与登录审计原子提交，固定最长30分钟。</summary>
    /// <param name="ticket">经过OIDC验证的服务器认证票据。</param>
    /// <returns>随机服务器引用。</returns>
    public async Task<string> StoreAsync(AuthenticationTicket ticket)
    {
        // 随机引用不承载主体、声明或token，且不可预测。
        var key = Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(32));
        // 票据与数据库均采用同一固定失效时间，不启用滑动延长。
        var expires = clock.GetUtcNow().AddMinutes(30);
        if (ticket.Properties.ExpiresUtc is { } requested && requested < expires)
        {
            expires = requested;
        }
        ticket.Properties.ExpiresUtc = expires;
        // 单次SaveChanges使会话建立和登录审计处于同一PG事务。
        await using var database = await factory.CreateDbContextAsync();
        database.Sessions.Add(new ServerSession
        {
            Id = key,
            ProtectedTicket = protector.Protect(TicketSerializer.Default.Serialize(ticket)),
            ExpiresAtUtc = expires
        });
        database.AuditRecords.Add(AuditService.Create(accessor.HttpContext, ticket.Principal,
            "authentication.login", "session", "allowed"));
        await database.SaveChangesAsync();
        return key;
    }

    /// <summary>更新票据内容时保留原始绝对失效时间，不复活撤销会话。</summary>
    /// <param name="key">随机服务器引用。</param>
    /// <param name="ticket">待更新的票据。</param>
    /// <returns>更新提交完成的任务。</returns>
    public async Task RenewAsync(string key, AuthenticationTicket ticket)
    {
        // 每次更新直接查询PG，双实例共享撤销事实。
        await using var database = await factory.CreateDbContextAsync();
        // 使用行条件避免撤销或过期票据被续期路径复活。
        var session = await database.Sessions.SingleOrDefaultAsync(value => value.Id == key);
        if (session is null || session.RevokedAtUtc is not null || session.ExpiresAtUtc <= clock.GetUtcNow())
        {
            return;
        }
        ticket.Properties.ExpiresUtc = session.ExpiresAtUtc;
        // 条件更新避免并发注销后用旧实体覆盖撤销状态。
        var protectedTicket = protector.Protect(TicketSerializer.Default.Serialize(ticket));
        await database.Sessions.Where(value => value.Id == key && value.RevokedAtUtc == null && value.ExpiresAtUtc > clock.GetUtcNow())
            .ExecuteUpdateAsync(update => update.SetProperty(value => value.ProtectedTicket, protectedTicket));
    }

    /// <summary>仅解密仍有效且未撤销的PG票据。</summary>
    /// <param name="key">浏览器受保护Cookie中解析出的随机引用。</param>
    /// <returns>有效认证票据或空。</returns>
    public async Task<AuthenticationTicket?> RetrieveAsync(string key)
    {
        // 每次读取都检查数据库事实，禁止进程内缓存掩盖注销或过期。
        await using var database = await factory.CreateDbContextAsync();
        // 仅获取有效行，过期及撤销票据根本不进入解密路径。
        var session = await database.Sessions.AsNoTracking().SingleOrDefaultAsync(value => value.Id == key
            && value.RevokedAtUtc == null && value.ExpiresAtUtc > clock.GetUtcNow());
        if (session is null)
        {
            return null;
        }
        try
        {
            return TicketSerializer.Default.Deserialize(protector.Unprotect(session.ProtectedTicket));
        }
        catch (CryptographicException)
        {
            return null;
        }
    }

    /// <summary>原子撤销会话并记录注销审计，旧Cookie随后不能重放。</summary>
    /// <param name="key">需要撤销的随机服务器引用。</param>
    /// <returns>撤销与审计提交完成的任务。</returns>
    public async Task RemoveAsync(string key)
    {
        // 使用事务把撤销与审计绑定，依赖故障则整体失败关闭。
        await using var database = await factory.CreateDbContextAsync();
        // 同一事务中的条件更新只允许一次有效注销。
        await using var transaction = await database.Database.BeginTransactionAsync();
        // 从当前认证请求读取审计主体，绝不输出服务器票据。
        var principal = accessor.HttpContext?.User ?? new ClaimsPrincipal();
        // 条件更新防止并发注销生成多个成功审计。
        var changed = await database.Sessions.Where(value => value.Id == key && value.RevokedAtUtc == null)
            .ExecuteUpdateAsync(update => update.SetProperty(value => value.RevokedAtUtc, clock.GetUtcNow()));
        if (changed > 0)
        {
            database.AuditRecords.Add(AuditService.Create(accessor.HttpContext, principal,
                "authentication.logout", "session", "allowed"));
            await database.SaveChangesAsync();
        }
        await transaction.CommitAsync();
    }
}
