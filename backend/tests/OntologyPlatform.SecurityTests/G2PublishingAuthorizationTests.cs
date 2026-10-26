using System.Net;
using System.Text;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using OntologyPlatform.Api;
using OntologyPlatform.Api.G2;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.SecurityTests;

/// <summary>生产发布路由在正文绑定前授权，真实PG审计失败时保持失败关闭。</summary>
[TestClass]
public sealed class G2PublishingAuthorizationTests
{
    /// <summary>三个实际POST对匿名和错误角色畸形JSON分别返回401和持久审计后的403。</summary>
    [TestMethod]
    public async Task ActualPublishingPostsAuthorizeBeforeMalformedBindingAndPersistDenial()
    {
        // 正式迁移的随机PG库只保存本次拒绝审计。
        await using var database = await G2PgFixture.CreateAsync();
        // 分别覆盖匿名挑战和已认证但缺少发布角色的拒绝。
        foreach (var role in new string?[] { null, "platform.viewer" })
        {
            // 固定主体夹具只证明授权顺序，不代表OIDC验收。
            await using var app = Host(role, database.Writer);
            await app.StartAsync();
            // Kestrel为当前测试分配独立端口。
            using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
            // 三个真实发布POST逐个发送相同畸形载荷。
            // 每个生产发布写入口都保持相同前置安全顺序。
            foreach (var path in Paths())
            {
                // 畸形JSON不得在授权拒绝前被解析。
                using var response = await client.PostAsync(path, new StringContent("{", Encoding.UTF8, "application/json"));
                Assert.AreEqual(role is null ? HttpStatusCode.Unauthorized : HttpStatusCode.Forbidden, response.StatusCode, path);
            }
        }
        // 新连接读回证明403返回前真实审计已经提交。
        await using var reader = database.CreateDbContext();
        // 三条拒绝均保留可信完整双厂范围。
        var records = await reader.AuditRecords.AsNoTracking().ToArrayAsync();
        Assert.HasCount(3, records);
        Assert.IsTrue(records.All(row => row.Action == "authorization.denied" && row.Outcome == "denied" && row.Resource == "g2.api" && row.ScopeSiteIds!.SequenceEqual(new[] { "site-a", "site-b" })));
    }

    /// <summary>实际发布POST拒绝审计写入失败时输出安全500，不能提前发送403或执行发布。</summary>
    [TestMethod]
    public async Task ActualPublishingDenialAuditFailureFailsClosed()
    {
        // 故障只注入本测试拥有的随机PG数据库。
        await using var database = await G2PgFixture.CreateAsync();
        await using (var setup = database.CreateDbContext())
        {
            await setup.Database.ExecuteSqlRawAsync("""
                CREATE FUNCTION g2_probe.reject_publish_audit() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'synthetic-secret-marker'; END $$;
                CREATE TRIGGER reject_publish_audit BEFORE INSERT ON governance.audit_records
                FOR EACH ROW EXECUTE FUNCTION g2_probe.reject_publish_audit();
                """);
        }
        // 正式拒绝结果处理器调用真实Governance writer。
        await using var app = Host("platform.viewer", database.Writer);
        await app.StartAsync();
        // 随机回环入口只在本fixture生命周期内存在。
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
        // 每个生产发布写入口都保持相同前置安全顺序。
        foreach (var path in Paths())
        {
            // 每个发布POST均应在正文解析前传播审计故障到安全宿主边界。
            using var response = await client.PostAsync(path, new StringContent("{", Encoding.UTF8, "application/json"));
            Assert.AreEqual(HttpStatusCode.InternalServerError, response.StatusCode, path);
            Assert.IsFalse((await response.Content.ReadAsStringAsync()).Contains("synthetic-secret-marker", StringComparison.Ordinal));
        }
        Assert.AreEqual(0, await database.AuditCountAsync());
    }

    /// <summary>正确角色仍执行原生JSON绑定，合法DTO缺少防伪必须403且不进入业务服务。</summary>
    [TestMethod]
    public async Task AuthorizedPublishingPostsKeepBindingAndCsrfBoundaries()
    {
        // 本用例只检查HTTP前置条件，拒绝审计由内存观察器计数。
        var audit = new G2AuditCapture();
        // 每个生产发布写入口都保持相同前置安全顺序。
        foreach (var path in Paths())
        {
            // 审批要求auditor，其余两项要求operator。
            var role = path.Contains("approvals", StringComparison.Ordinal) ? "platform.auditor" : "platform.operator";
            // 业务替身的每个方法只抛异常，不能产生假成功。
            await using var app = Host(role, audit);
            await app.StartAsync();
            // 原生HTTP客户端不提供任何CSRF凭据。
            using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
            // 通过角色授权后畸形JSON仍应由原生绑定器拒绝。
            using var malformed = await client.PostAsync(path, new StringContent("{", Encoding.UTF8, "application/json"));
            Assert.AreEqual(HttpStatusCode.BadRequest, malformed.StatusCode, path);
            // 所有字段均来自唯一DTO，null分支按真实线协议显式提交。
            var body = path switch
            {
                "/api/v1/release-proposals" => """{"kind":"ROLLBACK","draftId":null,"draftRevision":null,"hashes":null,"validationReportId":null,"targetReleaseId":"release","targetManifestHash":"hash","command":{"commandId":"cmd","idempotencyKey":"idem","expectedRevision":1,"reason":"合成测试"}}""",
                "/api/v1/approvals/proposal/decisions" => """{"decision":"approve","command":{"commandId":"cmd","idempotencyKey":"idem","expectedRevision":1,"reason":"合成测试"}}""",
                _ => """{"proposalId":"proposal","expectedActivationRevision":1,"expectedActiveReleaseId":null,"command":{"commandId":"cmd","idempotencyKey":"idem","expectedRevision":1,"reason":"合成测试"}}"""
            };
            client.DefaultRequestHeaders.Add("Origin", "http://platform.test");
            // 合法绑定后必须首先执行真实防伪检查。
            using var csrf = await client.PostAsync(path, new StringContent(body, Encoding.UTF8, "application/json"));
            Assert.AreEqual(HttpStatusCode.Forbidden, csrf.StatusCode, path);
        }
        Assert.AreEqual(3, audit.Commands.Count);
        Assert.IsTrue(audit.Commands.All(command => command.Action == "csrf.denied"));
    }

