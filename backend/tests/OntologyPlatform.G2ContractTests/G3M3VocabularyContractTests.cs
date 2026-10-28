using System.Text.Json;
using System.Text.Json.Nodes;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.G2ContractTests;

/// <summary>冻结M3按源批量精确编辑的严格线协议，避免词汇写入错误源或身份注入。</summary>
[TestClass]
public sealed class G3M3VocabularyContractTests
{
    /// <summary>两个源在同一命令内表达，原始语言和显式空旧值往返保留。</summary>
    [TestMethod]
    public void ValidBatchKeepsSourceIdentityLanguageAndHashes()
    {
        // 真实序列化器使用与宿主相同的camelCase及严格生成DTO。
        var request = JsonSerializer.Deserialize<VocabularyEditsRequest>(Payload, Options)!;
        Assert.AreEqual(2, request.Changes.Length);
        Assert.AreEqual(VocabularyEditSource.Vocabulary, request.Changes[0].SourceId);
        Assert.AreEqual(VocabularyEditSource.Ontology, request.Changes[1].SourceId);
        Assert.AreEqual("zh-Hans", request.Changes[0].Edit.NewObject!.Language);
        Assert.IsNull(request.Changes[0].Edit.OldObject);
        Assert.AreEqual("bundle", request.Hashes.BundleHash);
        Assert.AreEqual(2L, request.Command.ExpectedRevision);
        // 再次解析序列化结果，确保每项源标识不会被默认值吞掉。
        var roundtrip = JsonSerializer.Deserialize<VocabularyEditsRequest>(JsonSerializer.Serialize(request, Options), Options)!;
        Assert.AreEqual(request.Changes[0], roundtrip.Changes[0]);
        Assert.AreEqual(request.Changes[1], roundtrip.Changes[1]);
    }

    /// <summary>必要的顶层字段缺席时必须在调用服务之前失败。</summary>
    /// <param name="member">分别被移除的必要字段。</param>
    [TestMethod]
    [DataRow("hashes")]
    [DataRow("changes")]
    [DataRow("command")]
    public void MissingBatchFieldsAreRejected(string member)
    {
        // 每个负例仅移除一个字段，不靠其他畸形值掩盖失败原因。
        var node = JsonNode.Parse(Payload)!;
        node.AsObject().Remove(member);
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<VocabularyEditsRequest>(node.ToJsonString(), Options));
    }

    /// <summary>错误源、未知枚举及数字值不能被解释为默认ontology写入。</summary>
    /// <param name="sourceJson">单个待测非法源JSON。</param>
    [TestMethod]
    [DataRow("\"shapes\"")]
    [DataRow("\"data\"")]
    [DataRow("\"unknown\"")]
    [DataRow("0")]
    [DataRow("null")]
    public void InvalidSourceCannotDefaultToOntology(string sourceJson)
    {
        // 其他完整内容保持有效，精确测试源判别字段。
        var node = JsonNode.Parse(Payload)!;
        node["changes"]![0]!["sourceId"] = JsonNode.Parse(sourceJson);
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<VocabularyEditsRequest>(node.ToJsonString(), Options));
    }

    /// <summary>源字段缺席、伪造actor或发布资格均不得进入业务。</summary>
    /// <param name="mode">相互独立的字段注入或缺失场景。</param>
    [TestMethod]
    [DataRow("missing-source")]
    [DataRow("extra-change")]
    [DataRow("extra-root")]
    [DataRow("null-array-item")]
    public void IncompleteAndForgedBatchesAreRejected(string mode)
    {
        // 仅对被测一处修改，避免错误相互遮蔽。
        var node = JsonNode.Parse(Payload)!;
        if (mode == "missing-source") node["changes"]![0]!.AsObject().Remove("sourceId");
        if (mode == "extra-change") node["changes"]![0]!["actor"] = "forged";
        if (mode == "extra-root") node["publishEligible"] = true;
        if (mode == "null-array-item") node["changes"]![0] = null;
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<VocabularyEditsRequest>(node.ToJsonString(), Options));
    }

    /// <summary>快照身份字段即使值为null也必须显式提供，禁止草稿伪装成正式发布。</summary>
    [TestMethod]
    public void SnapshotRequiresExplicitReleaseContextAndSourceProvenance()
    {
        // 合成快照直接使用严格协议，不构造假正式发布成功证据。
        const string json = """
            {"draftId":"draft","releaseId":null,"manifestHash":null,"revision":2,"hashes":{"ontologyHash":"o","shapesHash":"s","vocabularyHash":"v","dataHash":"d","bundleHash":"b"},"profileVersion":"3","profileHash":"profile","triples":[{"sourceId":"vocabulary","triple":{"subject":{"kind":"iri","value":"urn:synthetic:C","datatype":null,"language":null},"predicate":"http://www.w3.org/2004/02/skos/core#prefLabel","object":{"kind":"literal","value":"设备","datatype":null,"language":"zh"}}}],"diagnostics":[]}
            """;
        // 从完整快照确认来源与原始RDF项保留。
        var snapshot = JsonSerializer.Deserialize<VocabularySnapshot>(json, Options)!;
        Assert.IsNull(snapshot.ReleaseId);
        Assert.AreEqual("vocabulary", snapshot.Triples[0].SourceId);
        Assert.AreEqual("zh", snapshot.Triples[0].Triple.Object.Language);
        // 删除显式身份字段后，不能被默认null隐藏。
        var node = JsonNode.Parse(json)!;
        node.AsObject().Remove("releaseId");
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<VocabularySnapshot>(node.ToJsonString(), Options));
    }

    /// <summary>宿主同样使用标准Web序列化设置。</summary>
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web);

    /// <summary>仅合成IRI、非秘密hash和精确修订命令。</summary>
    private const string Payload = """
        {"hashes":{"ontologyHash":"ontology","shapesHash":"shapes","vocabularyHash":"vocabulary","dataHash":"data","bundleHash":"bundle"},"changes":[{"sourceId":"vocabulary","edit":{"subjectIri":"urn:synthetic:C","predicateIri":"http://www.w3.org/2004/02/skos/core#prefLabel","oldObject":null,"newObject":{"kind":"literal","value":"设备","datatype":null,"language":"zh-Hans"}}},{"sourceId":"ontology","edit":{"subjectIri":"urn:synthetic:property","predicateIri":"urn:ontology-platform:semantics:nominalUnit","oldObject":null,"newObject":{"kind":"iri","value":"urn:synthetic:unit:v1","datatype":null,"language":null}}}],"command":{"commandId":"m3-contract","idempotencyKey":"m3-contract","reason":"验证批量来源合同","expectedRevision":2}}
        """;
}
