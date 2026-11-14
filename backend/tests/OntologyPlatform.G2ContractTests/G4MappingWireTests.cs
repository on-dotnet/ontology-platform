using System.Text.Json;
using System.Text.Json.Nodes;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.G2ContractTests;

/// <summary>发布与回滚的严格传输边界，不替代真实源评估。</summary>
[TestClass]
public sealed class G4MappingWireTests
{
    /// <summary>两种合法分支必须可读取，回滚不依赖草稿。</summary>
    [TestMethod]
    public void PublishAndRollbackHaveSeparateRequiredTargets()
    {
        Assert.IsInstanceOfType<MappingPublishProposalRequest>(G4MappingRules.ReadProposal(Proposal("PUBLISH")));
        Assert.IsInstanceOfType<MappingRollbackProposalRequest>(G4MappingRules.ReadProposal(Proposal("ROLLBACK")));
    }

    /// <summary>字段混用、额外字段、空目标和缺失目标不能被静默吞掉。</summary>
    [TestMethod]
    public void MixedMissingNullAndUnknownFieldsAreRejected()
    {
        foreach (var change in new Action<JsonObject>[]
        {
            body => body["draftRevision"] = 9,
            body => body.Remove("targetReleaseId"),
            body => body["targetReleaseId"] = null,
            body => body["autoApprove"] = true,
            body => body["manifestHash"] = "sha256:synthetic",
            body => body["kind"] = "rollback"
        })
        {
            // 每个变异仅改变一个合同边界，其他输入保持合法。
            var body = JsonNode.Parse(Proposal("ROLLBACK"))!.AsObject();
            change(body);
            Assert.Throws<SemanticOperationException>(() => G4MappingRules.ReadProposal(body.ToJsonString()));
        }
    }

    /// <summary>重复键不能由JSON解析器最后值覆盖，从而改变审核目标。</summary>
    [TestMethod]
    public void DuplicateDiscriminatorAndNestedVersionAreRejected()
    {
        // 重复判别即便值相同也拒绝，避免不同消费者解析歧义。
        var duplicate = Proposal("PUBLISH").Replace("\"kind\":\"PUBLISH\"", "\"kind\":\"PUBLISH\",\"kind\":\"PUBLISH\"");
        Assert.Throws<SemanticOperationException>(() => G4MappingRules.ReadProposal(duplicate));
        // 嵌套版本也不得最后值获胜。
        var nested = Proposal("PUBLISH").Replace("\"secretVersion\":1", "\"secretVersion\":1,\"secretVersion\":2");
        Assert.Throws<SemanticOperationException>(() => G4MappingRules.ReadProposal(nested));
    }

    /// <summary>首次激活只允许null与0成对，防止不完整CAS。</summary>
    [TestMethod]
    public void ActivePointerRequiresBothIdentityAndMonotonicRevision()
    {
        // 固定合法发布命令，只改变指针配对。
        var body = JsonNode.Parse(Proposal("PUBLISH"))!.AsObject();
        body["expectedActive"]!["activationRevision"] = 1;
        Assert.Throws<SemanticOperationException>(() => G4MappingRules.ReadProposal(body.ToJsonString()));
    }

