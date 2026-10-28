namespace OntologyPlatform.Contracts;

/// <summary>复用本体草稿、修订与正式发布边界的术语和单位引用用例。</summary>
public interface IG3VocabularyService
{
    /// <summary>授权后读取精确草稿修订的四源词汇投影。</summary>
    /// <param name="actor">服务器可信主体与完整厂区范围。</param>
    /// <param name="draftId">服务器草稿标识。</param>
    /// <param name="cancellationToken">传播到数据库与RIOT解析的取消信号。</param>
    Task<VocabularySnapshot> ReadVocabularyAsync(ActorContext actor, string draftId, CancellationToken cancellationToken);

    /// <summary>以同一个CAS和审计事务原子保存本体及词汇源的精确变更。</summary>
    /// <param name="actor">服务器可信主体，不接受客户端身份。</param>
    /// <param name="draftId">目标草稿标识。</param>
    /// <param name="request">同修订四源散列、有限精确批次及幂等命令。</param>
    /// <param name="cancellationToken">覆盖解析与提交的取消信号。</param>
    Task<OntologyDraft> EditVocabularyAsync(ActorContext actor, string draftId, VocabularyEditsRequest request, CancellationToken cancellationToken);

    /// <summary>核验正式清单、源对象和实际Jena图后读取固定版本词汇。</summary>
    /// <param name="actor">重新授权的可信主体。</param>
    /// <param name="releaseId">已发布的不可变版本标识。</param>
    /// <param name="cancellationToken">覆盖所有实际外部读取的取消信号。</param>
    Task<VocabularySnapshot> ReadReleaseVocabularyAsync(ActorContext actor, string releaseId, CancellationToken cancellationToken);
}

/// <summary>按真实RIOT解析生成词汇投影和保留未知源的精确批量编辑。</summary>
public interface IG3VocabularyRuntime
{
    /// <summary>读取四源三元组及具有真实来源散列的SKOS和单位治理诊断。</summary>
    /// <param name="sources">仍为唯一权威的完整四源。</param>
    /// <param name="revision">服务器固定修订。</param>
    /// <param name="cancellationToken">解析及有限图检查共享的取消信号。</param>
    Task<VocabularySnapshot> ReadVocabularyAsync(SourceBundle sources, long revision, CancellationToken cancellationToken);

    /// <summary>完整解析后仅对显式目标源执行有限批次，不清洗未知图。</summary>
    /// <param name="sources">同修订的完整原始四源。</param>
    /// <param name="changes">最多64项本体或词汇源精确变更。</param>
    /// <param name="cancellationToken">解析与重写共享的取消信号。</param>
    Task<SourceBundle> ApplyVocabularyEditsAsync(SourceBundle sources, VocabularyChange[] changes, CancellationToken cancellationToken);
}
