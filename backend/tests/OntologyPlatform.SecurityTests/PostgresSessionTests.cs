using System.Security.Claims;
using System.Text;
using System.Xml.Linq;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Modules.Governance;

namespace OntologyPlatform.SecurityTests;

/// <summary>通过真实PG和两个独立宿主的共享加密keyring验证会话生命周期。</summary>
[TestClass]
public sealed class PostgresSessionTests
{
    /// <summary>票据必须跨实例可读、数据库内加密且注销后立即不可重放。</summary>
    /// <returns>真实PG和DataProtection交互任务。</returns>
    [TestMethod]
    public async Task SharedEncryptedTicketRevocationAndExpiryUsePostgresFacts()
    {
        // 只接受本轮专用隔离PG连接；缺少前提明确跳过而非伪造通过。
        var connection = Environment.GetEnvironmentVariable("G1_SEC_PG_CONNECTION");
        if (string.IsNullOrWhiteSpace(connection))
        {
            Assert.Inconclusive("NOT_RUN: G1_SEC_PG_CONNECTION未注入隔离PG；需要Master先应用Governance迁移。");
        }
        // 两个正式宿主共享同一测试创建的证书及目录，分别拥有独立容器。
        using var fixture = new SecurityHostFixture();
        // 第一个真实宿主提供独立的DataProtection和票据存储实例。
        await using var first = fixture.Create(connection: connection);
        // 第二个宿主只共享PG和持久证书keyring，没有内存会话缓存。
        await using var second = fixture.Create(connection: connection);
        // 读取正式注册的票据存储器，而非测试替身。
        var firstStore = first.Services.GetRequiredService<PostgresTicketStore>();
        // 第二个服务容器解析出另一个独立存储器。
        var secondStore = second.Services.GetRequiredService<PostgresTicketStore>();
        // 合成主体仅用于本测试真实存储验证，不冒充OIDC端到端登录。
        var subject = "synthetic-session-test-" + Guid.NewGuid().ToString("N");
        // 最小可信票据包含一个只在加密服务端保留的合成令牌。
        var principal = new ClaimsPrincipal(new ClaimsIdentity(new[] { new Claim("sub", subject),
            new Claim("organization_id", "org-demo"), new Claim("site_ids", "site-a") }, "synthetic-storage-test"));
        // 认证属性独立于客户端公开DTO。
        var properties = new AuthenticationProperties();
        properties.StoreTokens([new AuthenticationToken { Name = "id_token", Value = "synthetic-ticket-encryption-marker" }]);
        // 会话通过生产存储代码进入真实PG。
        var key = await firstStore.StoreAsync(new AuthenticationTicket(principal, properties, CookieAuthenticationDefaults.AuthenticationScheme));
        // 第二实例只能借助共享证书keyring解密，不依赖第一个实例内存。
        var restored = await secondStore.RetrieveAsync(key);
        Assert.IsNotNull(restored);
        Assert.AreEqual(subject, restored.Principal.FindFirstValue("sub"));
        // 查询模块行检查静态密文，没有输出原始行或票据。
        await using var database = await first.Services.GetRequiredService<IDbContextFactory<GovernanceDbContext>>().CreateDbContextAsync();
        // 独立读取验证密文和绝对有效期。
        var row = await database.Sessions.AsNoTracking().SingleAsync(value => value.Id == key);
        Assert.IsFalse(Encoding.UTF8.GetString(row.ProtectedTicket).Contains("synthetic-ticket-encryption-marker", StringComparison.Ordinal));
        Assert.IsTrue(row.ExpiresAtUtc <= DateTimeOffset.UtcNow.AddMinutes(30));
        Assert.IsTrue(fixture.KeyRingFiles().Length > 0);
        Assert.IsTrue(fixture.KeyRingFiles().All(document => document.Descendants().Any(element => element.Name.LocalName == "encryptedSecret")));
        // 注销审计使用与真实请求相同的可信身份上下文。
        var accessor = second.Services.GetRequiredService<IHttpContextAccessor>();
        accessor.HttpContext = new DefaultHttpContext { User = principal };
        await secondStore.RemoveAsync(key);
        accessor.HttpContext = null;
        Assert.IsNull(await firstStore.RetrieveAsync(key));
        // 已撤销行不能被Renew路径重新激活。
        await firstStore.RenewAsync(key, new AuthenticationTicket(principal, properties, CookieAuthenticationDefaults.AuthenticationScheme));
        Assert.IsNull(await secondStore.RetrieveAsync(key));
        // 原子登录审计必须存在，不能以Console日志代替。
        Assert.IsTrue(await database.AuditRecords.AnyAsync(value => value.Actor == subject && value.Action == "authentication.login"));
        Assert.IsTrue(await database.AuditRecords.AnyAsync(value => value.Actor == subject && value.Action == "authentication.logout"));
        // 另建短票据并直接控制数据库UTC失效，验证实际行条件。
        var expiredKey = await firstStore.StoreAsync(new AuthenticationTicket(principal,
            new AuthenticationProperties { ExpiresUtc = DateTimeOffset.UtcNow.AddMinutes(-1) }, CookieAuthenticationDefaults.AuthenticationScheme));
        Assert.IsNull(await secondStore.RetrieveAsync(expiredKey));
        // 清理仅触及本测试创建的会话及合成审计，不触碰其他任务数据。
        await database.Sessions.Where(value => value.Id == key || value.Id == expiredKey).ExecuteDeleteAsync();
        await database.AuditRecords.Where(value => value.Actor == subject).ExecuteDeleteAsync();
    }
}
