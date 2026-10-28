using System.Globalization;
using System.Text.RegularExpressions;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>M3显式SKOS与Synthetic单位治理，不执行词汇下载、OWL推理或单位换算。</summary>
public sealed partial class JenaSemanticRuntime
{
    /// <summary>W3C SKOS标准命名空间。</summary>
    private const string Skos = "http://www.w3.org/2004/02/skos/core#";

    /// <summary>平台自身有限语义词汇命名空间。</summary>
    private const string PlatformSemantics = "urn:ontology-platform:semantics:";

    /// <summary>来源关系标准命名空间。</summary>
    private const string Prov = "http://www.w3.org/ns/prov#";

    /// <summary>XML Schema数据类型命名空间。</summary>
    private const string Xsd = "http://www.w3.org/2001/XMLSchema#";

    /// <summary>本轮明确登记的SKOS谓词，不对未知SKOS结构开放编辑。</summary>
    private static readonly HashSet<string> SkosPredicates = new(["prefLabel", "altLabel", "hiddenLabel", "notation", "definition", "scopeNote", "note", "broader", "narrower", "related", "inScheme", "topConceptOf", "hasTopConcept", "exactMatch", "closeMatch", "broadMatch", "narrowMatch", "relatedMatch"], StringComparer.Ordinal);

    /// <summary>七个SI基本量指数按长度、质量、时间、电流、温度、物质的量、光强固定排序。</summary>
    private static readonly string[] Exponents = ["lengthExponent", "massExponent", "timeExponent", "electricCurrentExponent", "temperatureExponent", "amountExponent", "luminousIntensityExponent"];

    /// <summary>仅有限单位元数据及受控废弃annotation进入v3支持白名单。</summary>
    private static bool M3MetadataPredicate(string predicate) => predicate == JenaRdfCodec.Owl + "deprecated" || new[] { "canonicalUnit", "version", "quantityKind", "dimension", "symbol", "standardSource", "precision", "synthetic", "nominalUnit" }.Concat(Exponents).Any(name => predicate == PlatformSemantics + name);

    /// <summary>仅v3正式部署、回验及正式读取追加当前政策，历史v1/v2不追溯升级。</summary>
    private static bool PublicationGovernance(ReleaseManifest manifest, SourceBundle sources, RdfTriple[][] parsed, CancellationToken token) => manifest.Semantics?.ProfileVersion != "3" || VocabularyDiagnostics(parsed, JenaRdfCodec.Hashes(sources), token).All(item => item.Diagnostic.Severity == DiagnosticSeverity.Info);

    /// <summary>全四源治理诊断入口，SHACL报告保持引擎原始结果。</summary>
    private static AssessmentDiagnostic[] VocabularyDiagnostics(RdfTriple[][] parsed, SourceHashes hashes, CancellationToken token)
    {
        // 每次运行独享诊断上下文，不在全局缓存源或用户信息。
        var governance = new VocabularyGovernance(parsed, hashes, token);
        governance.CheckSkos();
        governance.CheckUnits();
        return governance.Diagnostics.Distinct().ToArray();
    }

    /// <summary>当前有界已解析图的纯治理检查器，没有网络或第二套持久化权威。</summary>
    private sealed partial class VocabularyGovernance
    {
        /// <summary>四个来源图，仅用于真实来源定位。</summary>
        private readonly RdfTriple[][] parsed;

        /// <summary>按RDF集合语义去重后的完整图。</summary>
        private readonly RdfTriple[] triples;

        /// <summary>同一原始源的精确散列。</summary>
        private readonly SourceHashes hashes;

        /// <summary>与运行时共享的执行取消预算。</summary>
        private readonly CancellationToken token;

        /// <summary>全部有界检查实际发现的诊断。</summary>
        internal List<AssessmentDiagnostic> Diagnostics { get; } = [];

        /// <summary>固定已解析图与源hash，不解析或改写Turtle。</summary>
        internal VocabularyGovernance(RdfTriple[][] parsed, SourceHashes hashes, CancellationToken token)
        {
            this.parsed = parsed;
            this.hashes = hashes;
            this.token = token;
            triples = parsed.SelectMany(graph => graph).Distinct().ToArray();
        }

        /// <summary>读取同一精确主体的指定谓词，不隐式选择多值中的第一项。</summary>
        private RdfTerm[] Values(RdfTerm subject, string predicate) => triples.Where(triple => triple.Subject == subject && triple.Predicate == predicate).Select(triple => triple.Object).Distinct().ToArray();

