using System.Data;
using System.Data.Common;
using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Governance;

/// <summary>组织级映射授权参与者，授权集合不能跨记录拼接。</summary>
public sealed class MappingAuthorizationParticipant : IMappingAuthorizationAuthority
{
    /// <summary>治理专属上下文工厂，不跨模块写表。</summary>
    private readonly IDbContextFactory<GovernanceDbContext> factory;

    /// <summary>宿主提供的加密票据解释边界。</summary>
    private readonly IMappingSessionAuthority sessions;

    /// <summary>全流程共用UTC时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>组合治理数据库、宿主票据与当前时间，不缓存授权结果。</summary>
    public MappingAuthorizationParticipant(IDbContextFactory<GovernanceDbContext> factory, IMappingSessionAuthority sessions, TimeProvider clock)
    {
        this.factory = factory;
        this.sessions = sessions;
        this.clock = clock;
    }

    /// <summary>验证单条显式授权覆盖完整范围和全部源字段。</summary>
    public static bool Covers(MappingAuthorizationGrant grant, MappingAuthorizationProof proof, DateTimeOffset now)
    {
        return grant.SubjectId == proof.Actor.SubjectId && grant.OrganizationId == proof.Scope.OrganizationId
            && proof.Actor.OrganizationId == proof.Scope.OrganizationId && grant.Permission == proof.Permission
            && grant.RevokedAtUtc is null && grant.ExpiresAtUtc > now && proof.Scope.SiteIds.Length > 0
            && proof.Scope.SiteIds.All(site => grant.SiteIds.Contains(site, StringComparer.Ordinal) && proof.Actor.SiteIds.Contains(site, StringComparer.Ordinal))
            && (proof.Permission == "mapping.source.validate"
                ? proof.ConnectionId is not null && grant.ConnectionId == proof.ConnectionId && proof.ObjectRefs.Length > 0 && proof.FieldRefs.Length > 0
                    && proof.ObjectRefs.All(value => grant.ObjectRefs.Contains(value, StringComparer.Ordinal))
                    && proof.FieldRefs.All(value => grant.FieldRefs.Contains(value, StringComparer.Ordinal))
                : grant.ConnectionId is null && grant.ObjectRefs.Length == 0 && grant.FieldRefs.Length == 0
                    && proof.ConnectionId is null && proof.ObjectRefs.Length == 0 && proof.FieldRefs.Length == 0);
    }

    /// <summary>同时检查可信角色资格，不以角色替代授权记录。</summary>
    public static bool RoleAllows(ActorContext actor, string permission) => permission switch
    {
        "mapping.read" => actor.Roles.Any(role => role is "platform.operator" or "platform.auditor"),
        "mapping.review" or "mapping.approve" => actor.Roles.Contains("platform.auditor", StringComparer.Ordinal),
        "mapping.edit" or "mapping.validate" or "mapping.submit" or "mapping.activate" => actor.Roles.Contains("platform.operator", StringComparer.Ordinal),
        "mapping.source.validate" => actor.Roles.Any(role => role is "platform.operator" or "platform.auditor"),
        _ => false
    };

