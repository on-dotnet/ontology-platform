using System.Net;
using System.Net.Http.Json;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Authorization.Policy;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Api;
using OntologyPlatform.Api.G2;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.SecurityTests;

/// <summary>通过真实Kestrel与原生防伪验证G2共同HTTP安全边界。</summary>
[TestClass]
public sealed class G2SecurityTests
{
    /// <summary>未登录与缺少权限的身份均不能进入业务委托。</summary>
    /// <param name="role">仅测试宿主固定配置的角色。</param>
    /// <param name="status">预期拒绝状态。</param>
    /// <returns>真实HTTP边界检查任务。</returns>
    [TestMethod]
    [DataRow(null, 401)]
    [DataRow("platform.viewer", 403)]
    public async Task IdentityBoundaryRejectsBeforeBusiness(string? role, int status)
    {
        // 每个用例拥有独立回环宿主，身份从固定服务器fixture注入。
        await using var fixture = await G2HttpFixture.StartAsync(role);
        // 使用真实HTTP响应核对状态和无业务副作用。
        using var response = await fixture.Client.PostAsJsonAsync("/write", G2HttpFixture.Command());
        Assert.AreEqual(status, (int)response.StatusCode);
        Assert.AreEqual(0, fixture.BusinessCalls);
        Assert.AreEqual(status == 403 ? 1 : 0, fixture.Audit.Commands.Count);
        Assert.AreEqual("no-store", response.Headers.CacheControl?.ToString());
        Assert.IsFalse(response.Headers.Contains("X-Audit-Id"));
    }

    /// <summary>四个共同具名策略按批准平台角色独立执行。</summary>
    /// <param name="role">可信服务器角色。</param>
    /// <param name="policy">被验证策略。</param>
    /// <param name="status">期望响应状态。</param>
    /// <returns>真实授权检查任务。</returns>
    [TestMethod]
    [DataRow("platform.viewer", "semantic.read", 200)]
    [DataRow("platform.operator", "semantic.read", 200)]
    [DataRow("platform.auditor", "semantic.read", 200)]
    [DataRow("platform.operator", "ontology.edit", 200)]
    [DataRow("platform.auditor", "ontology.edit", 403)]
    [DataRow("platform.auditor", "release.approve", 200)]
    [DataRow("platform.operator", "release.approve", 403)]
    [DataRow("platform.operator", "release.activate", 200)]
    [DataRow("platform.auditor", "release.activate", 403)]
    public async Task SharedPoliciesMatchApprovedRoles(string role, string policy, int status)
    {
        // 每个策略使用同一正式注册入口。
        await using var fixture = await G2HttpFixture.StartAsync(role, policy);
        // GET不需要防伪，但必须执行相同具名授权。
        using var response = await fixture.Client.GetAsync("/read");
        Assert.AreEqual(status, (int)response.StatusCode);
    }

    /// <summary>合法防伪令牌不能绕过外部或畸形Origin。</summary>
    /// <param name="origin">合成不可信来源。</param>
    /// <returns>真实Origin拒绝检查任务。</returns>
    [TestMethod]
    [DataRow("https://external.invalid")]
    [DataRow("null")]
    [DataRow("http://platform.test/path")]
    [DataRow("http://platform.test.evil.invalid")]
    [DataRow("http://platform.test,http://platform.test")]
    public async Task OriginMustBeExactOrigin(string origin)
    {
        // 正确角色与原生防伪先成立，单独隔离来源边界。
        await using var fixture = await G2HttpFixture.StartAsync("platform.operator");
        await fixture.SetCsrfAsync();
        fixture.Client.DefaultRequestHeaders.TryAddWithoutValidation("Origin", origin);
        // 真实HTTP响应仅用于状态和公开错误边界断言。
        using var response = await fixture.Client.PostAsJsonAsync("/write", G2HttpFixture.Command());
        Assert.AreEqual(HttpStatusCode.Forbidden, response.StatusCode);
        Assert.AreEqual(0, fixture.BusinessCalls);
        Assert.AreEqual(1, fixture.Audit.Commands.Count);
    }

