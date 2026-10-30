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

namespace OntologyPlatform.SecurityTests;

/// <summary>通过正式编辑路由验证绑定前权限及真实防伪后的修订头门禁。</summary>
[TestClass]
public sealed class G3M4EndpointTests
{
    /// <summary>未经授权者的畸形正文不能进入绑定或业务。</summary>
    /// <param name="role">宿主固定的合成角色，空值为匿名。</param>
    /// <param name="status">正式权限边界状态。</param>
    [TestMethod]
    [DataRow(null, 401)]
    [DataRow("platform.viewer", 403)]
    public async Task EditAuthorizesBeforeMalformedBody(string? role, int status)
    {
        // 启动可信角色对应的正式路由宿主，验证绑定正文前先拒绝越权。
        await using var app = Host(role);
        await app.StartAsync();
        // 使用实际随机端口，既不模拟HTTP响应也不提供业务成功替身。
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
        // 保留畸形请求的实际HTTP响应，以断言权限门禁优先于JSON解析。
        using var response = await client.PostAsync("/api/v1/ontology-drafts/m4/identity-time-edits", new StringContent("{", Encoding.UTF8, "application/json"));
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
        // 启动操作员正式路由宿主，使请求继续到修订头前置检查。
        await using var app = Host("platform.operator");
        await app.StartAsync();
        // 原生Cookie仅保留在当前HttpClient内存，不写证据或源码。
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
        // 原生Antiforgery令牌确保失败确实来自修订门禁。
        var token = await client.GetFromJsonAsync<string>("/m4-token");
        client.DefaultRequestHeaders.Add("X-CSRF-TOKEN", token);
        client.DefaultRequestHeaders.Add("Origin", "http://platform.test");
        if (etag is not null) client.DefaultRequestHeaders.TryAddWithoutValidation("If-Match", etag);
        // 读取真实CSRF校验后的HTTP响应，核对强修订头的失败关闭状态。
        using var response = await client.PostAsJsonAsync("/api/v1/ontology-drafts/m4/identity-time-edits", new IdentityTimeEditsRequest
        {
            Hashes = new SourceHashes(),
            Changes = [new VocabularyChange { SourceId = VocabularyEditSource.Vocabulary, Edit = new SemanticEdit { SubjectIri = "urn:synthetic:m4:C", PredicateIri = "urn:ontology-platform:semantics:externalIdentifier", NewObject = new RdfTerm { Kind = RdfTermKind.Literal, Value = "设备", Language = "zh" } } }],
            Command = G2HttpFixture.Command()
        });
        Assert.AreEqual(status, (int)response.StatusCode);
    }

    /// <summary>两个新POST均先执行身份/角色门禁，畸形正文不能提前绑定。</summary>
    /// <param name="path">正式M4报告或差异入口。</param>
    /// <param name="role">宿主可信角色，空为匿名。</param>
    /// <param name="status">实际授权拒绝状态。</param>
    [TestMethod]
    [DataRow("/api/v1/ontology-version-diffs", null, 401)]
    [DataRow("/api/v1/impact-reports", null, 401)]
    [DataRow("/api/v1/impact-reports", "platform.viewer", 403)]
    public async Task ImpactAuthorizesBeforeMalformedBody(string path, string? role, int status)
    {
        // 正式端点没有产品成功替身，意外调用应用服务即失败。
        await using var app = Host(role);
        await app.StartAsync();
        // 随机回环端口防止触碰真实开发入口。
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
        // 畸形JSON必须被原生授权中间件先拒绝。
        using var response = await client.PostAsync(path, new StringContent("{", Encoding.UTF8, "application/json"));
        Assert.AreEqual(status, (int)response.StatusCode);
    }

