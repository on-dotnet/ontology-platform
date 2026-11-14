using System.Text;
using Microsoft.EntityFrameworkCore;
using System.Text.Json;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>映射字节与不可变身份的确定性回归。</summary>
[TestClass]
public sealed class G4MappingTests
{
    /// <summary>对象键和集合重排不改变身份，业务键顺序不可交换。</summary>
    [TestMethod]
    public void CanonicalSetsAndOrderedKeysHaveDifferentSemantics()
    {
        Assert.AreEqual(Hash("{\"b\":1,\"a\":null}"), Hash("{\"a\":null,\"b\":1}"));
        Assert.AreEqual(Hash("{\"siteIds\":[\"B\",\"A\"]}"), Hash("{\"siteIds\":[\"A\",\"B\"]}"));
        Assert.AreNotEqual(Hash("{\"externalIdFieldRefs\":[\"A\",\"B\"]}"), Hash("{\"externalIdFieldRefs\":[\"B\",\"A\"]}"));
        Assert.AreNotEqual(Hash("{\"a\":null}"), Hash("{}"));
        Assert.AreNotEqual(Hash("{\"a\":\"é\"}"), Hash("{\"a\":\"é\"}"));
    }

    /// <summary>重复集合、浮点和重复键不得产生貌似可信的canonical。</summary>
    [TestMethod]
    public void CanonicalRejectsAmbiguousNumbersAndDuplicates()
    {
        foreach (var raw in new[] { "{\"a\":1.0}", "{\"a\":-0}", "{\"a\":1,\"a\":2}", "{\"siteIds\":[\"A\",\"A\"]}" })
        {
            Assert.Throws<SemanticOperationException>(() => Hash(raw));
        }
    }

    /// <summary>控制字符统一编码且UTF8无BOM和尾换行。</summary>
    [TestMethod]
    public void CanonicalPreservesUnicodeAndEscapesControlCharacters()
    {
        // JSON控制字符按合同固定四位小写转义。
        using var document = G4MappingRules.ReadDocument("{\"x\":\"é\\n/\"}");
        Assert.AreEqual("{\"x\":\"é\\u000a/\"}", Encoding.UTF8.GetString(MappingCanonical.Bytes(document.RootElement)));
    }

    /// <summary>映射正式历史与Active必须分表，CAS和唯一提案保证在模型中显式存在。</summary>
    [TestMethod]
    public void MappingPersistenceHasSeparateHistoryAndCas()
    {
        // 仅检查EF模型；真实不可变触发器和竞态须另在PG执行。
        using var database = new ConnectionsDbContext(new DbContextOptionsBuilder<ConnectionsDbContext>()
            .UseNpgsql("Host=127.0.0.1;Database=unused;Username=unused;Password=unused").Options);
        // 未连接数据库，模型必须已包含正式发布实体。
        var release = database.Model.FindEntityType(typeof(MappingReleaseRecord));
        Assert.IsNotNull(release);
        Assert.AreEqual("connections", release.GetSchema());
        Assert.AreEqual("bytea", release.FindProperty(nameof(MappingReleaseRecord.CanonicalBytes))!.GetColumnType());
        Assert.IsTrue(database.Model.FindEntityType(typeof(MappingActiveRecord))!
            .FindProperty(nameof(MappingActiveRecord.ActivationRevision))!.IsConcurrencyToken);
        Assert.IsTrue(database.Model.FindEntityType(typeof(MappingActivationRecord))!.GetIndexes()
            .Any(index => index.IsUnique && index.Properties.Single().Name == "ProposalId"));
    }

