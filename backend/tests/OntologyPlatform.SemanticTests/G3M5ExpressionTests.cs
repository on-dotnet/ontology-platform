using System.Reflection;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SemanticTests;

/// <summary>高阶只读投影的廉价结构正反回归及真实RIOT集成入口，二者分别计量。</summary>
[TestClass]
public sealed class G3M5ExpressionTests
{
    /// <summary>精确标准OWL谓词。</summary>
    private const string Owl = "http://www.w3.org/2002/07/owl#";

    /// <summary>精确标准RDF谓词。</summary>
    private const string Rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#";

    /// <summary>基数需要真实非负整数类型。</summary>
    private const string IntegerType = "http://www.w3.org/2001/XMLSchema#nonNegativeInteger";

    /// <summary>基数合法正负词法均依据XML Schema值域，不转换为机器整数。</summary>
    [TestMethod]
    [DataRow("0", true)]
    [DataRow("+0002", true)]
    [DataRow("-0", true)]
    [DataRow(" 12 ", true)]
    [DataRow("123456789012345678901234567890", true)]
    [DataRow("-1", false)]
    [DataRow("1.0", false)]
    [DataRow("1e2", false)]
    [DataRow("1 2", false)]
    [DataRow("+", false)]
    [DataRow("１２", false)]
    public void ProjectionCardinalityPreservesLexicalAndDiagnosesInvalid(string lexical, bool valid)
    {
        // 合成已解析项只检验投影词法逻辑；真实解析由Real开头用例单独验证。
        var source = Build(Restriction(Owl + "cardinality", Literal(lexical, IntegerType)));
        Assert.AreEqual(valid ? "COMPLETE" : "INDETERMINATE", source.Status);
        Assert.AreEqual(lexical, source.Nodes.Single().Properties.Single(item => item.PredicateIri == Owl + "cardinality").Values.Single().Value);
        Assert.AreEqual(valid, source.ReadOnlyStructured);
        Assert.AreEqual(!valid, source.Diagnostics.Any(item => item.Code == "cardinality_invalid"));
        Assert.IsTrue(source.SourcePreserved);
        Assert.IsFalse(source.Editable);
        Assert.IsFalse(source.Inferred);
    }

    /// <summary>词面相同但类型或语言错误不能冒充合法OWL基数。</summary>
    [TestMethod]
    public void ProjectionCardinalityRejectsWrongTypeAndLanguage()
    {
        foreach (var term in new[] { Literal("1", "http://www.w3.org/2001/XMLSchema#integer"), Literal("1", IntegerType) with { Language = "zh" }, Iri("urn:one") })
        {
            // 每种不支持项保留原对象，禁止清洗或猜测类型。
            var result = Build(Restriction(Owl + "minCardinality", term));
            Assert.AreEqual("INDETERMINATE", result.Status);
            Assert.AreEqual(term, result.Nodes.Single().Properties.Single(item => item.PredicateIri == Owl + "minCardinality").Values.Single());
        }
    }

    /// <summary>限定基数必须具有准确onProperty和唯一onClass或onDataRange。</summary>
    [TestMethod]
    [DataRow("onClass")]
    [DataRow("onDataRange")]
    public void ProjectionQualifiedCardinalityRequiresUniqueQualifier(string qualifier)
    {
        // 同一合法restricted主体的三个必要标准项。
        RdfTriple[] triples = [.. Restriction(Owl + "qualifiedCardinality", Literal("01", IntegerType)), Triple(Blank("r"), Owl + qualifier, Iri("urn:C"))];
        Assert.AreEqual("COMPLETE", Build(triples).Status);
        Assert.AreEqual("INDETERMINATE", Build(triples[..^1]).Status);
        Assert.AreEqual("INDETERMINATE", Build([.. triples, Triple(Blank("r"), Owl + (qualifier == "onClass" ? "onDataRange" : "onClass"), Iri("urn:Other"))]).Status);
    }

