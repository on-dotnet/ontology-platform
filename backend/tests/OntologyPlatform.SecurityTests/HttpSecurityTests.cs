using System.Collections.Concurrent;
using System.Net;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;
using System.Xml.Linq;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.OpenIdConnect;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Microsoft.IdentityModel.Protocols.OpenIdConnect;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Api;

namespace OntologyPlatform.SecurityTests;

/// <summary>以真实Kestrel请求验证安全入口，不用模拟HTTP处理器替代管道。</summary>
[TestClass]
public sealed class HttpSecurityTests
{
    /// <summary>匿名及坏Cookie只得到401，伪造身份头不能建立权限。</summary>
    /// <returns>真实请求和宿主释放任务。</returns>
    [TestMethod]
    public async Task AnonymousAndCorruptedCookieRemainUnauthenticated()
    {
        // 为测试生成独立证书与密钥目录，绝不读取用户已有密钥。
        using var fixture = new SecurityHostFixture();
        // 启动正式API代码，使用未连接数据库的匿名路径。
        await using var app = fixture.Create();
        await app.StartAsync();
        // 真实请求禁止自动跳转，401不得被OIDC302掩盖。
        using var client = fixture.CreateClient(app);
        // 伪造角色及厂区头不得影响服务器身份。
        using var request = new HttpRequestMessage(HttpMethod.Get, "/api/v1/platform/me");
        request.Headers.Add("Cookie", ".OntologyPlatform.Session=corrupted-development-test");
        request.Headers.Add("X-Roles", "platform.viewer");
        request.Headers.Add("X-Site-Id", "site-a");
        // 检查完整错误合同并确认没有登录302。
        using var response = await client.SendAsync(request);
        Assert.AreEqual(HttpStatusCode.Unauthorized, response.StatusCode);
        Assert.AreEqual("application/problem+json", response.Content.Headers.ContentType?.MediaType);
        // 只解析通用错误，不把任何认证材料写进断言输出。
        using var body = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        Assert.AreEqual("unauthenticated", body.RootElement.GetProperty("code").GetString());
        Assert.IsTrue(response.Headers.Contains("X-Trace-Id"));
        Assert.IsTrue(response.Headers.Contains("X-Correlation-Id"));
        Assert.AreEqual(HttpStatusCode.Unauthorized, (await client.GetAsync("/api/v1/platform/resources")).StatusCode);
    }

    /// <summary>默认拒绝伪造转发头，回调错误输出通用400。</summary>
    /// <returns>真实安全负例请求任务。</returns>
    [TestMethod]
    public async Task ForwardedHeadersAndInvalidCallbackFailClosed()
    {
        // 测试不依赖真实OIDC发现，错误回调应在协议验证阶段失败。
        using var fixture = new SecurityHostFixture();
        // 正式宿主沿用默认无可信代理策略。
        await using var app = fixture.Create();
        await app.StartAsync();
        // 只连接动态回环端口，不访问外部服务。
        using var client = fixture.CreateClient(app);
        // 不可信转发Host必须拒绝而非影响生成回调。
        using var request = new HttpRequestMessage(HttpMethod.Get, "/auth/login");
        request.Headers.Add("X-Forwarded-Host", "evil.invalid");
        Assert.AreEqual(HttpStatusCode.BadRequest, (await client.SendAsync(request)).StatusCode);
        Assert.AreEqual(HttpStatusCode.BadRequest, (await client.GetAsync("/auth/login?returnUrl=%2F%2Fevil.invalid")).StatusCode);
        Assert.AreEqual(HttpStatusCode.BadRequest, (await client.GetAsync("/signin-oidc?error=invalid_request")).StatusCode);
    }

