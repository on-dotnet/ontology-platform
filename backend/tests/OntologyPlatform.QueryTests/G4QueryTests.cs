using System.Text;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using System.Text.Json;
using OntologyPlatform.Modules.SemanticQuery;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.QueryTests;

/// <summary>规范字节不依赖运行时文化、字段声明顺序或浏览器浮点格式。</summary>
[TestClass]
public sealed class G4QueryTests
{
    /// <summary>同一登记器保留旧能力，G4实际输出严格区分四态载荷和精确标量。</summary>
    [TestMethod]
    public void RegistryUsesGeneratedClosedG4SchemaWithoutChangingG2()
    {
        // 默认旧宿主不因新增查询能力改变能力文档或版本字节。
        var legacy = new CapabilityRegistry().Read();
        // 只有显式启用的查询宿主加载当前正式G4生成物。
        var configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?> { ["G4:QueryEnabled"] = "true" }).Build();
        // 相同生成输入跨实例必须产生相同能力版本。
        var capabilities = new CapabilityRegistry(configuration).Read();
        Assert.AreEqual(4, capabilities.Length);
        CollectionAssert.AreEqual(legacy.Select(value => JsonSerializer.Serialize(value)).ToArray(),
            capabilities.Where(value => !value.Id.StartsWith("g4_", StringComparison.Ordinal)).Select(value => JsonSerializer.Serialize(value)).ToArray());
        // 真实输出闭包包含所有正式判别子类，而不是any或G2图数据。
        var query = capabilities.Single(value => value.Id == "g4_resolve_entity");
        Assert.AreEqual(query.Version, new CapabilityRegistry(configuration).Read().Single(value => value.Id == query.Id).Version);
        // 组件名由原生OpenAPI导出稳定生成，不能在测试中构造替身Schema。
        var definitions = query.OutputSchema.GetProperty("$defs");
        Assert.AreEqual(4, definitions.GetProperty("G4QueryDatum").GetProperty("oneOf").GetArrayLength());
        Assert.IsTrue(definitions.GetProperty("G4QueryDatumG4EntityDatum").GetProperty("required").EnumerateArray().Any(value => value.GetString() == "kind"));
        Assert.AreEqual("string", definitions.GetProperty("G4QueryValueG4Int64Value").GetProperty("properties").GetProperty("lexical").GetProperty("type").GetString());
        Assert.AreEqual("null", definitions.GetProperty("G4QueryValueG4NullValue").GetProperty("properties").GetProperty("lexical").GetProperty("type").GetString());
        Assert.IsFalse(definitions.GetProperty("G4QueryResultV1").GetProperty("additionalProperties").GetBoolean());
        Assert.AreEqual(6, definitions.GetProperty("G4QueryResultV1").GetProperty("properties").GetProperty("status").GetProperty("enum").GetArrayLength());
    }

    /// <summary>无结果读取授权的首次无数据响应不得通过执行视图泄露已保存结果摘要。</summary>
    [TestMethod]
    public void ExecutionViewDoesNotDisclosePersistedHash()
    {
        // 模拟已持久的无数据六态；仅有执行状态不构成result.read许可。
        var record = new G4QueryRecord { Id = "query-no-read", ExecutionStatus = "COMPLETED", ResultHash = new string('a', 64),
            CreatedAtUtc = DateTimeOffset.UtcNow, CompletedAtUtc = DateTimeOffset.UtcNow, ExpiresAtUtc = DateTimeOffset.UtcNow.AddHours(24) };
        Assert.IsNull(G4QueryResultStore.View(record).ResultHash);
        Assert.AreEqual(new string('a', 64), record.ResultHash);
    }

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

    /// <summary>同外部号不同厂区必须产生不同完整身份，原精确数值及业务时间不丢失。</summary>
    [TestMethod]
    public void TypedProjectionPreservesScopeAndPreciseSourceValues()
    {
        // 单元材料仅覆盖映射投影，正式发布身份由真实HTTP切片另证。
        var dataset = new MappingDatasetRef { SnapshotId = "catalog-original", Schema = "production", Name = "fixture", Kind = "TABLE" };
        // 此处字段名与序号显式登记，测试不拼自由SQL。
        MappingFieldRef Field(string name, int ordinal) => new() { DatasetRef = dataset, Name = name, Ordinal = ordinal };
        // 固定最小映射覆盖源scope、有效时间与精确decimal属性。
        var mapping = new MappingDefinition
        {
            Entities = [new MappingEntityBinding { Id = "asset", EntityClassIri = "urn:fixture:Asset", DatasetRef = dataset,
                IdentitySpecId = "identity", TemporalSpecId = "time", ScopeFields = new MappingScopeFields { Organization = Field("org",1), Site = Field("site",2) } }],
            IdentitySpecs = [new MappingIdentitySpec { Id = "identity", OrganizationFieldRef = Field("org",1), SiteFieldRef = Field("site",2),
                ExternalIdFieldRefs = [Field("id",3)], SourceNamespace = "fixture", ValidFromFieldRef = Field("from",4), ValidToFieldRef = Field("to",5) }],
            TemporalSpecs = [new MappingTemporalSpec { Id = "time", EventTimeFieldRef = Field("from",4), ObservedAtFieldRef = null,
                ValidFromFieldRef = Field("from",4), ValidToFieldRef = Field("to",5), TimezonePolicy = new MappingTimezonePolicy { Kind = "UTC", ZoneId = null }, Precision = "MICROSECOND" }],
            Properties = [new MappingPropertyBinding { Id = "value", EntityBindingId = "asset", PropertyIri = "urn:fixture:value", FieldRef = Field("value",6), ConversionId = null, UnitSpecId = null, NullPolicy = "REJECT_NULL" }],
            Relations = [], Conversions = [], UnitSpecs = []
        };
        // 全范围只用于本单元样本，不构造真实授权证明。
        var scope = new ResourceScope { OrganizationId = "org-1", SiteIds = ["site-1", "site-2"] };
        // 上游已验证材料在此明确是投影单元替身，禁止据此宣称真实发布通过。
        var context = new G4QueryBindingContext { Binding = G4QueryRaceTests.Binding(1), Scope = scope, OriginalCatalog = null!, CurrentCatalog = null!,
            Manifest = new MappingReleaseManifest { SchemaVersion = "g4.mapping.v1", MappingReleaseId = "mapping-1", MappingId = "mapping-root",
                Scope = scope, OriginDraftId = "draft", OriginDraftRevision = 1, Binding = null!, Mapping = mapping, ReviewReceipt = null!, CreatedAtUtc = DateTimeOffset.UtcNow } };
        // 字典中的值均来自正式精确标量类型，不允许任意对象或double混入。
        var row = new Dictionary<string, G4QueryValue>
        {
            ["org"] = new G4StringValue { Lexical = "org-1" }, ["site"] = new G4StringValue { Lexical = "site-1" }, ["id"] = new G4StringValue { Lexical = "same" },
            ["from"] = new G4UtcValue { Lexical = "2026-11-14T01:02:03.123456Z" },
            ["to"] = new G4UtcValue { Lexical = "2026-11-15T01:02:03.123456Z" },
            ["value"] = new G4DecimalValue { Lexical = "9007199254740993.20", Precision = 20, Scale = 2 }
        };
        // 第二厂同号是另一个真实身份，不能按externalId合并。
        var second = new Dictionary<string, G4QueryValue>(row) { ["site"] = new G4StringValue { Lexical = "site-2" } };
        // 水位明确标记为单元样本，真实PG测试另行提供实际pg_current_snapshot。
        var read = new G4SourceQueryRead { EntityBindingId = "asset", Rows = [row,second], StartedAtUtc = DateTimeOffset.UtcNow,
            CompletedAtUtc = DateTimeOffset.UtcNow, TransactionSnapshot = "fixture-only", Limited = false, Indeterminate = false,
            RecordKeyFields = ["org","site","id","from"], QueryPlanHash = new string('e',64) };
        // 实际投影代码必须给每个当前有权源行闭合证据。
        var projected = G4QueryExecution.ProjectEntities("query-1", "trace-1", context, read);
        Assert.HasCount(2, projected.Entities);
        Assert.AreNotEqual(projected.Entities[0].EntityIri, projected.Entities[1].EntityIri);
        Assert.AreEqual("9007199254740993.20", projected.Entities[0].Properties[0].Value.Lexical);
        Assert.AreEqual("2026-11-14T01:02:03.123456Z", projected.Entities[0].Identity.EffectiveTime!.From.Lexical);
        Assert.IsTrue(projected.Evidence.All(item => item.Precision == "ROW_KEY" && item.SourceRecordRef is not null));
        Assert.IsNull(projected.Receipt.Receipt.SourceRecordRef, "多行回执不能伪造一个总行键。");
        Assert.Throws<SemanticOperationException>(() => G4QueryExecution.ProjectEntities("query-2", "trace-1", context, read with { Rows = [row,row] }));
        // 缺主键时保留实际数据集证据，不升级为记录定位。
        var degraded = G4QueryExecution.ProjectEntities("query-3", "trace-1", context, read with { RecordKeyFields = [] });
        Assert.IsTrue(degraded.Evidence.All(item => item.Precision == "DATASET" && item.SourceRecordRef is null));
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
