using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.SemanticTests;

/// <summary>真实官方Fuseki SHACL正反例与执行前Shape安全边界。</summary>
[TestClass]
public sealed class ShaclTests
{
    /// <summary>五类、多对多和双厂同号合成样例满足真实Core约束。</summary>
    [TestMethod]
    public async Task StandardSampleConforms()
    {
        // 启动依赖由隔离脚本提供，不从历史容器读数据。
        var runtime = SemanticFixture.Runtime();
        // 完整样例通过标准报告判据。
        var report = await runtime.ValidateAsync(SemanticFixture.Sources(), CancellationToken.None);
        Assert.IsTrue(report.Conforms);
        Assert.AreEqual(ValidationKind.ShaclCore, report.Kind);
        Assert.IsEmpty(report.Issues);
        Assert.AreEqual(64, report.RawReportHash.Length);
    }

    /// <summary>缺键、错误datatype、越界、错误class及缺关系都必须真实定位。</summary>
    [TestMethod]
    [DataRow("", "MinCountConstraintComponent")]
    [DataRow("<urn:x> <urn:ontology-platform:vocabulary:externalId> 12 .", "DatatypeConstraintComponent")]
    [DataRow("<urn:x> <urn:ontology-platform:vocabulary:weight> 101.0 .", "MaxInclusiveConstraintComponent")]
    [DataRow("<urn:h> a <urn:synthetic:metals:Heat> ; <urn:synthetic:metals:castIn> <urn:x> .", "ClassConstraintComponent")]
    public async Task StandardNegativeReportsLocateRealFailure(string extra, string component)
    {
        // 实际运行同一服务与同一标准Shapes。
        var runtime = SemanticFixture.Runtime();
        // 缺关系/业务键与每个独立坏值形成可重复反例。
        var source = SemanticFixture.Sources() with { DataTurtle = "<urn:x> a <urn:synthetic:metals:Coil> . " + extra };
        // 真实报告要求定位字段而非固定错误字符串。
        var report = await runtime.ValidateAsync(source, CancellationToken.None);
        Assert.IsFalse(report.Conforms);
        Assert.IsTrue(report.Issues.Any(issue => issue.ConstraintComponent?.EndsWith(component, StringComparison.Ordinal) == true && issue.FocusNode is not null && issue.Path is not null && issue.SourceShape is not null));
    }

    /// <summary>解析后拒绝SPARQL、JS、递归、imports与复杂path，不依赖关键词正则。</summary>
    [TestMethod]
    [DataRow("<urn:s> <http://www.w3.org/ns/shacl#sparql> <urn:q> .")]
    [DataRow("<urn:s> <http://www.w3.org/ns/shacl#js> <urn:q> .")]
    [DataRow("<urn:s> <http://www.w3.org/ns/shacl#node> <urn:s> .")]
    [DataRow("<urn:s> <http://www.w3.org/2002/07/owl#imports> <http://192.0.2.1/never> .")]
    [DataRow("<urn:s> <http://www.w3.org/ns/shacl#path> [ <http://www.w3.org/ns/shacl#inversePath> <urn:p> ] .")]
    [DataRow("<urn:s> <http://www.w3.org/ns/shacl#property> <urn:s> ; <http://www.w3.org/ns/shacl#path> <urn:p> .")]
    public async Task UnsafeShapesRejectedBeforeExecution(string shapes)
    {
        // 真实运行时必须先RIOT再按RDF谓词白名单判断。
        var runtime = SemanticFixture.Runtime();
        // 任意危险形状都保持固定机器码，不把正文放入错误。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ValidateAsync(new SourceBundle { ShapesTurtle = shapes }, CancellationToken.None));
        Assert.AreEqual(422, error.Status);
        Assert.AreEqual("shape_unsupported", error.Code);
    }
}