    /// <summary>缺少或伪造防伪令牌均由原生服务拒绝。</summary>
    /// <param name="token">合成无效令牌或空值。</param>
    /// <returns>真实防伪检查任务。</returns>
    [TestMethod]
    [DataRow(null)]
    [DataRow("synthetic-secret-marker")]
    public async Task NativeCsrfRejectsMissingOrInvalidToken(string? token)
    {
        // 固定有写权限身份避免角色检查遮挡防伪失败。
        await using var fixture = await G2HttpFixture.StartAsync("platform.operator");
        if (token is not null)
        {
            fixture.Client.DefaultRequestHeaders.Add("X-CSRF-TOKEN", token);
        }
        // 真实HTTP响应仅用于状态和公开错误边界断言。
        using var response = await fixture.Client.PostAsJsonAsync("/write", G2HttpFixture.Command());
        Assert.AreEqual(HttpStatusCode.Forbidden, response.StatusCode);
        Assert.AreEqual(0, fixture.BusinessCalls);
        Assert.IsFalse((await response.Content.ReadAsStringAsync()).Contains("synthetic-secret-marker", StringComparison.Ordinal));
    }

    /// <summary>修订头必须为单个强ETag且与命令一致。</summary>
    /// <param name="etag">请求修订头。</param>
    /// <param name="status">预期状态。</param>
    /// <returns>修订边界检查任务。</returns>
    [TestMethod]
    [DataRow(null, 428)]
    [DataRow("W/\"2\"", 400)]
    [DataRow("*", 400)]
    [DataRow("\"-1\"", 400)]
    [DataRow("\"02\"", 400)]
    [DataRow("\"2\", \"3\"", 400)]
    [DataRow("\"3\"", 409)]
    [DataRow("\"2\"", 200)]
    public async Task RevisionPreconditionMatchesCommand(string? etag, int status)
    {
        // 原生防伪通过之后才能准确观察修订前置条件。
        await using var fixture = await G2HttpFixture.StartAsync("platform.operator");
        await fixture.SetCsrfAsync();
        if (etag is not null)
        {
            fixture.Client.DefaultRequestHeaders.TryAddWithoutValidation("If-Match", etag);
        }
        fixture.Client.DefaultRequestHeaders.Add("Origin", "http://platform.test");
        // 真实HTTP响应仅用于状态和公开错误边界断言。
        using var response = await fixture.Client.PostAsJsonAsync("/revise", G2HttpFixture.Command());
        Assert.AreEqual(status, (int)response.StatusCode, "宿主异常类型：" + fixture.PropagatedFailureType?.Name);
        Assert.AreEqual(status == 200 ? 1 : 0, fixture.BusinessCalls);
        if (status == 200)
        {
            Assert.AreEqual("\"3\"", response.Headers.ETag?.Tag);
            Assert.IsFalse(response.Headers.Contains("X-Audit-Id"));
        }
    }

    /// <summary>空白、越界和负修订命令不能进入应用层。</summary>
    /// <param name="field">被破坏的字段。</param>
    /// <returns>命令校验任务。</returns>
    [TestMethod]
    [DataRow("command")]
    [DataRow("key")]
    [DataRow("reason")]
    [DataRow("revision")]
    public async Task InvalidCommandsNeverInvokeBusiness(string field)
    {
        // 防伪及角色均合法，失败唯一来自命令边界。
        await using var fixture = await G2HttpFixture.StartAsync("platform.operator");
        await fixture.SetCsrfAsync();
        // 从规范命令仅修改被测字段，确保正反例可对照。
        var command = G2HttpFixture.Command();
        command = field switch
        {
            "command" => command with { CommandId = " " },
            "key" => command with { IdempotencyKey = new string('a', 65) },
            "reason" => command with { Reason = new string('a', 501) },
            _ => command with { ExpectedRevision = -1 }
        };
        // 真实HTTP响应仅用于状态和公开错误边界断言。
        using var response = await fixture.Client.PostAsJsonAsync("/write", command);
        Assert.AreEqual(HttpStatusCode.BadRequest, response.StatusCode);
        Assert.AreEqual(0, fixture.BusinessCalls);
    }

