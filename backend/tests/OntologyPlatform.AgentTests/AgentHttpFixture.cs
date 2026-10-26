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

    /// <summary>观察服务器实际结束首条SSE请求，验证慢客户端不占用无限连接。</summary>
    internal Task StreamStopped { get; }

    /// <summary>仅记录MCP实际媒体类型，不记录消息、令牌或正文。</summary>
    internal System.Collections.Concurrent.ConcurrentBag<string> McpMediaTypes { get; } = [];

    /// <summary>内存Cookie容器，不保存认证材料到文件。</summary>
    internal HttpClient Client { get; }

    /// <summary>仅本进程使用的防伪令牌，不输出报告。</summary>
    internal string Csrf { get; private set; } = string.Empty;

    /// <summary>关闭自动重定向避免401被登录页掩盖。</summary>
    private AgentHttpFixture(WebApplication app, Task streamStopped)
    {
        App = app;
        StreamStopped = streamStopped;
        Client = new HttpClient(new MediaRecorder(this)) { BaseAddress = new Uri(app.Urls.Single()), Timeout = TimeSpan.FromSeconds(35) };
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
        // 测试观测请求实际退出，不只以客户端等待超时假称服务已关闭。
        var streamStopped = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        app.Use(async (context, next) =>
        {
            try { await next(context); }
            finally { if (context.Request.Path.Value?.EndsWith("/events", StringComparison.Ordinal) == true) streamStopped.TrySetResult(); }
        });
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
        app.MapPost("/fixture/restrict", async (HttpContext context, IAntiforgery antiforgery) =>
        {
            await antiforgery.ValidateRequestAsync(context);
            // 通过原生同session续写更新可信范围，旧连接仍携带相同受保护引用。
            var principal = new ClaimsPrincipal(new ClaimsIdentity(context.User.Claims.Where(value => value.Type != "site_ids" || value.Value == "site-a"), CookieAuthenticationDefaults.AuthenticationScheme));
            await context.SignInAsync(CookieAuthenticationDefaults.AuthenticationScheme, principal);
            return Results.NoContent();
        }).RequireAuthorization();
        app.MapPost("/fixture/logout", async (HttpContext context, IAntiforgery antiforgery) =>
        {
            await antiforgery.ValidateRequestAsync(context);
            await context.SignOutAsync(CookieAuthenticationDefaults.AuthenticationScheme);
            return Results.NoContent();
        }).RequireAuthorization();
        await app.StartAsync();
        security.PublicOrigin = app.Urls.Single();
        return new AgentHttpFixture(app, streamStopped.Task);
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

    /// <summary>透明观察SDK实际传输类型，不替换任何HTTP响应。</summary>
    private sealed class MediaRecorder : DelegatingHandler
    {
        /// <summary>只用于当前测试断言的媒体类型收集器。</summary>
        private readonly AgentHttpFixture fixture;

        /// <summary>使用真实CookieContainer和真实回环网络。</summary>
        internal MediaRecorder(AgentHttpFixture fixture) : base(new HttpClientHandler { CookieContainer = new CookieContainer(), AllowAutoRedirect = false, UseProxy = false }) => this.fixture = fixture;

        /// <summary>仅读取公开Content-Type，绝不复制请求认证头或正文。</summary>
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            // 响应由真实Kestrel产生，观测不改变消息内容。
            var response = await base.SendAsync(request, token);
            if (request.RequestUri?.AbsolutePath == "/api/v1/mcp" && response.Content.Headers.ContentType?.MediaType is { } media)
                fixture.McpMediaTypes.Add(media);
            return response;
        }
    }

    /// <summary>关闭当前Kestrel和内存Cookie，不留下票据文件。</summary>
    public async ValueTask DisposeAsync()
    {
        Client.Dispose();
        await App.StopAsync();
        await App.DisposeAsync();
    }
}
