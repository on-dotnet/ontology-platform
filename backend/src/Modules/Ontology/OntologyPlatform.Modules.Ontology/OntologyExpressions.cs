using System.Text.Json;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>复用权威固定版本恢复和完整组织厂区授权的高阶结构只读用例。</summary>
public sealed partial class OntologyService : IG3ExpressionService
{
    /// <summary>重新授权指定版本，核验原文hash后返回只读结构，不写业务记录。</summary>
    /// <param name="actor">服务器可信主体。</param>
    /// <param name="reference">精确草稿修订或正式发布，不能携带外部地址。</param>
    /// <param name="cancellationToken">贯穿源恢复和真实RIOT解析的取消信号。</param>
    /// <returns>精确版本、完整范围、原文和策略绑定的只读快照。</returns>
    public async Task<OwlExpressionSnapshot> ReadExpressionsAsync(ActorContext actor, VersionRef reference, CancellationToken cancellationToken)
    {
        DemandRole(actor, false);
        if (reference is null || !Enum.IsDefined(reference.Kind) || reference.Id is null || reference.Id.Length > 64)
            throw new SemanticOperationException(422, "expression_reference_invalid");
        try { JsonSerializer.Serialize(reference); }
        catch (JsonException) { throw new SemanticOperationException(422, "expression_reference_invalid"); }
        // 固定历史修订或正式对象必须先恢复并重新核实完整scope，再访问语义运行时。
        var version = await ReadVersionAsync(actor, reference, cancellationToken);
        cancellationToken.ThrowIfCancellationRequested();
        if (runtime is not IG3ExpressionRuntime expressions) throw new SemanticOperationException(503, "expression_runtime_unavailable");
        // 当前发布策略不升级；独立只读投影版本不会改变历史profile/hash。
        var profile = SemanticProfile.Current();
        // 运行时仅展示原始RDF，不执行imports加载或OWL推理。
        var sources = await expressions.ProjectExpressionsAsync(version.Sources, cancellationToken);
        return new OwlExpressionSnapshot
        {
            ProjectionVersion = "1",
            Version = reference,
            Scope = version.Scope,
            Hashes = JenaRdfCodec.Hashes(version.Sources),
            ProfileId = profile.ProfileId,
            ProfileVersion = profile.Version,
            ProfileHash = profile.Hash,
            Sources = sources
        };
    }
}
