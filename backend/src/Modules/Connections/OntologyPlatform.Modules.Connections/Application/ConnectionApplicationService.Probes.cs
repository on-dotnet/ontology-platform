using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>持久探测预约、真实源调用及版本栅栏完成路径。</summary>
public sealed partial class ConnectionApplicationService
{
    /// <summary>读取报告时重新检查资源及捕获范围，过期不能恢复为新成功。</summary>
    private async Task<ConnectionReply> ReadProbeAsync(ConnectionInvocation call, CancellationToken token)
    {
        // 短上下文只读取当前授权事实。
        await using var db = await factory.CreateDbContextAsync(token);
        // 先检查连接，避免通过探测ID跨范围枚举。
        var row = await FindAsync(db, call.Actor, call.Id, token);
        // 探测必须属于指定连接及组织。
        var probe = await db.ConnectionProbes.AsNoTracking().SingleOrDefaultAsync(value => value.Id == call.ChildId
            && value.ConnectionId == row.Id && value.OrganizationId == call.Actor.OrganizationId, token)
            ?? throw new SemanticOperationException(403, "connection_scope_forbidden");
        // 捕获范围也需仍被当前身份完整覆盖。
        var report = Decode<ConnectionProbeView>(probe.ReportJson);
        DemandScope(call.Actor, report.Scope);
        return new ConnectionReply { Value = report with { Stale = report.Stale || row.LastProbeId != probe.Id || row.State == "DISABLED"
            || report.ConfigHash != row.ConfigHash || report.SecretVersion != row.SecretVersion || report.ExpiresAtUtc <= clock.GetUtcNow() } };
    }

