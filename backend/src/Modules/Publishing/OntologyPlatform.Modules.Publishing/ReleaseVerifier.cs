using System.Text;
using System.Text.Json;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Publishing;

/// <summary>共同执行PG清单、RustFS精确字节及Jena正式图真实一致性回验。</summary>
public sealed class ReleaseVerifier
{
    /// <summary>不可变对象存储读写边界。</summary>
    private readonly IReleaseArtifactStore artifacts;

    /// <summary>唯一SEM语义实现，禁止复制RDF引擎。</summary>
    private readonly ISemanticRuntime runtime;

    /// <summary>注入同一组真实对象及语义适配。</summary>
    public ReleaseVerifier(IReleaseArtifactStore artifacts, ISemanticRuntime runtime)
    {
        this.artifacts = artifacts;
        this.runtime = runtime;
    }

    /// <summary>核实清单自身及全部源对象，失败绝不返回部分快照。</summary>
    public async Task<ReleaseManifest> VerifyArtifactsAsync(ReleaseRecord row, CancellationToken token)
    {
        if (PublishingRules.Hash(row.ManifestJson) != row.ManifestHash) throw new SemanticOperationException(503, "manifest_hash_mismatch");
        // 清单引用独立存储，清单不能包含自己的散列。
        var reference = JsonSerializer.Deserialize<ArtifactObject>(row.ManifestObjectJson)!;
        // 比较真实S3返回字节与PG固定字节，两者缺一不可。
        var bytes = await artifacts.ReadVerifiedAsync(reference, token);
        if (reference.Hash != row.ManifestHash || !bytes.AsSpan().SequenceEqual(Encoding.UTF8.GetBytes(row.ManifestJson))) throw new SemanticOperationException(503, "manifest_hash_mismatch");
        // 唯一合同反序列化也执行非空/判别验证。
        var manifest = JsonSerializer.Deserialize<ReleaseManifest>(row.ManifestJson)!;
        // 准备时PG源是恢复依据，不从TDB2重建权威字节。
        var sources = JsonSerializer.Deserialize<SourceBundle>(row.SourcesJson)!;
        // 固定位置完整源与清单每个内容对象逐一回验。
        var expected = SourceContents(sources);
        if (manifest.ArtifactObjects.Length != expected.Length) throw new SemanticOperationException(503, "artifact_binding_mismatch");
        for (var index = 0; index < expected.Length; index++)
        {
            // 同位置真实字节必须与固定源完全一致，不仅检查对象自报hash。
            var source = await artifacts.ReadVerifiedAsync(manifest.ArtifactObjects[index], token);
            if (!source.AsSpan().SequenceEqual(Encoding.UTF8.GetBytes(expected[index]))) throw new SemanticOperationException(503, "artifact_binding_mismatch");
        }
        return manifest;
    }

    /// <summary>除对象外还执行SEM正式图回读、SHACL及查询对账。</summary>
    public async Task<ReleaseManifest> VerifyAsync(ReleaseRecord row, CancellationToken token)
    {
        // 对象先验，防止图存在但权威字节已丢失仍被当作可用。
        var manifest = await VerifyArtifactsAsync(row, token);
        if (!await runtime.VerifyAsync(manifest, JsonSerializer.Deserialize<SourceBundle>(row.SourcesJson)!, token)) throw new SemanticOperationException(503, "release_graph_mismatch");
        return manifest;
    }

    /// <summary>严格采用ontology、shapes、可选vocabulary、data固定顺序。</summary>
    internal static string[] SourceContents(SourceBundle source) => source.VocabularyTurtle is null
        ? [source.OntologyTurtle, source.ShapesTurtle, source.DataTurtle]
        : [source.OntologyTurtle, source.ShapesTurtle, source.VocabularyTurtle, source.DataTurtle];
}
