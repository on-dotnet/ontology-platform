using System.Net;
using System.Net.Http.Json;
using System.Security.Claims;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using OntologyPlatform.Api.G2;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Agents;
using OntologyPlatform.Modules.Governance;

namespace OntologyPlatform.AgentTests;

/// <summary>真实随机回环Kestrel、原生Cookie/CSRF和同一PG票据；仅OIDC入口用服务器固定Synthetic身份。</summary>
internal sealed class AgentHttpFixture : IAsyncDisposable
{
    /// <summary>当前测试服务。</summary>
    internal WebApplication App { get; }

    /// <summary>内存Cookie容器，不保存认证材料到文件。</summary>
    internal HttpClient Client { get; }

    /// <summary>仅本进程使用的防伪令牌，不输出报告。</summary>
    internal string Csrf { get; private set; } = string.Empty;

    /// <summary>关闭自动重定向避免401被登录页掩盖。</summary>
    private AgentHttpFixture(WebApplication app)
    {
        App = app;
        Client = new HttpClient(new HttpClientHandler { CookieContainer = new CookieContainer(), AllowAutoRedirect = false, UseProxy = false }) { BaseAddress = new Uri(app.Urls.Single()), Timeout = TimeSpan.FromSeconds(35) };
    }

    /// <summary>复用实际Run/Gateway/审计及真实PostgresTicketStore，不复制业务或安全实现。</summary>
    internal static async Task<AgentHttpFixture> StartAsync(AgentFixture fixture)
    {
        // 无全局配置变更，Kestrel仅监听当前随机回环端口。
        var builder = WebApplication.CreateBuilder(new WebApplicationOptions { EnvironmentName = Environments.Development });
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        builder.Logging.ClearProviders();
        builder.Services.AddSingleton<TimeProvider>(fixture.Clock);
        builder.Services.AddSingleton<IDataProtectionProvider>(new EphemeralDataProtectionProvider());
        builder.Services.AddDataProtection();
        builder.Services.AddHttpContextAccessor();
        builder.Services.AddDbContextFactory<GovernanceDbContext>(options => options.UseNpgsql(Environment.GetEnvironmentVariable("G2_AI_PG"), database => database.MigrationsHistoryTable("__EFMigrationsHistory", "governance")));
        builder.Services.AddSingleton<PostgresTicketStore>();
        builder.Services.AddSingleton<IAuditTrail, TransactionalAuditWriter>();
        builder.Services.AddSingleton(fixture.Runs);
        builder.Services.AddSingleton(fixture.Gateway);
        builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme).AddCookie(options =>
        {
            options.Cookie.Name = ".AgentTests.Session";
            options.SlidingExpiration = false;
            options.Events.OnRedirectToLogin = context => { context.Response.StatusCode = 401; return Task.CompletedTask; };
            options.Events.OnRedirectToAccessDenied = context => { context.Response.StatusCode = 403; return Task.CompletedTask; };
        });
        builder.Services.AddOptions<CookieAuthenticationOptions>(CookieAuthenticationDefaults.AuthenticationScheme).Configure<PostgresTicketStore>((options, store) => options.SessionStore = store);
        builder.Services.AddAntiforgery(options => options.HeaderName = "X-CSRF-TOKEN");
        builder.Services.AddG2Authorization();
        builder.Services.AddSemanticMcpEndpoints();
        // 固定可信Origin在随机端口确定后填入同一个Options实例。
        var security = new PlatformSecurityOptions();
        builder.Services.AddSingleton<IOptions<PlatformSecurityOptions>>(Options.Create(security));
        // 构建真实应用，所有生产端点均来自Api工程。
        var app = builder.Build();
        app.UseAuthentication();
        app.UseAuthorization();
        app.MapExecutionEndpoints();
        app.MapMcpEndpoints();
        app.MapPost("/fixture/login", async (HttpContext context) =>
        {
            // Synthetic身份由测试服务器固定，不从请求头或JSON接收actor。
            var claims = new List<Claim> { new("sub", fixture.Author.SubjectId), new("organization_id", fixture.Author.OrganizationId), new(ClaimTypes.Role, "platform.operator") };
            claims.AddRange(fixture.Author.SiteIds.Select(value => new Claim("site_ids", value)));
            await context.SignInAsync(CookieAuthenticationDefaults.AuthenticationScheme, new ClaimsPrincipal(new ClaimsIdentity(claims, CookieAuthenticationDefaults.AuthenticationScheme)));
            return Results.NoContent();
        });
        app.MapGet("/fixture/csrf", (HttpContext context, IAntiforgery antiforgery) => Results.Json(antiforgery.GetAndStoreTokens(context).RequestToken)).RequireAuthorization();
        app.MapPost("/fixture/logout", async (HttpContext context, IAntiforgery antiforgery) =>
        {
            await antiforgery.ValidateRequestAsync(context);
            await context.SignOutAsync(CookieAuthenticationDefaults.AuthenticationScheme);
            return Results.NoContent();
        }).RequireAuthorization();
        await app.StartAsync();
        security.PublicOrigin = app.Urls.Single();
        return new AgentHttpFixture(app);
    }

    /// <summary>真实SignIn建立PG票据和Cookie，之后获取原生防伪令牌。</summary>
    internal async Task LoginAsync()
    {
        // 登录只经过当前测试专属Synthetic入口，其他安全实现完全真实。
        using var response = await Client.PostAsync("/fixture/login", null);
        Assert.AreEqual(HttpStatusCode.NoContent, response.StatusCode);
        Csrf = (await Client.GetFromJsonAsync<string>("/fixture/csrf"))!;
        Client.DefaultRequestHeaders.Add("X-CSRF-TOKEN", Csrf);
        Client.DefaultRequestHeaders.Add("Origin", Client.BaseAddress!.GetLeftPart(UriPartial.Authority));
    }

    /// <summary>关闭当前Kestrel和内存Cookie，不留下票据文件。</summary>
    public async ValueTask DisposeAsync()
    {
        Client.Dispose();
        await App.StopAsync();
        await App.DisposeAsync();
    }
}