    /// <summary>客户端身份头不影响从可信Claims得到的完整主体与范围。</summary>
    /// <returns>可信身份投影检查任务。</returns>
    [TestMethod]
    public async Task ActorIgnoresClientIdentityHeaders()
    {
        // fixture身份在服务器构造，客户端无法选择角色或组织。
        await using var fixture = await G2HttpFixture.StartAsync("platform.viewer");
        fixture.Client.DefaultRequestHeaders.Add("X-Subject-Id", "attacker");
        fixture.Client.DefaultRequestHeaders.Add("X-Organization-Id", "other");
        // 返回值直接来自guard投影，验证实际HTTP数据。
        var actor = await fixture.Client.GetFromJsonAsync<ActorContext>("/read");
        Assert.AreEqual("fixture-subject", actor!.SubjectId);
        Assert.AreEqual("org-demo", actor.OrganizationId);
        CollectionAssert.AreEqual(new[] { "site-a", "site-b" }, actor.SiteIds);
        CollectionAssert.AreEqual(new[] { "platform.viewer" }, actor.Roles);
    }

    /// <summary>端点授权元数据必须在畸形JSON绑定前返回统一401。</summary>
    /// <returns>真实匿名HTTP请求的授权顺序验证任务。</returns>
    [TestMethod]
    public async Task MiddlewareRejectsAnonymousBeforeMalformedBodyBinding()
    {
        // 固定匿名身份完全由测试宿主决定，客户端不能通过请求头选择身份。
        await using var fixture = await G2HttpFixture.StartAsync(null);
        // 合成敏感标记位于故意截断的JSON，不应被绑定器或错误响应回显。
        using var body = new StringContent("{\"commandId\":\"synthetic-secret-marker\",", Encoding.UTF8, "application/json");
        // 使用附带RequireAuthorization的真实最小API路由。
        using var response = await fixture.Client.PostAsync("/protected-write", body);
        Assert.AreEqual(HttpStatusCode.Unauthorized, response.StatusCode);
        Assert.AreEqual("application/problem+json", response.Content.Headers.ContentType?.MediaType);
        Assert.AreEqual("no-store", response.Headers.CacheControl?.ToString());
        // 读取实际Problem字段，避免将框架空401视为满足错误合同。
        var problem = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.AreEqual("authentication_required", problem.GetProperty("code").GetString());
        Assert.AreEqual("fixture-correlation", problem.GetProperty("correlationId").GetString());
        Assert.IsFalse(problem.GetRawText().Contains("synthetic-secret-marker", StringComparison.Ordinal));
        Assert.AreEqual(0, fixture.BusinessCalls);
        Assert.AreEqual(0, fixture.Audit.Commands.Count);
    }

