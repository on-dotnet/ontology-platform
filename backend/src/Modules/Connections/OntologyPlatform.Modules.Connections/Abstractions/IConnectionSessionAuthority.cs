using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>后台任务重验可信会话，不用持久化的旧角色替代撤权事实。</summary>
public interface IConnectionSessionAuthority
{
    /// <summary>确认当前会话仍有效，且保有请求时的组织厂区及operator权限。</summary>
    /// <param name="reference">服务器内部会话引用。</param>
    /// <param name="actor">服务器捕获的主体。</param>
    /// <param name="token">取消信号。</param>
    /// <returns>只有实时授权完整时为真。</returns>
    Task<bool> IsCurrentAsync(string reference, ActorContext actor, CancellationToken token);
}
