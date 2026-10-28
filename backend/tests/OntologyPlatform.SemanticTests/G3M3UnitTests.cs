using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.SemanticTests;

/// <summary>真实RIOT解析Synthetic单位，校验来源、基数和精确IRI身份，不执行换算。</summary>
[TestClass]
public sealed class G3M3UnitTests
{
    /// <summary>共享温度量纲的K和℃仍是两个单位，旧普通数据属性无需强加单位。</summary>
    [TestMethod]
    public async Task CompleteSyntheticUnitsAndOrdinaryPropertyAreValid()
    {
        // 四种单位的合法登记作为正控，不以缺省精度假装已知。
        var snapshot = await ((IG3VocabularyRuntime)SemanticFixture.Runtime()).ReadVocabularyAsync(Sources(), 1, default);
        Assert.IsEmpty(snapshot.Diagnostics, string.Join(",", snapshot.Diagnostics.Select(item => item.Diagnostic.Code)));
        Assert.AreEqual(4, snapshot.Triples.Count(item => item.Triple.Predicate == "urn:ontology-platform:semantics:canonicalUnit"));
    }

    /// <summary>每个缺失、多值或错配必须精确诊断，不能选First或从符号猜身份。</summary>
    [TestMethod]
    [DataRow("version", "unit_version_reference_missing")]
    [DataRow("duplicate", "unit_definition_conflict")]
    [DataRow("quantity", "quantity_kind_reference_missing")]
    [DataRow("dimension", "dimension_reference_missing")]
    [DataRow("exponent", "dimension_definition_invalid")]
    [DataRow("exponent-range", "dimension_definition_invalid")]
    [DataRow("exponent-type", "dimension_definition_invalid")]
    [DataRow("source", "unit_source_required")]
    [DataRow("source-duplicate", "unit_source_required")]
    [DataRow("source-label", "unit_source_required")]
    [DataRow("precision", "unit_precision_unknown")]
    [DataRow("property-missing", "property_unit_binding_invalid")]
    [DataRow("property-duplicate", "property_unit_binding_invalid")]
    [DataRow("unit-missing", "unit_reference_missing")]
    [DataRow("dimension-mismatch", "unit_dimension_mismatch")]
    [DataRow("quantity-mismatch", "unit_quantity_kind_mismatch")]
    [DataRow("same-exponents", "unit_dimension_mismatch")]
    [DataRow("quantity-duplicate", "quantity_kind_reference_missing")]
    public async Task UnitFailuresHaveExactSourceDiagnostics(string scenario, string code)
    {
        // 每个场景仅改变明确三元组，真实解析保留datatype和IRI。
        var source = Sources();
        // 测试修改只作用当前fixture原文，不进入生产解析实现。
        var text = source.VocabularyTurtle!;
        text = scenario switch
        {
            "version" => text.Replace("p:version \"1\"", "p:version \"\"", StringComparison.Ordinal),
            "duplicate" => text + "ex:K-v1 p:symbol \"other\" .",
            "quantity" => text.Replace("p:quantityKind ex:Temperature", "p:quantityKind ex:missing", StringComparison.Ordinal),
            "dimension" => text.Replace("p:dimension ex:temperature", "p:dimension ex:missing", StringComparison.Ordinal),
            "exponent" => text.Replace("p:lengthExponent 0 ;", "", StringComparison.Ordinal),
            "exponent-range" => text.Replace("p:lengthExponent 0", "p:lengthExponent 33", StringComparison.Ordinal),
            "exponent-type" => text.Replace("p:lengthExponent 0", "p:lengthExponent \"0\"", StringComparison.Ordinal),
            "source" => text.Replace("p:standardSource ex:standard-v1", "p:standardSource ex:missing", StringComparison.Ordinal),
            "source-duplicate" => text + "ex:standard-v1 p:version \"2\" .",
            "source-label" => text + "ex:standard-v1 rdfs:label \"另一来源\"@ZH .",
            "precision" => text.Replace("declared-exact", "UNKNOWN", StringComparison.Ordinal),
            "property-missing" => text.Replace("; p:nominalUnit ex:K-v1", "", StringComparison.Ordinal),
            "property-duplicate" => text + "ex:reading p:nominalUnit ex:C-v1 .",
            "unit-missing" => text.Replace("p:nominalUnit ex:K-v1", "p:nominalUnit ex:missing", StringComparison.Ordinal),
            "dimension-mismatch" => text.Replace("ex:reading a owl:DatatypeProperty ; p:quantityKind ex:Temperature ; p:dimension ex:temperature", "ex:reading a owl:DatatypeProperty ; p:quantityKind ex:Temperature ; p:dimension ex:mass", StringComparison.Ordinal),
            "quantity-mismatch" => text + "ex:OtherTemperature a p:QuantityKind ; p:dimension ex:temperature . ex:reading p:quantityKind ex:OtherTemperature .",
            "same-exponents" => text + "ex:temperature2 a p:Dimension ; p:lengthExponent 0 ; p:massExponent 0 ; p:timeExponent 0 ; p:electricCurrentExponent 0 ; p:temperatureExponent 1 ; p:amountExponent 0 ; p:luminousIntensityExponent 0 . ex:K-v1 p:dimension ex:temperature2 .",
            _ => text + "ex:Temperature p:dimension ex:mass ."
        };
        // 精确quantityKind错配仍维持属性基数为一。
        if (scenario == "quantity-mismatch") text = text.Replace("ex:reading a owl:DatatypeProperty ; p:quantityKind ex:Temperature", "ex:reading a owl:DatatypeProperty ; p:quantityKind ex:OtherTemperature", StringComparison.Ordinal);
        // 精确量纲IRI错配不以多值噪声代替真正身份比较。
        if (scenario == "same-exponents") text = text.Replace("ex:K-v1 a p:UnitDefinition ; p:canonicalUnit ex:K ; p:version \"1\" ; p:quantityKind ex:Temperature ; p:dimension ex:temperature", "ex:K-v1 a p:UnitDefinition ; p:canonicalUnit ex:K ; p:version \"1\" ; p:quantityKind ex:Temperature ; p:dimension ex:temperature2", StringComparison.Ordinal);
        // 所有结果都来自本轮真实Jena执行。
        var snapshot = await ((IG3VocabularyRuntime)SemanticFixture.Runtime()).ReadVocabularyAsync(source with { VocabularyTurtle = text }, 1, default);
        // 缺失诊断应包含准确source/hash/focus/path，未知精度是warning阻断。
        var diagnostics = snapshot.Diagnostics.Where(item => item.Diagnostic.Code == code).ToArray();
        Assert.IsNotEmpty(diagnostics, code);
        Assert.IsTrue(diagnostics.All(item => item.SourceId == "vocabulary" && item.SourceHash == snapshot.Hashes.VocabularyHash && item.Diagnostic.FocusNode is not null && item.Diagnostic.Path is not null));
    }

