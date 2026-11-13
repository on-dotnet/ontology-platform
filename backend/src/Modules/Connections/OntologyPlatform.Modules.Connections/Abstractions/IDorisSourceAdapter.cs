using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>固定内部目录的Doris只读元数据能力，不接受自由SQL。</summary>
public interface IDorisSourceAdapter
{
    /// <summary>共享十秒总期限执行网络、TLS、认证、权限与元数据探测。</summary>
    /// <param name="profile">服务端再次核对的精确目标。</param>
    /// <param name="secret">仅本次调用内存中的只读密码。</param>
    /// <param name="cancellationToken">调用方取消信号。</param>
    /// <returns>真实阶段结果，失败后阶段保持未运行。</returns>
    Task<ConnectionProbeStage[]> ProbeAsync(DorisConnectionProfile profile, string secret, CancellationToken cancellationToken);

    /// <summary>十秒内重新检查有效权限并读取有界元数据，取消清理另限四秒。</summary>
    /// <param name="profile">固定内部目录的准确目标。</param>
    /// <param name="secret">当前版本只读密码。</param>
    /// <param name="cancellationToken">持久取消意图和会话撤销信号。</param>
    /// <returns>完整可见目录；截断或空目录按安全失败处理。</returns>
    Task<CatalogObject[]> DiscoverAsync(DorisConnectionProfile profile, string secret, CancellationToken cancellationToken);
}
