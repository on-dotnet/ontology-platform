using System.Text.Json;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.G2ContractTests;

/// <summary>查询判别合同必须在生成或持久化之前保护精确值和封闭字段。</summary>
[TestClass]
public sealed class G4QueryWireTests
{
    /// <summary>超过JavaScript安全整数的值仍以原始十进制字符串往返。</summary>
    [TestMethod]
    public void ExactObservationSurvivesWireRoundTrip()
    {
        // 独立合成观测验证Int64及PG微秒，不把字节测试当成真实源读取。
        var datum = G4QueryRules.ReadDatum(Observation);
        Assert.IsInstanceOfType<G4ObservationDatum>(datum);
        Assert.AreEqual("9223372036854775807", ((G4ObservationDatum)datum).Value.Lexical);
        // 成员顺序不构成普通wire兼容，重新严格解码确认精确值不变。
        var restored = (G4ObservationDatum)G4QueryRules.ReadDatum(JsonSerializer.Serialize<G4QueryDatum>(datum, G4QueryJson.Options));
        Assert.AreEqual(((G4ObservationDatum)datum).Value.Lexical, restored.Value.Lexical);
        Assert.AreEqual("2026-11-14T01:02:03.123456Z", restored.EventTime!.Lexical);
    }

    /// <summary>封闭判别对象不允许未知字段、重复转义键、错误类型或越界精度。</summary>
    [TestMethod]
    public void InvalidObservationBytesAreRejectedBeforeUse()
    {
        // 每个变体只改变一条已冻结不变量，避免仅验证实现分支是否存在。
        var invalid = new[]
        {
            Observation.Replace("\"kind\":\"observation\"", "\"kind\":\"observation\",\"k\\u0069nd\":\"entity\""),
            Observation.Replace("\"kind\":\"observation\"", "\"kind\":\"observation\",\"sql\":\"SELECT 1\""),
            Observation.Replace("9223372036854775807", "9223372036854775808"),
            Observation.Replace("\"9223372036854775807\"", "9223372036854775807"),
            Observation.Replace("\"fractionalDigits\":6", "\"fractionalDigits\":7"),
            Observation.Replace("2026-11-14T01:02:03.123456Z", "2026-02-30T01:02:03.123456Z"),
            Observation.Replace("\"evidenceIds\":[\"e-1\"]", "\"evidenceIds\":[]"),
            Observation.Replace("e-1", "e-1\\n"),
            Observation.Replace("2026-11-14T01:02:03.123456Z", "2026-11-14T01:02:03.123456Z\\n")
        };
        foreach (var body in invalid)
        {
            Assert.Throws<SemanticOperationException>(() => G4QueryRules.ReadDatum(body));
        }
    }

    /// <summary>decimal的scale固定且不得经浮点中转、舍入或去尾零。</summary>
    [TestMethod]
    public void DecimalScaleAndNullRemainDistinct()
    {
        // 源数值大于2的53次方，尾零仍属于批准scale。
        var exact = Observation.Replace("\"type\":\"int64\",\"lexical\":\"9223372036854775807\"", "\"type\":\"decimal\",\"lexical\":\"9007199254740993.20\",\"precision\":20,\"scale\":2");
        Assert.AreEqual("9007199254740993.20", ((G4ObservationDatum)G4QueryRules.ReadDatum(exact)).Value.Lexical);
        Assert.Throws<SemanticOperationException>(() => G4QueryRules.ReadDatum(exact.Replace("\"scale\":2", "\"scale\":3")));
        Assert.Throws<SemanticOperationException>(() => G4QueryRules.ReadDatum(exact.Replace("9007199254740993.20", "-0.00")));
    }

    /// <summary>请求预算、选择上下文与严格原始字节在同一入口验证。</summary>
    [TestMethod]
    public void RequestRejectsUnknownFieldsAndInvalidSelection()
    {
        // 十字段请求包含已冻结能力和有界预算，版本由登记器另核。
        var body = """
            {"assetId":"asset-1","ontologyReleaseId":"release-1","mappingReleaseIds":["mapping-1"],"capabilityId":"g4_resolve_entity","capabilityVersion":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","relationshipIris":[],"depth":1,"maxRows":2,"timeoutMs":1000,"filters":{}}
            """;
        Assert.AreEqual(2, G4QueryRules.ReadQuery(System.Text.Encoding.UTF8.GetBytes(body), null).MaxRows);
        foreach (var invalid in new[]
        {
            body.Replace("\"maxRows\":2", "\"maxRows\":1"),
            body.Replace("\"filters\":{}", "\"filters\":{\"entityIri\":null}"),
            body.Replace("\"filters\":{}", "\"filters\":{\"cursor\":\"next\"}"),
            body.Replace("\"filters\":{}", "\"filters\":{\"validFrom\":\"2026-11-14T00:00:00Z\"}"),
            body.Replace("\"filters\":{}", "\"filters\":{\"entityIri\":\"urn:fixture:1\",\"siteId\":\"site-1\"}")
        })
        {
            Assert.Throws<SemanticOperationException>(() => G4QueryRules.ReadQuery(System.Text.Encoding.UTF8.GetBytes(invalid), null));
        }
        Assert.Throws<SemanticOperationException>(() => G4QueryRules.ReadQuery(System.Text.Encoding.UTF8.GetBytes(body), "query-1"));
        Assert.Throws<SemanticOperationException>(() => G4QueryRules.ReadQuery([0xff, 0xfe], null));
    }