    /// <summary>先提交RUNNING与审计，再在事务外调用源；重试只读取原探测。</summary>
    private async Task<ConnectionReply> ProbeAsync(ConnectionInvocation call, CancellationToken token)
    {
        // 草稿和保存后探测共用固定阶段，身份与秘密绑定分别检查。
        var draft = call.Body as ConnectionDraftProbeRequest;
        // 请求模型已通过严格字段与修订验证。
        var command = draft?.Command ?? ((ConnectionMutationCommand)call.Body!).Command;
        // 只由创建预约的请求持有真实源输入，重放不会重新连接。
        PgConnectionProfile? profile = null;
        // 明文仅留在当前调用内存，不进入报告或命令回执。
        string? secret = null;
        // 同事务预约可在进程中断后保持真实RUNNING记录。
        var reserved = await CommandAsync<ConnectionProbeView>(call, command, "connection.probe.start", 200, async (db, ct) =>
        {
            // 当前连接可为空，草稿没有可枚举GET路由。
            ConnectionRecord? row = null;
            // 捕获范围由可信资源或已授权的草稿子集决定。
            var scope = Normalize(draft?.ScopeSelection ?? Scope(row = await FindAsync(db, call.Actor, call.Id, ct)));
            DemandScope(call.Actor, scope);
            if (row is not null)
            {
                Cas(call, row, command);
                if (row.State == "DISABLED") throw new SemanticOperationException(409, "connection_disabled");
            }
            // 同一保存连接只允许一个未过期探测。
            if (row is not null && await db.ConnectionProbes.AnyAsync(value => value.ConnectionId == row.Id && value.Deadline > clock.GetUtcNow()
                && value.ReportJson.Contains("RUNNING"), ct)) throw new SemanticOperationException(409, "connection_version_conflict");
            profile = Pg(draft?.Config ?? Decode<ConnectionConfig>(row!.ConfigJson));
            // 草稿Ref尚未消费；保存连接使用已绑定版本，不受入库TTL影响。
            var credential = draft is not null ? await UnboundSecretAsync(db, call.Actor, draft.SecretRef, scope, ct)
                : await db.ConnectionSecrets.SingleAsync(value => value.Id == row!.SecretId, ct);
            secret = cipher.Decrypt(credential);
            // 真实开始时刻是唯一期限依据。
            var now = clock.GetUtcNow();
            // 没执行的阶段明确NOT_RUN。
            var report = new ConnectionProbeView { ProbeId = Guid.NewGuid().ToString("N"), ConnectionId = row?.Id,
                ConfigHash = row?.ConfigHash ?? Hash(Encode(new { Scope = scope, draft!.Config })), SecretVersion = credential.Version,
                Scope = scope, Status = "RUNNING", Stages = new[] { "NETWORK", "TLS", "AUTH", "READ_ONLY", "METADATA" }
                    .Select(name => new ConnectionProbeStage { Name = name, Status = "NOT_RUN", DurationMs = 0, DiagnosticCode = null }).ToArray(),
                StartedAtUtc = now, CompletedAtUtc = null, ExpiresAtUtc = now.AddMinutes(10), TraceId = call.Actor.TraceId, Stale = false };
            db.ConnectionProbes.Add(new ConnectionProbeRecord { Revision = row?.Revision ?? 0, CommandKey = CommandKey(call, command), ActorJson = Encode(call.Actor), Id = report.ProbeId, OrganizationId = scope.OrganizationId, SiteIds = scope.SiteIds,
                ConnectionId = row?.Id, Owner = call.Actor.SubjectId, ReportJson = Encode(report), ConfigHash = report.ConfigHash,
                SecretVersion = report.SecretVersion, ExpiresAtUtc = report.ExpiresAtUtc, Deadline = now.AddSeconds(15) });
            return (report, scope, scope, row is null ? null : Etag(row));
        }, token);
        if (profile is null || secret is null) return reserved;
        // 请求断开或10秒截止都会传播到真实Npgsql取消。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        deadline.CancelAfter(TimeSpan.FromSeconds(10));
        // 预约返回值只包含非敏感状态。
        var original = (ConnectionProbeView)reserved.Value;
        // 失败默认不产生任何成功阶段。
        var stages = original.Stages;
        try
        {
            if (!await authority.IsCurrentAsync(call.SessionReference, call.Actor, deadline.Token))
                throw new OperationCanceledException();
            stages = await adapter.ProbeAsync(profile, secret, deadline.Token);
        }
        catch (OperationCanceledException)
        {
            stages = stages.Select(value => value with { Status = "NOT_VERIFIED", DiagnosticCode = "connection_cancelled" }).ToArray();
        }
        catch (PgSourceException exception)
        {
            stages = stages.Select(value => value with { Status = "NOT_VERIFIED", DiagnosticCode = exception.Code }).ToArray();
        }
        finally { secret = null; }
        // 独立有界完成期限允许客户端断开后写真实终态，绝不复用已取消请求token。
        using var completion = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        // 会话注销后不把源成功提升为可用报告。
        var current = await authority.IsCurrentAsync(call.SessionReference, call.Actor, completion.Token);
        // 完成时重新取得资源锁，旧版本调用不能覆盖编辑/轮换/禁用。
        await using var finalDb = await factory.CreateDbContextAsync(completion.Token);
        await using var transaction = await finalDb.Database.BeginTransactionAsync(completion.Token);
        await LockAsync(finalDb, CommandKey(call, command), completion.Token);
        if (call.Id is not null) await LockAsync(finalDb, "connection:" + call.Id, completion.Token);
        // 持久预约是完成提交的准确对象。
        var record = await finalDb.ConnectionProbes.SingleAsync(value => value.Id == original.ProbeId, completion.Token);
        if (Decode<ConnectionProbeView>(record.ReportJson).Status != "RUNNING")
            return new ConnectionReply { Value = Decode<ConnectionProbeView>(record.ReportJson), Etag = reserved.Etag };
        // 源调用期间资源可能已经改变，不能用旧输入回写状态。
        var connection = call.Id is null ? null : await finalDb.Connections.SingleAsync(value => value.Id == call.Id, completion.Token);
        // 权限及绑定版本均是完成条件。
        var stale = !current || record.Deadline <= clock.GetUtcNow() || connection is not null && (connection.Revision != record.Revision || connection.State == "DISABLED" || connection.ConfigHash != original.ConfigHash
            || connection.SecretVersion != original.SecretVersion);
        // 报告中的成功必须真实完整且没有取消或失效。
        var reportDone = original with { Stages = stages, CompletedAtUtc = clock.GetUtcNow(), Stale = stale,
            Status = !stale && stages.All(value => value.Status == "PASS") ? "TEST_OK" : stages.Any(value => value.DiagnosticCode == "connection_cancelled") ? "CANCELLED" : "TEST_FAILED" };
        record.ReportJson = Encode(reportDone);
        record.Deadline = clock.GetUtcNow();
        if (connection is not null && !stale) connection.LastProbeId = original.ProbeId;
        // 原命令指向相同探测的最终结果，重试不会调用源。
        var receipt = await finalDb.ConnectionCommands.SingleAsync(value => value.Id == CommandKey(call, command), completion.Token);
        receipt.ReceiptJson = Encode(reportDone);
        await SaveAuditAsync(finalDb, call.Actor, "connection.probe.complete", call.Id ?? original.ProbeId, original.Scope, completion.Token);
        await transaction.CommitAsync(completion.Token);
        return new ConnectionReply { Value = reportDone, Etag = reserved.Etag };
    }

}
