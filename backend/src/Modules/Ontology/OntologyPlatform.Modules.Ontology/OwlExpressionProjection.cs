using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>仅投影已由RIOT解析的RDF项；有限列表、共享引用和损坏结构均不改变原文。</summary>
internal sealed class OwlExpressionProjection
{
    /// <summary>标准OWL命名空间，不以名称近似匹配术语。</summary>
    private const string Owl = "http://www.w3.org/2002/07/owl#";

    /// <summary>标准RDF列表命名空间。</summary>
    private const string Rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#";

    /// <summary>标准非负整数数据类型。</summary>
    private const string NonNegativeInteger = "http://www.w3.org/2001/XMLSchema#nonNegativeInteger";

    /// <summary>表达式嵌套上限，不将列表rest链当作表达式深度。</summary>
    private const int MaxDepth = 32;

    /// <summary>主体节点及单条列表项的独立有界上限。</summary>
    private const int MaxNodes = 512;

    /// <summary>完整OWL2 RDF词汇白名单；未知词汇必须显式诊断。</summary>
    private static readonly HashSet<string> OwlTerms = new(("AllDifferent AllDisjointClasses AllDisjointProperties Annotation AnnotationProperty AsymmetricProperty Axiom Class DataRange DatatypeProperty DeprecatedClass DeprecatedProperty FunctionalProperty InverseFunctionalProperty IrreflexiveProperty NamedIndividual NegativePropertyAssertion Nothing ObjectProperty Ontology OntologyProperty ReflexiveProperty Restriction SymmetricProperty Thing TransitiveProperty allValuesFrom annotatedProperty annotatedSource annotatedTarget assertionProperty backwardCompatibleWith bottomDataProperty bottomObjectProperty cardinality complementOf datatypeComplementOf deprecated differentFrom disjointUnionOf disjointWith distinctMembers equivalentClass equivalentProperty hasKey hasSelf hasValue imports incompatibleWith intersectionOf inverseOf maxCardinality maxQualifiedCardinality members minCardinality minQualifiedCardinality onClass onDataRange onDatatype onProperties onProperty oneOf priorVersion propertyChainAxiom propertyDisjointWith qualifiedCardinality sameAs someValuesFrom sourceIndividual targetIndividual targetValue topDataProperty topObjectProperty unionOf versionIRI versionInfo withRestrictions").Split(' '), StringComparer.Ordinal);

    /// <summary>普通及qualified基数谓词，不将其误当SHACL数量约束。</summary>
    private static readonly HashSet<string> Cardinalities = new([Owl + "cardinality", Owl + "minCardinality", Owl + "maxCardinality", Owl + "qualifiedCardinality", Owl + "minQualifiedCardinality", Owl + "maxQualifiedCardinality"], StringComparer.Ordinal);

    /// <summary>restriction单个构造槽位，不能把多个限制字段误认成单一完整表达式。</summary>
    private static readonly HashSet<string> RestrictionConstructors = new(Cardinalities.Concat([Owl + "someValuesFrom", Owl + "allValuesFrom", Owl + "hasValue", Owl + "hasSelf"]), StringComparer.Ordinal);

    /// <summary>以RDF列表表达的标准OWL构造。</summary>
    private static readonly HashSet<string> ListPredicates = new([Owl + "intersectionOf", Owl + "unionOf", Owl + "oneOf", Owl + "propertyChainAxiom", Owl + "hasKey", Owl + "members", Owl + "distinctMembers", Owl + "disjointUnionOf", Owl + "onProperties", Owl + "withRestrictions"], StringComparer.Ordinal);

    /// <summary>完整图按规范化主体索引，仅用于本次只读快照。</summary>
    private readonly Dictionary<RdfTerm, RdfTriple[]> subjects;

    /// <summary>已完成有界列表遍历的缓存，保存实际顺序和共享引用。</summary>
    private readonly Dictionary<RdfTerm, RdfTerm[]> lists = [];

    /// <summary>已检查过的列表单元；共享尾链无需重复物化每个后缀。</summary>
    private readonly HashSet<RdfTerm> checkedListNodes = [];

