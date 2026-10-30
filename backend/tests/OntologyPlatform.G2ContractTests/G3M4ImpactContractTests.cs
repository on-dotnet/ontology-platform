using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.G2ContractTests;

/// <summary>业务并行前冻结固定版本、影响引用与canonical内容身份的正反例。</summary>
[TestClass]
public sealed class G3M4ImpactContractTests
{
    /// <summary>真实宿主采用的Web JSON命名策略。</summary>
    private static readonly JsonSerializerOptions Options = new(JsonSerializerDefaults.Web);

    /// <summary>完整合成版本定位与命令，不含客户端权限或源正文。</summary>
    private const string RequestJson = """
        {"from":{"kind":"DRAFT","id":"draft-synthetic","revision":2},"to":{"kind":"DRAFT","id":"draft-synthetic","revision":2},"baselineKind":"INITIAL","assessmentId":"assessment-synthetic","command":{"commandId":"impact-contract","idempotencyKey":"impact-contract","reason":"验证报告幂等协议","expectedRevision":2}}
        """;

    /// <summary>合法首次发布自基线准确往返，普通分析不能隐式冒充INITIAL。</summary>
    [TestMethod]
    public void ExplicitInitialBaselineRoundtrips()
    {
        // 真实严格DTO解析保留每个固定版本字段。
        var request = JsonSerializer.Deserialize<GenerateImpactReportRequest>(RequestJson, Options)!;
        Assert.AreEqual(ImpactBaselineKind.Initial, request.BaselineKind);
        Assert.AreEqual(request.From, request.To);
        Assert.AreEqual(request, JsonSerializer.Deserialize<GenerateImpactReportRequest>(JsonSerializer.Serialize(request, Options), Options));
    }

