using System.Text;
using System.Text.Json;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>只对本资产已解析四源显式事实作有界影响解释，未知和范围限制独立报告。</summary>
public sealed partial class OntologyService
{
    /// <summary>从同一次比较事实构造真实证据，不进行imports加载或OWL推理。</summary>
    private static ImpactReport BuildImpactReport(VersionDiff diff, ImpactBaselineKind kind, PublicationSemantics? semantics, string profileVersion, string profileHash, bool assessmentEligible, string? assessmentError,
        RdfTriple[][]? original, RdfTriple[][]? target, DateTimeOffset generated, DateTimeOffset expires, bool baselineVerified, CancellationToken token)
    {
        // 结论集合各自保留语义类别，达到256预算后明确阻断而非悄悄截断。
        var known = new List<ImpactConclusion>();
        // 审核者不能覆盖技术阻断。
        var blockers = new List<ImpactConclusion>();
        // 明确不覆盖与实际无法解析分别用Blocking表达。
        var unknown = new List<ImpactConclusion>();
        // 只收集命名IRI，不保存随机blank label作为稳定身份。
        var changedIris = new HashSet<string>(StringComparer.Ordinal);
        // 所有可追溯资产引用都来自服务器实际assetId。
        string[] assets = [diff.AssetId];
        // 超限信号仅使最终报告更保守，不能变成成功无影响。
        var exceeded = false;
        // 真实目标bundle是无法细分定位时的最小可信证据。
        var bundle = Evidence(diff, false, "bundle", null);
        Add(unknown, Conclusion("impact_scope_limit", "仅覆盖本资产四源显式变化及已解析入向引用；M5/G4/G5、外部系统与完整OWL推理未覆盖，不代表这些范围无影响。", false, [], [bundle]));
        if (!assessmentEligible || semantics is null)
            Add(blockers, Conclusion(assessmentError ?? "impact_assessment_required", "目标缺少通过完整来源/profile/阶段/时效检查的评估，不能取得新发布技术资格。", true, [], [bundle]));
        if (diff.To.Kind != VersionRefKind.Draft)
            Add(blockers, Conclusion("impact_target_not_draft", "固定正式版本可供分析；新发布必须绑定准确当前草稿修订。", true, [], [bundle]));
        if (kind == ImpactBaselineKind.VersionPair && diff.From.Kind != VersionRefKind.Release)
            Add(blockers, Conclusion("impact_publication_baseline_required", "此固定版本对可供分析；用于发布时基础必须是准确active Release及manifest hash。", true, [], [Evidence(diff, true, "bundle", null)]));
        if (kind == ImpactBaselineKind.Initial && !baselineVerified)
            Add(unknown, Conclusion("impact_initial_baseline_unverified", "当前服务没有可核验active的发布目录，不能把自比声明为已确认首次发布。", true, [], [bundle]));
        foreach (var source in diff.Sources)
        {
            token.ThrowIfCancellationRequested();
            if (source.Graph.Status == GraphComparisonStatus.Indeterminate || source.TripleDeltaStatus == TripleDeltaStatus.Indeterminate)
                Add(unknown, Conclusion(source.Graph.Status == GraphComparisonStatus.Indeterminate ? "impact_comparison_indeterminate" : "impact_blank_alignment_indeterminate", "实际比较预算/取消或变化空白结构无法可靠对齐；完整两侧原文及已知统计保留，不能认定无影响。", true, [], [Evidence(diff, false, source.SourceId, null)]));
            if (kind == ImpactBaselineKind.Initial) continue;
            foreach (var triple in source.RemovedTriples)
            {
                token.ThrowIfCancellationRequested();
                // 删除结论只引用基础版本原始source/hash及可信地面三元组。
                var iris = Iris(triple);
                changedIris.UnionWith(iris);
                Add(known, Conclusion("impact_explicit_triple_removed", "固定基础版本中的显式地面三元组被移除；该结论不包含未执行推理的隐含影响。", false, iris, [Evidence(diff, true, source.SourceId, triple)]));
            }
            foreach (var triple in source.AddedTriples)
            {
                token.ThrowIfCancellationRequested();
                // 新增结论只引用目标版本，不为它伪造旧版本来源。
                var iris = Iris(triple);
                changedIris.UnionWith(iris);
                Add(known, Conclusion("impact_explicit_triple_added", "固定目标版本新增显式地面三元组；不据同名或同编号自动合并身份。", false, iris, [Evidence(diff, false, source.SourceId, triple)]));
            }
            if (source.SourceChanged && source.Graph.Status == GraphComparisonStatus.Equivalent)
                Add(known, Conclusion("impact_source_bytes_changed", "原始源码字节或来源缺席状态变化，但本次有界RDF图比较等价；原文/hash差异仍明确保留。", false, [], [Evidence(diff, false, source.SourceId, null)]));
        }
        if (kind == ImpactBaselineKind.Initial)
        {
            if (target is null)
                Add(unknown, Conclusion("impact_initial_facts_unavailable", "首次引入的完整事实未能在预算内解析，不能以自比no-op宣称无影响。", true, [], [bundle]));
            else
            {
                // 初始自比的Diff按合同仍为no-op，影响则明确是整个本资产首次引入。
                changedIris.UnionWith(target.SelectMany(graph => graph).SelectMany(Iris));
                Add(known, Conclusion("impact_initial_asset_introduced", "INITIAL为本资产、显式实体及引用首次引入；自比图相同不表示没有引入影响。", false, changedIris.Order(StringComparer.Ordinal).ToArray(), [bundle]));
            }
        }
        else if (diff.Sources.All(source => source.Graph.Status == GraphComparisonStatus.Equivalent && !source.SourceChanged))
            Add(known, Conclusion("impact_bounded_no_delta", "这两个准确固定版本的四源原文和本次有界图比较未发现差异；不扩展为全系统无影响结论。", false, [], [bundle]));
        if (target is not null)
        {
            // 当前支持白名单只评估ontology/vocabulary/data，Shapes仍由原assessment处理。
            var supportedFacts = target[0].Concat(target[2]).Concat(target[3]).ToArray();
            foreach (var diagnostic in JenaSemanticRuntime.ImpactSupport(supportedFacts))
            {
                token.ThrowIfCancellationRequested();
                // blank focus仅在源码保留，证据不会捏造稳定blank IRI。
                var evidence = Locate(diff, target, false, diagnostic.FocusNode, diagnostic.Path);
                Add(blockers, Conclusion("impact_unsupported_axiom", "目标存在当前profile未覆盖公理或语义结构，不能由审核覆盖该技术阻断。", true, diagnostic.FocusNode?.Kind == RdfTermKind.Iri ? [diagnostic.FocusNode.Value] : [], [evidence]));
            }
            // 显式入向引用只按已解析事实检查，不执行外部依赖加载或闭包。
            var before = original?.SelectMany(graph => graph).ToArray() ?? [];
            // 目标完整事实保持各源作用域，blank只用于局部分析不输出稳定标识。
            var after = target.SelectMany(graph => graph).ToArray();
            // 删除显式定义后仍被引用必须技术阻断，不因主体还有label便视为定义仍在。
            var removedDefinitions = before.Where(triple => triple.Subject.Kind == RdfTermKind.Iri && triple.Predicate == JenaRdfCodec.Type).Select(triple => triple.Subject.Value).Except(after.Where(triple => triple.Subject.Kind == RdfTermKind.Iri && triple.Predicate == JenaRdfCodec.Type).Select(triple => triple.Subject.Value), StringComparer.Ordinal).ToHashSet(StringComparer.Ordinal);
            // 受控命名关系及显式ObjectProperty才表示本轮依赖，不把来源metadata当待加载语义。
            var objectProperties = after.Where(triple => triple.Predicate == JenaRdfCodec.Type && triple.Object.Kind == RdfTermKind.Iri && triple.Object.Value == JenaRdfCodec.Owl + "ObjectProperty").Select(triple => triple.Subject.Value).ToHashSet(StringComparer.Ordinal);
            // 显式本地资源集合不需要联网即可确认。
            var subjects = after.Where(triple => triple.Subject.Kind == RdfTermKind.Iri).Select(triple => triple.Subject.Value).ToHashSet(StringComparer.Ordinal);
            for (var index = 0; index < target.Length; index++)
                foreach (var triple in target[index])
                {
                    token.ThrowIfCancellationRequested();
                    if (triple.Object.Kind != RdfTermKind.Iri) continue;
                    // 入向引用可解释地指向仍被使用的已删除定义。
                    var evidence = Evidence(diff, false, SourceName(index), triple);
                    if (removedDefinitions.Contains(triple.Object.Value))
                        Add(blockers, Conclusion("impact_removed_definition_referenced", "目标四源仍显式引用已从本版本移除类型定义的IRI，引用治理未闭合。", true, [triple.Object.Value], [evidence]));
                    else if ((objectProperties.Contains(triple.Predicate) || triple.Predicate is JenaRdfCodec.Type or "http://www.w3.org/2000/01/rdf-schema#subClassOf" or "http://www.w3.org/2000/01/rdf-schema#domain" or "http://www.w3.org/2000/01/rdf-schema#range" or JenaRdfCodec.Owl + "equivalentClass" or JenaRdfCodec.Owl + "disjointWith" or JenaRdfCodec.Owl + "inverseOf") && !subjects.Contains(triple.Object.Value) && !StandardIri(triple.Object.Value))
                        Add(unknown, Conclusion("impact_dependency_unresolved", "显式语义关系引用未在本资产四源解析登记的资源；未联网解析，实际覆盖未知并阻断。", true, [triple.Object.Value], [evidence]));
                }
        }
        // imports无论新增/保留/移除都可能触及未解析闭包，不以字节删除当闭包已证明无影响。
        foreach (var pair in new[] { (Facts: original, Before: true), (Facts: target, Before: false) })
            if (pair.Facts is not null)
                for (var index = 0; index < pair.Facts.Length; index++)
                    foreach (var triple in pair.Facts[index].Where(triple => triple.Predicate == JenaRdfCodec.Owl + "imports"))
                    {
                        token.ThrowIfCancellationRequested();
                        Add(unknown, Conclusion("impact_imports_unresolved", "发现未加载/未解析owl:imports；本轮不联网解析依赖，其闭包影响实际未知。", true, Iris(triple), [Evidence(diff, pair.Before, SourceName(index), triple)]));
                    }
        if (exceeded)
            unknown.Add(Conclusion("impact_conclusion_budget", "结论超过256项预算，保留完整原文/hash/统计和明确未知；没有把截断当完整无影响。", true, [], [bundle]));
        return new ImpactReport { SchemaVersion = 1, ReportId = "", InputFingerprint = "", CanonicalHash = "", ExecutorVersion = ImpactContractRules.ExecutorVersion, BudgetIdentity = ImpactContractRules.BudgetIdentity, GeneratedAtUtc = generated, ExpiresAtUtc = expires, BaselineKind = kind, Diff = diff, ProfileVersion = profileVersion, ProfileHash = profileHash, TargetSemantics = semantics, ChangedIris = changedIris.Order(StringComparer.Ordinal).ToArray(), AssetReferences = assets, KnownImpacts = known.ToArray(), Blockers = blockers.ToArray(), UnknownCoverage = unknown.ToArray(), PublishEligible = assessmentEligible && semantics is not null && diff.To.Kind == VersionRefKind.Draft && blockers.Count == 0 && !unknown.Any(item => item.Blocking) };

        // 最多255项普通结论，为强制预算未知留一项位置。
        void Add(List<ImpactConclusion> collection, ImpactConclusion conclusion)
        {
            token.ThrowIfCancellationRequested();
            if (known.Count + blockers.Count + unknown.Count >= 255) { exceeded = true; return; }
            collection.Add(conclusion);
        }

        // 所有结论有至少一项已验证source或bundle证据，不复用正式EvidenceRef的假时间/图。
        ImpactConclusion Conclusion(string code, string message, bool blocking, string[] iris, ImpactEvidenceReference[] evidence) => new() { Code = code, Message = message, Blocking = blocking, AffectedIris = iris.Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray(), AssetReferences = assets, Evidence = evidence };
    }