    /// <summary>错误角色的畸形JSON请求必须在绑定前完成真实拒绝审计再返回统一403。</summary>
    /// <returns>真实Kestrel、原生授权及治理PG的组合验证任务。</returns>
    [TestMethod]
    public async Task MiddlewarePersistsForbiddenAuditBeforeMalformedBodyBinding()
    {
        // 使用本轮新建随机数据库与正式治理writer，不用内存审计冒充持久事实。
        await using var database = await G2PgFixture.CreateAsync();
        // 身份只有viewer，端点要求与guard相同的ontology.edit策略。
        await using var fixture = await G2HttpFixture.StartAsync("platform.viewer", audit: database.Writer);
        // 请求正文非法，若授权顺序错误会先返回400或泄露解析细节。
        using var body = new StringContent("{\"commandId\":\"synthetic-secret-marker\",", Encoding.UTF8, "application/json");
        // 先观察传输安全结果，再使用独立数据库连接读取真实已提交审计。
        using var response = await fixture.Client.PostAsync("/protected-write", body);
        Assert.AreEqual(HttpStatusCode.Forbidden, response.StatusCode);
        Assert.AreEqual("application/problem+json", response.Content.Headers.ContentType?.MediaType);
        Assert.AreEqual("no-store", response.Headers.CacheControl?.ToString());
        // 固定安全Problem不包含JSON正文或框架解析异常。
        var problem = await response.Content.ReadFromJsonAsync<JsonElement>();
        Assert.AreEqual("authorization_denied", problem.GetProperty("code").GetString());
        Assert.IsFalse(problem.GetRawText().Contains("synthetic-secret-marker", StringComparison.Ordinal));
        // 独立读取上下文确保403之前审计已经提交。
        await using var reader = database.CreateDbContext();
        // 使用真实持久记录核对完整可信身份和两个厂区。
        var record = await reader.AuditRecords.AsNoTracking().SingleAsync();
        Assert.AreEqual("fixture-subject", record.Actor);
        Assert.AreEqual("authorization.denied", record.Action);
        Assert.AreEqual("g2.api", record.Resource);
        Assert.AreEqual("denied", record.Outcome);
        Assert.AreEqual("org-demo", record.OrganizationId);
        CollectionAssert.AreEqual(new[] { "site-a", "site-b" }, record.ScopeSiteIds);
        Assert.IsNull(record.SiteId);
        Assert.AreEqual(0, fixture.BusinessCalls);
    }

    /// <summary>真实PG拒绝审计失败必须传播给宿主，不得伪装成已经审计的403。</summary>
    /// <returns>真实拒绝审计故障与安全宿主响应验证任务。</returns>
    [TestMethod]
    public async Task MiddlewareAuditFailurePropagatesWithoutFalse403()
    {
        // 只在本测试随机库注入审计写入故障，不碰任何保留数据库。
        await using var database = await G2PgFixture.CreateAsync();
        // 故障触发器归属于测试schema，在正式治理表上阻断本次测试写入。
        await using (var setup = database.CreateDbContext())
        {
            await setup.Database.ExecuteSqlRawAsync("""
                CREATE FUNCTION g2_probe.reject_middleware_audit() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'synthetic-secret-marker'; END $$;
                CREATE TRIGGER reject_middleware_audit BEFORE INSERT ON governance.audit_records
                FOR EACH ROW EXECUTE FUNCTION g2_probe.reject_middleware_audit();
                """);
        }
        // 测试宿主仅观察向外传播的异常类型，并以原平台Problem格式失败关闭。
        await using var fixture = await G2HttpFixture.StartAsync("platform.viewer", audit: database.Writer);
        // 畸形JSON仍不应参与失败路径，审计故障发生在授权中间件。
        using var body = new StringContent("{", Encoding.UTF8, "application/json");
        // 收到安全500证明没有提前写403或吞掉审计异常。
        using var response = await fixture.Client.PostAsync("/protected-write", body);
        Assert.AreEqual(HttpStatusCode.InternalServerError, response.StatusCode);
        Assert.AreEqual(typeof(DbUpdateException), fixture.PropagatedFailureType);
        Assert.AreEqual("application/problem+json", response.Content.Headers.ContentType?.MediaType);
        Assert.IsFalse((await response.Content.ReadAsStringAsync()).Contains("synthetic-secret-marker", StringComparison.Ordinal));
        Assert.AreEqual(0, await database.AuditCountAsync());
        Assert.AreEqual(0, fixture.BusinessCalls);
    }