    /// <summary>适配历史codec两种blank前缀而不改变literal和来源隔离。</summary>
    [TestMethod]
    public void ProjectionBlankPrefixSharedReferencesAndSourcesAreIsolated()
    {
        // 主体带_:而对象不带，必须在新投影内部关联到同一个实际节点。
        RdfTriple[] triples = [Triple(Iri("urn:A"), Owl + "equivalentClass", Blank("r")), Triple(Iri("urn:B"), Owl + "equivalentClass", Blank("_:r")), .. Restriction(Owl + "hasValue", Literal("012", "urn:type"))];
        // 同名blank出现在另一源时只允许使用该源自己的定义。
        var left = Build(triples);
        // 第二源词面不同，不能因为blank ID相同而污染第一源。
        var right = Build(Restriction(Owl + "hasValue", Literal("另一源", null, "zh")), "vocabulary");
        Assert.AreEqual(3, left.Nodes.Length);
        Assert.AreEqual("_:r", left.Nodes.Single(item => item.Term.Kind == RdfTermKind.Blank).Term.Value);
        Assert.IsTrue(left.Diagnostics.Any(item => item.Code == "shared_blank_reference"));
        Assert.AreEqual("COMPLETE", left.Status);
        Assert.AreEqual("012", left.Nodes.Single(item => item.Term.Kind == RdfTermKind.Blank).Properties.Single(item => item.PredicateIri == Owl + "hasValue").Values.Single().Value);
        Assert.AreEqual("另一源", right.Nodes.Single().Properties.Single(item => item.PredicateIri == Owl + "hasValue").Values.Single().Value);
        Assert.AreEqual("zh", right.Nodes.Single().Properties.Single(item => item.PredicateIri == Owl + "hasValue").Values.Single().Language);
    }

    /// <summary>量词目标只接受类或数据范围项，不把literal解释成类。</summary>
    [TestMethod]
    [DataRow("someValuesFrom")]
    [DataRow("allValuesFrom")]
    public void ProjectionRestrictionQuantifierHasLegalTarget(string predicate)
    {
        Assert.AreEqual("COMPLETE", Build(Restriction(Owl + predicate, Iri("urn:C"))).Status);
        Assert.AreEqual("INDETERMINATE", Build(Restriction(Owl + predicate, Literal("urn:C"))).Status);
        Assert.AreEqual("INDETERMINATE", Build(Restriction(Owl + predicate, Blank("missing"))).Status);
        // 匿名目标必须有本源真实结构，不从其他源按同名blank补齐。
        var nested = Restriction(Owl + predicate, Blank("c")).Concat([Triple(Blank("c"), Owl + "complementOf", Iri("urn:C"))]).ToArray();
        Assert.AreEqual("COMPLETE", Build(nested).Status);
    }

    /// <summary>IRI、typed literal和language literal的hasValue都保留准确项身份。</summary>
    [TestMethod]
    public void ProjectionRestrictionHasValuePreservesSupportedValueKinds()
    {
        foreach (var term in new[] { Iri("urn:individual"), Literal("001", "urn:type"), Literal("中文", null, "zh") })
        {
            // 合法完整restriction不能因保守发布阻断而丢失只读值结构。
            var source = Build(Restriction(Owl + "hasValue", term));
            Assert.AreEqual("COMPLETE", source.Status);
            Assert.AreEqual(term, source.Nodes.Single().Properties.Single(item => item.PredicateIri == Owl + "hasValue").Values.Single());
        }
        // 匿名个体暂不确认槽位类型，原项仍完整保留而非改成IRI。
        var anonymous = Build([.. Restriction(Owl + "hasValue", Blank("i")), Triple(Blank("i"), Rdf + "type", Iri(Owl + "NamedIndividual"))]);
        Assert.AreEqual("INDETERMINATE", anonymous.Status);
        Assert.IsTrue(anonymous.Diagnostics.Any(item => item.Code == "restriction_value_unsupported"));
    }

