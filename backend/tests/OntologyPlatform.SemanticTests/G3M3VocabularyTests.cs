using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SemanticTests;

/// <summary>M3固定策略、真实四源投影及精确批量编辑回归。</summary>
[TestClass]
public sealed class G3M3VocabularyTests
{
    /// <summary>当前v3显式扩展两项能力而历史v1/v2保持独立登记。</summary>
    [TestMethod]
    public void VersionThreeKeepsHistoricalProfiles()
    {
        // 当前策略应明确登记术语与单位的新增范围。
        var current = SemanticProfile.Current();
        Assert.AreEqual("3", current.Version);
        Assert.AreEqual(22, current.Capabilities.Length);
        Assert.AreEqual("54e4db0fac2c7e4f89802678f3269b8a460190775b53b4fb74955f8cbadd8b86", SemanticProfile.LegacyM1().Hash);
        // 反射使尚无历史工厂时仍以行为断言呈现RED。
        var legacy = typeof(SemanticProfile).GetMethod("LegacyM2");
        Assert.IsNotNull(legacy);
        Assert.AreEqual("2", ((SemanticSupportProfile)legacy.Invoke(null, null)!).Version);
    }

    /// <summary>公共接口必须接入真实运行时及事务服务，不能只有DTO。</summary>
    [TestMethod]
    public void VocabularyInterfacesAreImplemented()
    {
        Assert.IsTrue(typeof(IG3VocabularyRuntime).IsAssignableFrom(typeof(JenaSemanticRuntime)));
        Assert.IsTrue(typeof(IG3VocabularyService).IsAssignableFrom(typeof(OntologyService)));
    }

    /// <summary>每个源的实际三元组和语言项仍携带明确来源，原子双源编辑不改其余字节。</summary>
    [TestMethod]
    public async Task FourSourcesAndAtomicChangesUseRealRiot()
    {
        // 真实引擎由隔离fixture提供，接口缺失时测试明确失败。
        var engine = SemanticFixture.Runtime();
        Assert.IsInstanceOfType<IG3VocabularyRuntime>(engine);
        // 不从本体projection推断词汇或事实源。
        var runtime = (IG3VocabularyRuntime)(object)engine;
        // 注释和CRLF用于核验未改动源原字节。
        var source = new SourceBundle { OntologyTurtle = "<urn:c> a <http://www.w3.org/2002/07/owl#Class> .", ShapesTurtle = "# shapes\r\n", VocabularyTurtle = "<urn:v> <http://www.w3.org/2004/02/skos/core#prefLabel> \"温度\"@zh .", DataTurtle = "<urn:d> <urn:reference> <urn:v> ." };
        // snapshot必须覆盖真实四源而非只返回ontology。
        var snapshot = await runtime.ReadVocabularyAsync(source, 7, default);
        Assert.AreEqual(7, snapshot.Revision);
        Assert.IsTrue(snapshot.Triples.Any(item => item.SourceId == "vocabulary" && item.Triple.Object.Language == "zh"));
        Assert.IsTrue(snapshot.Triples.Any(item => item.SourceId == "data"));
        // 精确旧对象来自同修订真实投影。
        var old = snapshot.Triples.Single(item => item.SourceId == "vocabulary").Triple.Object;
        // 两源编辑使用同一个有限批次。
        VocabularyChange[] changes = [new() { SourceId = VocabularyEditSource.Ontology, Edit = new SemanticEdit { SubjectIri = "urn:c", PredicateIri = "http://www.w3.org/2000/01/rdf-schema#label", NewObject = new RdfTerm { Kind = RdfTermKind.Literal, Value = "温度类", Language = "zh" } } }, new() { SourceId = VocabularyEditSource.Vocabulary, Edit = new SemanticEdit { SubjectIri = "urn:v", PredicateIri = "http://www.w3.org/2004/02/skos/core#prefLabel", OldObject = old, NewObject = old with { Value = "新温度" } } }];
        // 未声明的data谓词被原样保留，不能清洗未知图。
        var edited = await runtime.ApplyVocabularyEditsAsync(source, changes, default);
        Assert.AreEqual(source.ShapesTurtle, edited.ShapesTurtle);
        Assert.AreEqual(source.DataTurtle, edited.DataTurtle);
        Assert.AreNotEqual(source.OntologyTurtle, edited.OntologyTurtle);
        Assert.AreNotEqual(source.VocabularyTurtle, edited.VocabularyTurtle);
        Assert.AreEqual("vocabulary_edit_conflict", (await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ApplyVocabularyEditsAsync(edited, changes, default))).Code);
        Assert.AreEqual("vocabulary_edit_invalid", (await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ApplyVocabularyEditsAsync(source, [], default))).Code);
    }
}