    /// <summary>纯转换必须可逆且明确精度，不接受四舍五入或自由表达式。</summary>
    [TestMethod]
    public void RegisteredConversionsPreserveValuesAndRejectLoss()
    {
        // 转换实例固定版本和封闭参数。
        var kelvin = new MappingConversion { Id = "conversion", RegisteredId = "celsius-to-kelvin", Version = "1", Parameters = JsonSerializer.SerializeToElement(new { }) };
        // 单位证据由完整评估另验，此测试只验证精确转换本身。
        var source = new MappingSourceCell { NativeType = "numeric(12,4)", Value = "20.125" };
        Assert.AreEqual("293.275", MappingValidationService.ConvertValue(source, kelvin));
        Assert.IsNull(MappingValidationService.ConvertValue(source with { Value = null }, kelvin));
        // 不允许以目标scale为由把源值静默舍入。
        var scale = kelvin with { RegisteredId = "decimal-scale-exact", Parameters = JsonSerializer.SerializeToElement(new { scale = 2 }) };
        Assert.Throws<SemanticOperationException>(() => MappingValidationService.ConvertValue(source, scale));
        Assert.AreEqual("20.12", MappingValidationService.ConvertValue(source with { Value = "20.12" }, scale));
        Assert.Throws<SemanticOperationException>(() => MappingValidationService.ConvertValue(source, kelvin with { RegisteredId = "eval" }));
    }

    /// <summary>JSON只允许固定顶层scalar，不读取嵌套路径或猜测null。</summary>
    [TestMethod]
    public void JsonConversionRequiresExactTopLevelKeyAndType()
    {
        // 注册转换只访问明确键，不解释JSONPath或表达式。
        var conversion = new MappingConversion { Id = "json", RegisteredId = "json-top-level-scalar", Version = "1", Parameters = JsonSerializer.SerializeToElement(new { key = "quality", valueType = "STRING" }) };
        // 只将对应scalar交给纯转换，其他对象不成为模型指令。
        var source = new MappingSourceCell { NativeType = "jsonb", Value = "{\"quality\":\"good\"}" };
        Assert.AreEqual("good", MappingValidationService.ConvertValue(source, conversion));
        Assert.Throws<SemanticOperationException>(() => MappingValidationService.ConvertValue(source with { Value = "{\"quality\":{\"value\":\"good\"}}" }, conversion));
        Assert.Throws<SemanticOperationException>(() => MappingValidationService.ConvertValue(source with { Value = "{}" }, conversion));
    }

    /// <summary>空样本或未证明授权不得伪造七项PASS。</summary>
    [TestMethod]
    public void SevenStagesNeverInferEvidenceFromEmptyInput()
    {
        // 此用例只检验失败关闭，不把内存合成对象称为真实源验收。
        var scope = new ResourceScope { OrganizationId = "org", SiteIds = ["A"] };
        // 未观测源没有安全证明和事务身份。
        var source = new MappingSourceObservation
        {
            Tables = [],
            CatalogFingerprint = new string('a', 64),
            TransactionSnapshot = "unobserved",
            StartedAtUtc = DateTimeOffset.UtcNow,
            FinishedAtUtc = DateTimeOffset.UtcNow,
            SecurityVerified = false
        };
        // 空词汇不得提供类、属性、身份或单位的存在性证明。
        var ontology = new VocabularySnapshot { Triples = [], Diagnostics = [] };
        // 空定义由形状守卫拒绝，不能编造默认映射。
        var mapping = new MappingDefinition { Entities = [], Properties = [], Relations = [], IdentitySpecs = [], TemporalSpecs = [], Conversions = [], UnitSpecs = [] };
        Assert.Throws<SemanticOperationException>(() => MappingValidationService.Evaluate(mapping, source, ontology, scope, false, false, new string('b', 64)));
    }

    /// <summary>七阶段正例保留跨厂同号并区分语义不变量与新观察证据。</summary>
    [TestMethod]
    public void CompleteEvaluationPreservesScopeAndSeparatesObservationHash()
    {
        // 纯评估夹具不代替真实PG与G3集成验收。
        var (definition, source, ontology, scope) = EvaluationFixture();
        // 首轮完整的声明与样本应使七阶段全部通过。
        var first = MappingValidationService.Evaluate(definition, source, ontology, scope, true, true, new string('b', 64));
        Assert.IsTrue(first.Passed, string.Join(",", first.Issues.Select(issue => issue.Code)));
        // 新观察可以变化业务值与事务身份，但不能暗改数量或范围。
        var changedRows = source.Tables[0].Rows.Select(row => new Dictionary<string, MappingSourceCell>(row)
        { ["value"] = row["value"] with { Value = "new value" } }).ToArray();
        // 固定身份和声明不变，只换真实观察负载。
        var second = MappingValidationService.Evaluate(definition, source with
        {
            TransactionSnapshot = "new-transaction",
            Tables = [source.Tables[0] with { Rows = changedRows }]
        }, ontology, scope, true, true, new string('b', 64));
        Assert.IsTrue(second.Passed);
        Assert.AreEqual(first.SemanticResultHash, second.SemanticResultHash);
        Assert.AreNotEqual(first.EvidenceHash, second.EvidenceHash);
    }