    /// <summary>授权成功继续执行原生绑定和guard，不跳过防伪或提前写响应。</summary>
    /// <param name="malformed">是否故意发送畸形JSON。</param>
    /// <returns>真实成功分支与绑定顺序验证任务。</returns>
    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public async Task MiddlewareSuccessContinuesToNativeBindingAndGuard(bool malformed)
    {
        // 固定operator满足端点与guard共同具名策略。
        await using var fixture = await G2HttpFixture.StartAsync("platform.operator");
        await fixture.SetCsrfAsync();
        // 授权成功后畸形正文仍由原生绑定器拒绝，合法正文才进入业务。
        using var response = malformed
            ? await fixture.Client.PostAsync("/protected-write", new StringContent("{", Encoding.UTF8, "application/json"))
            : await fixture.Client.PostAsJsonAsync("/protected-write", G2HttpFixture.Command());
        Assert.AreEqual(malformed ? HttpStatusCode.BadRequest : HttpStatusCode.OK, response.StatusCode, "宿主异常类型：" + fixture.PropagatedFailureType?.Name);
        Assert.AreEqual(malformed ? 0 : 1, fixture.BusinessCalls);
        Assert.AreEqual(0, fixture.Audit.Commands.Count);
    }

    /// <summary>授权中间件结果处理不能吞掉请求取消，也不能提前发送挑战响应。</summary>
    /// <returns>原生结果处理契约的取消传播验证任务。</returns>
    [TestMethod]
    public async Task MiddlewareCancellationPropagatesBeforeResponseStarts()
    {
        // 直接调用实际注册的处理器以观察取消异常，不把断开的HTTP连接作为成功断言。
        await using var fixture = await G2HttpFixture.StartAsync(null);
        // 已取消信号在任何响应或审计之前应被传播。
        var context = new DefaultHttpContext { RequestServices = fixture.App.Services, RequestAborted = new CancellationToken(true) };
        // 取生产注册入口得到的结果处理器，而不是测试手写替身。
        var handler = fixture.App.Services.GetRequiredService<IAuthorizationMiddlewareResultHandler>();
        // 挑战结果对应未认证，仍应保留取消语义。
        var policy = new AuthorizationPolicyBuilder().RequireAuthenticatedUser().Build();
        await Assert.ThrowsExactlyAsync<OperationCanceledException>(() => handler.HandleAsync(_ => Task.CompletedTask, context, policy, PolicyAuthorizationResult.Challenge()));
        Assert.IsFalse(context.Response.HasStarted);
    }

    /// <summary>拒绝审计的未预料异常应原样传播给宿主而非写出403或空成功。</summary>
    /// <returns>实际结果处理器的未知审计故障传播验证任务。</returns>
    [TestMethod]
    public async Task MiddlewareUnexpectedAuditFailurePropagatesUnchanged()
    {
        // 固定viewer只触发拒绝分支，异常由审计依赖真实抛出。
        await using var fixture = await G2HttpFixture.StartAsync("platform.viewer");
        // 合成异常仅保存在测试内存，不作为响应正文或日志输出。
        var failure = new InvalidOperationException("synthetic-secret-marker");
        fixture.Audit.Failure = failure;
        // 请求服务与可信身份结构同真实服务器请求。
        var context = new DefaultHttpContext { RequestServices = fixture.App.Services, User = G2HttpFixture.Principal("platform.viewer") };
        // 由正式注册取得实际处理器，验证它不会替换依赖异常。
        var handler = fixture.App.Services.GetRequiredService<IAuthorizationMiddlewareResultHandler>();
        // 同一具名策略的核心角色要求用于构造原生拒绝结果。
        var policy = new AuthorizationPolicyBuilder().RequireRole("platform.operator").Build();
        // 捕获原异常对象，避免默认中间件缺认证配置时的其他InvalidOperationException造成假阳性。
        var observed = await Assert.ThrowsExactlyAsync<InvalidOperationException>(() => handler.HandleAsync(_ => Task.CompletedTask, context, policy, PolicyAuthorizationResult.Forbid()));
        Assert.AreSame(failure, observed);
        Assert.IsFalse(context.Response.HasStarted);
        Assert.AreEqual(StatusCodes.Status200OK, context.Response.StatusCode);
    }

