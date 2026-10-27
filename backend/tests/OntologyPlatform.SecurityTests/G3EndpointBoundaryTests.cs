using System.Net;
using System.Text;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using OntologyPlatform.Api.G2;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.SecurityTests;

/// <summary>生产M1路由的真实HTTP安全边界，业务替身一旦被调用即失败。</summary>
[TestClass]
public sealed class G3EndpointBoundaryTests
{
    /// <summary>匿名和只读角色不能借畸形JSON越过绑定前授权。</summary>
    [TestMethod]
    public async Task AssessmentAuthorizesBeforeMalformedBody()
    {
        // 每次使用独立Kestrel随机端口及无业务成功能力的服务。
        foreach (var role in new string?[] { null, "platform.viewer" })
        {
            await using var app = Host(role);
            await app.StartAsync();
            // 不持有Cookie或令牌，只有明确的合成角色。
            using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
            using var response = await client.PostAsync("/api/v1/ontology-drafts/draft/assessments",
                new StringContent("{", Encoding.UTF8, "application/json"));
            Assert.AreEqual(role is null ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, response.StatusCode);
        }
    }

    /// <summary>只读比较POST仍需同源防伪，不能把查询端点变成无保护代理。</summary>
    [TestMethod]
    public async Task ComparisonRejectsMissingCsrfBeforeBusiness()
    {
        await using var app = Host("platform.viewer");
        await app.StartAsync();
        // 对真实路由提交完整固定版本定位，不含外部查询或地址。
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
        client.DefaultRequestHeaders.Add("Origin", "http://platform.test");
        using var response = await client.PostAsync("/api/v1/ontology-comparisons", new StringContent(
            """{"from":{"kind":"DRAFT","id":"draft","revision":1},"to":{"kind":"DRAFT","id":"draft","revision":2}}""",
            Encoding.UTF8, "application/json"));
        Assert.AreEqual(HttpStatusCode.Forbidden, response.StatusCode);
    }

    /// <summary>在真实生产路由上创建不允许业务成功的回环宿主。</summary>
    /// <param name="role">固定测试角色，空值为匿名。</param>
    /// <returns>由用例启动和释放的宿主。</returns>
    private static WebApplication Host(string? role)
    {
        // 沿用既有HTTP前置验证夹具，不代表真实OIDC或业务数据库验收。
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        builder.Logging.ClearProviders();
        builder.Services.AddDataProtection().UseEphemeralDataProtectionProvider();
        builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme).AddCookie();
        builder.Services.AddG2Authorization();
        builder.Services.AddAntiforgery(options => options.HeaderName = "X-CSRF-TOKEN");
        builder.Services.Configure<PlatformSecurityOptions>(options => options.PublicOrigin = "http://platform.test");
        builder.Services.AddSingleton<IAuditTrail>(new G2AuditCapture());
        builder.Services.AddSingleton<IG3OntologyService, RejectBusiness>();
        // 身份仅来自宿主固定夹具，不从请求头/正文接收主体。
        var app = builder.Build();
        app.Use((context, next) =>
        {
            context.User = G2HttpFixture.Principal(role);
            return next(context);
        });
        app.UseAuthorization();
        app.MapG3Endpoints();
        return app;
    }

    /// <summary>仅在前置安全失效时抛错，测试不得依赖伪造业务成功。</summary>
    private sealed class RejectBusiness : IG3OntologyService
    {
        /// <summary>安全用例不应读取支持策略。</summary>
        public SemanticSupportProfile GetProfile() => throw new InvalidOperationException();

        /// <summary>安全用例不应执行真实评估。</summary>
        public Task<SemanticAssessment> AssessAsync(ActorContext actor, string draftId, ValidateDraftRequest request, CancellationToken cancellationToken)
            => throw new InvalidOperationException();

        /// <summary>安全用例不应读取评估。</summary>
        public Task<SemanticAssessment> ReadAssessmentAsync(ActorContext actor, string assessmentId, CancellationToken cancellationToken)
            => throw new InvalidOperationException();

        /// <summary>安全用例不应进入比较。</summary>
        public Task<SourceComparison[]> CompareAsync(ActorContext actor, CompareVersionsRequest request, CancellationToken cancellationToken)
            => throw new InvalidOperationException();
    }
}