    /// <summary>正式生产探针始终存在且有密钥保护，PG故障只影响就绪。</summary>
    /// <returns>探针检查及释放任务。</returns>
    [TestMethod]
    public async Task ProductionHealthRemainsProtectedAndDependencyAware()
    {
        // 生产配置使用HTTPS可信地址，但内部Kestrel仍用动态回环端口测试。
        using var fixture = new SecurityHostFixture();
        // 正式API不受InfraAPI生产404历史规则影响。
        await using var app = fixture.Create("Production");
        await app.StartAsync();
        // 错误凭据必须401，不能泄露依赖状态。
        using var client = fixture.CreateClient(app);
        Assert.AreEqual(HttpStatusCode.Unauthorized, (await client.GetAsync("/health/live")).StatusCode);
        client.DefaultRequestHeaders.Add("X-Health-Key", fixture.HealthKey);
        Assert.AreEqual(HttpStatusCode.OK, (await client.GetAsync("/health/live")).StatusCode);
        Assert.AreEqual(HttpStatusCode.ServiceUnavailable, (await client.GetAsync("/health/ready")).StatusCode);
        Assert.AreEqual(HttpStatusCode.Unauthorized, (await client.GetAsync("/openapi/v1.json")).StatusCode);
    }

    /// <summary>请求Host不能超出显式入口白名单，避免恶意Host参与平台流转。</summary>
    /// <returns>真实恶意Host请求验证任务。</returns>
    [TestMethod]
    public async Task UntrustedHostNeverEntersPlatformRoutes()
    {
        // 正式宿主使用仅回环的显式允许主机。
        using var fixture = new SecurityHostFixture();
        // 保持实际Kestrel监听，不模拟Host校验中间件。
        await using var app = fixture.Create();
        await app.StartAsync();
        // 连接仍在回环，只有不可信Host由测试注入。
        using var client = fixture.CreateClient(app);
        client.DefaultRequestHeaders.Host = "evil.invalid";
        Assert.AreEqual(HttpStatusCode.BadRequest, (await client.GetAsync("/health/live")).StatusCode);
    }

    /// <summary>向本轮真实Keycloak推送授权，记录五个安全布尔并观察前端仅含PAR引用。</summary>
    /// <returns>正式宿主与真实签发者的推送验证任务。</returns>
    [TestMethod]
    public async Task RealIssuerPushRetainsCodePkceStateAndNonce()
    {
        // 只由显式环境变量消费本轮私有runtime，不打印配置或协议值。
        var runtimePath = Environment.GetEnvironmentVariable("G1_SEC_OIDC_RUNTIME");
        if (string.IsNullOrWhiteSpace(runtimePath))
        {
            Assert.Inconclusive("NOT_RUN: 未注入本轮专用Keycloak运行时配置。");
        }
        // runtime文件只在进程内解析，不能作为断言输出。
        using var runtime = JsonDocument.Parse(await File.ReadAllTextAsync(runtimePath));
        // 专用realm文件保存本轮随机客户端秘密，本测试只发PAR不读取用户密码。
        using var realm = JsonDocument.Parse(await File.ReadAllTextAsync(runtime.RootElement.GetProperty("realmFile").GetString()!));
        // 捕获所有本测试日志用于确保只存在安全布尔证据。
        using var logs = new CapturedLogs();
        // 证书和keyring仍使用测试隔离资产，不接触统一栈私钥。
        using var fixture = new SecurityHostFixture();
        // 仅覆盖正式OIDC所需配置，回调保持统一栈批准入口。
        var issuer = new Dictionary<string, string?>
        {
            ["Security:Authority"] = realm.RootElement.GetProperty("authority").GetString(),
            ["Security:ClientId"] = realm.RootElement.GetProperty("clientId").GetString(),
            ["Security:ClientSecret"] = realm.RootElement.GetProperty("clientSecret").GetString()
        };
        // 实际Kestrel挑战将通过正式中间件向真实Keycloak发出PAR。
        await using var app = fixture.Create(logs: logs, overrides: issuer);
        await app.StartAsync();
        // 不跟随登录页，本项只验证推送参数及实际request_uri响应。
        using var client = fixture.CreateClient(app);
        // 发起正式认证挑战，不使用测试协议处理替身。
        using var response = await client.GetAsync("/auth/login?returnUrl=%2F");
        Assert.AreEqual(HttpStatusCode.Redirect, response.StatusCode);
        // 只检查字段存在，不把任何URL值传递给断言或日志。
        var query = Microsoft.AspNetCore.WebUtilities.QueryHelpers.ParseQuery(response.Headers.Location!.Query);
        Assert.IsTrue(query.ContainsKey("request_uri"));
        Assert.IsFalse(query.ContainsKey("state"));
        Assert.IsFalse(query.ContainsKey("nonce"));
        Assert.IsTrue(logs.Messages.Any(value => value.Contains("PAR协议 code=True pkceS256=True hasChallenge=True hasState=True hasNonce=True", StringComparison.Ordinal)), "真实推送必须观察到五个安全布尔为真。");
        Assert.IsFalse(logs.Messages.Any(value => value.Contains(issuer["Security:ClientSecret"]!, StringComparison.Ordinal)), "客户端秘密不得进入日志。");
    }

