using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>启用使用持久预约在真实源调用前去重，不长持平台事务。</summary>
public sealed partial class ConnectionApplicationService
{
    /// <summary>当前完整Probe、源权限复查及最终CAS同时成立才启用。</summary>
    private async Task<ConnectionReply> EnableAsync(ConnectionInvocation call, CancellationToken token)
    {
        // 固定命令和完整请求HMAC用于两阶段预约与重放。
        var command = ((ConnectionMutationCommand)call.Body!).Command;
        // 不依赖可变scope的准确幂等查找键。
        var key = CommandKey(call, command);
        // HMAC包括前置ETag，不存凭据散列。
        var requestHash = cipher.RequestHash(Encode(new { call.Body, call.Etag }));
        // 仅完成预约的请求获得真实源输入。
        PgConnectionProfile profile;
        // 合成秘密只留当前调用内存。
        string secret;
        // 同一事务完成当前授权、CAS、Probe资格和预约。
        await using (var db = await factory.CreateDbContextAsync(token))
        {
            // 源IO开始前即释放本事务及连接。
            await using var transaction = await db.Database.BeginTransactionAsync(token);
            await LockAsync(db, key, token);
            // 已完成或进行中的同键请求都不会再次访问源。
            var replay = await ReplayAsync(db, call, key, requestHash, typeof(ConnectionView), token);
            if (replay is not null) return replay;
            await LockAsync(db, "connection:" + call.Id, token);
            // 当前资源状态是预约的唯一依据。
            var row = await FindAsync(db, call.Actor, call.Id, token);
            Cas(call, row, command);
            if (row.State == "DISABLED" || !await FreshAsync(db, row, token)) throw new SemanticOperationException(409, "connection_probe_stale");
            if (!await authority.IsCurrentAsync(call.SessionReference, call.Actor, token)) throw new SemanticOperationException(401, "authentication_required");
            profile = Pg(Decode<ConnectionConfig>(row.ConfigJson));
            // 凭据仅在完整授权通过后解密。
            var credential = await db.ConnectionSecrets.SingleAsync(value => value.Id == row.SecretId, token);
            secret = cipher.Decrypt(credential);
            db.ConnectionCommands.Add(new ConnectionCommandRecord
            {
                Id = key,
                RequestHash = requestHash,
                ScopeJson = Encode(Scope(row)),
                ResultScopeJson = Encode(Scope(row)),
                ReceiptJson = "null",
                CreatedAtUtc = clock.GetUtcNow(),
                StatusCode = 102
            });
            await db.SaveChangesAsync(token);
            await transaction.CommitAsync(token);
        }
        // 默认失败关闭，只有真实五阶段PASS才能提交ACTIVE。
        string? failure = null;
        // 失败HTTP分类不携异常详情。
        var status = 409;
        try
        {
            // Adapter使用新的VerifyFull物理连接重新验证当前只读权限。
            var stages = await adapter.ProbeAsync(profile, secret, token);
            if (stages.Any(value => value.Status != "PASS")) failure = "connection_probe_stale";
        }
        catch (OperationCanceledException) { failure = "connection_cancelled"; }
        catch (PgSourceException) { failure = "connection_probe_stale"; }
        finally { secret = string.Empty; }
        // 即使请求取消，也用独立有界期限持久记录失败预约。
        using var completion = new CancellationTokenSource(TimeSpan.FromSeconds(5));
        if (!await authority.IsCurrentAsync(call.SessionReference, call.Actor, completion.Token)) { failure = "authentication_required"; status = 401; }
        // 第二个短事务与编辑/禁用串行，不跨源IO持锁。
        await using var finalDb = await factory.CreateDbContextAsync(completion.Token);
        // 原命令只可从预约完成一次。
        await using var finalTransaction = await finalDb.Database.BeginTransactionAsync(completion.Token);
        await LockAsync(finalDb, key, completion.Token);
        await LockAsync(finalDb, "connection:" + call.Id, completion.Token);
        // 查准确预约，不能覆盖另一个幂等请求。
        var receipt = await finalDb.ConnectionCommands.SingleAsync(value => value.Id == key, completion.Token);
        // 已有当前组织范围授权的连接在最终事务重新取值。
        var current = await finalDb.Connections.SingleAsync(value => value.Id == call.Id, completion.Token);
        if (current.Revision != command.ExpectedRevision || current.State == "DISABLED" || receipt.CreatedAtUtc.AddSeconds(20) <= clock.GetUtcNow()
            || !await FreshAsync(finalDb, current, completion.Token)) failure ??= "connection_version_conflict";
        if (failure is not null)
        {
            receipt.StatusCode = status;
            receipt.ErrorCode = failure;
            await finalDb.SaveChangesAsync(completion.Token);
            await finalTransaction.CommitAsync(completion.Token);
            throw new SemanticOperationException(status, failure);
        }
        DemandScope(call.Actor, Scope(current));
        current.State = "ACTIVE";
        current.Revision++;
        current.UpdatedAtUtc = clock.GetUtcNow();
        // 原成功回执与业务状态及审计共同提交。
        var view = await ViewAsync(finalDb, call.Actor, current, completion.Token);
        receipt.ReceiptJson = Encode(view);
        receipt.Etag = Etag(current);
        receipt.StatusCode = 200;
        await SaveAuditAsync(finalDb, call.Actor, "connection.enable", current.Id, Scope(current), completion.Token);
        await finalTransaction.CommitAsync(completion.Token);
        return new ConnectionReply { Value = view, Etag = receipt.Etag };
    }
}