    /// <summary>业务拒绝使用安全Problem，未预料故障和取消继续抛给宿主。</summary>
    /// <returns>异常映射与传播验证任务。</returns>
    [TestMethod]
    public async Task ControlledFailuresMapAndUnknownFailuresPropagate()
    {
        // 真实HTTP先验证可公开的受控业务错误。
        await using var fixture = await G2HttpFixture.StartAsync("platform.operator");
        // 真实HTTP响应仅用于状态和公开错误边界断言。
        using var response = await fixture.Client.GetAsync("/failure");
        Assert.AreEqual(HttpStatusCode.Conflict, response.StatusCode);
        Assert.IsTrue((await response.Content.ReadAsStringAsync()).Contains("revision_conflict", StringComparison.Ordinal));
        // 直调用仅验证异常传播语义，避免Kestrel将取消转换成连接关闭影响断言。
        var context = new DefaultHttpContext { RequestServices = fixture.App.Services, User = G2HttpFixture.Principal("platform.operator") };
        await Assert.ThrowsExactlyAsync<InvalidOperationException>(() => G2EndpointGuard.ReadAsync<string>(context, "semantic.read", (_, _) => throw new InvalidOperationException("synthetic-secret-marker")));
        await Assert.ThrowsExactlyAsync<OperationCanceledException>(() => G2EndpointGuard.ReadAsync<string>(context, "semantic.read", (_, _) => throw new OperationCanceledException()));
    }
}

/// <summary>只存在于测试程序集的固定可信身份与真实回环HTTP宿主。</summary>
internal sealed class G2HttpFixture : IAsyncDisposable
{
    /// <summary>本测试启动的Kestrel实例。</summary>
    public WebApplication App { get; private set; } = null!;

    /// <summary>自动保存原生防伪Cookie的回环客户端。</summary>
    public HttpClient Client { get; private set; } = null!;

    /// <summary>用于观察拒绝调用的测试审计接收器。</summary>
    public G2AuditCapture Audit { get; } = new();

    /// <summary>实际到达业务委托的次数。</summary>
    public int BusinessCalls { get; private set; }

    /// <summary>传播到测试宿主安全异常边界的类型，不保存原始异常正文。</summary>
    public Type? PropagatedFailureType { get; private set; }

