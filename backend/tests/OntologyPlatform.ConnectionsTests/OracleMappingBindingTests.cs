using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>Oracle 正式读取的纯类型、关系和原目录字节资格反例，不触碰任何实例。</summary>
[TestClass]
public sealed class OracleMappingBindingTests
{
    /// <summary>同键异标度精确匹配；NULL、邻近值、跨厂与纳秒边界不会组成边。</summary>
    [TestMethod]
    public void OnlyExactKeysAndOverlappingHalfOpenIntervalsMatch()
    {
        // 父区间为两个微秒，子窗口可向前或向后偏移一个纳秒。
        var parent = Row("1.0", 12, 1, "2026-01-01T00:00:00.000001Z", "2026-01-01T00:00:00.000003Z");
        // 已知交叠的目标用于逐项替换单一输入。
        var target = Row("1.00", 13, 2, "2026-01-01T00:00:00.000002999Z", "2026-01-01T00:00:00.000005Z");
        Assert.IsTrue(OracleQueryReader.Matches(parent, target));
        target["FROM_TS"] = new G4UtcValue { Lexical = "2026-01-01T00:00:00.000003Z" };
        Assert.IsFalse(OracleQueryReader.Matches(parent, target));
        target["FROM_TS"] = new G4UtcValue { Lexical = "2026-01-01T00:00:00.000001Z" };
        target["SITE_ID"] = new G4StringValue { Lexical = "site-b" };
        Assert.IsFalse(OracleQueryReader.Matches(parent, target));
        target["SITE_ID"] = new G4StringValue { Lexical = "site-a" };
        target["JOIN_KEY"] = new G4DecimalValue { Precision = 13, Scale = 2, Lexical = "1.01" };
        Assert.IsFalse(OracleQueryReader.Matches(parent, target));
        target["JOIN_KEY"] = new G4NullValue { Lexical = null, DeclaredType = "decimal" };
        Assert.IsFalse(OracleQueryReader.Matches(parent, target));
        parent["JOIN_KEY"] = target["JOIN_KEY"];
        Assert.IsFalse(OracleQueryReader.Matches(parent, target));
    }

