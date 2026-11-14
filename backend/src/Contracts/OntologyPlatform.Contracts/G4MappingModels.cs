using System.Text.Json;
using System.Globalization;
using System.Text.Json.Serialization;

namespace OntologyPlatform.Contracts;

/// <summary>固定目录中精确的数据集引用。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingDatasetRef
{
    /// <summary>不可变目录快照标识。</summary>
    public required string SnapshotId { get; init; }

    /// <summary>保留大小写的源Schema。</summary>
    public required string Schema { get; init; }

    /// <summary>保留大小写的表名。</summary>
    public required string Name { get; init; }

    /// <summary>首切片仅支持TABLE。</summary>
    public required string Kind { get; init; }
}

/// <summary>固定数据集内的字段引用，不接受SQL片段。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingFieldRef
{
    /// <summary>字段所属固定数据集。</summary>
    public required MappingDatasetRef DatasetRef { get; init; }

    /// <summary>目录记录的字段序号。</summary>
    public required int Ordinal { get; init; }

    /// <summary>目录中的精确字段名。</summary>
    public required string Name { get; init; }
}

/// <summary>源行组织厂区字段，不能由调用者scope替代。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingScopeFields
{
    /// <summary>组织字段引用。</summary>
    public required MappingFieldRef Organization { get; init; }

    /// <summary>厂区字段引用。</summary>
    public required MappingFieldRef Site { get; init; }
}

/// <summary>明确业务时区，不使用服务器本地时区猜测。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingTimezonePolicy
{
    /// <summary>UTC或REGISTERED_ZONE。</summary>
    public required string Kind { get; init; }

    /// <summary>UTC时为null，否则为已登记时区。</summary>
    public required string? ZoneId { get; init; }
}

/// <summary>绑定现存G3类与源数据集。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingEntityBinding
{
    /// <summary>绑定唯一标识。</summary>
    public required string Id { get; init; }

    /// <summary>固定G3发布的类IRI。</summary>
    public required string EntityClassIri { get; init; }

    /// <summary>固定源数据集。</summary>
    public required MappingDatasetRef DatasetRef { get; init; }

    /// <summary>身份规则引用。</summary>
    public required string IdentitySpecId { get; init; }

    /// <summary>时间规则引用。</summary>
    public required string TemporalSpecId { get; init; }

    /// <summary>真实组织厂区字段。</summary>
    public required MappingScopeFields ScopeFields { get; init; }
}

/// <summary>绑定现存属性及可证明的单位和转换。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingPropertyBinding
{
    /// <summary>属性绑定标识。</summary>
    public required string Id { get; init; }

    /// <summary>实体绑定引用。</summary>
    public required string EntityBindingId { get; init; }

    /// <summary>固定G3属性IRI。</summary>
    public required string PropertyIri { get; init; }

    /// <summary>固定源字段。</summary>
    public required MappingFieldRef FieldRef { get; init; }

    /// <summary>注册纯转换引用，无转换为null。</summary>
    public required string? ConversionId { get; init; }

    /// <summary>物理量必填的单位证据引用。</summary>
    public required string? UnitSpecId { get; init; }

    /// <summary>KEEP_NULL或REJECT_NULL。</summary>
    public required string NullPolicy { get; init; }
}

/// <summary>同源关系的有序连接键对。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingJoinFieldPair
{
    /// <summary>起点字段。</summary>
    public required MappingFieldRef From { get; init; }

    /// <summary>终点字段。</summary>
    public required MappingFieldRef To { get; init; }
}

/// <summary>同源已登记键的有界关系绑定。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingRelationBinding
{
    /// <summary>关系标识。</summary>
    public required string Id { get; init; }

    /// <summary>起点实体。</summary>
    public required string FromBindingId { get; init; }

    /// <summary>终点实体。</summary>
    public required string ToBindingId { get; init; }

    /// <summary>固定G3关系IRI。</summary>
    public required string PredicateIri { get; init; }

    /// <summary>有序连接键，不可重排。</summary>
    public required MappingJoinFieldPair[] JoinFieldPairs { get; init; }

    /// <summary>ONE_TO_MANY或MANY_TO_MANY。</summary>
    public required string Cardinality { get; init; }

    /// <summary>半开区间重叠规则。</summary>
    public required string TemporalJoinPolicy { get; init; }
}

