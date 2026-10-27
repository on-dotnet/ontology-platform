using System.Text.Json;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SemanticTests;

/// <summary>M2命名公理与词法元数据的真实RIOT编辑边界。</summary>
[TestClass]
public sealed class G3M2EditingTests
{
    /// <summary>当前版本升级编辑能力，同时显式登记不可变M1历史。</summary>
    [TestMethod]
    public void CurrentProfileIsVersionTwoAndLegacyGoldenRemainsRegistered()
    {
        // 当前策略必须明确切换，不能重写旧版本内容。
        var current = SemanticProfile.Current();
        Assert.AreEqual("2", current.Version);
        Assert.AreEqual("ontology-platform/g3-m1", current.ProfileId);
        Assert.AreEqual("SOURCE", current.Capabilities[0].Edit);
        Assert.IsTrue(current.Capabilities.Skip(1).Take(10).All(item => item.Edit == "BASIC"));
        // 历史工厂必须可被显式调用，不靠当前策略覆盖旧散列。
        var factory = typeof(SemanticProfile).GetMethod("LegacyM1");
        Assert.IsNotNull(factory);
        // 反射仅容纳首次RED缺少工厂的生产状态，不替代真实DTO计算。
        var legacy = (SemanticSupportProfile)factory.Invoke(null, null)!;
        Assert.AreEqual("1", legacy.Version);
        Assert.AreEqual("54e4db0fac2c7e4f89802678f3269b8a460190775b53b4fb74955f8cbadd8b86", legacy.Hash);
        Assert.AreNotEqual(legacy.Hash, current.Hash);
        Assert.AreEqual(JsonSerializer.Serialize(legacy), JsonSerializer.Serialize(factory.Invoke(null, null)));
    }

