using Microsoft.EntityFrameworkCore;
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
        }
        services.AddSingleton<CapabilityRegistry>();
        services.AddScoped<VerifiedReleaseSources>();
        services.AddScoped<ISemanticGateway, SemanticGateway>();
        services.AddScoped<IEvidenceService, EvidenceService>();
        return services;
    }
}
