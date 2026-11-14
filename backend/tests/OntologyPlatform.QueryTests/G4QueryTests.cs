using System.Text;
using Microsoft.AspNetCore.DataProtection;
using System.Text.Json;
using OntologyPlatform.Modules.SemanticQuery;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.QueryTests;

/// <summary>规范字节不依赖运行时文化、字段声明顺序或浏览器浮点格式。</summary>
[TestClass]
public sealed class G4QueryTests
{
    /// <summary>UTF8键顺序、控制符最小规则与精确字符串逐字节稳定。</summary>
    [TestMethod]
    public void CanonicalBytesPreservePreciseValuesAndUnicode()
    {
        // 补充平面字符与私用字符验证UTF8排序不同于UTF16 ordinal排序。
        using var input = JsonDocument.Parse("{\"𐀀\":0,\"\ue000\":1,\"value\":\"9007199254740993.20\",\"text\":\"中文\\n\\t/\"}");
        // 控制字符统一小写u00xx，非ASCII和斜线保真。
        var expected = "{\"text\":\"中文\\u000a\\u0009/\",\"value\":\"9007199254740993.20\",\"\ue000\":1,\"𐀀\":0}";
        CollectionAssert.AreEqual(Encoding.UTF8.GetBytes(expected), G4QueryCanonical.Value(input.RootElement));
        // 不允许一般JSON数字冒充安全结构整数。
        using var unsafeNumber = JsonDocument.Parse("{\"value\":9007199254740993}");
        Assert.Throws<InvalidOperationException>(() => G4QueryCanonical.Value(unsafeNumber.RootElement));
        using var fraction = JsonDocument.Parse("{\"value\":1.5}");
        Assert.Throws<InvalidOperationException>(() => G4QueryCanonical.Value(fraction.RootElement));
    }
    /// <summary>不同小数精度的同类型时间按真实时刻排序，不能按Z字符位置排序。</summary>
    [TestMethod]
    public void ProjectionSortsActualTimeAndRefusesMixedTimeKinds()
    {
        // 这里只验证规范排序，不以合成wire代替真实源证据。
        var first = new G4ObservationDatum
        {
            EntityIri = "urn:fixture:one", EvidenceIds = ["e-1"],
            Identity = new G4QueryIdentity { OrganizationId = "org-1", SiteId = "site-1", SourceNamespace = "fixture", ExternalId = "one", EffectiveTime = null },
            PropertyIri = "urn:fixture:value", Value = new G4Int64Value { Lexical = "1" }, Unit = null,
            EventTime = new G4QueryTime { Kind = "UTC", Lexical = "2026-11-14T00:00:03Z", FractionalDigits = 0 },
            ObservedAtUtc = "2026-11-14T00:00:04.000000Z", ValidTime = null
        };
        // 同秒稍晚100毫秒，但词法小数点排在Z之前。
        var later = first with { EventTime = first.EventTime with { Lexical = "2026-11-14T00:00:03.1Z", FractionalDigits = 1 } };
        using var ordered = JsonDocument.Parse(G4QueryCanonical.Projection([later, first]));
        Assert.AreEqual(first.EventTime.Lexical, ordered.RootElement[0].GetProperty("eventTime").GetProperty("lexical").GetString());
        // LOCAL与UTC没有已知可比较基准，不能自行换算或混排。
        var local = first with { EventTime = first.EventTime with { Kind = "LOCAL", Lexical = "2026-11-14T00:00:03" } };
        Assert.Throws<InvalidOperationException>(() => G4QueryCanonical.Projection([local, first]));
    }

    /// <summary>密文与queryId绑定，换行或密文篡改不能作为可恢复结果披露。</summary>
    [TestMethod]
    public void ProtectedResultRejectsTamperingAndCrossQueryReplay()
    {
        // 纯密码学测试使用一次性内存provider，真实跨上下文keyring由持久测试另验。
        var provider = new EphemeralDataProtectionProvider();
        // 测试wire证据只服务精确序列化，不声明为真实源回执。
        var result = FixtureResult();
        // 相同规范明文必须在解密后逐字节恢复。
        var protectedResult = G4QueryResultStore.Protect(provider, "query-1", result);
        CollectionAssert.AreEqual(G4QueryCanonical.Result(result), G4QueryResultStore.Unprotect(provider, "query-1", protectedResult.Ciphertext, protectedResult.Hash));
        Assert.Throws<SemanticOperationException>(() => G4QueryResultStore.Unprotect(provider, "query-other", protectedResult.Ciphertext, protectedResult.Hash));
        // 篡改真实密文字节，不以单纯不同测试字符串替代完整性检查。
        var damaged = protectedResult.Ciphertext.ToArray();
        damaged[^1] ^= 1;
        Assert.Throws<SemanticOperationException>(() => G4QueryResultStore.Unprotect(provider, "query-1", damaged, protectedResult.Hash));
        Assert.Throws<SemanticOperationException>(() => G4QueryResultStore.Unprotect(provider, "query-1", protectedResult.Ciphertext, new string('0',64)));
    }