    /// <summary>所有输出列表展开项共用512项预算，避免共享尾链二次方放大响应。</summary>
    private int projectedListItems;

    /// <summary>固定预算诊断，不包含输入正文或伪造行列。</summary>
    private readonly List<OwlExpressionDiagnostic> diagnostics = [];

    /// <summary>诊断的结构身份去重，避免共享节点重复放大输出。</summary>
    private readonly HashSet<(string, RdfTerm?, string?)> diagnosticKeys = [];

    /// <summary>解析和投影共享同一取消/超时信号。</summary>
    private readonly CancellationToken token;

    /// <summary>存在不能准确结构化的内容时必须失败关闭。</summary>
    private bool indeterminate;

    /// <summary>记录本次源的有限主体索引，不建立通用语义引擎。</summary>
    private OwlExpressionProjection(RdfTriple[] triples, CancellationToken token)
    {
        this.token = token;
        subjects = triples.GroupBy(item => item.Subject).ToDictionary(group => group.Key, group => group.ToArray());
    }

    /// <summary>从完整RIOT三元组构建独立源的有限只读结构。</summary>
    /// <param name="sourceId">四源固定槽位。</param>
    /// <param name="sourceHash">权威原文散列。</param>
    /// <param name="triples">真实解析的完整三元组。</param>
    /// <param name="publicationBlocked">既有profile是否阻断本源发布。</param>
    /// <param name="token">共享取消信号。</param>
    /// <returns>源保真与结构完整性独立报告的只读事实。</returns>
    internal static OwlExpressionSource Build(string sourceId, string sourceHash, RdfTriple[] triples, bool publicationBlocked, CancellationToken token)
    {
        token.ThrowIfCancellationRequested();
        // 只在新投影统一codec历史的subject/object blank前缀，不回写原图或持久对象。
        var normalized = triples.Select(item => item with { Subject = Normalize(item.Subject), Object = Normalize(item.Object) }).Distinct().ToArray();
        // 单次投影持有本源索引，不能将不同源同名blank合并。
        var projection = new OwlExpressionProjection(normalized, token);
        return projection.Project(sourceId, sourceHash, publicationBlocked);
    }

    /// <summary>将blank引用统一为_:前缀，literal词法/语言/datatype逐字段保持。</summary>
    private static RdfTerm Normalize(RdfTerm term) => term.Kind == RdfTermKind.Blank && !term.Value.StartsWith("_:", StringComparison.Ordinal)
        ? term with { Value = "_:" + term.Value } : term;

