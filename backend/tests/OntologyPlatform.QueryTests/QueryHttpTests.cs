using System.Net;
using System.Net.Http.Json;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Http.Metadata;
using Microsoft.AspNetCore.Routing;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using OntologyPlatform.Api;
using OntologyPlatform.Api.G2;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.QueryTests;

/// <summary>通过生产薄端点、真实Kestrel/原生防伪和真实PG审计验证HTTP安全顺序。</summary>
[TestClass]
public sealed class QueryHttpTests
{
    /// <summary>标准查询路由必须与冻结合同完全一致，旧单数路径不存在。</summary>
    [TestMethod]
    public async Task QueryRouteMatchesFrozenContract()
    {
        // 真实模块与Kestrel，无模拟Gateway。
        using var query = new QueryFixture();
        // 服务器固定合法身份，不模拟用户登录或OIDC。
        await using var fixture = await QueryHttpFixture.StartAsync(query, "platform.operator");
        Assert.AreEqual("/api/v1/semantic/queries", fixture.QueryPath);
        // 单数错误路径不应成为保留的非合同入口。
        using var old = await fixture.Client.PostAsJsonAsync("/api/v1/semantic/query", new { });
        Assert.AreEqual(HttpStatusCode.NotFound, old.StatusCode);
    }

    /// <summary>缺少或伪造原生CSRF令牌时必须先拒绝且真实保存安全审计。</summary>
    [TestMethod]
    [DataRow(null)]
    [DataRow("synthetic-forged-csrf")]
    public async Task QueryPostRequiresNativeCsrf(string? token)
    {
        // 真实发布能确保旧错误实现确实会查询成功，避免404遮住CSRF缺陷。
        using var query = new QueryFixture();
        // 正式源、图与PG活动指针均已真实就绪。
        var release = await query.PublishAsync();
        // 角色允许读取，隔离防伪检查。
        await using var fixture = await QueryHttpFixture.StartAsync(query, "platform.operator");
        if (token is not null) fixture.Client.DefaultRequestHeaders.Add("X-CSRF-TOKEN", token);
        // 动态发现仅用于在修复路由前仍能单独复现安全缺陷；另有精确路由断言。
        using var response = await fixture.Client.PostAsJsonAsync(fixture.QueryPath, query.Plan(release));
        Assert.AreEqual(HttpStatusCode.Forbidden, response.StatusCode);
        Assert.AreEqual(1, await AuditCountAsync(query, "csrf.denied"));
        Assert.AreEqual(0, await AuditCountAsync(query, "semantic.query"));
    }

    /// <summary>合法原生防伪令牌仍不能绕过异源或畸形Origin。</summary>
    [TestMethod]
    [DataRow("https://external.invalid")]
    [DataRow("http://platform.test/path")]
    [DataRow("null")]
    public async Task QueryPostRequiresExactOrigin(string origin)
    {
        // 实际资产存在，成功查询依赖全部真实。
        using var query = new QueryFixture();
        // 发布先完成，不把未发布错误误认为来源拦截。
        var release = await query.PublishAsync();
        // 只变更待测Origin，其他前提合法。
        await using var fixture = await QueryHttpFixture.StartAsync(query, "platform.operator");
        await fixture.SetCsrfAsync();
        fixture.Client.DefaultRequestHeaders.TryAddWithoutValidation("Origin", origin);
        // 对生产映射的真实HTTP路由发送请求。
        using var response = await fixture.Client.PostAsJsonAsync(fixture.QueryPath, query.Plan(release));
        Assert.AreEqual(HttpStatusCode.Forbidden, response.StatusCode);
        Assert.AreEqual(1, await AuditCountAsync(query, "csrf.denied"));
        Assert.AreEqual(0, await AuditCountAsync(query, "semantic.query"));
    }