    /// <summary>受控命名公理可新增、精确删除且no-op保留原文，声明不可被遗留公理破坏。</summary>
    [TestMethod]
    [DataRow("equivalentClass", "Class")]
    [DataRow("disjointWith", "Class")]
    [DataRow("inverseOf", "ObjectProperty")]
    public async Task NamedAxiomEditPreservesOtherSourcesAndRequiresBothDeclarations(string axiom, string kind)
    {
        // 所有解析及改写均调用本轮实际Jena。
        var runtime = SemanticFixture.Runtime();
        // 注释、CRLF及其余三源用作字节保真基线。
        var source = new SourceBundle { OntologyTurtle = $"# 精确原文\r\n<urn:a> a <{Owl}{kind}> . <urn:b> a <{Owl}{kind}> .\r\n", ShapesTurtle = "# shapes\r\n", VocabularyTurtle = "# vocabulary\n", DataTurtle = "# data\r\n" };
        // 新对象必须完整携带IRI种类且不附字面量元数据。
        var edit = new SemanticEdit { SubjectIri = "urn:a", PredicateIri = Owl + axiom, NewObject = Iri("urn:b") };
        // 新增后projection声明整图允许结构编辑。
        var added = await runtime.ApplyEditAsync(source, edit, default);
        Assert.AreEqual(source with { OntologyTurtle = added.OntologyTurtle }, added);
        Assert.IsTrue((await runtime.AnalyzeAsync(added, 2, default)).Projection.StructuralEditAllowed);
        Assert.AreEqual(added, await runtime.ApplyEditAsync(added, edit, default));
        Assert.AreEqual(added, await runtime.ApplyEditAsync(added, edit with { OldObject = edit.NewObject }, default));
        // 删除任一端显式声明会遗留非法公理，必须失败关闭。
        foreach (var subject in new[] { "urn:a", "urn:b" })
        {
            // 精确声明三元组不以标签匹配。
            var declaration = new SemanticEdit { SubjectIri = subject, PredicateIri = Type, OldObject = Iri(Owl + kind) };
            Assert.AreEqual("rdf_edit_invalid", (await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ApplyEditAsync(added, declaration, default))).Code);
        }
        // 删除公理不删除两端声明，随后声明删除才合法。
        var removed = await runtime.ApplyEditAsync(added, edit with { OldObject = edit.NewObject, NewObject = null }, default);
        Assert.AreEqual(2, (await runtime.AnalyzeAsync(removed, 3, default)).Projection.Triples.Length);
        // 编辑前已有未声明公理也必须明确类型失败，不能修洗图。
        var invalid = source with { OntologyTurtle = $"<urn:a> a <{Owl}{kind}> ; <{Owl}{axiom}> <urn:b> ." };
        Assert.AreEqual("rdf_edit_invalid", (await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ApplyEditAsync(invalid, edit, default))).Code);
    }

    /// <summary>IRI附literal元数据及语言冲突不能在序列化或no-op中静默丢弃。</summary>
    [TestMethod]
    [DataRow("iri-language")]
    [DataRow("iri-datatype")]
    [DataRow("literal-conflict")]
    [DataRow("langString-without-language")]
    public async Task InvalidMetadataFailsBeforeAnyNoOpOrSerialization(string scenario)
    {
        // 独占真实RIOT解析器。
        var runtime = SemanticFixture.Runtime();
        // 纯命名声明不包含任何未知公理。
        var source = new SourceBundle { OntologyTurtle = $"<urn:a> a <{Owl}Class> ." };
        // 分别覆盖会被原有Term忽略的字段组合。
        var term = scenario switch
        {
            "iri-language" => Iri(Owl + "Class") with { Language = "zh" },
            "iri-datatype" => Iri(Owl + "Class") with { Datatype = "http://www.w3.org/2001/XMLSchema#string" },
            "literal-conflict" => new RdfTerm { Kind = RdfTermKind.Literal, Value = "值", Language = "zh", Datatype = "http://www.w3.org/2001/XMLSchema#string" },
            _ => new RdfTerm { Kind = RdfTermKind.Literal, Value = "值", Datatype = LangString }
        };
        // 新增及相同对象no-op都必须先拒绝非法词法元数据。
        foreach (var old in new RdfTerm?[] { null, term })
        {
            // 字面量用label，IRI用type，避免其它支持边界掩盖字段缺陷。
            var edit = new SemanticEdit { SubjectIri = "urn:a", PredicateIri = term.Kind == RdfTermKind.Iri ? Type : Label, OldObject = old, NewObject = term };
            Assert.AreEqual("rdf_edit_invalid", (await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ApplyEditAsync(source, edit, default))).Code);
        }
    }

    /// <summary>RIOT投影rdf:langString与语言组合可以完整精确替换及删除。</summary>
    [TestMethod]
    public async Task RiotLanguageTermCanBeCopiedAndDeletedPrecisely()
    {
        // 实际RIOT输出是oldObject唯一权威来源。
        var runtime = SemanticFixture.Runtime();
        // typed lexical及语言标签在另一个标签编辑后仍保持原值。
        var source = new SourceBundle { OntologyTurtle = $"<urn:a> a <{Owl}Class> ; <{Label}> \"中文😀\"@zh-Hans ." };
        // 精确复制真实投影中的语言和datatype字段。
        var old = (await runtime.AnalyzeAsync(source, 1, default)).Projection.Triples.Single(item => item.Predicate == Label).Object;
        Assert.AreEqual("zh-Hans", old.Language, ignoreCase: true);
        // language+规范rdf:langString是合法组合，客户端可以显式指定。
        var replacement = old with { Value = "修改😀", Datatype = LangString };
        // 替换必须经实际RIOT重读校验，而非只看输出文本。
        var changed = await runtime.ApplyEditAsync(source, new SemanticEdit { SubjectIri = "urn:a", PredicateIri = Label, OldObject = old, NewObject = replacement }, default);
        // 输出可能按RIOT规范表示datatype，但词法和语言必须保留。
        var actual = (await runtime.AnalyzeAsync(changed, 2, default)).Projection.Triples.Single(item => item.Predicate == Label).Object;
        Assert.AreEqual("修改😀", actual.Value);
        Assert.AreEqual(old.Language, actual.Language);
        // 删除沿用服务端真实投影，不能省略rdf:langString而误删其它值。
        var removed = await runtime.ApplyEditAsync(changed, new SemanticEdit { SubjectIri = "urn:a", PredicateIri = Label, OldObject = actual }, default);
        Assert.AreEqual(1, (await runtime.AnalyzeAsync(removed, 3, default)).Projection.Triples.Length);
    }

    /// <summary>构造不带literal字段的命名IRI项。</summary>
    private static RdfTerm Iri(string value) => new() { Kind = RdfTermKind.Iri, Value = value };

    /// <summary>OWL标准命名空间。</summary>
    private const string Owl = "http://www.w3.org/2002/07/owl#";

    /// <summary>显式类型谓词。</summary>
    private const string Type = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";

    /// <summary>标签谓词。</summary>
    private const string Label = "http://www.w3.org/2000/01/rdf-schema#label";

    /// <summary>语言字面量规范类型。</summary>
    private const string LangString = "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString";
}