    /// <summary>本次审查覆盖的三个生产发布写路由。</summary>
    /// <returns>仅用于测试调用的实际路由地址。</returns>
    private static string[] Paths() => ["/api/v1/release-proposals", "/api/v1/approvals/proposal/decisions", "/api/v1/release-activations"];

    /// <summary>创建生产发布路由与授权处理器的真实Kestrel固定主体夹具。</summary>
    /// <param name="role">测试启动时固定的平台角色；null表示匿名。</param>
    /// <param name="audit">真实持久写入器或仅观察HTTP前置检查的接收器。</param>
    /// <returns>由调用方启动和释放的隔离宿主。</returns>
    private static WebApplication Host(string? role, IAuditTrail audit)
    {
        // 只用本测试随机端口和临时内存数据保护密钥。
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        builder.Logging.ClearProviders();
        builder.Services.AddDataProtection().UseEphemeralDataProtectionProvider();
        builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme).AddCookie();
        builder.Services.AddG2Authorization();
        builder.Services.AddAntiforgery(options => options.HeaderName = "X-CSRF-TOKEN");
        builder.Services.Configure<PlatformSecurityOptions>(options => options.PublicOrigin = "http://platform.test");
        builder.Services.AddSingleton(audit);
        builder.Services.AddSingleton<IPublishingService, RejectBusiness>();
        builder.Services.AddSingleton<IReleaseCatalog, RejectBusiness>();
        // 宿主只把未知异常转换为固定安全Problem，不记录原始异常文本。
        var app = builder.Build();
        app.Use(async (context, next) =>
        {
            context.User = G2HttpFixture.Principal(role);
            try { await next(context); }
            catch (Exception) when (!context.RequestAborted.IsCancellationRequested)
            {
                await PlatformProblem.Create(context, 500, "internal_failure").ExecuteAsync(context);
            }
        });
        app.UseAuthorization();
        app.MapPublishingEndpoints();
        return app;
    }

    /// <summary>若前置安全边界失效立即失败，绝不伪造业务发布成功。</summary>
    private sealed class RejectBusiness : IPublishingService, IReleaseCatalog
    {
        /// <summary>本测试禁止到达发布提案读取。</summary>
        public Task<ReleaseProposal[]> ListProposalsAsync(ActorContext actor, CancellationToken cancellationToken) => throw new InvalidOperationException("业务边界不应到达。");

        /// <summary>本测试禁止创建真实或模拟成功提案。</summary>
        public Task<ReleaseProposal> CreateProposalAsync(ActorContext actor, CreateProposalRequest request, CancellationToken cancellationToken) => throw new InvalidOperationException("业务边界不应到达。");

        /// <summary>本测试禁止创建真实或模拟成功审批。</summary>
        public Task<ReleaseProposal> DecideAsync(ActorContext actor, string proposalId, ApprovalDecisionRequest request, CancellationToken cancellationToken) => throw new InvalidOperationException("业务边界不应到达。");

        /// <summary>本测试禁止创建真实或模拟成功激活。</summary>
        public Task<ReleaseActivation> ActivateAsync(ActorContext actor, ActivateReleaseRequest request, CancellationToken cancellationToken) => throw new InvalidOperationException("业务边界不应到达。");

        /// <summary>本测试禁止到达发布目录列表。</summary>
        public Task<ReleaseSummary[]> ListReleasesAsync(ActorContext actor, string? assetId, CancellationToken cancellationToken) => throw new InvalidOperationException("业务边界不应到达。");

        /// <summary>本测试禁止到达正式发布读取。</summary>
        public Task<ReleaseSummary> ReadAsync(ActorContext actor, string releaseId, CancellationToken cancellationToken) => throw new InvalidOperationException("业务边界不应到达。");

        /// <summary>本测试禁止到达活动发布解析。</summary>
        public Task<ReleaseSummary> ResolveAsync(ActorContext actor, string assetId, string? releaseId, CancellationToken cancellationToken) => throw new InvalidOperationException("业务边界不应到达。");
    }
}
