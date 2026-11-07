using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>固定HTTPS GET操作的typed能力，不接收PG配置或任意URL。</summary>
public interface IWebSourceAdapter
{
    /// <summary>真实核验网络、TLS、API Key、GET策略和声明数据合同。</summary>
    /// <param name="profile">由服务器批准的固定Web配置。</param>
    /// <param name="secret">当前调用内存中的API Key。</param>
    /// <param name="cancellationToken">调用取消与总预算。</param>
    /// <returns>真实五阶段报告，未执行阶段不得标PASS。</returns>
    Task<ConnectionProbeStage[]> ProbeAsync(WebApiConnectionProfile profile, string secret, CancellationToken cancellationToken);

    /// <summary>验证真实响应后返回服务器登记的数据合同元数据，不保存响应值。</summary>
    /// <param name="profile">固定服务器操作配置。</param>
    /// <param name="secret">当前版本的内存API Key。</param>
    /// <param name="cancellationToken">任务取消与总预算。</param>
    /// <returns>完整验证后的目录，超预算或合同不符必须拒绝。</returns>
    Task<CatalogObject[]> DiscoverAsync(WebApiConnectionProfile profile, string secret, CancellationToken cancellationToken);
}
