using System.Text.Json;
using System.Text.Json.Serialization;

namespace OntologyPlatform.Contracts;

/// <summary>G4判别数据只承载已授权语义值，来源与旧G2图模型独立。</summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "kind")]
[JsonDerivedType(typeof(G4EntityDatum), "entity")]
[JsonDerivedType(typeof(G4RelationshipDatum), "relationship")]
[JsonDerivedType(typeof(G4ObservationDatum), "observation")]
[JsonDerivedType(typeof(G4OntologyDatum), "ontology")]
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public abstract record G4QueryDatum
{
    /// <summary>实体标识；仅未开放的本体分支为空。</summary>
    public required string? EntityIri { get; init; }

    /// <summary>本响应中必须可解引用的来源标识。</summary>
    public required string[] EvidenceIds { get; init; }
}

/// <summary>固定身份、类型与精确属性的实体结果。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4EntityDatum : G4QueryDatum
{
    /// <summary>组织厂区及来源命名空间组成的完整身份。</summary>
    public required G4QueryIdentity Identity { get; init; }

    /// <summary>已发布正式类型IRI集合。</summary>
    public required string[] TypeIris { get; init; }

    /// <summary>来源显示名；未知不补造。</summary>
    public required string? Label { get; init; }

    /// <summary>精确属性集合，不接受任意字典。</summary>
    public required G4QueryProperty[] Properties { get; init; }

    /// <summary>来源有效半开区间，未知为空。</summary>
    public required G4QueryInterval? ValidTime { get; init; }
}

/// <summary>已发布关系的方向、两端与基数，不伪造越权端点。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4RelationshipDatum : G4QueryDatum
{
    /// <summary>正式对象属性IRI。</summary>
    public required string RelationshipIri { get; init; }

    /// <summary>关系源端完整身份。</summary>
    public required G4QueryEndpoint Source { get; init; }

    /// <summary>关系目标端完整身份。</summary>
    public required G4QueryEndpoint Target { get; init; }

    /// <summary>发布关系声明的四种基数之一。</summary>
    public required string Cardinality { get; init; }

    /// <summary>关系有效半开区间。</summary>
    public required G4QueryInterval? ValidTime { get; init; }
}

/// <summary>保留精确数值、单位、事件时间与观察时间的观测。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4ObservationDatum : G4QueryDatum
{
    /// <summary>观测主体的完整身份。</summary>
    public required G4QueryIdentity Identity { get; init; }

    /// <summary>正式属性IRI。</summary>
    public required string PropertyIri { get; init; }

    /// <summary>有显式类型的精确源值。</summary>
    public required G4QueryValue Value { get; init; }

    /// <summary>经发布映射或源字段证明的单位。</summary>
    public required G4QueryUnit? Unit { get; init; }

    /// <summary>源事件时间，未知不以观察时间替代。</summary>
    public required G4QueryTime? EventTime { get; init; }

    /// <summary>真实读取UTC观察时间。</summary>
    public required string ObservedAtUtc { get; init; }

    /// <summary>业务有效区间。</summary>
    public required G4QueryInterval? ValidTime { get; init; }
}

/// <summary>仅冻结形状的本体分支，当前G4能力不开放。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4OntologyDatum : G4QueryDatum
{
    /// <summary>不可变正式本体发布。</summary>
    public required string OntologyReleaseId { get; init; }

    /// <summary>正式类说明集合。</summary>
    public required G4QueryClass[] Classes { get; init; }

    /// <summary>正式属性说明集合。</summary>
    public required G4QueryOntologyProperty[] Properties { get; init; }
}

/// <summary>外部号不构成全局主键，身份保留来源和有效范围。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QueryIdentity
{
    /// <summary>所属组织标识。</summary>
    public required string OrganizationId { get; init; }

    /// <summary>所属厂区标识。</summary>
    public required string SiteId { get; init; }

    /// <summary>已登记来源命名空间。</summary>
    public required string SourceNamespace { get; init; }

    /// <summary>源外部号原值。</summary>
    public required string ExternalId { get; init; }

    /// <summary>身份有效区间。</summary>
    public required G4QueryInterval? EffectiveTime { get; init; }
}

/// <summary>关系端点必须与当前已授权正式实体一致。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QueryEndpoint
{
    /// <summary>端点实体标识。</summary>
    public required string EntityIri { get; init; }

    /// <summary>端点的完整来源身份。</summary>
    public required G4QueryIdentity Identity { get; init; }

    /// <summary>端点正式类型集合。</summary>
    public required string[] TypeIris { get; init; }
}

