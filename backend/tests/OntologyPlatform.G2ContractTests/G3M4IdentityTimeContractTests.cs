using System.Text.Json;
using System.Text.Json.Nodes;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.G2ContractTests;

/// <summary>在业务并行前冻结身份时间的严格JSON和不猜时区的半开关系。</summary>
[TestClass]
public sealed class G3M4IdentityTimeContractTests
{
    /// <summary>与宿主相同的JSON命名策略。</summary>
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web);

    /// <summary>仅合成IRI与固定非秘密散列占位的完整命令。</summary>
    private const string Payload = """
        {"hashes":{"ontologyHash":"o","shapesHash":"s","vocabularyHash":"v","dataHash":"d","bundleHash":"b"},"changes":[{"sourceId":"ontology","edit":{"subjectIri":"urn:synthetic:claim","predicateIri":"urn:ontology-platform:semantics:externalIdentifier","oldObject":null,"newObject":{"kind":"literal","value":"编号甲","datatype":null,"language":null}}}],"command":{"commandId":"m4-contract","idempotencyKey":"m4-contract","reason":"身份时间合同测试","expectedRevision":2}}
        """;

    /// <summary>精确源、编号词法和完整CAS命令往返保留。</summary>
    [TestMethod]
    public void ExactIdentityCommandRoundtrips()
    {
        // 输入经真实严格DTO解析，不手工模拟宿主结果。
        var request = JsonSerializer.Deserialize<IdentityTimeEditsRequest>(Payload, Options)!;
        Assert.AreEqual(2L, request.Command.ExpectedRevision);
        Assert.AreEqual("编号甲", request.Changes[0].Edit.NewObject!.Value);
        Assert.AreEqual(request.Changes[0], JsonSerializer.Deserialize<IdentityTimeEditsRequest>(JsonSerializer.Serialize(request, Options), Options)!.Changes[0]);
    }

    /// <summary>缺失、null、未知字段和非法源均在调用服务前拒绝。</summary>
    /// <param name="mode">互不遮蔽的单字段畸形场景。</param>
    [TestMethod]
    [DataRow("missing-command")]
    [DataRow("missing-hashes")]
    [DataRow("missing-changes")]
    [DataRow("null-changes")]
    [DataRow("null-item")]
    [DataRow("extra-actor")]
    [DataRow("numeric-source")]
    [DataRow("unknown-source")]
    public void InvalidIdentityEnvelopeFailsClosed(string mode)
    {
        // 每个负例只改一处，保证错误不会互相掩盖。
        var value = JsonNode.Parse(Payload)!;
        if (mode.StartsWith("missing-", StringComparison.Ordinal)) value.AsObject().Remove(mode[8..]);
        if (mode == "null-changes") value["changes"] = null;
        if (mode == "null-item") value["changes"]![0] = null;
        if (mode == "extra-actor") value["actor"] = "forged";
        if (mode == "numeric-source") value["changes"]![0]!["sourceId"] = 0;
        if (mode == "unknown-source") value["changes"]![0]!["sourceId"] = "data";
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<IdentityTimeEditsRequest>(value.ToJsonString(), Options));
    }

    /// <summary>词法不带时区、非法日期和超出受控精度的值不被机器默认补齐。</summary>
    /// <param name="text">保持原始输入词法。</param>
    /// <param name="valid">受控模板是否接受。</param>
    [TestMethod]
    [DataRow("2026-01-01T00:00:00Z", true)]
    [DataRow("2026-01-01T08:00:00+08:00", true)]
    [DataRow("2026-01-01T00:00:00.1234567-05:30", true)]
    [DataRow("2026-01-01T00:00:00", false)]
    [DataRow("2026-02-30T00:00:00Z", false)]
    [DataRow("2026-01-01", false)]
    [DataRow("2026-01-01T24:00:00Z", false)]
    [DataRow("2026-01-01T00:00:60Z", false)]
    [DataRow("2026-01-01T00:00:00+14:01", false)]
    [DataRow("2026-01-01T00:00:00.12345678Z", false)]
    [DataRow("2026-01-01T00:00:00Z ", false)]
    [DataRow("2026-01-01T00:00:00Z\n", false)]
    [DataRow("2026-01-01T00:00:00Z\r\n", false)]
    [DataRow("\t2026-01-01T00:00:00Z", false)]
    [DataRow("2026-01-01T00:00:00Z\t", false)]
    public void ExplicitTimezoneAndExactLexicalBoundary(string text, bool valid) =>
        Assert.AreEqual(valid, TemporalContractRules.TryInstant(text, out _));

    /// <summary>半开相邻区间不冲突，倒序无效，未知不冒充确定。</summary>
    [TestMethod]
    public void IntervalRelationsKeepUnknownDistinct()
    {
        Assert.AreEqual(TemporalRelation.Disjoint, TemporalContractRules.Compare("2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z", "2026-02-01T08:00:00+08:00", null));
        Assert.AreEqual(TemporalRelation.Overlap, TemporalContractRules.Compare("2026-01-01T00:00:00Z", "2026-03-01T00:00:00Z", "2026-02-01T00:00:00Z", "2026-04-01T00:00:00Z"));
        Assert.AreEqual(TemporalRelation.Indeterminate, TemporalContractRules.Compare("2026-01-01T00:00:00Z", null, "2026-02-01T00:00:00Z", null));
        Assert.AreEqual(TemporalRelation.Invalid, TemporalContractRules.Compare("2026-02-01T00:00:00Z", "2026-01-01T00:00:00Z", null, null));
        Assert.AreEqual(TemporalRelation.Invalid, TemporalContractRules.Compare("2026-01-01T00:00:00Z", "2026-01-01T00:00:00Z", null, null));
    }
}