    /// <summary>推送授权事件仅记录五个布尔结果，不改变框架PAR行为或输出协议值。</summary>
    /// <returns>内置事件执行与安全日志检查任务。</returns>
    [TestMethod]
    public async Task PushedAuthorizationObservationContainsBooleansOnly()
    {
        // 捕获本宿主安全事件，合成协议值不应进入日志正文。
        using var logs = new CapturedLogs();
        // 证书及keyring仍为本测试临时资产。
        using var fixture = new SecurityHostFixture();
        // 读取正式配置而不模拟OnPushAuthorization委托。
        await using var app = fixture.Create(logs: logs);
        // 正式OIDC选项携带实际事件注册。
        var options = app.Services.GetRequiredService<IOptionsMonitor<OpenIdConnectOptions>>().Get(OpenIdConnectDefaults.AuthenticationScheme);
        // 仅无效合成值用于保证日志不回显nonce/state/PKCE。
        const string marker = "synthetic-par-sensitive-marker";
        // 事件在框架生成state/nonce/PKCE之后运行。
        var message = new OpenIdConnectMessage { ResponseType = "code", State = marker, Nonce = marker };
        message.SetParameter("code_challenge", marker);
        message.SetParameter("code_challenge_method", "S256");
        // 请求服务提供日志器；事件不会自行发网络或读取用户凭证。
        var context = new PushedAuthorizationContext(new DefaultHttpContext { RequestServices = app.Services },
            new AuthenticationScheme(OpenIdConnectDefaults.AuthenticationScheme, null, typeof(OpenIdConnectHandler)), options, message, new AuthenticationProperties());
        await options.Events.PushAuthorization(context);
        Assert.IsTrue(logs.Messages.Any(value => value.Contains("PAR协议", StringComparison.Ordinal)), "正式事件必须保留安全布尔观察。");
        Assert.IsFalse(logs.Messages.Any(value => value.Contains(marker, StringComparison.Ordinal)), "协议秘密不得记录。");
        Assert.IsFalse(context.HandledPush);
        Assert.IsFalse(context.SkippedPush);
        Assert.AreEqual(marker, message.State);
    }

    /// <summary>代理URL中的敏感查询标记不能进入任何框架或自定义日志正文。</summary>
    /// <returns>真实代理请求和捕获日志检查任务。</returns>
    [TestMethod]
    public async Task ProxyQueryNeverEntersLogBody()
    {
        // 捕获宿主所有日志正文而不写Console或证据，使用固定无效合成标记。
        using var logs = new CapturedLogs();
        // 正式宿主保留真实YARP管道，目标Next未运行不影响日志边界检查。
        using var fixture = new SecurityHostFixture();
        // 将只读捕获器接入测试宿主，不改变生产日志配置。
        await using var app = fixture.Create(logs: logs);
        await app.StartAsync();
        // 真实HTTP URL含合成敏感参数，错误正文也不应回显该值。
        using var client = fixture.CreateClient(app);
        // 合成标记仅用于验证日志泄露负例，不包含真实认证材料。
        const string marker = "synthetic-query-confidential-marker";
        await client.GetAsync("/?access_token=" + marker);
        Assert.IsFalse(logs.Messages.Any(message => message.Contains(marker, StringComparison.Ordinal)), "代理请求的查询内容不得进入日志正文。");
    }