    /// <summary>8MiB预算超限时明确撤回解释覆盖，保留原文/hash/真实统计而不伪装完整。</summary>
    private static ImpactReport BoundImpactReport(ImpactReport report)
    {
        if (Encoding.UTF8.GetByteCount(JsonSerializer.Serialize(report)) <= 8 * 1024 * 1024) return report;
        // 大数组被明确标为实际未知，来源字节和真实图比较结果仍保留。
        var sources = report.Diff.Sources.Select(source => source with { AddedTriples = [], RemovedTriples = [], TripleDeltaStatus = source.Graph.Status == GraphComparisonStatus.Equivalent ? TripleDeltaStatus.Equivalent : TripleDeltaStatus.Indeterminate }).ToArray();
        // 超预算不能继续宣称完整的命名IRI或逐三元组解释覆盖。
        var reduced = report with { Diff = report.Diff with { Sources = sources }, ChangedIris = [], KnownImpacts = [], Blockers = [], UnknownCoverage = [new ImpactConclusion { Code = "impact_report_byte_budget", Message = "完整报告超过8MiB，保留四源原文/hash/真实统计；三元组解释与引用覆盖已明确撤回为阻断UNKNOWN。", Blocking = true, AffectedIris = [], AssetReferences = [report.Diff.AssetId], Evidence = [Evidence(report.Diff, false, "bundle", null)] }], PublishEligible = false, CanonicalHash = "" };
        reduced = reduced with { CanonicalHash = ImpactContractRules.CanonicalHash(reduced) };
        if (Encoding.UTF8.GetByteCount(JsonSerializer.Serialize(reduced)) > 8 * 1024 * 1024) throw new SemanticOperationException(413, "impact_report_budget");
        return reduced;
    }