    /// <summary>捕获当前组织版本及真实票据、单条完整授权的共同期限。</summary>
    public async Task<MappingAuthorizationProof> CaptureAsync(MappingAuthorizationProof request, CancellationToken cancellationToken)
    {
        // 捕获同样取得组织锁，避免读取到跨授权变更的组合状态。
        await using var database = await factory.CreateDbContextAsync(cancellationToken);
        // 事务只涉及平台授权查询，不执行源网络IO。
        await using var transaction = await database.Database.BeginTransactionAsync(cancellationToken);
        // 捕获模式只允许服务器读取当前epoch，返回时固定非零值。
        var proof = await VerifyAsync(database, request, capture: true, cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return proof;
    }

    /// <summary>在调用方同物理事务中重验授权；失败使整笔事务失效。</summary>
    public async Task DemandInTransactionAsync(MappingAuthorizationProof proof, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken)
    {
        try
        {
            if (connection.State != ConnectionState.Open || !ReferenceEquals(connection, transaction.Connection))
            {
                throw new InvalidOperationException("映射授权必须参加同一物理事务。");
            }
            // 只有治理上下文访问治理表，不取得调用方连接所有权。
            await using var database = await factory.CreateDbContextAsync(cancellationToken);
            database.Database.SetDbConnection(connection, contextOwnsConnection: false);
            await database.Database.UseTransactionAsync(transaction, cancellationToken);
            await VerifyAsync(database, proof, capture: false, cancellationToken);
        }
        catch
        {
            // 不能让调用者捕获授权失败后继续提交业务写入。
            await transaction.RollbackAsync(CancellationToken.None);
            throw;
        }
    }

    /// <summary>组织锁主键只有organizationId，覆盖相交或不相交厂区集合。</summary>
    public static async Task<MappingAuthorizationEpoch> LockOrganizationAsync(GovernanceDbContext database, string organizationId, CancellationToken cancellationToken)
    {
        G4MappingRules.Identifier(organizationId);
        if (database.Database.CurrentTransaction is null)
        {
            throw new InvalidOperationException("组织授权锁必须位于显式事务内。");
        }
        await database.Database.ExecuteSqlRawAsync("SET LOCAL lock_timeout = '2s'; SET LOCAL statement_timeout = '5s'; SET LOCAL idle_in_transaction_session_timeout = '5s'", cancellationToken);
        await database.Database.ExecuteSqlInterpolatedAsync($"INSERT INTO governance.\"MappingAuthorizationEpochs\" (\"OrganizationId\", \"Revision\") VALUES ({organizationId}, 1) ON CONFLICT (\"OrganizationId\") DO NOTHING", cancellationToken);
        // 缺行通过唯一主键创建；并发首次请求也不能形成多个锁域。
        var epochs = await database.MappingAuthorizationEpochs.FromSqlInterpolated($"SELECT * FROM governance.\"MappingAuthorizationEpochs\" WHERE \"OrganizationId\" = {organizationId} FOR UPDATE")
            .AsNoTracking().ToArrayAsync(cancellationToken);
        return epochs.Single();
    }

    /// <summary>锁顺序为组织、服务器会话、授权行；所有值均参数化。</summary>
    private async Task<MappingAuthorizationProof> VerifyAsync(GovernanceDbContext database, MappingAuthorizationProof proof, bool capture, CancellationToken cancellationToken)
    {
        G4MappingRules.Scope(proof.Scope);
        if (!RoleAllows(proof.Actor, proof.Permission) || proof.Actor.OrganizationId != proof.Scope.OrganizationId
            || proof.SessionReference.Length != 64 || !proof.SessionReference.All(character => char.IsAsciiHexDigitLower(character)))
        {
            throw new SemanticOperationException(403, "mapping_forbidden");
        }
        // 组织版本先锁定，防止跨厂区grant撤销与激活交错。
        var epoch = await LockOrganizationAsync(database, proof.Scope.OrganizationId, cancellationToken);
        // 同事务重读会话，不能依赖HTTP进入时缓存的Actor。
        var records = await database.Sessions.FromSqlInterpolated($"SELECT * FROM governance.server_sessions WHERE \"Id\" = {proof.SessionReference} FOR UPDATE")
            .AsNoTracking().ToArrayAsync(cancellationToken);
        // 最多一条服务器会话，空或失效均拒绝。
        var session = records.SingleOrDefault();
        // 获取组织锁之后再读取当前时间，不能用排队之前的时间放行过期。
        var now = clock.GetUtcNow();
        if (session is null || session.RevokedAtUtc is not null || session.ExpiresAtUtc <= now
            || !sessions.Matches(session.ProtectedTicket, proof.Actor, now))
        {
            throw new SemanticOperationException(403, "mapping_session_stale");
        }
        if (!capture && (proof.AuthorizationEpoch != epoch.Revision || proof.ExpiresAtUtc <= now))
        {
            throw new SemanticOperationException(409, "mapping_authorization_stale");
        }
        // 一次读取同主体同权限候选，不拼接多个grant的厂区或字段。
        var grants = await database.MappingAuthorizationGrants.FromSqlInterpolated($"SELECT * FROM governance.\"MappingAuthorizationGrants\" WHERE \"OrganizationId\" = {proof.Scope.OrganizationId} AND \"SubjectId\" = {proof.Actor.SubjectId} AND \"Permission\" = {proof.Permission} ORDER BY \"Id\" FOR UPDATE")
            .AsNoTracking().ToArrayAsync(cancellationToken);
        // 选择一条完整覆盖授权；若有多条，期限取其中最长但不跨条合并。
        var grant = grants.Where(value => Covers(value, proof, now)).OrderByDescending(value => value.ExpiresAtUtc).FirstOrDefault();
        if (grant is null)
        {
            throw new SemanticOperationException(403, "mapping_forbidden");
        }
        // 证明不能超过服务器会话、单条授权及当前半小时租约。
        var expiry = new[] { session.ExpiresAtUtc, grant.ExpiresAtUtc, now.AddMinutes(30) }.Min();
        return proof with { AuthorizationEpoch = epoch.Revision, ExpiresAtUtc = capture ? expiry : proof.ExpiresAtUtc };
    }
}