/// <summary>组织厂区命名空间与时间限定的业务身份。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingIdentitySpec
{
    /// <summary>身份规则标识。</summary>
    public required string Id { get; init; }

    /// <summary>组织字段。</summary>
    public required MappingFieldRef OrganizationFieldRef { get; init; }

    /// <summary>厂区字段。</summary>
    public required MappingFieldRef SiteFieldRef { get; init; }

    /// <summary>不可省略的来源命名空间。</summary>
    public required string SourceNamespace { get; init; }

    /// <summary>有序复合业务键。</summary>
    public required MappingFieldRef[] ExternalIdFieldRefs { get; init; }

    /// <summary>有效起点，未知为null。</summary>
    public required MappingFieldRef? ValidFromFieldRef { get; init; }

    /// <summary>有效终点，未知不等于永久有效。</summary>
    public required MappingFieldRef? ValidToFieldRef { get; init; }
}

/// <summary>业务时间与观察时间分别绑定。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingTemporalSpec
{
    /// <summary>时间规则标识。</summary>
    public required string Id { get; init; }

    /// <summary>业务事件时间。</summary>
    public required MappingFieldRef? EventTimeFieldRef { get; init; }

    /// <summary>源观察时间。</summary>
    public required MappingFieldRef? ObservedAtFieldRef { get; init; }

    /// <summary>明确时区策略。</summary>
    public required MappingTimezonePolicy TimezonePolicy { get; init; }

    /// <summary>声明的源时间精度。</summary>
    public required string Precision { get; init; }

    /// <summary>半开起点。</summary>
    public required MappingFieldRef? ValidFromFieldRef { get; init; }

    /// <summary>半开终点。</summary>
    public required MappingFieldRef? ValidToFieldRef { get; init; }
}

/// <summary>只有注册纯转换及其封闭参数可执行。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingConversion
{
    /// <summary>转换实例标识。</summary>
    public required string Id { get; init; }

    /// <summary>固定注册转换名。</summary>
    public required string RegisteredId { get; init; }

    /// <summary>转换规则版本。</summary>
    public required string Version { get; init; }

    /// <summary>按注册转换校验的封闭参数。</summary>
    public required JsonElement Parameters { get; init; }
}

/// <summary>从实际源列证明单位，不以模型推测代替。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingUnitSpec
{
    /// <summary>单位规则标识。</summary>
    public required string Id { get; init; }

    /// <summary>已发布源单位IRI。</summary>
    public required string SourceUnitIri { get; init; }

    /// <summary>已发布目标单位IRI。</summary>
    public required string TargetUnitIri { get; init; }

    /// <summary>每行必须匹配的单位证据列。</summary>
    public required MappingFieldRef SourceUnitFieldRef { get; init; }

    /// <summary>精确单位代码。</summary>
    public required string SourceUnitCode { get; init; }

    /// <summary>固定单位登记版本。</summary>
    public required string UnitRegistryVersion { get; init; }

    /// <summary>首切片仅SOURCE_FIELD。</summary>
    public required string EvidenceKind { get; init; }
}

/// <summary>映射语义内容，不是正式本体事实模型。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingDefinition
{
    /// <summary>按id规范化的实体集合。</summary>
    public required MappingEntityBinding[] Entities { get; init; }

    /// <summary>属性集合。</summary>
    public required MappingPropertyBinding[] Properties { get; init; }

    /// <summary>关系集合。</summary>
    public required MappingRelationBinding[] Relations { get; init; }

    /// <summary>身份规则集合。</summary>
    public required MappingIdentitySpec[] IdentitySpecs { get; init; }

    /// <summary>时间规则集合。</summary>
    public required MappingTemporalSpec[] TemporalSpecs { get; init; }

    /// <summary>纯转换集合。</summary>
    public required MappingConversion[] Conversions { get; init; }

    /// <summary>真实源单位证据集合。</summary>
    public required MappingUnitSpec[] UnitSpecs { get; init; }
}

