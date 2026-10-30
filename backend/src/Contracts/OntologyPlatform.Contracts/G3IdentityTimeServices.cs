namespace OntologyPlatform.Contracts;

/// <summary>身份与时间用例复用完整四源、修订、权限和正式版本核验。</summary>
public interface IG3IdentityTimeService
{
    /// <summary>授权完整范围后读取同修订身份时间事实及真实来源诊断。</summary>
    /// <param name="actor">服务器可信主体及授权范围。</param>
    /// <param name="draftId">固定草稿标识。</param>
    /// <param name="cancellationToken">传播到实际I/O与解析的取消信号。</param>
    Task<VocabularySnapshot> ReadIdentityTimeAsync(ActorContext actor, string draftId, CancellationToken cancellationToken);

    /// <summary>以强CAS及幂等命令原子保存受控身份时间精确批次。</summary>
    /// <param name="actor">已认证主体，不接受客户端伪造身份。</param>
    /// <param name="draftId">服务器草稿标识。</param>
    /// <param name="request">精确源散列、有限编辑批次及幂等CAS命令。</param>
    /// <param name="cancellationToken">覆盖实际I/O及数据库事务的取消信号。</param>
    Task<OntologyDraft> EditIdentityTimeAsync(ActorContext actor, string draftId, IdentityTimeEditsRequest request, CancellationToken cancellationToken);

    /// <summary>核验固定正式清单、RustFS对象与Jena图后读取原身份时间事实。</summary>
    /// <param name="actor">重新授权的服务器主体。</param>
    /// <param name="releaseId">固定不可变正式版本标识。</param>
    /// <param name="cancellationToken">覆盖制品、正式图及解析的取消信号。</param>
    Task<VocabularySnapshot> ReadReleaseIdentityTimeAsync(ActorContext actor, string releaseId, CancellationToken cancellationToken);
}