/// <summary>属性不丢失空值、单位及事件时间。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QueryProperty
{
    /// <summary>正式属性IRI。</summary>
    public required string PropertyIri { get; init; }

    /// <summary>精确标量值。</summary>
    public required G4QueryValue Value { get; init; }

    /// <summary>有依据的单位或未知。</summary>
    public required G4QueryUnit? Unit { get; init; }

    /// <summary>事件发生时间或未知。</summary>
    public required G4QueryTime? EventTime { get; init; }

    /// <summary>该属性的真实证据引用。</summary>
    public required string[] EvidenceIds { get; init; }
}

/// <summary>单位来源必须可核到固定映射或登记字段。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QueryUnit
{
    /// <summary>已发布单位规格标识。</summary>
    public required string UnitSpecId { get; init; }

    /// <summary>正式单位IRI。</summary>
    public required string UnitIri { get; init; }

    /// <summary>MAPPING_RELEASE或SOURCE_FIELD。</summary>
    public required string Source { get; init; }

    /// <summary>源字段来源时必填，映射来源时为空。</summary>
    public required string? SourceFieldRef { get; init; }

    /// <summary>单位来源证据。</summary>
    public required string[] EvidenceIds { get; init; }
}

/// <summary>保留时间类型和精度的半开业务区间。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QueryInterval
{
    /// <summary>包含的起点。</summary>
    public required G4QueryTime From { get; init; }

    /// <summary>排除的终点，未知结束为空。</summary>
    public required G4QueryTime? To { get; init; }
}

/// <summary>UTC、本地无时区时间及日期严格区分。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QueryTime
{
    /// <summary>UTC、LOCAL或DATE，不自动补猜时区。</summary>
    public required string Kind { get; init; }

    /// <summary>保持声明精度的时间词法。</summary>
    public required string Lexical { get; init; }

    /// <summary>实际小数秒位数，日期必须为零。</summary>
    public required int FractionalDigits { get; init; }
}

/// <summary>正式本体类的封闭说明。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QueryClass
{
    /// <summary>正式类IRI。</summary>
    public required string Iri { get; init; }

    /// <summary>显示名或未知。</summary>
    public required string? Label { get; init; }

    /// <summary>类定义证据。</summary>
    public required string[] EvidenceIds { get; init; }
}

/// <summary>正式属性保留种类及定义域和值域。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QueryOntologyProperty
{
    /// <summary>正式属性IRI。</summary>
    public required string Iri { get; init; }

    /// <summary>OBJECT或DATATYPE。</summary>
    public required string Kind { get; init; }

    /// <summary>定义域集合。</summary>
    public required string[] DomainIris { get; init; }

    /// <summary>值域集合。</summary>
    public required string[] RangeIris { get; init; }

    /// <summary>属性定义证据。</summary>
    public required string[] EvidenceIds { get; init; }
}

/// <summary>精确标量以类型和词法表示，不经浮点中转。</summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type")]
[JsonDerivedType(typeof(G4StringValue), "string")]
[JsonDerivedType(typeof(G4BooleanValue), "boolean")]
[JsonDerivedType(typeof(G4Int64Value), "int64")]
[JsonDerivedType(typeof(G4DecimalValue), "decimal")]
[JsonDerivedType(typeof(G4DateValue), "date")]
[JsonDerivedType(typeof(G4UtcValue), "timestampUtc")]
[JsonDerivedType(typeof(G4LocalValue), "timestampLocal")]
[JsonDerivedType(typeof(G4NullValue), "null")]
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public abstract record G4QueryValue
{
    /// <summary>非null分支为精确字符串，null分支仅为JSON null。</summary>
    public required string? Lexical { get; init; }
}

/// <summary>源字符串，空串与null严格区分。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4StringValue : G4QueryValue
{
}

/// <summary>布尔词法仅true或false。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4BooleanValue : G4QueryValue
{
}

/// <summary>有符号64位整数的精确十进制字符串。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4Int64Value : G4QueryValue
{
}

/// <summary>固定precision与scale的精确十进制值。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4DecimalValue : G4QueryValue
{
    /// <summary>批准目录声明的十进制精度。</summary>
    public required int Precision { get; init; }

    /// <summary>批准目录声明的小数位数。</summary>
    public required int Scale { get; init; }
}

/// <summary>不附加午夜的源日期。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4DateValue : G4QueryValue
{
}

/// <summary>精确UTC时间词法。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4UtcValue : G4QueryValue
{
}

/// <summary>不附加时区的本地时间词法。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4LocalValue : G4QueryValue
{
}

/// <summary>显式源空值，不代表缺字段。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4NullValue : G4QueryValue
{
    /// <summary>null原字段的非null类型声明。</summary>
    public required string DeclaredType { get; init; }
}