/// <summary>审批必须固定的所有输入版本。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingVersionBinding
{
    /// <summary>连接标识。</summary>
    public required string SourceConnectionId { get; init; }

    /// <summary>固定连接配置修订。</summary>
    public required long ConnectionRevision { get; init; }

    /// <summary>配置内容散列。</summary>
    public required string ConfigHash { get; init; }

    /// <summary>首切片POSTGRESQL。</summary>
    public required string SourceType { get; init; }

    /// <summary>固定目录快照。</summary>
    public required string SourceCatalogSnapshotId { get; init; }

    /// <summary>原目录算法生成的指纹。</summary>
    public required string SourceCatalogFingerprint { get; init; }

    /// <summary>G3固定发布标识。</summary>
    public required string OntologyReleaseId { get; init; }

    /// <summary>G3原Manifest散列。</summary>
    public required string OntologyManifestHash { get; init; }

    /// <summary>固定映射语义散列。</summary>
    public required string MappingHash { get; init; }

    /// <summary>不可变受审评估散列。</summary>
    public required string ValidationHash { get; init; }

    /// <summary>固定影响基线散列。</summary>
    public required string ImpactHash { get; init; }

    /// <summary>不可变评估标识。</summary>
    public required string AssessmentId { get; init; }

    /// <summary>源适配器版本。</summary>
    public required string AdapterVersion { get; init; }

    /// <summary>验证执行器版本。</summary>
    public required string ExecutorVersion { get; init; }

    /// <summary>映射canonical版本。</summary>
    public required string CanonicalVersion { get; init; }

    /// <summary>当前凭据版本，不含明文。</summary>
    public required long SecretVersion { get; init; }

    /// <summary>组织级授权版本。</summary>
    public required long AuthorizationEpoch { get; init; }
}

/// <summary>指针ID与单调修订共同防止ABA。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingExpectedActive
{
    /// <summary>首次激活为null。</summary>
    public required string? ReleaseId { get; init; }

    /// <summary>首次为0，之后单调增加。</summary>
    public required long ActivationRevision { get; init; }
}

/// <summary>异人对固定提案作决定。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingDecisionRequest
{
    /// <summary>APPROVE或REJECT。</summary>
    public required string Decision { get; init; }

    /// <summary>已审不可变提案绑定散列。</summary>
    public required string BindingHash { get; init; }

    /// <summary>决定命令及预期提案修订。</summary>
    public required CommandContext Command { get; init; }
}

/// <summary>固定批准目标的CAS激活命令。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingActivationRequest
{
    /// <summary>不可变提案散列。</summary>
    public required string BindingHash { get; init; }

    /// <summary>必须等于提案固定CAS基线。</summary>
    public required MappingExpectedActive ExpectedActive { get; init; }

    /// <summary>幂等及预期提案修订。</summary>
    public required CommandContext Command { get; init; }
}

/// <summary>创建固定本体与源的映射草稿。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingDraftCreateRequest
{
    /// <summary>完整组织厂区选择。</summary>
    public required ResourceScope Scope { get; init; }

    /// <summary>G3固定发布。</summary>
    public required string OntologyReleaseId { get; init; }

    /// <summary>原发布散列。</summary>
    public required string OntologyManifestHash { get; init; }

    /// <summary>固定连接。</summary>
    public required string SourceConnectionId { get; init; }

    /// <summary>固定目录。</summary>
    public required string SourceCatalogSnapshotId { get; init; }

    /// <summary>手工或规则采纳的内容。</summary>
    public required MappingDefinition Mapping { get; init; }

    /// <summary>创建命令，修订为0。</summary>
    public required CommandContext Command { get; init; }
}

/// <summary>不更换长期身份的CAS内容编辑。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingDraftPatchRequest
{
    /// <summary>新的完整映射内容。</summary>
    public required MappingDefinition Mapping { get; init; }

    /// <summary>草稿预期修订。</summary>
    public required CommandContext Command { get; init; }
}

/// <summary>取消等无额外载荷的命令。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingCommandRequest
{
    /// <summary>幂等与预期对象修订。</summary>
    public required CommandContext Command { get; init; }
}

/// <summary>通过kind严格区分发布与回滚，回滚不存在草稿字段。</summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "kind")]
[JsonDerivedType(typeof(MappingPublishProposalRequest), "PUBLISH")]
[JsonDerivedType(typeof(MappingRollbackProposalRequest), "ROLLBACK")]
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public abstract record MappingProposalCreateRequest
{
    /// <summary>固定g4.mapping.v1。</summary>
    public required string SchemaVersion { get; init; }

    /// <summary>完整资源范围。</summary>
    public required ResourceScope Scope { get; init; }

    /// <summary>全部评估输入版本。</summary>
    public required MappingVersionBinding Binding { get; init; }

    /// <summary>固定指针CAS基线。</summary>
    public required MappingExpectedActive ExpectedActive { get; init; }

    /// <summary>提案最晚有效时刻。</summary>
    public required DateTimeOffset ExpiresAtUtc { get; init; }

    /// <summary>新提案命令，expectedRevision为0。</summary>
    public required CommandContext Command { get; init; }

}