    /// <summary>缺属性、literal/复杂属性、多构造及普通基数混限定都不能标完整。</summary>
    [TestMethod]
    [DataRow("missing-property")]
    [DataRow("literal-property")]
    [DataRow("blank-property")]
    [DataRow("two-properties")]
    [DataRow("two-constructors")]
    [DataRow("two-cardinalities")]
    [DataRow("ordinary-qualifier")]
    [DataRow("no-constructor")]
    [DataRow("missing-type")]
    [DataRow("qualified-literal-property")]
    public void ProjectionRestrictionRejectsAmbiguousOrMalformedShape(string scenario)
    {
        // 反例以一个完整合法restriction为起点，只改动正在验证的槽位。
        var triples = Restriction(Owl + "cardinality", Literal("1", IntegerType)).ToList();
        if (scenario == "missing-property") triples.RemoveAll(item => item.Predicate == Owl + "onProperty");
        if (scenario is "literal-property" or "blank-property" or "qualified-literal-property")
        {
            triples.RemoveAll(item => item.Predicate == Owl + "onProperty");
            triples.Add(Triple(Blank("r"), Owl + "onProperty", scenario == "blank-property" ? Blank("inverse") : Literal("urn:p")));
        }
        if (scenario == "two-properties") triples.Add(Triple(Blank("r"), Owl + "onProperty", Iri("urn:other")));
        if (scenario == "two-constructors") triples.Add(Triple(Blank("r"), Owl + "someValuesFrom", Iri("urn:C")));
        if (scenario == "two-cardinalities") triples.Add(Triple(Blank("r"), Owl + "maxCardinality", Literal("2", IntegerType)));
        if (scenario == "ordinary-qualifier") triples.Add(Triple(Blank("r"), Owl + "onClass", Iri("urn:C")));
        if (scenario == "no-constructor") triples.RemoveAll(item => item.Predicate == Owl + "cardinality");
        if (scenario == "missing-type") triples.RemoveAll(item => item.Predicate == Rdf + "type");
        if (scenario == "qualified-literal-property")
        {
            triples.RemoveAll(item => item.Predicate == Owl + "cardinality");
            triples.Add(Triple(Blank("r"), Owl + "qualifiedCardinality", Literal("1", IntegerType)));
            triples.Add(Triple(Blank("r"), Owl + "onClass", Iri("urn:C")));
        }
        // 已解析的合法RDF可以有损坏OWL结构；保留源同时撤回完整结论。
        var result = Build(triples.ToArray());
        Assert.AreEqual("INDETERMINATE", result.Status);
        Assert.IsTrue(result.SourcePreserved);
        Assert.IsFalse(result.ReadOnlyStructured);
        Assert.IsTrue(result.Diagnostics.Any(item => item.Code == "restriction_invalid"));
    }

    /// <summary>链顺序与字典排序分离，rdf:rest链长度不算表达式嵌套。</summary>
    [TestMethod]
    public void ProjectionListOrderAndLongListDoNotUseExpressionDepth()
    {
        // 四十项列表超过表达式深度32但属于合法有限列表。
        var triples = new List<RdfTriple> { Triple(Iri("urn:p"), Owl + "propertyChainAxiom", Blank("l0")) };
        for (var index = 0; index < 40; index++)
        {
            // 倒序IRI证明恢复依赖first/rest而不是词面排序。
            var cell = Blank("l" + index);
            triples.Add(Triple(cell, Rdf + "first", Iri("urn:p" + (40 - index))));
            triples.Add(Triple(cell, Rdf + "rest", index == 39 ? Iri(Rdf + "nil") : Blank("l" + (index + 1))));
        }
        // 完整结构保持有序列表，内部cell只保留flat引用避免尾链重复物化。
        var result = Build(triples.ToArray());
        Assert.AreEqual("COMPLETE", result.Status);
        CollectionAssert.AreEqual(Enumerable.Range(0, 40).Select(index => "urn:p" + (40 - index)).ToArray(), result.Nodes.Single(item => item.Term.Value == "_:l0").OrderedItems.Select(item => item.Value).ToArray());
        Assert.IsTrue(result.Nodes.Sum(item => item.OrderedItems.Length) <= 512);
    }

    /// <summary>断裂、分叉和纯环列表都有明确失败关闭诊断。</summary>
    [TestMethod]
    [DataRow("broken")]
    [DataRow("branch")]
    [DataRow("cycle")]
    public void ProjectionMalformedListsNeverBecomeComplete(string scenario)
    {
        // 不提供命名root，纯环分量也必须被检查。
        var triples = new List<RdfTriple> { Triple(Blank("l"), Rdf + "first", Iri("urn:A")) };
        if (scenario != "broken") triples.Add(Triple(Blank("l"), Rdf + "rest", scenario == "cycle" ? Blank("l") : Iri(Rdf + "nil")));
        if (scenario == "branch") triples.Add(Triple(Blank("l"), Rdf + "first", Iri("urn:B")));
        // 未准确恢复不能标readOnlyStructured=true。
        var source = Build(triples.ToArray());
        Assert.AreEqual("INDETERMINATE", source.Status);
        Assert.IsFalse(source.ReadOnlyStructured);
        Assert.IsTrue(source.Diagnostics.Any(item => item.Code == (scenario == "cycle" ? "expression_cycle" : "list_invalid")));
        Assert.IsTrue(source.Roots.Length > 0);
    }

