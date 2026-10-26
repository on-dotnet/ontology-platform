using System.Net;
using System.Net.Http.Json;
using System.Security.Claims;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.VisualStudio.TestTools.UnitTesting;
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
        Assert.AreEqual(status, (int)response.StatusCode);
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
        builder.Services.AddG2Authorization();
        builder.Services.AddAntiforgery(options => options.HeaderName = "X-CSRF-TOKEN");
        builder.Services.Configure<PlatformSecurityOptions>(options => options.PublicOrigin = "http://platform.test");
        builder.Services.AddSingleton<IAuditTrail>(audit ?? fixture.Audit);
        fixture.App = builder.Build();
        fixture.App.Use(async (context, next) =>
        {
            context.User = Principal(role);
            context.Items["CorrelationId"] = "fixture-correlation";
            await next(context);
        });
        fixture.App.MapGet("/csrf", (HttpContext context, IAntiforgery antiforgery) => Results.Text(antiforgery.GetAndStoreTokens(context).RequestToken!));
        fixture.App.MapGet("/read", (Delegate)((HttpContext context) => G2EndpointGuard.ReadAsync(context, policy, (actor, _) => Task.FromResult(actor))));
        fixture.App.MapGet("/failure", (Delegate)((HttpContext context) => G2EndpointGuard.ReadAsync<string>(context, "semantic.read", (_, _) => throw new SemanticOperationException(409, "revision_conflict"))));
        fixture.App.MapPost("/write", (HttpContext context, CommandContext command) => G2EndpointGuard.WriteAsync(context, "ontology.edit", command, (_, _) =>
        {
            fixture.BusinessCalls++;
            return Task.FromResult(new OntologyDraft { Revision = 3, Etag = "\"3\"" });
        }));
        fixture.App.MapPost("/revise", (HttpContext context, CommandContext command) => G2EndpointGuard.WriteAsync(context, "ontology.edit", command, (_, _) =>
        {
            fixture.BusinessCalls++;
            return Task.FromResult(new OntologyDraft { Revision = 3, Etag = "\"3\"" });
        }, requiresRevision: true));
        await fixture.App.StartAsync();
        fixture.Client = new HttpClient { BaseAddress = new Uri(fixture.App.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single()) };
        return fixture;
    }

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

    /// <summary>保存固定审计命令用于边界断言。</summary>
    /// <param name="actor">可信身份。</param>
    /// <param name="command">受控拒绝命令。</param>
    /// <param name="cancellationToken">请求取消信号。</param>
    /// <returns>合成审计标识，不能代表真实持久事实。</returns>
    public Task<string> WriteAsync(ActorContext actor, AuditCommand command, CancellationToken cancellationToken)
    {
        Commands.Add(command);
        return Task.FromResult("fixture-audit");
    }
}