/// <summary>发布必须绑定当前不可变草稿修订。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingPublishProposalRequest : MappingProposalCreateRequest
{
    /// <summary>固定草稿标识。</summary>
    public required string DraftId { get; init; }

    /// <summary>固定且必须仍当前的修订。</summary>
    public required long DraftRevision { get; init; }
}

/// <summary>回滚只绑定历史正式制品，不接受当前草稿替代。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingRollbackProposalRequest : MappingProposalCreateRequest
{
    /// <summary>同映射和完整scope的历史发布。</summary>
    public required string TargetReleaseId { get; init; }

    /// <summary>历史manifest原字节散列。</summary>
    public required string ManifestHash { get; init; }
}

/// <summary>映射专用严格JSON选项，禁止未知字段和隐式大小写容错。</summary>
public static class G4MappingJson
{
    /// <summary>统一Host与合同测试使用的只读选项。</summary>
    public static JsonSerializerOptions Options { get; } = Create();

    /// <summary>构造Web命名、显式null与严格必填选项。</summary>
    private static JsonSerializerOptions Create()
    {
        // HTTP与生成模型共享同一命名及空值语义。
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web)
        {
            PropertyNameCaseInsensitive = false,
            UnmappedMemberHandling = JsonUnmappedMemberHandling.Disallow,
            RespectNullableAnnotations = true,
            AllowOutOfOrderMetadataProperties = true,
            NumberHandling = JsonNumberHandling.Strict,
            MaxDepth = 48
        };
        options.Converters.Add(new MappingUtcConverter());
        options.MakeReadOnly(populateMissingResolver: true);
        return options;
    }
}

/// <summary>验证目标判别，回滚不要求当前草稿等于历史版本。</summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "kind")]
[JsonDerivedType(typeof(MappingPublishTarget), "PUBLISH")]
[JsonDerivedType(typeof(MappingRollbackTarget), "ROLLBACK")]
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public abstract record MappingValidationTarget;

/// <summary>映射固定编辑修订及当前评估投影，不混入Proposal状态。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingDraftView
{
    /// <summary>固定g4.mapping.v1。</summary>
    public required string SchemaVersion { get; init; }

    /// <summary>永久映射标识。</summary>
    public required string MappingId { get; init; }

    /// <summary>永久草稿标识。</summary>
    public required string DraftId { get; init; }

    /// <summary>不可裁剪的完整范围。</summary>
    public required ResourceScope Scope { get; init; }

    /// <summary>固定G3正式发布。</summary>
    public required string OntologyReleaseId { get; init; }

    /// <summary>G3原Manifest散列。</summary>
    public required string OntologyManifestHash { get; init; }

    /// <summary>固定源连接。</summary>
    public required string SourceConnectionId { get; init; }

    /// <summary>固定目录快照。</summary>
    public required string SourceCatalogSnapshotId { get; init; }

    /// <summary>保存修订单调CAS。</summary>
    public required long Revision { get; init; }

    /// <summary>定义canonical内容散列。</summary>
    public required string MappingHash { get; init; }

    /// <summary>固定定义内容。</summary>
    public required MappingDefinition Mapping { get; init; }

    /// <summary>仅Draft状态机。</summary>
    public required string Status { get; init; }

    /// <summary>此修订保存时间。</summary>
    public required DateTimeOffset UpdatedAtUtc { get; init; }
}

/// <summary>发布验证只固定草稿修订。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingPublishTarget : MappingValidationTarget
{
    /// <summary>目标草稿修订。</summary>
    public required long DraftRevision { get; init; }
}

/// <summary>回滚验证只固定历史制品。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingRollbackTarget : MappingValidationTarget
{
    /// <summary>目标正式发布标识。</summary>
    public required string TargetReleaseId { get; init; }

    /// <summary>旧制品原字节散列。</summary>
    public required string ManifestHash { get; init; }
}

