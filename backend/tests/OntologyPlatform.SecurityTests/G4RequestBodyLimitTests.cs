using System.Collections.Concurrent;
using System.Net;
using System.Net.Http.Json;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Server.Kestrel.Core;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using OntologyPlatform.Api.G4;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.SecurityTests;

/// <summary>使用真实回环Kestrel、Cookie与防伪验证正文硬限；业务哨兵不代表PG/OIDC产品验收。</summary>
[TestClass]
public sealed class G4RequestBodyLimitTests
{
    /// <summary>三种实际传输均在65536字节边界接受有效输入，并在超界时阻止密钥及业务处理器执行。</summary>
    /// <param name="transport">固定长度HTTP1、分块HTTP1或无长度HTTP2。</param>
    /// <param name="secret">是否测试专用密钥入口；否则测试连接创建入口。</param>
    /// <param name="size">包括合法尾部空白在内的实际UTF8字节数。</param>
    /// <returns>真实请求和服务清理任务。</returns>
    [TestMethod]
    [DataRow("length", true, 65536)]
    [DataRow("length", true, 65537)]
    [DataRow("length", true, 131072)]
    [DataRow("chunked", true, 65536)]
    [DataRow("chunked", true, 65537)]
    [DataRow("chunked", true, 131072)]
    [DataRow("http2", true, 65536)]
    [DataRow("http2", true, 65537)]
    [DataRow("http2", true, 131072)]
    [DataRow("length", false, 65536)]
    [DataRow("length", false, 65537)]
    [DataRow("length", false, 131072)]
    [DataRow("chunked", false, 65536)]
    [DataRow("chunked", false, 65537)]
    [DataRow("chunked", false, 131072)]
    [DataRow("http2", false, 65536)]
    [DataRow("http2", false, 65537)]
    [DataRow("http2", false, 131072)]
    public async Task EnforcesActualBytesBeforeApplication(string transport, bool secret, int size)
    {
        // 每项创建独立随机回环端口及内存认证，避免依赖其他任务环境。
        await using var fixture = await HttpFixture.StartAsync(transport == "http2");
        await fixture.LoginAsync();
        // 请求仅含固定合成值，不落磁盘或普通日志。
        var json = secret
            ? """{"secretValue":"synthetic-only","scopeSelection":{"organizationId":"fixture-org","siteIds":["fixture-site"]},"purpose":"POSTGRESQL_READONLY","command":{"commandId":"fixture-command","idempotencyKey":"fixture-key","reason":"synthetic boundary","expectedRevision":0}}"""
            : """{"displayName":"synthetic","scopeSelection":{"organizationId":"fixture-org","siteIds":["fixture-site"]},"config":{"type":"POSTGRESQL","profile":{"host":"pg-source","port":5432,"database":"fixture","username":"fixture_reader","sslMode":"VerifyFull","allowedSchemas":["production"]}},"secretRef":"synthetic-ref","command":{"commandId":"fixture-command","idempotencyKey":"fixture-key","reason":"synthetic boundary","expectedRevision":0}}""";
        // 尾部JSON空白合法，保证失败原因是字节预算而非字段长度或反序列化。
        var payload = Encoding.UTF8.GetBytes(json.PadRight(size));
        // 无长度内容使用真实分块写入；HTTP2由DATA帧承载且禁止回退HTTP1。
        using var content = transport == "length" ? (HttpContent)new ByteArrayContent(payload) : new FragmentedContent(payload);
        content.Headers.ContentType = new("application/json");
        // 两个入口覆盖凭据签发与普通业务命令前的共同边界。
        using var request = new HttpRequestMessage(HttpMethod.Post, secret ? "/api/v1/connection-secrets" : "/api/v1/connections")
        {
            Content = content,
            Version = transport == "http2" ? HttpVersion.Version20 : HttpVersion.Version11,
            VersionPolicy = HttpVersionPolicy.RequestVersionExact
        };
        // 固定版本防止HTTP2测试被透明降级为HTTP1。
        using var response = await fixture.Client.SendAsync(request);
        Assert.AreEqual(request.Version, response.Version);
        Assert.AreEqual(size > 65536 ? HttpStatusCode.RequestEntityTooLarge : HttpStatusCode.OK, response.StatusCode);
        Assert.AreEqual(size > 65536 ? 0 : 1, fixture.Handler.Calls, "拒绝正文不得进入密钥签发、命令或持久化边界。");
        // 服务端观察真实协议和长度，而不只相信客户端设置。
        var observed = fixture.Observations.Single();
        Assert.AreEqual(transport == "http2" ? "HTTP/2" : "HTTP/1.1", observed.Protocol);
        Assert.AreEqual(transport == "length" ? (long?)size : null, observed.Length);
        Assert.AreEqual(transport == "chunked", observed.Chunked);
        if (size > 65536)
        {
            // 错误只能返回平台安全码，不能包含合成秘密或签发结果。
            var text = await response.Content.ReadAsStringAsync();
            using var problem = JsonDocument.Parse(text);
            Assert.AreEqual("connection_profile_invalid", problem.RootElement.GetProperty("code").GetString());
            Assert.IsFalse(text.Contains("synthetic-only", StringComparison.Ordinal));
            Assert.IsFalse(text.Contains("secretRef", StringComparison.Ordinal));
        }
    }