    /// <summary>完整检查所有分量，再按硬上限输出；截断必须标无法确定。</summary>
    private OwlExpressionSource Project(string sourceId, string sourceHash, bool publicationBlocked)
    {
        if (subjects.Count > MaxNodes) Add("expression_budget_exceeded", "原文已保留；结构主体数超出512节点预算。", null, null);
        // 有界确定性子集仅用于显示，超限状态已撤回结构完整结论。
        var selected = subjects.Keys.OrderBy(TermKey, StringComparer.Ordinal).Take(MaxNodes).ToArray();
        // 优先检查被非rest谓词引用的真实列表head，避免随机blank排序反复展开尾链。
        var heads = subjects.Values.SelectMany(items => items).Where(item => item.Predicate != Rdf + "rest" && IsList(item.Object)).Select(item => item.Object).Distinct().Take(MaxNodes).ToArray();
        foreach (var head in heads) ReadList(head);
        // 再检查所有主体，使没有head的纯环及断半链也不会漏过。
        foreach (var subject in selected)
        {
            token.ThrowIfCancellationRequested();
            Inspect(subject);
        }
        // 从每个分量检查，纯环没有入度为零的root也不能漏诊。
        var state = new Dictionary<RdfTerm, int>();
        // 最长表达式嵌套在完成节点后复用，避免共享DAG指数展开。
        var depths = new Dictionary<RdfTerm, int>();
        foreach (var subject in selected) Visit(subject, 1, state, depths);
        // flat引用使每个主体只出现一次，properties完整保留所有实际RDF项。
        var nodes = selected.Select(subject => new OwlExpressionNode
        {
            Term = subject,
            Kind = Kind(subject),
            Properties = subjects[subject].GroupBy(item => item.Predicate).OrderBy(group => group.Key, StringComparer.Ordinal)
                .Select(group => new OwlExpressionProperty { PredicateIri = group.Key, Values = group.Select(item => item.Object).OrderBy(TermKey, StringComparer.Ordinal).ToArray() }).ToArray(),
            OrderedItems = lists.GetValueOrDefault(subject, [])
        }).ToArray();
        // 命名主体和匿名无入度主体作为视图入口；其余共享结构保留为引用。
        var incoming = subjects.Values.SelectMany(items => items).Where(item => item.Object.Kind == RdfTermKind.Blank).Select(item => item.Object).ToHashSet();
        // 纯环也提供真实入口，不能在有诊断时渲染成“空结构”。
        var roots = selected.Where(subject => subject.Kind == RdfTermKind.Iri || !incoming.Contains(subject)).ToArray();
        if (roots.Length == 0 && selected.Length > 0) roots = [selected[0]];
        return new OwlExpressionSource
        {
            SourceId = sourceId,
            SourceHash = sourceHash,
            Status = indeterminate ? "INDETERMINATE" : "COMPLETE",
            SourcePreserved = true,
            ReadOnlyStructured = !indeterminate,
            Editable = false,
            PublishEligible = publicationBlocked || indeterminate ? "BLOCKED" : "NOT_ASSESSED",
            Inferred = false,
            Roots = roots,
            Nodes = nodes,
            Diagnostics = diagnostics.ToArray()
        };
    }

    /// <summary>检验真实标准项、列表及restriction形状，未知内容不静默解释。</summary>
    private void Inspect(RdfTerm subject)
    {
        foreach (var triple in subjects[subject])
        {
            token.ThrowIfCancellationRequested();
            if (triple.Predicate.StartsWith(Owl, StringComparison.Ordinal) && !OwlTerms.Contains(triple.Predicate[Owl.Length..])
                || triple.Predicate == Rdf + "type" && triple.Object.Kind == RdfTermKind.Iri && triple.Object.Value.StartsWith(Owl, StringComparison.Ordinal) && !OwlTerms.Contains(triple.Object.Value[Owl.Length..]))
                Add("owl_term_unknown", "原文保留；遇到未登记OWL词汇，不能确认结构语义。", subject, triple.Predicate);
            if (triple.Predicate == Owl + "imports")
                Add("imports_not_loaded", "仅显示imports原始引用；不联网、不加载或执行未锁定闭包。", subject, triple.Predicate, invalid: false);
            if (Cardinalities.Contains(triple.Predicate) && !ValidCardinality(triple.Object))
                Add("cardinality_invalid", "基数必须为合法xsd:nonNegativeInteger词法，保留原项且不按SHACL计数解释。", subject, triple.Predicate);
            if (ListPredicates.Contains(triple.Predicate))
            {
                if (triple.Object.Kind == RdfTermKind.Iri && triple.Object.Value == Rdf + "nil") continue;
                if (triple.Object.Kind != RdfTermKind.Blank || !subjects.ContainsKey(triple.Object))
                    Add("list_invalid", "列表引用缺失或目标不是RDF列表；原文保持不变。", subject, triple.Predicate);
                else ReadList(triple.Object);
            }
            if (triple.Object.Kind == RdfTermKind.Blank && !subjects.ContainsKey(triple.Object))
                Add("expression_reference_missing", "空白引用没有本源主体定义；不从其他源补齐。", subject, triple.Predicate);
        }
        if (IsList(subject) && !checkedListNodes.Contains(subject)) ReadList(subject);
        // 同一空白结构有多个入边时显示引用；共享不等于损坏或循环。
        if (subject.Kind == RdfTermKind.Blank && subjects.Values.SelectMany(items => items).Count(item => item.Object == subject) > 1)
            Add("shared_blank_reference", "该空白结构由多个位置共享；只读视图使用引用，不复制或改写。", subject, null, invalid: false);
        InspectRestriction(subject);
    }