    /// <summary>不能把源text静默写成声明boolean，目标range必须实际匹配。</summary>
    [TestMethod]
    public void EvaluationRejectsTargetDatatypeMismatch()
    {
        // 非boolean文本不可因为属性IRI存在就通过SCHEMA。
        var (definition, source, ontology, scope) = EvaluationFixture();
        // 仅修改正式range，实际源值仍为普通文字。
        var triples = ontology.Triples.Select(item => item.Triple.Predicate == "http://www.w3.org/2000/01/rdf-schema#range"
            ? item with { Triple = item.Triple with { Object = item.Triple.Object with { Value = "http://www.w3.org/2001/XMLSchema#boolean" } } } : item).ToArray();
        // 必须明确阻断，不能返回七PASS。
        var result = MappingValidationService.Evaluate(definition, source, ontology with { Triples = triples }, scope, true, true, new string('b', 64));
        Assert.IsFalse(result.Passed);
        Assert.IsTrue(result.Issues.Any(issue => issue.Code == "mapping_target_datatype_mismatch"));
    }

    /// <summary>关系键未知不能被解释成有效的零条关系。</summary>
    [TestMethod]
    public void EvaluationRejectsUnknownRelationEndpoint()
    {
        // 自连接使用独立的关联列，避免身份列null先遮蔽本用例。
        var (definition, source, ontology, scope) = EvaluationFixture();
        // 固定字段引用与已登记数据集一致。
        var field = definition.Properties[0].FieldRef with { Name = "link", Ordinal = 8 };
        // null关系键明确表示未知，不是已证明没有关系。
        var relation = new MappingRelationBinding
        {
            Id = "link",
            FromBindingId = "entity",
            ToBindingId = "entity",
            PredicateIri = "urn:test:related",
            Cardinality = "MANY_TO_MANY",
            TemporalJoinPolicy = "HALF_OPEN_OVERLAP",
            JoinFieldPairs = [new MappingJoinFieldPair { From = field, To = field }]
        };
        // 已知的正式关系类型不能替代源端点证据。
        var vocabulary = ontology with
        {
            Triples = [.. ontology.Triples, Triple("urn:test:related", "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", "http://www.w3.org/2002/07/owl#ObjectProperty"),
            Triple("urn:test:related", "http://www.w3.org/2000/01/rdf-schema#domain", "urn:test:Entity"),
            Triple("urn:test:related", "http://www.w3.org/2000/01/rdf-schema#range", "urn:test:Entity")]
        };
        // 任一未知端点都阻断而不是静默丢行。
        var result = MappingValidationService.Evaluate(definition with { Relations = [relation] }, source, vocabulary, scope, true, true, new string('b', 64));
        Assert.IsFalse(result.Passed);
        Assert.IsTrue(result.Issues.Any(issue => issue.Code == "mapping_relation_endpoint_unknown"));
    }