    /// <summary>共享列表尾链是合法引用，不因不同head而误判环。</summary>
    [TestMethod]
    public void ProjectionSharedListTailDoesNotBecomeCycle()
    {
        // 两个列表head共享第三个实际cell。
        var result = Build([Triple(Iri("urn:A"), Owl + "unionOf", Blank("a")), Triple(Iri("urn:B"), Owl + "unionOf", Blank("b")), Triple(Blank("a"), Rdf + "first", Iri("urn:A")), Triple(Blank("a"), Rdf + "rest", Blank("tail")), Triple(Blank("b"), Rdf + "first", Iri("urn:B")), Triple(Blank("b"), Rdf + "rest", Blank("tail")), Triple(Blank("tail"), Rdf + "first", Iri("urn:Shared")), Triple(Blank("tail"), Rdf + "rest", Iri(Rdf + "nil"))]);
        Assert.AreEqual("COMPLETE", result.Status);
        Assert.IsFalse(result.Diagnostics.Any(item => item.Code == "expression_cycle"));
        Assert.AreEqual("urn:Shared", result.Nodes.Single(item => item.Term.Value == "_:a").OrderedItems[^1].Value);
        Assert.AreEqual("urn:Shared", result.Nodes.Single(item => item.Term.Value == "_:b").OrderedItems[^1].Value);
    }

    /// <summary>匿名表达式环必须诊断；命名子类环不能错误声称OWL不一致。</summary>
    [TestMethod]
    public void ProjectionAnonymousCycleAndNamedSubclassCycleAreDistinct()
    {
        Assert.AreEqual("INDETERMINATE", Build([Triple(Blank("a"), Owl + "complementOf", Blank("b")), Triple(Blank("b"), Owl + "complementOf", Blank("a"))]).Status);
        Assert.AreEqual("COMPLETE", Build([Triple(Iri("urn:A"), "http://www.w3.org/2000/01/rdf-schema#subClassOf", Iri("urn:B")), Triple(Iri("urn:B"), "http://www.w3.org/2000/01/rdf-schema#subClassOf", Iri("urn:A"))]).Status);
    }

    /// <summary>未知OWL不能静默结构化，imports只显示引用且不宣称加载或推理。</summary>
    [TestMethod]
    public void ProjectionUnknownTermsAndImportsHaveSeparateSupport()
    {
        // 未锁imports可准确显示本地引用，但不代表发布或推理可执行。
        var imports = Build([Triple(Iri("urn:ontology"), Owl + "imports", Iri("https://example.invalid/not-loaded"))]);
        Assert.AreEqual("COMPLETE", imports.Status);
        Assert.IsTrue(imports.Diagnostics.Any(item => item.Code == "imports_not_loaded"));
        Assert.IsFalse(imports.Inferred);
        // 未知标准命名空间词汇会撤回结构完整性。
        var unknown = Build([Triple(Iri("urn:ontology"), Rdf + "type", Iri(Owl + "ImaginaryClass"))]);
        Assert.AreEqual("INDETERMINATE", unknown.Status);
        Assert.IsTrue(unknown.Diagnostics.Any(item => item.Code == "owl_term_unknown"));
    }

    /// <summary>主体节点及表达式深度预算真实触发，不以截断冒充完整。</summary>
    [TestMethod]
    public void ProjectionNodeAndDepthBudgetFailClosed()
    {
        // 不超过triple总预算，但主体多于只读结构节点预算。
        var nodes = Enumerable.Range(0, 513).Select(index => Triple(Iri("urn:n" + index), Rdf + "type", Iri(Owl + "Class"))).ToArray();
        // 超限仍可保留有限视图，但不能承诺完整树。
        var bounded = Build(nodes);
        Assert.AreEqual(512, bounded.Nodes.Length);
        Assert.AreEqual("INDETERMINATE", bounded.Status);
        // 深链每层为真实匿名表达式，不是rdf:rest链。
        var deep = Enumerable.Range(0, 34).Select(index => Triple(Blank("d" + index), Owl + "complementOf", index == 33 ? Iri("urn:C") : Blank("d" + (index + 1)))).ToArray();
        Assert.AreEqual("INDETERMINATE", Build(deep).Status);
        Assert.IsTrue(Build(deep).Diagnostics.Any(item => item.Code == "expression_budget_exceeded"));
    }

