using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.SemanticTests;

/// <summary>SKOS标准完整性和明确域政策必须返回精确来源诊断，不能冒充SHACL。</summary>
[TestClass]
public sealed class G3M3GovernanceTests
{
    /// <summary>不同治理负例保留精确代码、真实源hash及定位。</summary>
    [TestMethod]
    [DataRow("s14", "skos_pref_label_conflict")]
    [DataRow("s13", "skos_label_relation_conflict")]
    [DataRow("no-language", "skos_label_language_required")]
    [DataRow("unknown-language", "language_policy_unknown")]
    [DataRow("invalid-term", "skos_label_term_invalid")]
    [DataRow("missing-scheme", "skos_scheme_reference_missing")]
    [DataRow("missing-concept", "skos_concept_reference_missing")]
    [DataRow("cycle", "skos_hierarchy_cycle")]
    [DataRow("related", "skos_related_hierarchy_conflict")]
    [DataRow("notation", "skos_notation_duplicate")]
    [DataRow("mapping-scheme", "skos_mapping_scheme_conflict")]
    [DataRow("s46", "skos_mapping_relation_conflict")]
    [DataRow("deprecated", "semantic_reference_deprecated")]
    public async Task SkosPolicyReturnsExactSourceDiagnostic(string scenario, string code)
    {
        // 固定命名空间和已登记Scheme/Concept为每个负例排除无关缺失。
        var source = new SourceBundle
        {
            VocabularyTurtle = Prefix + Base + (scenario switch
            {
                "s14" => "ex:a skos:prefLabel \"甲\"@en, \"乙\"@EN .",
                "s13" => "ex:a skos:prefLabel \"甲\"@zh ; skos:altLabel \"甲\"@ZH .",
                "no-language" => "ex:a skos:prefLabel \"甲\" .",
                "unknown-language" => "ex:a skos:prefLabel \"a\"@fr .",
                "invalid-term" => "ex:a skos:prefLabel ex:b .",
                "missing-scheme" => "ex:a skos:inScheme ex:unknown .",
                "missing-concept" => "ex:a skos:broader ex:unknown .",
                "cycle" => "ex:a skos:broader ex:b . ex:b skos:broader ex:a .",
                "related" => "ex:a skos:broader ex:b . ex:b skos:related ex:a .",
                "notation" => "ex:a skos:notation \"T\" . ex:b skos:notation \"T\" .",
                "mapping-scheme" => "ex:a skos:exactMatch ex:b .",
                "s46" => "ex:a skos:exactMatch ex:c . ex:c skos:broadMatch ex:a .",
                _ => "ex:b owl:deprecated true . ex:a skos:broader ex:b ."
            })
        };
        // 来源投影必须来自真实RIOT，不从Turtle字符串猜语言或关系。
        var snapshot = await ((IG3VocabularyRuntime)SemanticFixture.Runtime()).ReadVocabularyAsync(source, 1, default);
        // 诊断不能丢失精确规则码或任意猜行列。
        var diagnostics = snapshot.Diagnostics.Where(item => item.Diagnostic.Code == code).ToArray();
        Assert.IsNotEmpty(diagnostics, code);
        Assert.IsTrue(diagnostics.All(item => item.SourceId == "vocabulary" && item.SourceHash == snapshot.Hashes.VocabularyHash && item.Diagnostic.FocusNode is not null && item.Diagnostic.Path is not null && item.Line is null && item.Column is null));
        Assert.IsTrue(diagnostics.All(item => item.Diagnostic.Severity == (code == "language_policy_unknown" ? DiagnosticSeverity.Warning : DiagnosticSeverity.Error)));
    }

