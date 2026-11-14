using System.Security.Cryptography;
using System.Globalization;
using System.Text.Json;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>查询结果的规范字节加密边界；授权与到期检查由调用方在解密前执行。</summary>
public sealed class G4QueryResultStore : IG4QueryRunStore
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

    /// <summary>PG原子计数限制同运行的并发工具，失败尝试同样占用预算。</summary>
    public async Task ReserveRunAsync(ActorContext actor, string sessionReference, string runId, DateTimeOffset deadline, CancellationToken token)
    {
        DemandIdentity(runId);
        // 运行引用只接受当前服务器创建的三十秒期限，不能由模型延长。
        var now = clock.GetUtcNow();
        if (deadline <= now || deadline > now.AddSeconds(30) || sessionReference.Length != 64)
            throw new SemanticOperationException(429, "query_run_budget");
        // 新运行与查询结果共用模块容量锁，不能绕过64MiB元数据额度。
        await using var database = await factory.CreateDbContextAsync(token);
        await using var transaction = await database.Database.BeginTransactionAsync(token);
        await LockCapacityAsync(database, token);
        await DemandStorageAsync(database, 2048, 0, token);
        // 同ID只允许同主体、同会话和同期限增加次数，PG条件在行锁内执行。
        var affected = await database.Database.ExecuteSqlInterpolatedAsync($"""
            INSERT INTO semantic_query."QueryRuns" ("Id", "OrganizationId", "SubjectId", "SessionReference", "CreatedAtUtc", "DeadlineAtUtc", "ToolCalls")
            VALUES ({runId}, {actor.OrganizationId}, {actor.SubjectId}, {sessionReference}, {now}, {deadline}, 1)
            ON CONFLICT ("Id") DO UPDATE SET "ToolCalls" = semantic_query."QueryRuns"."ToolCalls" + 1
            WHERE semantic_query."QueryRuns"."OrganizationId" = {actor.OrganizationId}
              AND semantic_query."QueryRuns"."SubjectId" = {actor.SubjectId}
              AND semantic_query."QueryRuns"."SessionReference" = {sessionReference}
              AND semantic_query."QueryRuns"."DeadlineAtUtc" = {deadline}
              AND semantic_query."QueryRuns"."DeadlineAtUtc" > {now}
              AND semantic_query."QueryRuns"."ToolCalls" < 3
            """, token);
        if (affected != 1) throw new SemanticOperationException(429, "query_run_budget");
        await transaction.CommitAsync(token);
    }

    /// <summary>真实Query完成或返回运行视图后只保存其标识，不复制结果。</summary>
    public async Task BindRunQueryAsync(ActorContext actor, string sessionReference, string runId, string queryId, CancellationToken token)
    {
        // 同主体与会话检查在参数化更新内完成，不允许引用他人的历史Query。
        await using var database = await factory.CreateDbContextAsync(token);
        var affected = await database.Database.ExecuteSqlInterpolatedAsync($"""
            UPDATE semantic_query."QueryRuns" AS r SET "QueryIds" = array_append(r."QueryIds", {queryId})
            WHERE r."Id" = {runId} AND r."OrganizationId" = {actor.OrganizationId}
              AND r."SubjectId" = {actor.SubjectId} AND r."SessionReference" = {sessionReference}
              AND r."DeadlineAtUtc" > {clock.GetUtcNow()} AND cardinality(r."QueryIds") < r."ToolCalls"
              AND EXISTS (SELECT 1 FROM semantic_query."Queries" AS q WHERE q."Id" = {queryId}
                  AND q."OrganizationId" = r."OrganizationId" AND q."SubjectId" = r."SubjectId")
            """, token);
        if (affected != 1) throw new SemanticOperationException(503, "query_run_unavailable");
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
            || current.RequestHash != lease.RequestHash || !PlanStateMatches(ReadState(current), state)
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

    /// <summary>只在当前主体组织域查幂等引用，识别旧执行后不得重新访问业务源。</summary>
    public async Task<G4QueryRecord?> FindKeyAsync(ActorContext actor, string key, CancellationToken token)
    {
        // 准入事务仍负责最终去重，此查询只是恢复路径的提前分流。
        await using var database = await factory.CreateDbContextAsync(token);
        return await database.Queries.AsNoTracking().SingleOrDefaultAsync(row => row.OrganizationId == actor.OrganizationId
            && row.SubjectId == actor.SubjectId && row.IdempotencyKey == key, token);
    }

    /// <summary>恢复已保存的原请求；调用方必须先判本人查询与24小时期限。</summary>
    public static G4SemanticQuery ReadRequest(G4QueryRecord record)
    {
        try
        {
            if (record.RequestHash != G4QueryCanonical.Hash(record.RequestBytes)) throw new SemanticOperationException(503, "query_result_invalid");
            // 原件中的选择上下文也参与请求验证，不能拆掉header含义后继续执行。
            using var document = JsonDocument.Parse(record.RequestBytes);
            return G4QueryRules.ReadQuery(System.Text.Encoding.UTF8.GetBytes(document.RootElement.GetProperty("query").GetRawText()),
                document.RootElement.GetProperty("selectionQueryId").GetString());
        }
        catch (Exception error) when (error is JsonException or InvalidOperationException or KeyNotFoundException)
        {
            throw new SemanticOperationException(503, "query_result_invalid");
        }
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

    /// <summary>当前完整execute及读取许可通过后，在同事务记录读取审计并返回原规范字节。</summary>
    public async Task<G4QueryDelivery> ReadAuthorizedAsync(string queryId, MappingAuthorizationProof session,
        MappingAuthorizationProof[] executeProofs, MappingAuthorizationProof[] readProofs, MappingAuthorizationProof[] evidenceProofs,
        G4QueryConnectionAccess[] sourceAccess, bool includeResult, bool evidenceRead, CancellationToken token)
    {
        // 当前身份只来自服务器会话，源ACL和正式根快照须由Gateway在此调用前重验。
        await using var database = await factory.CreateDbContextAsync(token);
        // 授权检查和读取审计的线性化点在同一个短平台事务中。
        await using var transaction = await database.Database.BeginTransactionAsync(token);
        await DemandAsync(database, session, executeProofs, token);
        // 所有者先过滤，其他用户不会获知查询状态、散列或到期时间。
        var record = await database.Queries.AsNoTracking().SingleOrDefaultAsync(row => row.Id == queryId
            && row.OrganizationId == session.Actor.OrganizationId && row.SubjectId == session.Actor.SubjectId, token)
            ?? throw new SemanticOperationException(404, "query_not_found");
        // 先验证安全元数据的当前投影，再允许解密任何业务值。
        var state = ReadState(record);
        // 零数据拒绝结果在恢复时也不因创建时的session-only获得默认数据许可。
        var projections = state.Projections.Length == 0 ? state.RequiredProjections : state.Projections;
        if (projections.Length == 0) throw new SemanticOperationException(403, "query_forbidden");
        // 历史授权epoch可变化，但保存的连接和完整字段集合不能变化。
        var current = state with { Projections = projections, Binding = state.Binding with { AuthorizationEpoch = session.AuthorizationEpoch.ToString(CultureInfo.InvariantCulture) } };
        DemandProofSet(current, session, executeProofs);
        DemandReadProofSet(current, session, readProofs, "data.query.result.read");
        if (evidenceRead) DemandReadProofSet(current, session, evidenceProofs, "data.query.evidence.read");
        foreach (var proof in readProofs.Concat(evidenceRead ? evidenceProofs : []))
            await authority.DemandInTransactionAsync(proof, database.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
        if (sourceAccess.Length != projections.Length || sourceAccess.Any(access => access.ConnectionId != state.Binding.ConnectionId
            || access.Scope.OrganizationId != state.Scope.OrganizationId || !access.Scope.SiteIds.Order(StringComparer.Ordinal).SequenceEqual(state.Scope.SiteIds.Order(StringComparer.Ordinal))))
            throw new SemanticOperationException(503, "query_source_access_unverified");
        foreach (var projection in projections)
            if (!sourceAccess.Any(access => access.Projection.ObjectRefs.Order(StringComparer.Ordinal).SequenceEqual(projection.ObjectRefs.Order(StringComparer.Ordinal))
                && access.Projection.FieldRefs.Order(StringComparer.Ordinal).SequenceEqual(projection.FieldRefs.Order(StringComparer.Ordinal))))
                throw new SemanticOperationException(503, "query_source_access_unverified");
        foreach (var access in sourceAccess)
            await bindings.VerifyHistoricalAccessInTransactionAsync(session.Actor, access, database.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
        if (record.ExpiresAtUtc <= clock.GetUtcNow()) throw new SemanticOperationException(410, "result_expired");
        if (includeResult && record.ExecutionStatus is "CANCELLED" or "FAILED") throw new SemanticOperationException(409, "query_already_finished");
        // 只有COMPLETED才有可恢复结果，RUNNING返回QueryView而不是第七业务态。
        byte[]? bytes = null;
        if (includeResult && record.ExecutionStatus == "COMPLETED")
        {
            bytes = Unprotect(protection, record.Id, record.ResultCiphertext, record.ResultHash ?? string.Empty);
            // 恢复时再次校验回执、保存版本及证据闭合，不能只信认证密文本身。
            var result = G4QueryRules.ReadResult(bytes);
            G4SourceEvidenceService.BindReceipts(record.Id, state, result, state.Receipts);
        }
        await audit.WriteAsync(session.Actor, new AuditCommand { Action = evidenceRead ? "data.query.evidence.read" : "data.query.read",
            Resource = record.Id, Outcome = "allowed", Scope = state.Scope }, database.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
        if (record.ExpiresAtUtc <= clock.GetUtcNow()) throw new SemanticOperationException(410, "result_expired");
        await transaction.CommitAsync(token);
        return new G4QueryDelivery { View = View(record) with { ResultHash = record.ResultHash }, ResultBytes = bytes };
    }

    /// <summary>基础执行视图隐藏结果摘要；仅当前result.read事务通过后才另外填充摘要。</summary>
    public static G4QueryView View(G4QueryRecord record) => new()
    {
        QueryId = record.Id, ExecutionStatus = record.ExecutionStatus, CreatedAtUtc = G4QueryExecution.Utc(record.CreatedAtUtc),
        CompletedAtUtc = record.CompletedAtUtc is null ? null : G4QueryExecution.Utc(record.CompletedAtUtc.Value),
        ExpiresAtUtc = G4QueryExecution.Utc(record.ExpiresAtUtc), ResultHash = null, ErrorCode = record.ErrorCode
    };

    /// <summary>读取许可与execute分别命中完整grant，不跨许可或跨grant拼接字段。</summary>
    private static void DemandReadProofSet(G4QueryState state, MappingAuthorizationProof session, MappingAuthorizationProof[] proofs, string permission)
    {
        if (proofs.Any(proof => proof.Permission != permission)) throw new SemanticOperationException(403, "query_forbidden");
        // 仅复用集合一致性检查；真实许可仍由原permission逐项参与数据库事务校验。
        DemandProofSet(state, session, proofs.Select(proof => proof with { Permission = "data.query.execute" }).ToArray());
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

    /// <summary>按准确ID终结失联执行与删除到期材料；接管只写FAILED，绝不重新执行源。</summary>
    public async Task<int> SweepAsync(CancellationToken token)
    {
        // 有界候选扫描，不持长事务，不执行任何外部源操作。
        await using var scan = await factory.CreateDbContextAsync(token);
        // 记录统一扫描时刻，具体删除前仍在锁内重新比较实际时间。
        var now = clock.GetUtcNow();
        // 七天安全元数据保留期独立于二十四小时结果保留期。
        var retention = now.AddDays(-7);
        // 只取确实仍有待处理数据的行，已清空结果不占据下一页候选。
        var ids = await scan.Queries.AsNoTracking().Where(row => row.CreatedAtUtc <= retention
            || row.ExpiresAtUtc <= now && (row.ResultCiphertext.Length > 0 || row.RequestBytes.Length > 0)
            || row.ExecutionStatus == "RUNNING" && (row.LeaseUntilUtc == null || row.LeaseUntilUtc <= now || row.DeadlineAtUtc <= now))
            .OrderBy(row => row.CreatedAtUtc).Select(row => row.Id).Take(64).ToArrayAsync(token);
        // 返回真正提交的修改数量，不把扫描到的候选当作删除成功。
        var changed = 0;
        // Run引用只有组织级所有权而没有业务投影；维护审计只记录该准确所有权范围。
        var runs = await scan.Database.SqlQuery<G4ExpiredRun>($"""
            SELECT "Id", "OrganizationId" FROM semantic_query."QueryRuns"
            WHERE "CreatedAtUtc" <= {retention} ORDER BY "CreatedAtUtc" LIMIT 64
            """).ToArrayAsync(token);
        foreach (var run in runs)
        {
            // 每个准确Run的删除与无值审计同物理事务，审计异常保留原引用。
            await using var database = await factory.CreateDbContextAsync(token);
            await using var transaction = await database.Database.BeginTransactionAsync(token);
            await LockCapacityAsync(database, token);
            // 删除前再核真实保留期及组织，不依赖此前扫描副本。
            var removed = await database.Database.ExecuteSqlInterpolatedAsync($"""
                DELETE FROM semantic_query."QueryRuns" WHERE "Id" = {run.Id}
                    AND "OrganizationId" = {run.OrganizationId} AND "CreatedAtUtc" <= {clock.GetUtcNow().AddDays(-7)}
                """, token);
            if (removed == 0) continue;
            // 只记录系统到期事实，不冒充创建者仍已认证，也不读取Query结果。
            var trace = Guid.NewGuid().ToString("N");
            var system = new ActorContext { SubjectId = "system.query.expiry", OrganizationId = run.OrganizationId,
                SiteIds = [], Roles = [], TraceId = trace, CorrelationId = trace };
            await audit.WriteAsync(system, new AuditCommand { Action = "data.query.expire", Resource = run.Id, Outcome = "allowed",
                Scope = new ResourceScope { OrganizationId = run.OrganizationId, SiteIds = [] } },
                database.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
            await transaction.CommitAsync(token);
            changed += removed;
        }
        foreach (var id in ids)
        {
            // 单行短事务避免大量到期材料阻断正常准入。
            await using var database = await factory.CreateDbContextAsync(token);
            // 只修改查询拥有的行；治理审计通过同物理事务参与者写入。
            await using var transaction = await database.Database.BeginTransactionAsync(token);
            await LockCapacityAsync(database, token);
            // 多worker可能已清除此准确ID，不将不存在视为错误或再次执行。
            var rows = await database.Queries.FromSqlInterpolated($"SELECT * FROM semantic_query.\"Queries\" WHERE \"Id\" = {id} FOR UPDATE").ToArrayAsync(token);
            if (rows.Length == 0) continue;
            // 行锁取得后以当前实际状态判断，拒绝使用旧扫描副本删除。
            var row = rows[0];
            // 原scope只用于无值维护审计，不授予读取或解密业务结果。
            var state = ReadState(row);
            // 每次维护有独立可信关联身份，不复用已失效会话票据。
            var trace = Guid.NewGuid().ToString("N");
            // 后台过期是服务器维护事实，不冒充创建主体仍已登录。
            var system = new ActorContext { SubjectId = "system.query.expiry", OrganizationId = row.OrganizationId,
                SiteIds = state.Scope.SiteIds, Roles = [], TraceId = trace, CorrelationId = trace };
            // 锁等待不能延长结果或执行寿命。
            var current = clock.GetUtcNow();
            // 固定审计操作决定是失联失败还是无值过期删除。
            string action;
            if (row.CreatedAtUtc <= current.AddDays(-7))
            {
                database.Queries.Remove(row);
                action = "data.query.expire";
            }
            else if (row.ExpiresAtUtc <= current && (row.ResultCiphertext.Length > 0 || row.RequestBytes.Length > 0))
            {
                row.ResultCiphertext = [];
                row.ResultSize = 0;
                row.RequestBytes = [];
                action = "data.query.expire";
            }
            else if (row.ExecutionStatus == "RUNNING" && (row.LeaseUntilUtc is null || row.LeaseUntilUtc <= current || row.DeadlineAtUtc <= current))
            {
                row.ExecutionStatus = "FAILED";
                row.ErrorCode = "query_timeout";
                row.CompletedAtUtc = current;
                row.LeaseOwner = null;
                row.LeaseUntilUtc = null;
                row.Fence++;
                action = "data.query.execute";
            }
            else continue;
            await database.SaveChangesAsync(token);
            await audit.WriteAsync(system, new AuditCommand { Action = action, Resource = row.Id,
                Outcome = action == "data.query.execute" ? "failure" : "allowed", Scope = state.Scope },
                database.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
            await transaction.CommitAsync(token);
            changed++;
        }
        return changed;
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

    /// <summary>只允许实际投影在准入固定计划内演进；绑定、范围和完整必需字段不可换入。</summary>
    private static bool PlanStateMatches(G4QueryState admitted, G4QueryState completed) =>
        G4QueryCanonical.Serialize(admitted with { Projections = completed.Projections }).AsSpan().SequenceEqual(G4QueryCanonical.Serialize(completed))
        && completed.Projections.All(projection => admitted.RequiredProjections.Concat(admitted.Projections).Any(required =>
            required.ObjectRefs.SequenceEqual(projection.ObjectRefs) && required.FieldRefs.SequenceEqual(projection.FieldRefs)));

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
        var runSize = await database.Database.SqlQueryRaw<long>("SELECT COALESCE(sum(pg_column_size(r)), 0)::bigint AS \"Value\" FROM semantic_query.\"QueryRuns\" AS r").SingleAsync(token);
        // 查询输入与运行引用合计受同一容量约束。
        var metadataSize = runSize + await database.Queries.SumAsync(row => (long)row.RequestBytes.Length + row.BindingBytes.Length, token);
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
    /// <summary>过期运行扫描只读取维护所需的无值身份。</summary>
    private sealed class G4ExpiredRun
    {
        /// <summary>模块拥有的准确运行标识。</summary>
        public required string Id { get; init; }

        /// <summary>删除审计使用的原组织所有权，不扩张为源数据授权。</summary>
        public required string OrganizationId { get; init; }
    }

}