    /// <summary>保留API/auth/health/openapi前缀的未知路径不可转发到Next。</summary>
    /// <returns>保留前缀负例验证任务。</returns>
    [TestMethod]
    public async Task ReservedPrefixesNeverReachWebProxy()
    {
        // Next故意未运行；若保留路由被错误代理会返回502而非404。
        using var fixture = new SecurityHostFixture();
        // 使用正式路由表验证边界，不检查源代码文本。
        await using var app = fixture.Create();
        await app.StartAsync();
        // 未知保留路径必须留在.NET管道。
        using var client = fixture.CreateClient(app);
        foreach (var path in new[] { "/api/not-registered", "/auth/not-registered", "/health/not-registered", "/openapi/not-registered" })
        {
            Assert.AreEqual(HttpStatusCode.NotFound, (await client.GetAsync(path)).StatusCode, "保留前缀不得代理至Web");
        }
    }
}

/// <summary>仅测试使用的临时证书及真实API宿主生命周期管理器。</summary>
internal sealed class SecurityHostFixture : IDisposable
{
    /// <summary>本测试拥有的临时根目录。</summary>
    private readonly string root = Path.Combine(Path.GetTempPath(), "ontology-sec-test-" + Guid.NewGuid().ToString("N"));

    /// <summary>测试生成的PFX密码，不向日志或断言传递。</summary>
    private readonly string password = Convert.ToHexString(RandomNumberGenerator.GetBytes(24));

    /// <summary>仅本测试使用的探针凭据。</summary>
    public string HealthKey { get; } = Convert.ToHexString(RandomNumberGenerator.GetBytes(24));

