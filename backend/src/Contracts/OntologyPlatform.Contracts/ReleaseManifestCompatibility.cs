using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace OntologyPlatform.Contracts;

/// <summary>显式区分无语义绑定的G2清单与带评估绑定的G3清单，不升级历史事实。</summary>
public static class ReleaseManifestCompatibility
{
    /// <summary>在序列化及反序列化边界执行相同版本判别，未知版本失败关闭。</summary>
    /// <param name="manifest">严格DTO解析的固定清单。</param>
    public static void Validate(ReleaseManifest manifest)
    {
        switch (manifest.SchemaVersion)
        {
            case 1 when manifest.Semantics is null:
                return;
            case 2 when manifest.Semantics is not null:
                ValidateBinding(manifest.Semantics);
                ValidateHashes(manifest.Hashes);
                return;
            default:
                throw new JsonException("清单版本与语义评估绑定不一致。");
        }
    }

    /// <summary>检查版本化评估引用的精确格式，内容真实性由Ontology持久事实核验。</summary>
    /// <param name="binding">服务器生成的评估引用。</param>
    public static void ValidateBinding(PublicationSemantics binding)
    {
        if (string.IsNullOrWhiteSpace(binding.ProfileVersion) || binding.ProfileVersion.Length > 64
            || string.IsNullOrWhiteSpace(binding.AssessmentId) || binding.AssessmentId.Length > 64
            || !IsHash(binding.ProfileHash) || !IsHash(binding.AssessmentHash))
        {
            throw new JsonException("语义评估绑定字段无效。");
        }
    }

    /// <summary>只接受精确小写SHA256编码，不能把空值或未知值当作有效散列。</summary>
    /// <param name="value">待核对的协议散列。</param>
    private static bool IsHash(string value) => value is { Length: 64 } && value.All(char.IsAsciiHexDigitLower);

    /// <summary>新版本必须携带完整源身份，词汇缺席与空源码不能混淆。</summary>
    /// <param name="hashes">正式清单的四源与组合散列。</param>
    private static void ValidateHashes(SourceHashes hashes)
    {
        if (hashes is null || !IsHash(hashes.OntologyHash) || !IsHash(hashes.ShapesHash)
            || !IsHash(hashes.DataHash) || !IsHash(hashes.BundleHash)
            || (hashes.VocabularyHash is not null && !IsHash(hashes.VocabularyHash)))
        {
            throw new JsonException("V2清单必须包含精确的源SHA256。");
        }
        // 与既有SourceHashes合同相同，四槽位顺序及absent标记不归一化原文。
        var expected = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(
            string.Join('\n', hashes.OntologyHash, hashes.ShapesHash, hashes.VocabularyHash ?? "absent", hashes.DataHash))));
        if (hashes.BundleHash != expected)
        {
            throw new JsonException("V2清单的组合散列与四源不一致。");
        }
    }
}
