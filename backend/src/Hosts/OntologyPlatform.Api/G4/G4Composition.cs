using System.Security.Claims;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using OntologyPlatform.Api.G2;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;
using OntologyPlatform.Modules.Governance;

namespace OntologyPlatform.Api.G4;

/// <summary>Master组合独立Connections模块，关闭时不改变既有G3运行路径。</summary>
public static class G4Composition
{
    /// <summary>开发M1仅准入明确文件凭据、固定合成源和真实PG持久化。</summary>
    public static void AddG4Module(this WebApplicationBuilder builder)
    {
        if (!builder.Configuration.GetValue<bool>("G4:Enabled")) return;
        if (!builder.Environment.IsDevelopment()) throw new InvalidOperationException("M1只允许隔离开发环境。");
        if (!builder.Configuration.GetValue<bool>("G2:Enabled"))
        {
            builder.Services.AddSingleton<IOptions<PlatformSecurityOptions>>(provider => Options.Create(provider.GetRequiredService<PlatformSecurityOptions>()));
            builder.Services.AddG2Authorization();
            builder.Services.AddScoped<TransactionalAuditWriter>();
            builder.Services.AddScoped<ITransactionalAuditWriter>(provider => provider.GetRequiredService<TransactionalAuditWriter>());
            builder.Services.AddScoped<IAuditTrail>(provider => provider.GetRequiredService<TransactionalAuditWriter>());
        }
        builder.Services.AddAuthorization(options =>
        {
            foreach (var policy in new[] { "connection.read", "schema.read" })
                options.AddPolicy(policy, rule => rule.RequireAuthenticatedUser().RequireRole("platform.operator", "platform.auditor"));
            foreach (var policy in new[] { "connection.manage", "connection.secret.manage", "connection.test", "schema.discover" })
                options.AddPolicy(policy, rule => rule.RequireAuthenticatedUser().RequireRole("platform.operator"));
        });
        builder.Services.AddDbContextFactory<ConnectionsDbContext>(options => options.UseNpgsql(builder.Configuration.GetConnectionString("governance"),
            database => database.MigrationsHistoryTable("__EFMigrationsHistory", "connections")));
        builder.Services.AddSingleton(new PgAdapterOptions
        {
            RootCertificatePath = builder.Configuration["G4:SourceCaPath"] ?? string.Empty,
            AllowedSchemas = builder.Configuration.GetValue<bool>("G4:AllowEmptyPublicSchema") ? ["production", "public"] : ["production"]
        });
        builder.Services.AddSingleton<IPgSourceAdapter, PgSourceAdapter>();
        builder.Services.AddSingleton(provider => new ConnectionSecretCipher(builder.Configuration["G4:KeyFile"] ?? string.Empty));
        builder.Services.AddSingleton<IConnectionSessionAuthority, G4SessionAuthority>();
        builder.Services.AddScoped<ConnectionApplicationService>();
        builder.Services.AddHostedService<CatalogWorker>();
        builder.Services.AddScoped<IConnectionRequestHandler>(provider => provider.GetRequiredService<ConnectionApplicationService>());
        builder.Services.AddOpenApi("g4", options => options.AddG4Contracts());
    }

    /// <summary>显式开发迁移只写Connections自己的schema。</summary>
    public static async Task InitializeG4Async(WebApplication app)
    {
        if (!app.Configuration.GetValue<bool>("G4:Enabled") || !app.Configuration.GetValue<bool>("G4:ApplyMigrations")) return;
        if (!app.Environment.IsDevelopment()) throw new InvalidOperationException("禁止生产自动迁移。");
        // 作用域由宿主初始化拥有，不跨模块写表。
        await using var scope = app.Services.CreateAsyncScope();
        // 执行已提交EF迁移，不用EnsureCreated替代。
        var factory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<ConnectionsDbContext>>();
        // 模块上下文只连接隔离平台PG。
        await using var db = await factory.CreateDbContextAsync();
        await db.Database.MigrateAsync();
    }
}

/// <summary>后台只接受仍有效的服务器票据和不变主体授权集合。</summary>
public sealed class G4SessionAuthority : IConnectionSessionAuthority
{
    /// <summary>无本地缓存的加密PG会话存储。</summary>
    private readonly PostgresTicketStore tickets;

    /// <summary>复用真实注销/过期事实，绝不伪造后台账号。</summary>
    public G4SessionAuthority(PostgresTicketStore tickets) => this.tickets = tickets;

    /// <summary>每次源IO及提交前重新比对可信角色、组织、厂区。</summary>
    public async Task<bool> IsCurrentAsync(string reference, ActorContext actor, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (string.IsNullOrEmpty(reference)) return false;
        // 解密仅发生在未撤销且未过期的服务器记录上。
        var ticket = await tickets.RetrieveAsync(reference);
        // 与捕获身份比较全量授权集合，不只检查Subject相同。
        var principal = ticket?.Principal;
        return principal?.Identity?.IsAuthenticated == true && principal.FindFirstValue("sub") == actor.SubjectId
            && principal.FindFirstValue("organization_id") == actor.OrganizationId
            && principal.FindAll("site_ids").Select(value => value.Value).Distinct().Order(StringComparer.Ordinal).SequenceEqual(actor.SiteIds.Order(StringComparer.Ordinal))
            && new[] { "platform.viewer", "platform.operator", "platform.auditor" }.Where(principal.IsInRole).Order(StringComparer.Ordinal)
                .SequenceEqual(actor.Roles.Order(StringComparer.Ordinal));
    }
}