/// <summary>验证调度仍须核最新编辑头CAS。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingValidateRequest
{
    /// <summary>严格发布或回滚目标。</summary>
    public required MappingValidationTarget Target { get; init; }

    /// <summary>调度幂等与最新编辑头修订。</summary>
    public required CommandContext Command { get; init; }
}

/// <summary>首切片仅人工和确定性候选，不调用模型。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingSuggestionRequest
{
    /// <summary>唯一允许OFF。</summary>
    public required string Mode { get; init; }

    /// <summary>同修订幂等命令。</summary>
    public required CommandContext Command { get; init; }
}

/// <summary>不可变的单阶段实证摘要，不能默认PASS。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingStageResult
{
    /// <summary>七个固定阶段之一。</summary>
    public required string Stage { get; init; }

    /// <summary>PASS、FAIL、INDETERMINATE、NOT_RUN。</summary>
    public required string Status { get; init; }

    /// <summary>固定脱敏诊断代码。</summary>
    public required string[] IssueCodes { get; init; }

    /// <summary>本次真实阶段证据散列。</summary>
    public required string EvidenceHash { get; init; }
}

/// <summary>可定位的安全问题，不包含源行值。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingIssue
{
    /// <summary>固定错误代码。</summary>
    public required string Code { get; init; }

    /// <summary>能明确定位时给出绑定ID。</summary>
    public required string? BindingId { get; init; }

    /// <summary>能明确定位时给出固定字段。</summary>
    public required MappingFieldRef? FieldRef { get; init; }
}

/// <summary>原受审七阶段报告；新的激活复核不能覆盖它。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingAssessmentView
{
    /// <summary>固定g4.mapping.v1。</summary>
    public required string SchemaVersion { get; init; }

    /// <summary>不可变报告标识。</summary>
    public required string AssessmentId { get; init; }

    /// <summary>报告所属映射。</summary>
    public required string MappingId { get; init; }

    /// <summary>受评估固定目标。</summary>
    public required MappingValidationTarget Target { get; init; }

    /// <summary>完整受审输入及本报告散列。</summary>
    public required MappingVersionBinding Binding { get; init; }

    /// <summary>受审影响分析的Active基线。</summary>
    public required MappingExpectedActive ExpectedActive { get; init; }

    /// <summary>固定顺序七阶段。</summary>
    public required MappingStageResult[] Stages { get; init; }

    /// <summary>脱敏且可定位的问题。</summary>
    public required MappingIssue[] Issues { get; init; }

    /// <summary>真实聚合状态。</summary>
    public required string Status { get; init; }

    /// <summary>稳定语义不变量散列，排除观察时刻与业务数值。</summary>
    public required string SemanticResultHash { get; init; }

    /// <summary>本次真实观察证据散列，用于重算受审validationHash。</summary>
    public required string EvidenceHash { get; init; }

    /// <summary>真实评估开始时刻。</summary>
    public required DateTimeOffset StartedAtUtc { get; init; }

    /// <summary>真实评估完成时刻。</summary>
    public required DateTimeOffset FinishedAtUtc { get; init; }

    /// <summary>受审报告到期时刻。</summary>
    public required DateTimeOffset ExpiresAtUtc { get; init; }
}

/// <summary>持久任务状态；刷新只读取，不重复调度。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingJobView
{
    /// <summary>永久任务标识。</summary>
    public required string JobId { get; init; }

    /// <summary>所属映射。</summary>
    public required string MappingId { get; init; }

    /// <summary>任务状态CAS修订。</summary>
    public required long Revision { get; init; }

    /// <summary>固定受评估目标。</summary>
    public required MappingValidationTarget Target { get; init; }

    /// <summary>QUEUED、RUNNING、SUCCEEDED、FAILED、CANCELLED。</summary>
    public required string Status { get; init; }

    /// <summary>成功报告引用，其余为空。</summary>
    public required string? AssessmentId { get; init; }

    /// <summary>脱敏失败代码。</summary>
    public required string[] IssueCodes { get; init; }

    /// <summary>服务器调度时刻。</summary>
    public required DateTimeOffset CreatedAtUtc { get; init; }

    /// <summary>未完成时为null。</summary>
    public required DateTimeOffset? CompletedAtUtc { get; init; }
}