    /// <summary>未读取分支不能强迫伪造回执，UNKNOWN回执不能升级为确定行证据。</summary>
    [TestMethod]
    public void ReceiptsMatchActualReadsAndCannotUpgradePrecision()
    {
        // 使用完整冻结wire，当前测试不冒充真实源读取。
        var result = FixtureResult();
        // 空投影只为验证回执形状，不授予任何运行权限。
        var state = new G4QueryState { Binding = G4QueryRaceTests.Binding(1), Scope = result.Evidence[0].Scope, Projections = [] };
        // FORBIDDEN未读源，无真实读取回执，合同必须允许null引用。
        var forbidden = result with { Status = "UNAUTHORIZED", Data = [], Evidence = [],
            SubSources = [result.SubSources[0] with { Status = "FORBIDDEN", SourceReadReceiptId = null, WatermarkKind = "UNKNOWN" }] };
        G4QueryRules.ValidateResult(forbidden);
        Assert.AreEqual(0, G4SourceEvidenceService.BindReceipts("query-1", state, forbidden, []).Receipts.Length);
        // 重新计算有效外置hash，确保负例检验精度而不是被无效hash提前挡住。
        var receipt = ReceiptFixture("query-1", state.Binding, result).Receipt with { Precision = "UNKNOWN", SourceRecordRef = null };
        // 一份完整认证的UNKNOWN回执也不能支撑ROW_KEY断言。
        var stored = new G4QueryStoredReceipt { Receipt = receipt, ReceiptHash = G4QueryCanonical.Hash(G4QueryCanonical.Serialize(receipt)) };
        Assert.Throws<SemanticOperationException>(() => G4SourceEvidenceService.BindReceipts("query-1", state, result, [stored]));
    }

    /// <summary>事务测试构造闭合回执；来源适配器真实回执必须由执行器按源事实另建。</summary>
    internal static G4QueryStoredReceipt ReceiptFixture(string queryId, G4QueryBinding binding, G4QueryResultV1 result)
    {
        // 回执仅覆盖分支投影，不把回执自身或总结果放入resultHash。
        var receipt = new G4SourceReadReceipt
        {
            SchemaVersion = "g4.read-receipt.v1", ReceiptId = "receipt-1", QueryId = queryId, Binding = binding,
            SourceDatasetRef = "dataset-1", QueryPlanHash = new string('e',64), AdapterVersion = "pg-query-v1",
            Scope = result.Evidence[0].Scope, Status = "SUCCESS", RowCount = 1, Limited = false,
            WatermarkKind = "TRANSACTION_SNAPSHOT", Watermark = "fixture-only", SourceRecordRef = "row-1", Precision = "ROW_KEY",
            ValidTime = null, ReadStartedAtUtc = "2026-11-14T01:02:03.000000Z", ReadCompletedAtUtc = result.ObservedAtUtc,
            ResultHash = G4QueryCanonical.Hash(G4QueryCanonical.Projection(result.Data)), TraceId = result.TraceId
        };
        return new G4QueryStoredReceipt { Receipt = receipt, ReceiptHash = G4QueryCanonical.Hash(G4QueryCanonical.Serialize(receipt)) };
    }

    /// <summary>字节与密码学用的完整判别结果，不冒充真实源或当前授权证明。</summary>
    internal static G4QueryResultV1 FixtureResult() => new()
    {
        SchemaVersion = "g4.query-result.v1", Status = "FOUND", Candidates = [], Limited = false, Diagnostics = [],
        TraceId = "trace-1", ObservedAtUtc = "2026-11-14T01:02:04.000000Z", ValidTime = null,
        Snapshot = new G4QuerySnapshot { OntologyReleaseId = "ontology-1", MappingReleaseIds = ["mapping-1"], SourceCatalogSnapshotIds = ["catalog-current"],
            CapabilityId = "g4_read_observations", CapabilityVersion = new string('a',64) },
        Data = [new G4ObservationDatum { EntityIri = "urn:fixture:one", EvidenceIds = ["e-1"],
            Identity = new G4QueryIdentity { OrganizationId = "org-1", SiteId = "site-1", SourceNamespace = "fixture", ExternalId = "one", EffectiveTime = null },
            PropertyIri = "urn:fixture:value", Value = new G4DecimalValue { Lexical = "9007199254740993.20", Precision = 20, Scale = 2 }, Unit = null,
            EventTime = new G4QueryTime { Kind = "UTC", Lexical = "2026-11-14T01:02:03.123456Z", FractionalDigits = 6 },
            ObservedAtUtc = "2026-11-14T01:02:04.000000Z", ValidTime = null }],
        Evidence = [new G4SourceEvidenceRef { EvidenceId = "e-1", ConnectionId = "connection-1", MappingReleaseId = "mapping-1", SourceCatalogSnapshotId = "catalog-original",
            SourceDatasetRef = "dataset-1", SourceReadReceiptId = "receipt-1", Scope = new ResourceScope { OrganizationId = "org-1", SiteIds = ["site-1"] },
            Precision = "ROW_KEY", SourceRecordRef = "row-1", ValidTime = null, ObservedAtUtc = "2026-11-14T01:02:04.000000Z" }],
        SubSources = [new G4QuerySubSource { ConnectionId = "connection-1", Status = "SUCCESS", ObservedAtUtc = "2026-11-14T01:02:04.000000Z",
            WatermarkKind = "TRANSACTION_SNAPSHOT", SourceReadReceiptId = "receipt-1", Limited = false }]
    };
}
