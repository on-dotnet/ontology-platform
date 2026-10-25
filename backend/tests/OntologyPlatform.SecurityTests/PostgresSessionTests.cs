using System.Net;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using System.Xml.Linq;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Modules.Governance;

namespace OntologyPlatform.SecurityTests;

/// <summary>通过真实PG和两个独立宿主的共享加密keyring验证会话生命周期。</summary>
[TestClass]
public sealed class PostgresSessionTests
{
    /// <summary>有效引用先通过真实HTTP认证，再因专属PG会话行过期而返回401。</summary>
    /// <returns>独立Kestrel、真实PG和受保护Cookie的生命周期验证任务。</returns>
    [TestMethod]
    public async Task ExpiredServerSessionCookieReturnsHttp401()
    {
        // 只接收本轮专用PG配置，缺少前提不冒充HTTP负例通过。
        var connection = Environment.GetEnvironmentVariable("G1_SEC_PG_CONNECTION");
        if (string.IsNullOrWhiteSpace(connection))
        {
            Assert.Inconclusive("NOT_RUN: 未注入本轮隔离PG连接。");
        }
        // 证书、keyring和监听端口均由本测试单独创建。
        using var fixture = new SecurityHostFixture();
        // 正式API管道保持原有Cookie处理器与PG票据存储器。
        await using var app = fixture.Create(connection: connection);
        await app.StartAsync();
        // 主体随机且只属于当前测试，清理不会触及其他登录会话。
        var subject = "synthetic-expired-http-" + Guid.NewGuid().ToString("N");
        // 最小合成可信票据用于隔离HTTP过期验证，不代表OIDC登录验收。
        var principal = new ClaimsPrincipal(new ClaimsIdentity(new[] { new Claim("sub", subject),
            new Claim("organization_id", "org-demo"), new Claim("site_ids", "site-a") }, "synthetic-expiry-test"));
        // 正式存储器生成唯一随机引用并写入真实PG。
        var store = app.Services.GetRequiredService<PostgresTicketStore>();
        // 保持票据本身未到期，确保负例由PG行失效条件触发。
        var properties = new AuthenticationProperties { ExpiresUtc = DateTimeOffset.UtcNow.AddMinutes(10) };
        // 该随机引用只在测试内存中使用，断言与证据不输出其值。
        var key = await store.StoreAsync(new AuthenticationTicket(principal, properties, CookieAuthenticationDefaults.AuthenticationScheme));
        // 独立上下文只修改本测试刚创建的唯一会话行。
        await using var database = await app.Services.GetRequiredService<IDbContextFactory<GovernanceDbContext>>().CreateDbContextAsync();
        try
        {
            // 使用正式Cookie加密格式创建内置SessionStore引用票据。
            var options = app.Services.GetRequiredService<IOptionsMonitor<CookieAuthenticationOptions>>().Get(CookieAuthenticationDefaults.AuthenticationScheme);
            // 此声明名来自ASP.NET Core Cookie处理器的服务器会话协议。
            var reference = new ClaimsPrincipal(new ClaimsIdentity(new[] { new Claim("Microsoft.AspNetCore.Authentication.Cookies-SessionId", key) }, CookieAuthenticationDefaults.AuthenticationScheme));
            // 认证Cookie只含受保护引用，不承载原始主体或长期令牌。
            var cookie = options.TicketDataFormat.Protect(new AuthenticationTicket(reference, properties, CookieAuthenticationDefaults.AuthenticationScheme));
            // 同一真实HTTP客户端在过期前后重放相同受保护引用。
            using var client = fixture.CreateClient(app);
            client.DefaultRequestHeaders.Add("Cookie", options.Cookie.Name + "=" + cookie);
            // 正向控制证明Cookie有效且服务端能够读取这一个PG票据。
            using var valid = await client.GetAsync("/api/v1/platform/me");
            Assert.AreEqual(HttpStatusCode.OK, valid.StatusCode);
            // 失效只作用于本测试的唯一store key，不改变全局时钟或其他会话。
            var changed = await database.Sessions.Where(value => value.Id == key)
                .ExecuteUpdateAsync(update => update.SetProperty(value => value.ExpiresAtUtc, DateTimeOffset.UtcNow.AddMinutes(-1)));
            Assert.AreEqual(1, changed);
            // Cookie仍可解密，但PG会话过期必须使正式API拒绝认证。
            using var expired = await client.GetAsync("/api/v1/platform/me");
            Assert.AreEqual(HttpStatusCode.Unauthorized, expired.StatusCode);
            Assert.AreEqual("application/problem+json", expired.Content.Headers.ContentType?.MediaType);
            Assert.IsTrue(expired.Headers.CacheControl?.NoStore);
            // 只解析通用错误码，不回显Cookie、身份或认证属性。
            using var body = JsonDocument.Parse(await expired.Content.ReadAsStringAsync());
            Assert.AreEqual("unauthenticated", body.RootElement.GetProperty("code").GetString());
            Assert.IsTrue(expired.Headers.Contains("X-Trace-Id"));
            Assert.IsTrue(expired.Headers.Contains("X-Correlation-Id"));
        }
        finally
        {
            await database.Sessions.Where(value => value.Id == key).ExecuteDeleteAsync();
            await database.AuditRecords.Where(value => value.Actor == subject).ExecuteDeleteAsync();
        }
    }

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