    /// <summary>预先取消不返回虚构完整投影。</summary>
    [TestMethod]
    public void ProjectionCancellationPropagates()
    {
        // 取消在实际遍历前就可见，无任何外部服务或副作用。
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();
        Assert.Throws<OperationCanceledException>(() => Build([], token: cancellation.Token));
    }

    /// <summary>全部高阶语料经真实RIOT读取，原词法、结构顺序和发布阻断并存。</summary>
    [TestMethod]
    public async Task RealRiotReadsAdvancedFixtureWithoutLosingSourceOrEnablingPublish()
    {
        // 只连接Master的本轮临时真实Jena，不以投影单测替代解析证据。
        var runtime = SemanticFixture.Runtime();
        // fixture从已提交样例恢复，不写死机器目录。
        var sources = ComplexSources();
        // 序列化前后原bundle不能因只读投影改变。
        var before = System.Text.Json.JsonSerializer.Serialize(sources);
        // 新接口走真实Execute和RIOT，而非手工构造解析结果。
        var projection = await ((IG3ExpressionRuntime)runtime).ProjectExpressionsAsync(sources, default);
        // 精确ontology源内的高阶表达式均可被结构化保留。
        var ontology = projection.Single(item => item.SourceId == "ontology");
        Assert.AreEqual("COMPLETE", ontology.Status);
        Assert.AreEqual("BLOCKED", ontology.PublishEligible);
        Assert.IsFalse(ontology.Inferred);
        Assert.IsFalse(ontology.Editable);
        Assert.AreEqual(before, System.Text.Json.JsonSerializer.Serialize(sources));
        CollectionAssert.AreEqual(new[] { "urn:synthetic:m5:p", "urn:synthetic:m5:q" }, ontology.Nodes.Single(node => node.Term == ontology.Nodes.Single(node => node.Term.Value == "urn:synthetic:m5:chain").Properties.Single(item => item.PredicateIri == Owl + "propertyChainAxiom").Values.Single()).OrderedItems.Select(item => item.Value).ToArray());
        Assert.IsTrue(ontology.Nodes.Any(item => item.Kind == "restriction"));
        Assert.IsTrue(ontology.Nodes.Any(item => item.Kind == "intersection"));
        Assert.IsTrue(ontology.Nodes.Any(item => item.Kind == "union"));
        Assert.IsTrue(ontology.Nodes.Any(item => item.Kind == "complement"));
        Assert.IsTrue(ontology.Diagnostics.Any(item => item.Code == "imports_not_loaded"));
        Assert.IsFalse((await runtime.ValidateAsync(sources, default)).Conforms);
        Assert.IsTrue(ontology.Diagnostics.All(item => item.Line is null && item.Column is null));
    }

    /// <summary>四源同名blank由RIOT分别解析，复杂Shapes只读可保留但不放开正式执行。</summary>
    [TestMethod]
    public async Task RealRiotSeparatesFourSourceBlankScopesAndPreservesLiteralMetadata()
    {
        // 相同源内blank写法相同，不同源值必须隔离。
        var sources = new SourceBundle { OntologyTurtle = "_:x <urn:p> \"本体\"@zh .", ShapesTurtle = "_:x <urn:p> \"约束\"@zh .", VocabularyTurtle = "_:x <urn:p> \"词汇\"@zh .", DataTurtle = "_:x <urn:p> \"001\"^^<urn:custom:type> ." };
        // 读取走新接口checkShapes:false，不能被旧ShapePolicy提前吞掉复杂结构。
        var result = await ((IG3ExpressionRuntime)SemanticFixture.Runtime()).ProjectExpressionsAsync(sources, default);
        Assert.AreEqual(4, result.Length);
        CollectionAssert.AreEqual(new[] { "本体", "约束", "词汇", "001" }, result.Select(source => source.Nodes.Single().Properties.Single().Values.Single().Value).ToArray());
        Assert.AreEqual("urn:custom:type", result[^1].Nodes.Single().Properties.Single().Values.Single().Datatype);
        Assert.IsTrue(result.All(source => source.Nodes.Single().Term.Value.StartsWith("_:", StringComparison.Ordinal)));
    }

