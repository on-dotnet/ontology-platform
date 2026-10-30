using System.Text.Json;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology;
using OntologyPlatform.Modules.Ontology.Domain;

namespace OntologyPlatform.SemanticTests;

/// <summary>真实RIOT受控模板、同号歧义、半开历史及未知关系回归。</summary>
[TestClass]
public sealed class G3M4IdentityTimeTests
{
    /// <summary>v4只扩展当前时间和身份能力，三个历史profile保持各自散列。</summary>
    [TestMethod]
    public void CurrentProfileRetainsExactHistoricalFactories()
    {
        // 当前策略独立内容散列；不能通过修改旧版本取得新能力。
        var current = SemanticProfile.Current();
        Assert.AreEqual("4", current.Version);
        Assert.AreEqual(23, current.Capabilities.Length);
        Assert.AreEqual("SUPPORTED", current.Capabilities.Single(item => item.Id == "20").Publish);
        Assert.AreEqual("BASIC", current.Capabilities.Single(item => item.Id == "23").Edit);
        Assert.AreEqual("54e4db0fac2c7e4f89802678f3269b8a460190775b53b4fb74955f8cbadd8b86", SemanticProfile.LegacyM1().Hash);
        // 原v3通过同一DTO顺序、原M2和新增两行算法独立重建黄金值。
        var legacy = SemanticProfile.LegacyM2();
        // 原合同的两行能力不包含M4身份或时间升级。
        var capabilities = legacy.Capabilities.Concat(new[] { "SKOS术语与标准治理", "Synthetic单位与量纲引用" }.Select((name, index) => new SemanticCapabilitySupport { Id = (21 + index).ToString(System.Globalization.CultureInfo.InvariantCulture), Name = name, Edit = "BASIC", Preserve = "EXACT", Publish = "SUPPORTED", Validation = "ASSERTED", Reason = "仅有界显式事实与平台域治理；保留来源版本，不执行OWL推理或通用单位换算。" })).ToArray();
        // 精确历史原始内容散列与不可变工厂对照。
        var original = legacy with { Version = "3", Hash = "", Capabilities = capabilities };
        Assert.AreEqual(OntologyRules.Hash(JsonSerializer.Serialize(original)), SemanticProfile.LegacyM3().Hash);
        Assert.AreEqual(22, SemanticProfile.LegacyM3().Capabilities.Length);
        Assert.AreEqual("BLOCKED", SemanticProfile.LegacyM3().Capabilities.Single(item => item.Id == "20").Publish);
        Assert.IsTrue(typeof(IG3IdentityTimeService).IsAssignableFrom(typeof(OntologyService)));
    }

    /// <summary>真实解析后的诊断保持准确源hash和独立未知状态。</summary>
    /// <param name="scenario">唯一被改动的受控场景。</param>
    /// <param name="code">预期固定诊断，空值为无治理冲突。</param>
    [TestMethod]
    [DataRow("valid", null)]
    [DataRow("different-site", null)]
    [DataRow("different-namespace", null)]
    [DataRow("adjacent", null)]
    [DataRow("overlap", "identity_ambiguous")]
    [DataRow("unknown", "identity_relation_indeterminate")]
    [DataRow("no-zone", "time_timezone_required")]
    [DataRow("reverse", "time_interval_reversed")]
    [DataRow("missing-point", "time_reference_missing")]
    [DataRow("double-time", "time_lexical_invalid")]
    [DataRow("unsupported", "time_template_unsupported")]
    [DataRow("unknown-target", "identity_claim_invalid")]
    [DataRow("double-key", "identity_claim_invalid")]
    [DataRow("event-missing", "event_time_invalid")]
    [DataRow("observer-zone", "time_timezone_required")]
    [DataRow("double-type", "time_template_unsupported")]
    public async Task ControlledTemplatesAndIdentityRelations(string scenario, string? code)
    {
        // 一条合法开放终点身份作为共同对照，同号不自动合并目标。
        var text = Claim("one");
        text = scenario switch
        {
            "different-site" => text + Claim("two", site: "site-b", target: "B"),
            "different-namespace" => text + Claim("two", source: "mes.synthetic", target: "B"),
            "adjacent" => Claim("one", to: "2026-02-01T00:00:00Z") + Claim("two", from: "2026-02-01T08:00:00+08:00", target: "B"),
            "overlap" => Claim("one", to: "2026-03-01T00:00:00Z") + Claim("two", from: "2026-02-01T00:00:00Z", to: "2026-04-01T00:00:00Z", target: "B"),
            "unknown" => text + Claim("two", from: "2026-02-01T00:00:00Z", target: "B"),
            "no-zone" => Claim("one", from: "2026-01-01T00:00:00"),
            "reverse" => Claim("one", from: "2026-03-01T00:00:00Z", to: "2026-02-01T00:00:00Z"),
            "missing-point" => text.Replace("ex:from-one a time:Instant", "ex:unrelated a time:Instant", StringComparison.Ordinal),
            "double-time" => text + "ex:from-one time:inXSDDateTimeStamp \"2026-02-01T00:00:00Z\"^^xsd:dateTimeStamp .",
            "unsupported" => text + "ex:from-one time:before ex:A .",
            "unknown-target" => Claim("one", target: "not-registered"),
            "double-key" => text + "ex:claim-one p:externalIdentifier \"EQ-02\" .",
            "event-missing" => text + "ex:event a p:Event .",
            "observer-zone" => text + "ex:event a p:Event ; time:hasTime ex:from-one ; p:observedAtUtc \"2026-01-01T01:00:00\"^^xsd:dateTimeStamp .",
            "double-type" => text + "ex:interval-one a time:Instant .",
            _ => text
        };
        // 完整源始终由真实Jena RIOT解析，不用Turtle正则制造事实。
        var snapshot = await ((IG3VocabularyRuntime)SemanticFixture.Runtime()).ReadVocabularyAsync(Sources(text), 1, default);
        if (code is null) Assert.IsEmpty(snapshot.Diagnostics);
        else
        {
            // 每条结论定位真实ontology源，不伪造行号。
            var diagnostic = snapshot.Diagnostics.FirstOrDefault(item => item.Diagnostic.Code == code);
            Assert.IsNotNull(diagnostic, code);
            Assert.AreEqual("ontology", diagnostic.SourceId);
            Assert.AreEqual(snapshot.Hashes.OntologyHash, diagnostic.SourceHash);
            Assert.IsNotNull(diagnostic.Diagnostic.FocusNode);
            Assert.IsNotNull(diagnostic.Diagnostic.Path);
            Assert.IsNull(diagnostic.Line);
            Assert.IsNull(diagnostic.Column);
            Assert.AreEqual(code == "identity_relation_indeterminate" ? DiagnosticSeverity.Warning : DiagnosticSeverity.Error, diagnostic.Diagnostic.Severity);
        }
        Assert.IsFalse(snapshot.Triples.Any(item => item.Triple.Predicate == "http://www.w3.org/2002/07/owl#sameAs"));
    }

