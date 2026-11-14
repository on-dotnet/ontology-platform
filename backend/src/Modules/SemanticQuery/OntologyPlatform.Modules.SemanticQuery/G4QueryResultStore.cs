using System.Security.Cryptography;
using System.Globalization;
using System.Text.Json;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>查询结果的规范字节加密边界；授权与到期检查由调用方在解密前执行。</summary>
public sealed class G4QueryResultStore
{
    /// <summary>查询独占模型的短生命周期工厂。</summary>
    private readonly IDbContextFactory<G4QueryDbContext> factory;

    /// <summary>同事务当前会话及完整字段授权参与者。</summary>
    private readonly IG4QueryAuthorizationAuthority authority;

    /// <summary>Connections模块拥有的固定版本复核。</summary>
    private readonly IG4QueryBindingReader bindings;

    /// <summary>与查询状态共同提交的治理审计。</summary>
    private readonly ITransactionalAuditWriter audit;

    /// <summary>专属任务keyring，由正式宿主配置，不使用认证purpose。</summary>
    private readonly IDataProtectionProvider protection;

    /// <summary>租约、到期与deadline使用统一UTC时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>只依赖模块公开参与者，不直接写治理或连接表。</summary>
    public G4QueryResultStore(IDbContextFactory<G4QueryDbContext> factory, IG4QueryAuthorizationAuthority authority,
        IG4QueryBindingReader bindings, ITransactionalAuditWriter audit, IDataProtectionProvider protection, TimeProvider clock)
    {
        this.factory = factory;
        this.authority = authority;
        this.bindings = bindings;
        this.audit = audit;
        this.protection = protection;
        this.clock = clock;
    }