    /// <summary>真实RIOT保留语言子标签，治理拒绝重复variant或extension且允许合法私用尾部。</summary>
    [TestMethod]
    [DataRow("en-u-ca-gregory-u-nu-latn", false)]
    [DataRow("en-1901-1901", false)]
    [DataRow("en-a-bbb-x-a-ccc", true)]
    public async Task LanguageTagSubtagsRespectBcp47Uniqueness(string language, bool valid)
    {
        // Scheme与Concept已经注册，唯一可变项为被校验的语言标签。
        var source = new SourceBundle { VocabularyTurtle = Prefix + Base + "ex:a skos:prefLabel \"合成语言标签\"@" + language + " ." };
        // 调用真实RIOT解析和生产治理，而不是单独验证正则表达式。
        var snapshot = await ((IG3VocabularyRuntime)SemanticFixture.Runtime()).ReadVocabularyAsync(source, 1, default);
        Assert.IsTrue(snapshot.Triples.Any(item => item.Triple.Predicate == "http://www.w3.org/2004/02/skos/core#prefLabel" && string.Equals(item.Triple.Object.Language, language, StringComparison.OrdinalIgnoreCase)));
        if (valid)
        {
            Assert.IsEmpty(snapshot.Diagnostics);
        }
        else
        {
            // 诊断必须准确归属于原词汇hash、主体和标签谓词。
            var diagnostic = snapshot.Diagnostics.Single(item => item.Diagnostic.Code == "skos_label_language_invalid");
            Assert.AreEqual(DiagnosticSeverity.Error, diagnostic.Diagnostic.Severity);
            Assert.AreEqual("vocabulary", diagnostic.SourceId);
            Assert.AreEqual(snapshot.Hashes.VocabularyHash, diagnostic.SourceHash);
            Assert.AreEqual("urn:synthetic:m3:a", diagnostic.Diagnostic.FocusNode?.Value);
            Assert.AreEqual("http://www.w3.org/2004/02/skos/core#prefLabel", diagnostic.Diagnostic.Path);
        }
    }

    /// <summary>合法多语言、跨Scheme映射及不同语言同文字不应被误判冲突。</summary>
    [TestMethod]
    public async Task ValidMultilingualAndCrossSchemeMappingHaveNoDiagnostics()
    {
        // 同一Concept可属于多个Scheme；映射存在至少一对不同Scheme即可。
        var source = new SourceBundle { VocabularyTurtle = Prefix + Base + "ex:a skos:prefLabel \"相同\"@zh, \"相同\"@en ; skos:altLabel \"别名\"@zh ; skos:exactMatch ex:c . ex:b skos:inScheme ex:t ." };
        // 原文字节不参与治理重写。
        var snapshot = await ((IG3VocabularyRuntime)SemanticFixture.Runtime()).ReadVocabularyAsync(source, 1, default);
        Assert.IsEmpty(snapshot.Diagnostics);
    }

    /// <summary>读取四源中重复定位时必须诚实使用bundle hash。</summary>
    [TestMethod]
    public async Task CrossSourceDuplicateFocusUsesBundleHash()
    {
        // 同一冲突标签分散在两个真实文档，无法伪称单源定位。
        var source = new SourceBundle { OntologyTurtle = Prefix + "ex:a skos:prefLabel \"甲\"@zh .", VocabularyTurtle = Prefix + "ex:a skos:prefLabel \"乙\"@zh ." };
        // 两源合并治理保持各自完整投影。
        var snapshot = await ((IG3VocabularyRuntime)SemanticFixture.Runtime()).ReadVocabularyAsync(source, 1, default);
        // 同focus/path出现在两源，诊断绑定完整bundle。
        var diagnostic = snapshot.Diagnostics.Single(item => item.Diagnostic.Code == "skos_pref_label_conflict");
        Assert.AreEqual("bundle", diagnostic.SourceId);
        Assert.AreEqual(snapshot.Hashes.BundleHash, diagnostic.SourceHash);
    }

    /// <summary>测试专用合法命名空间，所有资源均为合成IRI。</summary>
    private const string Prefix = "@prefix ex: <urn:synthetic:m3:> . @prefix skos: <http://www.w3.org/2004/02/skos/core#> . @prefix owl: <http://www.w3.org/2002/07/owl#> . ";

    /// <summary>两个Scheme和三个Concept的明确注册，不从标签推断身份。</summary>
    private const string Base = "ex:s a skos:ConceptScheme . ex:t a skos:ConceptScheme . ex:a a skos:Concept ; skos:inScheme ex:s . ex:b a skos:Concept ; skos:inScheme ex:s . ex:c a skos:Concept ; skos:inScheme ex:t . ";
}
