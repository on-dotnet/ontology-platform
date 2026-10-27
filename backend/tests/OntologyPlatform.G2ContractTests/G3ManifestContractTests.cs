using System.Text.Json;
using System.Text.Json.Nodes;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.G2ContractTests;

/// <summary>验证升级前后的清单版本边界，防止宽松字段或伪造评估绑定进入正式读取。</summary>
[TestClass]
public sealed class G3ManifestContractTests
{
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

    /// <summary>仅提供完整非空旧必需引用，避免用缺字段错误冒充版本测试。</summary>
    private static ReleaseManifest Manifest(int version) => new()
    {
        SchemaVersion = version,
        Scope = new ResourceScope(),
        Hashes = new SourceHashes(),
        Snapshot = new AssetVersionSnapshot()
    };
}
