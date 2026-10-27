using System.Text.Json;
using OntologyPlatform.Modules.Ontology.Domain;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SemanticTests;

/// <summary>新关口必须由真实生产服务实现，不能只交付DTO。</summary>
[TestClass]
public sealed class G3BoundaryTests
{
    /// <summary>本体服务和Jena分别实现新增应用与比较合同。</summary>
    [TestMethod]
    public void G3ProductionBoundariesExist()
    {
        Assert.IsTrue(typeof(IG3OntologyService).IsAssignableFrom(typeof(OntologyService)), "缺少持久评估与版本比较应用服务。");
        Assert.IsTrue(typeof(IG3SemanticRuntime).IsAssignableFrom(typeof(JenaSemanticRuntime)), "缺少有界精确图比较。");
    }
    /// <summary>策略固定二十行、四维边界和确定性内容散列。</summary>
    [TestMethod]
    public void ProfileHasExactMatrixAndStableHash()
    {
        // 获取策略不需要数据库或外部运行时。
        var service = new OntologyService(null!, null!, null!, TimeProvider.System);
        Assert.IsInstanceOfType<IG3OntologyService>(service);
        // 固定JSON顺序与空hash计算规范可由客户端独立复算。
        var profile = ((IG3OntologyService)(object)service).GetProfile();
        Assert.AreEqual(20, profile.Capabilities.Length);
        Assert.AreEqual("ontology-platform/g3-m1", profile.ProfileId);
        Assert.AreEqual("1", profile.Version);
        Assert.AreEqual("ASSERTED_ONLY", profile.ReasoningMode);
        Assert.AreEqual(OntologyRules.Hash(JsonSerializer.Serialize(profile with { Hash = "" })), profile.Hash);
        for (var index = 0; index < 20; index++)
        {
            Assert.AreEqual((index + 1).ToString("D2"), profile.Capabilities[index].Id);
            Assert.AreEqual(index is >= 1 and <= 7 ? "BASIC" : "SOURCE", profile.Capabilities[index].Edit);
            Assert.AreEqual(index < 11 ? "SUPPORTED" : "BLOCKED", profile.Capabilities[index].Publish);
            Assert.AreEqual("EXACT", profile.Capabilities[index].Preserve);
        }
    }

    /// <summary>真实RIOT后的空白节点标签变化不改变图语义。</summary>
    [TestMethod]
    public async Task RenamedBlankNodesCompareExactlyAndNearMissIsDifferent()
    {
        // 全部图来自本轮隔离的实际Jena。
        var runtime = SemanticFixture.Runtime();
        Assert.IsInstanceOfType<IG3SemanticRuntime>(runtime);
        // 对称环还包含共享节点，简单按label或度数比较无法可靠判等。
        var left = new SourceBundle { OntologyTurtle = "_:a <urn:p> _:b . _:b <urn:p> _:a . _:a <urn:q> _:c . _:b <urn:q> _:c . _:c <urn:v> 1 ." };
        // 同一集合采用完全不同标签和三元组顺序。
        var right = left with { OntologyTurtle = "_:z <urn:v> 1 . _:y <urn:q> _:z . _:x <urn:q> _:z . _:y <urn:p> _:x . _:x <urn:p> _:y ." };
        // 非同构只改变共享结构，仍有相同节点和三元组数量。
        var different = right with { OntologyTurtle = "_:z <urn:v> 1 . _:y <urn:q> _:z . _:x <urn:q> _:y . _:y <urn:p> _:x . _:x <urn:p> _:y ." };
        Assert.AreEqual(GraphComparisonStatus.Equivalent, (await ((IG3SemanticRuntime)(object)runtime).CompareSourcesAsync(left, right, default))[0].Graph.Status);
        Assert.AreEqual(GraphComparisonStatus.Different, (await ((IG3SemanticRuntime)(object)runtime).CompareSourcesAsync(left, different, default))[0].Graph.Status);
    }
    /// <summary>二十个真实Turtle语料逐项验证支持矩阵，有限命名公理只允许源码发布。</summary>
    [TestMethod]
    public async Task TwentyCorpusRowsUseAssertedOnlySupportAndShapesBlankException()
    {
        // 语料位置由本轮隔离fixture显式指定，不读取历史证据。
        var samples = Environment.GetEnvironmentVariable("G2_SEM_SAMPLES");
        if (samples is null) Assert.Inconclusive("NOT_RUN: 缺少本轮隔离样例目录。");
        // G3语料与已提交G2样例同在samples下。
        var corpus = Directory.GetFiles(Path.Combine(Path.GetDirectoryName(samples)!, "g3-m1"), "*.ttl").Order(StringComparer.Ordinal).ToArray();
        Assert.AreEqual(20, corpus.Length);
        // 所有报告都由真实RIOT/SHACL执行，不能按文件名返回预制结果。
        var runtime = SemanticFixture.Runtime();
        for (var index = 0; index < corpus.Length; index++)
        {
            // 本项原始源码必须可解析保留，不支持不代表删除或改写。
            var sources = new SourceBundle { OntologyTurtle = File.ReadAllText(corpus[index]) };
            // 真实支持报告独立于结构编辑权限。
            var report = await runtime.ValidateAsync(sources, default);
            Assert.AreEqual(index < 11, report.Conforms, Path.GetFileName(corpus[index]));
            if (index is >= 8 and <= 10)
            {
                // 命名OWL公理SOURCE可编辑但整图不能结构重写。
                var analysis = await runtime.AnalyzeAsync(sources, 1, default);
                Assert.IsFalse(analysis.Projection.StructuralEditAllowed);
            }
        }
        // 合法SHACL property/list blank节点遵守独立ShapePolicy。
        var shapes = new SourceBundle { ShapesTurtle = "@prefix sh: <http://www.w3.org/ns/shacl#> . <urn:S> a sh:NodeShape ; sh:targetClass <urn:C> ; sh:property [ sh:path <urn:p> ; sh:in ( 1 2 ) ] ." };
        Assert.IsTrue((await runtime.ValidateAsync(shapes, default)).Conforms);
    }

