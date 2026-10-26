using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>对一次正式发布读取建立有界索引；只解释标准声明和明确元数据词汇。</summary>
internal sealed class PublishedGraph
{
    /// <summary>标准RDF词汇命名空间。</summary>
    internal const string Rdf = "http://www.w3.org/1999/02/22-rdf-syntax-ns#";

    /// <summary>标准OWL词汇命名空间。</summary>
    private const string Owl = "http://www.w3.org/2002/07/owl#";

    /// <summary>标准RDFS显示标签。</summary>
    private const string Label = "http://www.w3.org/2000/01/rdf-schema#label";

    /// <summary>冻结的平台元数据词汇。</summary>
    internal const string Vocabulary = "urn:ontology-platform:vocabulary:";

    /// <summary>固定正式清单，源对象及模型版本只能取自此处。</summary>
    private readonly ReleaseManifest manifest;

    /// <summary>真实正式事实按主语分组，避免重复遍历全图。</summary>
    private readonly ILookup<string, RdfTriple> subjects;

    /// <summary>标准本体描述，不含行业硬编码。</summary>
    internal OntologyDescription Description { get; }

    /// <summary>声明的对象属性白名单。</summary>
    internal HashSet<string> Relationships { get; }

    /// <summary>正式图中的可识别业务实体，尚需按当前主体过滤。</summary>
    internal Dictionary<string, SemanticEntity> Entities { get; }

    /// <summary>真实业务断言与PROV-O来源形成的证据；没有来源的断言不造证据。</summary>
    internal Dictionary<string, EvidenceRef> Evidence { get; } = new(StringComparer.Ordinal);

    /// <summary>真实正式三元组，仅由受控Runtime传入。</summary>
    internal RdfTriple[] Triples { get; }

    /// <summary>读取正式OWL声明，再解析实体与标准reification/PROV-O。</summary>
    internal PublishedGraph(ReleaseManifest manifest, PublishedRdfData data, CancellationToken token)
    {
        this.manifest = manifest;
        Triples = data.DataTriples;
        subjects = Triples.ToLookup(value => value.Subject.Value, StringComparer.Ordinal);
        Description = new OntologyDescription
        {
            ClassIris = Declarations(data.OntologyTriples, Owl + "Class"),
            ObjectPropertyIris = Declarations(data.OntologyTriples, Owl + "ObjectProperty"),
            DatatypePropertyIris = Declarations(data.OntologyTriples, Owl + "DatatypeProperty"),
            Labels = data.OntologyTriples.Where(value => value.Predicate == Label).Select(value => new SemanticPropertyValue { PredicateIri = value.Subject.Value, Value = value.Object }).ToArray(),
            SupportedAxioms = ["rdf:type", "rdfs:subClassOf", "rdfs:domain", "rdfs:range", "owl:Class", "owl:ObjectProperty", "owl:DatatypeProperty"]
        };
        Relationships = Description.ObjectPropertyIris.ToHashSet(StringComparer.Ordinal);
        Entities = new Dictionary<string, SemanticEntity>(StringComparer.Ordinal);
        foreach (var group in subjects)
        {
            token.ThrowIfCancellationRequested();
            // 只有正式类声明的IRI实体才能进入结果；来源断言和未知类不当业务实体。
            var types = group.Where(value => value.Predicate == Rdf + "type" && value.Object.Kind == RdfTermKind.Iri && Description.ClassIris.Contains(value.Object.Value, StringComparer.Ordinal)).Select(value => value.Object.Value).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray();
            if (types.Length == 0 || group.First().Subject.Kind != RdfTermKind.Iri) continue;
            // 多值或缺失范围元数据不能靠first选择放行。
            var organization = Literal(group.Key, Vocabulary + "organizationId");
            // 每个实体具有唯一厂区身份，跨厂同号不会合并。
            var site = Literal(group.Key, Vocabulary + "siteId");
            // 外部号只作过滤条件，不作为字典主键。
            var external = Literal(group.Key, Vocabulary + "externalId");
            if (organization is null || site is null || external is null || Literal(group.Key, Vocabulary + "synthetic") is not ("true" or "1")) continue;
            Entities.Add(group.Key, new SemanticEntity { Iri = group.Key, TypeIris = types, OrganizationId = organization, SiteId = site, ExternalId = external, Label = Literal(group.Key, Label) ?? external, Synthetic = true });
        }
        foreach (var assertion in Triples.Where(value => value.Predicate == Rdf + "type" && value.Object.Kind == RdfTermKind.Iri && value.Object.Value == Rdf + "Statement"))
        {
            token.ThrowIfCancellationRequested();
            // 每个声明都核对真实被断言三元组及源信息。
            var evidence = ParseEvidence(assertion.Subject.Value);
            if (evidence is not null) Evidence.TryAdd(evidence.EvidenceId, evidence);
        }
    }