    /// <summary>分批刷新真实网络流并禁止计算Content-Length，避免客户端自动补齐长度。</summary>
    private sealed class FragmentedContent : HttpContent
    {
        /// <summary>仅本测试内存存在的合成正文。</summary>
        private readonly byte[] payload;

        /// <summary>保存一次请求的固定字节，后续不修改。</summary>
        /// <param name="payload">待发送的合成正文。</param>
        internal FragmentedContent(byte[] payload) => this.payload = payload;

        /// <summary>明确不公布长度，HTTP1必须chunked，HTTP2必须无Content-Length。</summary>
        /// <param name="length">无可信预先长度。</param>
        /// <returns>始终为假。</returns>
        protected override bool TryComputeLength(out long length)
        {
            length = 0;
            return false;
        }

        /// <summary>逐片实际写入并刷新，形成多次异步读入而非一次内存流。</summary>
        /// <param name="stream">真实HTTP输出流。</param>
        /// <param name="context">框架传输上下文。</param>
        /// <returns>写入完成任务。</returns>
        protected override async Task SerializeToStreamAsync(Stream stream, TransportContext? context)
        {
            // 257不是协议缓冲区的整倍数，覆盖不对齐和末尾一字节边界。
            for (var offset = 0; offset < payload.Length; offset += 257)
            {
                await stream.WriteAsync(payload.AsMemory(offset, Math.Min(257, payload.Length - offset)));
                await stream.FlushAsync();
            }
        }
    }

    /// <summary>只计数真实端点到应用的调用；不注册秘密、数据库或业务服务。</summary>
    private sealed class ApplicationSentinel : IConnectionRequestHandler
    {
        /// <summary>进入实际业务边界的次数，超界必须为零。</summary>
        private int calls;

        /// <summary>原子读取已观察的调用次数。</summary>
        internal int Calls => Volatile.Read(ref calls);

        /// <summary>用无秘密固定回执确认合规正文确实进入应用边界。</summary>
        /// <param name="invocation">生产端点完成校验后的请求。</param>
        /// <param name="token">当前请求取消信号。</param>
        /// <returns>无外部副作用的测试回执。</returns>
        public Task<ConnectionReply> HandleAsync(ConnectionInvocation invocation, CancellationToken token)
        {
            Interlocked.Increment(ref calls);
            return Task.FromResult(new ConnectionReply { Value = new { accepted = true } });
        }
    }

    /// <summary>真实HTTP边界夹具；固定合成登录替代外部OIDC，只用于请求大小安全回归。</summary>
    private sealed class HttpFixture : IAsyncDisposable
    {
        /// <summary>独占的真实Kestrel服务。</summary>
        private readonly WebApplication app;

        /// <summary>同一次测试实际协议版本。</summary>
        private readonly Version version;

        /// <summary>只存在内存的Cookie客户端。</summary>
        internal HttpClient Client { get; }

        /// <summary>应用调用哨兵，不连接数据库。</summary>
        internal ApplicationSentinel Handler { get; }

        /// <summary>仅记录传输元数据，不保存正文、Cookie或防伪值。</summary>
        internal ConcurrentQueue<(string Protocol, long? Length, bool Chunked)> Observations { get; }

        /// <summary>绑定当前服务及仅回环客户端。</summary>
        /// <param name="app">已启动的独占服务。</param>
        /// <param name="handler">当前测试哨兵。</param>
        /// <param name="observations">传输元数据队列。</param>
        /// <param name="http2">是否强制HTTP2。</param>
        private HttpFixture(WebApplication app, ApplicationSentinel handler, ConcurrentQueue<(string Protocol, long? Length, bool Chunked)> observations, bool http2)
        {
            this.app = app;
            Handler = handler;
            Observations = observations;
            version = http2 ? HttpVersion.Version20 : HttpVersion.Version11;
            Client = new HttpClient(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false, CookieContainer = new CookieContainer() })
            {
                BaseAddress = new Uri(app.Urls.Single()),
                DefaultRequestVersion = version,
                DefaultVersionPolicy = HttpVersionPolicy.RequestVersionExact,
                Timeout = TimeSpan.FromSeconds(10)
            };
        }

