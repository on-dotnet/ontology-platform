using System.Data.Common;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Governance;

/// <summary>查询授权复用治理组织锁、会话与单条grant事务算法，独立限制查询许可。</summary>
public sealed class QueryAuthorizationParticipant : IG4QueryAuthorizationAuthority
{
    /// <summary>治理内部共享的真实会话与授权复核，不绕过数据库。</summary>
    private readonly MappingAuthorizationParticipant participant;

    /// <summary>依赖同模块的事务算法，避免复制另一套epoch和会话验证。</summary>
    public QueryAuthorizationParticipant(MappingAuthorizationParticipant participant)
    {
        this.participant = participant;
    }

    /// <summary>仅接受批准的三个独立查询许可，默认没有任何grant。</summary>
    public static bool IsQueryPermission(string permission) => permission is "data.query.execute" or "data.query.result.read" or "data.query.evidence.read";

    /// <summary>精确角色只是资格，必须再检查完整grant。</summary>
    public static bool RoleAllows(ActorContext actor, string permission) => IsQueryPermission(permission)
        && actor.Roles.Any(role => role is "platform.viewer" or "platform.operator" or "platform.auditor");

    /// <summary>同一grant必须覆盖请求连接及全部厂区、对象、字段，不拼接授权。</summary>
    public static bool Covers(MappingAuthorizationGrant grant, MappingAuthorizationProof proof, DateTimeOffset now) =>
        IsQueryPermission(proof.Permission) && RoleAllows(proof.Actor, proof.Permission)
        && MappingAuthorizationParticipant.Covers(grant, proof, now);

    /// <summary>无字段会话证明只用于已授权可见snapshot元数据，不能作为源grant。</summary>
    public async Task<MappingAuthorizationProof> CaptureSessionAsync(ActorContext actor, string sessionReference, ResourceScope scope, CancellationToken cancellationToken)
    {
        // 空投影必须由服务器构造，不从客户端接收proof或epoch。
        var request = new MappingAuthorizationProof
        {
            Actor = actor, SessionReference = sessionReference, Scope = scope, Permission = "data.query.execute",
            ConnectionId = null, ObjectRefs = [], FieldRefs = [], AuthorizationEpoch = 0, ExpiresAtUtc = default
        };
        DemandPermission(request);
        try { return await participant.CaptureSessionAsync(request, cancellationToken); }
        catch (SemanticOperationException exception) when (exception.Status is 403 or 409) { throw new SemanticOperationException(403, "query_forbidden"); }
    }

    /// <summary>源grant另验；当前会话或epoch失效时无数据结果也不得披露。</summary>
    public async Task DemandSessionInTransactionAsync(MappingAuthorizationProof proof, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken)
    {
        try { await participant.DemandSessionInTransactionAsync(proof, connection, transaction, cancellationToken); }
        catch (SemanticOperationException exception) when (exception.Status is 403 or 409) { throw new SemanticOperationException(403, "query_forbidden"); }
    }

    /// <summary>捕获当前查询权限；历史映射权限不能通过此入口。</summary>
    public async Task<MappingAuthorizationProof> CaptureAsync(MappingAuthorizationProof request, CancellationToken cancellationToken)
    {
        DemandPermission(request);
        try
        {
            return await participant.CaptureAsync(request, cancellationToken);
        }
        catch (SemanticOperationException exception) when (exception.Status is 403 or 409)
        {
            throw new SemanticOperationException(403, "query_forbidden");
        }
    }

    /// <summary>当前会话、grant撤销或epoch变化均拒绝，沿用同物理事务强制回滚。</summary>
    public async Task DemandInTransactionAsync(MappingAuthorizationProof proof, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken)
    {
        if (!RoleAllows(proof.Actor, proof.Permission))
        {
            await transaction.RollbackAsync(CancellationToken.None);
            throw new SemanticOperationException(403, "query_forbidden");
        }
        try
        {
            await participant.DemandInTransactionAsync(proof, connection, transaction, cancellationToken);
        }
        catch (SemanticOperationException exception) when (exception.Status is 403 or 409)
        {
            throw new SemanticOperationException(403, "query_forbidden");
        }
    }

    /// <summary>在调用共享算法前固定查询许可边界。</summary>
    private static void DemandPermission(MappingAuthorizationProof proof)
    {
        if (!RoleAllows(proof.Actor, proof.Permission)) throw new SemanticOperationException(403, "query_forbidden");
    }
}