    /// <summary>使用固定可信身份创建隔离宿主，产品不存在测试登录入口。</summary>
    /// <param name="role">启动时固定角色，null为匿名。</param>
    /// <param name="policy">读取接口的共同策略。</param>
    /// <param name="audit">可选真实Governance持久审计。</param>
    /// <returns>已经启动并拥有客户端的fixture。</returns>
    public static async Task<G2HttpFixture> StartAsync(string? role, string policy = "semantic.read", IAuditTrail? audit = null)
    {
        // 生命周期全部限定于本次测试对象。
        var fixture = new G2HttpFixture();
        // 原生Kestrel随机回环端口不接触开发入口。
        var builder = WebApplication.CreateBuilder();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        builder.Logging.ClearProviders();
        // 原生Cookie与防伪使用本fixture内存密钥，不读取或写入用户持久密钥环。
        builder.Services.AddDataProtection().UseEphemeralDataProtectionProvider();
        builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme).AddCookie();
        builder.Services.AddG2Authorization();
        builder.Services.AddAntiforgery(options => options.HeaderName = "X-CSRF-TOKEN");
        builder.Services.Configure<PlatformSecurityOptions>(options => options.PublicOrigin = "http://platform.test");
        builder.Services.AddSingleton<IAuditTrail>(audit ?? fixture.Audit);
        fixture.App = builder.Build();
        fixture.App.Use(async (context, next) =>
        {
            context.User = Principal(role);
            context.Items["CorrelationId"] = "fixture-correlation";
            try
            {
                await next(context);
            }
            catch (Exception failure) when (!context.RequestAborted.IsCancellationRequested)
            {
                fixture.PropagatedFailureType = failure.GetType();
                await PlatformProblem.Create(context, 500, "internal_failure").ExecuteAsync(context);
            }
        });
        fixture.App.UseAuthorization();
        fixture.App.MapGet("/csrf", (HttpContext context, IAntiforgery antiforgery) => Results.Text(antiforgery.GetAndStoreTokens(context).RequestToken!));
        fixture.App.MapGet("/read", (Delegate)((HttpContext context) => G2EndpointGuard.ReadAsync(context, policy, (actor, _) => Task.FromResult(actor))));
        fixture.App.MapGet("/failure", (Delegate)((HttpContext context) => G2EndpointGuard.ReadAsync<string>(context, "semantic.read", (_, _) => throw new SemanticOperationException(409, "revision_conflict"))));
        fixture.App.MapPost("/write", (HttpContext context, CommandContext command) => G2EndpointGuard.WriteAsync(context, "ontology.edit", command, (_, _) =>
        {
            fixture.BusinessCalls++;
            return Task.FromResult(SyntheticDraft());
        }));
        fixture.App.MapPost("/revise", (HttpContext context, CommandContext command) => G2EndpointGuard.WriteAsync(context, "ontology.edit", command, (_, _) =>
        {
            fixture.BusinessCalls++;
            return Task.FromResult(SyntheticDraft());
        }, requiresRevision: true));
        fixture.App.MapPost("/protected-write", (HttpContext context, CommandContext command) => G2EndpointGuard.WriteAsync(context, "ontology.edit", command, (_, _) =>
        {
            fixture.BusinessCalls++;
            return Task.FromResult(SyntheticDraft());
        })).RequireAuthorization("ontology.edit");
        await fixture.App.StartAsync();
        fixture.Client = new HttpClient { BaseAddress = new Uri(fixture.App.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single()) };
        return fixture;
    }

    /// <summary>构造完整合成草稿供HTTP安全夹具输出，不能代表真实本体持久化或解析验收。</summary>
    /// <returns>源码、实际散列、修订及手工固定单三元组投影一致的测试草稿。</returns>
    private static OntologyDraft SyntheticDraft()
    {
        // 本体只声明一个合成类，使固定投影可与整份本体源码逐项对应。
        const string classIri = "urn:fixture:Thing";
        // 标准RDF类型谓词用于唯一的类声明三元组。
        const string typeIri = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";
        // 标准OWL类标识同时用于源三元组和节点类型。
        const string owlClassIri = "http://www.w3.org/2002/07/owl#Class";
        // 数据显式标记Synthetic；未实现的可选词汇保持null，不伪造资产。
        var sources = new SourceBundle
        {
            OntologyTurtle = $"<{classIri}> <{typeIri}> <{owlClassIri}> .\n",
            ShapesTurtle = "@prefix sh: <http://www.w3.org/ns/shacl#> .\n<urn:fixture:ThingShape> a sh:NodeShape; sh:targetClass <urn:fixture:Thing> .\n",
            VocabularyTurtle = null,
            DataTurtle = "<urn:fixture:org-demo:site-a:sample> a <urn:fixture:Thing>; <urn:fixture:synthetic> true .\n"
        };
        // 三个必需来源散列直接取对应UTF8字节，不使用占位常量。
        var ontologyHash = HashSyntheticSource(sources.OntologyTurtle);
        // Shape散列对应完整合成SHACL源码。
        var shapesHash = HashSyntheticSource(sources.ShapesTurtle);
        // 数据散列对应显式Synthetic事实源码。
        var dataHash = HashSyntheticSource(sources.DataTurtle);
        // 组合散列严格采用ontology、shapes、vocabulary/absent、data的LF顺序。
        var hashes = new SourceHashes
        {
            OntologyHash = ontologyHash,
            ShapesHash = shapesHash,
            VocabularyHash = null,
            DataHash = dataHash,
            BundleHash = HashSyntheticSource($"{ontologyHash}\n{shapesHash}\nabsent\n{dataHash}")
        };
        return new OntologyDraft
        {
            DraftId = "fixture-draft",
            AssetId = "fixture-asset",
            Scope = new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a", "site-b"] },
            BaseReleaseId = null,
            Revision = 3,
            Etag = "\"3\"",
            Name = "合成安全测试草稿",
            Sources = sources,
            Hashes = hashes,
            OwnerSubjectId = "fixture-subject",
            UpdatedAtUtc = new DateTimeOffset(2026, 10, 26, 0, 0, 0, TimeSpan.Zero),
            Projection = new SemanticProjection
            {
                Revision = 3,
                Hashes = hashes,
                Triples = [new RdfTriple
                {
                    Subject = new RdfTerm { Kind = RdfTermKind.Iri, Value = classIri },
                    Predicate = typeIri,
                    Object = new RdfTerm { Kind = RdfTermKind.Iri, Value = owlClassIri }
                }],
                Nodes = [new SemanticNode { Id = classIri, Kind = SemanticNodeKind.Class, Label = classIri, TypeIris = [owlClassIri] }],
                Edges = [],
                StructuralEditAllowed = true,
                Diagnostics = []
            }
        };
    }

    /// <summary>按冻结合同为合成源码的完整UTF8字节计算小写SHA256。</summary>
    /// <param name="value">仅由本测试生成的完整源码或规范组合散列文本。</param>
    /// <returns>64位小写十六进制散列。</returns>
    private static string HashSyntheticSource(string value) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));

    /// <summary>生成与G1验证后结构相同的服务器身份，不读取请求输入。</summary>
    /// <param name="role">服务器测试配置角色。</param>
    /// <returns>最小可信身份或匿名身份。</returns>
    public static ClaimsPrincipal Principal(string? role)
    {
        if (role is null)
        {
            return new ClaimsPrincipal(new ClaimsIdentity());
        }
        return new ClaimsPrincipal(new ClaimsIdentity([
            new Claim("sub", "fixture-subject"), new Claim("organization_id", "org-demo"),
            new Claim("site_ids", "site-a"), new Claim("site_ids", "site-b"), new Claim(ClaimTypes.Role, role)
        ], "fixture"));
    }

    /// <summary>提供合法且可重复的合成修订命令。</summary>
    /// <returns>不含秘密的测试命令。</returns>
    public static CommandContext Command() => new() { CommandId = "cmd-1", IdempotencyKey = "idem-1", ExpectedRevision = 2, Reason = "合成测试修改" };

    /// <summary>由原生服务签发令牌并保持对应Cookie。</summary>
    /// <returns>令牌设置完成任务。</returns>
    public async Task SetCsrfAsync()
    {
        // 只在内存往返令牌，不输出或持久化其值。
        var token = await Client.GetStringAsync("/csrf");
        Client.DefaultRequestHeaders.Add("X-CSRF-TOKEN", token);
    }

    /// <summary>停止本测试Kestrel并释放回环客户端。</summary>
    /// <returns>生命周期清理任务。</returns>
    public async ValueTask DisposeAsync()
    {
        Client.Dispose();
        await App.DisposeAsync();
    }
}

/// <summary>仅检查调用顺序的内存接收器，持久原子性由独立真实PG测试覆盖。</summary>
internal sealed class G2AuditCapture : IAuditTrail
{
    /// <summary>本次测试观察到的审计命令。</summary>
    public List<AuditCommand> Commands { get; } = [];

    /// <summary>可选合成依赖故障，只用于验证异常原样传播。</summary>
    public Exception? Failure { get; set; }

    /// <summary>保存固定审计命令用于边界断言。</summary>
    /// <param name="actor">可信身份。</param>
    /// <param name="command">受控拒绝命令。</param>
    /// <param name="cancellationToken">请求取消信号。</param>
    /// <returns>合成审计标识，不能代表真实持久事实。</returns>
    public Task<string> WriteAsync(ActorContext actor, AuditCommand command, CancellationToken cancellationToken)
    {
        if (Failure is not null)
        {
            return Task.FromException<string>(Failure);
        }
        Commands.Add(command);
        return Task.FromResult("fixture-audit");
    }
}
