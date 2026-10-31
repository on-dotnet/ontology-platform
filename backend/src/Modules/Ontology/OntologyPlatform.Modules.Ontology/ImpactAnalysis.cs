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
            // 声明按IRI与准确种类分别登记，不能用NamedIndividual掩盖Class定义被删除。
            var oldDefinitions = ImpactDefinitions(original ?? [[], [], [], []]);
            // 同一资源可合法有多个显式类型，各consumer只要求自己消费的声明种类。
            var newDefinitions = ImpactDefinitions(target);
            // 普通对象引用可确认命名资源存在；类型/公理消费必须另查准确声明。
            var subjects = after.Where(triple => triple.Subject.Kind == RdfTermKind.Iri).Select(triple => triple.Subject.Value).ToHashSet(StringComparer.Ordinal);
            for (var index = 0; index < target.Length; index++)
                foreach (var triple in target[index])
                {
                    token.ThrowIfCancellationRequested();
                    // 谓词位置也消费属性声明，literal客体不能被提前continue遗漏。
                    var evidence = Evidence(diff, false, SourceName(index), triple);
                    foreach (var consumer in ImpactConsumers(triple, oldDefinitions, newDefinitions))
                    {
                        token.ThrowIfCancellationRequested();
                        if (consumer.Kind == "RESOURCE" ? subjects.Contains(consumer.Iri) || ImpactBuiltin(consumer.Iri, consumer.Kind)
                            : consumer.Kind == "PROPERTY" ? new[] { JenaRdfCodec.Owl + "ObjectProperty", JenaRdfCodec.Owl + "DatatypeProperty", JenaRdfCodec.Owl + "AnnotationProperty" }.Any(kind => newDefinitions.ContainsKey((consumer.Iri, kind))) || ImpactBuiltin(consumer.Iri, consumer.Kind)
                            : newDefinitions.ContainsKey(consumer) || ImpactBuiltin(consumer.Iri, consumer.Kind)) continue;
                        // 只有原来同种显式声明被删除，才称为定义删除；其它未登记依赖保持UNKNOWN。
                        var prior = oldDefinitions.TryGetValue(consumer, out var declaration) ? declaration : ((int Source, RdfTriple? Triple)?)(null);
                        if (prior is { } removed)
                            Add(blockers, Conclusion("impact_removed_definition_referenced", "目标仍按原声明种类消费已删除的Class/ObjectProperty/DatatypeProperty定义；其它rdf:type不能替代该声明。", true, [consumer.Iri], [evidence, Evidence(diff, true, removed.Source < 0 ? "bundle" : SourceName(removed.Source), removed.Triple)]));
                        else
                            Add(unknown, Conclusion("impact_dependency_unresolved", "显式关系所需声明未在本资产登记，也不属于精确受控内建词汇；命名空间外观不是登记或无影响证明。", true, [consumer.Iri], [evidence]));
                    }
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

    /// <summary>精确声明种类的四源索引；重复来源只给bundle，不任选一个源。</summary>
    private static Dictionary<(string Iri, string Kind), (int Source, RdfTriple? Triple)> ImpactDefinitions(RdfTriple[][] graphs) =>
        graphs.SelectMany((graph, index) => graph.Select(triple => (Triple: triple, Source: index)))
            .Where(item => item.Triple.Subject.Kind == RdfTermKind.Iri && item.Triple.Predicate == JenaRdfCodec.Type && item.Triple.Object.Kind == RdfTermKind.Iri && item.Triple.Object.Value is JenaRdfCodec.Owl + "Class" or JenaRdfCodec.Owl + "ObjectProperty" or JenaRdfCodec.Owl + "DatatypeProperty" or JenaRdfCodec.Owl + "AnnotationProperty")
            .GroupBy(item => (item.Triple.Subject.Value, item.Triple.Object.Value))
            .ToDictionary(group => group.Key, group => (group.Select(item => item.Source).Distinct().Count() == 1 ? group.First().Source : -1, (RdfTriple?)group.First().Triple));

    /// <summary>依照显式consumer位置要求声明，不执行RDFS/OWL隐式类型推理。</summary>
    private static IEnumerable<(string Iri, string Kind)> ImpactConsumers(RdfTriple triple, Dictionary<(string Iri, string Kind), (int Source, RdfTriple? Triple)> before, Dictionary<(string Iri, string Kind), (int Source, RdfTriple? Triple)> after)
    {
        // 先检查谓词的属性角色，删除DatatypeProperty后保留NamedIndividual不能掩盖literal消费。
        var propertyKind = triple.Object.Kind == RdfTermKind.Literal ? JenaRdfCodec.Owl + "DatatypeProperty" : JenaRdfCodec.Owl + "ObjectProperty";
        if (before.ContainsKey((triple.Predicate, propertyKind)) || after.ContainsKey((triple.Predicate, propertyKind)))
        {
            yield return (triple.Predicate, propertyKind);
            if (triple.Object.Kind == RdfTermKind.Iri) yield return (triple.Object.Value, "RESOURCE");
        }
        if (triple.Object.Kind != RdfTermKind.Iri) yield break;
        if (triple.Predicate == JenaRdfCodec.Type) yield return (triple.Object.Value, JenaRdfCodec.Owl + "Class");
        else if (triple.Predicate is "http://www.w3.org/2000/01/rdf-schema#subClassOf" or JenaRdfCodec.Owl + "equivalentClass" or JenaRdfCodec.Owl + "disjointWith")
        {
            if (triple.Subject.Kind == RdfTermKind.Iri) yield return (triple.Subject.Value, JenaRdfCodec.Owl + "Class");
            yield return (triple.Object.Value, JenaRdfCodec.Owl + "Class");
        }
        else if (triple.Predicate == JenaRdfCodec.Owl + "inverseOf")
        {
            if (triple.Subject.Kind == RdfTermKind.Iri) yield return (triple.Subject.Value, JenaRdfCodec.Owl + "ObjectProperty");
            yield return (triple.Object.Value, JenaRdfCodec.Owl + "ObjectProperty");
        }
        else if (triple.Predicate is "http://www.w3.org/2000/01/rdf-schema#domain" or "http://www.w3.org/2000/01/rdf-schema#range")
        {
            if (triple.Subject.Kind == RdfTermKind.Iri)
            {
                // 只沿明确已有属性种类检查主体，不把RDFS隐含domain当新增声明。
                var kinds = new[] { JenaRdfCodec.Owl + "ObjectProperty", JenaRdfCodec.Owl + "DatatypeProperty", JenaRdfCodec.Owl + "AnnotationProperty" }.Where(kind => before.ContainsKey((triple.Subject.Value, kind)) || after.ContainsKey((triple.Subject.Value, kind))).ToArray();
                foreach (var kind in kinds) yield return (triple.Subject.Value, kind);
                if (kinds.Length == 0) yield return (triple.Subject.Value, "PROPERTY");
            }
            yield return (triple.Object.Value, triple.Predicate.EndsWith("#range", StringComparison.Ordinal) && (before.ContainsKey((triple.Subject.Value, JenaRdfCodec.Owl + "DatatypeProperty")) || after.ContainsKey((triple.Subject.Value, JenaRdfCodec.Owl + "DatatypeProperty"))) ? "DATATYPE" : JenaRdfCodec.Owl + "Class");
        }
        else if (triple.Predicate is ShapePolicy.Sh + "targetClass" or ShapePolicy.Sh + "class") yield return (triple.Object.Value, JenaRdfCodec.Owl + "Class");
        else if (triple.Predicate == ShapePolicy.Sh + "datatype") yield return (triple.Object.Value, "DATATYPE");
        else if (triple.Predicate == ShapePolicy.Sh + "path")
        {
            // Shape路径需要同一种属性声明；多类型只在实际相应consumer存在时分别约束。
            var kinds = new[] { JenaRdfCodec.Owl + "ObjectProperty", JenaRdfCodec.Owl + "DatatypeProperty", JenaRdfCodec.Owl + "AnnotationProperty" }.Where(kind => before.ContainsKey((triple.Object.Value, kind)) || after.ContainsKey((triple.Object.Value, kind))).ToArray();
            foreach (var kind in kinds) yield return (triple.Object.Value, kind);
            if (kinds.Length == 0) yield return (triple.Object.Value, "PROPERTY");
        }
    }

    /// <summary>只豁免已冻结受控词汇的准确IRI；W3C站点或平台前缀本身不提供登记证明。</summary>
    private static bool ImpactBuiltin(string iri, string kind)
    {
        // 当前profile已登记的声明类型和有限域类型，不能按命名空间整体放行。
        string[] types = [JenaRdfCodec.Owl + "Class", JenaRdfCodec.Owl + "ObjectProperty", JenaRdfCodec.Owl + "DatatypeProperty", JenaRdfCodec.Owl + "AnnotationProperty", JenaRdfCodec.Owl + "NamedIndividual", JenaRdfCodec.Owl + "Ontology", "http://www.w3.org/1999/02/22-rdf-syntax-ns#Statement", "http://www.w3.org/2004/02/skos/core#Concept", "http://www.w3.org/2004/02/skos/core#ConceptScheme", "http://www.w3.org/2006/time#Instant", "http://www.w3.org/2006/time#Interval", ShapePolicy.Sh + "NodeShape", ShapePolicy.Sh + "PropertyShape", IdentityTimePolicy.P + "UnitDefinition", IdentityTimePolicy.P + "QuantityKind", IdentityTimePolicy.P + "Dimension", IdentityTimePolicy.P + "StandardSource", IdentityTimePolicy.P + "IdentityClaim", IdentityTimePolicy.P + "Event"];
        if (kind is "RESOURCE" or JenaRdfCodec.Owl + "Class") return types.Contains(iri, StringComparer.Ordinal) || iri is JenaRdfCodec.Owl + "Thing" or JenaRdfCodec.Owl + "Nothing" or "http://www.w3.org/2000/01/rdf-schema#Resource" or "http://www.w3.org/2000/01/rdf-schema#Literal";
        if (kind == "PROPERTY") return iri is "http://www.w3.org/2000/01/rdf-schema#label" or "http://www.w3.org/2000/01/rdf-schema#comment";
        if (kind != "DATATYPE") return false;
        // 标准datatype仍由RIOT处理词法，本检查只确认明确有限的类型IRI，不执行换算。
        string[] datatypes = ["string", "boolean", "decimal", "float", "double", "duration", "dateTime", "dateTimeStamp", "time", "date", "gYearMonth", "gYear", "gMonthDay", "gDay", "gMonth", "hexBinary", "base64Binary", "anyURI", "QName", "NOTATION", "integer", "nonPositiveInteger", "negativeInteger", "long", "int", "short", "byte", "nonNegativeInteger", "unsignedLong", "unsignedInt", "unsignedShort", "unsignedByte", "positiveInteger", "normalizedString", "token", "language", "Name", "NCName", "ID", "IDREF", "IDREFS", "ENTITY", "ENTITIES", "NMTOKEN", "NMTOKENS", "dayTimeDuration", "yearMonthDuration"];
        return datatypes.Any(name => iri == "http://www.w3.org/2001/XMLSchema#" + name) || iri is "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString" or "http://www.w3.org/1999/02/22-rdf-syntax-ns#XMLLiteral";
    }

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