    /// <summary>正式声明只接受IRI主体和IRI类型，不按标签猜测类型。</summary>
    private static string[] Declarations(RdfTriple[] triples, string type) => triples.Where(value => value.Subject.Kind == RdfTermKind.Iri && value.Predicate == Rdf + "type" && value.Object.Kind == RdfTermKind.Iri && value.Object.Value == type).Select(value => value.Subject.Value).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray();

    /// <summary>单值元数据才有确定语义，缺失或冲突都返回无值。</summary>
    private RdfTerm? Term(string subject, string predicate)
    {
        // RDF集合可包含重复传输项，但不同RDF项不可任选一个。
        var values = subjects[subject].Where(value => value.Predicate == predicate).Select(value => value.Object).Distinct().Take(2).ToArray();
        return values.Length == 1 ? values[0] : null;
    }

    /// <summary>仅以真实字面量解释平台元数据，IRI不是文本值。</summary>
    private string? Literal(string subject, string predicate) => Term(subject, predicate) is { Kind: RdfTermKind.Literal } term ? term.Value : null;

    /// <summary>解析完整reification、PROV来源和时间；模型以正式manifest绑定而非合成模板号。</summary>
    private EvidenceRef? ParseEvidence(string assertion)
    {
        // 标准reification的三个项必须唯一，并与实际断言完全一致。
        var subject = Term(assertion, Rdf + "subject");
        // 谓词必须是标准IRI，不接受字面量模拟关系。
        var predicate = Term(assertion, Rdf + "predicate");
        // 完整客体保留datatype与language，不能简化成字符串Join。
        var value = Term(assertion, Rdf + "object");
        if (subject is not { Kind: RdfTermKind.Iri } || predicate is not { Kind: RdfTermKind.Iri } || value is null || !Entities.TryGetValue(subject.Value, out var entity) || !subjects[subject.Value].Any(row => row.Predicate == predicate.Value && row.Object == value)) return null;
        // 范围必须落入清单；关系目标也必须具备真实合法范围。
        var sites = new HashSet<string>(StringComparer.Ordinal) { entity.SiteId };
        if (Relationships.Contains(predicate.Value))
        {
            if (value.Kind != RdfTermKind.Iri || !Entities.TryGetValue(value.Value, out var target) || target.OrganizationId != entity.OrganizationId) return null;
            sites.Add(target.SiteId);
        }
        if (entity.OrganizationId != manifest.Scope.OrganizationId || !sites.All(site => manifest.Scope.SiteIds.Contains(site, StringComparer.Ordinal))) return null;
        // PROV-O来源及受控来源标识缺一不可。
        var derived = Term(assertion, "http://www.w3.org/ns/prov#wasDerivedFrom");
        // 源记录由真实assertion读取。
        var source = Literal(assertion, Vocabulary + "sourceId");
        // 源内记录标识不得由用户计划提供。
        var record = Literal(assertion, Vocabulary + "sourceRecordId");
        // 来源模板版本只用于确认来源完整，不能冒充本体发布。
        var model = Literal(assertion, Vocabulary + "modelVersion");
        if (derived is not { Kind: RdfTermKind.Iri } || string.IsNullOrWhiteSpace(source) || string.IsNullOrWhiteSpace(record) || string.IsNullOrWhiteSpace(model) || Literal(assertion, Vocabulary + "mappingStatus") != "absent" || Literal(assertion, Vocabulary + "synthetic") is not ("true" or "1")) return null;
        if (!Timestamp(assertion, "validFromUtc", out var validFrom) || !Timestamp(assertion, "observedAtUtc", out var observed)) return null;
        // 可选业务终点若出现，格式或顺序错误不能忽略。
        DateTimeOffset? validTo = null;
        if (Term(assertion, Vocabulary + "validToUtc") is not null)
        {
            if (!Timestamp(assertion, "validToUtc", out var end) || end < validFrom) return null;
            validTo = end;
        }
        // 数据源引用由正式manifest散列唯一选择，不能构造未经发布的对象键。
        var artifacts = manifest.ArtifactObjects.Where(item => item.Hash == manifest.Snapshot.DataHash).ToArray();
        if (artifacts.Length != 1) return null;
        return new EvidenceRef { EvidenceId = manifest.ReleaseId + "." + Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(assertion))), ReleaseId = manifest.ReleaseId, Scope = new ResourceScope { OrganizationId = entity.OrganizationId, SiteIds = sites.Order(StringComparer.Ordinal).ToArray() }, GraphIri = manifest.DataGraphIri, SubjectIri = subject.Value, PredicateIri = predicate.Value, ObjectTerm = value, SourceId = source, SourceRecordId = record, SourceObjectKey = artifacts[0].ObjectKey, ContentHash = artifacts[0].Hash, ValidFromUtc = validFrom, ValidToUtc = validTo, ObservedAtUtc = observed, ModelVersion = manifest.ReleaseId, MappingVersion = null, Synthetic = true };
    }

    /// <summary>标准xsd:dateTime必须包含UTC偏移，避免依赖机器本地时区。</summary>
    private bool Timestamp(string subject, string name, out DateTimeOffset value)
    {
        value = default;
        // 精确datatype和显式时区保证有效时间/观察时间含义明确。
        var term = Term(subject, Vocabulary + name);
        return term is { Kind: RdfTermKind.Literal, Datatype: "http://www.w3.org/2001/XMLSchema#dateTime" } && (term.Value.EndsWith('Z') || term.Value.Length >= 6 && term.Value[^6] is '+' or '-') && DateTimeOffset.TryParse(term.Value, CultureInfo.InvariantCulture, DateTimeStyles.None, out value);
    }

    /// <summary>当前主体、清单和可选请求厂区必须同时覆盖真实实体。</summary>
    internal bool Visible(ActorContext actor, SemanticEntity entity, string? site) => entity.OrganizationId == actor.OrganizationId && entity.OrganizationId == manifest.Scope.OrganizationId && actor.SiteIds.Contains(entity.SiteId, StringComparer.Ordinal) && manifest.Scope.SiteIds.Contains(entity.SiteId, StringComparer.Ordinal) && (site is null || site == entity.SiteId);

    /// <summary>按完整标准断言找到本请求获准的证据。</summary>
    internal EvidenceRef[] For(ActorContext actor, RdfTriple triple) => Evidence.Values.Where(value => value.SubjectIri == triple.Subject.Value && value.PredicateIri == triple.Predicate && value.ObjectTerm == triple.Object && QueryRules.Covers(actor, value.Scope)).OrderBy(value => value.EvidenceId, StringComparer.Ordinal).ToArray();

    /// <summary>只公开正式数据属性、类型和标签；对象关系只能通过两端授权遍历返回。</summary>
    internal SemanticEntity DescribeEntity(ActorContext actor, SemanticEntity entity) => entity with { Properties = subjects[entity.Iri].Where(row => row.Predicate == Rdf + "type" && entity.TypeIris.Contains(row.Object.Value, StringComparer.Ordinal) || row.Predicate == Label || Description.DatatypePropertyIris.Contains(row.Predicate, StringComparer.Ordinal)).Select(row => new SemanticPropertyValue { PredicateIri = row.Predicate, Value = row.Object, EvidenceIds = For(actor, row).Select(value => value.EvidenceId).ToArray() }).ToArray() };
}
