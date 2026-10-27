namespace OntologyPlatform.Contracts;

/// <summary>复用本体权限和权威源的M1评估与固定版本比较用例。</summary>
public interface IG3OntologyService
{
    /// <summary>读取稳定内容散列的二十项支持策略。</summary>
    SemanticSupportProfile GetProfile();

    /// <summary>真实验证精确修订并原子保存评估、报告、幂等和审计。</summary>
    /// <param name="actor">服务器可信主体。</param>
    /// <param name="draftId">已授权草稿。</param>
    /// <param name="request">修订、四源散列及命令。</param>
    /// <param name="cancellationToken">传播到实际I/O的取消信号。</param>
    Task<SemanticAssessment> AssessAsync(ActorContext actor, string draftId, ValidateDraftRequest request, CancellationToken cancellationToken);

    /// <summary>再次核验草稿完整scope后读取原始持久评估。</summary>
    /// <param name="actor">服务器可信主体。</param>
    /// <param name="assessmentId">持久评估标识。</param>
    /// <param name="cancellationToken">取消信号。</param>
    Task<SemanticAssessment> ReadAssessmentAsync(ActorContext actor, string assessmentId, CancellationToken cancellationToken);

    /// <summary>比较同一资产及完整范围的两个固定修订或正式版本。</summary>
    /// <param name="actor">服务器可信主体。</param>
    /// <param name="request">不含外部地址或客户端散列的定位请求。</param>
    /// <param name="cancellationToken">覆盖读取与比较的取消信号。</param>
    Task<SourceComparison[]> CompareAsync(ActorContext actor, CompareVersionsRequest request, CancellationToken cancellationToken);
}

/// <summary>基于真实RIOT解析及共享总预算的四源图比较运行时。</summary>
public interface IG3SemanticRuntime
{
    /// <summary>独立隔离四源空白节点，并将超预算或取消明确返回为无法确定。</summary>
    /// <param name="left">左侧完整权威源。</param>
    /// <param name="right">右侧完整权威源。</param>
    /// <param name="cancellationToken">解析、细化和搜索共同使用的取消信号。</param>
    Task<SourceComparison[]> CompareSourcesAsync(SourceBundle left, SourceBundle right, CancellationToken cancellationToken);
}