    /// <summary>匿名或错误角色的畸形JSON必须先返回401/已审计403，而非绑定400。</summary>
    [TestMethod]
    [DataRow(null, 401)]
    [DataRow("unapproved-role", 403)]
    public async Task AuthenticationAndAuthorizationPrecedeBodyBinding(string? role, int expected)
    {
        // 拒绝审计必须真实落本轮临时PG。
        using var query = new QueryFixture();
        // 固定角色由测试服务器决定，客户端不可选身份。
        await using var fixture = await QueryHttpFixture.StartAsync(query, role);
        // 截断JSON能够暴露先绑定后授权的顺序缺陷。
        using var response = await fixture.Client.PostAsync(fixture.QueryPath, new StringContent("{\"externalId\":\"synthetic-marker\",", Encoding.UTF8, "application/json"));
        Assert.AreEqual(expected, (int)response.StatusCode);
        Assert.AreEqual("application/problem+json", response.Content.Headers.ContentType?.MediaType);
        Assert.AreEqual(expected == 403 ? 1 : 0, await AuditCountAsync(query, "authorization.denied"));
        Assert.AreEqual(0, await AuditCountAsync(query, "semantic.query"));
        Assert.IsFalse((await response.Content.ReadAsStringAsync()).Contains("synthetic-marker", StringComparison.Ordinal));
    }

    /// <summary>所有正式查询路由有共同策略及明确Problem响应元数据。</summary>
    [TestMethod]
    public async Task QueryEndpointsDeclareAuthorizationAndProblems()
    {
        // 实际最小API EndpointDataSource，不能靠源码字符串代替元数据。
        using var query = new QueryFixture();
        // 只读取启动后真实端点元数据。
        await using var fixture = await QueryHttpFixture.StartAsync(query, "platform.operator");
        foreach (var endpoint in fixture.SemanticRoutes)
        {
            Assert.IsTrue(endpoint.Metadata.GetOrderedMetadata<IAuthorizeData>().Any(value => value.Policy == "semantic.read"));
            // 实际生产薄适配声明的响应类型与媒体类型。
            var responses = endpoint.Metadata.GetOrderedMetadata<IProducesResponseTypeMetadata>();
            Assert.IsTrue(responses.Any(value => value.StatusCode == 401 && value.ContentTypeMatches("application/problem+json")));
            Assert.IsTrue(responses.Any(value => value.StatusCode == 403 && value.ContentTypeMatches("application/problem+json")));
        }
    }

    /// <summary>授权、同源和原生防伪通过后才能查询真实发布，响应为唯一完整DTO。</summary>
    [TestMethod]
    public async Task ValidQueryPostReturnsRealPublishedResult()
    {
        // 真实正式发布包含可验证来源。
        using var query = new QueryFixture();
        // 发布服务同时绑定真实能力版本。
        var release = await query.PublishAsync();
        // 固定可信principal只用于传输夹具，不宣称真实OIDC已测。
        await using var fixture = await QueryHttpFixture.StartAsync(query, "platform.viewer");
        await fixture.SetCsrfAsync();
        fixture.Client.DefaultRequestHeaders.Add("Origin", "http://platform.test");
        // 合法请求无需虚构CommandContext，原生POST仍受防伪保护。
        using var response = await fixture.Client.PostAsJsonAsync(fixture.QueryPath, query.Plan(release));
        Assert.AreEqual(HttpStatusCode.OK, response.StatusCode);
        // 实际JSON必须满足唯一合同的完整序列化边界。
        var result = await response.Content.ReadFromJsonAsync<SemanticQueryResult>();
        Assert.AreEqual(SemanticQueryStatus.Found, result!.Status);
        Assert.AreEqual(release.Manifest.ReleaseId, result.Snapshot.ReleaseId);
        Assert.IsNotEmpty(result.Evidence);
        Assert.AreEqual(1, await AuditCountAsync(query, "semantic.query"));
    }

    /// <summary>按当前随机组织读取真实已提交审计数，不使用捕获替身。</summary>
    private static Task<int> AuditCountAsync(QueryFixture query, string action) => query.Database.Database.SqlQuery<int>($"SELECT COUNT(*)::int AS \"Value\" FROM governance.audit_records WHERE \"OrganizationId\"={query.Author.OrganizationId} AND \"Action\"={action}").SingleAsync();
}

/// <summary>真实Kestrel夹具复用生产端点，固定principal与临时密钥只用于本测试。</summary>
internal sealed class QueryHttpFixture : IAsyncDisposable
{
    /// <summary>当前测试生命周期内的Web宿主。</summary>
    internal WebApplication App { get; private set; } = null!;