    /// <summary>空白节点超限、调用方取消及总时限必须统一撤回四源结论。</summary>
    [TestMethod]
    [DataRow("blank_node_budget")]
    [DataRow("comparison_cancelled")]
    [DataRow("comparison_timeout")]
    public async Task ComparisonBudgetOrCancellationRevokesAllPartialResults(string expectedCode)
    {
        // 真实引擎仍提供全部解析响应，只有时序由测试控制。
        var runtime = expectedCode == "comparison_timeout" ? SemanticFixture.RuntimeWithGate(async (request, token) =>
        {
            if (request.Method == HttpMethod.Get) await Task.Delay(Timeout.InfiniteTimeSpan, token);
        }) : SemanticFixture.Runtime();
        // 超限放在最后data源，确认前三源部分结论也不会泄漏为完成。
        var left = new SourceBundle { OntologyTurtle = "<urn:C> a <http://www.w3.org/2002/07/owl#Class> .", DataTurtle = expectedCode == "blank_node_budget" ? string.Join('\n', Enumerable.Range(0, 129).Select(index => $"_:b{index} <urn:p> 1 .")) : "<urn:a> <urn:p> 1 ." };
        // 原始字节变化仍必须准确返回。
        var right = left with { OntologyTurtle = left.OntologyTurtle + "\r\n# byte change" };
        // 已取消也不能把相同字节快速路径误判为成功。
        using var cancellation = new CancellationTokenSource();
        if (expectedCode == "comparison_cancelled") cancellation.Cancel();
        // 全四源共享同一个真实预算结论。
        var results = await ((IG3SemanticRuntime)(object)runtime).CompareSourcesAsync(left, right, cancellation.Token);
        Assert.AreEqual(4, results.Length);
        Assert.IsTrue(results.All(item => item.Graph.Status == GraphComparisonStatus.Indeterminate && item.Graph.Code == expectedCode));
        Assert.IsTrue(results[0].SourceChanged);
        Assert.IsFalse(results[3].SourceChanged);
    }

    /// <summary>跨文档总量不能变成四份各5000条，非法Turtle不能伪装图不同。</summary>
    [TestMethod]
    public async Task ComparisonPreservesAbsentBytesAndRejectsInvalidOrOversizedBundles()
    {
        // 运行时必须由真实RIOT拒绝非法源码，不采用测试parser。
        var runtime = (IG3SemanticRuntime)(object)SemanticFixture.Runtime();
        // 词汇缺席与空字符串hash不同，但合法空图等价。
        var result = await runtime.CompareSourcesAsync(new SourceBundle(), new SourceBundle { VocabularyTurtle = "" }, default);
        Assert.IsTrue(result[2].SourceChanged);
        Assert.IsNull(result[2].LeftHash);
        Assert.IsNotNull(result[2].RightHash);
        Assert.AreEqual(GraphComparisonStatus.Equivalent, result[2].Graph.Status);
        // 合法字节范围内，ontology和data之和5001条仍必须拒绝。
        var sources = new SourceBundle { OntologyTurtle = string.Join('\n', Enumerable.Range(0, 2501).Select(index => $"<urn:s{index}> <urn:p> 1 .")), DataTurtle = string.Join('\n', Enumerable.Range(0, 2500).Select(index => $"<urn:d{index}> <urn:p> 1 .")) };
        Assert.AreEqual("rdf_triple_budget", (await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.CompareSourcesAsync(sources, new SourceBundle(), default))).Code);
        // 相同非法文本也必须422，不能按字节相同绕过解析。
        Assert.AreEqual(422, (await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.CompareSourcesAsync(new SourceBundle { OntologyTurtle = "invalid turtle" }, new SourceBundle { OntologyTurtle = "invalid turtle" }, default))).Status);
    }

}