    /// <summary>相邻半开历史关系允许一对多，真实重叠的起点才构成基数冲突。</summary>
    [TestMethod]
    public void HistoricalCardinalityUsesOverlappingIntervals()
    {
        // 基础源只有同厂一条，另外创建两段不相交的来源历史。
        var (definition, source, ontology, scope) = EvaluationFixture();
        // 关系目标使用独立表，避免将相同目标重复展开成两个实体。
        var dataset = definition.Entities[0].DatasetRef with { Name = "target" };
        // 复制字段身份只修改明确目标数据集。
        MappingFieldRef Target(MappingFieldRef field) => field with { DatasetRef = dataset };
        // 当前目标身份覆盖整个年度。
        var identity = definition.IdentitySpecs[0];
        // 时间策略同源，字段引用重新绑定目标表。
        var time = definition.TemporalSpecs[0];
        // 两段历史来源业务号不同，关联键一致。
        var first = new Dictionary<string, MappingSourceCell>(source.Tables[0].Rows[0])
        {
            ["to"] = source.Tables[0].Rows[0]["to"] with { Value = "2026-07-01T00:00:00.0000000Z" },
            ["link"] = new() { NativeType = "text", Value = "target" }
        };
        // 右边段从左边段终点开始，半开语义没有交叠。
        var second = new Dictionary<string, MappingSourceCell>(source.Tables[0].Rows[0])
        {
            ["from"] = first["from"] with { Value = "2026-07-01T00:00:00.0000000Z" },
            ["id"] = first["id"] with { Value = "second" },
            ["link"] = first["link"]
        };
        // 唯一目标行覆盖两个合法相邻关系窗口。
        var target = new Dictionary<string, MappingSourceCell>(source.Tables[0].Rows[0]) { ["link"] = first["link"] };
        // 目标定义的域与时间皆使用独立明确引用。
        var model = definition with
        {
            Entities = [.. definition.Entities, definition.Entities[0] with { Id = "target", DatasetRef = dataset,
                IdentitySpecId = "target-identity", TemporalSpecId = "target-time",
                ScopeFields = new MappingScopeFields { Organization = Target(identity.OrganizationFieldRef), Site = Target(identity.SiteFieldRef) } }],
            IdentitySpecs = [identity, identity with { Id = "target-identity", OrganizationFieldRef = Target(identity.OrganizationFieldRef),
                SiteFieldRef = Target(identity.SiteFieldRef), ExternalIdFieldRefs = identity.ExternalIdFieldRefs.Select(Target).ToArray(),
                ValidFromFieldRef = Target(identity.ValidFromFieldRef!), ValidToFieldRef = Target(identity.ValidToFieldRef!) }],
            TemporalSpecs = [time, time with { Id = "target-time", EventTimeFieldRef = Target(time.EventTimeFieldRef!), ObservedAtFieldRef = Target(time.ObservedAtFieldRef!),
                ValidFromFieldRef = Target(time.ValidFromFieldRef!), ValidToFieldRef = Target(time.ValidToFieldRef!) }],
            Relations = [new MappingRelationBinding { Id = "related", FromBindingId = "entity", ToBindingId = "target", PredicateIri = "urn:test:related",
                Cardinality = "ONE_TO_MANY", TemporalJoinPolicy = "HALF_OPEN_OVERLAP", JoinFieldPairs = [new MappingJoinFieldPair {
                    From = identity.OrganizationFieldRef with { Name = "link", Ordinal = 8 }, To = Target(identity.OrganizationFieldRef) with { Name = "link", Ordinal = 8 } }] }]
        };
        // 正式关系类型声明与纯算法测试输入显式区分。
        var vocabulary = ontology with
        {
            Triples = [.. ontology.Triples, Triple("urn:test:related", "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", "http://www.w3.org/2002/07/owl#ObjectProperty"),
            Triple("urn:test:related", "http://www.w3.org/2000/01/rdf-schema#domain", "urn:test:Entity"),
            Triple("urn:test:related", "http://www.w3.org/2000/01/rdf-schema#range", "urn:test:Entity")]
        };
        // 两段不相交的历史，任一瞬间只有一个起点。
        var observed = source with { Tables = [source.Tables[0] with { Rows = [first, second] }, new MappingSourceTable { Dataset = dataset, Rows = [target] }] };
        // 相邻不能被全部pairs计数误拒绝。
        var adjacent = MappingValidationService.Evaluate(model, observed, vocabulary, scope, true, true, new string('b', 64));
        Assert.IsTrue(adjacent.Passed, string.Join(",", adjacent.Issues.Select(issue => issue.Code)));
        // 不匹配或多值的正式域和值域不能因关联键恰好相等而放行。
        foreach (var predicate in new[] { "domain", "range" })
        {
            // 原明确声明加一个相异IRI，证明多值不能任取第一项。
            var ambiguous = vocabulary with
            {
                Triples = [.. vocabulary.Triples,
                Triple("urn:test:related", "http://www.w3.org/2000/01/rdf-schema#" + predicate, "urn:test:Other")]
            };
            // 复用完全相同的真实语义输入，仅词汇域和值域发生变化。
            var invalid = MappingValidationService.Evaluate(model, observed, ambiguous, scope, true, true, new string('b', 64));
            Assert.IsFalse(invalid.Passed);
            Assert.IsTrue(invalid.Issues.Any(issue => issue.Code == "mapping_relation_" + predicate + "_unknown"));
        }
        second["from"] = second["from"] with { Value = "2026-06-01T00:00:00.0000000Z" };
        // 同一目标在六月有两个起点，必须拒绝。
        var overlap = MappingValidationService.Evaluate(model, observed, vocabulary, scope, true, true, new string('b', 64));
        Assert.IsFalse(overlap.Passed);
        Assert.IsTrue(overlap.Issues.Any(issue => issue.Code == "mapping_cardinality_conflict"));
    }

