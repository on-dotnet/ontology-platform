using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>本体模块唯一组合入口，配置由宿主Single Writer提供。</summary>
public static class OntologyModule
{
    /// <summary>注册专属PG上下文与受控Jena运行时，连接与治理共库但不同schema。</summary>
    /// <param name="services">宿主服务集合。</param>
    /// <param name="configuration">可信启动配置。</param>
    /// <returns>原服务集合。</returns>
    public static IServiceCollection AddOntologyModule(this IServiceCollection services, IConfiguration configuration)
    {
        services.AddDbContext<OntologyDbContext>(options => options.UseNpgsql(configuration.GetConnectionString("governance"), database => database.MigrationsHistoryTable("__EFMigrationsHistory", "ontology")));
        services.AddHttpClient("ontology-jena").ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false });
        services.AddSingleton<JenaSemanticRuntime>();
        services.AddSingleton<ISemanticRuntime>(provider => provider.GetRequiredService<JenaSemanticRuntime>());
        services.AddSingleton<IG3VocabularyRuntime>(provider => provider.GetRequiredService<JenaSemanticRuntime>());
        services.AddSingleton<IG3VersionDiffRuntime>(provider => provider.GetRequiredService<JenaSemanticRuntime>());
        services.AddSingleton<IG3ExpressionRuntime>(provider => provider.GetRequiredService<JenaSemanticRuntime>());
        services.AddSingleton<IG3SemanticRuntime>(provider => provider.GetRequiredService<JenaSemanticRuntime>());
        services.AddScoped<OntologyService>();
        services.AddScoped<IG3ExpressionService>(provider => provider.GetRequiredService<OntologyService>());
        services.AddScoped<IG3ImpactService>(provider => provider.GetRequiredService<OntologyService>());
        services.AddScoped<IG3IdentityTimeService>(provider => provider.GetRequiredService<OntologyService>());
        services.AddScoped<IG3VocabularyService>(provider => provider.GetRequiredService<OntologyService>());
        services.AddScoped<IG3OntologyService>(provider => provider.GetRequiredService<OntologyService>());
        services.AddScoped<IOntologyService>(provider => provider.GetRequiredService<OntologyService>());
        services.AddScoped<IImpactPublicationReader>(provider => provider.GetRequiredService<OntologyService>());
        services.AddScoped<IDraftPublicationReader>(provider => provider.GetRequiredService<OntologyService>());
        return services;
    }
}
