using System.Data.Common;

namespace OntologyPlatform.Contracts;

/// <summary>复用固定版本及源权威的M4差异与持久影响报告用例。</summary>
public interface IG3ImpactService
{
    /// <summary>授权同资产完整scope后比较两个准确固定版本的四源。</summary>
    /// <param name="actor">服务器可信主体。</param>
    /// <param name="request">只含固定版本定位，不接受源或外部地址。</param>
    /// <param name="cancellationToken">覆盖真实源读取和有界比较的取消信号。</param>
    Task<VersionDiff> DiffAsync(ActorContext actor, CompareVersionsRequest request, CancellationToken cancellationToken);

    /// <summary>真实分析后幂等持久报告，重放保持首次ID与期限。</summary>
    /// <param name="actor">具备本体编辑角色的可信主体。</param>
    /// <param name="request">准确版本、评估引用和显式幂等命令。</param>
    /// <param name="cancellationToken">覆盖比较与事务的取消信号。</param>
    Task<ImpactReport> GenerateImpactAsync(ActorContext actor, GenerateImpactReportRequest request, CancellationToken cancellationToken);

    /// <summary>完整scope重新授权后返回原不可变报告，过期仍可审计读取。</summary>
    /// <param name="actor">服务器可信读取主体。</param>
    /// <param name="reportId">服务器报告标识。</param>
    /// <param name="cancellationToken">数据库读取取消信号。</param>
    Task<ImpactReport> ReadImpactAsync(ActorContext actor, string reportId, CancellationToken cancellationToken);
}

/// <summary>在M1同一真实解析与图预算内生成四源源码及可信三元组差异。</summary>
public interface IG3VersionDiffRuntime
{
    /// <summary>保留两侧原文和独立blank作用域，不把无法对齐的blank当可靠delta。</summary>
    /// <param name="left">完整基础四源。</param>
    /// <param name="right">完整目标四源。</param>
    /// <param name="cancellationToken">解析、搜索和差异共用的取消信号。</param>
    Task<SourceVersionDiff[]> DiffSourcesAsync(SourceBundle left, SourceBundle right, CancellationToken cancellationToken);
}

/// <summary>由Ontology自己在发布事务内核验报告，Publishing不跨模块写表。</summary>
public interface IImpactPublicationReader
{
    /// <summary>核验真实报告、hash、输入、评估、目标及期限，锁内不调用Jena。</summary>
    /// <param name="actor">已认证并重新授权完整scope的主体。</param>
    /// <param name="reportId">准确持久报告ID。</param>
    /// <param name="canonicalHash">客户端或已批准提案固定的准确hash。</param>
    /// <param name="snapshot">同事务已锁读的当前目标草稿与评估。</param>
    /// <param name="connection">发布方提供的共同物理连接。</param>
    /// <param name="transaction">同一个当前PG事务。</param>
    /// <param name="cancellationToken">实际读取取消信号。</param>
    /// <returns>只能由服务器构造的精确审批内容。</returns>
    Task<ImpactApprovalBinding> LockForPublicationAsync(ActorContext actor, string reportId, string canonicalHash,
        DraftPublicationSnapshot snapshot, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken);
}