    /// <summary>目录保留的varchar长度和timestamp精度不改变其明确XSD标量类型。</summary>
    [TestMethod]
    public void ParameterizedSourceTypesRetainDeclaredDatatype()
    {
        // 仅替换实际标量类型，其他身份和固定词汇保持相同。
        var (definition, source, ontology, scope) = EvaluationFixture();
        foreach (var row in source.Tables[0].Rows)
        {
            row["value"] = row["value"] with { NativeType = "character varying(20)" };
        }
        Assert.IsTrue(MappingValidationService.Evaluate(definition, source, ontology, scope, true, true, new string('b', 64)).Passed);
        foreach (var row in source.Tables[0].Rows)
        {
            row["value"] = row["from"] with { NativeType = "timestamp(3) with time zone" };
        }
        // 唯一range必须明确改为dateTime，不能自动猜测或进行文本转换。
        var dates = ontology with
        {
            Triples = [.. ontology.Triples.Where(item => item.Triple.Predicate != "http://www.w3.org/2000/01/rdf-schema#range"),
            Triple("urn:test:label", "http://www.w3.org/2000/01/rdf-schema#range", "http://www.w3.org/2001/XMLSchema#dateTime")]
        };
        Assert.IsTrue(MappingValidationService.Evaluate(definition, source, dates, scope, true, true, new string('b', 64)).Passed);
    }

    /// <summary>确定性候选有明确来源，重复匹配和单位属性不能进入低风险批采纳。</summary>
    [TestMethod]
    public void DeterministicCandidatesNeverImplyValidationOrApproval()
    {
        // 固定目录只有一个同名text字段，草稿尚未人工绑定属性。
        var (definition, _, ontology, scope) = EvaluationFixture();
        // 元数据名称匹配不读取样本。
        var catalog = new CatalogSnapshotView
        {
            SnapshotId = "snapshot",
            ConnectionId = "source",
            ConfigRevision = 1,
            SecretVersion = 1,
            Scope = scope,
            SchemaFingerprint = new string('a', 64),
            CapturedAtUtc = DateTimeOffset.UtcNow,
            Status = "READY",
            Objects = [new CatalogObject { Schema = "production", Name = "readings", Kind = "TABLE", Fields = [new CatalogField { Name = "label", Ordinal = 9, NativeType = "text", Nullable = false, Precision = null, Scale = null }] }]
        };
        // 没有属性的定义仍具有完整实体身份与时间。
        var draft = definition with { Properties = [] };
        // 单一同名直接字符串可以由用户显式采纳，但仍无实样验证。
        var result = MappingValidationService.Suggest(draft, catalog, catalog, ontology, 3);
        Assert.AreEqual(3, result.Revision);
        Assert.HasCount(1, result.Candidates);
        Assert.AreEqual("METADATA", result.Candidates[0].Evidence);
        Assert.AreEqual("CANDIDATE_ONLY", result.Candidates[0].Status);
        // 无名称匹配应如实返回空候选，不制造本体概念。
        var absent = catalog with { Objects = [catalog.Objects[0] with { Fields = [catalog.Objects[0].Fields[0] with { Name = "unknown" }] }] };
        Assert.IsEmpty(MappingValidationService.Suggest(draft, absent, absent, ontology, 3).Candidates);
        // 旧目录曾可见但当前目录已移除的未使用列，不能通过规则候选重新披露。
        // 同一原命令重放也必须拒绝已撤权字段，原回执不被裁剪后伪称成功。
        var reduced = MappingValidationService.Suggest(draft, catalog, absent, ontology, 3);
        Assert.IsEmpty(reduced.Candidates);
        Assert.AreEqual(403, Assert.Throws<SemanticOperationException>(() => MappingValidationService.DemandVisibleCandidates(result, reduced)).Status);
        MappingValidationService.DemandVisibleCandidates(result, result);
        // 同名但正式声明单位后必须转为逐项人工处理。
        var physical = ontology with
        {
            Triples = [.. ontology.Triples,
            Triple("urn:test:label", "urn:ontology-platform:semantics:nominalUnit", "urn:test:Unit")]
        };
        Assert.AreEqual("TERM", MappingValidationService.Suggest(draft, catalog, catalog, physical, 3).Candidates.Single().Evidence);
        // 已有绑定不会被候选覆盖。
        var bound = definition with { Properties = [definition.Properties[0] with { FieldRef = definition.Properties[0].FieldRef with { Name = "label", Ordinal = 9 } }] };
        Assert.IsEmpty(MappingValidationService.Suggest(bound, catalog, catalog, ontology, 3).Candidates);
    }