    /// <summary>真实回环客户端自动保持原生防伪Cookie。</summary>
    internal HttpClient Client { get; private set; } = null!;

    /// <summary>生产映射的四项正式查询路由，不包含fixture辅助入口。</summary>
    internal RouteEndpoint[] SemanticRoutes => ((IEndpointRouteBuilder)App).DataSources.SelectMany(value => value.Endpoints).OfType<RouteEndpoint>().Where(value => value.RoutePattern.RawText!.StartsWith("/api/v1/", StringComparison.Ordinal)).ToArray();

    /// <summary>实际接收唯一查询计划的生产端点，独立精确路由测试约束其拼写。</summary>
    internal string QueryPath => SemanticRoutes.Single(value => value.Metadata.GetMetadata<IAcceptsMetadata>()?.RequestType == typeof(SemanticQueryPlan)).RoutePattern.RawText!;

    /// <summary>创建固定身份的真实Kestrel，并注入本轮真实业务和审计实例。</summary>
    internal static async Task<QueryHttpFixture> StartAsync(QueryFixture query, string? role)
    {
        // 生命周期容器不保存任何认证材料到磁盘。
        var fixture = new QueryHttpFixture();
        // 本轮服务端固定随机回环端口。
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        builder.Logging.ClearProviders();
        builder.Services.AddDataProtection().UseEphemeralDataProtectionProvider();
        builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme).AddCookie();
        builder.Services.AddG2Authorization();
        builder.Services.AddAntiforgery(options => options.HeaderName = "X-CSRF-TOKEN");
        builder.Services.Configure<PlatformSecurityOptions>(options => options.PublicOrigin = "http://platform.test");
        builder.Services.AddSingleton(query.Gateway);
        builder.Services.AddSingleton(query.Evidence);
        builder.Services.AddSingleton(query.Audit);
        fixture.App = builder.Build();
        fixture.App.Use(async (context, next) =>
        {
            context.User = role is null ? new ClaimsPrincipal(new ClaimsIdentity()) : new ClaimsPrincipal(new ClaimsIdentity([new Claim("sub", query.Author.SubjectId), new Claim("organization_id", query.Author.OrganizationId), new Claim("site_ids", "site-a"), new Claim("site_ids", "site-b"), new Claim(ClaimTypes.Role, role)], "query-fixture"));
            context.Items["CorrelationId"] = query.Author.CorrelationId;
            try { await next(context); }
            catch (Exception) when (!context.RequestAborted.IsCancellationRequested) { await PlatformProblem.Create(context, 500, "internal_failure").ExecuteAsync(context); }
        });
        fixture.App.UseAuthorization();
        fixture.App.MapGet("/fixture/csrf", (HttpContext context, IAntiforgery antiforgery) => Results.Text(antiforgery.GetAndStoreTokens(context).RequestToken!));
        fixture.App.MapSemanticEndpoints();
        await fixture.App.StartAsync();
        fixture.Client = new HttpClient(new HttpClientHandler { UseProxy = false }) { BaseAddress = new Uri(fixture.App.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single()) };
        return fixture;
    }

    /// <summary>仅通过原生服务签发并在内存保存防伪令牌，不输出其值。</summary>
    internal async Task SetCsrfAsync()
    {
        // 原生令牌对应同一HttpClient保持的Cookie。
        var token = await Client.GetStringAsync("/fixture/csrf");
        Client.DefaultRequestHeaders.Add("X-CSRF-TOKEN", token);
    }

    /// <summary>释放本轮真实回环服务及客户端。</summary>
    public async ValueTask DisposeAsync()
    {
        Client.Dispose();
        await App.DisposeAsync();
    }
}

/// <summary>仅测试用的响应元数据比较，媒体类型来自实际Endpoint metadata。</summary>
internal static class ResponseMetadataChecks
{
    /// <summary>检查声明媒体类型，避免将HTTP状态一致误当Problem合同一致。</summary>
    internal static bool ContentTypeMatches(this IProducesResponseTypeMetadata metadata, string contentType) => metadata.ContentTypes.Contains(contentType, StringComparer.Ordinal);
}
