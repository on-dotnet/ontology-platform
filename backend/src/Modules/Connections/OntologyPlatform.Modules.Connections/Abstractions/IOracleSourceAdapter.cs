using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>固定PDB与合成只读主体的Oracle元数据能力，不接受自由SQL。</summary>
public interface IOracleSourceAdapter
{
    /// <summary>当前服务端信任材料指纹；改变时旧探测依据失效。</summary>
    string TrustFingerprint { get; }

    /// <summary>共享十秒期限探测网络、TLS、身份、只读权限与元数据。</summary>
    /// <param name="profile">服务端核对的固定目标。</param>
    /// <param name="secret">仅调用内存中的只读密码。</param>
    /// <param name="cancellationToken">贯通驱动的真实取消令牌。</param>
    /// <returns>真实阶段快照，未执行阶段保持NOT_RUN。</returns>
    Task<ConnectionProbeStage[]> ProbeAsync(OracleConnectionProfile profile, string secret, CancellationToken cancellationToken);

    /// <summary>二十秒内重新核权限并读取有界元数据，不读取业务行。</summary>
    /// <param name="profile">精确目标与owner集合。</param>
    /// <param name="secret">当前凭据版本的内存密码。</param>
    /// <param name="cancellationToken">会话失效或任务取消信号。</param>
    /// <returns>完整可见目录；未知或截断不产生可信快照。</returns>
    Task<CatalogObject[]> DiscoverAsync(OracleConnectionProfile profile, string secret, CancellationToken cancellationToken);
}
