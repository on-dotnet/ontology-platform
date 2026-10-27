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
}