/// <summary>与固定输入散列绑定的独立审核事实。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingDecision
{
    /// <summary>审核主体，不得等提交主体。</summary>
    public required string DecidedBy { get; init; }

    /// <summary>服务器决定时刻。</summary>
    public required DateTimeOffset DecidedAtUtc { get; init; }

    /// <summary>APPROVE或REJECT。</summary>
    public required string Decision { get; init; }

    /// <summary>审核命令理由。</summary>
    public required string Reason { get; init; }

    /// <summary>审核时固定提案散列。</summary>
    public required string BindingHash { get; init; }
}

/// <summary>成功原子提交后的可恢复原回执。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingActivationReceipt
{
    /// <summary>唯一激活标识。</summary>
    public required string ActivationId { get; init; }

    /// <summary>永久映射标识。</summary>
    public required string MappingId { get; init; }

    /// <summary>批准提案标识。</summary>
    public required string ProposalId { get; init; }

    /// <summary>PUBLISH或ROLLBACK。</summary>
    public required string Kind { get; init; }

    /// <summary>实际目标发布标识。</summary>
    public required string MappingReleaseId { get; init; }

    /// <summary>目标原字节散列。</summary>
    public required string ManifestHash { get; init; }

    /// <summary>首次激活才为null。</summary>
    public required string? PreviousReleaseId { get; init; }

    /// <summary>包括回滚在内单调递增。</summary>
    public required long ActivationRevision { get; init; }

    /// <summary>同物理事务的治理审计。</summary>
    public required string AuditId { get; init; }

    /// <summary>同物理事务的事件标识。</summary>
    public required string OutboxEventId { get; init; }

    /// <summary>提交前生成且提交后才公开的时刻。</summary>
    public required DateTimeOffset ActivatedAtUtc { get; init; }
}

/// <summary>发布和回滚的封闭独立审核读模型。</summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "kind")]
[JsonDerivedType(typeof(MappingPublishProposalView), "PUBLISH")]
[JsonDerivedType(typeof(MappingRollbackProposalView), "ROLLBACK")]
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public abstract record MappingProposalView
{
    /// <summary>固定g4.mapping.v1。</summary>
    public required string SchemaVersion { get; init; }

    /// <summary>提案永久标识。</summary>
    public required string ProposalId { get; init; }

    /// <summary>所属映射。</summary>
    public required string MappingId { get; init; }

    /// <summary>提案CAS修订。</summary>
    public required long ProposalRevision { get; init; }

    /// <summary>完整固定范围。</summary>
    public required ResourceScope Scope { get; init; }

    /// <summary>固定受审输入。</summary>
    public required MappingVersionBinding Binding { get; init; }

    /// <summary>固定影响和CAS基线。</summary>
    public required MappingExpectedActive ExpectedActive { get; init; }

    /// <summary>原提交主体。</summary>
    public required string SubmittedBy { get; init; }

    /// <summary>原提交时间。</summary>
    public required DateTimeOffset SubmittedAtUtc { get; init; }

    /// <summary>不可延长的截止时间。</summary>
    public required DateTimeOffset ExpiresAtUtc { get; init; }

    /// <summary>提案状态或当前STALE/EXPIRED投影。</summary>
    public required string Status { get; init; }

    /// <summary>未决定时为空。</summary>
    public required MappingDecision? Decision { get; init; }

    /// <summary>不可变提案内容散列。</summary>
    public required string BindingHash { get; init; }

    /// <summary>未激活时为空。</summary>
    public required MappingActivationReceipt? Activation { get; init; }
}

/// <summary>发布提案携带准确草稿身份。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingPublishProposalView : MappingProposalView
{
    /// <summary>固定草稿标识。</summary>
    public required string DraftId { get; init; }

    /// <summary>受审精确草稿修订。</summary>
    public required long DraftRevision { get; init; }
}

/// <summary>回滚提案只指向历史原字节。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingRollbackProposalView : MappingProposalView
{
    /// <summary>固定历史发布。</summary>
    public required string TargetReleaseId { get; init; }

    /// <summary>历史制品散列。</summary>
    public required string ManifestHash { get; init; }
}