    /// <summary>标准词汇IRI只是受控语法，不将它们假定为外部待加载业务依赖。</summary>
    private static bool StandardIri(string iri) => iri.StartsWith("http://www.w3.org/", StringComparison.Ordinal) || iri.StartsWith("https://www.w3.org/", StringComparison.Ordinal) || iri.StartsWith(IdentityTimePolicy.P, StringComparison.Ordinal);

    /// <summary>只从命名项取得稳定IRI；语言/datatype仍完整保存在可信三元组中。</summary>
    private static string[] Iris(RdfTriple triple) => new[] { triple.Subject.Kind == RdfTermKind.Iri ? triple.Subject.Value : null, triple.Predicate, triple.Object.Kind == RdfTermKind.Iri ? triple.Object.Value : null }.Where(value => value is not null).Select(value => value!).Distinct(StringComparer.Ordinal).ToArray();

    /// <summary>固定四槽位名称，不从用户字段决定源位置。</summary>
    private static string SourceName(int index) => new[] { "ontology", "shapes", "vocabulary", "data" }[index];

    /// <summary>只有真实单源定位才能给source，跨源则诚实给bundle。</summary>
    private static ImpactEvidenceReference Locate(VersionDiff diff, RdfTriple[][] facts, bool before, RdfTerm? focus, string? path)
    {
        // 缺失focus/path或跨源共享时不能任意选择第一个位置。
        var matches = Enumerable.Range(0, facts.Length).Where(index => facts[index].Any(triple => triple.Subject == focus && triple.Predicate == path)).ToArray();
        // 真实唯一匹配的事实可以提供ground三元组，blank仅保留命名focus或bundle。
        var triple = matches.Length == 1 ? facts[matches[0]].First(item => item.Subject == focus && item.Predicate == path) : null;
        return Evidence(diff, before, matches.Length == 1 ? SourceName(matches[0]) : "bundle", triple);
    }

    /// <summary>每条证据精确绑定基础或目标hash，空白节点永不进入canonical定位。</summary>
    private static ImpactEvidenceReference Evidence(VersionDiff diff, bool before, string source, RdfTriple? triple)
    {
        // 证据所属版本由真实删除/新增方向决定，而非按显示文本猜测。
        var hashes = before ? diff.BaseHashes : diff.TargetHashes;
        // 可选词汇缺席使用准确bundle证据，不能伪造文件hash。
        var hash = source switch { "ontology" => hashes.OntologyHash, "shapes" => hashes.ShapesHash, "vocabulary" => hashes.VocabularyHash, "data" => hashes.DataHash, _ => hashes.BundleHash };
        if (hash is null) { source = "bundle"; hash = hashes.BundleHash; }
        return new ImpactEvidenceReference { Version = before ? diff.From : diff.To, SourceId = source, SourceHash = hash, Triple = triple?.Subject.Kind == RdfTermKind.Iri && triple.Object.Kind != RdfTermKind.Blank ? triple : null, FocusIri = triple?.Subject.Kind == RdfTermKind.Iri ? triple.Subject.Value : null, Path = triple?.Predicate, Line = null, Column = null };
    }
}
