using System.Text.Json;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.G2ContractTests;

/// <summary>验证不可信JSON无法绕过共享枚举与持久事件判别边界。</summary>
[TestClass]
public sealed class WireContractTests
{
    /// <summary>数值枚举既不能表示隐藏状态，也不能绕过登记的文本协议。</summary>
    [TestMethod]
    public void NumericEnumCannotBypassSemanticProtocol()
    {
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<SemanticQueryStatus>("0"));
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<SemanticQueryStatus>("999"));
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<ProposalKind>("1"));
    }

    /// <summary>模型正文不能夹带actor字段污染服务器可信上下文。</summary>
    [TestMethod]
    public void SourceBundleRejectsInjectedIdentityField()
    {
        // 所有已知源码字段合法，只有额外身份字段必须触发拒绝。
        const string payload = "{\"ontologyTurtle\":\"\",\"shapesTurtle\":\"\",\"vocabularyTurtle\":null,\"dataTurtle\":\"\",\"actor\":\"injected\"}";
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<SourceBundle>(payload, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
    }

    /// <summary>事件载荷必须保留可执行判别，未知kind不能当作答案接受。</summary>
    [TestMethod]
    public void PersistentEventPayloadUsesCanonicalDiscriminator()
    {
        // 用户正文只是受保护文本，不作为动态HTML或工具指令执行。
        ExecutionPayload payload = new MessageDeltaPayload { Text = "真实工具结果" };
        // 使用与宿主一致的Web JSON命名规则检查实际字节协议。
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
        // 持久化和重放必须使用相同kind和文本，不从active重新构建。
        var json = JsonSerializer.Serialize(payload, options);
        StringAssert.Contains(json, "\"kind\":\"message.delta\"");
        Assert.AreEqual("真实工具结果", ((MessageDeltaPayload)JsonSerializer.Deserialize<ExecutionPayload>(json, options)!).Text);
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<ExecutionPayload>("{\"kind\":\"unregistered\",\"text\":\"x\"}", options));
    }

    /// <summary>业务数据判别必须恰有同名非空分支，不能全空或同时多个分支。</summary>
    [TestMethod]
    public void SemanticDatumRejectsEmptyMismatchedAndMultipleBranches()
    {
        // 完整JSON字段都存在，失败应来自分支规则而不是缺字段。
        const string empty = "{\"kind\":\"entity\",\"ontology\":null,\"entity\":null,\"relationship\":null}";
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<SemanticDatum>(empty, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(new SemanticDatum
        {
            Kind = SemanticDatumKind.Entity,
            Entity = new SemanticEntity(),
            Ontology = new OntologyDescription()
        }));
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(new SemanticDatum
        {
            Kind = SemanticDatumKind.Relationship,
            Entity = new SemanticEntity()
        }));
    }

    /// <summary>事件类型、载荷及版本必须匹配，不能让重放客户端接受错类消息。</summary>
    [TestMethod]
    public void EventEnvelopeRejectsMismatchedPayloadAndUnsupportedVersion()
    {
        // 使用完整可序列化封套，单独改变事件判别与版本。
        var value = new ExecutionEvent
        {
            RunId = "run-test",
            Seq = 1,
            EventId = "run-test:1",
            EventType = "tool.completed",
            SchemaVersion = 1,
            Snapshot = new AssetVersionSnapshot(),
            Payload = new MessageDeltaPayload { Text = "正文" }
        };
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(value));
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(value with { EventType = "message.delta", SchemaVersion = 99 }));
    }

    /// <summary>终态载荷的status必须是对应终态，不能携带RUNNING或另一终态。</summary>
    [TestMethod]
    public void TerminalPayloadRejectsOtherExecutionStates()
    {
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(new RunCompletedPayload { Status = ExecutionStatus.Running }));
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(new RunFailedPayload { Status = ExecutionStatus.Completed }));
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(new RunCancelledPayload { Status = ExecutionStatus.Failed, Code = "cancelled" }));
    }

    /// <summary>字段存在不能代替非空性，真正可空字段则必须允许显式null。</summary>
    [TestMethod]
    public void RequiredReferenceCannotBeNullButNullableFieldCan()
    {
        // Web默认选项复现宿主边界，不擅自收紧历史G1全局序列化。
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
        // 非可空本体字段是明确的合同负例。
        const string invalid = "{\"ontologyTurtle\":null,\"shapesTurtle\":\"\",\"vocabularyTurtle\":null,\"dataTurtle\":\"\"}";
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<SourceBundle>(invalid, options));
        // 词汇未实施允许null，其余源字段存在且非null。
        const string valid = "{\"ontologyTurtle\":\"\",\"shapesTurtle\":\"\",\"vocabularyTurtle\":null,\"dataTurtle\":\"\"}";
        Assert.IsNull(JsonSerializer.Deserialize<SourceBundle>(valid, options)!.VocabularyTurtle);
    }

    /// <summary>三个合法数据分支都能保留kind和对应标准值往返。</summary>
    [TestMethod]
    [DataRow("ontology")]
    [DataRow("entity")]
    [DataRow("relationship")]
    public void EachSemanticBranchRoundtrips(string kind)
    {
        // 每次只构造与kind对应的一个非空分支。
        var value = kind switch
        {
            "ontology" => new SemanticDatum { Kind = SemanticDatumKind.Ontology, Ontology = new OntologyDescription() },
            "entity" => new SemanticDatum { Kind = SemanticDatumKind.Entity, Entity = new SemanticEntity() },
            _ => new SemanticDatum { Kind = SemanticDatumKind.Relationship, Relationship = new SemanticRelationship() }
        };
        // 采用宿主Web命名设置验证实际协议而非仅比较内存对象。
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
        // 实际字节再解析触发与输入相同的判别检查。
        var restored = JsonSerializer.Deserialize<SemanticDatum>(JsonSerializer.Serialize(value, options), options)!;
        Assert.AreEqual(value.Kind, restored.Kind);
        Assert.AreEqual(kind == "ontology", restored.Ontology is not null);
        Assert.AreEqual(kind == "entity", restored.Entity is not null);
        Assert.AreEqual(kind == "relationship", restored.Relationship is not null);
    }

    /// <summary>全部登记事件均保留唯一payload判别及固定封套版本。</summary>
    [TestMethod]
    [DataRow("run.started")]
    [DataRow("tool.started")]
    [DataRow("tool.completed")]
    [DataRow("evidence.added")]
    [DataRow("message.delta")]
    [DataRow("approval.required")]
    [DataRow("run.completed")]
    [DataRow("run.failed")]
    [DataRow("run.cancelled")]
    public void EveryEventPayloadRoundtripsWithMatchingEnvelope(string kind)
    {
        // 嵌套合同均提供完整非空引用，事件模式检查与业务语义校验分开。
        ExecutionPayload payload = kind switch
        {
            "run.started" => new RunStartedPayload(),
            "tool.started" => new ToolStartedPayload { Plan = new SemanticQueryPlan() },
            "tool.completed" => new ToolCompletedPayload { Result = new SemanticQueryResult { Snapshot = new AssetVersionSnapshot() } },
            "evidence.added" => new EvidenceAddedPayload { Evidence = new EvidenceRef { Scope = new ResourceScope(), ObjectTerm = new RdfTerm() } },
            "message.delta" => new MessageDeltaPayload { Text = "实际受保护正文" },
            "approval.required" => new ApprovalRequiredPayload { Scope = new ResourceScope() },
            "run.completed" => new RunCompletedPayload { Status = ExecutionStatus.Completed },
            "run.failed" => new RunFailedPayload { Status = ExecutionStatus.Failed },
            _ => new RunCancelledPayload { Status = ExecutionStatus.Cancelled, Code = "cancelled" }
        };
        // 固定seq和eventId验证实际重放字节可以再次输入，不重新读取active。
        var value = new ExecutionEvent
        {
            RunId = "run-test", Seq = 1, EventId = "run-test:1", EventType = kind,
            SchemaVersion = 1, Snapshot = new AssetVersionSnapshot(), Payload = payload
        };
        // 实际宿主命名策略。
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
        // 从序列化字节恢复强类型派生载荷。
        var restored = JsonSerializer.Deserialize<ExecutionEvent>(JsonSerializer.Serialize(value, options), options)!;
        Assert.AreEqual(kind, restored.EventType);
        Assert.AreEqual(payload.GetType(), restored.Payload.GetType());
        Assert.AreEqual(1, restored.SchemaVersion);
    }
}
