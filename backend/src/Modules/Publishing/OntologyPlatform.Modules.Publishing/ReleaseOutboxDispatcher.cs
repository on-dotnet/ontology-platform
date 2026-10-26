using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace OntologyPlatform.Modules.Publishing;

/// <summary>真正后台至少一次调和，通知不改变权威active或删除历史制品。</summary>
public sealed class ReleaseOutboxDispatcher : BackgroundService
{
    /// <summary>每次尝试独立scope和上下文。</summary>
    private readonly IServiceScopeFactory scopes;

    /// <summary>租约及退避时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>本进程唯一租约持有者。</summary>
    private readonly string owner = Guid.NewGuid().ToString("N");

    /// <summary>注入生命周期工厂与时钟，不捕获请求scope。</summary>
    public ReleaseOutboxDispatcher(IServiceScopeFactory scopes, TimeProvider clock)
    {
        this.scopes = scopes;
        this.clock = clock;
    }

    /// <summary>持续处理持久Outbox，失败保留下一次调和机会。</summary>
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                if (!await DispatchOnceAsync(stoppingToken)) await Task.Delay(TimeSpan.FromSeconds(1), clock, stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested) { break; }
            catch (Exception)
            {
                // 固定计数不记录底层异常、正文或连接信息。
                PublishingTelemetry.Record("outbox", "failure", "lease");
                await Task.Delay(TimeSpan.FromSeconds(2), clock, stoppingToken);
            }
        }
    }

    /// <summary>一次真实租约、外部核验和唯一回执消费，供隔离故障矩阵调用。</summary>
    public async Task<bool> DispatchOnceAsync(CancellationToken token)
    {
        // 独立scope确保每次重新读取数据库事实。
        using var scope = scopes.CreateScope();
        // 本模块上下文不跨生命周期共享。
        var database = scope.ServiceProvider.GetRequiredService<PublishingDbContext>();
        // 当前时间决定重试窗口和过期租约。
        var now = clock.GetUtcNow();
        // 固定事件快照携带本次租约fence。
        OutboxRecord? item;
        await using (var transaction = await database.Database.BeginTransactionAsync(token))
        {
            // SKIP LOCKED让多worker分工，锁只覆盖租约领取。
            item = await database.Outbox.FromSqlInterpolated($"SELECT * FROM publishing.\"Outbox\" WHERE \"DispatchedAtUtc\" IS NULL AND \"NextAttemptAtUtc\"<={now} AND (\"LeaseUntilUtc\" IS NULL OR \"LeaseUntilUtc\"<={now}) ORDER BY \"CreatedAtUtc\" LIMIT 1 FOR UPDATE SKIP LOCKED").SingleOrDefaultAsync(token);
            if (item is null) return false;
            item.LeaseOwner = owner;
            item.LeaseUntilUtc = now.AddSeconds(30);
            item.FencingToken++;
            item.Attempts++;
            await database.SaveChangesAsync(token);
            await transaction.CommitAsync(token);
        }
        database.ChangeTracker.Clear();
        // 真实验证结果不能依赖缓存的可用性。
        var verified = false;
        try
        {
            // 延迟事件始终读取固定旧版，不重新解析active造成混版。
            var release = await database.Releases.AsNoTracking().SingleAsync(row => row.ReleaseId == item.ReleaseId && row.Published, token);
            if (release.ManifestHash != item.PayloadHash) throw new InvalidOperationException("事件固定版本绑定不匹配。");
            await scope.ServiceProvider.GetRequiredService<ReleaseVerifier>().VerifyAsync(release, token);
            verified = true;
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { throw; }
        catch (Exception)
        {
            // 无法回验仅退避，不变更active、不生成成功回执。
            PublishingTelemetry.Record("outbox", "failure", "verify");
        }
        await using (var transaction = await database.Database.BeginTransactionAsync(token))
        {
            // 提交时检查fence和租约，过期worker无权写回。
            var current = await database.Outbox.FromSqlInterpolated($"SELECT * FROM publishing.\"Outbox\" WHERE \"EventId\"={item.EventId} FOR UPDATE").SingleAsync(token);
            if (current.FencingToken != item.FencingToken || current.LeaseOwner != owner || current.LeaseUntilUtc <= clock.GetUtcNow() || current.DispatchedAtUtc is not null) return true;
            if (verified)
            {
                // eventId唯一主键保证重启和重复消费只产生一条回执。
                if (!await database.Receipts.AnyAsync(row => row.EventId == item.EventId, token))
                {
                    database.Receipts.Add(new OutboxReceiptRecord { EventId = item.EventId, ReleaseId = item.ReleaseId, ManifestHash = item.PayloadHash, VerifiedAtUtc = clock.GetUtcNow() });
                }
                current.DispatchedAtUtc = clock.GetUtcNow();
                PublishingTelemetry.Record("outbox", "allowed", "consume");
            }
            else current.NextAttemptAtUtc = clock.GetUtcNow().AddSeconds(Math.Min(60, 1 << Math.Min(current.Attempts, 5)));
            current.LeaseOwner = null;
            current.LeaseUntilUtc = null;
            await database.SaveChangesAsync(token);
            await transaction.CommitAsync(token);
        }
        return true;
    }
}
