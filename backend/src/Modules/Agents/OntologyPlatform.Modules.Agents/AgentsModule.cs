using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Hosting;

namespace OntologyPlatform.Modules.Agents;

/// <summary>注册独立agents schema和默认禁用模型的运行器。</summary>
public static class AgentsModule
{
    /// <summary>复用governance物理数据库，模块只拥有自己的表。</summary>
    public static IServiceCollection AddAgentsModule(this IServiceCollection services, IConfiguration configuration)
    {
        // 连接串由宿主显式配置，不读取或输出认证材料。
        var connection = configuration.GetConnectionString("governance") ?? throw new InvalidOperationException("缺少治理数据库配置。");
        services.AddDbContextFactory<AgentsDbContext>(options => options.UseNpgsql(connection, database => database.MigrationsHistoryTable("__EFMigrationsHistory", "agents")));
        services.TryAddSingleton(TimeProvider.System);
        services.AddScoped<ExecutionRunService>();
        services.AddScoped<AgentRunExecutor>();
        services.AddHostedService<AgentRunWorker>();
        return services;
    }
}

/// <summary>短轮询PG候选，多实例以行锁竞争，不把本地队列作为真相。</summary>
internal sealed class AgentRunWorker : BackgroundService
{
    /// <summary>为每次执行创建独立请求服务作用域。</summary>
    private readonly IServiceScopeFactory scopes;

    /// <summary>当前进程工作者随机标识，不写入指标标签。</summary>
    private readonly string workerId = Guid.NewGuid().ToString("N");

    /// <summary>仅接收作用域工厂，不跨运行共享DbContext。</summary>
    public AgentRunWorker(IServiceScopeFactory scopes) => this.scopes = scopes;

    /// <summary>失败后保留PG租约等待恢复，不把异常原文写日志。</summary>
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                // 每次候选由新scope获得实际Gateway和事务writer。
                await using var scope = scopes.CreateAsyncScope();
                if (await scope.ServiceProvider.GetRequiredService<AgentRunExecutor>().RunOneAsync(workerId, stoppingToken)) continue;
            }
            catch (Exception failure) when (failure is not OutOfMemoryException && !stoppingToken.IsCancellationRequested)
            {
                // 依赖恢复之后由PG租约接管；不输出含Prompt/SQL的异常。
            }
            await Task.Delay(TimeSpan.FromMilliseconds(200), stoppingToken);
        }
    }
}