    /// <summary>真实RIOT接受合法RDF但损坏OWL列表必须在投影失败关闭。</summary>
    [TestMethod]
    [DataRow("broken")]
    [DataRow("cycle")]
    [DataRow("cardinality")]
    [DataRow("unknown")]
    public async Task RealRiotMalformedOwlHasExplicitProjectionDiagnostics(string scenario)
    {
        // RDF语法均合法，反例针对高阶结构而不是自研Turtle解释。
        var source = scenario switch
        {
            "broken" => "_:x <" + Rdf + "first> <urn:A> .",
            "cycle" => "_:x <" + Rdf + "first> <urn:A> ; <" + Rdf + "rest> _:x .",
            "cardinality" => "_:x <" + Owl + "cardinality> \"-1\"^^<" + IntegerType + "> .",
            _ => "<urn:A> <" + Rdf + "type> <" + Owl + "ImaginaryClass> ."
        };
        // 不能由于RIOT解析成功就把结构完整性标PASS。
        var result = (await ((IG3ExpressionRuntime)SemanticFixture.Runtime()).ProjectExpressionsAsync(new SourceBundle { OntologyTurtle = source }, default))[0];
        Assert.AreEqual("INDETERMINATE", result.Status);
        Assert.IsFalse(result.ReadOnlyStructured);
        Assert.IsTrue(result.SourcePreserved);
    }

