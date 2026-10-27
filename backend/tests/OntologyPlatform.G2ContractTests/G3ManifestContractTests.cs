using System.Text.Json;
using System.Text.Json.Nodes;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.G2ContractTests;

/// <summary>验证升级前后的清单版本边界，防止宽松字段或伪造评估绑定进入正式读取。</summary>
[TestClass]
public sealed class G3ManifestContractTests
{
    /// <summary>独立保留的兼容二进制读取真实发布导出的V2清单；缺少栈产物不伪造成功。</summary>
    [TestMethod]
    public void CompatibilityBinaryReadsActualV2Manifest()
    {
        // 只允许当前测试树公开合成制品目录，不读取任何认证材料。
        var path = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "actual-v2-manifest.json"));
        if (!File.Exists(path)) Assert.Inconclusive("真实主栈尚未导出V2清单；该项由g3-compatibility单独强制执行。");
        // 使用正式Web命名规则及同一严格DTO验证真实制品，未知字段不能被忽略。
        var manifest = JsonSerializer.Deserialize<ReleaseManifest>(File.ReadAllText(path), new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
        Assert.AreEqual(2, manifest.SchemaVersion);
        Assert.IsNotNull(manifest.Semantics);
        Assert.AreEqual(64, manifest.Semantics.AssessmentHash.Length);
        Assert.AreEqual(manifest.ReleaseId, manifest.Snapshot.ReleaseId);
        Assert.IsTrue(manifest.ArtifactObjects.Length is 3 or 4);
    }

    /// <summary>旧版本无评估字段时保持原线协议，不能伪造默认值。</summary>
    [TestMethod]
    public void LegacyManifestDoesNotInventSemanticBinding()
    {
        // 构造完整旧合同引用成员，检查升级不会改变原来的字段集合。
        var json = JsonSerializer.Serialize(Manifest(1));
        Assert.IsFalse(json.Contains("Semantics", StringComparison.Ordinal));
        Assert.AreEqual(1, JsonSerializer.Deserialize<ReleaseManifest>(json)!.SchemaVersion);
    }

    /// <summary>新版本必须保留真实评估绑定，不能因旧读取器忽略字段而丢失。</summary>
    [TestMethod]
    public void V2RoundtripRetainsExactAssessmentBinding()
    {
        // 先从旧形状构造合法完整正文，只新增授权所需的V2判别与绑定。
        var node = JsonNode.Parse(JsonSerializer.Serialize(Manifest(1)))!;
        node["SchemaVersion"] = 2;
        node["Semantics"] = new JsonObject
        {
            ["ProfileVersion"] = "1",
            ["ProfileHash"] = new string('a', 64),
            ["AssessmentId"] = "assessment-test",
            ["AssessmentHash"] = new string('b', 64)
        };
        // 恢复后必须仍有相同hash，不只是接受schemaVersion数值。
        var restored = JsonSerializer.Deserialize<ReleaseManifest>(node.ToJsonString())!;
        StringAssert.Contains(JsonSerializer.Serialize(restored), new string('b', 64));
    }

    /// <summary>没有绑定的V2以及未知清单版本必须在边界失败关闭。</summary>
    [TestMethod]
    public void NewOrUnknownManifestCannotSkipBinding()
    {
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(Manifest(2)));
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(Manifest(99)));
    }

    /// <summary>V2不能接受空源散列、缺失字段、格式正确但组合不一致的散列。</summary>
    [TestMethod]
    public void V2RejectsEmptyMissingAndInconsistentSourceHashes()
    {
        // 独立固定样例确保失败来自散列规则，评估引用本身完整合法。
        var value = Manifest(2) with
        {
            Semantics = new PublicationSemantics
            {
                ProfileVersion = "1",
                ProfileHash = new string('a', 64),
                AssessmentId = "assessment-test",
                AssessmentHash = new string('b', 64)
            }
        };
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(value with { Hashes = value.Hashes with { OntologyHash = "" } }));
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(value with { Hashes = value.Hashes with { DataHash = "not-a-sha256" } }));
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(value with { Hashes = value.Hashes with { BundleHash = new string('f', 64) } }));
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(value with { Hashes = value.Hashes with { VocabularyHash = new string('c', 64) } }));
        // 即使其他字段有效，不能靠字段缺席伪造原始源身份。
        var json = JsonNode.Parse(JsonSerializer.Serialize(value))!;
        json["Hashes"]!.AsObject().Remove("ShapesHash");
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<ReleaseManifest>(json.ToJsonString()));
    }

    /// <summary>仅提供完整非空旧必需引用，避免用缺字段错误冒充版本测试。</summary>
    private static ReleaseManifest Manifest(int version) => new()
    {
        SchemaVersion = version,
        Scope = new ResourceScope(),
        Hashes = new SourceHashes
        {
            OntologyHash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ShapesHash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            DataHash = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            VocabularyHash = null,
            BundleHash = "7b1385c0e43e8e1dd9fc9d923f774296d7710849351fd5a667a63512920534ab"
        },
        Snapshot = new AssetVersionSnapshot()
    };
}