    /// <summary>来源缺陷须定位真实缺失字段，不能把Synthetic或PROV错误指向version。</summary>
    [TestMethod]
    [DataRow("synthetic", "urn:ontology-platform:semantics:synthetic")]
    [DataRow("provenance", "http://www.w3.org/ns/prov#wasDerivedFrom")]
    public async Task StandardSourceFailureKeepsExactPredicate(string scenario, string path)
    {
        // 只改变标准来源，单位自身合成标识与其他字段保持合法。
        var source = Sources();
        // 这两个缺陷都是合法RDF，不靠RIOT语法错误提前退出。
        var text = scenario == "synthetic" ? source.VocabularyTurtle!.Replace("p:synthetic true ; prov:wasDerivedFrom", "p:synthetic false ; prov:wasDerivedFrom", StringComparison.Ordinal) : source.VocabularyTurtle!.Replace("prov:wasDerivedFrom ex:fixture", "prov:wasDerivedFrom \"UNKNOWN\"", StringComparison.Ordinal);
        // 诊断来自真实四源解析上下文。
        var snapshot = await ((IG3VocabularyRuntime)SemanticFixture.Runtime()).ReadVocabularyAsync(source with { VocabularyTurtle = text }, 1, default);
        Assert.IsTrue(snapshot.Diagnostics.Any(item => item.Diagnostic.Code == "unit_source_required" && item.Diagnostic.FocusNode?.Value == "urn:synthetic:m3:standard-v1" && item.Diagnostic.Path == path && item.SourceId == "vocabulary" && item.SourceHash == snapshot.Hashes.VocabularyHash));
    }

    /// <summary>从脚本明确注入的样例根读取本轮已提交的合成单位文档。</summary>
    internal static SourceBundle Sources()
    {
        // 沿用现有脚本固定样例根，不读取私有runtime或凭证文件。
        var root = Environment.GetEnvironmentVariable("G2_SEM_SAMPLES") ?? throw new InvalidOperationException("NOT_RUN: 缺少明确隔离样例根。");
        return new SourceBundle { VocabularyTurtle = File.ReadAllText(Path.Combine(root, "..", "g3-m3", "units.ttl")) };
    }
}