/// <summary>正式制品内不可变的原始审核收据。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingReviewReceipt
{
    /// <summary>原发布提案。</summary>
    public required string ProposalId { get; init; }

    /// <summary>原提案散列。</summary>
    public required string BindingHash { get; init; }

    /// <summary>原提交主体。</summary>
    public required string SubmittedBy { get; init; }

    /// <summary>原异人审核主体。</summary>
    public required string DecidedBy { get; init; }

    /// <summary>原决定时刻。</summary>
    public required DateTimeOffset DecidedAtUtc { get; init; }
}

/// <summary>只追加的正式映射制品，不含Active或当前健康。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingReleaseManifest
{
    /// <summary>固定g4.mapping.v1。</summary>
    public required string SchemaVersion { get; init; }

    /// <summary>正式发布唯一标识。</summary>
    public required string MappingReleaseId { get; init; }

    /// <summary>永久映射标识。</summary>
    public required string MappingId { get; init; }

    /// <summary>完整固定范围。</summary>
    public required ResourceScope Scope { get; init; }

    /// <summary>原始草稿标识。</summary>
    public required string OriginDraftId { get; init; }

    /// <summary>原始受审修订。</summary>
    public required long OriginDraftRevision { get; init; }

    /// <summary>原发布全部受审输入。</summary>
    public required MappingVersionBinding Binding { get; init; }

    /// <summary>原始映射定义。</summary>
    public required MappingDefinition Mapping { get; init; }

    /// <summary>不可变的异人审批收据。</summary>
    public required MappingReviewReceipt ReviewReceipt { get; init; }

    /// <summary>原发布创建时刻。</summary>
    public required DateTimeOffset CreatedAtUtc { get; init; }
}

/// <summary>当前使用状态独立于历史原字节。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingReleaseProjection
{
    /// <summary>当前编辑头CAS摘要；读取历史原件不要求最新草稿字段可见。</summary>
    public required long CurrentDraftRevision { get; init; }

    /// <summary>是否当前指针。</summary>
    public required bool Active { get; init; }

    /// <summary>当前单调激活版本。</summary>
    public required long ActivationRevision { get; init; }

    /// <summary>当前版本与授权是否可用。</summary>
    public required bool Usable { get; init; }

    /// <summary>不可用的固定原因。</summary>
    public required string[] ReasonCodes { get; init; }

    /// <summary>当前状态观察时刻。</summary>
    public required DateTimeOffset ObservedAtUtc { get; init; }
}

/// <summary>历史原文和当前状态分离，不裁剪Manifest仍宣称原hash。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingReleaseView
{
    /// <summary>完整原始Manifest。</summary>
    public required MappingReleaseManifest Manifest { get; init; }

    /// <summary>原canonical字节散列。</summary>
    public required string ManifestHash { get; init; }

    /// <summary>固定真，不支持原地编辑。</summary>
    public required bool ReadOnly { get; init; }

    /// <summary>当前状态投影。</summary>
    public required MappingReleaseProjection Projection { get; init; }
}

/// <summary>激活前独立新鲜复核，不改原Assessment。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingActivationCheck
{
    /// <summary>本次复核标识。</summary>
    public required string CheckId { get; init; }

    /// <summary>被复核提案。</summary>
    public required string ProposalId { get; init; }

    /// <summary>受审提案散列。</summary>
    public required string BindingHash { get; init; }

    /// <summary>原受审报告。</summary>
    public required string AssessmentId { get; init; }

    /// <summary>必须与原受审全部版本逐字段一致。</summary>
    public required MappingVersionBinding CheckedBinding { get; init; }

    /// <summary>本次复核完成时间。</summary>
    public required DateTimeOffset CheckedAtUtc { get; init; }

    /// <summary>不超过复核完成后30秒且不超提案截止。</summary>
    public required DateTimeOffset ExpiresAtUtc { get; init; }

    /// <summary>新七阶段真实实证。</summary>
    public required MappingStageResult[] Stages { get; init; }

    /// <summary>本次语义不变量散列。</summary>
    public required string SemanticResultHash { get; init; }

    /// <summary>本次观察证据散列。</summary>
    public required string EvidenceHash { get; init; }
}

/// <summary>列表仅提供当前完整可见对象。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingListItem
{
    /// <summary>永久映射标识。</summary>
    public required string MappingId { get; init; }

    /// <summary>完整范围。</summary>
    public required ResourceScope Scope { get; init; }

    /// <summary>最新编辑修订。</summary>
    public required long Revision { get; init; }

    /// <summary>Draft状态。</summary>
    public required string Status { get; init; }

    /// <summary>未激活时null。</summary>
    public required string? ActiveReleaseId { get; init; }
}