    /// <summary>映射时间始终以七位小数UTC Z输出，不能漂移为可变精度offset格式。</summary>
    [TestMethod]
    public void MappingUtcWireIsExactAndRejectsAlternateOffsets()
    {
        // 转换到UTC后仍保留固定七位小数，以便跨语言canonical一致。
        var instant = new DateTimeOffset(2026, 11, 14, 8, 0, 0, TimeSpan.FromHours(8));
        Assert.AreEqual("\"2026-11-14T00:00:00.0000000Z\"", JsonSerializer.Serialize(instant, G4MappingJson.Options));
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<DateTimeOffset>("\"2026-11-14T00:00:00+00:00\"", G4MappingJson.Options));
    }

    /// <summary>定义引用必须闭合，不能把未知转换或缺单位证据留到发布后。</summary>
    [TestMethod]
    public void DefinitionRejectsBrokenReferencesAndUnregisteredConversions()
    {
        // 最小完整定义仅证明合同结构，不冒充源验证。
        var mapping = Definition();
        G4MappingRules.Definition(mapping);
        Assert.Throws<SemanticOperationException>(() => G4MappingRules.Definition(mapping with { Entities = [] }));
        Assert.Throws<SemanticOperationException>(() => G4MappingRules.Definition(mapping with { IdentitySpecs = [] }));
        Assert.Throws<SemanticOperationException>(() => G4MappingRules.Definition(mapping with { Entities = [mapping.Entities[0], mapping.Entities[0]] }));
        Assert.Throws<SemanticOperationException>(() => G4MappingRules.Definition(mapping with
        {
            Conversions = [new MappingConversion { Id = "c", RegisteredId = "eval", Version = "1", Parameters = JsonSerializer.SerializeToElement(new { expression = "1" }) }]
        }));
        Assert.Throws<SemanticOperationException>(() => G4MappingRules.Definition(mapping with
        {
            TemporalSpecs = [mapping.TemporalSpecs[0] with { TimezonePolicy = new MappingTimezonePolicy { Kind = "UTC", ZoneId = "Asia/Shanghai" } }]
        }));
    }

    /// <summary>闭合定义使用同一个固定数据集和组织厂区字段。</summary>
    private static MappingDefinition Definition()
    {
        // 字段序号对应测试目录，不查询任何外部源。
        var dataset = new MappingDatasetRef { SnapshotId = "snapshot", Schema = "production", Name = "assets", Kind = "TABLE" };
        // 组织字段同时用于scope与身份，避免互相矛盾。
        var org = new MappingFieldRef { DatasetRef = dataset, Ordinal = 1, Name = "organization_id" };
        // 厂区字段不允许跨数据集引用。
        var site = org with { Ordinal = 2, Name = "site_id" };
        return new MappingDefinition
        {
            Entities = [new MappingEntityBinding { Id = "entity", EntityClassIri = "https://example.org/Asset", DatasetRef = dataset, IdentitySpecId = "identity", TemporalSpecId = "time", ScopeFields = new MappingScopeFields { Organization = org, Site = site } }],
            IdentitySpecs = [new MappingIdentitySpec { Id = "identity", OrganizationFieldRef = org, SiteFieldRef = site, SourceNamespace = "fixture", ExternalIdFieldRefs = [org with { Ordinal = 3, Name = "id" }], ValidFromFieldRef = null, ValidToFieldRef = null }],
            TemporalSpecs = [new MappingTemporalSpec { Id = "time", EventTimeFieldRef = null, ObservedAtFieldRef = null, ValidFromFieldRef = null, ValidToFieldRef = null, TimezonePolicy = new MappingTimezonePolicy { Kind = "UTC", ZoneId = null }, Precision = "MICROSECOND" }],
            Properties = [],
            Relations = [],
            Conversions = [],
            UnitSpecs = []
        };
    }

    /// <summary>合成请求覆盖完整固定输入，散列仅用于形状测试。</summary>
    private static string Proposal(string kind)
    {
        // 64位设计hash不冒充源运行或发布制品证据。
        var hash = new string('a', 64);
        // 固定版本组由测试创建，避免读取外部可变文档。
        var binding = new MappingVersionBinding
        {
            SourceConnectionId = "connection-demo",
            ConnectionRevision = 1,
            ConfigHash = hash,
            SourceType = "POSTGRESQL",
            SourceCatalogSnapshotId = "catalog-demo",
            SourceCatalogFingerprint = hash,
            OntologyReleaseId = "ontology-demo",
            OntologyManifestHash = hash,
            MappingHash = hash,
            ValidationHash = hash,
            ImpactHash = hash,
            AssessmentId = "assessment-demo",
            AdapterVersion = "pg-mapping-v1",
            ExecutorVersion = "mapping-validator-v1",
            CanonicalVersion = "mapping-c14n-v1",
            SecretVersion = 1,
            AuthorizationEpoch = 1
        };
        // 正例不在shape检查中依赖机器当前时间，期限由应用层当前时钟核验。
        var body = new JsonObject
        {
            ["kind"] = kind,
            ["schemaVersion"] = "g4.mapping.v1",
            ["scope"] = JsonSerializer.SerializeToNode(new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a"] }, G4MappingJson.Options),
            ["binding"] = JsonSerializer.SerializeToNode(binding, G4MappingJson.Options),
            ["expectedActive"] = new JsonObject { ["releaseId"] = kind == "PUBLISH" ? null : "release-current", ["activationRevision"] = kind == "PUBLISH" ? 0 : 2 },
            ["expiresAtUtc"] = "2026-11-14T08:15:00.0000000Z",
            ["command"] = JsonSerializer.SerializeToNode(new CommandContext { CommandId = "cmd-demo", IdempotencyKey = "idem-demo", ExpectedRevision = 0, Reason = "合同测试" }, G4MappingJson.Options)
        };
        if (kind == "PUBLISH")
        {
            body["draftId"] = "draft-demo";
            body["draftRevision"] = 1;
        }
        else
        {
            body["targetReleaseId"] = "release-old";
            body["manifestHash"] = hash;
        }
        return body.ToJsonString();
    }
}