        /// <summary>仅显式命名IRI类型声明登记为本轮治理实体。</summary>
        private HashSet<RdfTerm> Registered(string type) => triples.Where(triple => triple.Subject.Kind == RdfTermKind.Iri && triple.Predicate == JenaRdfCodec.Type && triple.Object.Kind == RdfTermKind.Iri && triple.Object.Value == type).Select(triple => triple.Subject).ToHashSet();

        /// <summary>保留精确规则码，并在无法唯一定位来源时诚实绑定bundle。</summary>
        private void Add(string code, RdfTerm subject, string path, string message, bool unknown = false)
        {
            token.ThrowIfCancellationRequested();
            // 优先定位focus/path的真实事实，缺失谓词使用该focus的登记源作为证据。
            var sources = Enumerable.Range(0, 4).Where(index => parsed[index].Any(triple => triple.Subject == subject && triple.Predicate == path)).ToArray();
            if (sources.Length == 0) sources = Enumerable.Range(0, 4).Where(index => parsed[index].Any(triple => triple.Subject == subject)).ToArray();
            // 跨源冲突绝不猜第一源。
            var source = sources.Length == 1 ? new[] { "ontology", "shapes", "vocabulary", "data" }[sources[0]] : "bundle";
            Diagnostics.Add(new AssessmentDiagnostic { SourceId = source, SourceHash = source switch { "ontology" => hashes.OntologyHash, "shapes" => hashes.ShapesHash, "vocabulary" => hashes.VocabularyHash ?? hashes.BundleHash, "data" => hashes.DataHash, _ => hashes.BundleHash }, Diagnostic = new SemanticDiagnostic { Code = code, Severity = unknown ? DiagnosticSeverity.Warning : DiagnosticSeverity.Error, FocusNode = subject, Path = path, Message = message }, Line = null, Column = null, SourceShape = null });
        }

        /// <summary>仅为SKOS完整性统一RDF字符串类型与language大小写，原始投影不变。</summary>
        private static RdfTerm LabelIdentity(RdfTerm term) => term with { Language = term.Language?.ToLowerInvariant(), Datatype = term.Language is not null ? "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString" : term.Datatype ?? Xsd + "string" };

        /// <summary>BCP47语法验证支持普通、private use及登记的grandfathered形式，不把语言政策当语法。</summary>
        private static bool LanguageSyntax(string language) => Regex.IsMatch(language, @"^(?:(?:[a-z]{2,3}(?:-[a-z]{3}){0,3}|[a-z]{4}|[a-z]{5,8})(?:-[a-z]{4})?(?:-(?:[a-z]{2}|[0-9]{3}))?(?:-(?:[a-z0-9]{5,8}|[0-9][a-z0-9]{3}))*(?:-[0-9a-wy-z](?:-[a-z0-9]{2,8})+)*(?:-x(?:-[a-z0-9]{1,8})+)?|x(?:-[a-z0-9]{1,8})+|en-GB-oed|i-(?:ami|bnn|default|enochian|hak|klingon|lux|mingo|navajo|pwn|tao|tay|tsu)|sgn-(?:BE-FR|BE-NL|CH-DE)|art-lojban|cel-gaulish|no-bok|no-nyn|zh-guoyu|zh-hakka|zh-min|zh-min-nan|zh-xiang)$", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(100));

