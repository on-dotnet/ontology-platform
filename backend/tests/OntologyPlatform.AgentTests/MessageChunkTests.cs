using System.Reflection;
using System.Text;
using System.Text.Json;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Agents;

namespace OntologyPlatform.AgentTests;

/// <summary>真实Gateway结果在测试中注入边界标签后，经MAF、消息分片及PG重放逐字符保真。</summary>
[TestClass]
public sealed class MessageChunkTests
{
    /// <summary>让非BMP字符精确跨越4096个UTF16单元边界，捕获序列化替换字符。</summary>
    [TestMethod]
    [DataRow("😀")]
    [DataRow("𠀀")]
    public async Task NonBmpResultLabelSurvivesMessageBoundaryAndReplay(string scalar)
    {
        // 首次短标签真实执行用于定位答案中标签的起点，不假造Gateway或MAF输出。
        using var fixture = new AgentFixture();
        // 已有Synthetic样例与后续长标签具有相同查询结构。
        var baseline = await fixture.PublishAsync();
        // 基准运行的真实文本前缀决定UTF16边界；正式版本ID均为GuidN。
        var baselineRun = await fixture.Runs.CreateAsync(fixture.Author, RunFlowTests.Request(fixture.Plan(baseline)), default);
        await fixture.Executor.RunOneAsync("unicode-baseline", default);
        // 使用持久消息找到标签起点，保持测试不依赖提供者前缀的具体措辞。
        var baselineText = string.Concat((await RunFlowTests.AllAsync(fixture, baselineRun.RunId)).Select(value => value.Payload).OfType<MessageDeltaPayload>().Select(value => value.Text));
        // 样例目标实体标签在短答案中唯一；缺失应立即失败而非生成错误用例。
        var labelOffset = baselineText.IndexOf("炉次heat-1", StringComparison.Ordinal);
        Assert.IsTrue(labelOffset >= 0 && labelOffset < 4095);
        // 高代理恰在索引4095，且第二个代理对覆盖下一次分片的推进边界。
        var label = new string('a', 4095 - labelOffset) + scalar + new string('b', 4093) + scalar + "z";
        // 明确测试装饰器只替换真实查询的标签；正式发布、scope、证据和MAF仍走实际实现。
        var executor = new AgentRunExecutor(fixture.Runs, new BoundaryLabelGateway(fixture.Gateway, label), fixture.Clock);
        // 同一真实发布固定计划，不通过未整合的SEM字符规范化阻断被测消息路径。
        var run = await fixture.Runs.CreateAsync(fixture.Author, RunFlowTests.Request(fixture.Plan(baseline)), default);
        await executor.RunOneAsync("unicode-boundary", default);
        // 只从数据库分页读取，不能以内存响应掩盖JSON序列化损坏。
        var events = await RunFlowTests.AllAsync(fixture, run.RunId);
        Assert.IsInstanceOfType<RunCompletedPayload>(events.Last().Payload);
        // ToolCompleted结果应保持注入的完整标签，定位损坏发生于消息分片。
        var result = events.Select(value => value.Payload).OfType<ToolCompletedPayload>().Single().Result;
        Assert.AreEqual(label, result.Data.Single().Entity!.Label);
        // 所有分片按持久seq拼接，字符数上限与UTF8事件上限分别核验。
        var chunks = events.Select(value => value.Payload).OfType<MessageDeltaPayload>().Select(value => value.Text).ToArray();
        Assert.IsTrue(chunks.Length >= 3);
        Assert.IsTrue(chunks.All(value => value.Length is > 0 and <= 4096));
        // label范围由测试输入独立确定，不能接受FFFD或丢失/重复字符。
        var text = string.Concat(chunks);
        Assert.AreEqual(label, text.Substring(labelOffset, label.Length), "持久消息必须完整保留跨边界的Unicode字符。");
        Assert.IsFalse(text.Contains('\uFFFD'));
        Assert.IsTrue(events.All(value => Encoding.UTF8.GetByteCount(JsonSerializer.Serialize(value)) <= 128 * 1024));
        Assert.IsTrue(events.Select((value, index) => value.Seq == index + 1 && value.EventId == run.RunId + ":" + (index + 1)).All(value => value));
        // 再次分页重放必须与首次持久读取逐字节一致，且不能重新调用工具。
        Assert.AreEqual(JsonSerializer.Serialize(events), JsonSerializer.Serialize(await RunFlowTests.AllAsync(fixture, run.RunId)));
    }

    /// <summary>空文本不生成事件；ASCII在边界内外均不丢字符且段长不超过合同上限。</summary>
    [TestMethod]
    [DataRow(0, 0)]
    [DataRow(4096, 1)]
    [DataRow(4097, 2)]
    [DataRow(8193, 3)]
    public void EmptyAndAsciiTextPreserveExactLength(int length, int expectedChunks)
    {
        // 定向调用生产分片函数，避免为不可达的空模型答案增加产品测试入口。
        var method = typeof(AgentRunExecutor).GetMethod("ChunkMessageText", BindingFlags.NonPublic | BindingFlags.Static)!;
        // ASCII输入按已知长度独立构造，不使用被测实现计算期望结果。
        var text = new string('a', length);
        // 枚举实际生产迭代器并通过JSON往返，覆盖与持久事件相同的字符串序列化边界。
        var chunks = ((IEnumerable<string>)method.Invoke(null, [text])!).ToArray();
        Assert.HasCount(expectedChunks, chunks);
        Assert.IsTrue(chunks.All(value => value.Length is > 0 and <= 4096));
        Assert.AreEqual(text, string.Concat(JsonSerializer.Deserialize<string[]>(JsonSerializer.Serialize(chunks))!));
    }

    /// <summary>只在实际Gateway成功后注入合成标签，用于定位消息传输边界而非证明标签查询。</summary>
    private sealed class BoundaryLabelGateway(ISemanticGateway inner, string label) : ISemanticGateway
    {
        /// <summary>仍使用同一实际注册表，不伪造能力或schema。</summary>
        public SemanticCapability[] GetCapabilities() => inner.GetCapabilities();

        /// <summary>实际查询保留正式快照和证据，只有唯一实体展示标签由边界输入替换。</summary>
        public async Task<SemanticQueryResult> ExecuteAsync(ActorContext actor, SemanticQueryPlan plan, CancellationToken cancellationToken)
        {
            // 先完整执行实际服务，再改变唯一被测显示字符串。
            var result = await inner.ExecuteAsync(actor, plan, cancellationToken);
            Assert.HasCount(1, result.Data);
            return result with { Data = [result.Data[0] with { Entity = result.Data[0].Entity! with { Label = label } }] };
        }
    }
}
