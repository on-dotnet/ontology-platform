using System.Data.Common;

namespace OntologyPlatform.Contracts;

/// <summary>查询专用当前授权边界，不将映射管理许可解释成数据读取许可。</summary>
public interface IG4QueryAuthorizationAuthority
{
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
