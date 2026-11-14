using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>治理通知至少一次投递；重复eventId去重且旧修订不能覆盖新投影。</summary>
public sealed class MappingOutboxDispatcher : BackgroundService
{
    /// <summary>只操作Connections持有的outbox、receipt和通知投影。</summary>
    private readonly IDbContextFactory<ConnectionsDbContext> factory;

    /// <summary>统一UTC消费时间。</summary>
    private readonly TimeProvider clock;

    /// <summary>仅输出固定失败码，避免持久内容泄漏。</summary>
    private readonly ILogger<MappingOutboxDispatcher> logger;

    /// <summary>此消费者仅通知治理状态，不执行M4业务映射。</summary>
    public MappingOutboxDispatcher(IDbContextFactory<ConnectionsDbContext> factory, TimeProvider clock, ILogger<MappingOutboxDispatcher> logger)
    {
        this.factory = factory;
        this.clock = clock;
        this.logger = logger;
    }

    /// <summary>每两秒最多消费一个事件，失败保留待投递原件。</summary>
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                // 候选仅提供身份，消费事务仍重新读取。
                await using var db = await factory.CreateDbContextAsync(stoppingToken);
                // 不跳过历史未投递事件，不按当前Active推测已消费。
                var id = await db.MappingOutboxs.AsNoTracking().Where(row => row.DispatchedAtUtc == null)
                    .OrderBy(row => row.CreatedAtUtc).ThenBy(row => row.Id).Select(row => row.Id).FirstOrDefaultAsync(stoppingToken);
                if (id is not null)
                {
                    await DispatchAsync(id, stoppingToken);
                }
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception error) when (error is not OutOfMemoryException)
            {
                logger.LogWarning("映射通知等待重试：mapping_outbox_unavailable");
            }
            await Task.Delay(TimeSpan.FromSeconds(2), clock, stoppingToken);
        }
    }

    /// <summary>同一入口用于宿主和真实重复/乱序验收，不允许调用方传入事件正文。</summary>
    public async Task DispatchAsync(string eventId, CancellationToken token)
    {
        G4MappingRules.Identifier(eventId);
        // 单次投递全过程五秒，不能占据无界后台资源。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        deadline.CancelAfter(TimeSpan.FromSeconds(5));
        token = deadline.Token;
        // 记录尝试独立提交，后续事务失败仍留下实际尝试次数。
        await using var attempt = await factory.CreateDbContextAsync(token);
        // 查固定内部outbox，不接受HTTP提交的伪造通知。
        var candidate = await attempt.MappingOutboxs.AsNoTracking().SingleOrDefaultAsync(row => row.Id == eventId, token)
            ?? throw new SemanticOperationException(409, "mapping_outbox_missing");
        _ = await attempt.MappingOutboxs.Where(row => row.Id == eventId && row.Attempts < G4MappingRules.MaximumRevision)
            .ExecuteUpdateAsync(update => update.SetProperty(row => row.Attempts, row => row.Attempts + 1), token);
        // 消费原子事务将receipt与单调投影和投递确认共同提交。
        await using var db = await factory.CreateDbContextAsync(token);
        // 后台不再获取组织授权锁，不会形成反向锁顺序。
        await using var transaction = await db.Database.BeginTransactionAsync(token);
        await db.Database.ExecuteSqlRawAsync("SET LOCAL lock_timeout = '2s'; SET LOCAL statement_timeout = '5s'", token);
        await ConnectionApplicationService.LockAsync(db, "mapping:" + candidate.MappingId, token);
        // 重新读取真实事件，不相信候选读取后可变的状态。
        var item = await db.MappingOutboxs.SingleAsync(row => row.Id == eventId, token);
        if (!await db.MappingOutboxReceipts.AnyAsync(row => row.Id == eventId, token))
        {
            // 正式历史必须证明通知身份与单调版本真实存在。
            var activation = await db.MappingActivations.AsNoTracking().SingleOrDefaultAsync(row => row.MappingId == item.MappingId
                && row.ActivationRevision == item.ActivationRevision && row.ReleaseId == item.ReleaseId && row.OrganizationId == item.OrganizationId, token)
                ?? throw new SemanticOperationException(409, "mapping_outbox_binding_invalid");
            // 原激活回执绑定准确eventId及manifestHash。
            var receipt = MappingApplicationService.Original<MappingActivationReceipt>(activation.CanonicalBytes, activation.ContentHash);
            if (receipt.OutboxEventId != item.Id || receipt.ManifestHash != item.ManifestHash)
            {
                throw new SemanticOperationException(409, "mapping_outbox_binding_invalid");
            }
            // 任何顺序到达都只提升版本，不根据releaseId大小排序。
            var state = await db.MappingNotifications.SingleOrDefaultAsync(row => row.MappingId == item.MappingId, token);
            if (state is null)
            {
                state = new MappingNotificationRecord { MappingId = item.MappingId, OrganizationId = item.OrganizationId };
                db.MappingNotifications.Add(state);
            }
            if (item.ActivationRevision > state.ActivationRevision)
            {
                state.ActivationRevision = item.ActivationRevision;
                state.ReleaseId = item.ReleaseId;
                state.ManifestHash = item.ManifestHash;
                state.EventId = item.Id;
            }
            db.MappingOutboxReceipts.Add(new MappingOutboxReceiptRecord
            {
                Id = item.Id,
                MappingId = item.MappingId,
                ActivationRevision = item.ActivationRevision,
                CreatedAtUtc = clock.GetUtcNow()
            });
        }
        item.DispatchedAtUtc ??= clock.GetUtcNow();
        await db.SaveChangesAsync(token);
        await transaction.CommitAsync(token);
    }
}
