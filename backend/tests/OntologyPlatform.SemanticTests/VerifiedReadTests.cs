using System.Text;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology.Domain;

namespace OntologyPlatform.SemanticTests;

/// <summary>用真实RIOT和TDB2验证实际消费批次与权威源、清单和快照的完整绑定。</summary>
[TestClass]
public sealed class VerifiedReadTests
{
    /// <summary>旧适配器没有新实现时必须503，禁止回退到旧的未核验读。</summary>
    [TestMethod]
    public async Task LegacyAdapterCannotFallbackToUnverifiedRead()
    {
        // 旧适配器仅用于测试接口默认行为，不冒充真实引擎验证。
        ISemanticRuntime runtime = new LegacyRuntime();
        // 默认方法必须在任何旧入口被调用前失败关闭。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ReadVerifiedPublishedAsync(new ReleaseManifest(), new SourceBundle(), CancellationToken.None));
        Assert.AreEqual(503, error.Status);
        Assert.AreEqual("verified_runtime_unavailable", error.Code);
    }

    /// <summary>正式图只读取一次，返回对账过的原数组；两次正式读取之间的变动不能触发二次取数。</summary>
    [TestMethod]
    public async Task VerifiedReadReturnsExactlyTheComparedBatch()
    {
        // 四源含非空词汇，验证本体正式图同时包含ontology与vocabulary。
        var source = Sources();
        // 部署及初始校验都访问真实引擎。
        ISemanticRuntime runtime = SemanticFixture.Runtime();
        // 完整权威清单从原文字节生成。
        var manifest = Manifest(source);
        await runtime.DeployAsync(manifest, source, CancellationToken.None);
        Assert.IsTrue(await runtime.VerifyAsync(manifest, source, CancellationToken.None));
        // 正式GET计数用来检出Verify后再Read产生的额外请求。
        var formalReads = 0;
        // 数据图请求发送前，本体图已经实际读完，此时真实修改本体存储。
        ISemanticRuntime gated = SemanticFixture.RuntimeWithGate(async (request, token) =>
        {
            if (request.Method != HttpMethod.Get || request.RequestUri!.AbsolutePath != "/ontology/data") return;
            if (Interlocked.Increment(ref formalReads) == 2)
                await ChangeGraphAsync(manifest.OntologyGraphIri, "<urn:changed> <urn:p> 1 .", token);
        });
        // 已读取的本体仍匹配源，返回的同批数据不可被随后读出的篡改图替换。
        var result = await gated.ReadVerifiedPublishedAsync(manifest, source, CancellationToken.None);
        Assert.AreEqual(2, formalReads);
        Assert.AreEqual(2, result.OntologyTriples.Length);
        Assert.IsTrue(result.OntologyTriples.Any(triple => triple.Subject.Value == "urn:verified:C"));
        Assert.IsTrue(result.OntologyTriples.Any(triple => triple.Subject.Value == "urn:verified:vocabulary"));
        Assert.IsFalse(result.OntologyTriples.Any(triple => triple.Subject.Value == "urn:changed"));
        Assert.AreEqual(2, result.DataTriples.Length);
        // 下一次读取看到真实篡改后必须失败，不能携带旧hash返回EMPTY或错误事实。
        var changed = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ReadVerifiedPublishedAsync(manifest, source, CancellationToken.None));
        Assert.AreEqual(503, changed.Status);
    }

    /// <summary>目录先前校验成功后发生篡改、删除或词法变化，正式消费仍失败关闭。</summary>
    [TestMethod]
    [DataRow("ontology")]
    [DataRow("data")]
    [DataRow("delete")]
    [DataRow("lexical")]
    public async Task ChangedPublishedGraphCannotReturnOldHashData(string scenario)
    {
        // typed lexical场景的权威源保留01，TDB2实际可能规范化为1。
        var source = scenario == "lexical" ? Sources() with { DataTurtle = "<urn:verified:i> <urn:verified:n> \"01\"^^<http://www.w3.org/2001/XMLSchema#integer> ." } : Sources();
        // 所有操作均调用真实Jena，不构造假的图响应。
        ISemanticRuntime runtime = SemanticFixture.Runtime();
        // 错误不来自清单字段缺省或无效hash。
        var manifest = Manifest(source);
        await runtime.DeployAsync(manifest, source, CancellationToken.None);
        if (scenario != "lexical")
        {
            Assert.IsTrue(await runtime.VerifyAsync(manifest, source, CancellationToken.None));
            // 目录已校验之后真实改变专属图，模拟被发现的二读窗口。
            await ChangeGraphAsync(scenario == "ontology" ? manifest.OntologyGraphIri : manifest.DataGraphIri, scenario == "delete" ? null : "<urn:tampered> <urn:p> 1 .", CancellationToken.None);
        }
        // 即使仍有三元组且HTTP200，也必须拒绝源与事实不一致。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ReadVerifiedPublishedAsync(manifest, source, CancellationToken.None));
        Assert.AreEqual(503, error.Status);
    }

    /// <summary>清单、快照、四源及组合hash逐项错版必须503；合法控制先证明新路径确实可用。</summary>
    [TestMethod]
    public async Task EveryManifestSnapshotAndSourceBindingIsChecked()
    {
        // 四个源都有独立hash，optional词汇也不能漏验。
        var source = Sources();
        // 同一真实运行时用于正控及各错版输入。
        ISemanticRuntime runtime = SemanticFixture.Runtime();
        // 正确字段全部显式提供。
        var manifest = Manifest(source);
        await runtime.DeployAsync(manifest, source, CancellationToken.None);
        Assert.AreEqual(2, (await runtime.ReadVerifiedPublishedAsync(manifest, source, CancellationToken.None)).DataTriples.Length);
        // 所有篡改只变一个绑定维度，不能由其他无效字段掩盖遗漏。
        var invalid = new[]
        {
            manifest with { SchemaVersion = 2 },
            manifest with { ReleaseId = Guid.NewGuid().ToString("N") },
            manifest with { OntologyGraphIri = manifest.DataGraphIri },
            manifest with { DataGraphIri = manifest.OntologyGraphIri },
            manifest with { Hashes = manifest.Hashes with { OntologyHash = "wrong" } },
            manifest with { Hashes = manifest.Hashes with { ShapesHash = "wrong" } },
            manifest with { Hashes = manifest.Hashes with { VocabularyHash = null } },
            manifest with { Hashes = manifest.Hashes with { DataHash = "wrong" } },
            manifest with { Hashes = manifest.Hashes with { BundleHash = "wrong" } },
            manifest with { Snapshot = manifest.Snapshot with { ReleaseId = Guid.NewGuid().ToString("N") } },
            manifest with { Snapshot = manifest.Snapshot with { OntologyGraphIri = manifest.DataGraphIri } },
            manifest with { Snapshot = manifest.Snapshot with { DataGraphIri = manifest.OntologyGraphIri } },
            manifest with { Snapshot = manifest.Snapshot with { OntologyHash = "wrong" } },
            manifest with { Snapshot = manifest.Snapshot with { ShapesHash = "wrong" } },
            manifest with { Snapshot = manifest.Snapshot with { VocabularyHash = null } },
            manifest with { Snapshot = manifest.Snapshot with { DataHash = "wrong" } }
        };
        foreach (var item in invalid)
        {
            // 各绑定的失败状态必须稳定，不暴露原文或抛未受控异常。
            var error = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ReadVerifiedPublishedAsync(item, source, CancellationToken.None));
            Assert.AreEqual(503, error.Status);
        }
        // 改源码注释虽不改变图，仍改变权威源hash，不能默许错版。
        var sourceError = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ReadVerifiedPublishedAsync(manifest, source with { OntologyTurtle = source.OntologyTurtle + "\n# changed" }, CancellationToken.None));
        Assert.AreEqual(503, sourceError.Status);
    }

    /// <summary>合法词汇缺席与null快照/清单故障有明确区别，不因默认空字符串误接受错版。</summary>
    [TestMethod]
    public async Task OptionalVocabularyAndMissingBindingFailClosed()
    {
        // absent词汇仍是完整且合法的三份权威源。
        var source = Sources() with { VocabularyTurtle = null };
        // 正控必须使用实际部署读取而不是固定数组。
        ISemanticRuntime runtime = SemanticFixture.Runtime();
        // 可选hash保持null参与BundleHash。
        var manifest = Manifest(source);
        await runtime.DeployAsync(manifest, source, CancellationToken.None);
        Assert.AreEqual(1, (await runtime.ReadVerifiedPublishedAsync(manifest, source, CancellationToken.None)).OntologyTriples.Length);
        // 模块内部空引用错误也必须稳定失败关闭。
        var emptySnapshot = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ReadVerifiedPublishedAsync(manifest with { Snapshot = null! }, source, CancellationToken.None));
        Assert.AreEqual(503, emptySnapshot.Status);
        // 缺失清单不能导致未受控NullReferenceException。
        var emptyManifest = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ReadVerifiedPublishedAsync(null!, source, CancellationToken.None));
        Assert.AreEqual(503, emptyManifest.Status);
    }

    /// <summary>同一受控执行预算覆盖解析到正式读，取消和五秒超时后必须清理已写入暂存图。</summary>
    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public async Task VerifiedReadCancellationAndTimeoutCleanTemporaryGraphs(bool callerCancels)
    {
        // 合法清单与源确保真正走入RIOT暂存，而不是在字段检查阶段短路。
        var source = Sources();
        // 所有正式图先由真实引擎部署。
        var manifest = Manifest(source);
        await SemanticFixture.Runtime().DeployAsync(manifest, source, CancellationToken.None);
        // 只延迟首次暂存GET，此时真实PUT已经完成。
        var blocked = 0;
        // gate保留真实HTTP，finally DELETE不受该延迟影响。
        ISemanticRuntime runtime = SemanticFixture.RuntimeWithGate(async (request, token) =>
        {
            if (request.Method == HttpMethod.Get && Interlocked.Exchange(ref blocked, 1) == 0)
                await Task.Delay(Timeout.InfiniteTimeSpan, token);
        });
        // 取消不得转成成功或不可用结果；内部预算则映射固定503。
        using var cancellation = new CancellationTokenSource();
        if (callerCancels) cancellation.CancelAfter(TimeSpan.FromMilliseconds(150));
        // 整体任务只占一个运行时并发槽位。
        var task = runtime.ReadVerifiedPublishedAsync(manifest, source, cancellation.Token);
        if (callerCancels) await Assert.ThrowsAsync<OperationCanceledException>(() => task);
        else
        {
            // 超时分类来自共享Execute，与旧解析入口保持一致。
            var error = await Assert.ThrowsAsync<SemanticOperationException>(() => task);
            Assert.AreEqual(503, error.Status);
            Assert.AreEqual("semantic_timeout", error.Code);
        }
        Assert.AreEqual(1, blocked);
    }

    /// <summary>单源业务三元组边界不包含内部marker，4999和5000合法，5001明确拒绝。</summary>
    [TestMethod]
    [DataRow(4999)]
    [DataRow(5000)]
    [DataRow(5001)]
    public async Task TemporaryMarkerDoesNotConsumeBusinessTripleBudget(int count)
    {
        // 同主体同谓词短literal避免无关节点、边和字节预算掩盖三元组边界。
        var source = new SourceBundle { OntologyTurtle = BoundedTriples(count) };
        // 计数来自真实RIOT而非预置JSON。
        var runtime = SemanticFixture.Runtime();
        if (count <= 5000)
        {
            // 投影必须包含全部业务三元组，既不少一条也不包含marker。
            var analysis = await runtime.AnalyzeAsync(source, 1, CancellationToken.None);
            Assert.AreEqual(count, analysis.Projection.Triples.Length);
            Assert.AreEqual(OntologyRules.Hash(source.OntologyTurtle), analysis.Hashes.OntologyHash);
        }
        else
        {
            // 超过业务上限仍返回明确拒绝，不因多容纳内部marker而放宽业务图。
            var error = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.AnalyzeAsync(source, 1, CancellationToken.None));
            Assert.AreEqual(422, error.Status);
            Assert.AreEqual("rdf_triple_budget", error.Code);
        }
    }

    /// <summary>正式同批读维持四源合计预算，合法总量4999/5000成功、5001失败且不访问正式图。</summary>
    [TestMethod]
    [DataRow(4999)]
    [DataRow(5000)]
    [DataRow(5001)]
    public async Task VerifiedReadRetainsAggregateBusinessTripleBudget(int count)
    {
        // ontology一条且data非空，避免空正式图缺失规则干扰合计预算测试。
        var source = Sources() with { VocabularyTurtle = null, DataTurtle = BoundedTriples(count - 1) };
        // 全部hash与snapshot都精确绑定当前合成源。
        var manifest = Manifest(source);
        // 统计实际正式GET，合法路径仍只能读取每图一次。
        var formalReads = 0;
        // 只计数真实HTTP请求，不拦截或伪造响应。
        ISemanticRuntime runtime = SemanticFixture.RuntimeWithGate((request, _) =>
        {
            if (request.Method == HttpMethod.Get && request.RequestUri!.AbsolutePath == "/ontology/data") Interlocked.Increment(ref formalReads);
            return Task.CompletedTask;
        });
        if (count <= 5000)
        {
            await runtime.DeployAsync(manifest, source, CancellationToken.None);
            // 正式读返回同批完整业务三元组，不能由内部marker挤占一条。
            var result = await runtime.ReadVerifiedPublishedAsync(manifest, source, CancellationToken.None);
            Assert.AreEqual(count, result.OntologyTriples.Length + result.DataTriples.Length);
            Assert.AreEqual(2, formalReads);
        }
        else
        {
            // 两个单源各自不过限但合计5001，必须在正式访问前失败关闭。
            var error = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ReadVerifiedPublishedAsync(manifest, source, CancellationToken.None));
            Assert.AreEqual(503, error.Status);
            Assert.AreEqual(0, formalReads);
        }
    }

    /// <summary>5001条真实正式图读取仍受原5000上限约束，临时marker许可不能泄漏到正式读。</summary>
    [TestMethod]
    public async Task PublishedGraphDoesNotReceiveTemporaryMarkerAllowance()
    {
        // 合法源总计5000且两个正式图都非空。
        var source = Sources() with { VocabularyTurtle = null, DataTurtle = BoundedTriples(4999) };
        // 当前清单严格绑定源，而后续故障注入只改变真实正式data图。
        var manifest = Manifest(source);
        // 生产运行时走真实部署与读回。
        ISemanticRuntime runtime = SemanticFixture.Runtime();
        await runtime.DeployAsync(manifest, source, CancellationToken.None);
        await ChangeGraphAsync(manifest.DataGraphIri, BoundedTriples(5001), CancellationToken.None);
        // 原受控低层读也不得一般性接受额外一条业务数据。
        var direct = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ReadPublishedAsync(manifest.Snapshot, CancellationToken.None));
        Assert.AreEqual(422, direct.Status);
        Assert.AreEqual("rdf_triple_budget", direct.Code);
        // 消费边界把损坏正式资产映射不可用，不返回截断成功。
        var verified = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ReadVerifiedPublishedAsync(manifest, source, CancellationToken.None));
        Assert.AreEqual(503, verified.Status);
    }

    /// <summary>生成一个主体和短字面量组成的指定数量业务三元组，不触发其他资源上限。</summary>
    private static string BoundedTriples(int count) => string.Join('\n', Enumerable.Range(0, count).Select(index => $"<urn:s> <urn:p> \"{index}\" ."));

    /// <summary>仓库Synthetic标签与来源断言中的非BMP字符必须通过真实校验和正式同批读取。</summary>
    [TestMethod]
    [DataRow("😀")]
    [DataRow("𠀀")]
    public async Task SyntheticNonBmpLabelSurvivesValidationAndPublication(string label)
    {
        // 原样复现AI的唯一变更：同时替换业务标签和来源断言里的同一字面值。
        var source = SemanticFixture.Sources();
        source = source with { DataTurtle = source.DataTurtle.Replace("炉次heat-1", label, StringComparison.Ordinal) };
        // 保存原始字节事实，运行时不得为了兼容而重写权威源。
        var originalData = source.DataTurtle;
        // 全链均使用脚本创建的真实Jena。
        ISemanticRuntime runtime = SemanticFixture.Runtime();
        // 清单与快照hash严格来自原始UTF8源。
        var manifest = Manifest(source);
        Assert.AreEqual(manifest.Hashes, (await runtime.AnalyzeAsync(source, 1, CancellationToken.None)).Hashes);
        // 此步会经由完整图导出再Load，是旧Unicode错误的实际触发点。
        var report = await runtime.ValidateAsync(source, CancellationToken.None);
        Assert.IsTrue(report.Conforms);
        Assert.AreEqual(manifest.Hashes, report.Hashes);
        await runtime.DeployAsync(manifest, source, CancellationToken.None);
        Assert.IsTrue(await runtime.VerifyAsync(manifest, source, CancellationToken.None));
        // 真正正式回读不能把非BMP字符丢掉或替换成replacement character。
        var result = await runtime.ReadVerifiedPublishedAsync(manifest, source, CancellationToken.None);
        Assert.IsTrue(result.DataTriples.Count(triple => triple.Object.Kind == RdfTermKind.Literal && triple.Object.Value == label) >= 2);
        Assert.AreEqual(originalData, source.DataTurtle);
        Assert.AreEqual(OntologyRules.Hash(originalData), manifest.Hashes.DataHash);
    }

    /// <summary>编辑导出的标准literal应完整保留所有控制字符、引号、反斜线、字面转义与非BMP，且无法注入三元组。</summary>
    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public async Task NonBmpLiteralEditIsLosslessAndCannotInjectTriples(bool languageTagged)
    {
        // ontology源保留注释，真正结构变更后格式变化允许但必须有实际内容差异。
        var source = Sources() with { OntologyTurtle = "# 原始注释\n<urn:verified:C> a <http://www.w3.org/2002/07/owl#Class> ; <http://www.w3.org/2000/01/rdf-schema#label> \"旧标签\" .\n" };
        // 全C0/C1控制字符与恶意分隔符均作为数据值，不能变成RDF语法。
        var value = "😀𠀀 引号\" 反斜线\\ 字面\\uD83D\\uDE00\\U0001F600 \" . <urn:injected> <urn:p> <urn:o> . #\n" + string.Concat(Enumerable.Range(0, 32).Concat(Enumerable.Range(127, 33)).Select(code => (char)code));
        // 语言和datatype两个分支都必须保留精确词法。
        var replacement = new RdfTerm { Kind = RdfTermKind.Literal, Value = value, Language = languageTagged ? "zh" : null, Datatype = languageTagged ? null : "urn:unicode:literal" };
        // 真实RIOT给出旧对象的完整类型信息，避免凭字符串猜测类型。
        ISemanticRuntime runtime = SemanticFixture.Runtime();
        // 取真实源三元组进行一次精确编辑。
        var analysis = await runtime.AnalyzeAsync(source, 1, CancellationToken.None);
        // 唯一label是待编辑目标，其余图必须完整保留。
        var oldLabel = analysis.Projection.Triples.Single(triple => triple.Predicate == "http://www.w3.org/2000/01/rdf-schema#label");
        // 新源码来自生产Term导出，不能使用测试自行转义来掩盖错误。
        var edited = await runtime.ApplyEditAsync(source, new SemanticEdit { SubjectIri = oldLabel.Subject.Value, PredicateIri = oldLabel.Predicate, OldObject = oldLabel.Object, NewObject = replacement }, CancellationToken.None);
        Assert.AreNotEqual(source.OntologyTurtle, edited.OntologyTurtle);
        Assert.AreNotEqual(analysis.Hashes.OntologyHash, OntologyRules.Hash(edited.OntologyTurtle));
        // 导出再交给真实RIOT，检验值而非仅比较序列化字符串。
        var reparsed = await runtime.AnalyzeAsync(edited, 2, CancellationToken.None);
        Assert.AreEqual(2, reparsed.Projection.Triples.Length);
        Assert.IsFalse(reparsed.Projection.Triples.Any(triple => triple.Subject.Value == "urn:injected"));
        // 语言字面量会由标准RIOT补rdf:langString，分别核对语义字段。
        var actual = reparsed.Projection.Triples.Single(triple => triple.Predicate == oldLabel.Predicate).Object;
        Assert.AreEqual(value, actual.Value);
        Assert.AreEqual(replacement.Language, actual.Language);
        if (!languageTagged) Assert.AreEqual(replacement.Datatype, actual.Datatype);
        Assert.AreEqual(edited, await runtime.ApplyEditAsync(edited, new SemanticEdit { SubjectIri = oldLabel.Subject.Value, PredicateIri = oldLabel.Predicate, OldObject = actual, NewObject = actual }, CancellationToken.None));
        Assert.IsTrue((await runtime.ValidateAsync(edited, CancellationToken.None)).Conforms);
        // 正式发布及同批读取不能在二次导出时再次损失Unicode或控制字符。
        var manifest = Manifest(edited);
        await runtime.DeployAsync(manifest, edited, CancellationToken.None);
        Assert.IsTrue(await runtime.VerifyAsync(manifest, edited, CancellationToken.None));
        // 返回数组的字面量词法必须与调用方给定的新值逐字符一致。
        var published = await runtime.ReadVerifiedPublishedAsync(manifest, edited, CancellationToken.None);
        Assert.AreEqual(value, published.OntologyTriples.Single(triple => triple.Subject == oldLabel.Subject && triple.Predicate == oldLabel.Predicate).Object.Value);
        Assert.AreEqual(2, published.OntologyTriples.Count(triple => triple.Subject.Value == "urn:verified:C"));
    }

    /// <summary>不完整UTF16代理项不能被导出器悄悄替换成另一个RDF字面量。</summary>
    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public async Task InvalidSurrogateLiteralIsRejectedWithoutReplacement(bool highSurrogate)
    {
        // 通过真实RIOT解析合法原图，只将编辑输入的新字面量设为不完整代理项。
        var runtime = SemanticFixture.Runtime();
        // 构造无合法Unicode标量对应的单独高/低代理项，不把有效非BMP误判无效。
        var value = new string((char)(highSurrogate ? 0xD800 : 0xDC00), 1);
        // 生产导出器必须拒绝，而非替换成U+FFFD并返回看似成功的新源码。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ApplyEditAsync(Sources(), new SemanticEdit { SubjectIri = "urn:verified:C", PredicateIri = "http://www.w3.org/2000/01/rdf-schema#label", NewObject = new RdfTerm { Kind = RdfTermKind.Literal, Value = value } }, CancellationToken.None));
        Assert.AreEqual(422, error.Status);
        Assert.AreEqual("rdf_literal_invalid", error.Code);
    }

    /// <summary>四源leading BOM只影响临时解析视图，原文hash、no-op及literal内FEFF都必须保留。</summary>
    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public async Task LeadingBomSourcesKeepExactBytesAndRelativeIris(bool vocabularyOnlyBom)
    {
        // 全部四源带BOM，optional词汇分别覆盖仅BOM空图与含业务字面量。
        var source = new SourceBundle
        {
            OntologyTurtle = "\uFEFF# 本体原注释\n<#C> a <http://www.w3.org/2002/07/owl#Class> ; <http://www.w3.org/2000/01/rdf-schema#label> \"中\uFEFF文😀𠀀\"@zh .\n",
            ShapesTurtle = "\uFEFF@prefix sh: <http://www.w3.org/ns/shacl#> .\n",
            VocabularyTurtle = vocabularyOnlyBom ? "\uFEFF" : "\uFEFF<#term> <http://www.w3.org/2000/01/rdf-schema#label> \"词\uFEFF汇\" .\n",
            DataTurtle = "\uFEFF<#i> a <https://ontology.invalid/source/0/#C> ; <http://www.w3.org/2000/01/rdf-schema#comment> \"数\uFEFF据\" .\n"
        };
        // 固定清单散列根据包含BOM的完整原始UTF8计算。
        var manifest = Manifest(source);
        // 唯一生产解析器必须接受合法leading BOM而非将其移到BASE之后。
        ISemanticRuntime runtime = SemanticFixture.Runtime();
        // 两次随机暂存图解析仍必须得到稳定默认文档基址。
        var first = await runtime.AnalyzeAsync(source, 1, CancellationToken.None);
        // 第二次真实解析必须保持相同默认文档IRI，不含随机暂存身份。
        var second = await runtime.AnalyzeAsync(source, 1, CancellationToken.None);
        Assert.AreEqual(manifest.Hashes, first.Hashes);
        CollectionAssert.AreEquivalent(first.Projection.Triples, second.Projection.Triples);
        Assert.AreEqual(2, first.Projection.Triples.Length);
        Assert.IsTrue(first.Projection.Triples.All(triple => triple.Subject.Value == "https://ontology.invalid/source/0/#C"));
        // 中间FEFF是合法词法内容，不能随leading BOM处理被全局删除。
        var label = first.Projection.Triples.Single(triple => triple.Predicate == "http://www.w3.org/2000/01/rdf-schema#label");
        Assert.AreEqual("中\uFEFF文😀𠀀", label.Object.Value);
        // no-op编辑应原样返回全部SourceBundle，包括四个起始BOM与注释。
        Assert.AreEqual(source, await runtime.ApplyEditAsync(source, new SemanticEdit { SubjectIri = label.Subject.Value, PredicateIri = label.Predicate, OldObject = label.Object, NewObject = label.Object }, CancellationToken.None));
        // SHACL的Shapes请求也经同一SourceDocument，须直接证明真实执行成功。
        var report = await runtime.ValidateAsync(source, CancellationToken.None);
        Assert.IsTrue(report.Conforms);
        Assert.AreEqual(manifest.Hashes, report.Hashes);
        await runtime.DeployAsync(manifest, source, CancellationToken.None);
        Assert.IsTrue(await runtime.VerifyAsync(manifest, source, CancellationToken.None));
        // 正式同批读保留各自默认base及literal词法，不从原文BOM生成业务三元组。
        var result = await runtime.ReadVerifiedPublishedAsync(manifest, source, CancellationToken.None);
        Assert.AreEqual(vocabularyOnlyBom ? 2 : 3, result.OntologyTriples.Length);
        Assert.IsTrue(result.DataTriples.All(triple => triple.Subject.Value == "https://ontology.invalid/source/3/#i"));
        Assert.IsTrue(result.DataTriples.Any(triple => triple.Object.Value == "数\uFEFF据"));
        if (!vocabularyOnlyBom) Assert.IsTrue(result.OntologyTriples.Any(triple => triple.Subject.Value == "https://ontology.invalid/source/2/#term" && triple.Object.Value == "词\uFEFF汇"));
        Assert.IsTrue(source.OntologyTurtle.StartsWith('\uFEFF'));
        Assert.IsTrue(source.ShapesTurtle.StartsWith('\uFEFF'));
        Assert.IsTrue(source.VocabularyTurtle!.StartsWith('\uFEFF'));
        Assert.IsTrue(source.DataTurtle.StartsWith('\uFEFF'));
    }

    /// <summary>精确字节散列的测试清单不依赖生产序列化器构造期望值。</summary>
    private static ReleaseManifest Manifest(SourceBundle source)
    {
        // 正式图只能从服务器生成的GuidN派生。
        var id = Guid.NewGuid().ToString("N");
        // 单独散列每个源，null词汇与空源保持不同。
        var hashes = new SourceHashes { OntologyHash = OntologyRules.Hash(source.OntologyTurtle), ShapesHash = OntologyRules.Hash(source.ShapesTurtle), VocabularyHash = source.VocabularyTurtle is null ? null : OntologyRules.Hash(source.VocabularyTurtle), DataHash = OntologyRules.Hash(source.DataTurtle) };
        hashes = hashes with { BundleHash = OntologyRules.Hash(string.Join('\n', hashes.OntologyHash, hashes.ShapesHash, hashes.VocabularyHash ?? "absent", hashes.DataHash)) };
        // 同一版本快照显式复制所有source/graph字段。
        var snapshot = new AssetVersionSnapshot { ReleaseId = id, OntologyHash = hashes.OntologyHash, ShapesHash = hashes.ShapesHash, VocabularyHash = hashes.VocabularyHash, DataHash = hashes.DataHash, OntologyGraphIri = "urn:ontology-platform:release:" + id + ":ontology", DataGraphIri = "urn:ontology-platform:release:" + id + ":data" };
        return new ReleaseManifest { SchemaVersion = 1, ReleaseId = id, AssetId = "verified-asset", DraftId = "verified-draft", Revision = 1, Scope = new ResourceScope { OrganizationId = "test-org", SiteIds = ["test-site"] }, Hashes = hashes, OntologyGraphIri = snapshot.OntologyGraphIri, DataGraphIri = snapshot.DataGraphIri, Snapshot = snapshot, CreatedAtUtc = DateTimeOffset.UtcNow };
    }

    /// <summary>四源只用标准RDF，不依赖行业类或外部网络。</summary>
    private static SourceBundle Sources() => new() { OntologyTurtle = "<urn:verified:C> a <http://www.w3.org/2002/07/owl#Class> .", ShapesTurtle = "@prefix sh: <http://www.w3.org/ns/shacl#> .\n", VocabularyTurtle = "<urn:verified:vocabulary> <http://www.w3.org/2000/01/rdf-schema#label> \"词汇\"@zh .", DataTurtle = "<urn:verified:i> a <urn:verified:C> ; <http://www.w3.org/2000/01/rdf-schema#comment> 1 ." };

    /// <summary>只改变当前fixture内指定的正式测试图，响应仍由实际GSP产生。</summary>
    private static async Task ChangeGraphAsync(string graph, string? source, CancellationToken token)
    {
        // 地址只来自测试脚本新建的随机回环端口，无历史状态/凭证。
        var origin = Environment.GetEnvironmentVariable("G2_SEM_JENA_ORIGIN") ?? throw new InvalidOperationException("缺少隔离Jena。");
        // 仅测试故障注入，不开放生产任意图写入口。
        using var client = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false });
        // null表示真实删除，其他值是实际PUT到测试专属图的Turtle。
        using var request = new HttpRequestMessage(source is null ? HttpMethod.Delete : HttpMethod.Put, origin + "/ontology/data?graph=" + Uri.EscapeDataString(graph));
        if (source is not null) request.Content = new StringContent(source, Encoding.UTF8, "text/turtle");
        // 未成功注入不能把后续测试当作证明。
        using var response = await client.SendAsync(request, token);
        response.EnsureSuccessStatusCode();
    }

    /// <summary>保留旧接口形状的测试适配器，任何旧入口调用都揭露禁止的降级。</summary>
    private sealed class LegacyRuntime : ISemanticRuntime
    {
        /// <summary>默认新方法不得通过旧解析入口降级。</summary>
        public Task<SemanticAnalysis> AnalyzeAsync(SourceBundle sources, long revision, CancellationToken cancellationToken) => throw new AssertFailedException("不应调用旧解析入口。");

        /// <summary>默认新方法不得通过旧校验入口降级。</summary>
        public Task<SemanticValidationReport> ValidateAsync(SourceBundle sources, CancellationToken cancellationToken) => throw new AssertFailedException("不应调用旧校验入口。");

        /// <summary>默认新方法不得写入草稿。</summary>
        public Task<SourceBundle> ApplyEditAsync(SourceBundle sources, SemanticEdit edit, CancellationToken cancellationToken) => throw new AssertFailedException("不应调用旧编辑入口。");

        /// <summary>默认新方法不得部署新图。</summary>
        public Task DeployAsync(ReleaseManifest manifest, SourceBundle sources, CancellationToken cancellationToken) => throw new AssertFailedException("不应调用旧部署入口。");

        /// <summary>默认新方法不得先Verify后单独再读。</summary>
        public Task<bool> VerifyAsync(ReleaseManifest manifest, SourceBundle sources, CancellationToken cancellationToken) => throw new AssertFailedException("不应调用旧Verify入口。");

        /// <summary>默认新方法不得读取未核验正式事实。</summary>
        public Task<PublishedRdfData> ReadPublishedAsync(AssetVersionSnapshot snapshot, CancellationToken cancellationToken) => throw new AssertFailedException("不应调用旧Read入口。");
    }
}
