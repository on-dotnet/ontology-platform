using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Publishing;

/// <summary>发布模块组合入口，独立Catalog避免草稿和发布服务循环。</summary>
public static class PublishingModule
{
    /// <summary>注册同治理PG的模块上下文、真实对象存储和后台Outbox。</summary>
    public static IServiceCollection AddPublishingModule(this IServiceCollection services, IConfiguration configuration)
    {
        services.TryAddSingleton(TimeProvider.System);
        services.AddDbContext<PublishingDbContext>(options => options.UseNpgsql(configuration.GetConnectionString("governance"), database => database.MigrationsHistoryTable("__EFMigrationsHistory", "publishing")));
        services.AddHttpClient("publishing-s3", client => client.Timeout = TimeSpan.FromSeconds(5)).ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false });
        services.AddSingleton<IReleaseArtifactStore, RustfsArtifactStore>();
        services.AddScoped<ReleaseVerifier>();
        services.AddScoped<IReleaseCatalog, PublishingCatalog>();
        services.AddScoped<IPublishingService, PublishingService>();
        services.AddHostedService<ReleaseOutboxDispatcher>();
        return services;
    }
}
