using Microsoft.EntityFrameworkCore;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>注册唯一正式语义Gateway及可跨实例重建的证据读取服务。</summary>
public static class SemanticQueryModule
{
    /// <summary>依赖由Ontology、Publishing及Governance各自拥有，不复制适配器或业务写入。</summary>
    public static IServiceCollection AddSemanticQueryModule(this IServiceCollection services, IConfiguration configuration)
    {
        ArgumentNullException.ThrowIfNull(configuration);
        if (configuration.GetValue<bool>("G4:QueryEnabled"))
        {
            services.AddDbContextFactory<G4QueryDbContext>(options => options.UseNpgsql(configuration.GetConnectionString("governance"),
                postgres => postgres.MigrationsHistoryTable("__EFMigrationsHistory", "semantic_query")));
            services.AddScoped(provider =>
            {
                // 任务专用key ring由受控运行环境创建，不能退回用户全局key ring。
                var path = configuration["G4:QueryKeyRingPath"];
                if (string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path) || !Directory.Exists(path))
                    throw new InvalidOperationException("查询专用密钥目录未准备。");
                if (!OperatingSystem.IsWindows() && (File.GetUnixFileMode(path) & (UnixFileMode.GroupRead | UnixFileMode.GroupWrite | UnixFileMode.GroupExecute
                    | UnixFileMode.OtherRead | UnixFileMode.OtherWrite | UnixFileMode.OtherExecute)) != 0)
                    throw new InvalidOperationException("查询专用密钥目录权限不符合要求。");
                // 专用应用身份与结果purpose共同隔离查询密文，不复用认证票据密钥。
                var protection = DataProtectionProvider.Create(new DirectoryInfo(path), builder => builder.SetApplicationName("OntologyPlatform.G4-M4-QUERY-001"));
                return new G4QueryResultStore(provider.GetRequiredService<IDbContextFactory<G4QueryDbContext>>(),
                    provider.GetRequiredService<IG4QueryAuthorizationAuthority>(), provider.GetRequiredService<IG4QueryBindingReader>(),
                    provider.GetRequiredService<ITransactionalAuditWriter>(), protection, provider.GetRequiredService<TimeProvider>());
            });
            services.AddScoped<IG4QueryRunStore>(provider => provider.GetRequiredService<G4QueryResultStore>());
            services.AddScoped<G4QueryExecution>();
            services.AddHostedService<G4QueryWorker>();
        }
        services.AddSingleton<CapabilityRegistry>();
        services.AddScoped<VerifiedReleaseSources>();
        services.AddScoped<ISemanticGateway, SemanticGateway>();
        services.AddScoped<IEvidenceService, EvidenceService>();
        return services;
    }
}
