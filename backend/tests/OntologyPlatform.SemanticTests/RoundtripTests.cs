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

    /// <summary>真实TDB2按隔离版本部署和回读，验证词法规范化不能悄悄宣称相同。</summary>
    [TestMethod]
    public async Task PublishedGraphsAreIsolatedAndLexicalMismatchIsRejected()
    {
        // 测试脚本提供真实临时TDB2且结束后删除整个容器。
        var runtime = SemanticFixture.Runtime();
        // 使用规范字面量的最小版本不依赖行业特定逻辑。
        var sources = new SourceBundle { OntologyTurtle = "<urn:test:C> a <http://www.w3.org/2002/07/owl#Class> .", DataTurtle = "<urn:test:i> a <urn:test:C> ; <urn:test:n> 1 ." };
        // 实际解析散列用于绑定发布清单。
        var analysis = await runtime.AnalyzeAsync(sources, 1, CancellationToken.None);
        // 正式图仅按服务端GuidN派生。
        var id = Guid.NewGuid().ToString("N");
        // 快照和清单必须使用同一不可变版本。
        var snapshot = new AssetVersionSnapshot { ReleaseId = id, OntologyHash = analysis.Hashes.OntologyHash, ShapesHash = analysis.Hashes.ShapesHash, DataHash = analysis.Hashes.DataHash, OntologyGraphIri = "urn:ontology-platform:release:" + id + ":ontology", DataGraphIri = "urn:ontology-platform:release:" + id + ":data" };
        // 清单中的hash由真实源派生，不能客户端自行编写。
        var manifest = new ReleaseManifest { SchemaVersion = 1, ReleaseId = id, Hashes = analysis.Hashes, OntologyGraphIri = snapshot.OntologyGraphIri, DataGraphIri = snapshot.DataGraphIri, Snapshot = snapshot };
        await runtime.DeployAsync(manifest, sources, CancellationToken.None);
        Assert.IsTrue(await runtime.VerifyAsync(manifest, sources, CancellationToken.None));
        // 正式读确实返回当前版本图数据。
        var published = await runtime.ReadPublishedAsync(snapshot, CancellationToken.None);
        Assert.IsTrue(published.DataTriples.Any(triple => triple.Predicate == "urn:test:n" && triple.Object.Value == "1"));
        // 第二版本包含TDB2可能规范化的原始typed lexical，不能改变第一图。
        var lexical = sources with { DataTurtle = "<urn:test:i> a <urn:test:C> ; <urn:test:n> \"01\"^^<http://www.w3.org/2001/XMLSchema#integer> ." };
        // 第二图与第一个版本完全隔离。
        var second = Guid.NewGuid().ToString("N");
        // 保存权威字节散列，即使图规范化也不可篡改。
        var lexicalAnalysis = await runtime.AnalyzeAsync(lexical, 2, CancellationToken.None);
        // 使用新的图名，绝不覆盖旧发布。
        var secondManifest = manifest with { ReleaseId = second, Hashes = lexicalAnalysis.Hashes, OntologyGraphIri = "urn:ontology-platform:release:" + second + ":ontology", DataGraphIri = "urn:ontology-platform:release:" + second + ":data" };
        await runtime.DeployAsync(secondManifest, lexical, CancellationToken.None);
        Assert.IsFalse(await runtime.VerifyAsync(secondManifest, lexical, CancellationToken.None));
        Assert.IsTrue(await runtime.VerifyAsync(manifest, sources, CancellationToken.None));
    }

    /// <summary>完全空图的标准SHACL验证也应有真实报告，而非错误503。</summary>
    [TestMethod]
    public async Task EmptyGraphStillProducesRealShaclReport()
    {
        // 空源码是有效的Turtle文档，不能假称依赖故障。
        var runtime = SemanticFixture.Runtime();
        // Jena实际空图报告必须仍有标准conforms和报告hash。
        var report = await runtime.ValidateAsync(new SourceBundle(), CancellationToken.None);
        Assert.IsTrue(report.Conforms);
        Assert.AreEqual(ValidationKind.ShaclCore, report.Kind);
    }

    /// <summary>仅注释、空白或prefix仍由真实RIOT解析为空图，原文和散列保持不变。</summary>
    [TestMethod]
    [DataRow("# comment\n")]
    [DataRow(" \t\r\n")]
    [DataRow("@prefix ex: <urn:empty:> .\n")]
    public async Task LegalEmptyDocumentsKeepExactHashesAndProduceEmptyGraph(string ontology)
    {
        // 同时覆盖仅prefix的Shapes及其他两类合法空文档。
        var source = new SourceBundle { OntologyTurtle = ontology, ShapesTurtle = "@prefix sh: <http://www.w3.org/ns/shacl#> .\n", VocabularyTurtle = "# vocabulary", DataTurtle = " \n" };
        // 每个请求必须真实执行RIOT，而不是猜测源码关键字。
        var runtime = SemanticFixture.Runtime();
        // 权威hash始终依据调用方完整原文。
        var analysis = await runtime.AnalyzeAsync(source, 1, CancellationToken.None);
        Assert.AreEqual(0, analysis.Projection.Triples.Length);
        Assert.AreEqual(OntologyPlatform.Modules.Ontology.Domain.OntologyRules.Hash(ontology), analysis.Hashes.OntologyHash);
        Assert.AreEqual(OntologyPlatform.Modules.Ontology.Domain.OntologyRules.Hash(source.ShapesTurtle), analysis.Hashes.ShapesHash);
        // 官方SHACL真实返回空图符合，不生成伪造报告。
        var report = await runtime.ValidateAsync(source, CancellationToken.None);
        Assert.IsTrue(report.Conforms);
        Assert.AreEqual(analysis.Hashes, report.Hashes);
        Assert.AreEqual(ontology, source.OntologyTurtle);
        Assert.AreEqual("@prefix sh: <http://www.w3.org/ns/shacl#> .\n", source.ShapesTurtle);
    }

    /// <summary>空图上的真实新增只能导出业务三元组，解析辅助内容不得泄漏。</summary>
    [TestMethod]
    public async Task EditingLegalEmptyDocumentExportsOnlyRequestedTriple()
    {
        // 空文档保留注释到首次真正业务变更为止。
        var source = new SourceBundle { OntologyTurtle = "# comment\n", ShapesTurtle = "@prefix sh: <http://www.w3.org/ns/shacl#> .\n" };
        // 使用真实RIOT和正式编辑服务路径。
        var runtime = SemanticFixture.Runtime();
        // 单一新增是最终图中的唯一三元组。
        var edited = await runtime.ApplyEditAsync(source, new SemanticEdit { SubjectIri = "urn:empty:C", PredicateIri = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type", NewObject = new RdfTerm { Kind = RdfTermKind.Iri, Value = "http://www.w3.org/2002/07/owl#Class" } }, CancellationToken.None);
        Assert.AreEqual("<urn:empty:C> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <http://www.w3.org/2002/07/owl#Class> .\n", edited.OntologyTurtle);
        Assert.AreEqual(source.ShapesTurtle, edited.ShapesTurtle);
        // 再解析不能出现额外投影节点或内部三元组。
        var analysis = await runtime.AnalyzeAsync(edited, 2, CancellationToken.None);
        Assert.AreEqual(1, analysis.Projection.Triples.Length);
    }

    /// <summary>真实临时图丢失或被替换必须503，不能把运行时重启等故障当合法空图。</summary>
    [TestMethod]
    [DataRow(false)]
    [DataRow(true)]
    public async Task LostOrReplacedTemporaryGraphRemainsUnavailable(bool replace)
    {
        // 在真实PUT之后、首次GET之前注入真实图删除或替换。
        var intercepted = 0;
        // 测试钩子不伪造响应，实际引擎决定随后GET结果。
        var runtime = SemanticFixture.RuntimeWithGate(async (request, token) =>
        {
            if (request.Method != HttpMethod.Get || Interlocked.Exchange(ref intercepted, 1) != 0) return;
            // 仅操作本次运行时生成的临时图，不触碰其他请求或正式图。
            using var client = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false });
            // 替换场景留下可读的真实图，验证存在性之外的完整性检查。
            using var change = new HttpRequestMessage(replace ? HttpMethod.Put : HttpMethod.Delete, request.RequestUri);
            if (replace) change.Content = new StringContent("<urn:replaced> <urn:p> 1 .", System.Text.Encoding.UTF8, "text/turtle");
            // 真实GSP成功才可继续检验生产回读。
            using var response = await client.SendAsync(change, token);
            response.EnsureSuccessStatusCode();
        });
        // 非空文档确保旧实现也会走真实GSP回读。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.AnalyzeAsync(new SourceBundle { OntologyTurtle = "<urn:original> <urn:p> 1 ." }, 1, CancellationToken.None));
        Assert.AreEqual(503, error.Status);
        Assert.AreEqual(1, intercepted);
    }

    /// <summary>正式非空图被删除时仍明确不可用，临时空文档支持不放宽正式回读。</summary>
    [TestMethod]
    public async Task MissingPublishedGraphRemainsUnavailable()
    {
        // 使用真实临时TDB2部署两个非空正式图。
        var runtime = SemanticFixture.Runtime();
        // 业务源不存在空图歧义。
        var source = new SourceBundle { OntologyTurtle = "<urn:C> a <http://www.w3.org/2002/07/owl#Class> .", DataTurtle = "<urn:i> a <urn:C> ." };
        // 散列来自实际源解析。
        var analysis = await runtime.AnalyzeAsync(source, 1, CancellationToken.None);
        // 服务端派生独立发布ID，测试不激活版本。
        var id = Guid.NewGuid().ToString("N");
        // 真实部署和回读共享同一不可变图名。
        var snapshot = new AssetVersionSnapshot { ReleaseId = id, OntologyGraphIri = "urn:ontology-platform:release:" + id + ":ontology", DataGraphIri = "urn:ontology-platform:release:" + id + ":data" };
        // 精确源绑定保持正式部署的原有合同。
        var manifest = new ReleaseManifest { SchemaVersion = 1, ReleaseId = id, Hashes = analysis.Hashes, OntologyGraphIri = snapshot.OntologyGraphIri, DataGraphIri = snapshot.DataGraphIri, Snapshot = snapshot };
        await runtime.DeployAsync(manifest, source, CancellationToken.None);
        Assert.AreEqual(1, (await runtime.ReadPublishedAsync(snapshot, CancellationToken.None)).DataTriples.Length);
        // 只删除刚部署的该测试专属数据图，模拟正式存储图丢失。
        using var client = new HttpClient(new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false });
        // 地址仅来自脚本的独占随机端口，绝不读取历史环境。
        using var response = await client.DeleteAsync(Environment.GetEnvironmentVariable("G2_SEM_JENA_ORIGIN") + "/ontology/data?graph=" + Uri.EscapeDataString(snapshot.DataGraphIri));
        response.EnsureSuccessStatusCode();
        // 正式查询与部署回验都不能吞掉404。
        var readError = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.ReadPublishedAsync(snapshot, CancellationToken.None));
        Assert.AreEqual(503, readError.Status);
        // Verify必须失败关闭而不是宣称空图正确。
        var verifyError = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.VerifyAsync(manifest, source, CancellationToken.None));
        Assert.AreEqual(503, verifyError.Status);
    }

    /// <summary>正式回验必须包含本体中的subClassOf，不能只校验data图而漏掉继承目标。</summary>
    [TestMethod]
    public async Task PublishedShaclUsesTheSameOntologyContext()
    {
        // 真实隔离运行时使用实际RDFS目标继承行为。
        var runtime = SemanticFixture.Runtime();
        // 子类事实缺少父类Shape所要求的字段。
        var source = new SourceBundle
        {
            OntologyTurtle = "<urn:C> a <http://www.w3.org/2002/07/owl#Class> ; <http://www.w3.org/2000/01/rdf-schema#subClassOf> <urn:P> . <urn:P> a <http://www.w3.org/2002/07/owl#Class> .",
            DataTurtle = "<urn:i> a <urn:C> .",
            ShapesTurtle = "@prefix sh: <http://www.w3.org/ns/shacl#> . <urn:S> a sh:NodeShape ; sh:targetClass <urn:P> ; sh:property [ sh:path <urn:key> ; sh:minCount 1 ] ."
        };
        // 内存草稿校验应真实发现父类约束缺失。
        var report = await runtime.ValidateAsync(source, CancellationToken.None);
        Assert.IsFalse(report.Conforms);
        // 服务器生成独占测试图，测试不能激活版本。
        var id = Guid.NewGuid().ToString("N");
        // 精确绑定当前源散列，回验必须复现同一约束结果。
        var manifest = new ReleaseManifest { SchemaVersion = 1, ReleaseId = id, Hashes = report.Hashes, OntologyGraphIri = "urn:ontology-platform:release:" + id + ":ontology", DataGraphIri = "urn:ontology-platform:release:" + id + ":data" };
        await runtime.DeployAsync(manifest, source, CancellationToken.None);
        Assert.IsFalse(await runtime.VerifyAsync(manifest, source, CancellationToken.None));
    }

    /// <summary>相对IRI解析必须使用稳定文档基址，不能包含随机暂存图身份。</summary>
    [TestMethod]
    public async Task RelativeIriAndExactEditPreserveRemainingGraph()
    {
        // 连续独立操作必须得到相同IRI集合。
        var runtime = SemanticFixture.Runtime();
        // 无显式base时也允许标准相对IRI源码，其他三元组不可丢失。
        var sources = new SourceBundle { OntologyTurtle = "<#C> a <http://www.w3.org/2002/07/owl#Class> ; <http://www.w3.org/2000/01/rdf-schema#label> \"旧标签\"@zh ; <urn:retained> \"保留\" ." };
        // 两次实际RIOT解析使用不同临时图。
        var first = await runtime.AnalyzeAsync(sources, 1, CancellationToken.None);
        // 第二次解析不能偷偷改写实体身份。
        var second = await runtime.AnalyzeAsync(sources, 1, CancellationToken.None);
        CollectionAssert.AreEquivalent(first.Projection.Triples, second.Projection.Triples);
        // 从真实投影选择精确旧三元组，非no-op编辑只改变这一值。
        var label = first.Projection.Triples.Single(triple => triple.Predicate.EndsWith("#label", StringComparison.Ordinal));
        // 新源来自完整图精确编辑，余下图必须保留。
        var changed = await runtime.ApplyEditAsync(sources, new SemanticEdit { SubjectIri = label.Subject.Value, PredicateIri = label.Predicate, OldObject = label.Object, NewObject = label.Object with { Value = "新标签" } }, CancellationToken.None);
        // 新源码再经真实RIOT解析，不只检查字符串包含。
        var edited = await runtime.AnalyzeAsync(changed, 2, CancellationToken.None);
        Assert.AreEqual(first.Projection.Triples.Length, edited.Projection.Triples.Length);
        Assert.IsTrue(edited.Projection.Triples.Any(triple => triple.Object.Value == "保留"));
        Assert.IsTrue(edited.Projection.Triples.Any(triple => triple.Object.Value == "新标签"));
        Assert.IsFalse(edited.Projection.Triples.Any(triple => triple.Object.Value == "旧标签"));
    }

    /// <summary>源码、三元组和可视投影预算都由真实运行时拒绝，不能静默截断。</summary>
    [TestMethod]
    public async Task SourceTripleAndProjectionBudgetsFailExplicitly()
    {
        // 只有字节超限在网络前拒绝，其他限制对真实RIOT结果生效。
        var runtime = SemanticFixture.Runtime();
        // 字节预算以UTF8长度判断，不用字符数冒充。
        var bytes = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.AnalyzeAsync(new SourceBundle { OntologyTurtle = new string('中', 90000) }, 1, CancellationToken.None));
        Assert.AreEqual(413, bytes.Status);
        // 单源小于256KiB但包含5001条不同真实三元组。
        var graph = string.Join('\n', Enumerable.Range(0, 5001).Select(index => $"<urn:s{index}> <urn:p> 1 ."));
        // 超过RDF预算拒绝，而非返回5000条假完整图。
        var triples = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.AnalyzeAsync(new SourceBundle { OntologyTurtle = graph }, 1, CancellationToken.None));
        Assert.AreEqual("rdf_triple_budget", triples.Code);
        // 可视节点限制小于RDF完整图限制。
        var nodes = string.Join('\n', Enumerable.Range(0, 1001).Select(index => $"<urn:s{index}> <urn:p> 1 ."));
        // 单独证明节点限制，不依赖三元组限制触发。
        var projection = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.AnalyzeAsync(new SourceBundle { OntologyTurtle = nodes }, 1, CancellationToken.None));
        Assert.AreEqual("projection_budget", projection.Code);
        // 同一主体上2001条不同IRI边，不增加主体节点数量。
        var edges = string.Join('\n', Enumerable.Range(0, 2001).Select(index => $"<urn:s> <urn:p> <urn:o{index}> ."));
        // 边超限也保持固定明确错误。
        var edgeBudget = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.AnalyzeAsync(new SourceBundle { OntologyTurtle = edges }, 1, CancellationToken.None));
        Assert.AreEqual("projection_budget", edgeBudget.Code);
    }

    /// <summary>两个真实操作占用槽位时第三个立即429，释放后前两个正常完成。</summary>
    [TestMethod]
    public async Task ThirdConcurrentOperationIsRejected()
    {
        // 两个请求到达发送边界后才触发第三请求，避免依赖偶然网络速度。
        var ready = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        // 时序门只延迟请求，释放后仍真正调用Jena。
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        // 原子计数用于等待前两次PUT确实占有槽位。
        var count = 0;
        // 不构造假响应，所有成功操作仍来自真正RIOT。
        var runtime = SemanticFixture.RuntimeWithGate(async (request, token) =>
        {
            if (request.Method == HttpMethod.Put)
            {
                if (Interlocked.Increment(ref count) == 2) ready.TrySetResult();
                await release.Task.WaitAsync(token);
            }
        });
        // 最小真实图保持测试只测资源槽位。
        var source = new SourceBundle { OntologyTurtle = "<urn:s> <urn:p> 1 ." };
        // 第一个真实任务进入槽位。
        var first = runtime.AnalyzeAsync(source, 1, CancellationToken.None);
        // 第二个真实任务进入槽位。
        var second = runtime.AnalyzeAsync(source, 1, CancellationToken.None);
        try
        {
            await ready.Task.WaitAsync(TimeSpan.FromSeconds(2));
            // 第三个不能绕过统一进程预算。
            var error = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.AnalyzeAsync(source, 1, CancellationToken.None));
            Assert.AreEqual(429, error.Status);
        }
        finally { release.TrySetResult(); }
        await Task.WhenAll(first, second);
    }

    /// <summary>已有真实暂存图后取消或超时，finally必须仍能删除图；脚本另外查询零残留。</summary>
    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public async Task CancellationAndTimeoutDoNotLeaveTemporaryGraphs(bool callerCancels)
    {
        // 只阻塞第一次GET，因此先前PUT已在真实Jena创建独占暂存图。
        var blocked = 0;
        // 删除请求不会被阻塞，使清理使用独立取消预算。
        var runtime = SemanticFixture.RuntimeWithGate(async (request, token) =>
        {
            if (request.Method == HttpMethod.Get && Interlocked.Exchange(ref blocked, 1) == 0)
                await Task.Delay(Timeout.InfiniteTimeSpan, token);
        });
        // 用户取消与服务内部五秒超时使用不同可观察结果。
        using var cancellation = new CancellationTokenSource();
        if (callerCancels) cancellation.CancelAfter(TimeSpan.FromMilliseconds(150));
        // 最小图使PUT在进入GET时已真实成功。
        var operation = runtime.AnalyzeAsync(new SourceBundle { OntologyTurtle = "<urn:s> <urn:p> 1 ." }, 1, cancellation.Token);
        if (callerCancels) await Assert.ThrowsAsync<OperationCanceledException>(() => operation);
        else
        {
            // 服务器预算映射固定503而不吞掉客户端取消。
            var error = await Assert.ThrowsAsync<SemanticOperationException>(() => operation);
            Assert.AreEqual("semantic_timeout", error.Code);
        }
        Assert.AreEqual(1, blocked);
    }
}
