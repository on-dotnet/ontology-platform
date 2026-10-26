using System.Security.Cryptography;
using System.Text;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>只从已授权发布清单恢复精确四源，校验快照、槽位、对象字节和严格UTF8后交唯一SEM解析。</summary>
public sealed class VerifiedReleaseSources
{
    /// <summary>对象访问与SigV4实现由Publishing拥有，本模块不复制存储适配。</summary>
    private readonly IReleaseArtifactStore artifacts;

    /// <summary>无损解码要求拒绝非法UTF8，不以替换字符修改权威源码。</summary>
    private static readonly UTF8Encoding StrictUtf8 = new(false, true);

    /// <summary>仅注入已有不可变对象读取边界。</summary>
    public VerifiedReleaseSources(IReleaseArtifactStore artifacts) => this.artifacts = artifacts;

    /// <summary>调用方必须先完成Catalog授权；返回的完整字节内容与此同版清单精确绑定。</summary>
    public async Task<SourceBundle> ReadAsync(ReleaseManifest manifest, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (manifest is null || manifest.SchemaVersion != 1 || !Guid.TryParseExact(manifest.ReleaseId, "N", out _) || manifest.Snapshot is null || manifest.Hashes is null || manifest.ArtifactObjects is null) throw InvalidBinding();
        // 快照字段是结果对外宣称的版本，不能仅校验ArtifactObject自报hash。
        var snapshot = manifest.Snapshot;
        // manifest和snapshot必须指向同一组固定服务器命名图及源hash。
        var hashes = manifest.Hashes;
        if (snapshot.ReleaseId != manifest.ReleaseId || manifest.OntologyGraphIri != "urn:ontology-platform:release:" + manifest.ReleaseId + ":ontology" || manifest.DataGraphIri != "urn:ontology-platform:release:" + manifest.ReleaseId + ":data" || snapshot.OntologyGraphIri != manifest.OntologyGraphIri || snapshot.DataGraphIri != manifest.DataGraphIri || snapshot.OntologyHash != hashes.OntologyHash || snapshot.ShapesHash != hashes.ShapesHash || snapshot.VocabularyHash != hashes.VocabularyHash || snapshot.DataHash != hashes.DataHash) throw InvalidBinding();
        // 固定发布顺序为本体、Shape、可选词汇、事实；缺词汇不能改变其他槽位语义。
        string[] expected = hashes.VocabularyHash is { } vocabulary ? [hashes.OntologyHash, hashes.ShapesHash, vocabulary, hashes.DataHash] : [hashes.OntologyHash, hashes.ShapesHash, hashes.DataHash];
        if (expected.Any(value => value is null || value.Length != 64 || !value.All(char.IsAsciiHexDigitLower)) || manifest.ArtifactObjects.Length != expected.Length || hashes.BundleHash != Hash(Encoding.UTF8.GetBytes(string.Join('\n', hashes.OntologyHash, hashes.ShapesHash, hashes.VocabularyHash ?? "absent", hashes.DataHash)))) throw InvalidBinding();
        // 每项保存严格解码后的原始源码，不由图投影重新生成Turtle。
        var texts = new string[expected.Length];
        // 当前索引就是Publishing固定源对象槽位，不能交换相同类型的对象。
        for (var index = 0; index < expected.Length; index++)
        {
            cancellationToken.ThrowIfCancellationRequested();
            // 正式源引用必须同时满足位置、对象名、媒体类型和精确hash。
            var artifact = manifest.ArtifactObjects[index];
            if (artifact is null || artifact.Hash != expected[index] || artifact.ObjectKey != "releases/" + manifest.ReleaseId + "/source-" + index + "-" + expected[index] + ".ttl" || artifact.ContentType != "text/turtle" || artifact.SizeBytes is < 0 or > 256 * 1024) throw InvalidBinding();
            // 真实GET回验后仍独立与manifest对应源hash核对，不能只信任适配器自报成功。
            var bytes = await artifacts.ReadVerifiedAsync(artifact, cancellationToken);
            if (bytes.LongLength != artifact.SizeBytes || Hash(bytes) != expected[index]) throw InvalidBinding();
            try { texts[index] = StrictUtf8.GetString(bytes); }
            catch (DecoderFallbackException) { throw new SemanticOperationException(503, "published_source_encoding_invalid"); }
        }
        return new SourceBundle { OntologyTurtle = texts[0], ShapesTurtle = texts[1], VocabularyTurtle = expected.Length == 4 ? texts[2] : null, DataTurtle = texts[^1] };
    }

    /// <summary>计算真实原始字节小写SHA256，不标准化空白或文本。</summary>
    private static string Hash(ReadOnlySpan<byte> bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));

    /// <summary>固定公开故障码不带对象地址、源正文或异常。</summary>
    private static SemanticOperationException InvalidBinding() => new(503, "published_source_binding_invalid");
}
