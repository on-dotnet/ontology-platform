using System.Diagnostics;
using System.Net;
using System.Security.Claims;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authentication.OpenIdConnect;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.AspNetCore.Routing;
using Microsoft.EntityFrameworkCore;
using Microsoft.IdentityModel.Protocols.OpenIdConnect;
using OntologyPlatform.Api.Contracts;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.ServiceDefaults;
using OpenTelemetry.Metrics;
using OpenTelemetry.Trace;
using Yarp.ReverseProxy.Configuration;
using Yarp.ReverseProxy.Transforms;

namespace OntologyPlatform.Api;

/// <summary>组合正式BFF安全宿主，缺少持久化或可信配置时拒绝启动。</summary>
public static class PlatformApiHost
{
    /// <summary>构造正式API与同源Web代理，调用方负责运行与释放。</summary>
    /// <param name="args">正常宿主配置参数。</param>
    /// <param name="configure">可选的宿主级配置扩展，用于隔离环境。</param>
    /// <returns>已经配置路由但尚未启动的正式API。</returns>
    public static WebApplication CreateApplication(string[] args, Action<WebApplicationBuilder>? configure = null)
    {
        // 应用标识固定为API程序集，防止测试宿主改变OIDC或OpenAPI发现。
        var builder = WebApplication.CreateBuilder(new WebApplicationOptions { Args = args, ApplicationName = typeof(PlatformApiHost).Assembly.GetName().Name });
        configure?.Invoke(builder);
        // 在任何记录或连接前读取并验证秘密配置，不向日志输出值。
        var security = builder.Configuration.GetSection("Security").Get<PlatformSecurityOptions>() ?? new PlatformSecurityOptions();
        // 模块连接只从宿主配置提供，设计时无密码回退不用于运行时。
        var connection = builder.Configuration.GetConnectionString("governance");
        security.Validate(builder.Environment.IsDevelopment(), connection);
        // Web代理目标必须显式为内部回环源，不能从请求Host推导。
        var webOrigin = builder.Configuration["Web:Origin"];
        if (!Uri.TryCreate(webOrigin, UriKind.Absolute, out var webAddress) || !webAddress.IsLoopback
            || webAddress.Scheme != "http" || !string.IsNullOrEmpty(webAddress.UserInfo)
            || !string.IsNullOrEmpty(webAddress.Query) || webAddress.AbsolutePath != "/")
        {
            throw new InvalidOperationException("Web内部源必须显式配置为回环HTTP入口。");
        }
        if (!builder.Environment.IsDevelopment() && (builder.Configuration.GetValue<bool>("Governance:ApplyMigrations")
            || builder.Configuration.GetValue<bool>("Governance:SeedDevelopmentResources")))
        {
            throw new InvalidOperationException("生产环境禁止启动时迁移和开发合成资源初始化。");
        }
        // 屏蔽可包含code/state/token的框架请求日志；自定义日志只含固定模板。
        builder.Logging.AddFilter("Microsoft.AspNetCore.Hosting.Diagnostics", LogLevel.None);
        builder.Logging.AddFilter("Microsoft.AspNetCore.Authentication", LogLevel.None);
        builder.Logging.AddFilter("Microsoft.IdentityModel", LogLevel.None);
        builder.Logging.AddFilter("System.Net.Http.HttpClient", LogLevel.None);
        // YARP默认日志含完整上游URL及query；仅保留本宿主的固定路由安全日志。
        builder.Logging.AddFilter("Yarp.ReverseProxy", LogLevel.None);
        builder.Logging.AddFilter("Microsoft.EntityFrameworkCore", LogLevel.None);
        builder.AddServiceDefaults();
        builder.Services.AddOpenTelemetry().WithMetrics(metrics => metrics.AddMeter("OntologyPlatform.Api"))
            .WithTracing(tracing => tracing.AddSource("OntologyPlatform.Api").AddAspNetCoreInstrumentation(options =>
            {
                options.EnrichWithHttpRequest = (activity, _) => activity.SetTag("url.query", null);
            }));
        builder.Services.AddSingleton(security);
        builder.Services.AddSingleton(TimeProvider.System);
        builder.Services.AddHttpContextAccessor();
        builder.Services.AddDbContextFactory<GovernanceDbContext>(options => options.UseNpgsql(connection,
            database => database.MigrationsHistoryTable("__EFMigrationsHistory", "governance")));
        builder.Services.AddScoped<AuditService>();
        builder.Services.AddSingleton<PostgresTicketStore>();
        // macOS由.NET临时keychain导入并随证书释放删除，其余平台使用内存导入；不安装信任。
        var certificate = X509CertificateLoader.LoadPkcs12FromFile(security.CertificatePath,
            security.CertificatePassword, OperatingSystem.IsMacOS() ? X509KeyStorageFlags.DefaultKeySet : X509KeyStorageFlags.EphemeralKeySet);
        if (!certificate.HasPrivateKey || certificate.NotAfter.ToUniversalTime() <= DateTime.UtcNow)
        {
            throw new InvalidOperationException("共享密钥环证书无效。");
        }
        builder.Services.AddDataProtection().SetApplicationName("OntologyPlatform.PlatformBff.v1")
            .PersistKeysToFileSystem(new DirectoryInfo(security.KeyRingPath)).ProtectKeysWithCertificate(certificate);
        builder.Services.AddAntiforgery(options =>
        {
            options.HeaderName = "X-CSRF-TOKEN";
            options.FormFieldName = "__RequestVerificationToken";
            options.Cookie.Name = ".OntologyPlatform.Antiforgery";
            options.Cookie.HttpOnly = true;
            options.Cookie.SameSite = SameSiteMode.Strict;
            options.Cookie.SecurePolicy = builder.Environment.IsDevelopment() ? CookieSecurePolicy.SameAsRequest : CookieSecurePolicy.Always;
        });
        builder.Services.AddAuthentication(options =>
        {
            options.DefaultScheme = CookieAuthenticationDefaults.AuthenticationScheme;
            options.DefaultChallengeScheme = OpenIdConnectDefaults.AuthenticationScheme;
        }).AddCookie(options =>
        {
            options.Cookie.Name = ".OntologyPlatform.Session";
            options.Cookie.HttpOnly = true;
            options.Cookie.SameSite = SameSiteMode.Lax;
            options.Cookie.SecurePolicy = builder.Environment.IsDevelopment() ? CookieSecurePolicy.SameAsRequest : CookieSecurePolicy.Always;
            options.ExpireTimeSpan = TimeSpan.FromMinutes(30);
            options.SlidingExpiration = false;
            options.Events.OnRedirectToLogin = context => PlatformProblem.Create(context.HttpContext, 401, "unauthenticated").ExecuteAsync(context.HttpContext);
            options.Events.OnRedirectToAccessDenied = context => PlatformProblem.Create(context.HttpContext, 403, "forbidden").ExecuteAsync(context.HttpContext);
        }).AddOpenIdConnect(options => ConfigureOidc(options, security, builder.Environment.IsDevelopment()));
        builder.Services.AddOptions<CookieAuthenticationOptions>(CookieAuthenticationDefaults.AuthenticationScheme)
            .Configure<PostgresTicketStore>((options, store) => options.SessionStore = store);
        builder.Services.AddAuthorization();
        builder.Services.AddOpenApi(options => options.AddPlatformContracts());
        builder.Services.AddReverseProxy().LoadFromMemory(
            [new RouteConfig { RouteId = "web", ClusterId = "next", Match = new RouteMatch { Path = "/{**webPath}" } }],
            [new ClusterConfig { ClusterId = "next", Destinations = new Dictionary<string, DestinationConfig>
            { ["local"] = new() { Address = webAddress.ToString() } } }])
            .AddTransforms(transforms => transforms.AddRequestTransform(context =>
            {
                // 可信内部SSR需要Cookie；移除Authorization及客户端伪造身份头。
                context.ProxyRequest.Headers.Remove("Authorization");
                context.ProxyRequest.Headers.Remove("X-User");
                context.ProxyRequest.Headers.Remove("X-Roles");
                context.ProxyRequest.Headers.Remove("X-Site-Id");
                return ValueTask.CompletedTask;
            }));
        builder.Services.Configure<ForwardedHeadersOptions>(options =>
        {
            options.ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto | ForwardedHeaders.XForwardedHost;
            options.ForwardLimit = 1;
            options.RequireHeaderSymmetry = true;
            options.KnownIPNetworks.Clear();
            options.KnownProxies.Clear();
            options.AllowedHosts.Add(new Uri(security.PublicOrigin).Host);
            foreach (var proxy in security.TrustedProxies)
            {
                options.KnownProxies.Add(IPAddress.Parse(proxy));
            }
        });
        // 构建后仅组装中间件，数据库迁移与seed由显式初始化入口控制。
        var app = builder.Build();
        app.Lifetime.ApplicationStopped.Register(certificate.Dispose);
        app.Use(async (context, next) =>
        {
            // 关联ID仅接受有限安全字符，外部输入不能注入日志内容。
            var candidate = context.Request.Headers["X-Correlation-Id"].ToString();
            context.Items["CorrelationId"] = candidate.Length is >= 1 and <= 64
                && candidate.All(character => char.IsAsciiLetterOrDigit(character) || character is '.' or '-')
                    ? candidate : Guid.NewGuid().ToString("N");
            context.Response.Headers["X-Correlation-Id"] = (string)context.Items["CorrelationId"]!;
            context.Response.Headers["X-Trace-Id"] = Activity.Current?.TraceId.ToString() ?? context.TraceIdentifier;
            context.Response.Headers.CacheControl = "no-store";
            context.Response.Headers["X-Content-Type-Options"] = "nosniff";
            // 记录耗时只用UTC无关的单调时钟。
            var started = Stopwatch.GetTimestamp();
            try
            {
                // 默认拒绝任何转发声明；显式代理也必须匹配真实对端IP。
                var hasForwarded = context.Request.Headers.Keys.Any(header => header.StartsWith("X-Forwarded-", StringComparison.OrdinalIgnoreCase)
                    || header.Equals("Forwarded", StringComparison.OrdinalIgnoreCase));
                if (hasForwarded && (context.Connection.RemoteIpAddress is null
                    || !security.TrustedProxies.Any(proxy => IPAddress.Parse(proxy).Equals(context.Connection.RemoteIpAddress))))
                {
                    await PlatformProblem.Create(context, 400, "invalid_request").ExecuteAsync(context);
                    return;
                }
                await next(context);
            }
            catch (Exception) when (!context.RequestAborted.IsCancellationRequested && !context.Response.HasStarted)
            {
                // 异常细节可能包含认证或连接信息，只返回通用可关联错误。
                await PlatformProblem.Create(context, 503, "dependency_unavailable").ExecuteAsync(context);
            }
            finally
            {
                // 模板来自路由元数据，未知路径归一化，避免高基数标签。
                var route = (context.GetEndpoint() as RouteEndpoint)?.RoutePattern.RawText ?? "unmatched";
                // 标签不携带ID、厂区、主体或查询字符串。
                var tags = new TagList { { "route", route }, { "status_class", $"{context.Response.StatusCode / 100}xx" } };
                PlatformTelemetry.Requests.Add(1, tags);
                PlatformTelemetry.Duration.Record(Stopwatch.GetElapsedTime(started).TotalSeconds, tags);
                PlatformTelemetry.RequestCompleted(app.Logger, route, context.Response.StatusCode,
                    Activity.Current?.TraceId.ToString() ?? context.TraceIdentifier, context.Response.Headers["X-Audit-Id"].FirstOrDefault());
            }
        });
        if (security.TrustedProxies.Length > 0)
        {
            app.UseForwardedHeaders();
        }
        app.UseAuthentication();
        app.UseAuthorization();
        app.Use(async (context, next) =>
        {
            if (context.Request.Path.StartsWithSegments("/openapi") && !app.Environment.IsDevelopment()
                && context.User.Identity?.IsAuthenticated != true)
            {
                await PlatformProblem.Create(context, 401, "unauthenticated").ExecuteAsync(context);
                return;
            }
            await next(context);
        });
        app.MapOpenApi();
        app.MapPlatformEndpoints(security);
        // 保留技术及API前缀的未知路径也不能落入Web代理。
        foreach (var prefix in new[] { "api", "auth", "health", "openapi" })
        {
            app.Map("/" + prefix + "/{**reservedPath}", (HttpContext context) => PlatformProblem.Create(context, 404, "resource_not_found"));
        }
        app.MapReverseProxy();
        return app;
    }