    /// <summary>只验证只读restriction形状，不执行OWL推理或把开放世界关系解释成业务必填。</summary>
    private void InspectRestriction(RdfTerm subject)
    {
        // 识别实际Restriction声明及其结构字段，防止缺类型或未知构造仍宣称完整。
        var declared = Values(subject, Rdf + "type").Any(item => item.Kind == RdfTermKind.Iri && item.Value == Owl + "Restriction");
        // 同一主体上的全部构造槽位都必须计数，不能任选某个cardinality或量词。
        var constructors = subjects[subject].Where(item => RestrictionConstructors.Contains(item.Predicate)).ToArray();
        // 属性与限定目标也能触发残缺restriction诊断。
        var properties = Values(subject, Owl + "onProperty");
        // 数据范围与类限定互斥，ordinary cardinality不允许混入限定目标。
        var qualifiers = subjects[subject].Where(item => item.Predicate is Owl + "onClass" or Owl + "onDataRange").ToArray();
        if (!declared && constructors.Length == 0 && properties.Length == 0 && qualifiers.Length == 0 && Values(subject, Owl + "onProperties").Length == 0) return;
        if (!declared || properties.Length != 1 || !NamedIri(properties[0]) || Values(subject, Owl + "onProperties").Length != 0)
            Add("restriction_invalid", "只读restriction要求显式类型及唯一命名IRI onProperty；逆属性表达式和多属性构造保留源码但尚不能确认结构。", subject, Owl + "onProperty");
        if (constructors.Length != 1)
        {
            Add("restriction_invalid", "一个restriction必须恰好具有一个量词、hasValue/hasSelf或基数构造；不任意选择冲突字段。", subject, null);
            return;
        }
        // 唯一构造已经确定，后续才检验相应对象槽位的RDF种类。
        var constructor = constructors[0];
        // qualified只由标准基数谓词识别，不按字符串近似命名开放未知语法。
        var qualified = constructor.Predicate is Owl + "qualifiedCardinality" or Owl + "minQualifiedCardinality" or Owl + "maxQualifiedCardinality";
        if (qualified && (qualifiers.Length != 1 || !ClassOrDataRange(qualifiers[0].Object)))
            Add("cardinality_invalid", "qualified cardinality需要唯一合法onClass或onDataRange类/数据范围项。", subject, constructor.Predicate);
        if (!qualified && qualifiers.Length != 0)
            Add("restriction_invalid", "普通基数、量词及值限制不能混用qualified限定槽位。", subject, qualifiers[0].Predicate);
        if (constructor.Predicate is Owl + "someValuesFrom" or Owl + "allValuesFrom" && !ClassOrDataRange(constructor.Object))
            Add("restriction_invalid", "some/allValuesFrom目标必须是类或数据范围IRI/已定义表达式，不能是literal。", subject, constructor.Predicate);
        if (constructor.Predicate == Owl + "hasValue" && constructor.Object.Kind == RdfTermKind.Blank)
            Add("restriction_value_unsupported", "hasValue匿名个体完整保留；本版只读值槽位仅确认IRI或typed/language literal。", subject, constructor.Predicate);
        if (constructor.Predicate == Owl + "hasSelf" && (constructor.Object.Kind != RdfTermKind.Literal
            || constructor.Object.Datatype != "http://www.w3.org/2001/XMLSchema#boolean" || constructor.Object.Language is not null
            || constructor.Object.Value.Trim(' ', '\t', '\r', '\n') is not ("true" or "1")))
            Add("restriction_invalid", "hasSelf需要值为true的xsd:boolean，不把其他literal当作自关系表达式。", subject, constructor.Predicate);
    }

    /// <summary>RIOT已校验IRI语法；结构槽位仍不得携带literal元数据。</summary>
    private static bool NamedIri(RdfTerm term) => term.Kind == RdfTermKind.Iri && term.Datatype is null && term.Language is null;

