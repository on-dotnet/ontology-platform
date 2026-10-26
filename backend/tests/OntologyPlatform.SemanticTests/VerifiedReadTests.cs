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
    private static SourceBundle Sources() => new() { OntologyTurtle = "<urn:verified:C> a <http://www.w3.org/2002/07/owl#Class> .", ShapesTurtle = "@prefix sh: <http://www.w3.org/ns/shacl#> .\n", VocabularyTurtle = "<urn:verified:vocabulary> <http://www.w3.org/2000/01/rdf-schema#label> \"词汇\"@zh .", DataTurtle = "<urn:verified:i> a <urn:verified:C> ; <urn:verified:n> 1 ." };

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