/// <summary>G4查询独立序列化策略，严格拒绝未知字段并保留所有null。</summary>
public static class G4QueryJson
{
    /// <summary>公开合同与持久恢复共用的只读选项，不修改G2或M3。</summary>
    public static JsonSerializerOptions Options { get; } = Create();

    /// <summary>元数据可以位于任意位置，便于按键排序的规范字节严格回读。</summary>
    /// <returns>不接受宽松数值转换的只读选项。</returns>
    private static JsonSerializerOptions Create()
    {
        // 使用Web命名，但关闭大小写容错和未知字段默认忽略。
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            PropertyNameCaseInsensitive = false,
            NumberHandling = JsonNumberHandling.Strict,
            UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
            AllowOutOfOrderMetadataProperties = true,
            MaxDepth = 16
        };
        options.MakeReadOnly(populateMissingResolver: true);
        return options;
    }
}

/// <summary>登记能力的受控查询请求，不接收SQL或任意URL。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4SemanticQuery
{
    /// <summary>正式本体资产标识。</summary>
    public required string AssetId { get; init; }

    /// <summary>固定正式本体发布。</summary>
    public required string OntologyReleaseId { get; init; }

    /// <summary>固定映射发布集合，首期一个源。</summary>
    public required string[] MappingReleaseIds { get; init; }

    /// <summary>登记查询能力名。</summary>
    public required string CapabilityId { get; init; }

    /// <summary>输入输出与执行器共同散列。</summary>
    public required string CapabilityVersion { get; init; }

    /// <summary>只允许发布关系路径。</summary>
    public required string[] RelationshipIris { get; init; }

    /// <summary>最大遍历深度，一至五。</summary>
    public required int Depth { get; init; }

    /// <summary>最大返回项数，二至一百。</summary>
    public required int MaxRows { get; init; }

    /// <summary>整体截止预算，一百至五千毫秒。</summary>
    public required int TimeoutMs { get; init; }

    /// <summary>仅允许受控身份和时间窗过滤。</summary>
    public required G4QueryFilters Filters { get; init; }
}

/// <summary>可选查询筛选只缩小当前授权范围。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QueryFilters
{
    /// <summary>候选所属厂区；选择IRI时必填。</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? SiteId { get; init; }

    /// <summary>原始外部号，不作为全局身份。</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? EntityExternalId { get; init; }

    /// <summary>半开时间窗UTC起点。</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ValidFrom { get; init; }

    /// <summary>半开时间窗UTC终点。</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ValidTo { get; init; }

    /// <summary>从原消歧查询选择的实体标识。</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? EntityIri { get; init; }
}

/// <summary>真实源查询的独立十二字段结果，不投影成旧G2伪图。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QueryResultV1
{
    /// <summary>固定g4.query-result.v1。</summary>
    public required string SchemaVersion { get; init; }

    /// <summary>统一六态之一，不包含执行进度。</summary>
    public required string Status { get; init; }

    /// <summary>当前获准的判别数据。</summary>
    public required G4QueryDatum[] Data { get; init; }

    /// <summary>已鉴权的歧义候选。</summary>
    public required G4QueryCandidate[] Candidates { get; init; }

    /// <summary>真实源证据引用集合。</summary>
    public required G4SourceEvidenceRef[] Evidence { get; init; }

    /// <summary>本次查询固定且获准可见的版本。</summary>
    public required G4QuerySnapshot Snapshot { get; init; }

    /// <summary>各读取分支真实状态，不声称跨源原子快照。</summary>
    public required G4QuerySubSource[] SubSources { get; init; }

    /// <summary>已知业务UTC有效区间或未知。</summary>
    public required G4QueryUtcInterval? ValidTime { get; init; }

    /// <summary>实际读取观察时间。</summary>
    public required string ObservedAtUtc { get; init; }

    /// <summary>服务端本次跟踪标识。</summary>
    public required string TraceId { get; init; }

    /// <summary>实际预算截断标记。</summary>
    public required bool Limited { get; init; }

    /// <summary>固定脱敏诊断，不含源异常。</summary>
    public required G4QueryDiagnostic[] Diagnostics { get; init; }
}

/// <summary>仅包含当前可见实体的选择候选。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QueryCandidate
{
    /// <summary>选择标识，不是可访问URL。</summary>
    public required string EntityIri { get; init; }

    /// <summary>正式类型集合。</summary>
    public required string[] EntityTypeIris { get; init; }

    /// <summary>源外部号。</summary>
    public required string ExternalId { get; init; }

    /// <summary>组织范围。</summary>
    public required string OrganizationId { get; init; }

    /// <summary>厂区范围。</summary>
    public required string SiteId { get; init; }

    /// <summary>当前可见且有依据的显示名。</summary>
    public required string Label { get; init; }

    /// <summary>候选身份的真实来源。</summary>
    public required string[] EvidenceIds { get; init; }
}

