using System.Text;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.Extensions.Configuration;
using System.Text.Json;
using OntologyPlatform.Modules.SemanticQuery;
using OntologyPlatform.Modules.Connections;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.QueryTests;

/// <summary>规范字节不依赖运行时文化、字段声明顺序或浏览器浮点格式。</summary>
[TestClass]
public sealed class G4QueryTests
{
    /// <summary>真实系统时钟验证只读参与者忽略取消时，原分支及时退出且永不披露迟到结果。</summary>
    [DataRow(false)]
    [DataRow(true)]
    [TestMethod]
    public async Task DorisLeaseObservationRejectsLateParticipant(bool sourceReturned)
    {
        // 只替换有意无限迟滞的平台读，不调用数据库或其他共享服务。
        var execution = new G4QueryExecution(null!, null!, null!, null!, TimeProvider.System);
        // 绑定实际运行使用的完整观察与清理方法，与已冻结产品公共 API 无关。
        var boundary = typeof(G4QueryExecution).GetMethod("ReadWithDorisLeaseAsync", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Instance)!;
        // 两个明确事件保证探针确已启动后再模拟读取正常返回或者读取中的取消。
        var started = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        // 忽略 CancellationToken 的平台探针模拟连接释放迟滞；测试结尾一定释放它。
        var release = new TaskCompletionSource<bool>(TaskCreationOptions.RunContinuationsAsynchronously);
        // 记录真实轮次，任何迟到或并发重试都违反此反例。
        var calls = 0;
        Task<bool> Check(CancellationToken unused)
        {
            Interlocked.Increment(ref calls);
            started.TrySetResult();
            return release.Task;
        }
        async Task<G4SourceQueryRead> Read(CancellationToken token)
        {
            await started.Task.WaitAsync(token);
            if (!sourceReturned) await Task.Delay(Timeout.Infinite, token);
            return null!;
        }
        // 预留五百毫秒提交后本次分支只有四百毫秒，不能从观察器另起计时放宽。
        var deadline = DateTimeOffset.UtcNow.AddMilliseconds(900);
        // 真实单调时间只度量被测调用，测试看门狗用于避免整个 MTP 停滞。
        var elapsed = System.Diagnostics.Stopwatch.StartNew();
        // 委托签名必须与真实业务调用完全相同。
        var work = (Task<G4SourceQueryRead>)boundary.Invoke(execution, ["query-lease-test", deadline, CancellationToken.None,
            (Func<CancellationToken, Task<G4SourceQueryRead>>)Read, (Func<CancellationToken, Task<bool>>)Check])!;
        try
        {
            await Assert.ThrowsAsync<OperationCanceledException>(async () => await work.WaitAsync(TimeSpan.FromSeconds(2)));
            Assert.AreEqual(1, calls);
            Assert.IsTrue(elapsed.ElapsedMilliseconds < 400);
        }
        finally
        {
            release.TrySetResult(true);
        }
    }

