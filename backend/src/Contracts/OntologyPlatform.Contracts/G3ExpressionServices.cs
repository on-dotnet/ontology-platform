namespace OntologyPlatform.Contracts;

/// <summary>在完整资源授权和权威源核验后读取高阶表达式，不改变任何修订。</summary>
public interface IG3ExpressionService
{
    /// <summary>读取指定不可变草稿修订或正式发布的有界只读表达式。</summary>
    /// <param name="actor">服务器可信主体。</param>
    /// <param name="reference">不含外部地址的精确版本。</param>
    /// <param name="cancellationToken">覆盖源恢复、解析和结构遍历的取消信号。</param>
    /// <returns>源hash和版本绑定的只读快照。</returns>
    Task<OwlExpressionSnapshot> ReadExpressionsAsync(ActorContext actor, VersionRef reference, CancellationToken cancellationToken);
}

/// <summary>复用真实RIOT及既有共享预算的独立四源只读结构运行时。</summary>
public interface IG3ExpressionRuntime
{
    /// <summary>投影实际RDF结构，未知或超预算明确诊断且不允许复杂发布。</summary>
    /// <param name="sources">已经权威核验的四源原文。</param>
    /// <param name="cancellationToken">传播到真实解析和遍历的取消信号。</param>
    /// <returns>四源独立的保真与支持分级事实。</returns>
    Task<OwlExpressionSource[]> ProjectExpressionsAsync(SourceBundle sources, CancellationToken cancellationToken);
}
