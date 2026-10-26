using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.SemanticTests;

/// <summary>验证真实运行时必须实现唯一语义合同。</summary>
[TestClass]
public sealed class RoundtripTests
{
    /// <summary>没有实现时明确失败，不把空测试工程视作语义通过。</summary>
    [TestMethod]
    public void RuntimeMustImplementCanonicalBoundary()
    {
        // 从真实模块装配查找生产类型，不用测试替身通过存在性门禁。
        var runtimeType = System.Reflection.Assembly.Load("OntologyPlatform.Modules.Ontology")
            .GetType("OntologyPlatform.Modules.Ontology.JenaSemanticRuntime");
        Assert.IsNotNull(runtimeType, "真实Jena受控适配尚未实现。");
        Assert.IsTrue(typeof(ISemanticRuntime).IsAssignableFrom(runtimeType));
    }

    /// <summary>真实RIOT保留中文、语言标签、typed lexical、blank与未知公理，结构编辑安全阻断。</summary>
    [TestMethod]
    public async Task RealRiotPreservesUnsupportedSourceAndTypedLexical()
    {
        // 真实隔离运行时，不使用预制解析结果。
        var runtime = SemanticFixture.Runtime();
        // 不触发网络抓取的imports与复杂空白节点一起保留。
        var source = new SourceBundle
        {
            OntologyTurtle = "@prefix ex: <urn:test:> . @prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . ex:C a owl:Class ; ex:label \"中文\"@zh ; ex:n \"01\"^^xsd:integer ; owl:imports <http://192.0.2.1/do-not-fetch> ; owl:equivalentClass [ ex:unknown \"保留\" ] ."
        };
        // 期望输出与输入hash/revision绑定并保留真实词法。
        var analysis = await runtime.AnalyzeAsync(source, 7, CancellationToken.None);
        Assert.AreEqual(7L, analysis.Projection.Revision);
        Assert.IsFalse(analysis.Projection.StructuralEditAllowed);
        Assert.IsTrue(analysis.Projection.Triples.Any(triple => triple.Object.Value == "中文" && triple.Object.Language == "zh"));
        Assert.IsTrue(analysis.Projection.Triples.Any(triple => triple.Object.Value == "01" && triple.Object.Datatype!.EndsWith("#integer", StringComparison.Ordinal)));
        Assert.IsTrue(analysis.Projection.Triples.Any(triple => triple.Subject.Kind == RdfTermKind.Blank));
        Assert.IsTrue(analysis.Projection.Diagnostics.Any(diagnostic => diagnostic.Code == "import_unlocked"));
        // 发布验证必须报告不支持，不把SHACL空报告当作可发布。
        var report = await runtime.ValidateAsync(source, CancellationToken.None);
        Assert.IsFalse(report.Conforms);
        Assert.AreEqual(ValidationKind.OwlSupport, report.Kind);
        await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ApplyEditAsync(source, new SemanticEdit { SubjectIri = "urn:test:C", PredicateIri = "http://www.w3.org/2000/01/rdf-schema#label", NewObject = new RdfTerm { Kind = RdfTermKind.Literal, Value = "修改" } }, CancellationToken.None));
    }

    /// <summary>对真实标准图的no-op必须保留包括注释在内的完整字节。</summary>
    [TestMethod]
    public async Task NoOpRetainsExactBytesAndInvalidSourceFails()
    {
        // 使用真实运行时验证原始字节不被导出序列化覆盖。
        var runtime = SemanticFixture.Runtime();
        // 简单标准图允许结构编辑。
        var source = new SourceBundle { OntologyTurtle = "# 中文注释\n<urn:test:C> a <http://www.w3.org/2002/07/owl#Class> .\n" };
        // 相同对象增加是集合语义no-op。
        var result = await runtime.ApplyEditAsync(source, new SemanticEdit { SubjectIri = "urn:test:C", PredicateIri = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", NewObject = new RdfTerm { Kind = RdfTermKind.Iri, Value = "http://www.w3.org/2002/07/owl#Class" } }, CancellationToken.None);
        Assert.AreEqual(source, result);
        // 真正RIOT语法错误不能产生新投影。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.AnalyzeAsync(source with { OntologyTurtle = "invalid Turtle" }, 1, CancellationToken.None));
        Assert.AreEqual(422, error.Status);
    }
}
