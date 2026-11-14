using System.Data.Common;

namespace OntologyPlatform.Contracts;

/// <summary>应用层传输结果；端点只输出View或原规范结果，不将此内部包装导出为业务DTO。</summary>
public sealed record G4QueryDelivery
{
    /// <summary>用于可信Location与X-Query-Id。</summary>
    public required G4QueryView View { get; init; }

    /// <summary>已完成结果的原规范UTF8字节；运行状态响应时为空。</summary>
    public required byte[]? ResultBytes { get; init; }
}

/// <summary>历史恢复期间实际核验源ACL所使用的当前连接身份，不替换历史Binding。</summary>
public sealed record G4QueryConnectionAccess
{
    /// <summary>当前连接永久标识。</summary>
    public required string ConnectionId { get; init; }

    /// <summary>核验时实际连接修订。</summary>
    public required long Revision { get; init; }

    /// <summary>当前配置身份摘要，不含秘密。</summary>
    public required string ConfigHash { get; init; }

    /// <summary>本次实际使用的当前秘密版本。</summary>
    public required long SecretVersion { get; init; }

    /// <summary>实际核验的完整范围。</summary>
    public required ResourceScope Scope { get; init; }

    /// <summary>实际逐列检查的投影，不能以同连接另一个表的ACL检查替代。</summary>
    public required G4QueryProjection Projection { get; init; }

    /// <summary>真实当前源权限检查完成时刻。</summary>
    public required DateTimeOffset CheckedAtUtc { get; init; }
}

/// <summary>查询专用当前授权边界，不将映射管理许可解释成数据读取许可。</summary>
public interface IG4QueryAuthorizationAuthority
{
    /// <summary>只捕获真实当前会话与组织epoch，用于已可见snapshot的无数据结果，不授予源字段权限。</summary>
    Task<MappingAuthorizationProof> CaptureSessionAsync(ActorContext actor, string sessionReference, ResourceScope scope, CancellationToken cancellationToken);

    /// <summary>同事务验证当前会话；业务值仍必须另外核验每个完整源投影grant。</summary>
    Task DemandSessionInTransactionAsync(MappingAuthorizationProof proof, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken);

    /// <summary>以真实服务器会话捕获单条覆盖全部投影的当前查询授权。</summary>
    /// <param name="request">服务端身份、范围和查询许可，不能由客户端构造身份。</param>
    /// <param name="cancellationToken">当前操作的有界取消。</param>
    /// <returns>固定组织授权版本及不可延长的期限。</returns>
    Task<MappingAuthorizationProof> CaptureAsync(MappingAuthorizationProof request, CancellationToken cancellationToken);

    /// <summary>加入结果与审计所在的同物理事务，拒绝后回滚整笔事务。</summary>
    /// <param name="proof">此前固定的查询授权证明。</param>
    /// <param name="connection">调用方拥有的已打开平台连接。</param>
    /// <param name="transaction">同一连接上的显式事务。</param>
    /// <param name="cancellationToken">当前提交期限。</param>
    /// <returns>当前授权验证的异步完成。</returns>
    Task DemandInTransactionAsync(MappingAuthorizationProof proof, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken);
}

/// <summary>Connections模块提供的已验证不可变材料，不携带连接秘密。</summary>
public sealed record G4QueryBindingContext
{
    /// <summary>查询固定版本链。</summary>
    public required G4QueryBinding Binding { get; init; }

    /// <summary>原发布已验hash的映射定义。</summary>
    public required MappingReleaseManifest Manifest { get; init; }

    /// <summary>当前请求获准的范围交集。</summary>
    public required ResourceScope Scope { get; init; }

    /// <summary>原发布目录，保持历史身份。</summary>
    public required CatalogSnapshotView OriginalCatalog { get; init; }

    /// <summary>本次激活绑定目录，不覆盖原发布目录。</summary>
    public required CatalogSnapshotView CurrentCatalog { get; init; }
}

