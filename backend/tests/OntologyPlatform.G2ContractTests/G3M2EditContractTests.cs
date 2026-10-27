using System.Text.Json;
using System.Text.Json.Nodes;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.G2ContractTests;

/// <summary>M2继续消费唯一精确编辑合同，严格拒绝不完整或伪造的客户端正文。</summary>
[TestClass]
public sealed class G3M2EditContractTests
{
    /// <summary>显式空旧值表示新增，主体与词法值不得由标签或画布重建。</summary>
    [TestMethod]
    public void ExactEditRoundtripRetainsNullAndLanguage()
    {
        // 固定完整JSON用于证明有效路径，而非仅测试所有正文都会拒绝。
        var edit = JsonSerializer.Deserialize<EditDraftRequest>(Payload, Options)!;
        Assert.IsNull(edit.Edit.OldObject);
        Assert.AreEqual("zh", edit.Edit.NewObject!.Language);
        Assert.AreEqual("设备", edit.Edit.NewObject.Value);
        Assert.AreEqual(2L, edit.Command.ExpectedRevision);
        Assert.AreEqual(edit, JsonSerializer.Deserialize<EditDraftRequest>(JsonSerializer.Serialize(edit, Options), Options));
    }

    /// <summary>缺字段与未知字段必须在进入服务前失败关闭。</summary>
    /// <param name="member">需要显式提供的精确命令字段。</param>
    [TestMethod]
    [DataRow("subjectIri")]
    [DataRow("predicateIri")]
    [DataRow("oldObject")]
    [DataRow("newObject")]
    public void MissingEditMemberCannotBecomeImplicitMutation(string member)
    {
        // 每次只移除一个字段，避免其他无效字段遮蔽被测边界。
        var node = JsonNode.Parse(Payload)!;
        node["edit"]!.AsObject().Remove(member);
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<EditDraftRequest>(node.ToJsonString(), Options));
    }

    /// <summary>畸形JSON、未知actor或发布资格都不能被忽略。</summary>
    /// <param name="extra">企图注入到精确编辑命令的额外字段。</param>
    [TestMethod]
    [DataRow("actor")]
    [DataRow("publishEligible")]
    [DataRow("sourceId")]
    public void UnknownEditFieldsAndMalformedJsonAreRejected(string extra)
    {
        // 身份、发布资格及目标源全部由服务器合同限定。
        var node = JsonNode.Parse(Payload)!;
        node["edit"]![extra] = "forged";
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<EditDraftRequest>(node.ToJsonString(), Options));
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<EditDraftRequest>("{", Options));
    }

    /// <summary>未知字符串和数字枚举在JSON边界拒绝，不降级为默认RDF项。</summary>
    /// <param name="kindJson">不受支持的JSON枚举值。</param>
    [TestMethod]
    [DataRow("\"unknown\"")]
    [DataRow("0")]
    public void UnknownAndNumericTermKindAreRejected(string kindJson)
    {
        // 保留其余有效字段，确保失败来自kind而非缺字段。
        var node = JsonNode.Parse(Payload)!;
        node["edit"]!["newObject"]!["kind"] = JsonNode.Parse(kindJson);
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<EditDraftRequest>(node.ToJsonString(), Options));
    }

    /// <summary>新诊断保留真实Shape定位，旧诊断缺席该可选字段时保持原字节。</summary>
    [TestMethod]
    public void AssessmentShapeIsOptionalAndRoundtripsWithoutChangingLegacyBytes()
    {
        // 旧M1诊断不添加null字段，避免改变历史assessment的原始散列。
        const string legacy = """
            {"sourceId":"shapes","sourceHash":"hash","diagnostic":{"code":"validation_issue","severity":"error","message":"\u7EA6\u675F\u4E0D\u7B26","focusNode":null,"path":null},"line":null,"column":null}
            """;
        // 仅在实际Jena报告提供Shape时才传递原始RDF项。
        var node = JsonNode.Parse(legacy)!;
        node["sourceShape"] = new JsonObject { ["kind"] = "iri", ["value"] = "urn:m2:Shape", ["datatype"] = null, ["language"] = null };
        // 使用JSON往返检查同一生成DTO，不通过第二套客户端结果类型绕过严格字段规则。
        var result = JsonSerializer.Deserialize<AssessmentDiagnostic>(node.ToJsonString(), Options)!;
        Assert.AreEqual("urn:m2:Shape", JsonNode.Parse(JsonSerializer.Serialize(result, Options))!["sourceShape"]!["value"]!.GetValue<string>());
        Assert.AreEqual(legacy, JsonSerializer.Serialize(JsonSerializer.Deserialize<AssessmentDiagnostic>(legacy, Options), Options));
    }

    /// <summary>与正式宿主一致的camelCase配置。</summary>
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web);

    /// <summary>只含合成IRI与无敏感信息的标准命令。</summary>
    private const string Payload = """
        {"edit":{"subjectIri":"urn:m2:C","predicateIri":"http://www.w3.org/2000/01/rdf-schema#label","oldObject":null,"newObject":{"kind":"literal","value":"设备","datatype":null,"language":"zh"}},"command":{"commandId":"m2-contract","idempotencyKey":"m2-contract","reason":"验证精确变更合同","expectedRevision":2}}
        """;
}