    /// <summary>从已审 M5 证据读取真实 PG manifest 和原始结果，校验发布时的内容身份及保存字节。</summary>
    [TestMethod]
    [DataRow("standard", "53191b9bc282b38a1089e39a51dc4bf11267d915e0154e3a93c3fc1a4ceedc82", "browser-s1-1794832846645-result.json.raw.json", "d5c527a7e538acd4cf8158abc05221a9ef4cb3a1ffee4327316a73226e399184")]
    [DataRow("numeric", "78e73a16a95f0e8c032d6f00012275e302b58366bbb89a7c1d071aa9dfdcc582", "browser-numeric-1794832894553-relationships.json.raw.json", "9045fa4d6d0fc4947d47076f7c15af7de268fbf3cdcf62d79bf90e88e138a643")]
    public void HistoricalPgReleaseAndResultKeepCanonicalBytes(string scenario, string manifestHash, string original, string resultHash)
    {
        // 从当前测试构建所在树定位版本控制中的既有证据，避免读取机器私有运行目录。
        var root = new DirectoryInfo(AppContext.BaseDirectory);
        while (root is not null && !Path.Exists(Path.Combine(root.FullName, ".git"))) root = root.Parent;
        Assert.IsNotNull(root);
        // 两个原件由 M5 交付，固定散列来自历史报告且早于本次实现。
        var directory = Path.Combine(root.FullName, "docs/evidence/G4-M5-INTEGRATION-001/integration-01/originals/integration-01");
        using var historical = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(directory, $"scenario-{scenario}.json")));
        // 已发布的 manifestHash 独立验证类型化对象经当前产品合同恢复后的字节身份。
        var release = historical.RootElement.GetProperty("mappingRelease");
        Assert.AreEqual(manifestHash, release.GetProperty("manifestHash").GetString());
        // 使用现行 wire 类型，新增默认字段或集合规范化变化都会反映在散列上。
        var manifest = release.GetProperty("manifest").Deserialize<MappingReleaseManifest>(G4MappingJson.Options);
        Assert.IsNotNull(manifest);
        Assert.AreEqual(manifestHash, G4QueryCanonical.Hash(MappingCanonical.Serialize(manifest)));
        if (scenario == "standard")
        {
            // 2509 字节直接来自历史数据库的 CanonicalBytes 列，散列来自同一行独立的 ContentHash 列。
            var assessmentBytes = File.ReadAllBytes(Path.Combine(root.FullName,
                "docs/evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/pg-standard-assessment.canonical.json"));
            Assert.AreEqual("b97c13b97057f7fb5c0c9119aaa0b0a0f3db9525e87dc53e5bbdb263c03e7665", G4QueryCanonical.Hash(assessmentBytes));
            // 用历史场景的公开对象校验当前类型化规范化结果，比较到每个真实原字节。
            var assessment = historical.RootElement.GetProperty("mappingAssessment").Deserialize<MappingAssessmentView>(G4MappingJson.Options);
            Assert.IsNotNull(assessment);
            Assert.AreEqual("ma-ace12515d7804af2870f2a434c167951", assessment.AssessmentId);
            CollectionAssert.AreEqual(assessmentBytes, MappingCanonical.Serialize(assessment));
        }
        using var envelope = JsonDocument.Parse(File.ReadAllBytes(Path.Combine(directory, original)));
        // 无损封装内的字节是实际 HTTP 正文，按字节比较包括属性顺序及定点数词法值。
        var bytes = envelope.RootElement.GetProperty("base64").GetBytesFromBase64();
        Assert.AreEqual(resultHash, envelope.RootElement.GetProperty("sha256").GetString());
        Assert.AreEqual(resultHash, G4QueryCanonical.Hash(bytes));
        CollectionAssert.AreEqual(bytes, G4QueryCanonical.Result(G4QueryRules.ReadResult(bytes)));
    }

    /// <summary>数据库等值numeric键不能因声明精度不同而静默丢弃关系；预期端点集合独立固定。</summary>
    [TestMethod]
    public void NumericRelationshipPreservesExpectedEdgesAcrossRepresentations()
    {
        // 反射仅定位原生产关系函数，避免为了旧实现RED先改产品可见性；真实Gateway另行验收。
        var relationship = typeof(G4QueryExecution).GetMethod("Relationship", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static)!;
        // 固定数据集与键登记；预期不调用待修相等逻辑生成。
        var dataset = new MappingDatasetRef { SnapshotId = "fixture", Schema = "production", Name = "numeric", Kind = "TABLE" };
        // 单字段连接精确指向登记列。
        var field = new MappingFieldRef { DatasetRef = dataset, Name = "key", Ordinal = 1 };
        // 半开时间区间在两个端点之间严格交叠。
        var interval = new G4QueryInterval
        {
            From = new G4QueryTime { Kind = "UTC", Lexical = "2026-11-14T00:00:00.000000Z", FractionalDigits = 6 },
            To = new G4QueryTime { Kind = "UTC", Lexical = "2026-11-15T00:00:00.000000Z", FractionalDigits = 6 }
        };
        // 根和目标仅身份号不同，组织厂区一致。
        var root = new G4EntityDatum
        {
            EntityIri = "urn:fixture:R",
            Label = null,
            EvidenceIds = ["e-root"],
            TypeIris = ["urn:fixture:Asset"],
            Properties = [],
            Identity = new G4QueryIdentity { OrganizationId = "org", SiteId = "site", SourceNamespace = "fixture", ExternalId = "R", EffectiveTime = interval },
            ValidTime = interval
        };
        // 正式关系合同保留有序连接键及时间规则。
        var relation = new MappingRelationBinding
        {
            Id = "relation",
            FromBindingId = "root",
            ToBindingId = "target",
            PredicateIri = "urn:fixture:links",
            JoinFieldPairs = [new MappingJoinFieldPair { From = field, To = field }],
            Cardinality = "ONE_TO_MANY",
            TemporalJoinPolicy = "HALF_OPEN_OVERLAP"
        };
        // 1.00和1.000应匹配，1.01不能匹配。
        var targets = new[] { new G4DecimalValue { Lexical = "1.00", Precision = 12, Scale = 2 },
            new G4DecimalValue { Lexical = "1.000", Precision = 12, Scale = 3 }, new G4DecimalValue { Lexical = "1.01", Precision = 12, Scale = 2 } };
        // 完整关系输出集合是断言对象，不是比较器返回布尔值。
        var edges = new List<string>();
        for (var index = 0; index < targets.Length; index++)
        {
            // 每个目标有独立身份和证据。
            var target = root with { EntityIri = "urn:fixture:T" + (index + 1), EvidenceIds = ["e-target-" + index], Identity = root.Identity with { ExternalId = "T" + (index + 1) } };
            // 旧函数直接执行真实生产关系匹配，之后真实源切片验证端到端。
            var edge = (G4RelationshipDatum?)relationship.Invoke(null, [relation, root, target,
                new Dictionary<string, G4QueryValue> { ["key"] = new G4DecimalValue { Lexical = "1.00", Precision = 10, Scale = 2 } },
                new Dictionary<string, G4QueryValue> { ["key"] = targets[index] }]);
            if (edge is not null) edges.Add(edge.Source.EntityIri + "→" + edge.Target.EntityIri);
        }
        CollectionAssert.AreEquivalent(new[] { "urn:fixture:R→urn:fixture:T1", "urn:fixture:R→urn:fixture:T2" }, edges.ToArray());
        // 使用同一生产关系入口验证多列顺序、作用域和半开时间，不把布尔helper当完整关系验收。
        G4RelationshipDatum? Match(G4EntityDatum target, string[] left, string[] right)
        {
            // 每列单独登记，避免简单拼接造成a/bc与ab/c碰撞。
            var pairs = left.Select((_, index) => new MappingJoinFieldPair { From = field with { Name = "k" + index }, To = field with { Name = "k" + index } }).ToArray();
            return (G4RelationshipDatum?)relationship.Invoke(null, [relation with { JoinFieldPairs = pairs }, root, target,
                left.Select((value, index) => (value, index)).ToDictionary(item => "k" + item.index, item => (G4QueryValue)new G4StringValue { Lexical = item.value }),
                right.Select((value, index) => (value, index)).ToDictionary(item => "k" + item.index, item => (G4QueryValue)new G4StringValue { Lexical = item.value })]);
        }
        Assert.IsNull(Match(root, ["a", "bc"], ["ab", "c"]));
        Assert.IsNull(Match(root, ["a", "bc"], ["a", "bd"]));
        Assert.IsNotNull(Match(root, ["a", "bc"], ["a", "bc"]));
        Assert.IsNull(Match(root with { Identity = root.Identity with { OrganizationId = "other" } }, ["a"], ["a"]));
        Assert.IsNull(Match(root with { Identity = root.Identity with { SiteId = "other" } }, ["a"], ["a"]));
        Assert.IsNull(Match(root with { ValidTime = interval with { From = interval.To, To = interval.To with { Lexical = "2026-11-16T00:00:00.000000Z" } } }, ["a"], ["a"]));
        // 严格交叠输出两端的精确交集，不扩大到任一原区间。
        var overlap = Match(root with { ValidTime = interval with { From = interval.From with { Lexical = "2026-11-14T12:00:00.000000Z" } } }, ["a"], ["a"]);
        Assert.AreEqual("2026-11-14T12:00:00.000000Z", overlap!.ValidTime!.From.Lexical);
        Assert.AreEqual(interval.To.Lexical, overlap.ValidTime!.To!.Lexical);
    }

    /// <summary>固定精确数值反例覆盖28位边界、最小小数、零和负值，预期由显式常量给出。</summary>
    [TestMethod]
    [DataRow("1.00", 10, 2, "1.000", 12, 3, true)]
    [DataRow("0.00", 10, 2, "0", 1, 0, true)]
    [DataRow("-1.00", 10, 2, "-1.000", 12, 3, true)]
    [DataRow("9007199254740993.20", 20, 2, "9007199254740993.200", 21, 3, true)]
    [DataRow("9007199254740993.20", 20, 2, "9007199254740993.21", 20, 2, false)]
    [DataRow("9999999999999999999999999999", 28, 0, "9999999999999999999999999998", 28, 0, false)]
    [DataRow("0.0000000000000000000000000001", 28, 28, "0.0000000000000000000000000000", 28, 28, false)]
    [DataRow("999999999999999999999999999.0", 28, 1, "999999999999999999999999999", 27, 0, true)]
    public void NumericKeyEqualityUsesExactApprovedRange(string left, int precision, int scale, string right, int otherPrecision, int otherScale, bool expected)
    {
        // 直接定位内部比较器供边界反例，完整边集合和Gateway另有独立验收。
        var method = typeof(G4QueryExecution).Assembly.GetType("OntologyPlatform.Modules.SemanticQuery.G4QueryKeyEquality")!.GetMethod("Equal", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static)!;
        // 两端仍保留各自声明，比较不得修改其序列化原件。
        var first = new G4DecimalValue { Lexical = left, Precision = precision, Scale = scale };
        // 第二端可以有不同精度与scale。
        var second = new G4DecimalValue { Lexical = right, Precision = otherPrecision, Scale = otherScale };
        // 规范原件见证比较没有污染输出表示。
        var bytes = G4QueryCanonical.Serialize(new[] { first, second });
        Assert.AreEqual(expected, (bool)method.Invoke(null, [first, second])!);
        CollectionAssert.AreEqual(bytes, G4QueryCanonical.Serialize(new[] { first, second }));
    }

    /// <summary>空值不成边，跨类型和非法源值必须拒绝，不能默默当零匹配。</summary>
    [TestMethod]
    public void RelationshipKeysRejectUnknownAndIncompatibleTypes()
    {
        // 内部比较入口与生产Relationship完全相同。
        var method = typeof(G4QueryExecution).Assembly.GetType("OntologyPlatform.Modules.SemanticQuery.G4QueryKeyEquality")!.GetMethod("Equal", System.Reflection.BindingFlags.NonPublic | System.Reflection.BindingFlags.Static)!;
        // 明确的源空值没有关系相等语义。
        var missing = new G4NullValue { Lexical = null, DeclaredType = "decimal" };
        foreach (var other in new G4QueryValue[] { missing, new G4DecimalValue { Lexical = "0", Precision = 1, Scale = 0 }, new G4StringValue { Lexical = "" } })
        {
            Assert.AreEqual(false, (bool)method.Invoke(null, [missing, other])!);
        }
        foreach (var other in new G4QueryValue[] { new G4StringValue { Lexical = "1" }, new G4Int64Value { Lexical = "1" },
            new G4DecimalValue { Lexical = "1.00", Precision = 1, Scale = 2 }, new G4DecimalValue { Lexical = "-0.00", Precision = 4, Scale = 2 } })
        {
            // 反射仅包装真实产品异常，断言内层准确错误而非任意失败。
            var error = Assert.Throws<System.Reflection.TargetInvocationException>(() => method.Invoke(null, [new G4DecimalValue { Lexical = "1", Precision = 1, Scale = 0 }, other]));
            Assert.IsInstanceOfType<SemanticOperationException>(error.InnerException);
            Assert.AreEqual("query_source_indeterminate", ((SemanticOperationException)error.InnerException!).Code);
        }
    }

    /// <summary>破坏性测试准入先拒绝运行库或不属于当前nonce的同名库，不发送任何SQL。</summary>
    [TestMethod]
    public async Task DestructiveTestGuardRejectsRuntimeAndUnownedTargetBeforeConnecting()
    {
        // 无效端点不能影响预连接拒绝；若守卫错误放行，会得到连接异常而非准确断言异常。
        foreach (var database in new[] { "query", "postgres", "m4_query_test_ffffffffffff" })
        {
            await Assert.ThrowsAsync<AssertFailedException>(() => G4QueryPersistenceTests.DemandIsolatedDatabaseAsync(
                "Host=unreachable.invalid;Database=" + database + ";Username=fixture;Timeout=1"));
        }
    }

    /// <summary>同一登记器保留旧能力，G4实际输出严格区分四态载荷和精确标量。</summary>
    [TestMethod]
    public void RegistryUsesGeneratedClosedG4SchemaWithoutChangingG2()
    {
        // 默认旧宿主不因新增查询能力改变能力文档或版本字节。
        var legacy = new CapabilityRegistry().Read();
        // 只有显式启用的查询宿主加载当前正式G4生成物。
        var configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?> { ["G4:QueryEnabled"] = "true" }).Build();
        // 相同生成输入跨实例必须产生相同能力版本。
        var capabilities = new CapabilityRegistry(configuration).Read();
        Assert.AreEqual(6, capabilities.Length);
        CollectionAssert.AreEqual(legacy.Select(value => JsonSerializer.Serialize(value)).ToArray(),
            capabilities.Where(value => !value.Id.StartsWith("g4_", StringComparison.Ordinal)).Select(value => JsonSerializer.Serialize(value)).ToArray());
        // 真实输出闭包包含所有正式判别子类，而不是any或G2图数据。
        var query = capabilities.Single(value => value.Id == "g4_resolve_entity");
        Assert.AreEqual(query.Version, new CapabilityRegistry(configuration).Read().Single(value => value.Id == query.Id).Version);
        // 组件名由原生OpenAPI导出稳定生成，不能在测试中构造替身Schema。
        var definitions = query.OutputSchema.GetProperty("$defs");
        Assert.AreEqual(4, definitions.GetProperty("G4QueryDatum").GetProperty("oneOf").GetArrayLength());
        Assert.IsTrue(definitions.GetProperty("G4QueryDatumG4EntityDatum").GetProperty("required").EnumerateArray().Any(value => value.GetString() == "kind"));
        Assert.AreEqual("string", definitions.GetProperty("G4QueryValueG4Int64Value").GetProperty("properties").GetProperty("lexical").GetProperty("type").GetString());
        Assert.AreEqual("null", definitions.GetProperty("G4QueryValueG4NullValue").GetProperty("properties").GetProperty("lexical").GetProperty("type").GetString());
        Assert.IsFalse(definitions.GetProperty("G4QueryResultV1").GetProperty("additionalProperties").GetBoolean());
        Assert.AreEqual(6, definitions.GetProperty("G4QueryResultV1").GetProperty("properties").GetProperty("status").GetProperty("enum").GetArrayLength());
    }

    /// <summary>无结果读取授权的首次无数据响应不得通过执行视图泄露已保存结果摘要。</summary>
    [TestMethod]
    public void ExecutionViewDoesNotDisclosePersistedHash()
    {
        // 模拟已持久的无数据六态；仅有执行状态不构成result.read许可。
        var record = new G4QueryRecord { Id = "query-no-read", ExecutionStatus = "COMPLETED", ResultHash = new string('a', 64),
            CreatedAtUtc = DateTimeOffset.UtcNow, CompletedAtUtc = DateTimeOffset.UtcNow, ExpiresAtUtc = DateTimeOffset.UtcNow.AddHours(24) };
        Assert.IsNull(G4QueryResultStore.View(record).ResultHash);
        Assert.AreEqual(new string('a', 64), record.ResultHash);
    }

    /// <summary>UTF8键顺序、控制符最小规则与精确字符串逐字节稳定。</summary>
    [TestMethod]
    public void CanonicalBytesPreservePreciseValuesAndUnicode()
    {
        // 补充平面字符与私用字符验证UTF8排序不同于UTF16 ordinal排序。
        using var input = JsonDocument.Parse("{\"𐀀\":0,\"\ue000\":1,\"value\":\"9007199254740993.20\",\"text\":\"中文\\n\\t/\"}");
        // 控制字符统一小写u00xx，非ASCII和斜线保真。
        var expected = "{\"text\":\"中文\\u000a\\u0009/\",\"value\":\"9007199254740993.20\",\"\ue000\":1,\"𐀀\":0}";
        CollectionAssert.AreEqual(Encoding.UTF8.GetBytes(expected), G4QueryCanonical.Value(input.RootElement));
        // 不允许一般JSON数字冒充安全结构整数。
        using var unsafeNumber = JsonDocument.Parse("{\"value\":9007199254740993}");
        Assert.Throws<InvalidOperationException>(() => G4QueryCanonical.Value(unsafeNumber.RootElement));
        using var fraction = JsonDocument.Parse("{\"value\":1.5}");
        Assert.Throws<InvalidOperationException>(() => G4QueryCanonical.Value(fraction.RootElement));
    }
    /// <summary>不同小数精度的同类型时间按真实时刻排序，不能按Z字符位置排序。</summary>
    [TestMethod]
    public void ProjectionSortsActualTimeAndRefusesMixedTimeKinds()
    {
        // 这里只验证规范排序，不以合成wire代替真实源证据。
        var first = new G4ObservationDatum
        {
            EntityIri = "urn:fixture:one", EvidenceIds = ["e-1"],
            Identity = new G4QueryIdentity { OrganizationId = "org-1", SiteId = "site-1", SourceNamespace = "fixture", ExternalId = "one", EffectiveTime = null },
            PropertyIri = "urn:fixture:value", Value = new G4Int64Value { Lexical = "1" }, Unit = null,
            EventTime = new G4QueryTime { Kind = "UTC", Lexical = "2026-11-14T00:00:03Z", FractionalDigits = 0 },
            ObservedAtUtc = "2026-11-14T00:00:04.000000Z", ValidTime = null
        };
        // 同秒稍晚100毫秒，但词法小数点排在Z之前。
        var later = first with { EventTime = first.EventTime with { Lexical = "2026-11-14T00:00:03.1Z", FractionalDigits = 1 } };
        using var ordered = JsonDocument.Parse(G4QueryCanonical.Projection([later, first]));
        Assert.AreEqual(first.EventTime.Lexical, ordered.RootElement[0].GetProperty("eventTime").GetProperty("lexical").GetString());
        // LOCAL与UTC没有已知可比较基准，不能自行换算或混排。
        var local = first with { EventTime = first.EventTime with { Kind = "LOCAL", Lexical = "2026-11-14T00:00:03" } };
        Assert.Throws<InvalidOperationException>(() => G4QueryCanonical.Projection([local, first]));
    }

    /// <summary>密文与queryId绑定，换行或密文篡改不能作为可恢复结果披露。</summary>
    [TestMethod]
    public void ProtectedResultRejectsTamperingAndCrossQueryReplay()
    {
        // 纯密码学测试使用一次性内存provider，真实跨上下文keyring由持久测试另验。
        var provider = new EphemeralDataProtectionProvider();
        // 测试wire证据只服务精确序列化，不声明为真实源回执。
        var result = FixtureResult();
        // 相同规范明文必须在解密后逐字节恢复。
        var protectedResult = G4QueryResultStore.Protect(provider, "query-1", result);
        CollectionAssert.AreEqual(G4QueryCanonical.Result(result), G4QueryResultStore.Unprotect(provider, "query-1", protectedResult.Ciphertext, protectedResult.Hash));
        Assert.Throws<SemanticOperationException>(() => G4QueryResultStore.Unprotect(provider, "query-other", protectedResult.Ciphertext, protectedResult.Hash));
        // 篡改真实密文字节，不以单纯不同测试字符串替代完整性检查。
        var damaged = protectedResult.Ciphertext.ToArray();
        damaged[^1] ^= 1;
        Assert.Throws<SemanticOperationException>(() => G4QueryResultStore.Unprotect(provider, "query-1", damaged, protectedResult.Hash));
        Assert.Throws<SemanticOperationException>(() => G4QueryResultStore.Unprotect(provider, "query-1", protectedResult.Ciphertext, new string('0',64)));
    }

    /// <summary>未读取分支不能强迫伪造回执，UNKNOWN回执不能升级为确定行证据。</summary>
    [TestMethod]
    public void ReceiptsMatchActualReadsAndCannotUpgradePrecision()
    {
        // 使用完整冻结wire，当前测试不冒充真实源读取。
        var result = FixtureResult();
        // 空投影只为验证回执形状，不授予任何运行权限。
        var state = new G4QueryState { Binding = G4QueryRaceTests.Binding(1), Scope = result.Evidence[0].Scope, Projections = [] };
        // FORBIDDEN未读源，无真实读取回执，合同必须允许null引用。
        var forbidden = result with { Status = "UNAUTHORIZED", Data = [], Evidence = [],
            SubSources = [result.SubSources[0] with { Status = "FORBIDDEN", SourceReadReceiptId = null, WatermarkKind = "UNKNOWN" }] };
        G4QueryRules.ValidateResult(forbidden);
        Assert.AreEqual(0, G4SourceEvidenceService.BindReceipts("query-1", state, forbidden, []).Receipts.Length);
        // 重新计算有效外置hash，确保负例检验精度而不是被无效hash提前挡住。
        var receipt = ReceiptFixture("query-1", state.Binding, result).Receipt with { Precision = "UNKNOWN", SourceRecordRef = null };
        // 一份完整认证的UNKNOWN回执也不能支撑ROW_KEY断言。
        var stored = new G4QueryStoredReceipt { Receipt = receipt, ReceiptHash = G4QueryCanonical.Hash(G4QueryCanonical.Serialize(receipt)) };
        Assert.Throws<SemanticOperationException>(() => G4SourceEvidenceService.BindReceipts("query-1", state, result, [stored]));
    }

    /// <summary>同外部号不同厂区必须产生不同完整身份，原精确数值及业务时间不丢失。</summary>
    [TestMethod]
    public void TypedProjectionPreservesScopeAndPreciseSourceValues()
    {
        // 单元材料仅覆盖映射投影，正式发布身份由真实HTTP切片另证。
        var dataset = new MappingDatasetRef { SnapshotId = "catalog-original", Schema = "production", Name = "fixture", Kind = "TABLE" };
        // 此处字段名与序号显式登记，测试不拼自由SQL。
        MappingFieldRef Field(string name, int ordinal) => new() { DatasetRef = dataset, Name = name, Ordinal = ordinal };
        // 固定最小映射覆盖源scope、有效时间与精确decimal属性。
        var mapping = new MappingDefinition
        {
            Entities = [new MappingEntityBinding { Id = "asset", EntityClassIri = "urn:fixture:Asset", DatasetRef = dataset,
                IdentitySpecId = "identity", TemporalSpecId = "time", ScopeFields = new MappingScopeFields { Organization = Field("org",1), Site = Field("site",2) } }],
            IdentitySpecs = [new MappingIdentitySpec { Id = "identity", OrganizationFieldRef = Field("org",1), SiteFieldRef = Field("site",2),
                ExternalIdFieldRefs = [Field("id",3)], SourceNamespace = "fixture", ValidFromFieldRef = Field("from",4), ValidToFieldRef = Field("to",5) }],
            TemporalSpecs = [new MappingTemporalSpec { Id = "time", EventTimeFieldRef = Field("from",4), ObservedAtFieldRef = null,
                ValidFromFieldRef = Field("from",4), ValidToFieldRef = Field("to",5), TimezonePolicy = new MappingTimezonePolicy { Kind = "UTC", ZoneId = null }, Precision = "MICROSECOND" }],
            Properties = [new MappingPropertyBinding { Id = "value", EntityBindingId = "asset", PropertyIri = "urn:fixture:value", FieldRef = Field("value",6), ConversionId = null, UnitSpecId = null, NullPolicy = "REJECT_NULL" }],
            Relations = [], Conversions = [], UnitSpecs = []
        };
        // 全范围只用于本单元样本，不构造真实授权证明。
        var scope = new ResourceScope { OrganizationId = "org-1", SiteIds = ["site-1", "site-2"] };
        // 上游已验证材料在此明确是投影单元替身，禁止据此宣称真实发布通过。
        var context = new G4QueryBindingContext { Binding = G4QueryRaceTests.Binding(1), Scope = scope, OriginalCatalog = null!, CurrentCatalog = null!,
            Manifest = new MappingReleaseManifest { SchemaVersion = "g4.mapping.v1", MappingReleaseId = "mapping-1", MappingId = "mapping-root",
                Scope = scope, OriginDraftId = "draft", OriginDraftRevision = 1, Binding = null!, Mapping = mapping, ReviewReceipt = null!, CreatedAtUtc = DateTimeOffset.UtcNow } };
        // 字典中的值均来自正式精确标量类型，不允许任意对象或double混入。
        var row = new Dictionary<string, G4QueryValue>
        {
            ["org"] = new G4StringValue { Lexical = "org-1" }, ["site"] = new G4StringValue { Lexical = "site-1" }, ["id"] = new G4StringValue { Lexical = "same" },
            ["from"] = new G4UtcValue { Lexical = "2026-11-14T01:02:03.123456Z" },
            ["to"] = new G4UtcValue { Lexical = "2026-11-15T01:02:03.123456Z" },
            ["value"] = new G4DecimalValue { Lexical = "9007199254740993.20", Precision = 20, Scale = 2 }
        };
        // 第二厂同号是另一个真实身份，不能按externalId合并。
        var second = new Dictionary<string, G4QueryValue>(row) { ["site"] = new G4StringValue { Lexical = "site-2" } };
        // 水位明确标记为单元样本，真实PG测试另行提供实际pg_current_snapshot。
        var read = new G4SourceQueryRead { EntityBindingId = "asset", Rows = [row,second], StartedAtUtc = DateTimeOffset.UtcNow,
            CompletedAtUtc = DateTimeOffset.UtcNow, AdapterVersion = "pg-query-v1", WatermarkKind = "TRANSACTION_SNAPSHOT", Watermark = "fixture-only", Limited = false, Indeterminate = false,
            RecordKeyFields = ["org","site","id","from"], QueryPlanHash = new string('e',64) };
        // 实际投影代码必须给每个当前有权源行闭合证据。
        var projected = G4QueryExecution.ProjectEntities("query-1", "trace-1", context, read);
        Assert.HasCount(2, projected.Entities);
        Assert.AreNotEqual(projected.Entities[0].EntityIri, projected.Entities[1].EntityIri);
        Assert.AreEqual("9007199254740993.20", projected.Entities[0].Properties[0].Value.Lexical);
        Assert.AreEqual("2026-11-14T01:02:03.123456Z", projected.Entities[0].Identity.EffectiveTime!.From.Lexical);
        Assert.IsTrue(projected.Evidence.All(item => item.Precision == "ROW_KEY" && item.SourceRecordRef is not null));
        Assert.IsNull(projected.Receipt.Receipt.SourceRecordRef, "多行回执不能伪造一个总行键。");
        Assert.Throws<SemanticOperationException>(() => G4QueryExecution.ProjectEntities("query-2", "trace-1", context, read with { Rows = [row,row] }));
        // 同一主体多个观测保留各自精确值，不套用根定位的重复身份拒绝规则。
        var next = new Dictionary<string, G4QueryValue>(row) { ["value"] = new G4DecimalValue { Lexical = "9007199254740993.21", Precision = 20, Scale = 2 } };
        // 这里明确测试观测投影；根定位上面的负例仍必须拒绝重复身份。
        var repeated = G4QueryExecution.ProjectEntities("query-observations", "trace-1", context, read with { Rows = [row, next] }, observations: true);
        // 每行单独来源证据确保相同主体不覆盖后一次值。
        var observations = G4QueryExecution.Observations(repeated);
        Assert.HasCount(2, observations);
        Assert.AreEqual(observations[0].EntityIri, observations[1].EntityIri);
        Assert.AreEqual("9007199254740993.20", observations[0].Value.Lexical);
        Assert.AreEqual("9007199254740993.21", observations[1].Value.Lexical);
        Assert.AreNotEqual(observations[0].EvidenceIds[0], observations[1].EvidenceIds[0]);
        Assert.AreEqual("asset", G4QueryExecution.RootBinding(mapping).Id);
        Assert.Throws<SemanticOperationException>(() => G4QueryExecution.RootBinding(mapping with { Entities = [mapping.Entities[0], mapping.Entities[0] with { Id = "another-root" }] }));
        // 缺主键时保留实际数据集证据，不升级为记录定位。
        var degraded = G4QueryExecution.ProjectEntities("query-3", "trace-1", context, read with { RecordKeyFields = [] });
        Assert.IsTrue(degraded.Evidence.All(item => item.Precision == "DATASET" && item.SourceRecordRef is null));
    }

    /// <summary>合法四千字节字符串经规范转义膨胀时保留可信完整项前缀。</summary>
    [TestMethod]
    public void EscapedResponseBudgetKeepsOnlyClosedPrefix()
    {
        // 制造源侧合法、JSON编码后超过一MiB的完整观测，不使用非法超长标量。
        var original = FixtureResult();
        // 基准观测保留合法来源和精确身份。
        var value = (G4ObservationDatum)original.Data[0];
        // 每个属性各自完整，只有累计响应超出字节预算。
        var result = original with { Data = Enumerable.Range(0, 100).Select(index => (G4QueryDatum)(value with
            { PropertyIri = "urn:fixture:value:" + index, Value = new G4StringValue { Lexical = new string('\t', 4096) } })).ToArray() };
        // 原回执按实际完整投影形成，截断后必须重算而不能沿用旧hash。
        var receipt = ReceiptFixture("query-budget", G4QueryRaceTests.Binding(1), result);
        // 正式截断器重算投影回执并保持证据闭合。
        var bounded = G4QueryExecution.BoundResponse(result, [receipt]);
        Assert.AreEqual("PARTIAL", bounded.Result.Status);
        Assert.IsTrue(bounded.Result.Limited && bounded.Result.Data.Length is > 0 and < 100);
        Assert.IsTrue(G4QueryCanonical.Result(bounded.Result).Length <= G4QueryRules.MaximumResultBytes);
        Assert.AreEqual(bounded.Result.Data.Length, bounded.Receipts[0].Receipt.RowCount);
        Assert.AreEqual(G4QueryCanonical.Hash(G4QueryCanonical.Projection(bounded.Result.Data)), bounded.Receipts[0].Receipt.ResultHash);
        Assert.IsTrue(bounded.Receipts[0].Receipt.Limited);
    }

    /// <summary>事务测试构造闭合回执；来源适配器真实回执必须由执行器按源事实另建。</summary>
    internal static G4QueryStoredReceipt ReceiptFixture(string queryId, G4QueryBinding binding, G4QueryResultV1 result)
    {
        // 回执仅覆盖分支投影，不把回执自身或总结果放入resultHash。
        var receipt = new G4SourceReadReceipt
        {
            SchemaVersion = "g4.read-receipt.v1", ReceiptId = "receipt-1", QueryId = queryId, Binding = binding,
            SourceDatasetRef = "dataset-1", QueryPlanHash = new string('e',64), AdapterVersion = "pg-query-v1",
            Scope = result.Evidence[0].Scope, Status = "SUCCESS", RowCount = 1, Limited = false,
            WatermarkKind = "TRANSACTION_SNAPSHOT", Watermark = "fixture-only", SourceRecordRef = "row-1", Precision = "ROW_KEY",
            ValidTime = null, ReadStartedAtUtc = "2026-11-14T01:02:03.000000Z", ReadCompletedAtUtc = result.ObservedAtUtc,
            ResultHash = G4QueryCanonical.Hash(G4QueryCanonical.Projection(result.Data)), TraceId = result.TraceId
        };
        return new G4QueryStoredReceipt { Receipt = receipt, ReceiptHash = G4QueryCanonical.Hash(G4QueryCanonical.Serialize(receipt)) };
    }

    /// <summary>字节与密码学用的完整判别结果，不冒充真实源或当前授权证明。</summary>
    internal static G4QueryResultV1 FixtureResult() => new()
    {
        SchemaVersion = "g4.query-result.v1", Status = "FOUND", Candidates = [], Limited = false, Diagnostics = [],
        TraceId = "trace-1", ObservedAtUtc = "2026-11-14T01:02:04.000000Z", ValidTime = null,
        Snapshot = new G4QuerySnapshot { OntologyReleaseId = "ontology-1", MappingReleaseIds = ["mapping-1"], SourceCatalogSnapshotIds = ["catalog-current"],
            CapabilityId = "g4_read_observations", CapabilityVersion = new string('a',64) },
        Data = [new G4ObservationDatum { EntityIri = "urn:fixture:one", EvidenceIds = ["e-1"],
            Identity = new G4QueryIdentity { OrganizationId = "org-1", SiteId = "site-1", SourceNamespace = "fixture", ExternalId = "one", EffectiveTime = null },
            PropertyIri = "urn:fixture:value", Value = new G4DecimalValue { Lexical = "9007199254740993.20", Precision = 20, Scale = 2 }, Unit = null,
            EventTime = new G4QueryTime { Kind = "UTC", Lexical = "2026-11-14T01:02:03.123456Z", FractionalDigits = 6 },
            ObservedAtUtc = "2026-11-14T01:02:04.000000Z", ValidTime = null }],
        Evidence = [new G4SourceEvidenceRef { EvidenceId = "e-1", ConnectionId = "connection-1", MappingReleaseId = "mapping-1", SourceCatalogSnapshotId = "catalog-original",
            SourceDatasetRef = "dataset-1", SourceReadReceiptId = "receipt-1", Scope = new ResourceScope { OrganizationId = "org-1", SiteIds = ["site-1"] },
            Precision = "ROW_KEY", SourceRecordRef = "row-1", ValidTime = null, ObservedAtUtc = "2026-11-14T01:02:04.000000Z" }],
        SubSources = [new G4QuerySubSource { ConnectionId = "connection-1", Status = "SUCCESS", ObservedAtUtc = "2026-11-14T01:02:04.000000Z",
            WatermarkKind = "TRANSACTION_SNAPSHOT", SourceReadReceiptId = "receipt-1", Limited = false }]
    };
}
