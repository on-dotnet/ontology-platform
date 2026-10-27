using System.Net.Http.Json;
using System.Text;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using OntologyPlatform.Api.G2;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SecurityTests;

/// <summary>通过正式编辑路由验证绑定前权限及真实防伪后的修订头门禁。</summary>
[TestClass]
public sealed class G3M2EndpointTests
{
    /// <summary>未经授权者的畸形正文不能进入绑定或业务。</summary>
    /// <param name="role">宿主固定的合成角色，空值为匿名。</param>
    /// <param name="status">正式权限边界状态。</param>
    [TestMethod]
    [DataRow(null, 401)]
    [DataRow("platform.viewer", 403)]
    public async Task EditAuthorizesBeforeMalformedBody(string? role, int status)
    {
        await using var app = Host(role);
        await app.StartAsync();
        // 使用实际随机端口，既不模拟HTTP响应也不提供业务成功替身。
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
        using var response = await client.PostAsync("/api/v1/ontology-drafts/m2/edits", new StringContent("{", Encoding.UTF8, "application/json"));
        Assert.AreEqual(status, (int)response.StatusCode);
    }

    /// <summary>仅在真实CSRF有效后验证缺头、弱头和过期头。</summary>
    /// <param name="etag">提交的合成修订头。</param>
    /// <param name="status">预期前置失败状态。</param>
    [TestMethod]
    [DataRow(null, 428)]
    [DataRow("W/\"2\"", 400)]
    [DataRow("\"1\"", 409)]
    public async Task EditRequiresStrongMatchingRevision(string? etag, int status)
    {
        await using var app = Host("platform.operator");
        await app.StartAsync();
        // 原生Cookie仅保留在当前HttpClient内存，不写证据或源码。
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
        // 原生Antiforgery令牌确保失败确实来自修订门禁。
        var token = await client.GetFromJsonAsync<string>("/m2-token");
        client.DefaultRequestHeaders.Add("X-CSRF-TOKEN", token);
        client.DefaultRequestHeaders.Add("Origin", "http://platform.test");
        if (etag is not null) client.DefaultRequestHeaders.TryAddWithoutValidation("If-Match", etag);
        using var response = await client.PostAsJsonAsync("/api/v1/ontology-drafts/m2/edits", new EditDraftRequest
        {
            Edit = new SemanticEdit { SubjectIri = "urn:m2:C", PredicateIri = "http://www.w3.org/2000/01/rdf-schema#label", NewObject = new RdfTerm { Kind = RdfTermKind.Literal, Value = "设备" } },
            Command = G2HttpFixture.Command()
        });
        Assert.AreEqual(status, (int)response.StatusCode);
    }

    /// <summary>创建正式路由宿主，真实应用依赖为空使任何意外业务调用无法成功。</summary>
    /// <param name="role">宿主可信测试身份。</param>
    /// <returns>由调用方启动和释放的回环宿主。</returns>
    private static WebApplication Host(string? role)
    {
        // 采用与已有安全夹具相同的正式授权和原生防伪注册。
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        builder.Logging.ClearProviders();
        builder.Services.AddDataProtection().UseEphemeralDataProtectionProvider();
        builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme).AddCookie();
        builder.Services.AddG2Authorization();
        builder.Services.AddAntiforgery(options => options.HeaderName = "X-CSRF-TOKEN");
        builder.Services.Configure<PlatformSecurityOptions>(options => options.PublicOrigin = "http://platform.test");
        builder.Services.AddSingleton<IAuditTrail>(new G2AuditCapture());
        builder.Services.AddSingleton<IOntologyService>(new OntologyService(null!, null!, null!, TimeProvider.System));
        // 只有夹具固定身份，不允许请求指定role或actor。
        var app = builder.Build();
        app.Use((context, next) => { context.User = G2HttpFixture.Principal(role); return next(context); });
        app.UseAuthorization();
        app.MapOntologyEndpoints();
        app.MapGet("/m2-token", (Microsoft.AspNetCore.Http.HttpContext context, IAntiforgery antiforgery) =>
            Microsoft.AspNetCore.Http.Results.Json(antiforgery.GetAndStoreTokens(context).RequestToken));
        return app;
    }
}
