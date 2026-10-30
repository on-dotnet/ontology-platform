using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Agents;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.Ontology;
using OntologyPlatform.Modules.Publishing;
using OntologyPlatform.Modules.SemanticQuery;

namespace OntologyPlatform.Api.G2;

/// <summary>由Master唯一组合逐步集成的G2模块，未启用时保留原G1路径。</summary>
public static class G2Composition
{
    /// <summary>注册已实际实现的语义、事务审计及共同授权，不创建替代业务服务。</summary>
    /// <param name="builder">已经配置G1安全与持久化的宿主。</param>
    public static void AddG2Modules(this WebApplicationBuilder builder)
    {
        if (!builder.Configuration.GetValue<bool>("G2:Enabled"))
        {
            return;
        }
        if (!builder.Environment.IsDevelopment() && builder.Configuration.GetValue<bool>("G2:ApplyMigrations"))
        {
            throw new InvalidOperationException("生产G2禁止启动时应用迁移。");
        }
        // 复用主宿主已经验证的单一安全对象，避免guard拿到未绑定的默认空来源。
        builder.Services.AddSingleton<IOptions<PlatformSecurityOptions>>(provider => Options.Create(provider.GetRequiredService<PlatformSecurityOptions>()));
        builder.Services.AddG2Authorization();
        builder.Services.AddScoped<TransactionalAuditWriter>();
        builder.Services.AddScoped<ITransactionalAuditWriter>(provider => provider.GetRequiredService<TransactionalAuditWriter>());
        builder.Services.AddScoped<IAuditTrail>(provider => provider.GetRequiredService<TransactionalAuditWriter>());
        builder.Services.AddOntologyModule(builder.Configuration);
        builder.Services.AddPublishingModule(builder.Configuration);
        builder.Services.AddSemanticQueryModule(builder.Configuration);
        builder.Services.AddAgentsModule(builder.Configuration);
        builder.Services.AddSemanticMcpEndpoints();
        builder.Services.AddHttpClient("g2-readiness").ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false });
        builder.Services.AddOpenTelemetry()
            .WithTracing(tracing => tracing.AddSource("OntologyPlatform.Ontology", "OntologyPlatform.Publishing", "OntologyPlatform.SemanticQuery", "OntologyPlatform.Agents"))
            .WithMetrics(metrics => metrics.AddMeter("OntologyPlatform.Ontology", "OntologyPlatform.Publishing", "OntologyPlatform.SemanticQuery", "OntologyPlatform.Agents"));
    }

    /// <summary>只挂载当前真实模块路由，S2/S3随各自实现和集成门禁加入。</summary>
    /// <param name="app">已经使用原BFF认证管道的宿主。</param>
    public static void MapG2Endpoints(this WebApplication app)
    {
        if (app.Configuration.GetValue<bool>("G2:Enabled"))
        {
            app.MapOntologyEndpoints();
            app.MapVocabularyEndpoints();
            app.MapIdentityTimeEndpoints();
            app.MapImpactEndpoints();
            app.MapG3Endpoints();
            app.MapPublishingEndpoints();
            app.MapSemanticEndpoints();
            app.MapExecutionEndpoints();
            app.MapMcpEndpoints();
        }
    }

    /// <summary>仅在明确开发开关下应用Master提交的真实本体迁移。</summary>
    /// <param name="app">已经验证配置的宿主。</param>
    /// <returns>真实数据库迁移完成任务。</returns>
    public static async Task InitializeG2DevelopmentAsync(WebApplication app)
    {
        if (!app.Environment.IsDevelopment() || !app.Configuration.GetValue<bool>("G2:Enabled")
            || !app.Configuration.GetValue<bool>("G2:ApplyMigrations"))
        {
            return;
        }
        // 每模块仅由自己的DbContext迁移自己schema，不跨模块写表。
        await using var scope = app.Services.CreateAsyncScope();
        // 先前Governance初始化已在同一启动进程完成。
        var database = scope.ServiceProvider.GetRequiredService<OntologyDbContext>();
        await database.Database.MigrateAsync();
        // 发布模块独立迁移且保留其历史，不跨写其他schema。
        var publishing = scope.ServiceProvider.GetRequiredService<PublishingDbContext>();
        await publishing.Database.MigrateAsync();
        // 持久Run和事件也由自己的模块迁移，另一个实例只读取共享结果。
        var agents = scope.ServiceProvider.GetRequiredService<AgentsDbContext>();
        await agents.Database.MigrateAsync();
    }
}