    /// <summary>只有准确原始对象、类型、顺序和 Oracle 元数据才可执行。</summary>
    [TestMethod]
    public void RejectsChangedPhysicalDeclarationsAndCatalogAlgorithm()
    {
        // 固定 Oracle 两表形状，不依赖其它连接器的类型或命名。
        var table = Entity();
        OracleMappingSourceValidator.RequireShape(table);
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.RequireShape(table with { Kind = "VIEW" }));
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.RequireShape(table with { Name = "omq_entity" }));
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.RequireShape(table with { Fields = table.Fields.Reverse().ToArray() }));
        // 精度变化仍在 CLR 能力以内，但不属于获准模板，必须拒绝。
        var different = table.Fields.ToArray();
        different[0] = different[0] with { Precision = 19 };
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.RequireShape(table with { Fields = different }));
        Assert.AreNotEqual(ConnectionApplicationService.CanonicalCatalog([table], "oracle-m2-v1").Fingerprint,
            ConnectionApplicationService.CanonicalCatalog([table], "pg-m1-v1").Fingerprint);
    }

    /// <summary>二十八位系数、尾空格、组合字符、六位时间和空值分别无损保留。</summary>
    [TestMethod]
    public void TypedCellsPreserveExactPrecisionAndText()
    {
        // 日期由无时区源值构造，精确到实际微秒。
        var instant = new DateTime(2026, 11, 19, 12, 0, 0, DateTimeKind.Unspecified).AddTicks(10);
        // 词法边界使用允许的二十八位有符号系数。
        var row = new OracleMappingRow(999999999999999999L, 1m, -9999999999999999999999.999999m, "org-demo", "site-a",
            "ST-1", "e\u0301 ", instant, instant.AddDays(1), instant, instant);
        // 一次实际转换结果同时供映射与查询消费。
        var fields = OracleMappingSourceValidator.Cells(row, Entity());
        Assert.AreEqual("999999999999999999", fields["ROW_ID"].Value);
        Assert.AreEqual("-9999999999999999999999.999999", fields["VAL"].Value);
        Assert.AreEqual("1.0", fields["JOIN_KEY"].Value);
        Assert.AreEqual("e\u0301 ", fields["LABEL"].Value);
        Assert.AreEqual("2026-11-19 12:00:00.000001", fields["EVENT_TS"].Value);
        Assert.IsNull(OracleMappingSourceValidator.Cells(row with { Value = null }, Entity())["VAL"].Value);
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.Cells(row with { JoinKey = 1.01m }, Entity()));
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.Cells(row with { Event = instant.AddTicks(1) }, Entity()));
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.Cells(row with { External = "id " }, Entity()));
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.Cells(row with { To = instant }, Entity()));
    }

    /// <summary>Oracle 双表两个分支共享完整二十二字段证明，单表及目录变更仍有明确边界。</summary>
    [TestMethod]
    public void BothOracleBranchesDemandOneCompleteProjection()
    {
        // 生产入口的投影计算不访问构造器中的运行依赖。
        var reader = new QueryBindingReader(null!, null!, null!, null!, TimeProvider.System);
        // 目录由独立 DDL 清单构造，目标键使用不同精度与标度。
        var context = ProjectionContext();
        // 两个实际入口分别计算，不能以首个结果作为第二个结果的期望全集。
        var root = reader.DescribeProjection(context, "asset");
        // 目标同样需要原发布的完整闭包。
        var target = reader.DescribeProjection(context, "target");
        Assert.AreEqual(22, root.FieldRefs.Length);
        Assert.AreEqual(2, root.ObjectRefs.Length);
        CollectionAssert.AreEqual(root.FieldRefs, target.FieldRefs);
        Assert.IsTrue(root.FieldRefs.Contains("CaseOwner/OmqTarget/11/OBSERVED_TS"));
        Assert.IsTrue(root.FieldRefs.Contains("PRODUCTION/OMQ_ENTITY/1/ROW_ID"));
        // 历史单表映射仍保留十一列资格。
        var single = context with { Manifest = context.Manifest with { Mapping = context.Manifest.Mapping with
            { Entities = [context.Manifest.Mapping.Entities[0]] } } };
        Assert.AreEqual(11, reader.DescribeProjection(single, "asset").FieldRefs.Length);
        // 请求根实体时也必须核目标完整目录，不能把缺字段隐藏在尚未读的分支。
        var changed = context.CurrentCatalog.Objects.ToArray();
        changed[1] = changed[1] with { Fields = changed[1].Fields.Take(10).ToArray() };
        Assert.Throws<SemanticOperationException>(() => reader.DescribeProjection(context with
            { CurrentCatalog = context.CurrentCatalog with { Objects = changed } }, "asset"));
    }

    /// <summary>只为纯投影入口构造独立合同材料，不冒充正式发布或源执行。</summary>
    private static G4QueryBindingContext ProjectionContext()
    {
        // 根表精确形状来自本测试的独立清单。
        var entity = Entity();
        // 目标表保留大小写和异标度键声明。
        var target = entity with { Schema = "CaseOwner", Name = "OmqTarget", Fields = entity.Fields.Select(field => field.Name == "JOIN_KEY"
            ? field with { Precision = 13, Scale = 2 } : field).ToArray() };
        // 唯一合成组织和厂区。
        var scope = new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a"] };
        // 两表共享同一快照身份，当前与原始字节一致。
        var catalog = new CatalogSnapshotView { SnapshotId = "catalog", ConnectionId = "oracle", ConfigRevision = 1, SecretVersion = 1,
            Scope = scope, SchemaFingerprint = new string('a', 64), CapturedAtUtc = DateTimeOffset.UnixEpoch, Status = "READY", Objects = [entity, target] };
        // 投影只需要实体范围字段；其余独立规则不在此测试中伪造通过。
        var entities = catalog.Objects.Select((table, index) =>
        {
            // 每个实体必须绑定各自大小写敏感的物理对象。
            var dataset = new MappingDatasetRef { SnapshotId = "catalog", Schema = table.Schema, Name = table.Name, Kind = "TABLE" };
            return new MappingEntityBinding { Id = index == 0 ? "asset" : "target", EntityClassIri = "urn:test:Entity", DatasetRef = dataset,
                IdentitySpecId = "identity", TemporalSpecId = "time", ScopeFields = new MappingScopeFields
                { Organization = new MappingFieldRef { DatasetRef = dataset, Name = "ORG_ID", Ordinal = 4 },
                  Site = new MappingFieldRef { DatasetRef = dataset, Name = "SITE_ID", Ordinal = 5 } } };
        }).ToArray();
        // 发布身份仅是纯规则测试值，不进入任何数据库。
        var binding = new MappingVersionBinding { SourceConnectionId = "oracle", ConnectionRevision = 1, ConfigHash = new string('a',64),
            SourceType = "ORACLE", SourceCatalogSnapshotId = "catalog", SourceCatalogFingerprint = catalog.SchemaFingerprint,
            OntologyReleaseId = "ontology", OntologyManifestHash = new string('b',64), MappingHash = new string('c',64), ValidationHash = new string('d',64),
            ImpactHash = new string('e',64), AssessmentId = "assessment", AdapterVersion = "oracle-mapping-v1", ExecutorVersion = "oracle-mapping-validator-v1",
            CanonicalVersion = "mapping-c14n-v1", SecretVersion = 1, AuthorizationEpoch = 1 };
        return new G4QueryBindingContext { Scope = scope, OriginalCatalog = catalog, CurrentCatalog = catalog,
            Binding = new G4QueryBinding { MappingId = "mapping", MappingReleaseId = "release", ManifestHash = new string('f',64),
                OriginalCatalogSnapshotId = "catalog", OriginalCatalogFingerprint = catalog.SchemaFingerprint, CurrentCatalogSnapshotId = "catalog",
                CurrentCatalogFingerprint = catalog.SchemaFingerprint, ActivationId = "activation", ActivationRevision = "1", ConnectionId = "oracle",
                ConnectionRevision = "1", ConfigHash = binding.ConfigHash, SecretVersion = "1", OntologyReleaseId = "ontology", AuthorizationEpoch = "1", CapabilityVersion = new string('a',64) },
            Manifest = new MappingReleaseManifest { SchemaVersion = "g4.mapping.v1", MappingReleaseId = "release", MappingId = "mapping", Scope = scope,
                OriginDraftId = "draft", OriginDraftRevision = 1, Binding = binding, CreatedAtUtc = DateTimeOffset.UnixEpoch,
                Mapping = new MappingDefinition { Entities = entities, IdentitySpecs = [], TemporalSpecs = [], Properties = [], Relations = [], Conversions = [], UnitSpecs = [] },
                ReviewReceipt = new MappingReviewReceipt { ProposalId = "proposal", BindingHash = new string('a',64), SubmittedBy = "author", DecidedBy = "reviewer", DecidedAtUtc = DateTimeOffset.UnixEpoch } } };
    }

    /// <summary>完整身份集合拒绝交叠重复，半开接壤历史仍合法。</summary>
    [TestMethod]
    public void CompleteIdentityRejectsHiddenOverlappingVersions()
    {
        // 同业务身份的两行覆盖不同但交叠的窗口。
        var first = IntegrityRow("1", "same", "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z");
        // 第二行不会因请求先筛掉而免除完整性检查。
        var overlap = IntegrityRow("2", "same", "2026-01-15T00:00:00Z", "2026-03-01T00:00:00Z");
        Assert.AreEqual("query_source_indeterminate", Assert.Throws<SemanticOperationException>(() =>
            OracleQueryReader.DemandCompleteIdentity([first, overlap])).Code);
        overlap["FROM_TS"] = new G4UtcValue { Lexical = "2026-02-01T00:00:00Z" };
        OracleQueryReader.DemandCompleteIdentity([first, overlap]);
        overlap["FROM_TS"] = first["FROM_TS"];
        overlap["TO_TS"] = first["TO_TS"];
        Assert.Throws<SemanticOperationException>(() => OracleQueryReader.DemandCompleteIdentity([first, overlap]));
    }

    /// <summary>另一外部号的父项不能被根过滤隐藏；不存在目标或父区间接壤则不误报。</summary>
    [TestMethod]
    public void CompleteParentSetRejectsHiddenCardinalityConflict()
    {
        // 两个独立业务父身份具有相同关系键。
        var first = IntegrityRow("1", "parent-one", "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z");
        // 第二父行没有进入请求的根投影，但必须参加目标基数验证。
        var hidden = IntegrityRow("3", "parent-two", "2026-01-15T00:00:00Z", "2026-03-01T00:00:00Z");
        // 目标同时覆盖两父项的交叠时间。
        var target = IntegrityRow("2", "target", "2026-01-01T00:00:00Z", "2026-03-01T00:00:00Z", true);
        Assert.AreEqual("query_source_indeterminate", Assert.Throws<SemanticOperationException>(() => OracleQueryReader.DemandRelationIntegrity([first, hidden], [target])).Code);
        OracleQueryReader.DemandRelationIntegrity([first, hidden], []);
        hidden["FROM_TS"] = first["TO_TS"];
        OracleQueryReader.DemandRelationIntegrity([first, hidden], [target]);
    }

    /// <summary>十个不同目标为合法控制，第十一条使整分支拒绝而非截掉多余边。</summary>
    [TestMethod]
    public void FanoutRequiresTheCompleteTargetSet()
    {
        // 单一父项覆盖所有目标的有效期。
        var parent = IntegrityRow("1", "parent", "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z");
        // 每个目标均是独立身份，不能由重复身份异常替代扇出判定。
        var targets = Enumerable.Range(2, 11).Select(index => IntegrityRow(index.ToString(System.Globalization.CultureInfo.InvariantCulture),
            "target-" + index, "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z", true)).ToArray();
        OracleQueryReader.DemandRelationIntegrity([parent], targets.Take(10).ToArray());
        Assert.AreEqual("query_source_budget_exhausted", Assert.Throws<SemanticOperationException>(() =>
            OracleQueryReader.DemandRelationIntegrity([parent], targets)).Code);
    }

    /// <summary>完整性材料仅在服务端内存传递，不改变已有结果规范字节。</summary>
    [TestMethod]
    public void IntegrityRowsNeverEnterPublicSerialization()
    {
        // 序列化测试用同一只读回执逐项增加内部材料。
        var read = new G4SourceQueryRead { EntityBindingId = "asset", Rows = [], RecordKeyFields = ["ROW_ID"],
            StartedAtUtc = DateTimeOffset.UnixEpoch, CompletedAtUtc = DateTimeOffset.UnixEpoch,
            AdapterVersion = "oracle-query-v1", WatermarkKind = "UNKNOWN", Watermark = null, Indeterminate = false, Limited = false, QueryPlanHash = "plan" };
        CollectionAssert.AreEqual(MappingCanonical.Serialize(read), MappingCanonical.Serialize(read with
        { OracleIntegrityRows = [IntegrityRow("1", "internal", "2026-01-01T00:00:00Z", "2026-02-01T00:00:00Z")] }));
    }

    /// <summary>构造带物理键和业务身份的完整性规则输入，数值等值不依赖浮点。</summary>
    private static Dictionary<string, G4QueryValue> IntegrityRow(string key, string external, string from, string to, bool target = false)
    {
        // 原精确关系输入加上独立身份，不调用被测完整性算法构造预期。
        var row = Row(target ? "1.00" : "1.0", target ? 13 : 12, target ? 2 : 1, from, to);
        row["ROW_ID"] = new G4Int64Value { Lexical = key };
        row["EXT_ID"] = new G4StringValue { Lexical = external };
        return row;
    }

    /// <summary>构造最小输入行，保持数字类型与声明，与 Oracle 物理行键无关。</summary>
    private static Dictionary<string, G4QueryValue> Row(string number, int precision, int scale, string from, string to) =>
        new(StringComparer.Ordinal)
        {
            ["JOIN_KEY"] = new G4DecimalValue { Precision = precision, Scale = scale, Lexical = number },
            ["ORG_ID"] = new G4StringValue { Lexical = "org-demo" }, ["SITE_ID"] = new G4StringValue { Lexical = "site-a" },
            ["FROM_TS"] = new G4UtcValue { Lexical = from }, ["TO_TS"] = new G4UtcValue { Lexical = to }
        };

    /// <summary>由测试自身依照已冻结 DDL 构造 Oracle 原始目录；生产验证器仍独立核对。</summary>
    private static CatalogObject Entity()
    {
        // 名称和顺序由原始 DDL 固定，不从被测实现读取。
        string[] names = ["ROW_ID", "JOIN_KEY", "VAL", "ORG_ID", "SITE_ID", "EXT_ID", "LABEL", "FROM_TS", "TO_TS", "EVENT_TS", "OBSERVED_TS"];
        return new CatalogObject { Schema = "PRODUCTION", Name = "OMQ_ENTITY", Kind = "TABLE", Fields = names.Select((name, i) => new CatalogField
        {
            Name = name, Ordinal = i + 1, NativeType = i < 3 ? "NUMBER" : i < 7 ? "VARCHAR2" : "TIMESTAMP(6)", Nullable = i is 1 or 2 or 6,
            Precision = i switch { 0 => 18, 1 => 12, 2 => 28, _ => null }, Scale = i switch { 0 => 0, 1 => 1, 2 or > 6 => 6, _ => null },
            OracleMetadata = new OracleColumnMetadata { DataTypeOwner = null, SupportStatus = "SUPPORTED", TimeZoneKind = "NONE",
                CharLength = i is >= 3 and <= 6 ? (i == 6 ? 48 : 32) : null, CharSemantics = i is >= 3 and <= 6 ? "CHAR" : null,
                ByteLength = i is >= 3 and <= 6 ? (i == 6 ? 192 : 128) : null, FractionalSecondsPrecision = i > 6 ? 6 : null }
        }).ToArray() };
    }
}