    /// <summary>六态互斥和证据闭合必须在保存或恢复结果之前验证。</summary>
    [TestMethod]
    public void ResultRejectsFalseEmptyAndDanglingEvidence()
    {
        // 用原合同的真实形状构造字节用例，不声明它是源读取证据。
        var result = """
            {"schemaVersion":"g4.query-result.v1","status":"FOUND","data":[DATUM],"candidates":[],"evidence":[{"evidenceId":"e-1","connectionId":"connection-1","mappingReleaseId":"mapping-1","sourceCatalogSnapshotId":"catalog-original","sourceDatasetRef":"dataset-1","sourceReadReceiptId":"receipt-1","scope":{"organizationId":"org-1","siteIds":["site-1"]},"precision":"ROW_KEY","sourceRecordRef":"row-1","validTime":null,"observedAtUtc":"2026-11-14T01:02:04.000000Z"}],"snapshot":{"ontologyReleaseId":"ontology-1","mappingReleaseIds":["mapping-1"],"sourceCatalogSnapshotIds":["catalog-current"],"capabilityId":"g4_read_observations","capabilityVersion":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"},"subSources":[{"connectionId":"connection-1","status":"SUCCESS","observedAtUtc":"2026-11-14T01:02:04.000000Z","watermarkKind":"TRANSACTION_SNAPSHOT","sourceReadReceiptId":"receipt-1","limited":false}],"validTime":null,"observedAtUtc":"2026-11-14T01:02:04.000000Z","traceId":"trace-1","limited":false,"diagnostics":[]}
            """;
        result = result.Replace("DATUM", Observation);
        Assert.AreEqual("FOUND", G4QueryRules.ReadResult(System.Text.Encoding.UTF8.GetBytes(result)).Status);
        // UNKNOWN只有诊断证据，不得输出断言；此时是UNAVAILABLE而不是EMPTY。
        var uncertain = result.Replace(Observation, string.Empty).Replace("\"status\":\"FOUND\"", "\"status\":\"UNAVAILABLE\"")
            .Replace("\"precision\":\"ROW_KEY\"", "\"precision\":\"UNKNOWN\"")
            .Replace("\"sourceRecordRef\":\"row-1\"", "\"sourceRecordRef\":null");
        Assert.AreEqual("UNAVAILABLE", G4QueryRules.ReadResult(System.Text.Encoding.UTF8.GetBytes(uncertain)).Status);
        foreach (var invalid in new[]
        {
            result.Replace("\"status\":\"FOUND\"", "\"status\":\"EMPTY\""),
            result.Replace("\"evidenceId\":\"e-1\"", "\"evidenceId\":\"absent\""),
            result.Replace("\"status\":\"SUCCESS\"", "\"status\":\"TIMEOUT\""),
            result.Replace("\"precision\":\"ROW_KEY\"", "\"precision\":\"UNKNOWN\""),
            result.Replace("\"siteIds\":[\"site-1\"]", "\"siteIds\":[\"other-site\"]")
        }) Assert.Throws<SemanticOperationException>(() => G4QueryRules.ReadResult(System.Text.Encoding.UTF8.GetBytes(invalid)));
    }

    /// <summary>固定合同样例保留所有必填null，不使用任意字典载荷。</summary>
    private const string Observation = """
        {"kind":"observation","entityIri":"urn:fixture:heat:1","evidenceIds":["e-1"],"identity":{"organizationId":"org-1","siteId":"site-1","sourceNamespace":"pg-fixture","externalId":"H1","effectiveTime":null},"propertyIri":"urn:fixture:sequence","value":{"type":"int64","lexical":"9223372036854775807"},"unit":null,"eventTime":{"kind":"UTC","lexical":"2026-11-14T01:02:03.123456Z","fractionalDigits":6},"observedAtUtc":"2026-11-14T01:02:04.000000Z","validTime":null}
        """;
}
