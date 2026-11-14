using System.Data.Common;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>后台只终结失联执行及删除到期记录，不取得源执行权或重放查询。</summary>
public sealed class G4QueryWorker : BackgroundService
{
    /// <summary>每轮取得独立正式作用域，禁止长期持有DbContext或业务结果。</summary>
    private readonly IServiceScopeFactory scopes;

    /// <summary>同宿主统一UTC时间与可取消维护计时器。</summary>
    private readonly TimeProvider clock;

    /// <summary>只记录固定无值维护错误，不传入数据库异常正文。</summary>
    private readonly ILogger<G4QueryWorker> logger;

    /// <summary>只有显式启用G4查询的宿主注册此维护服务。</summary>
    public G4QueryWorker(IServiceScopeFactory scopes, TimeProvider clock, ILogger<G4QueryWorker> logger)
    {
        this.scopes = scopes;
        this.clock = clock;
        this.logger = logger;
    }

    /// <summary>每两秒有界扫描，宿主取消立即结束，失败不打印源或票据内容。</summary>
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        // 计时器不会因失败进行无间隔重试，也不扩张源读取预算。
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(2), clock);
        try
        {
            while (await timer.WaitForNextTickAsync(stoppingToken))
            {
                try
                {
                    // 每轮最多六十四个准确候选，作用域结束释放所有连接。
                    await using var scope = scopes.CreateAsyncScope();
                    // 维护与普通执行复用同一正式结果存储，不写另一套清理SQL。
                    var store = scope.ServiceProvider.GetRequiredService<G4QueryResultStore>();
                    // 维护自己的截止不属于任何已完成或已取消查询的延长期。
                    using var budget = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
                    budget.CancelAfter(TimeSpan.FromSeconds(5));
                    await store.SweepAsync(budget.Token);
                }
                catch (OperationCanceledException) when (!stoppingToken.IsCancellationRequested)
                {
                    logger.LogWarning("query_maintenance_timeout");
                }
                catch (Exception error) when (error is DbException or SemanticOperationException)
                {
                    logger.LogWarning("query_maintenance_failed");
                }
            }
        }
        catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
        {
            // 正常宿主停止不重试，也不启动任何源或外部服务。
        }
    }
}
