using System.Security.Cryptography;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>持久验证任务消费者：有界租约、递增fence、源IO不占平台事务。</summary>
public sealed class MappingJobWorker : BackgroundService
{
    /// <summary>每轮创建独立作用域，不将应用服务跨线程共享。</summary>
    private readonly IServiceScopeFactory scopes;

    /// <summary>日志只输出固定代码，不包含SQL、源值或秘密异常。</summary>
    private readonly ILogger<MappingJobWorker> logger;

    /// <summary>统一可替换UTC时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>宿主显式注册后才消费本任务队列。</summary>
    public MappingJobWorker(IServiceScopeFactory scopes, ILogger<MappingJobWorker> logger, TimeProvider clock)
    {
        this.scopes = scopes;
        this.logger = logger;
        this.clock = clock;
    }

    /// <summary>每轮至多一个任务；关闭时保留租约供新进程恢复。</summary>
    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                _ = await RunNextAsync(stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                break;
            }
            catch (Exception error) when (error is not OutOfMemoryException)
            {
                logger.LogWarning("映射任务消费者暂不可用：mapping_worker_unavailable");
            }
            await Task.Delay(TimeSpan.FromSeconds(2), clock, stoppingToken);
        }
    }

    /// <summary>执行一个持久任务，供真实PG验收与宿主使用同一路径。</summary>
    public async Task<bool> RunNextAsync(CancellationToken token)
    {
        // 新作用域使失败事务不会污染下一轮EF追踪。
        await using var scope = scopes.CreateAsyncScope();
        // 每个模块只使用自己的上下文工厂。
        var factory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<ConnectionsDbContext>>();
        // 当前权限与会话复核由Governance参与者完成。
        var authority = scope.ServiceProvider.GetRequiredService<IMappingAuthorizationAuthority>();
        // 审计与最终结果共享事务，不用后台异步审计代替。
        var audit = scope.ServiceProvider.GetRequiredService<ITransactionalAuditWriter>();
        // 真正七阶段源执行器，不用任务状态模拟评估。
        var validator = scope.ServiceProvider.GetRequiredService<MappingValidationService>();
        // 复用应用服务的完整字段授权与输入复核。
        var application = scope.ServiceProvider.GetRequiredService<MappingApplicationService>();
        // 候选查询只是提示，真正领取需要锁内重查。
        await using var lookup = await factory.CreateDbContextAsync(token);
        // 一个进程每轮至多领取一个，过期租约也进入同一受控路径。
        var now = clock.GetUtcNow();
        // 候选不含任何源行，后台只消费平台自己保存的输入。
        var candidate = await lookup.MappingJobs.AsNoTracking().Where(row => row.Status == "QUEUED"
            || row.Status == "RUNNING" && row.LeaseUntil <= now).OrderBy(row => row.CreatedAtUtc).ThenBy(row => row.Id).FirstOrDefaultAsync(token);
        if (candidate is null)
        {
            return false;
        }
        // 原始会话证明不能由worker换成系统身份。
        var proof = MappingApplicationService.Decode<MappingAuthorizationProof>(candidate.AuthorityJson);
        // 固定目标和定义原件，不取当前最新编辑头替代。
        var input = MappingApplicationService.Decode<MappingJobInput>(candidate.RequestJson);
        // 尚未领取时使用候选fence，失败终态必须同时匹配原状态修订。
        var fence = candidate.Fence;
        // 记录本轮实际领取后的修订，避免覆盖其它工作者。
        var revision = candidate.Revision;
        try
        {
            // 源字段权限也须在领取前当前有效。
            var proofs = await application.AccessAsync(proof.Actor, proof.SessionReference, input.Draft, "mapping.validate", token);
            if (proofs[0].AuthorizationEpoch != proof.AuthorizationEpoch || proof.ExpiresAtUtc <= clock.GetUtcNow())
            {
                throw new SemanticOperationException(409, "mapping_authorization_stale");
            }
            // 领取事务总限五秒，网络评估不在此事务内。
            using (var deadline = CancellationTokenSource.CreateLinkedTokenSource(token))
            {
                deadline.CancelAfter(TimeSpan.FromSeconds(5));
                // 独立上下文只保存短租约。
                await using var db = await factory.CreateDbContextAsync(deadline.Token);
                // 锁顺序保持组织/会话授权、连接、mapping。
                await using var transaction = await db.Database.BeginTransactionAsync(deadline.Token);
                foreach (var current in proofs.OrderBy(item => item.Permission, StringComparer.Ordinal))
                {
                    await authority.DemandInTransactionAsync(current, db.Database.GetDbConnection(), transaction.GetDbTransaction(), deadline.Token);
                }
                await ConnectionApplicationService.LockAsync(db, "connection:" + input.Draft.SourceConnectionId, deadline.Token);
                await ConnectionApplicationService.LockAsync(db, "mapping:" + candidate.MappingId, deadline.Token);
                // 领取时再查状态，另一进程可能已先领取或用户已取消。
                var job = await db.MappingJobs.SingleAsync(row => row.Id == candidate.Id, deadline.Token);
                if (job.Revision != candidate.Revision || job.Status != "QUEUED" && !(job.Status == "RUNNING" && job.LeaseUntil <= clock.GetUtcNow()))
                {
                    return true;
                }
                job.Status = "RUNNING";
                job.Revision = MappingApplicationService.Increment(job.Revision);
                job.Fence = MappingApplicationService.Increment(job.Fence);
                job.LeaseUntil = clock.GetUtcNow().AddSeconds(60);
                fence = job.Fence;
                revision = job.Revision;
                await db.SaveChangesAsync(deadline.Token);
                await transaction.CommitAsync(deadline.Token);
            }
            // 真正源IO与G3原件检查均受评估器统一30秒预算控制。
            var report = await validator.AssessAsync(proof.Actor, proof.SessionReference, input.Draft, input.Target, "mapping.validate", token);
            // 业务完成必须仍在原组织epoch与原租约内。
            if (report.Binding.AuthorizationEpoch != proof.AuthorizationEpoch)
            {
                throw new SemanticOperationException(409, "mapping_authorization_stale");
            }
            // 提交前重新取得字段证明，防止源观察期间字段grant撤销。
            var finalProofs = await application.AccessAsync(proof.Actor, proof.SessionReference, input.Draft, "mapping.validate", token);
            // 五秒平台提交预算与源预算分离。
            using var finishDeadline = CancellationTokenSource.CreateLinkedTokenSource(token);
            finishDeadline.CancelAfter(TimeSpan.FromSeconds(5));
            // 最终结果与治理审计加入同一个物理PG事务。
            await using var finish = await factory.CreateDbContextAsync(finishDeadline.Token);
            // 不借旧领取事务跨网络持锁。
            await using var finishTransaction = await finish.Database.BeginTransactionAsync(finishDeadline.Token);
            foreach (var current in finalProofs.OrderBy(item => item.Permission, StringComparer.Ordinal))
            {
                await authority.DemandInTransactionAsync(current, finish.Database.GetDbConnection(), finishTransaction.GetDbTransaction(), finishDeadline.Token);
            }
            await ConnectionApplicationService.LockAsync(finish, "connection:" + input.Draft.SourceConnectionId, finishDeadline.Token);
            await ConnectionApplicationService.LockAsync(finish, "mapping:" + candidate.MappingId, finishDeadline.Token);
            // fence、revision和租约同时验证；旧worker永远不能覆盖新结果。
            var finishing = await finish.MappingJobs.SingleAsync(row => row.Id == candidate.Id, finishDeadline.Token);
            if (finishing.Status != "RUNNING" || finishing.Fence != fence || finishing.Revision != revision || finishing.LeaseUntil <= clock.GetUtcNow())
            {
                return true;
            }
            await application.CurrentAsync(finish, input.Draft, input.Target, report.Binding, report.ExpectedActive, finalProofs[0].AuthorizationEpoch, finishDeadline.Token);
            // 保存完整原字节与独立hash，触发器保证只追加。
            var bytes = MappingCanonical.Serialize(report);
            finish.MappingAssessments.Add(new MappingAssessmentRecord
            {
                Id = report.AssessmentId,
                MappingId = candidate.MappingId,
                OrganizationId = input.Draft.Scope.OrganizationId,
                SiteIds = input.Draft.Scope.SiteIds,
                CanonicalBytes = bytes,
                ContentHash = Convert.ToHexStringLower(SHA256.HashData(bytes)),
                CreatedAtUtc = report.FinishedAtUtc,
                TargetKind = input.Target is MappingPublishTarget ? "PUBLISH" : "ROLLBACK",
                TargetId = input.Target is MappingRollbackTarget rollback ? rollback.TargetReleaseId : input.Draft.DraftId,
                TargetRevision = input.Target is MappingPublishTarget publish ? publish.DraftRevision : 0,
                BindingJson = MappingApplicationService.Encode(report.Binding),
                SemanticResultHash = report.SemanticResultHash,
                ImpactHash = report.Binding.ImpactHash,
                Status = report.Status,
                ExpiresAtUtc = report.ExpiresAtUtc
            });
            finishing.Status = "SUCCEEDED";
            finishing.ResultId = report.AssessmentId;
            finishing.Revision = MappingApplicationService.Increment(finishing.Revision);
            finishing.CompletedAtUtc = clock.GetUtcNow();
            finishing.LeaseUntil = null;
            await finish.SaveChangesAsync(finishDeadline.Token);
            _ = await audit.WriteAsync(proof.Actor, new AuditCommand
            {
                Action = "mapping.validate.finish",
                Resource = "mapping:" + candidate.MappingId,
                Outcome = "allowed",
                Scope = input.Draft.Scope
            }, finish.Database.GetDbConnection(), finishTransaction.GetDbTransaction(), finishDeadline.Token);
            await finishTransaction.CommitAsync(finishDeadline.Token);
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested)
        {
            // 宿主关闭留下租约，恢复进程重新领取；不冒充业务失败或完成。
            throw;
        }
        catch (Exception error) when (error is not OutOfMemoryException)
        {
            // 撤权只允许形成安全失败终态，不创建Assessment或向外返回源正文。
            var code = error is SemanticOperationException semantic ? semantic.Code : error is OperationCanceledException ? "mapping_assessment_budget_exceeded" : "mapping_validation_failed";
            await FailAsync(factory, audit, candidate.Id, candidate.MappingId, proof, fence, revision, code, token);
        }
        return true;
    }

    /// <summary>仅清算失败元数据，撤权后不能因无法成功授权而无限保持RUNNING。</summary>
    private async Task FailAsync(IDbContextFactory<ConnectionsDbContext> factory, ITransactionalAuditWriter audit, string jobId, string mappingId,
        MappingAuthorizationProof proof, long fence, long revision, string code, CancellationToken token)
    {
        // 失败终态不读取源、不创建结果，不需要授予已撤销主体任何业务权限。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        deadline.CancelAfter(TimeSpan.FromSeconds(5));
        // 独立事务不复用可能已回滚的成功上下文。
        await using var db = await factory.CreateDbContextAsync(deadline.Token);
        // 仅获取mapping锁，之后不再申请组织锁，避免反向锁序。
        await using var transaction = await db.Database.BeginTransactionAsync(deadline.Token);
        await ConnectionApplicationService.LockAsync(db, "mapping:" + mappingId, deadline.Token);
        // 原fence或revision改变表示另一个写者已接管，不得覆盖。
        var job = await db.MappingJobs.SingleAsync(row => row.Id == jobId, deadline.Token);
        if (job.Fence != fence || job.Revision != revision || job.Status is not ("QUEUED" or "RUNNING"))
        {
            return;
        }
        job.Status = "FAILED";
        job.ErrorCode = code;
        job.CompletedAtUtc = clock.GetUtcNow();
        job.LeaseUntil = null;
        job.Revision = MappingApplicationService.Increment(job.Revision);
        await db.SaveChangesAsync(deadline.Token);
        _ = await audit.WriteAsync(proof.Actor, new AuditCommand
        {
            Action = "mapping.validate.finish",
            Resource = "mapping:" + mappingId,
            Outcome = "denied",
            Scope = proof.Scope
        }, db.Database.GetDbConnection(), transaction.GetDbTransaction(), deadline.Token);
        await transaction.CommitAsync(deadline.Token);
    }
}