    /// <summary>按授权、版本、任务容量的固定锁顺序原子登记执行；源IO在事务外发生。</summary>
    public async Task<G4QueryAdmission> AdmitAsync(MappingAuthorizationProof session, MappingAuthorizationProof[] proofs,
        G4SemanticQuery query, G4QueryState state, string idempotencyKey, string? selectionQueryId, string owner,
        DateTimeOffset deadline, CancellationToken token)
    {
        if (idempotencyKey.Length is < 1 or > 128 || idempotencyKey.Any(value => value < 0x21 || value > 0x7e))
            throw new SemanticOperationException(422, "query_idempotency_invalid");
        DemandIdentity(owner);
        // hash包含选择上下文，不能复用同一幂等键绕过候选绑定。
        var request = G4QueryCanonical.Serialize(new { query, selectionQueryId });
        // 输入字节已经由请求合同校验，内部安全材料另行限制任务总量。
        var hash = G4QueryCanonical.Hash(request);
        // 每次调用创建新上下文，防止旧跟踪状态掩盖跨实例竞争。
        await using var database = await factory.CreateDbContextAsync(token);
        // 同物理事务按组织授权、连接版本、查询容量顺序取得锁。
        await using var transaction = await database.Database.BeginTransactionAsync(token);
        await DemandAsync(database, session, proofs, token);
        // 主体组织域内的幂等键不能泄露其他用户的查询。
        var existing = await database.Queries.SingleOrDefaultAsync(row => row.OrganizationId == session.Actor.OrganizationId
            && row.SubjectId == session.Actor.SubjectId && row.IdempotencyKey == idempotencyKey, token);
        if (existing is not null)
        {
            if (existing.RequestHash != hash) throw new SemanticOperationException(409, "query_idempotency_conflict");
            if (existing.ExpiresAtUtc <= clock.GetUtcNow()) throw new SemanticOperationException(410, "result_expired");
            // 历史结果按保存的投影重新授权，不要求当前Active重新等于历史版本。
            var saved = JsonSerializer.Deserialize<G4QueryState>(existing.BindingBytes, G4QueryJson.Options)
                ?? throw new SemanticOperationException(503, "query_result_invalid");
            DemandProofSet(saved with { Binding = saved.Binding with { AuthorizationEpoch = session.AuthorizationEpoch.ToString(CultureInfo.InvariantCulture) } }, session, proofs);
            await transaction.CommitAsync(token);
            return new G4QueryAdmission { Record = existing, Created = false };
        }
        DemandProofSet(state, session, proofs);
        await bindings.VerifyInTransactionAsync(session.Actor, query, state.Binding, database.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
        await LockCapacityAsync(database, token);
        // 容量计数在跨实例事务锁内执行，过期执行仍占位直到被worker明确终结。
        var running = database.Queries.Where(row => row.ExecutionStatus == "RUNNING");
        if (await running.CountAsync(token) >= 4
            || await running.CountAsync(row => row.ConnectionId == state.Binding.ConnectionId, token) >= 2
            || await running.AnyAsync(row => row.OrganizationId == session.Actor.OrganizationId && row.SubjectId == session.Actor.SubjectId, token))
            throw new SemanticOperationException(429, "query_capacity_exhausted");
        // 安全材料自身也有任务总预算，不能无限积累空结果绕过容量限制。
        var metadata = G4QueryCanonical.Serialize(state);
        await DemandStorageAsync(database, request.Length + metadata.Length, 0, token);
        // 实际准入时间决定24小时结果保留期；调用方不能延长原deadline。
        var now = clock.GetUtcNow();
        if (deadline <= now || deadline > now.AddSeconds(5)) throw new SemanticOperationException(503, "query_timeout");
        // 随机身份与fence共同固定本次执行权，后续恢复永不重放源查询。
        var record = new G4QueryRecord
        {
            Id = "query-" + Guid.NewGuid().ToString("N"), OrganizationId = session.Actor.OrganizationId,
            SubjectId = session.Actor.SubjectId, SessionReference = session.SessionReference, ConnectionId = state.Binding.ConnectionId,
            IdempotencyKey = idempotencyKey, RequestHash = hash, RequestBytes = request, BindingBytes = metadata,
            CreatedAtUtc = now, DeadlineAtUtc = deadline, ExpiresAtUtc = now.AddHours(24),
            LeaseOwner = owner, LeaseUntilUtc = deadline < now.AddSeconds(10) ? deadline : now.AddSeconds(10), Fence = 1
        };
        database.Queries.Add(record);
        await database.SaveChangesAsync(token);
        await transaction.CommitAsync(token);
        return new G4QueryAdmission { Record = record, Created = true };
    }

    /// <summary>来源完成后在短事务中重验当前授权与版本，密文和成功审计共同提交。</summary>
    public async Task CompleteAsync(G4QueryRecord lease, MappingAuthorizationProof session, MappingAuthorizationProof[] proofs,
        G4SemanticQuery query, G4QueryState state, G4QueryResultV1 result, G4QueryStoredReceipt[] receipts, CancellationToken token)
    {
        DemandProofSet(state, session, proofs);
        if (result.Snapshot.OntologyReleaseId != state.Binding.OntologyReleaseId
            || !result.Snapshot.MappingReleaseIds.SequenceEqual(new[] { state.Binding.MappingReleaseId })
            || result.Snapshot.CapabilityVersion != state.Binding.CapabilityVersion
            || result.Snapshot.CapabilityId != query.CapabilityId
            || !result.Snapshot.SourceCatalogSnapshotIds.SequenceEqual(new[] { state.Binding.CurrentCatalogSnapshotId })
            || result.Evidence.Any(item => item.ConnectionId != state.Binding.ConnectionId
                || item.MappingReleaseId != state.Binding.MappingReleaseId || item.SourceCatalogSnapshotId != state.Binding.OriginalCatalogSnapshotId
                || item.Scope.OrganizationId != state.Scope.OrganizationId || !item.Scope.SiteIds.All(state.Scope.SiteIds.Contains))
            || (result.Data.Length != 0 || result.Candidates.Length != 0) && proofs.Length == 0)
            throw new SemanticOperationException(503, "query_result_invalid");
        // 规范校验和加密在事务前完成，业务值只在有界内存中暂存。
        var encrypted = Protect(protection, lease.Id, result);
        // 回执与结果一起验证闭合，外置摘要不会形成循环散列。
        var completedMetadata = G4QueryCanonical.Serialize(G4SourceEvidenceService.BindReceipts(lease.Id, state, result, receipts));
        // 当前数据库事务不复用执行前的连接或跟踪实体。
        await using var database = await factory.CreateDbContextAsync(token);
        // 成功与撤权、取消的线性化点是这笔显式事务提交。
        await using var transaction = await database.Database.BeginTransactionAsync(token);
        await DemandAsync(database, session, proofs, token);
        await bindings.VerifyInTransactionAsync(session.Actor, query, state.Binding, database.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
        await LockCapacityAsync(database, token);
        // 固定身份行锁与租约条件防止取消后或过期worker的迟到提交。
        var current = await LockedAsync(database, lease.Id, token);
        // 实际提交请求必须与准入原件一致；仅比较调用方携带的hash不能阻止换query参数。
        using var savedRequest = JsonDocument.Parse(current.RequestBytes);
        if (current.RequestHash != G4QueryCanonical.Hash(current.RequestBytes)
            || !G4QueryCanonical.Value(savedRequest.RootElement.GetProperty("query")).AsSpan().SequenceEqual(G4QueryCanonical.Serialize(query)))
            throw new SemanticOperationException(409, "query_request_mismatch");
        if (current.ExecutionStatus != "RUNNING" || current.CancelRequested || current.Fence != lease.Fence
            || current.OrganizationId != session.Actor.OrganizationId || current.SubjectId != session.Actor.SubjectId
            || current.RequestHash != lease.RequestHash || !current.BindingBytes.AsSpan().SequenceEqual(G4QueryCanonical.Serialize(state))
            || current.LeaseOwner != lease.LeaseOwner || current.LeaseUntilUtc <= clock.GetUtcNow()
            || current.DeadlineAtUtc <= clock.GetUtcNow()) throw new SemanticOperationException(409, "query_execution_stale");
        await DemandStorageAsync(database, completedMetadata.Length - current.BindingBytes.Length, encrypted.Size, token);
        current.BindingBytes = completedMetadata;
        current.ResultCiphertext = encrypted.Ciphertext;
        current.ResultHash = encrypted.Hash;
        current.ResultSize = encrypted.Size;
        current.ExecutionStatus = "COMPLETED";
        current.CompletedAtUtc = clock.GetUtcNow();
        current.LeaseUntilUtc = null;
        current.LeaseOwner = null;
        await database.SaveChangesAsync(token);
        await audit.WriteAsync(session.Actor, new AuditCommand { Action = "data.query.execute", Resource = current.Id,
            Outcome = result.Status == "UNAUTHORIZED" ? "denied" : "allowed", Scope = state.Scope }, database.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
        // 审计完成后仍不能越过调用方固定deadline提交成功。
        if (current.DeadlineAtUtc <= clock.GetUtcNow()) throw new SemanticOperationException(503, "query_timeout");
        await transaction.CommitAsync(token);
    }

    /// <summary>运行中的原实例只能续租自己的fence，续租不能突破总deadline。</summary>
    public async Task<bool> HeartbeatAsync(G4QueryRecord lease, CancellationToken token)
    {
        // 续租不需要源业务值，也不变更任何结果或授权事实。
        await using var database = await factory.CreateDbContextAsync(token);
        // UTC时钟只计算一次，CAS条件和新租约使用同一时刻。
        var now = clock.GetUtcNow();
        // 更新上限仍为原deadline，已过期租约不能由旧worker复活。
        var until = lease.DeadlineAtUtc < now.AddSeconds(10) ? lease.DeadlineAtUtc : now.AddSeconds(10);
        return await database.Queries.Where(row => row.Id == lease.Id && row.LeaseOwner == lease.LeaseOwner && row.Fence == lease.Fence
            && row.ExecutionStatus == "RUNNING" && !row.CancelRequested && row.LeaseUntilUtc > now && row.DeadlineAtUtc > now)
            .ExecuteUpdateAsync(update => update.SetProperty(row => row.LeaseUntilUtc, until), token) == 1;
    }

    /// <summary>先核本人查询，未知和其他主体使用同一404，不返回任何存在性细节。</summary>
    public async Task<G4QueryRecord> FindOwnedAsync(ActorContext actor, string queryId, CancellationToken token)
    {
        // 读取只取自己的行，后续披露前仍须当前会话及完整投影权限。
        await using var database = await factory.CreateDbContextAsync(token);
        return await database.Queries.AsNoTracking().SingleOrDefaultAsync(row => row.Id == queryId
            && row.OrganizationId == actor.OrganizationId && row.SubjectId == actor.SubjectId, token)
            ?? throw new SemanticOperationException(404, "query_not_found");
    }

    /// <summary>取消与成功争同一查询行；当前权限验证失败或审计失败均不提交取消。</summary>
    public async Task<G4QueryRecord> CancelAsync(string queryId, MappingAuthorizationProof session, MappingAuthorizationProof[] proofs, CancellationToken token)
    {
        // 查询上下文不访问其他模块表，授权和审计显式加入同物理事务。
        await using var database = await factory.CreateDbContextAsync(token);
        // 先锁治理会话，再锁任务容量和准确查询行，保持所有写者一致顺序。
        await using var transaction = await database.Database.BeginTransactionAsync(token);
        await DemandAsync(database, session, proofs, token);
        await LockCapacityAsync(database, token);
        // 所有者条件进入数据库读取，异主体与未知查询统一404。
        var owned = await database.Queries.AsNoTracking().AnyAsync(row => row.Id == queryId
            && row.OrganizationId == session.Actor.OrganizationId && row.SubjectId == session.Actor.SubjectId, token);
        if (!owned) throw new SemanticOperationException(404, "query_not_found");
        // 同行锁提供取消和成功之间的明确线性化点。
        var record = await LockedAsync(database, queryId, token);
        // 历史保存投影重新捕获当前grant，Active变化不影响取消历史未终结执行。
        var state = ReadState(record);
        DemandProofSet(state with { Binding = state.Binding with { AuthorizationEpoch = session.AuthorizationEpoch.ToString(CultureInfo.InvariantCulture) } }, session, proofs);
        if (record.ExpiresAtUtc <= clock.GetUtcNow()) throw new SemanticOperationException(410, "result_expired");
        if (record.ExecutionStatus is "COMPLETED" or "FAILED") throw new SemanticOperationException(409, "query_already_finished");
        if (record.ExecutionStatus != "CANCELLED")
        {
            record.CancelRequested = true;
            record.ExecutionStatus = "CANCELLED";
            record.CompletedAtUtc = clock.GetUtcNow();
            record.LeaseOwner = null;
            record.LeaseUntilUtc = null;
            record.Fence++;
            await database.SaveChangesAsync(token);
            await audit.WriteAsync(session.Actor, new AuditCommand { Action = "data.query.cancel", Resource = record.Id, Outcome = "allowed", Scope = state.Scope },
                database.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
        }
        await transaction.CommitAsync(token);
        return record;
    }

    /// <summary>拒绝畸形安全元数据，不向上层传出框架异常或部分反序列化对象。</summary>
    public static G4QueryState ReadState(G4QueryRecord record)
    {
        try
        {
            return JsonSerializer.Deserialize<G4QueryState>(record.BindingBytes, G4QueryJson.Options)
                ?? throw new SemanticOperationException(503, "query_result_invalid");
        }
        catch (JsonException)
        {
            throw new SemanticOperationException(503, "query_result_invalid");
        }
    }

    /// <summary>同物理事务逐个重验完整授权，session-only永远不能代替字段授权。</summary>
    private async Task DemandAsync(G4QueryDbContext database, MappingAuthorizationProof session, MappingAuthorizationProof[] proofs, CancellationToken token)
    {
        // 调用方已开启事务，模块参与者不拥有该连接。
        var transaction = database.Database.CurrentTransaction!.GetDbTransaction();
        await authority.DemandSessionInTransactionAsync(session, database.Database.GetDbConnection(), transaction, token);
        foreach (var proof in proofs)
            await authority.DemandInTransactionAsync(proof, database.Database.GetDbConnection(), transaction, token);
    }

    /// <summary>存储提交也核验真实投影集合，不能把session-only当作任意非空业务结果的授权。</summary>
    private static void DemandProofSet(G4QueryState state, MappingAuthorizationProof session, MappingAuthorizationProof[] proofs)
    {
        if (session.Actor.OrganizationId != state.Scope.OrganizationId || session.Scope.OrganizationId != state.Scope.OrganizationId
            || !session.Scope.SiteIds.Order(StringComparer.Ordinal).SequenceEqual(state.Scope.SiteIds.Order(StringComparer.Ordinal))
            || state.Binding.AuthorizationEpoch != session.AuthorizationEpoch.ToString(CultureInfo.InvariantCulture)
            || proofs.Length != state.Projections.Length)
            throw new SemanticOperationException(403, "query_forbidden");
        foreach (var proof in proofs)
        {
            if (proof.Permission != "data.query.execute" || proof.Actor != session.Actor || proof.SessionReference != session.SessionReference
                || proof.AuthorizationEpoch != session.AuthorizationEpoch || proof.ConnectionId != state.Binding.ConnectionId
                || proof.Scope.OrganizationId != state.Scope.OrganizationId
                || !proof.Scope.SiteIds.Order(StringComparer.Ordinal).SequenceEqual(state.Scope.SiteIds.Order(StringComparer.Ordinal))
                || !state.Projections.Any(item => item.ObjectRefs.Order(StringComparer.Ordinal).SequenceEqual(proof.ObjectRefs.Order(StringComparer.Ordinal))
                    && item.FieldRefs.Order(StringComparer.Ordinal).SequenceEqual(proof.FieldRefs.Order(StringComparer.Ordinal))))
                throw new SemanticOperationException(403, "query_forbidden");
        }
        foreach (var projection in state.Projections)
            if (!proofs.Any(proof => projection.ObjectRefs.Order(StringComparer.Ordinal).SequenceEqual(proof.ObjectRefs.Order(StringComparer.Ordinal))
                && projection.FieldRefs.Order(StringComparer.Ordinal).SequenceEqual(proof.FieldRefs.Order(StringComparer.Ordinal))))
                throw new SemanticOperationException(403, "query_forbidden");
    }

    /// <summary>全任务短事务容量锁，跨API进程共享，禁止使用内存信号量代替。</summary>
    private static Task LockCapacityAsync(G4QueryDbContext database, CancellationToken token) =>
        database.Database.ExecuteSqlRawAsync("SELECT pg_advisory_xact_lock(73442001)", token);

    /// <summary>以参数化准确ID取得行锁，不能按客户端SQL片段定位。</summary>
    private static async Task<G4QueryRecord> LockedAsync(G4QueryDbContext database, string id, CancellationToken token) =>
        await database.Queries.FromSqlInterpolated($"SELECT * FROM semantic_query.\"Queries\" WHERE \"Id\" = {id} FOR UPDATE")
            .SingleOrDefaultAsync(token) ?? throw new SemanticOperationException(404, "query_not_found");

    /// <summary>两类容量分别约束为64MiB，不清理未到期结果来让新请求抢占。</summary>
    private static async Task DemandStorageAsync(G4QueryDbContext database, int metadata, int result, CancellationToken token)
    {
        // 使用long避免数据库大量记录使聚合溢出，bytea长度由PG计算。
        var metadataSize = await database.Queries.SumAsync(row => (long)row.RequestBytes.Length + row.BindingBytes.Length, token);
        // 结果按批准的规范明文总量计费，密文开销由包外资源预算另计。
        var resultSize = await database.Queries.SumAsync(row => (long)row.ResultSize, token);
        if (metadataSize + metadata > 64L * 1024 * 1024 || resultSize + result > 64L * 1024 * 1024)
            throw new SemanticOperationException(429, "query_storage_exhausted");
    }

    /// <summary>以独立用途和查询身份绑定密文，不改变规范明文或精确数值词法。</summary>
    public static G4QueryProtectedResult Protect(IDataProtectionProvider provider, string queryId, G4QueryResultV1 result)
    {
        DemandIdentity(queryId);
        // 先验证封闭合同再产生唯一规范明文，避免保存不可恢复的对象。
        var bytes = G4QueryCanonical.Result(result);
        return new G4QueryProtectedResult
        {
            Ciphertext = Protector(provider, queryId).Protect(bytes),
            Hash = G4QueryCanonical.Hash(bytes),
            Size = bytes.Length
        };
    }

    /// <summary>完整性、查询用途、明文散列和规范合同全部通过后才返回准确原件。</summary>
    public static byte[] Unprotect(IDataProtectionProvider provider, string queryId, byte[] ciphertext, string expectedHash)
    {
        DemandIdentity(queryId);
        // DataProtection开销远小于4096字节，拒绝不受控的大密文分配。
        if (ciphertext.Length is 0 || ciphertext.Length > G4QueryRules.MaximumResultBytes + 4096 ||
            expectedHash.Length != 64 || expectedHash.Any(character => !char.IsAsciiHexDigitLower(character)))
            throw new SemanticOperationException(503, "query_result_invalid");
        try
        {
            // 每次恢复都使用查询专属用途，阻止把其他行密文调换到当前身份。
            var bytes = Protector(provider, queryId).Unprotect(ciphertext);
            if (bytes.Length > G4QueryRules.MaximumResultBytes ||
                !CryptographicOperations.FixedTimeEquals(SHA256.HashData(bytes), Convert.FromHexString(expectedHash)))
                throw new SemanticOperationException(503, "query_result_invalid");
            // 认证密文也须满足当前冻结合同，且不得通过重编码掩盖原件变化。
            var result = G4QueryRules.ReadResult(bytes);
            if (!bytes.AsSpan().SequenceEqual(G4QueryCanonical.Result(result)))
                throw new SemanticOperationException(503, "query_result_invalid");
            return bytes;
        }
        catch (CryptographicException)
        {
            throw new SemanticOperationException(503, "query_result_invalid");
        }
        catch (SemanticOperationException)
        {
            throw new SemanticOperationException(503, "query_result_invalid");
        }
    }

    /// <summary>隔离模块、格式版本及查询身份，不借用认证票据的保护用途。</summary>
    private static IDataProtector Protector(IDataProtectionProvider provider, string queryId) =>
        provider.CreateProtector("OntologyPlatform.SemanticQuery", "g4.query-result.v1", queryId);

    /// <summary>查询身份必须是有界非空服务器值，不能使任意输入扩张用途串。</summary>
    private static void DemandIdentity(string queryId)
    {
        if (string.IsNullOrWhiteSpace(queryId) || queryId.Length > 128)
            throw new SemanticOperationException(503, "query_result_invalid");
    }
}