    /// <summary>仅在开发环境的明确开关下应用Master生成的迁移及合成资源。</summary>
    /// <param name="app">已验证配置的正式宿主。</param>
    /// <returns>初始化事务完成的任务。</returns>
    public static async Task InitializeDevelopmentAsync(WebApplication app)
    {
        if (!app.Environment.IsDevelopment())
        {
            return;
        }
        // 显式开关不启用时连数据库都不自动修改。
        var migrate = app.Configuration.GetValue<bool>("Governance:ApplyMigrations");
        // 合成资源初始化独立开关，不能被迁移隐式触发。
        var seed = app.Configuration.GetValue<bool>("Governance:SeedDevelopmentResources");
        if (!migrate && !seed)
        {
            return;
        }
        // 初始化仅访问Governance上下文，不跨模块改表。
        await using var scope = app.Services.CreateAsyncScope();
        // 真实模块数据库，无EnsureCreated或进程内替身。
        var database = scope.ServiceProvider.GetRequiredService<GovernanceDbContext>();
        if (migrate)
        {
            await database.Database.MigrateAsync();
        }
        if (seed)
        {
            // 仅当单条开发资源不存在时创建，不覆盖已有数据库事实。
            foreach (var site in new[] { "a", "b" })
            {
                if (!await database.Resources.AnyAsync(resource => resource.Id == "platform-site-" + site))
                {
                    database.Resources.Add(new SyntheticResource
                    {
                        Id = "platform-site-" + site,
                        Name = site == "a" ? "甲厂区合成开发资源" : "乙厂区合成开发资源",
                        OrganizationId = "org-demo",
                        SiteId = "site-" + site
                    });
                }
            }
            await database.SaveChangesAsync();
        }
    }