    /// <summary>JSON允许显式null进入必填引用时仍返回400，注册参数类型错误也不能变成500。</summary>
    [TestMethod]
    public void MalformedReferencesAndScaleAreSafeClientErrors()
    {
        // 从合法定义只修改一处引用，准确覆盖字典null键和JsonElement类型异常。
        var definition = EvaluationFixture().Definition;
        // 每个负例必须由公共规则稳定分类，不能泄漏实现异常。
        var cases = new[]
        {
            definition with { Entities = [definition.Entities[0] with { IdentitySpecId = null! }] },
            definition with { Entities = [definition.Entities[0] with { TemporalSpecId = null! }] },
            definition with { Properties = [definition.Properties[0] with { EntityBindingId = null! }] },
            definition with { Conversions = [new MappingConversion { Id = "scale", RegisteredId = "decimal-scale-exact", Version = "1",
                Parameters = JsonSerializer.SerializeToElement(new { scale = "2" }) }] }
        };
        foreach (var candidate in cases)
        {
            // 失败闭合为明确载荷错误，禁止NullReference/ArgumentNull/InvalidOperation向Host逃逸。
            var failure = Assert.Throws<SemanticOperationException>(() => G4MappingRules.Definition(candidate));
            Assert.AreEqual(400, failure.Status);
        }
    }

