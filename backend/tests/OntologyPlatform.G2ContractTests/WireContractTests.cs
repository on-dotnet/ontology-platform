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
}