    /// <summary>跨源同一时间点非法词法不能假称来自第一个匹配源。</summary>
    [TestMethod]
    public async Task CrossSourceTimestampDiagnosticUsesBundleEvidence()
    {
        // 同一真实主体和路径分布两源，来源只能诚实定位bundle。
        var source = Sources(Claim("one", from: "2026-01-01T00:00:00")) with { VocabularyTurtle = Prefix + "ex:from-one time:inXSDDateTimeStamp \"2026-01-01T00:00:00\"^^xsd:dateTimeStamp ." };
        // 完整四源仍独立解析，诊断hash绑定同一bundle。
        var snapshot = await ((IG3VocabularyRuntime)SemanticFixture.Runtime()).ReadVocabularyAsync(source, 1, default);
        // 同一路径不能选取第一个源宣称精确定位。
        var diagnostic = snapshot.Diagnostics.Single(item => item.Diagnostic.Code == "time_timezone_required");
        Assert.AreEqual("bundle", diagnostic.SourceId);
        Assert.AreEqual(snapshot.Hashes.BundleHash, diagnostic.SourceHash);
    }

    /// <summary>合成命名空间和受控标准词汇，来源均为Synthetic。</summary>
    internal const string Prefix = "@prefix ex: <urn:synthetic:m4:> . @prefix p: <urn:ontology-platform:semantics:> . @prefix time: <http://www.w3.org/2006/time#> . @prefix xsd: <http://www.w3.org/2001/XMLSchema#> . @prefix owl: <http://www.w3.org/2002/07/owl#> . ";

    /// <summary>构造目标已注册且保留三个独立时间概念的最小四源。</summary>
    internal static SourceBundle Sources(string? claims = null) => new()
    {
        OntologyTurtle = Prefix + "ex:Asset a owl:Class . ex:A a owl:NamedIndividual . ex:B a owl:NamedIndividual . " + (claims ?? Claim("one")),
        VocabularyTurtle = "",
        DataTurtle = Prefix + "ex:sample a ex:Asset ."
    };

    /// <summary>声明的组织厂区来源编号有效期全部显式，不从标签推断目标。</summary>
    internal static string Claim(string id, string site = "site-a", string source = "erp.synthetic", string from = "2026-01-01T00:00:00Z", string? to = null, string target = "A") =>
        $"ex:claim-{id} a p:IdentityClaim ; p:organizationId \"org-demo\" ; p:siteId \"{site}\" ; p:sourceNamespace \"{source}\" ; p:externalIdentifier \"EQ-01\" ; p:targetIri ex:{target} ; p:declarationSource <urn:synthetic:m4:declaration:v1> ; p:validityInterval ex:interval-{id} . ex:interval-{id} a time:Interval ; time:hasBeginning ex:from-{id} . ex:from-{id} a time:Instant ; time:inXSDDateTimeStamp \"{from}\"^^xsd:dateTimeStamp . " +
        (to is null ? "" : $"ex:interval-{id} time:hasEnd ex:to-{id} . ex:to-{id} a time:Instant ; time:inXSDDateTimeStamp \"{to}\"^^xsd:dateTimeStamp . ");
}