/// <summary>当前指针及可用性，无指针以404表示。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingActiveView
{
    /// <summary>永久映射。</summary>
    public required string MappingId { get; init; }

    /// <summary>当前正式制品。</summary>
    public required string MappingReleaseId { get; init; }

    /// <summary>制品原hash。</summary>
    public required string ManifestHash { get; init; }

    /// <summary>单调激活修订。</summary>
    public required long ActivationRevision { get; init; }

    /// <summary>当前可用性。</summary>
    public required bool Usable { get; init; }

    /// <summary>当前不可用原因。</summary>
    public required string[] ReasonCodes { get; init; }
}

/// <summary>映射wire固定七位小数UTC，不改变G2/G3历史序列化器。</summary>
public sealed class MappingUtcConverter : JsonConverter<DateTimeOffset>
{
    /// <summary>唯一允许的精确UTC格式。</summary>
    private const string Format = "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'";

    /// <summary>拒绝可变精度、offset替代及不合法日期。</summary>
    public override DateTimeOffset Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType != JsonTokenType.String || !DateTimeOffset.TryParseExact(reader.GetString(), Format,
            CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal | DateTimeStyles.AdjustToUniversal, out var instant))
        {
            throw new JsonException("映射时间必须为固定精度UTC。");
        }
        return instant;
    }

    /// <summary>跨文化和时区统一输出，不丢弃尾随小数零。</summary>
    public override void Write(Utf8JsonWriter writer, DateTimeOffset value, JsonSerializerOptions options)
    {
        writer.WriteStringValue(value.ToUniversalTime().ToString(Format, CultureInfo.InvariantCulture));
    }
}

/// <summary>所有映射列表共用有界keyset分页，游标只能由服务端签发。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingPage<T>
{
    /// <summary>本页当前完整授权的对象。</summary>
    public required T[] Items { get; init; }

    /// <summary>终页为空；非空绑定主体、scope、epoch、筛选及五分钟期限。</summary>
    public required string? NextCursor { get; init; }
}

/// <summary>人工模式不调用模型、不自动写草稿，候选仍须显式保存及验证。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingSuggestionView
{
    /// <summary>本次候选依据的固定编辑修订。</summary>
    public required long Revision { get; init; }

    /// <summary>首切片人工模式不猜测缺证据的候选。</summary>
    public required MappingSuggestionCandidate[] Candidates { get; init; }

    /// <summary>固定脱敏提示码。</summary>
    public required string[] IssueCodes { get; init; }
}

/// <summary>确定性候选引用，仍非批准或正式映射。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingSuggestionCandidate
{
    /// <summary>固定目录字段。</summary>
    public required MappingFieldRef FieldRef { get; init; }

    /// <summary>现存正式发布IRI。</summary>
    public required string TargetIri { get; init; }

    /// <summary>METADATA、TERM、USER_ASSERTION或NO_EVIDENCE。</summary>
    public required string Evidence { get; init; }

    /// <summary>候选不能直接成为可发布PASS。</summary>
    public required string Status { get; init; }
}

/// <summary>两个已授权固定原件的准确结构差异，不比较最新替代内容。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingDiffView
{
    /// <summary>永久映射身份。</summary>
    public required string MappingId { get; init; }

    /// <summary>起点原件或定义散列。</summary>
    public required string FromHash { get; init; }

    /// <summary>终点原件或定义散列。</summary>
    public required string ToHash { get; init; }

    /// <summary>按JSON指针排序的准确变化，省略与null明确分开。</summary>
    public required MappingDifference[] Changes { get; init; }
}

/// <summary>JSON指针上的精确结构变化，exists字段区分缺席和显式null。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record MappingDifference
{
    /// <summary>RFC6901字段位置。</summary>
    public required string Path { get; init; }

    /// <summary>旧原件是否存在该路径。</summary>
    public required bool BeforeExists { get; init; }

    /// <summary>新原件是否存在该路径。</summary>
    public required bool AfterExists { get; init; }

    /// <summary>旧值，路径缺席时为null。</summary>
    public required JsonElement? Before { get; init; }

    /// <summary>新值，路径缺席时为null。</summary>
    public required JsonElement? After { get; init; }
}
