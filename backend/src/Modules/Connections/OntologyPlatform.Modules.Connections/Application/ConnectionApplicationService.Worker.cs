using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>有界恢复、租约栅栏和真实源取消的目录消费者。</summary>
public sealed partial class ConnectionApplicationService
{
    /// <summary>每轮最多领取一个任务，lease失效只允许第二次尝试。</summary>
    public async Task<bool> RunOneAsync(CancellationToken token)
    {
        // 领取仅持短事务，源调用不占平台事务。
        await using var db = await factory.CreateDbContextAsync(token);
        // 全局领取锁仅协调当前模块多个实例。
        await using var transaction = await db.Database.BeginTransactionAsync(token);
        await LockAsync(db, "connection:catalog-claim", token);
        // 到期RUNNING可被新fence接管，旧进程随后无法提交。
        var now = clock.GetUtcNow();
        // 每轮一项避免同实例占满源和内存预算。
        var job = await db.CatalogJobs.Where(value => value.Status == "QUEUED" || value.Status == "RUNNING" && value.LeaseUntil < now)
            .OrderBy(value => value.CreatedAtUtc).FirstOrDefaultAsync(token);
        if (job is null) return false;
        // 恢复仍使用捕获的可信身份，但IO前必须重新验票据。
        var actor = Decode<ActorContext>(job.ActorJson);
        // 任务本身保留完整捕获范围供审计及授权。
        var scope = new ResourceScope { OrganizationId = job.OrganizationId, SiteIds = job.SiteIds };
        job.Fence++;
        if (job.CancelRequested || job.Attempt >= 2)
        {
            job.Status = job.CancelRequested ? "CANCELLED" : "FAILED";
            job.CompletedAtUtc = now;
            await SaveAuditAsync(db, actor, "connection.catalog.finish", job.ConnectionId, scope, token);
            await transaction.CommitAsync(token);
            return true;
        }
        job.Status = "RUNNING";
        job.Attempt++;
        job.LeaseUntil = now.AddSeconds(30);
        await db.SaveChangesAsync(token);
        await transaction.CommitAsync(token);
        await ExecuteJobAsync(job, actor, token);
        return true;
    }

    /// <summary>在所有旧报告上记录真实进程中断，不把未知探测结果补为成功。</summary>
    public async Task RecoverProbesAsync(CancellationToken token)
    {
        // 候选查询不持锁；每个准确命令随后在自己的短事务重验。
        await using var candidates = await factory.CreateDbContextAsync(token);
        // 有界集合防止一次恢复吞没平台数据库。
        var ids = await candidates.ConnectionProbes.AsNoTracking().Where(value => value.Deadline < clock.GetUtcNow()
            && value.ReportJson.Contains("RUNNING")).Select(value => value.Id).Take(50).ToArrayAsync(token);
        foreach (var id in ids)
        {
            // 每条探测使用与正常完成完全相同的锁顺序。
            await using var db = await factory.CreateDbContextAsync(token);
            // 先只读查出准确命令，不用模糊JSON搜索回执。
            var known = await db.ConnectionProbes.AsNoTracking().SingleAsync(value => value.Id == id, token);
            // 恢复终态与原始治理审计共同提交。
            await using var transaction = await db.Database.BeginTransactionAsync(token);
            await LockAsync(db, known.CommandKey, token);
            if (known.ConnectionId is not null) await LockAsync(db, "connection:" + known.ConnectionId, token);
            // 取得锁后重新读取，正常完成赢得竞争则不覆盖。
            var row = await db.ConnectionProbes.SingleAsync(value => value.Id == id, token);
            // 未过期或已经终态的记录无需恢复。
            var original = Decode<ConnectionProbeView>(row.ReportJson);
            if (row.Deadline >= clock.GetUtcNow() || original.Status != "RUNNING") continue;
            row.ReportJson = Encode(original with { Status = "TEST_FAILED", Stale = true, CompletedAtUtc = clock.GetUtcNow() });
            // 原准确命令只能恢复到同一探测的失败终态。
            var receipt = await db.ConnectionCommands.SingleAsync(value => value.Id == row.CommandKey, token);
            receipt.ReceiptJson = row.ReportJson;
            await SaveAuditAsync(db, Decode<ActorContext>(row.ActorJson), "connection.probe.complete", row.ConnectionId ?? row.Id, original.Scope, token);
            await transaction.CommitAsync(token);
        }
    }