        /// <summary>只检查已登记显式SKOS事实，区分W3C完整性规则与本平台治理政策。</summary>
        internal void CheckSkos()
        {
            // 标签检查适用于所有资源，不以显式Concept声明筛掉其它主体。
            var labels = triples.Where(triple => triple.Predicate is Skos + "prefLabel" or Skos + "altLabel" or Skos + "hiddenLabel").ToArray();
            foreach (var label in labels)
            {
                token.ThrowIfCancellationRequested();
                if (label.Object.Kind != RdfTermKind.Literal || string.IsNullOrWhiteSpace(label.Object.Value) || label.Object.Datatype is not (null or Xsd + "string" or "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString"))
                    Add("skos_label_term_invalid", label.Subject, label.Predicate, "SKOS标签必须为非空plain或language literal。");
                else if (label.Object.Language is null)
                    Add("skos_label_language_required", label.Subject, label.Predicate, "平台正式术语政策要求显式语言；源码原文仍保留。");
                else if (!LanguageSyntax(label.Object.Language))
                    Add("skos_label_language_invalid", label.Subject, label.Predicate, "语言标签不符合BCP47语法。");
                else if (label.Object.Language.Split('-')[0].ToLowerInvariant() is not ("zh" or "en"))
                    Add("language_policy_unknown", label.Subject, label.Predicate, "语言语法合法但本轮治理政策未确定，保留原文并显示UNKNOWN。", true);
            }
            foreach (var group in labels.GroupBy(triple => triple.Subject))
            {
                // S14以不区分大小写的语言比较，而S13以完整literal身份比较。
                foreach (var language in group.Where(triple => triple.Predicate == Skos + "prefLabel" && triple.Object.Kind == RdfTermKind.Literal).GroupBy(triple => triple.Object.Language?.ToLowerInvariant() ?? ""))
                    if (language.Select(triple => LabelIdentity(triple.Object)).Distinct().Count() > 1) Add("skos_pref_label_conflict", group.Key, Skos + "prefLabel", "SKOS S14：每个资源每种语言最多一个首选标签。");
                foreach (var value in group.GroupBy(triple => LabelIdentity(triple.Object)))
                    if (value.Select(triple => triple.Predicate).Distinct().Count() > 1)
                        foreach (var path in value.Select(triple => triple.Predicate).Distinct()) Add("skos_label_relation_conflict", group.Key, path, "SKOS S13：同一literal不能同时用作pref/alt/hidden标签。");
            }
            // Scheme和Concept仅从明确类型登记，不从关系推理生成类型。
            var concepts = Registered(Skos + "Concept");
            // Scheme声明允许多个Concept共享或同一Concept加入多个。
            var registeredSchemes = Registered(Skos + "ConceptScheme");
            // 各Concept明确Scheme集合供notation及mapping检查复用。
            var schemes = concepts.ToDictionary(concept => concept, concept => Values(concept, Skos + "inScheme").Concat(Values(concept, Skos + "topConceptOf")).Concat(triples.Where(triple => triple.Predicate == Skos + "hasTopConcept" && triple.Object == concept).Select(triple => triple.Subject)).Distinct().ToHashSet());
            foreach (var concept in concepts)
            {
                token.ThrowIfCancellationRequested();
                if (schemes[concept].Count == 0 || schemes[concept].Any(scheme => !registeredSchemes.Contains(scheme))) Add("skos_scheme_reference_missing", concept, Skos + "inScheme", "平台治理要求Concept至少属于一个明确登记的ConceptScheme，引用不得缺失。");
            }
            foreach (var triple in triples.Where(triple => triple.Predicate is Skos + "inScheme" or Skos + "topConceptOf" or Skos + "hasTopConcept"))
            {
                // inverse声明保持原始位置，不把hasTopConcept的主体误认为Concept。
                var scheme = triple.Predicate == Skos + "hasTopConcept" ? triple.Subject : triple.Object;
                // topConcept/inScheme两端都必须是明确登记实体。
                var concept = triple.Predicate == Skos + "hasTopConcept" ? triple.Object : triple.Subject;
                if (!registeredSchemes.Contains(scheme)) Add("skos_scheme_reference_missing", triple.Subject, triple.Predicate, "引用的Scheme没有明确ConceptScheme声明。");
                if (!concepts.Contains(concept)) Add("skos_concept_reference_missing", triple.Subject, triple.Predicate, "引用的Concept没有明确Concept声明。");
            }
            // 只对明确关系建有向边；narrower及narrowMatch反向等价于broader方向。
            var relations = triples.Where(triple => triple.Predicate is Skos + "broader" or Skos + "narrower" or Skos + "related" or Skos + "exactMatch" or Skos + "closeMatch" or Skos + "broadMatch" or Skos + "narrowMatch" or Skos + "relatedMatch").ToArray();
            foreach (var relation in relations)
            {
                if (!concepts.Contains(relation.Subject) || !concepts.Contains(relation.Object)) Add("skos_concept_reference_missing", relation.Subject, relation.Predicate, "关系两端必须是明确登记Concept，不能按标签猜身份。");
                if (relation.Predicate.EndsWith("Match", StringComparison.Ordinal) && (!schemes.TryGetValue(relation.Subject, out var left) || !schemes.TryGetValue(relation.Object, out var right) || !left.Any(a => registeredSchemes.Contains(a) && right.Any(b => registeredSchemes.Contains(b) && a != b))))
                    Add("skos_mapping_scheme_conflict", relation.Subject, relation.Predicate, "映射要求两端已登记Concept且至少存在一对不同的明确Scheme。");
            }
            // 邻接表只收合法IRI端点，不将unknown或literal当Concept身份。
            var hierarchy = relations.Where(relation => relation.Predicate is Skos + "broader" or Skos + "narrower" or Skos + "broadMatch" or Skos + "narrowMatch").Select(relation => (From: relation.Predicate is Skos + "narrower" or Skos + "narrowMatch" ? relation.Object : relation.Subject, To: relation.Predicate is Skos + "narrower" or Skos + "narrowMatch" ? relation.Subject : relation.Object)).Where(edge => concepts.Contains(edge.From) && concepts.Contains(edge.To)).ToArray();
            // 每次可达检查共享取消预算；不物化推理图或向用户返回新增事实。
            bool Reachable(RdfTerm from, RdfTerm to)
            {
                // 显式队列避免深层关系造成递归栈溢出。
                var pending = new Queue<RdfTerm>();
                // 每个节点每次检查最多访问一次。
                var visited = new HashSet<RdfTerm>();
                pending.Enqueue(from);
                while (pending.TryDequeue(out var current))
                {
                    token.ThrowIfCancellationRequested();
                    if (!visited.Add(current)) continue;
                    foreach (var edge in hierarchy.Where(edge => edge.From == current))
                    {
                        if (edge.To == to) return true;
                        pending.Enqueue(edge.To);
                    }
                }
                return false;
            }
            foreach (var relation in relations)
            {
                if (relation.Predicate is Skos + "broader" or Skos + "narrower" or Skos + "broadMatch" or Skos + "narrowMatch")
                {
                    // 检查边反向可达性可同时发现自身环及多节点环。
                    var from = relation.Predicate is Skos + "narrower" or Skos + "narrowMatch" ? relation.Object : relation.Subject;
                    // 与显式broader相同方向定义，不按名称猜前后端。
                    var to = relation.Predicate is Skos + "narrower" or Skos + "narrowMatch" ? relation.Subject : relation.Object;
                    if (Reachable(to, from)) Add("skos_hierarchy_cycle", relation.Subject, relation.Predicate, "平台有界层次图含环，属于治理冲突，不宣称OWL逻辑矛盾。");
                }
                if (relation.Predicate is Skos + "related" or Skos + "relatedMatch" && (relation.Subject == relation.Object || Reachable(relation.Subject, relation.Object) || Reachable(relation.Object, relation.Subject)))
                    Add(relation.Predicate == Skos + "relatedMatch" ? "skos_mapping_relation_conflict" : "skos_related_hierarchy_conflict", relation.Subject, relation.Predicate, "关联关系不得自指或与任一方向可达层次重叠。");
                if (relation.Predicate == Skos + "exactMatch" && relations.Any(other => other.Predicate is Skos + "broadMatch" or Skos + "narrowMatch" or Skos + "relatedMatch" && (other.Subject == relation.Subject && other.Object == relation.Object || other.Subject == relation.Object && other.Object == relation.Subject)))
                    Add("skos_mapping_relation_conflict", relation.Subject, relation.Predicate, "SKOS S46：exactMatch不得与同一对的broad/narrow/relatedMatch重叠。");
            }
            // notation唯一性只对共享明确Scheme、相同datatype和value判定。
            var notations = triples.Where(triple => triple.Predicate == Skos + "notation" && triple.Object.Kind == RdfTermKind.Literal).ToArray();
            foreach (var notation in notations)
            {
                if (!schemes.TryGetValue(notation.Subject, out var memberships) || memberships.Count == 0 || memberships.Any(scheme => !registeredSchemes.Contains(scheme)))
                {
                    Add("skos_reference_ambiguous", notation.Subject, notation.Predicate, "Scheme未明确登记，无法确定notation唯一性。", true);
                    continue;
                }
                if (notations.Any(other => other.Subject != notation.Subject && other.Object.Value == notation.Object.Value && (other.Object.Datatype ?? Xsd + "string") == (notation.Object.Datatype ?? Xsd + "string") && schemes.TryGetValue(other.Subject, out var otherSchemes) && memberships.Overlaps(otherSchemes))) Add("skos_notation_duplicate", notation.Subject, notation.Predicate, "共享Scheme内同datatype及词法值的notation必须唯一。");
            }
            // 当前四源所有明确关系或单位引用废弃项都报错；没有前一修订不声称时间差分。
            var deprecated = triples.Where(triple => triple.Predicate == JenaRdfCodec.Owl + "deprecated" && triple.Object.Kind == RdfTermKind.Literal && triple.Object.Datatype == Xsd + "boolean" && triple.Object.Value is "true" or "1").Select(triple => triple.Subject).ToHashSet();
            foreach (var reference in triples.Where(triple => triple.Object.Kind == RdfTermKind.Iri && deprecated.Contains(triple.Object) && (relations.Contains(triple) || triple.Predicate is PlatformSemantics + "nominalUnit" or PlatformSemantics + "quantityKind" or PlatformSemantics + "dimension" or PlatformSemantics + "standardSource" or Skos + "inScheme" or Skos + "topConceptOf" or Skos + "hasTopConcept"))) Add("semantic_reference_deprecated", reference.Subject, reference.Predicate, "当前四源引用已废弃IRI，须显式修复引用并保留历史身份。");
        }

    }
}