    /// <summary>完整内存样本专用于纯算法回归，不构成真实G3发布证据。</summary>
    private static (MappingDefinition Definition, MappingSourceObservation Source, VocabularySnapshot Ontology, ResourceScope Scope) EvaluationFixture()
    {
        // 同一业务号在不同厂区不应误判重叠身份。
        var scope = new ResourceScope { OrganizationId = "org", SiteIds = ["A", "B"] };
        // 字段引用全部属于同一个明确目录表。
        var dataset = new MappingDatasetRef { SnapshotId = "snapshot", Schema = "production", Name = "readings", Kind = "TABLE" };
        // 固定组织列作为后续字段引用的基底。
        var org = new MappingFieldRef { DatasetRef = dataset, Name = "org", Ordinal = 1 };
        // 厂区与时间端点必须显式存在。
        var site = org with { Name = "site", Ordinal = 2 };
        // 半开起点以UTC源时间表示。
        var from = org with { Name = "from", Ordinal = 4 };
        // 半开终点不借助系统当前时间。
        var to = org with { Name = "to", Ordinal = 5 };
        // 身份与时间均使用实际行中独立命名字段。
        var definition = new MappingDefinition
        {
            Entities = [new MappingEntityBinding { Id = "entity", EntityClassIri = "urn:test:Entity", DatasetRef = dataset,
                IdentitySpecId = "identity", TemporalSpecId = "time", ScopeFields = new MappingScopeFields { Organization = org, Site = site } }],
            IdentitySpecs = [new MappingIdentitySpec { Id = "identity", OrganizationFieldRef = org, SiteFieldRef = site,
                SourceNamespace = "fixture", ExternalIdFieldRefs = [org with { Name = "id", Ordinal = 3 }], ValidFromFieldRef = from, ValidToFieldRef = to }],
            TemporalSpecs = [new MappingTemporalSpec { Id = "time", EventTimeFieldRef = from, ObservedAtFieldRef = from,
                ValidFromFieldRef = from, ValidToFieldRef = to, TimezonePolicy = new MappingTimezonePolicy { Kind = "UTC", ZoneId = null }, Precision = "MICROSECOND" }],
            Properties = [new MappingPropertyBinding { Id = "property", EntityBindingId = "entity", PropertyIri = "urn:test:label",
                FieldRef = org with { Name = "value", Ordinal = 7 }, ConversionId = null, UnitSpecId = null, NullPolicy = "REJECT_NULL" }],
            Relations = [],
            UnitSpecs = [],
            Conversions = []
        };
        // 两个厂区各一条，业务号相同但scope不同。
        var rows = scope.SiteIds.Select(value => new Dictionary<string, MappingSourceCell>
        {
            ["org"] = new() { NativeType = "text", Value = "org" },
            ["site"] = new() { NativeType = "text", Value = value },
            ["id"] = new() { NativeType = "text", Value = "same-id" },
            ["value"] = new() { NativeType = "text", Value = "sample" },
            ["from"] = new() { NativeType = "timestamp with time zone", Value = "2026-01-01T00:00:00.0000000Z" },
            ["to"] = new() { NativeType = "timestamp with time zone", Value = "2027-01-01T00:00:00.0000000Z" },
            ["link"] = new() { NativeType = "text", Value = null }
        }).ToArray();
        // 固定观测时间使重复测试不依赖机器当前时刻。
        var now = DateTimeOffset.Parse("2026-11-14T00:00:00Z", System.Globalization.CultureInfo.InvariantCulture);
        // 合成已授权标志只在纯函数测试内部使用。
        var source = new MappingSourceObservation
        {
            Tables = [new MappingSourceTable { Dataset = dataset, Rows = rows }],
            CatalogFingerprint = new string('a', 64),
            TransactionSnapshot = "test",
            StartedAtUtc = now,
            FinishedAtUtc = now.AddSeconds(1),
            SecurityVerified = true
        };
        // 正式解析后的最小声明，生产服务必须另外核验发布原件。
        var ontology = new VocabularySnapshot
        {
            ReleaseId = "release",
            ManifestHash = new string('c', 64),
            ProfileVersion = "4",
            Triples = [
            Triple("urn:test:Entity", "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", "http://www.w3.org/2002/07/owl#Class"),
            Triple("urn:test:label", "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", "http://www.w3.org/2002/07/owl#DatatypeProperty"),
            Triple("urn:test:label", "http://www.w3.org/2000/01/rdf-schema#domain", "urn:test:Entity"),
            Triple("urn:test:label", "http://www.w3.org/2000/01/rdf-schema#range", "http://www.w3.org/2001/XMLSchema#string")],
            Diagnostics = []
        };
        return (definition, source, ontology, scope);
    }

    /// <summary>固定IRI三元组不会引入本地推理或自动造词汇。</summary>
    private static VocabularySourceTriple Triple(string subject, string predicate, string value) => new()
    {
        SourceId = "ontology",
        Triple = new RdfTriple
        {
            Subject = new RdfTerm { Kind = RdfTermKind.Iri, Value = subject },
            Predicate = predicate,
            Object = new RdfTerm { Kind = RdfTermKind.Iri, Value = value }
        }
    };

    /// <summary>以同一解析器产生规范化输入，避免测试自建算法。</summary>
    private static string Hash(string raw)
    {
        // 文档生命周期覆盖canonical执行。
        using var document = G4MappingRules.ReadDocument(raw);
        return MappingCanonical.Hash(document.RootElement);
    }
}