    /// <summary>配置内置OIDC code、PKCE及state/nonce，回调目标固定来自可信配置。</summary>
    /// <param name="options">框架OIDC选项。</param>
    /// <param name="security">经验证的安全配置。</param>
    /// <param name="development">是否允许回环HTTP开发。</param>
    private static void ConfigureOidc(OpenIdConnectOptions options, PlatformSecurityOptions security, bool development)
    {
        options.Authority = security.Authority;
        options.ClientId = security.ClientId;
        options.ClientSecret = security.ClientSecret;
        options.RequireHttpsMetadata = !development;
        options.ResponseType = OpenIdConnectResponseType.Code;
        options.ResponseMode = OpenIdConnectResponseMode.Query;
        options.UsePkce = true;
        options.MapInboundClaims = false;
        options.SaveTokens = true;
        options.GetClaimsFromUserInfoEndpoint = false;
        options.Scope.Clear();
        options.Scope.Add("openid");
        options.Scope.Add("profile");
        options.TokenValidationParameters.ValidateIssuer = true;
        options.TokenValidationParameters.ValidIssuer = security.Authority.TrimEnd('/');
        options.TokenValidationParameters.ValidateAudience = true;
        options.TokenValidationParameters.ValidAudience = security.ClientId;
        options.TokenValidationParameters.NameClaimType = "name";
        options.TokenValidationParameters.RoleClaimType = ClaimTypes.Role;
        options.CorrelationCookie.SameSite = SameSiteMode.Lax;
        options.NonceCookie.SameSite = SameSiteMode.Lax;
        options.CorrelationCookie.SecurePolicy = development ? CookieSecurePolicy.SameAsRequest : CookieSecurePolicy.Always;
        options.NonceCookie.SecurePolicy = development ? CookieSecurePolicy.SameAsRequest : CookieSecurePolicy.Always;
        options.Events.OnPushAuthorization = context =>
        {
            // PAR参数只观察存在性与算法，不输出state、nonce、challenge或认证材料。
            var message = context.ProtocolMessage;
            // 安全事件记录固定布尔结果，保留框架原有推送/客户端认证行为。
            var logger = context.HttpContext.RequestServices.GetRequiredService<ILoggerFactory>().CreateLogger("OntologyPlatform.Api.Security");
            PlatformTelemetry.AuthorizationPushed(logger, message.ResponseType == "code",
                message.GetParameter("code_challenge_method") == "S256", !string.IsNullOrEmpty(message.GetParameter("code_challenge")),
                !string.IsNullOrEmpty(message.State), !string.IsNullOrEmpty(message.Nonce));
            return Task.CompletedTask;
        };
        options.Events.OnRedirectToIdentityProvider = context =>
        {
            context.ProtocolMessage.RedirectUri = security.PublicOrigin.TrimEnd('/') + "/signin-oidc";
            return Task.CompletedTask;
        };
        options.Events.OnRedirectToIdentityProviderForSignOut = context =>
        {
            context.ProtocolMessage.PostLogoutRedirectUri = security.PublicOrigin.TrimEnd('/') + "/signout-callback-oidc";
            return Task.CompletedTask;
        };
        options.Events.OnRemoteFailure = async context =>
        {
            context.HandleResponse();
            await PlatformProblem.Create(context.HttpContext, 400, "oidc_callback_invalid").ExecuteAsync(context.HttpContext);
        };
        options.Events.OnAuthenticationFailed = async context =>
        {
            context.HandleResponse();
            await PlatformProblem.Create(context.HttpContext, 400, "oidc_callback_invalid").ExecuteAsync(context.HttpContext);
        };
        options.Events.OnTokenValidated = context =>
        {
            // 只把已验证签发者中的批准角色和范围映射到服务器身份。
            var source = context.Principal!;
            // 重新创建最小身份，避免任意令牌声明污染下游授权。
            var identity = new ClaimsIdentity(CookieAuthenticationDefaults.AuthenticationScheme, "name", ClaimTypes.Role);
            foreach (var name in new[] { "sub", "name", "preferred_username", "organization_id" })
            {
                if (source.FindFirst(name) is { } claim)
                {
                    identity.AddClaim(new Claim(name, claim.Value));
                }
            }
            foreach (var claim in source.FindAll("site_ids"))
            {
                if (claim.Value.StartsWith('['))
                {
                    foreach (var site in JsonSerializer.Deserialize<string[]>(claim.Value) ?? [])
                    {
                        identity.AddClaim(new Claim("site_ids", site));
                    }
                }
                else
                {
                    identity.AddClaim(new Claim("site_ids", claim.Value));
                }
            }
            if (source.FindFirst("realm_access") is { } realm)
            {
                // Keycloak签名realm角色采用JSON数组，非平台角色一律舍弃。
                using var roles = JsonDocument.Parse(realm.Value);
                if (roles.RootElement.TryGetProperty("roles", out var values))
                {
                    foreach (var value in values.EnumerateArray())
                    {
                        if (value.GetString() is "platform.viewer" or "platform.operator" or "platform.auditor")
                        {
                            identity.AddClaim(new Claim(ClaimTypes.Role, value.GetString()!));
                        }
                    }
                }
            }
            context.Principal = new ClaimsPrincipal(identity);
            context.Properties!.IssuedUtc = DateTimeOffset.UtcNow;
            context.Properties.ExpiresUtc = DateTimeOffset.UtcNow.AddMinutes(30);
            context.Properties.AllowRefresh = false;
            return Task.CompletedTask;
        };
    }
}