    /// <summary>缺字段、未知字段/枚举、非法版本及错误自基线在应用前拒绝。</summary>
    /// <param name="mode">仅变化单项的畸形场景。</param>
    [TestMethod]
    [DataRow("missing-from")]
    [DataRow("missing-to")]
    [DataRow("missing-assessmentId")]
    [DataRow("missing-command")]
    [DataRow("null-from")]
    [DataRow("unknown-baseline")]
    [DataRow("numeric-baseline")]
    [DataRow("forged-publishEligible")]
    [DataRow("different-initial-target")]
    [DataRow("release-with-revision")]
    public void InvalidGenerationRequestFailsClosed(string mode)
    {
        // 每次只修改被测条件，避免其它错误掩盖该边界。
        var node = JsonNode.Parse(RequestJson)!;
        if (mode.StartsWith("missing-", StringComparison.Ordinal)) node.AsObject().Remove(mode[8..]);
        if (mode == "null-from") node["from"] = null;
        if (mode == "unknown-baseline") node["baselineKind"] = "AUTOMATIC";
        if (mode == "numeric-baseline") node["baselineKind"] = 0;
        if (mode == "forged-publishEligible") node["publishEligible"] = true;
        if (mode == "different-initial-target") node["to"]!["revision"] = 3;
        if (mode == "release-with-revision") node["from"]!["kind"] = "RELEASE";
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<GenerateImpactReportRequest>(node.ToJsonString(), Options));
    }

    /// <summary>旧JSON缺席impact仍可解析，但孤立引用、坏hash或回滚夹带一律拒绝。</summary>
    [TestMethod]
    public void ProposalReferenceIsPairedAndRollbackCannotCarryImpact()
    {
        // 历史线协议的必需字段原样保留，新业务资格由服务层强制。
        var legacy = new CreateProposalRequest { Kind = ProposalKind.Publish, DraftId = "draft-synthetic", DraftRevision = 2,
            Hashes = Hashes("target"), ValidationReportId = "validation-synthetic", Command = new CommandContext() };
        // omitNull避免向历史对象字节追加两个null字段。
        var text = JsonSerializer.Serialize(legacy, Options);
        Assert.DoesNotContain("impactHash", text);
        Assert.DoesNotContain("impactReportId", text);
        Assert.IsNull(JsonSerializer.Deserialize<CreateProposalRequest>(text, Options)!.ImpactHash);
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(legacy with { ImpactReportId = "report" }, Options));
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(legacy with { ImpactReportId = "report", ImpactHash = "forged" }, Options));
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(legacy with { Kind = ProposalKind.Rollback, ImpactReportId = "report", ImpactHash = Hash("report") }, Options));
        // 新合法引用往返保持准确hash，不允许客户端附报告正文。
        var valid = legacy with { ImpactReportId = "report", ImpactHash = Hash("report") };
        Assert.AreEqual(valid.ImpactHash, JsonSerializer.Deserialize<CreateProposalRequest>(JsonSerializer.Serialize(valid, Options), Options)!.ImpactHash);
    }

    /// <summary>顺序、重复项、ID/时刻和实际图遥测不改变稳定内容身份。</summary>
    [TestMethod]
    public void CanonicalHashIgnoresEnvelopeTelemetryAndSetOrdering()
    {
        // 合成报告具有真实四槽位及完整RdfTerm，使用生产canonical算法。
        var report = Report();
        // 不同运行耗时或枚举顺序不是不同语义结论。
        var other = report with { ReportId = "different-first-id", GeneratedAtUtc = report.GeneratedAtUtc.AddHours(1), ExpiresAtUtc = report.ExpiresAtUtc.AddHours(1),
            Diff = report.Diff with { Scope = report.Diff.Scope with { SiteIds = ["site-b", "site-a", "site-a"] },
                Sources = report.Diff.Sources.Reverse().Select(source => source with { Graph = source.Graph with { ElapsedMilliseconds = 987, VisitedNodes = 654 } }).ToArray() },
            ChangedIris = report.ChangedIris.Reverse().Concat(report.ChangedIris).ToArray(),
            KnownImpacts = report.KnownImpacts.Reverse().ToArray() };
        Assert.AreEqual(ImpactContractRules.CanonicalHash(report), ImpactContractRules.CanonicalHash(other));
        Assert.AreEqual(ImpactContractRules.InputFingerprint(report.Diff, report.BaselineKind, report.TargetSemantics, report.ProfileVersion, report.ProfileHash),
            ImpactContractRules.InputFingerprint(other.Diff, other.BaselineKind, other.TargetSemantics, other.ProfileVersion, other.ProfileHash));
        Assert.AreEqual("site-a", report.Diff.Scope.SiteIds[0], "计算不能修改调用方数组。");
    }

    /// <summary>每种来源hash、版本、assessment/profile、未知阻断和literal元数据都进入身份。</summary>
    [TestMethod]
    public void MeaningfulInputsAndEvidenceCannotReuseCanonicalHash()
    {
        // 不同语义输入必须改变相同生产算法的内容身份。
        var report = Report();
        // 原hash仅作为本次对照，不预填未来报告hash。
        var original = ImpactContractRules.CanonicalHash(report);
        Assert.AreNotEqual(original, ImpactContractRules.CanonicalHash(Seal(report with { ProfileHash = Hash("new-profile"), TargetSemantics = report.TargetSemantics! with { ProfileHash = Hash("new-profile") } })));
        Assert.AreNotEqual(original, ImpactContractRules.CanonicalHash(Seal(report with { TargetSemantics = report.TargetSemantics! with { AssessmentHash = Hash("new-assessment") } })));
        Assert.AreNotEqual(original, ImpactContractRules.CanonicalHash(Seal(report with { Diff = report.Diff with { To = report.Diff.To with { Revision = 3 } } })));
        Assert.AreNotEqual(original, ImpactContractRules.CanonicalHash(InitialReport(report)));
        Assert.AreNotEqual(original, ImpactContractRules.CanonicalHash(report with { PublishEligible = false }));
        Assert.AreNotEqual(original, ImpactContractRules.CanonicalHash(report with { PublishEligible = false, UnknownCoverage = report.KnownImpacts.Select(item => item with { Blocking = true }).ToArray() }));
        // 当前槽位单独变化，其余三个源保持精确不变作为对照。
        foreach (var source in report.Diff.Sources)
        {
            // 单一源真实变化不能被其它三个源未变掩盖。
            var changed = report.Diff.Sources.Select(item => item.SourceId == source.SourceId
                ? item with { TargetText = item.TargetText + "# changed\n", TargetHash = Hash(item.TargetText + "# changed\n") } : item).ToArray();
            Assert.AreNotEqual(original, ImpactContractRules.CanonicalHash(Seal(report with { Diff = BindSources(report.Diff, changed) })));
        }
        // 同文字但语言或datatype不同是不同完整RDF项。
        var first = report.Diff.Sources[0];
        Assert.AreNotEqual(original, ImpactContractRules.CanonicalHash(report with { Diff = report.Diff with
        {
            Sources = [first with { AddedTriples = first.AddedTriples.Select(triple => triple with { Object = triple.Object with { Language = "en" } }).ToArray() }, .. report.Diff.Sources.Skip(1)]
        } }));
    }

    /// <summary>缺席、空源码和缺来源槽位不能在协议中混为同一输入。</summary>
    [TestMethod]
    public void FourSourceAndAbsenceContractIsStrict()
    {
        // 完整四源正例通过真实JSON往返。
        var diff = Report().Diff;
        Assert.AreEqual(4, JsonSerializer.Deserialize<VersionDiff>(JsonSerializer.Serialize(diff, Options), Options)!.Sources.Length);
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(diff with { Sources = diff.Sources.Take(3).ToArray() }, Options));
        Assert.Throws<JsonException>(() => JsonSerializer.Serialize(diff.Sources[0] with { BaseHash = null }, Options));
        Assert.AreNotEqual(ImpactContractRules.InputFingerprint(diff, ImpactBaselineKind.VersionPair, null, "4", Hash("profile")),
            ImpactContractRules.InputFingerprint(BindSources(diff, diff.Sources.Select(source => source.SourceId == "vocabulary"
                ? source with { TargetText = null, TargetHash = null, AddedTriples = [], TargetTripleCount = 0 } : source).ToArray()), ImpactBaselineKind.VersionPair, null, "4", Hash("profile")));
    }

    /// <summary>不稳定blank、伪造来源身份和无证据结论必须在canonical或wire边界拒绝。</summary>
    /// <param name="mode">被篡改的明确单项。</param>
    [TestMethod]
    [DataRow("slot-hash")]
    [DataRow("bundle-hash")]
    [DataRow("text-hash")]
    [DataRow("changed-flag")]
    [DataRow("blank-delta")]
    [DataRow("blank-evidence")]
    [DataRow("blank-focus")]
    [DataRow("evidence-hash")]
    [DataRow("evidence-version")]
    [DataRow("missing-evidence")]
    [DataRow("equivalent-with-delta")]
    [DataRow("indeterminate-eligible")]
    [DataRow("different-equivalent-delta")]
    [DataRow("different-empty-exact")]
    [DataRow("unnamed-focus")]
    [DataRow("unnamed-delta")]
    public void UnstableOrUnboundContentIsRejected(string mode)
    {
        // 每个负例保留其它合法输入，确保拒绝的是本项完整性缺口。
        var report = Report();
        // 同一个来源或证据仅发生一处受控篡改。
        var first = report.Diff.Sources[0];
        // 只在已知结论中替换本次测试证据。
        var conclusion = report.KnownImpacts[0];
        // 未登记blank不会被当成稳定命名IRI进行散列。
        var blank = new RdfTerm { Kind = RdfTermKind.Blank, Value = "random-riot-id" };
        if (mode == "slot-hash") report = report with { Diff = report.Diff with { TargetHashes = report.Diff.TargetHashes with { OntologyHash = Hash("forged") } } };
        if (mode == "bundle-hash") report = report with { Diff = report.Diff with { TargetHashes = report.Diff.TargetHashes with { BundleHash = Hash("forged") } } };
        if (mode == "text-hash") report = report with { Diff = report.Diff with { Sources = [first with { TargetText = "different original bytes" }, .. report.Diff.Sources.Skip(1)] } };
        if (mode == "changed-flag") report = report with { Diff = report.Diff with { Sources = [first with { SourceChanged = false }, .. report.Diff.Sources.Skip(1)] } };
        if (mode == "blank-delta") report = report with { Diff = report.Diff with { Sources = [first with { AddedTriples = [first.AddedTriples[0] with { Subject = blank }] }, .. report.Diff.Sources.Skip(1)] } };
        if (mode == "blank-evidence") report = report with { KnownImpacts = [conclusion with { Evidence = [conclusion.Evidence[0] with { Triple = first.AddedTriples[0] with { Object = blank } }] }] };
        if (mode == "blank-focus") report = report with { KnownImpacts = [conclusion with { Evidence = [conclusion.Evidence[0] with { FocusIri = "_:random-riot-id" }] }] };
        if (mode == "evidence-hash") report = report with { KnownImpacts = [conclusion with { Evidence = [conclusion.Evidence[0] with { SourceHash = Hash("forged") }] }] };
        if (mode == "evidence-version") report = report with { KnownImpacts = [conclusion with { Evidence = [conclusion.Evidence[0] with { Version = report.Diff.To with { Revision = 99 } }] }] };
        if (mode == "missing-evidence") report = report with { KnownImpacts = [conclusion with { Evidence = [] }] };
        if (mode == "equivalent-with-delta") report = report with { Diff = report.Diff with { Sources = [first with { Graph = first.Graph with { Status = GraphComparisonStatus.Equivalent } }, .. report.Diff.Sources.Skip(1)] } };
        if (mode == "indeterminate-eligible") report = report with { Diff = report.Diff with { Sources = [first with { Graph = first.Graph with { Status = GraphComparisonStatus.Indeterminate }, TripleDeltaStatus = TripleDeltaStatus.Indeterminate }, .. report.Diff.Sources.Skip(1)] } };
        if (mode == "different-equivalent-delta") report = report with { Diff = report.Diff with { Sources = [first with { TripleDeltaStatus = TripleDeltaStatus.Equivalent, AddedTriples = [], RemovedTriples = [] }, .. report.Diff.Sources.Skip(1)] } };
        if (mode == "different-empty-exact") report = report with { Diff = report.Diff with { Sources = [first with { AddedTriples = [], RemovedTriples = [] }, .. report.Diff.Sources.Skip(1)] } };
        if (mode == "unnamed-focus") report = report with { KnownImpacts = [conclusion with { Evidence = [conclusion.Evidence[0] with { FocusIri = "random-riot-id" }] }] };
        if (mode == "unnamed-delta") report = report with { Diff = report.Diff with { Sources = [first with { AddedTriples = [first.AddedTriples[0] with { Subject = new RdfTerm { Kind = RdfTermKind.Iri, Value = "random-riot-id" } }] }, .. report.Diff.Sources.Skip(1)] } };
        Assert.Throws<JsonException>(() => ImpactContractRules.CanonicalHash(report));
    }

    /// <summary>INITIAL不能只换枚举，必须真正自比固定草稿；普通版本对身份独立。</summary>
    [TestMethod]
    public void InitialReportRequiresRealSelfBaseline()
    {
        // 正例拥有自比原文/hash和明确首次引入结论。
        var initial = InitialReport(Report());
        Assert.AreEqual(initial.Diff.From, initial.Diff.To);
        Assert.IsTrue(initial.Diff.Sources.All(source => !source.SourceChanged));
        Assert.IsTrue(ImpactContractRules.IsHash(ImpactContractRules.CanonicalHash(initial)));
        Assert.Throws<JsonException>(() => ImpactContractRules.InputFingerprint(Report().Diff, ImpactBaselineKind.Initial,
            initial.TargetSemantics, initial.ProfileVersion, initial.ProfileHash));
    }

    /// <summary>构造真实合同的有界合成数据，不宣称产品比较或评估通过。</summary>
    private static ImpactReport Report()
    {
        // 两个固定版本只用于纯合同测试。
        var baseVersion = new VersionRef { Kind = VersionRefKind.Draft, Id = "draft-synthetic", Revision = 1 };
        // 目标与同资产草稿的第二个固定修订一致。
        var to = baseVersion with { Revision = 2 };
        // 语言literal保持完整字段，不用显示文本代替身份。
        var triple = new RdfTriple { Subject = new RdfTerm { Kind = RdfTermKind.Iri, Value = "urn:synthetic:m4:C" },
            Predicate = "http://www.w3.org/2000/01/rdf-schema#label", Object = new RdfTerm { Kind = RdfTermKind.Literal, Value = "合成类", Language = "zh" } };
        // 明确生成四源身份与真实UTF8散列。
        var diff = new VersionDiff { AssetId = "asset-synthetic", Scope = new ResourceScope { OrganizationId = "org-synthetic", SiteIds = ["site-a", "site-b"] },
            From = baseVersion, To = to, BaseHashes = Hashes("base"), TargetHashes = Hashes("target"),
            Sources = new[] { "ontology", "shapes", "vocabulary", "data" }.Select(id => new SourceVersionDiff
            {
                SourceId = id, BaseText = SourceText("base", id), TargetText = SourceText("target", id),
                BaseHash = Hash(SourceText("base", id)), TargetHash = Hash(SourceText("target", id)), SourceChanged = true,
                Graph = new GraphComparisonResult { Status = GraphComparisonStatus.Different, Code = "graph_different", ElapsedMilliseconds = 1, VisitedNodes = 2 },
                BaseTripleCount = 1, TargetTripleCount = 1, AddedTriples = [triple], RemovedTriples = [triple with { Object = triple.Object with { Value = "旧合成类" } }], TripleDeltaStatus = TripleDeltaStatus.Exact
            }).ToArray() };
        // 证据只引用固定目标源，不伪造正式图或时间。
        var evidence = new ImpactEvidenceReference { Version = to, SourceId = "ontology", SourceHash = diff.TargetHashes.OntologyHash, Triple = triple,
            FocusIri = triple.Subject.Value, Path = triple.Predicate };
        // 日期只作持久envelope，纯canonical算法明确排除。
        var time = new DateTimeOffset(2026, 10, 30, 0, 0, 0, TimeSpan.Zero);
        // 完整评估引用来自固定合成fixture，不作为真实引擎结果。
        var semantics = new PublicationSemantics { ProfileVersion = "4", ProfileHash = Hash("profile"), AssessmentId = "assessment-synthetic", AssessmentHash = Hash("assessment") };
        return new ImpactReport { SchemaVersion = 1, ReportId = "report-synthetic", InputFingerprint = ImpactContractRules.InputFingerprint(diff, ImpactBaselineKind.VersionPair, semantics, "4", semantics.ProfileHash),
            ExecutorVersion = ImpactContractRules.ExecutorVersion, BudgetIdentity = ImpactContractRules.BudgetIdentity,
            GeneratedAtUtc = time, ExpiresAtUtc = time.AddHours(24), BaselineKind = ImpactBaselineKind.VersionPair, Diff = diff, ProfileVersion = "4", ProfileHash = semantics.ProfileHash,
            TargetSemantics = semantics, ChangedIris = ["urn:synthetic:m4:C", "urn:synthetic:m4:D"], AssetReferences = [diff.AssetId],
            KnownImpacts = [new ImpactConclusion { Code = "asserted_added", Message = "显式新增合成标签。", AffectedIris = [triple.Subject.Value], AssetReferences = [diff.AssetId], Evidence = [evidence] }],
            Blockers = [], UnknownCoverage = [], PublishEligible = true };
    }

    /// <summary>生成一致四源组合身份，缺席词汇标记与原合同一致。</summary>
    private static SourceHashes Hashes(string tag)
    {
        // 每槽位的值与bundle组合次序明确固定。
        var hashes = new SourceHashes { OntologyHash = Hash(SourceText(tag, "ontology")), ShapesHash = Hash(SourceText(tag, "shapes")), VocabularyHash = Hash(SourceText(tag, "vocabulary")), DataHash = Hash(SourceText(tag, "data")) };
        return hashes with { BundleHash = Hash(string.Join('\n', hashes.OntologyHash, hashes.ShapesHash, hashes.VocabularyHash, hashes.DataHash)) };
    }

    /// <summary>变更语义输入后重新固定输入身份，模拟服务器受控构造而非伪造旧身份。</summary>
    private static ImpactReport Seal(ImpactReport report)
    {
        // 此fixture已知结论只引用目标；变更目标时显式重新绑定版本与对应源hash。
        var conclusions = report.KnownImpacts.Select(item => item with { Evidence = item.Evidence.Select(evidence => evidence with
        {
            Version = report.Diff.To,
            SourceHash = evidence.SourceId switch
            {
                "ontology" => report.Diff.TargetHashes.OntologyHash,
                "shapes" => report.Diff.TargetHashes.ShapesHash,
                "vocabulary" => report.Diff.TargetHashes.VocabularyHash!,
                "data" => report.Diff.TargetHashes.DataHash,
                _ => report.Diff.TargetHashes.BundleHash
            }
        }).ToArray() }).ToArray();
        return report with { KnownImpacts = conclusions,
            InputFingerprint = ImpactContractRules.InputFingerprint(report.Diff, report.BaselineKind, report.TargetSemantics, report.ProfileVersion, report.ProfileHash) };
    }

    /// <summary>首次发布仍使用真实自比no-op，但单独报告资产首次引入。</summary>
    private static ImpactReport InitialReport(ImpactReport report)
    {
        // 两侧固定定位和原文完全相同，不能只改Baseline枚举伪装自比。
        var sources = report.Diff.Sources.Select(source => source with { BaseText = source.TargetText, BaseHash = source.TargetHash, SourceChanged = false,
            BaseTripleCount = source.TargetTripleCount, AddedTriples = [], RemovedTriples = [], TripleDeltaStatus = TripleDeltaStatus.Equivalent,
            Graph = source.Graph with { Status = GraphComparisonStatus.Equivalent, Code = "graph_equivalent" } }).ToArray();
        return Seal(report with { BaselineKind = ImpactBaselineKind.Initial, Diff = BindSources(report.Diff with { From = report.Diff.To }, sources),
            KnownImpacts = report.KnownImpacts.Select(item => item with { Code = "initial_asset_introduction", Message = "首次引入合成资产的显式事实。" }).ToArray() });
    }

    /// <summary>按精确槽位原文重新绑定真实hash，避免合法正例使用自相矛盾的身份。</summary>
    private static VersionDiff BindSources(VersionDiff diff, SourceVersionDiff[] sources)
    {
        // 用固定来源名恢复两个版本的真实组合身份。
        SourceHashes Side(bool target)
        {
            // 每项原文已在场景中明确指定，缺词汇保持null。
            var values = sources.ToDictionary(item => item.SourceId, item => target ? item.TargetHash : item.BaseHash);
            return new SourceHashes { OntologyHash = values["ontology"]!, ShapesHash = values["shapes"]!, VocabularyHash = values["vocabulary"], DataHash = values["data"]!,
                BundleHash = Hash(string.Join('\n', values["ontology"], values["shapes"], values["vocabulary"] ?? "absent", values["data"])) };
        }
        return diff with { Sources = sources, BaseHashes = Side(false), TargetHashes = Side(true) };
    }

    /// <summary>每个槽位保留独立注释和真实Turtle标签，原文身份不再使用无关占位hash。</summary>
    private static string SourceText(string tag, string source) => "<urn:synthetic:m4:C> <http://www.w3.org/2000/01/rdf-schema#label> \""
        + (tag == "base" ? "旧合成类" : "合成类") + "\"@zh .\n# " + tag + "/" + source + "\n";

    /// <summary>仅纯fixture使用的准确UTF8散列函数。</summary>
    private static string Hash(string text) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(text)));
}