    /// <summary>接受真实命名目标或有本源结构定义的匿名类/数据范围，不从literal猜测类型。</summary>
    private bool ClassOrDataRange(RdfTerm term) => NamedIri(term) || term.Kind == RdfTermKind.Blank && subjects.ContainsKey(term)
        && (Values(term, Rdf + "type").Any(item => item.Kind == RdfTermKind.Iri && item.Value is Owl + "Class" or Owl + "Restriction" or Owl + "DataRange" or "http://www.w3.org/2000/01/rdf-schema#Datatype")
            || subjects[term].Any(item => item.Predicate is Owl + "intersectionOf" or Owl + "unionOf" or Owl + "complementOf" or Owl + "oneOf" or Owl + "datatypeComplementOf" or Owl + "onDatatype"));

    /// <summary>按first/rest真实顺序读取有界列表；分叉、断裂和环均不伪装完整。</summary>
    private RdfTerm[] ReadList(RdfTerm head)
    {
        if (lists.TryGetValue(head, out var cached)) return cached;
        // 每条链局部去重，不把共享尾节点误报为循环。
        var seen = new HashSet<RdfTerm>();
        // 仅收集明确读到的顺序项，损坏后仍由诊断撤回完整性结论。
        var items = new List<RdfTerm>();
        // 游标只来自真实rest目标。
        var current = head;
        while (current.Kind != RdfTermKind.Iri || current.Value != Rdf + "nil")
        {
            token.ThrowIfCancellationRequested();
            if (items.Count >= MaxNodes)
            {
                Add("expression_budget_exceeded", "列表超过512项预算，原文保留且结构无法确定。", head, Rdf + "rest");
                break;
            }
            if (!seen.Add(current))
            {
                Add("expression_cycle", "RDF列表rest存在环；不能把循环展示为有限完整列表。", current, Rdf + "rest");
                break;
            }
            if (current.Kind != RdfTermKind.Blank || !subjects.ContainsKey(current))
            {
                Add("list_invalid", "列表rest目标缺失或不是空白节点/rdf:nil。", current, Rdf + "rest");
                break;
            }
            checkedListNodes.Add(current);
            // 恰好一个first和rest才可准确恢复顺序，不任选第一个分支。
            var first = Values(current, Rdf + "first");
            // 断裂rest与空列表rdf:nil严格区分。
            var rest = Values(current, Rdf + "rest");
            if (first.Length != 1 || rest.Length != 1)
            {
                Add("list_invalid", "列表节点必须恰好包含一个rdf:first和一个rdf:rest。", current, Rdf + "rest");
                break;
            }
            items.Add(first[0]);
            current = rest[0];
        }
        if (projectedListItems + items.Count > MaxNodes)
        {
            Add("expression_budget_exceeded", "列表展开总项数超过512项预算；共享结构仍保留flat引用。", head, Rdf + "first");
            items = items.Take(Math.Max(0, MaxNodes - projectedListItems)).ToList();
        }
        projectedListItems += items.Count;
        lists[head] = items.ToArray();
        return lists[head];
    }

    /// <summary>检查所有匿名表达式分量，忽略rest链长度但保留真实嵌套和共享DAG。</summary>
    private int Visit(RdfTerm subject, int depth, Dictionary<RdfTerm, int> state, Dictionary<RdfTerm, int> depths)
    {
        token.ThrowIfCancellationRequested();
        if (depth > MaxDepth)
        {
            Add("expression_budget_exceeded", "表达式嵌套超过32层预算，原文保留且结构无法确定。", subject, null);
            return MaxDepth + 1;
        }
        if (state.TryGetValue(subject, out var visit))
        {
            if (visit == 1)
            {
                Add("expression_cycle", "匿名表达式存在循环引用，不能递归展开或假定完整OWL表达式。", subject, null);
                return 0;
            }
            return depths.GetValueOrDefault(subject);
        }
        if (state.Count >= MaxNodes)
        {
            Add("expression_budget_exceeded", "结构遍历超过512节点预算，原文保留。", subject, null);
            return 1;
        }
        state[subject] = 1;
        // 只沿匿名表达式引用遍历；命名类子类环不是此视图的匿名结构环。
        var children = subjects[subject].Where(item => item.Predicate != Rdf + "rest" && item.Object.Kind == RdfTermKind.Blank && subjects.ContainsKey(item.Object))
            .SelectMany(item => IsList(item.Object) ? ReadList(item.Object).Where(term => term.Kind == RdfTermKind.Blank && subjects.ContainsKey(term)) : [item.Object]).Distinct().ToArray();
        // memo保存从当前节点出发的最长嵌套，后续不同父路径仍能判定预算。
        var longest = 1;
        foreach (var child in children)
        {
            // 列表存储节点不是表达式层；列表项里的表达式才增加一层。
            var length = Visit(child, depth + 1, state, depths);
            longest = Math.Max(longest, 1 + length);
        }
        if (depth + longest - 1 > MaxDepth) Add("expression_budget_exceeded", "共享表达式路径超过32层嵌套预算。", subject, null);
        depths[subject] = longest;
        state[subject] = 2;
        return longest;
    }