    /// <summary>已认证的两个POST即使正文有效，也必须具备原生防伪令牌。</summary>
    /// <param name="generate">是否验证具备幂等命令的报告写入。</param>
    [TestMethod]
    [DataRow(false)]
    [DataRow(true)]
    public async Task ImpactRequiresNativeCsrf(bool generate)
    {
        // 操作员有读写角色；没有防伪值才是本次拒绝的具体原因。
        await using var app = Host("platform.operator");
        await app.StartAsync();
        // 使用独立HttpClient保留宿主原生安全行为。
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
        client.DefaultRequestHeaders.Add("Origin", "http://platform.test");
        // 精确固定草稿引用满足Wire合同，避免绑定错误掩盖CSRF门禁。
        var version = new VersionRef { Kind = VersionRefKind.Draft, Id = "m4", Revision = 2 };
        // 正式POST根据两种合同分别序列化；服务若被误调用会立即失败。
        using var response = generate
            ? await client.PostAsJsonAsync("/api/v1/impact-reports", new GenerateImpactReportRequest { From = version, To = version, BaselineKind = ImpactBaselineKind.Initial, AssessmentId = null, Command = G2HttpFixture.Command() })
            : await client.PostAsJsonAsync("/api/v1/ontology-version-diffs", new CompareVersionsRequest { From = version, To = version });
        Assert.AreEqual(403, (int)response.StatusCode);
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
        builder.Services.AddSingleton<IG3ImpactService>(new NeverImpactService());
        builder.Services.AddSingleton<IG3IdentityTimeService>(new NeverIdentityTimeService());
        // 只有夹具固定身份，不允许请求指定role或actor。
        var app = builder.Build();
        app.Use((context, next) => { context.User = G2HttpFixture.Principal(role); return next(context); });
        app.UseAuthorization();
        app.MapIdentityTimeEndpoints();
        app.MapImpactEndpoints();
        app.MapGet("/m4-token", (Microsoft.AspNetCore.Http.HttpContext context, IAntiforgery antiforgery) =>
            Microsoft.AspNetCore.Http.Results.Json(antiforgery.GetAndStoreTokens(context).RequestToken));
        return app;
    }

    /// <summary>前置门禁测试禁止进入应用逻辑，不提供任何伪产品成功响应。</summary>
    private sealed class NeverIdentityTimeService : IG3IdentityTimeService
    {
        /// <summary>若未先执行读取授权则使测试立即失败。</summary>
        public Task<VocabularySnapshot> ReadIdentityTimeAsync(ActorContext actor, string draftId, CancellationToken cancellationToken) =>
            throw new AssertFailedException("Unexpected identity/time application invocation");

        /// <summary>若未先执行写入角色、防伪和修订校验则使测试失败。</summary>
        public Task<OntologyDraft> EditIdentityTimeAsync(ActorContext actor, string draftId, IdentityTimeEditsRequest request, CancellationToken cancellationToken) =>
            throw new AssertFailedException("Unexpected identity/time application invocation");

        /// <summary>正式版本不能在未授权时调用外部源或图。</summary>
        public Task<VocabularySnapshot> ReadReleaseIdentityTimeAsync(ActorContext actor, string releaseId, CancellationToken cancellationToken) =>
            throw new AssertFailedException("Unexpected identity/time application invocation");
    }

    /// <summary>只验证HTTP前置失败，禁止应用被调用或返回模拟产品成功。</summary>
    private sealed class NeverImpactService : IG3ImpactService
    {
        /// <summary>固定版本比较若越过前置失败，立即报告测试失败。</summary>
        public Task<VersionDiff> DiffAsync(ActorContext actor, CompareVersionsRequest request, CancellationToken cancellationToken) =>
            throw new AssertFailedException("Unexpected impact application invocation");

        /// <summary>报告生成若未先验证权限/CSRF，立即报告测试失败。</summary>
        public Task<ImpactReport> GenerateImpactAsync(ActorContext actor, GenerateImpactReportRequest request, CancellationToken cancellationToken) =>
            throw new AssertFailedException("Unexpected impact generation invocation");

        /// <summary>本夹具不提供报告读取成功实现。</summary>
        public Task<ImpactReport> ReadImpactAsync(ActorContext actor, string reportId, CancellationToken cancellationToken) =>
            throw new AssertFailedException("Unexpected impact reading invocation");
    }

}
