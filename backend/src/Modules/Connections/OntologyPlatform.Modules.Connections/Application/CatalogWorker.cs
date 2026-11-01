using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;

namespace OntologyPlatform.Modules.Connections;

/// <summary>单消费者后台循环；多实例由PG领取锁和fence保证恢复边界。</summary>
public sealed class CatalogWorker : BackgroundService
{
    /// <summary>每轮创建独立业务与审计作用域。</summary>
    private readonly IServiceScopeFactory scopes;

    /// <summary>仅固定安全事件，不输出原异常或源SQL。</summary>
    private readonly ILogger<CatalogWorker> logger;

    /// <summary>宿主提供作用域与日志设施。</summary>
    public CatalogWorker(IServiceScopeFactory scopes, ILogger<CatalogWorker> logger)
    {
        this.scopes = scopes;
        this.logger = logger;
    }

    /// <summary>依赖故障时保留持久任务，等待租约恢复，不造成功结果。</summary>
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                // 当前轮业务服务不跨请求或任务缓存身份。
                await using var scope = scopes.CreateAsyncScope();
                // 应用服务统一拥有模块状态机及同事务审计。
                var service = scope.ServiceProvider.GetRequiredService<ConnectionApplicationService>();
                await service.RecoverProbesAsync(stoppingToken);
                if (await service.RunOneAsync(stoppingToken)) continue;
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception)
            {
                logger.LogWarning("Connections background operation unavailable; durable lease retained.");
            }
            try { await Task.Delay(TimeSpan.FromSeconds(1), stoppingToken); }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
        }
    }
}