    /// <summary>精确读取一个主体的某谓词全部对象，不任选冲突值。</summary>
    private RdfTerm[] Values(RdfTerm subject, string predicate) => subjects.TryGetValue(subject, out var triples)
        ? triples.Where(item => item.Predicate == predicate).Select(item => item.Object).ToArray() : [];

    /// <summary>列表节点由真实first或rest声明识别，断半链也必须进入诊断。</summary>
    private bool IsList(RdfTerm subject) => subjects.TryGetValue(subject, out var triples) && triples.Any(item => item.Predicate is Rdf + "first" or Rdf + "rest");

    /// <summary>仅以实际标准谓词/类型选择展示类别，不推断OWL事实。</summary>
    private string Kind(RdfTerm subject)
    {
        if (Values(subject, Rdf + "type").Any(term => term.Kind == RdfTermKind.Iri && term.Value == Owl + "Restriction")) return "restriction";
        if (Values(subject, Owl + "intersectionOf").Length > 0) return "intersection";
        if (Values(subject, Owl + "unionOf").Length > 0) return "union";
        if (Values(subject, Owl + "complementOf").Length > 0) return "complement";
        if (IsList(subject)) return "list";
        return subjects[subject].Any(item => item.Predicate.StartsWith(Owl, StringComparison.Ordinal)) ? "axiom" : "term";
    }

    /// <summary>按XML Schema整数词法和值域判断，不转换为有限机器整数或改写原词法。</summary>
    private static bool ValidCardinality(RdfTerm term)
    {
        if (term.Kind != RdfTermKind.Literal || term.Datatype != NonNegativeInteger || term.Language is not null) return false;
        // XML Schema整数的whiteSpace=collapse允许首尾标准XML空白，内部空白仍非法。
        var text = term.Value.Trim(' ', '\t', '\r', '\n');
        if (text.Length == 0) return false;
        // 正负号均属于integer词法；负零仍在nonNegativeInteger值域内。
        var negative = text[0] == '-';
        // 去掉至多一个合法符号，不放宽其他字符。
        var offset = text[0] is '+' or '-' ? 1 : 0;
        return offset < text.Length && text.AsSpan(offset).IndexOfAnyExceptInRange('0', '9') < 0
            && (!negative || text.AsSpan(offset).IndexOfAnyExcept('0') < 0);
    }

    /// <summary>稳定排序包含全部RDF项身份，不能把相同词面但语言/类型不同的项合并。</summary>
    private static string TermKey(RdfTerm term) => System.Text.Json.JsonSerializer.Serialize(term);

    /// <summary>有界记录准确结构诊断；无法确定始终失败关闭，不依赖诊断是否被去重。</summary>
    private void Add(string code, string message, RdfTerm? focus, string? predicate, bool invalid = true)
    {
        indeterminate |= invalid;
        if (diagnosticKeys.Add((code, focus, predicate)) && diagnostics.Count < 128)
            diagnostics.Add(new OwlExpressionDiagnostic { Code = code, Message = message, FocusNode = focus, PredicateIri = predicate, Line = null, Column = null });
    }
}