/// <summary>固定本体、映射、校验目录及能力版本。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QuerySnapshot
{
    /// <summary>固定本体发布。</summary>
    public required string OntologyReleaseId { get; init; }

    /// <summary>不可变映射发布集合。</summary>
    public required string[] MappingReleaseIds { get; init; }

    /// <summary>本次校验目录，不覆盖原发布目录。</summary>
    public required string[] SourceCatalogSnapshotIds { get; init; }

    /// <summary>实际执行登记能力。</summary>
    public required string CapabilityId { get; init; }

    /// <summary>固定执行语义版本。</summary>
    public required string CapabilityVersion { get; init; }
}

/// <summary>业务断言可回链的源证据，不包含伪造图身份。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4SourceEvidenceRef
{
    /// <summary>本次证据唯一标识。</summary>
    public required string EvidenceId { get; init; }

    /// <summary>获准可见的源连接。</summary>
    public required string ConnectionId { get; init; }

    /// <summary>实际使用的不可变映射。</summary>
    public required string MappingReleaseId { get; init; }

    /// <summary>原发布目录身份。</summary>
    public required string SourceCatalogSnapshotId { get; init; }

    /// <summary>已登记源数据集引用。</summary>
    public required string SourceDatasetRef { get; init; }

    /// <summary>实际读取分支回执。</summary>
    public required string SourceReadReceiptId { get; init; }

    /// <summary>此证据需要的完整范围。</summary>
    public required ResourceScope Scope { get; init; }

    /// <summary>RECORD、ROW_KEY、DATASET、TIME_WINDOW或UNKNOWN。</summary>
    public required string Precision { get; init; }

    /// <summary>真实可定位记录引用；未知必须为空。</summary>
    public required string? SourceRecordRef { get; init; }

    /// <summary>已知UTC业务区间。</summary>
    public required G4QueryUtcInterval? ValidTime { get; init; }

    /// <summary>实际读取观察时刻。</summary>
    public required string ObservedAtUtc { get; init; }
}

/// <summary>每个受控读取分支独立记录状态与水位。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QuerySubSource
{
    /// <summary>当前可见连接。</summary>
    public required string ConnectionId { get; init; }

    /// <summary>SUCCESS、EMPTY、TIMEOUT、FORBIDDEN、UNAVAILABLE或INDETERMINATE。</summary>
    public required string Status { get; init; }

    /// <summary>本次分支完成观察时刻。</summary>
    public required string ObservedAtUtc { get; init; }

    /// <summary>实际测得水位种类。</summary>
    public required string WatermarkKind { get; init; }

    /// <summary>实际回执；未读取时可空。</summary>
    public required string? SourceReadReceiptId { get; init; }

    /// <summary>分支预算是否截断。</summary>
    public required bool Limited { get; init; }
}

/// <summary>旧G4顶层有效区间只表达已知UTC时刻。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QueryUtcInterval
{
    /// <summary>半开区间起点。</summary>
    public required string FromUtc { get; init; }

    /// <summary>排除的终点，未知结束为空。</summary>
    public required string? ToUtc { get; init; }
}

/// <summary>客户端只获得固定脱敏诊断。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QueryDiagnostic
{
    /// <summary>固定机器码。</summary>
    public required string Code { get; init; }

    /// <summary>info、warning或error。</summary>
    public required string Severity { get; init; }

    /// <summary>固定中文消息。</summary>
    public required string Message { get; init; }

    /// <summary>有权可见焦点或空。</summary>
    public required string? FocusNode { get; init; }

    /// <summary>有权可见路径或空。</summary>
    public required string? Path { get; init; }
}

/// <summary>查询执行状态与业务六态分离的恢复视图。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record G4QueryView
{
    /// <summary>服务器生成查询身份。</summary>
    public required string QueryId { get; init; }

    /// <summary>RUNNING、COMPLETED、CANCELLED或FAILED。</summary>
    public required string ExecutionStatus { get; init; }

    /// <summary>真实创建时间。</summary>
    public required string CreatedAtUtc { get; init; }

    /// <summary>终结时间，执行中为空。</summary>
    public required string? CompletedAtUtc { get; init; }

    /// <summary>不可延长的结果到期时间。</summary>
    public required string ExpiresAtUtc { get; init; }

    /// <summary>获准结果读取者可见的规范字节SHA256。</summary>
    public required string? ResultHash { get; init; }

    /// <summary>失败固定码或空。</summary>
    public required string? ErrorCode { get; init; }
}
