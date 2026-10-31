using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>复用真实RIOT和原有共享预算的高阶四源只读结构入口。</summary>
public sealed partial class JenaSemanticRuntime : IG3ExpressionRuntime
{
    /// <summary>独立解析四源且不执行Shape策略，不修改源码、发布策略或正式图。</summary>
    /// <param name="sources">权威完整原文。</param>
    /// <param name="cancellationToken">覆盖实际解析、结构遍历和暂存图清理的取消信号。</param>
    /// <returns>逐源绑定原文散列的有界只读结构。</returns>
    public Task<OwlExpressionSource[]> ProjectExpressionsAsync(SourceBundle sources, CancellationToken cancellationToken) =>
        Execute(async (graphs, token) =>
        {
            // 新的只读解析允许展示复杂Shapes；正式验证继续使用既有ShapePolicy。
            var parsed = await ParseSourcesAsync(sources, graphs, token, checkShapes: false);
            // 散列来自未改写的原文，不来自投影或RIOT序列化。
            var hashes = JenaRdfCodec.Hashes(sources);
            // 源槽位顺序与原解析、导出及发布合同一致。
            string[] ids = ["ontology", "shapes", "vocabulary", "data"];
            // vocabulary缺席不能伪造为空源存在。
            string?[] sourceHashes = [hashes.OntologyHash, hashes.ShapesHash, hashes.VocabularyHash, hashes.DataHash];
            // 每源blank标识只在本源图中关联，不进行跨源拼接。
            var result = new List<OwlExpressionSource>();
            for (var index = 0; index < ids.Length; index++)
            {
                token.ThrowIfCancellationRequested();
                if (sourceHashes[index] is not { } sourceHash) continue;
                // Shapes的发布资格仍由独立ShapePolicy/assessment决定，读取不运行它。
                var blocked = index != 1 && Support(parsed[index]).Length != 0;
                result.Add(OwlExpressionProjection.Build(ids[index], sourceHash, parsed[index], blocked, token));
            }
            return result.ToArray();
        }, cancellationToken);
}