    /// <summary>固定20秒源调用配合持久取消观察，完成前重验会话/版本/fence。</summary>
    private async Task ExecuteJobAsync(CatalogJobRecord claimed, ActorContext actor, CancellationToken stopping)
    {
        // 租约大于源20秒期限及短提交期限，避免正常任务重复领取。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(stopping);
        deadline.CancelAfter(TimeSpan.FromSeconds(20));
        // 观察器独立停止信号避免完成后继续轮询。
        using var observing = CancellationTokenSource.CreateLinkedTokenSource(deadline.Token);
        // 初始状态在真实结果产生前保持失败关闭。
        var status = "FAILED";
        // 只有完整真实目录才有可提交对象。
        CatalogObject[]? objects = null;
        // 固定诊断分类不携底层异常或SQL。
        string? diagnostic = null;
        // 同时观察禁用、取消、角色撤销和版本变化。
        var watch = WatchJobAsync(claimed, actor, deadline, observing.Token);
        try
        {
            // 实时会话授权先于任何源IO。
            if (!await authority.IsCurrentAsync(claimed.SessionReference, actor, deadline.Token)) throw new OperationCanceledException();
            // 源输入来自当前受控记录，不使用浏览器旧配置。
            await using var read = await factory.CreateDbContextAsync(deadline.Token);
            // 先完整资源授权，再解密绑定秘密。
            var connection = await FindAsync(read, actor, claimed.ConnectionId, deadline.Token);
            if (!Matches(claimed, connection)) throw new OperationCanceledException();
            // 用当前版本建立全新物理连接。
            var secret = await read.ConnectionSecrets.SingleAsync(value => value.Id == connection.SecretId, deadline.Token);
            objects = await adapter.DiscoverAsync(Pg(Decode<ConnectionConfig>(connection.ConfigJson)), cipher.Decrypt(secret), deadline.Token);
            status = "SUCCEEDED";
        }
        catch (OperationCanceledException) { status = "CANCELLED"; diagnostic = "connection_cancelled"; }
        catch (PgSourceException exception)
        {
            diagnostic = exception.Code;
            status = exception.Code is "catalog_permission_limited" or "catalog_budget_exceeded" ? "PARTIAL"
                : exception.Code == "connection_cancelled" ? "CANCELLED" : "FAILED";
        }
        finally
        {
            await observing.CancelAsync();
            try { await watch; } catch (OperationCanceledException) { }
        }
        if (stopping.IsCancellationRequested) return;
        // 服务重启期间让lease恢复；正常完成即使客户端已走也要提交真实终态。
        using var completion = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        // 提交前实时角色与注销验证，不能只用领取时快照。
        var authorized = await authority.IsCurrentAsync(claimed.SessionReference, actor, completion.Token);
        // 此处开始第二个短事务，源连接已经释放。
        await using var finalDb = await factory.CreateDbContextAsync(completion.Token);
        // 资源锁串行化编辑、禁用和目录结果提交。
        await using var transaction = await finalDb.Database.BeginTransactionAsync(completion.Token);
        await LockAsync(finalDb, "connection:" + claimed.ConnectionId, completion.Token);
        // fence是跨进程旧工作者提交的硬门禁。
        var job = await finalDb.CatalogJobs.SingleAsync(value => value.Id == claimed.Id, completion.Token);
        if (job.Fence != claimed.Fence || job.Status != "RUNNING" || job.LeaseUntil <= clock.GetUtcNow()) return;
        // 记录完成时真实资源版本及当前状态。
        var row = await finalDb.Connections.SingleAsync(value => value.Id == claimed.ConnectionId, completion.Token);
        if (!authorized || job.CancelRequested || !Matches(job, row)) status = "CANCELLED";
        job.Status = status;
        job.CompletedAtUtc = clock.GetUtcNow();
        job.LeaseUntil = null;
        job.DiagnosticCode = diagnostic;
        if (status == "SUCCEEDED" && objects is not null)
        {
            // 排序后的内容和适配器版本构成指纹，捕获时间不参与内容相等性。
            var canonical = CanonicalCatalog(objects);
            // 快照是新行，绝不修改历史内容。
            var snapshot = new CatalogSnapshotView
            {
                SnapshotId = Guid.NewGuid().ToString("N"),
                ConnectionId = row.Id,
                ConfigRevision = job.Revision,
                SecretVersion = job.SecretVersion,
                Scope = Scope(row),
                SchemaFingerprint = canonical.Fingerprint,
                CapturedAtUtc = clock.GetUtcNow(),
                Status = "READY",
                Objects = canonical.Objects
            };
            finalDb.CatalogSnapshots.Add(new CatalogSnapshotRecord
            {
                Id = snapshot.SnapshotId,
                ConnectionId = row.Id,
                OrganizationId = row.OrganizationId,
                SiteIds = row.SiteIds,
                ConfigHash = job.ConfigHash,
                SecretVersion = job.SecretVersion,
                ViewJson = Encode(snapshot),
                CapturedAtUtc = snapshot.CapturedAtUtc
            });
            job.SnapshotId = snapshot.SnapshotId;
        }
        await SaveAuditAsync(finalDb, actor, "connection.catalog.finish", row.Id, Scope(row), completion.Token);
        await transaction.CommitAsync(completion.Token);
    }

    /// <summary>只接受仍启用且与捕获版本完全一致的源输入。</summary>
    private static bool Matches(CatalogJobRecord job, ConnectionRecord row) => row.State == "ACTIVE" && row.Revision == job.Revision
        && row.SecretVersion == job.SecretVersion && row.ConfigHash == job.ConfigHash && row.OrganizationId == job.OrganizationId
        && row.SiteIds.Order(StringComparer.Ordinal).SequenceEqual(job.SiteIds.Order(StringComparer.Ordinal));

    /// <summary>短轮询把持久取消、注销和编辑传播到实际驱动token。</summary>
    private async Task WatchJobAsync(CatalogJobRecord claimed, ActorContext actor, CancellationTokenSource operation, CancellationToken token)
    {
        while (!token.IsCancellationRequested)
        {
            await Task.Delay(TimeSpan.FromMilliseconds(250), token);
            // 每轮独立上下文确保不读取EF跟踪缓存的旧状态。
            await using var db = await factory.CreateDbContextAsync(token);
            // 任务和连接必须仍匹配当前栅栏。
            var job = await db.CatalogJobs.AsNoTracking().SingleAsync(value => value.Id == claimed.Id, token);
            // 源状态变化必须立即取消进行中的Npgsql调用。
            var row = await db.Connections.AsNoTracking().SingleAsync(value => value.Id == claimed.ConnectionId, token);
            if (job.CancelRequested || job.Fence != claimed.Fence || !Matches(claimed, row)
                || !await authority.IsCurrentAsync(claimed.SessionReference, actor, token))
            {
                await operation.CancelAsync();
                return;
            }
        }
    }
}