    /// <summary>真实RIOT接受合法RDF后，残缺或歧义restriction必须保留源并明确失败关闭。</summary>
    [TestMethod]
    [DataRow("missing-on-property")]
    [DataRow("some-literal")]
    [DataRow("all-literal")]
    [DataRow("qualified-literal-property")]
    [DataRow("multiple-constructors")]
    public async Task RealRiotRestrictionNegativeShapesPreserveSourceHash(string scenario)
    {
        // 所有分支均为合法Turtle/RDF；只改变OWL结构槽位，不能以解析失败代替目标诊断。
        var body = scenario switch
        {
            "missing-on-property" => "_:r a owl:Restriction ; owl:someValuesFrom <urn:C> .",
            "some-literal" => "_:r a owl:Restriction ; owl:onProperty <urn:p> ; owl:someValuesFrom \"urn:C\" .",
            "all-literal" => "_:r a owl:Restriction ; owl:onProperty <urn:p> ; owl:allValuesFrom \"urn:C\" .",
            "qualified-literal-property" => "_:r a owl:Restriction ; owl:onProperty \"urn:p\" ; owl:qualifiedCardinality \"1\"^^xsd:nonNegativeInteger ; owl:onClass <urn:C> .",
            _ => "_:r a owl:Restriction ; owl:onProperty <urn:p> ; owl:someValuesFrom <urn:C> ; owl:allValuesFrom <urn:D> ."
        };
        // 唯一固定标准prefix声明不会修复或掩盖任何restriction反例。
        var source = "@prefix owl: <" + Owl + "> .\n@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .\n" + body + "\n";
        // 原字节散列独立计算，不能用结果自身hash作期望值。
        var expectedHash = Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(source)));
        // 生产入口真实执行RIOT解析、暂存图回读和只读投影，不构造解析三元组替身。
        var result = (await ((IG3ExpressionRuntime)SemanticFixture.Runtime()).ProjectExpressionsAsync(new SourceBundle { OntologyTurtle = source }, default))[0];
        Assert.AreEqual("INDETERMINATE", result.Status);
        Assert.IsTrue(result.Diagnostics.Any(item => item.Code == "restriction_invalid"));
        Assert.IsTrue(result.SourcePreserved);
        Assert.AreEqual(expectedHash, result.SourceHash);
        Assert.IsFalse(result.ReadOnlyStructured);
        Assert.IsFalse(result.Editable);
        Assert.AreEqual("BLOCKED", result.PublishEligible);
        Assert.IsFalse(result.Inferred);
    }

    /// <summary>真实RIOT解析513个命名主体仍在triple/byte预算内，只读节点预算必须独立触发。</summary>
    [TestMethod]
    public async Task RealRiotNodeBudgetPreservesSourceAndFailsClosed()
    {
        // 每主体只有一条合法类声明，明确低于既有5000 triples及源字节预算。
        var source = string.Join('\n', Enumerable.Range(0, 513).Select(index => "<urn:synthetic:m5:budget:" + index + "> a <" + Owl + "Class> .")) + "\n";
        // 验证fixture规模，防止将源字节预算失败混作结构节点预算验收。
        var bytes = System.Text.Encoding.UTF8.GetBytes(source);
        Assert.IsTrue(bytes.Length < 256 * 1024);
        Assert.AreEqual(513, source.Split('\n', StringSplitOptions.RemoveEmptyEntries).Length);
        // 与实际投影返回独立的原文散列基线。
        var expectedHash = Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(bytes));
        // 通过真实生产运行时解析，RDF解析成功不能放开不完整结构的编辑/发布。
        var result = (await ((IG3ExpressionRuntime)SemanticFixture.Runtime()).ProjectExpressionsAsync(new SourceBundle { OntologyTurtle = source }, default))[0];
        Assert.AreEqual("INDETERMINATE", result.Status);
        Assert.IsTrue(result.Diagnostics.Any(item => item.Code == "expression_budget_exceeded"));
        Assert.AreEqual(512, result.Nodes.Length);
        Assert.IsTrue(result.SourcePreserved);
        Assert.AreEqual(expectedHash, result.SourceHash);
        Assert.IsFalse(result.ReadOnlyStructured);
        Assert.IsFalse(result.Editable);
        Assert.AreEqual("BLOCKED", result.PublishEligible);
        Assert.IsFalse(result.Inferred);
    }

    /// <summary>读取已提交高阶语料，保留注释、BOM及换行给真实服务链使用。</summary>
    internal static SourceBundle ComplexSources()
    {
        // 隔离harness只提供本仓库samples/g2路径，不读取历史环境。
        var samples = Environment.GetEnvironmentVariable("G2_SEM_SAMPLES");
        if (samples is null) Assert.Inconclusive("NOT_RUN: 需要本轮真实semantic-roundtrip样例目录。");
        return new SourceBundle { OntologyTurtle = File.ReadAllText(Path.Combine(Path.GetDirectoryName(samples)!, "g3", "m5", "advanced.owl.ttl")) };
    }

    /// <summary>直接调用内部纯投影检验边界；不把这些单测冒充真实RIOT验收。</summary>
    private static OwlExpressionSource Build(RdfTriple[] triples, string sourceId = "ontology", CancellationToken token = default)
    {
        // 反射只定位同模块固定类型，不接受输入中的类型或方法名。
        var type = typeof(JenaSemanticRuntime).Assembly.GetType("OntologyPlatform.Modules.Ontology.OwlExpressionProjection", throwOnError: true)!;
        try { return (OwlExpressionSource)type.GetMethod("Build", BindingFlags.NonPublic | BindingFlags.Static)!.Invoke(null, [sourceId, new string('a', 64), triples, true, token])!; }
        catch (TargetInvocationException exception) when (exception.InnerException is OperationCanceledException cancelled) { throw cancelled; }
    }

    /// <summary>构造完整合法restriction基线，词法回归不再依赖裸cardinality残缺图。</summary>
    private static RdfTriple[] Restriction(string predicate, RdfTerm value) =>
        [Triple(Blank("r"), Rdf + "type", Iri(Owl + "Restriction")), Triple(Blank("r"), Owl + "onProperty", Iri("urn:p")), Triple(Blank("r"), predicate, value)];

    /// <summary>构造明确IRI项。</summary>
    private static RdfTerm Iri(string value) => new() { Kind = RdfTermKind.Iri, Value = value };

    /// <summary>构造明确blank项，前缀异形用于真实codec兼容回归。</summary>
    private static RdfTerm Blank(string value) => new() { Kind = RdfTermKind.Blank, Value = value };

    /// <summary>保持literal词法、类型及语言的独立身份。</summary>
    private static RdfTerm Literal(string value, string? datatype = null, string? language = null) => new() { Kind = RdfTermKind.Literal, Value = value, Datatype = datatype, Language = language };

    /// <summary>构造已经解析的合成RDF事实，不解析Turtle。</summary>
    private static RdfTriple Triple(RdfTerm subject, string predicate, RdfTerm term) => new() { Subject = subject, Predicate = predicate, Object = term };
}