/// <summary>固定映射读取与同事务版本复核由Connections所有者执行。</summary>
public interface IG4QueryBindingReader
{
    /// <summary>历史恢复在回传事务中固定当前连接，防止源权限检查后禁用或轮换先提交。</summary>
    Task VerifyHistoricalAccessInTransactionAsync(ActorContext actor, G4QueryConnectionAccess access,
        DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken)
        => Task.FromException(new SemanticOperationException(503, "query_history_unavailable"));

    /// <summary>恢复已提交历史材料，不要求当前Active回到原发布；仍核当前主体完整保存范围。</summary>
    Task<G4QueryBindingContext> ReadHistoricalAsync(ActorContext actor, G4QueryBinding binding, ResourceScope scope, CancellationToken cancellationToken)
        => Task.FromException<G4QueryBindingContext>(new SemanticOperationException(503, "query_history_unavailable"));

    /// <summary>只读取平台不可变材料，不调用M3全映射源可用性检查。</summary>
    Task<G4QueryBindingContext> CaptureAsync(ActorContext actor, G4SemanticQuery query, long authorizationEpoch, CancellationToken cancellationToken);

    /// <summary>在授权组织锁之后加入同物理事务重验当前激活、连接和目录。</summary>
    Task VerifyInTransactionAsync(ActorContext actor, G4SemanticQuery query, G4QueryBinding expected,
        DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken);
}

/// <summary>仅在服务器内存使用的有界字段投影，不直接作为业务响应或日志。</summary>
public sealed record G4SourceQueryRead
{
    /// <summary>已固定来源实体绑定身份。</summary>
    public required string EntityBindingId { get; init; }

    /// <summary>只包含批准字段的精确标量，不是原始SELECT星号行。</summary>
    public required Dictionary<string, G4QueryValue>[] Rows { get; init; }

    /// <summary>实际源读取开始。</summary>
    public required DateTimeOffset StartedAtUtc { get; init; }

    /// <summary>真实只读事务完成。</summary>
    public required DateTimeOffset CompletedAtUtc { get; init; }

    /// <summary>实际事务快照水位，不声称与其他分支原子一致。</summary>
    public required string TransactionSnapshot { get; init; }

    /// <summary>存在无法确定窗口匹配的源时间，不可把空投影解释为EMPTY。</summary>
    public required bool Indeterminate { get; init; }

    /// <summary>只在真实超过返回预算时为真。</summary>
    public required bool Limited { get; init; }

    /// <summary>被完整投影且真实登记的源唯一键列；没有则不得声称记录定位。</summary>
    public required string[] RecordKeyFields { get; init; }

    /// <summary>固定类型计划摘要，不包含SQL或秘密。</summary>
    public required string QueryPlanHash { get; init; }
}

/// <summary>查询实际读取的完整权限投影，不把多个grant拼接成一次授权。</summary>
public sealed record G4QueryProjection
{
    /// <summary>固定源数据集权限身份。</summary>
    public required string[] ObjectRefs { get; init; }

    /// <summary>包含scope、身份、时间、属性和单位的全部读取字段。</summary>
    public required string[] FieldRefs { get; init; }
}

/// <summary>跨模块源查询只暴露类型化投影；秘密和连接生命周期由Connections拥有。</summary>
public interface IG4SourceQueryReader
{
    /// <summary>历史恢复只核当前源账号对原投影的权限和类型，不读取业务行或生成新的读取回执。</summary>
    Task<G4QueryConnectionAccess> VerifyAccessAsync(G4QueryBindingContext context, MappingAuthorizationProof proof, string entityBindingId,
        DateTimeOffset deadlineAtUtc, CancellationToken cancellationToken);

    /// <summary>由固定映射计算真实字段依赖，为每个分支取得单条完整grant。</summary>
    G4QueryProjection DescribeProjection(G4QueryBindingContext context, string entityBindingId);

    /// <summary>重验当前查询授权后读取独立只读源事务，不接受SQL或客户端身份。</summary>
    Task<G4SourceQueryRead> ReadAsync(G4QueryBindingContext context, MappingAuthorizationProof proof,
        string entityBindingId, G4SemanticQuery query, DateTimeOffset deadlineAtUtc, CancellationToken cancellationToken);
}