    /// <summary>创建临时证书及目录，不修改机器信任存储。</summary>
    public SecurityHostFixture()
    {
        Directory.CreateDirectory(Path.Combine(root, "keys"));
        // 仅临时RSA用于本次测试证书，调用方退出时释放。
        using var rsa = RSA.Create(2048);
        // 证书用途仅保护keyring，不用于公网TLS。
        var request = new CertificateRequest("CN=OntologyPlatform-Synthetic-Security-Test", rsa, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        // 短期自签名证书避免安装任何系统信任。
        using var certificate = request.CreateSelfSigned(DateTimeOffset.UtcNow.AddMinutes(-1), DateTimeOffset.UtcNow.AddDays(1));
        File.WriteAllBytes(Path.Combine(root, "protection.pfx"), certificate.Export(X509ContentType.Pfx, password));
        if (!OperatingSystem.IsWindows())
        {
            File.SetUnixFileMode(root, UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
            File.SetUnixFileMode(Path.Combine(root, "keys"), UnixFileMode.UserRead | UnixFileMode.UserWrite | UnixFileMode.UserExecute);
            File.SetUnixFileMode(Path.Combine(root, "protection.pfx"), UnixFileMode.UserRead | UnixFileMode.UserWrite);
        }
    }

    /// <summary>创建真实平台API，PG连接指向确定未运行端口以验证失败关闭。</summary>
    /// <param name="environment">需要验证的正式环境名。</param>
    /// <param name="connection">可选本轮隔离PG连接；未指定时使用故障端口。</param>
    /// <param name="logs">可选的测试日志捕获器。</param>
    /// <param name="overrides">可选的本轮真实签发者配置，仅用于显式集成测试。</param>
    /// <returns>未启动的正式API。</returns>
    public WebApplication Create(string environment = "Development", string? connection = null, ILoggerProvider? logs = null, IReadOnlyDictionary<string, string?>? overrides = null)
    {
        return PlatformApiHost.CreateApplication(["--environment", environment, "--urls", "http://127.0.0.1:0"], builder =>
        {
            builder.Logging.ClearProviders();
            if (logs is not null)
            {
                builder.Logging.AddProvider(logs);
            }
            builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
            {
                ["Security:Authority"] = environment == "Development" ? "http://localhost:18999/realms/test" : "https://issuer.invalid/realms/test",
                ["Security:ClientId"] = "synthetic-client",
                ["Security:ClientSecret"] = password,
                ["Security:PublicOrigin"] = environment == "Development" ? "http://localhost:15100" : "https://platform.invalid",
                ["Security:KeyRingPath"] = Path.Combine(root, "keys"),
                ["Security:CertificatePath"] = Path.Combine(root, "protection.pfx"),
                ["Security:CertificatePassword"] = password,
                ["Security:HealthKey"] = HealthKey,
                ["ConnectionStrings:governance"] = connection ?? "Host=127.0.0.1;Port=18998;Database=synthetic_test;Username=test;Password=synthetic-unused;Timeout=1;Command Timeout=1",
                ["Web:Origin"] = "http://127.0.0.1:18997",
                ["AllowedHosts"] = environment == "Development" ? "localhost;127.0.0.1" : "platform.invalid"
            });
            if (overrides is not null)
            {
                builder.Configuration.AddInMemoryCollection(overrides);
            }
        });
    }

    /// <summary>创建不自动跳转的真实回环HTTP客户端。</summary>
    /// <param name="app">已启动的Kestrel宿主。</param>
    /// <returns>调用方负责释放的客户端。</returns>
    public HttpClient CreateClient(WebApplication app)
    {
        // HTTP连接地址与可信Host分开，支持生产内部反代探针的真实Host。
        var client = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false })
        {
            BaseAddress = new Uri(app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single()),
            Timeout = TimeSpan.FromSeconds(10)
        };
        client.DefaultRequestHeaders.Host = app.Environment.IsDevelopment() ? "localhost" : "platform.invalid";
        return client;
    }

    /// <summary>读取本测试生成的密钥环XML，只向断言返回结构不输出密钥。</summary>
    /// <returns>本轮实际生成的加密keyring文档。</returns>
    public XDocument[] KeyRingFiles()
    {
        return Directory.GetFiles(Path.Combine(root, "keys"), "key-*.xml").Select(XDocument.Load).ToArray();
    }

    /// <summary>删除本测试创建的临时证书及keyring，避免残留秘密。</summary>
    public void Dispose()
    {
        Directory.Delete(root, true);
    }
}

/// <summary>只在测试内存中捕获格式化日志，避免测试输出携带敏感请求。</summary>
internal sealed class CapturedLogs : ILoggerProvider, ILogger
{
    /// <summary>当前测试捕获的日志正文，仅用于检查不进行输出。</summary>
    public ConcurrentBag<string> Messages { get; } = [];

    /// <summary>所有类别使用同一内存捕获器。</summary>
    /// <param name="categoryName">框架日志类别。</param>
    /// <returns>当前测试的捕获器。</returns>
    public ILogger CreateLogger(string categoryName) => this;

    /// <summary>测试日志不持久化作用域。</summary>
    /// <typeparam name="TState">日志作用域状态类型。</typeparam>
    /// <param name="state">未输出的作用域数据。</param>
    /// <returns>无需释放的空作用域。</returns>
    public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

    /// <summary>捕获所有未被正式宿主过滤的日志。</summary>
    /// <param name="logLevel">框架请求的日志级别。</param>
    /// <returns>始终启用测试捕获。</returns>
    public bool IsEnabled(LogLevel logLevel) => true;

    /// <summary>仅将格式化正文放入测试内存，不输出异常或认证材料。</summary>
    /// <typeparam name="TState">结构化状态类型。</typeparam>
    /// <param name="logLevel">日志级别。</param>
    /// <param name="eventId">事件编号。</param>
    /// <param name="state">待格式化状态。</param>
    /// <param name="exception">当前框架异常。</param>
    /// <param name="formatter">框架格式化委托。</param>
    public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
    {
        Messages.Add(formatter(state, exception));
    }

    /// <summary>测试结束不创建文件或额外资源。</summary>
    public void Dispose()
    {
    }
}