        /// <summary>在独立回环监听器注册生产G4路由、真实Cookie及防伪服务。</summary>
        /// <param name="http2">为真时使用仅HTTP2的h2c监听器。</param>
        /// <returns>可准确释放的当前测试夹具。</returns>
        internal static async Task<HttpFixture> StartAsync(bool http2)
        {
            // 清空日志提供程序，合成凭据也不进入普通运行日志。
            var builder = WebApplication.CreateBuilder();
            builder.Logging.ClearProviders();
            builder.WebHost.ConfigureKestrel(options => options.Listen(IPAddress.Loopback, 0, listener => listener.Protocols = http2 ? HttpProtocols.Http2 : HttpProtocols.Http1));
            builder.Services.AddSingleton<IDataProtectionProvider>(new EphemeralDataProtectionProvider());
            builder.Services.AddAuthentication(CookieAuthenticationDefaults.AuthenticationScheme).AddCookie();
            builder.Services.AddAuthorization(options =>
            {
                options.AddPolicy("connection.manage", policy => policy.RequireAuthenticatedUser().RequireRole("platform.operator"));
                options.AddPolicy("connection.secret.manage", policy => policy.RequireAuthenticatedUser().RequireRole("platform.operator"));
            });
            builder.Services.AddAntiforgery(options => options.HeaderName = "X-CSRF-TOKEN");
            // 端点只会解析已登记的哨兵，任何超界调用均可直接观察。
            var handler = new ApplicationSentinel();
            builder.Services.AddSingleton<IConnectionRequestHandler>(handler);
            // 随机监听端口启动后填入同一个可信Origin选项对象。
            var security = new PlatformSecurityOptions();
            builder.Services.AddSingleton<IOptions<PlatformSecurityOptions>>(Options.Create(security));
            // 队列只记录当前G4请求的传输，不记录认证端点。
            var observations = new ConcurrentQueue<(string Protocol, long? Length, bool Chunked)>();
            // 构建独立服务不注册数据库或任何业务持久化能力。
            var app = builder.Build();
            app.UseAuthentication();
            app.UseAuthorization();
            app.Use(async (context, next) =>
            {
                if (context.Request.Path.StartsWithSegments("/api/v1"))
                    observations.Enqueue((context.Request.Protocol, context.Request.ContentLength, context.Request.Headers.TransferEncoding.Contains("chunked")));
                await next(context);
            });
            app.MapG4Endpoints();
            app.MapPost("/fixture/login", async (HttpContext context) =>
            {
                // 身份仅由测试服务器生成，不接受HTTP伪造用户、组织或角色。
                var identity = new ClaimsIdentity(new[] { new Claim("sub", "fixture-user"), new Claim("organization_id", "fixture-org"), new Claim("site_ids", "fixture-site"), new Claim(ClaimTypes.Role, "platform.operator") }, CookieAuthenticationDefaults.AuthenticationScheme);
                await context.SignInAsync(CookieAuthenticationDefaults.AuthenticationScheme, new ClaimsPrincipal(identity));
                return Results.NoContent();
            });
            app.MapGet("/fixture/csrf", (HttpContext context, IAntiforgery antiforgery) => Results.Json(antiforgery.GetAndStoreTokens(context).RequestToken)).RequireAuthorization();
            await app.StartAsync();
            security.PublicOrigin = app.Urls.Single();
            return new HttpFixture(app, handler, observations, http2);
        }

        /// <summary>经真实Cookie登录与防伪令牌生成，随后发送同源业务请求。</summary>
        /// <returns>登录完成任务。</returns>
        internal async Task LoginAsync()
        {
            // 明确使用当前协议，h2c测试不得通过HTTP1取得身份。
            using var request = new HttpRequestMessage(HttpMethod.Post, "/fixture/login") { Version = version, VersionPolicy = HttpVersionPolicy.RequestVersionExact };
            // 测试Cookie只保存于当前HttpClientHandler内存。
            using var response = await Client.SendAsync(request);
            Assert.AreEqual(HttpStatusCode.NoContent, response.StatusCode);
            // 令牌不写日志，业务HTTP仍通过原生ValidateRequestAsync。
            var csrf = await Client.GetFromJsonAsync<string>("/fixture/csrf");
            Client.DefaultRequestHeaders.Add("X-CSRF-TOKEN", csrf);
            Client.DefaultRequestHeaders.Add("Origin", Client.BaseAddress!.GetLeftPart(UriPartial.Authority));
        }

        /// <summary>只关闭本测试客户端与监听服务，无持久资源可删除。</summary>
        /// <returns>真实服务退出任务。</returns>
        public async ValueTask DisposeAsync()
        {
            Client.Dispose();
            await app.StopAsync();
            await app.DisposeAsync();
        }
    }
}
