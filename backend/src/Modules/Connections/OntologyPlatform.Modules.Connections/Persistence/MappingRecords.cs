namespace OntologyPlatform.Modules.Connections;

/// <summary>永久映射与当前编辑头，锁定此行保护首次激活。</summary>
public sealed class MappingRecord
{
    /// <summary>永久资源标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织，查询必须同时校验完整厂区。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整资源厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>CAS修订，成功写入后单调递增。</summary>
    public long Revision { get; set; } = 1;

    /// <summary>显示名称。</summary>
    public string DisplayName { get; set; } = string.Empty;

    /// <summary>当前草稿永久标识。</summary>
    public string DraftId { get; set; } = string.Empty;

    /// <summary>当前不可变修订引用。</summary>
    public string CurrentRevisionId { get; set; } = string.Empty;

    /// <summary>绑定的源连接。</summary>
    public string SourceConnectionId { get; set; } = string.Empty;

    /// <summary>最新保存时刻。</summary>
    public DateTimeOffset UpdatedAtUtc { get; set; }
}

/// <summary>每次保存产生新修订，不覆盖历史映射定义。</summary>
public sealed class MappingRevisionRecord
{
    /// <summary>永久资源标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织，查询必须同时校验完整厂区。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整资源厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>所属永久映射标识。</summary>
    public string MappingId { get; set; } = string.Empty;

    /// <summary>CAS修订，成功写入后单调递增。</summary>
    public long Revision { get; set; } = 1;

    /// <summary>不可变规范化原字节，不重新序列化替代。</summary>
    public byte[] CanonicalBytes { get; set; } = [];

    /// <summary>原字节SHA256小写hex。</summary>
    public string ContentHash { get; set; } = string.Empty;

    /// <summary>服务器记录创建时刻。</summary>
    public DateTimeOffset CreatedAtUtc { get; set; }

    /// <summary>原草稿标识。</summary>
    public string DraftId { get; set; } = string.Empty;

    /// <summary>保存主体。</summary>
    public string CreatedBy { get; set; } = string.Empty;
}

/// <summary>不可变七阶段受审报告，激活复核另存。</summary>
public sealed class MappingAssessmentRecord
{
    /// <summary>永久资源标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织，查询必须同时校验完整厂区。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整资源厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>所属永久映射标识。</summary>
    public string MappingId { get; set; } = string.Empty;

    /// <summary>不可变规范化原字节，不重新序列化替代。</summary>
    public byte[] CanonicalBytes { get; set; } = [];

    /// <summary>原字节SHA256小写hex。</summary>
    public string ContentHash { get; set; } = string.Empty;

    /// <summary>服务器记录创建时刻。</summary>
    public DateTimeOffset CreatedAtUtc { get; set; }

    /// <summary>PUBLISH或ROLLBACK。</summary>
    public string TargetKind { get; set; } = string.Empty;

    /// <summary>精确修订或历史发布标识。</summary>
    public string TargetId { get; set; } = string.Empty;

    /// <summary>发布目标修订，回滚为零。</summary>
    public long TargetRevision { get; set; }

    /// <summary>完整固定输入版本。</summary>
    public string BindingJson { get; set; } = string.Empty;

    /// <summary>排除观察时间的固定语义不变量散列。</summary>
    public string SemanticResultHash { get; set; } = string.Empty;

    /// <summary>受审Active基线和依赖变化散列。</summary>
    public string ImpactHash { get; set; } = string.Empty;

    /// <summary>七阶段聚合真实状态。</summary>
    public string Status { get; set; } = string.Empty;

    /// <summary>受审报告到期时间。</summary>
    public DateTimeOffset ExpiresAtUtc { get; set; }
}

/// <summary>提案固定受审目标与三方内部授权，状态通过CAS推进。</summary>
public sealed class MappingProposalRecord
{
    /// <summary>永久资源标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织，查询必须同时校验完整厂区。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整资源厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>所属永久映射标识。</summary>
    public string MappingId { get; set; } = string.Empty;

    /// <summary>CAS修订，成功写入后单调递增。</summary>
    public long Revision { get; set; } = 1;

    /// <summary>服务器记录创建时刻。</summary>
    public DateTimeOffset CreatedAtUtc { get; set; }

    /// <summary>PUBLISH或ROLLBACK判别。</summary>
    public string Kind { get; set; } = string.Empty;

    /// <summary>不含变化状态的固定提案请求。</summary>
    public byte[] RequestBytes { get; set; } = [];

    /// <summary>固定提案输入散列。</summary>
    public string BindingHash { get; set; } = string.Empty;

    /// <summary>PENDING、APPROVED、REJECTED、CANCELLED状态。</summary>
    public string Status { get; set; } = "PENDING";

    /// <summary>提交主体，不得自批。</summary>
    public string SubmittedBy { get; set; } = string.Empty;

    /// <summary>内部提交会话与授权证明，不能公开。</summary>
    public string SubmitProofJson { get; set; } = string.Empty;

    /// <summary>独立审核主体。</summary>
    public string? DecidedBy { get; set; }

    /// <summary>原始决定完整读取对象，包含固定理由与绑定hash。</summary>
    public string? DecisionJson { get; set; }

    /// <summary>内部审核会话证明，不能公开。</summary>
    public string? DecisionProofJson { get; set; }

    /// <summary>明确审核决定时间。</summary>
    public DateTimeOffset? DecidedAtUtc { get; set; }

    /// <summary>提案固定截止时间。</summary>
    public DateTimeOffset ExpiresAtUtc { get; set; }

    /// <summary>成功激活唯一引用。</summary>
    public string? ActivationId { get; set; }
}

/// <summary>只追加的正式发布原字节；数据库拒绝UPDATE和DELETE。</summary>
public sealed class MappingReleaseRecord
{
    /// <summary>永久资源标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织，查询必须同时校验完整厂区。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整资源厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>所属永久映射标识。</summary>
    public string MappingId { get; set; } = string.Empty;

    /// <summary>不可变规范化原字节，不重新序列化替代。</summary>
    public byte[] CanonicalBytes { get; set; } = [];

    /// <summary>原字节SHA256小写hex。</summary>
    public string ContentHash { get; set; } = string.Empty;

    /// <summary>服务器记录创建时刻。</summary>
    public DateTimeOffset CreatedAtUtc { get; set; }
}

/// <summary>当前正式发布指针，可用性不写入历史Manifest。</summary>
public sealed class MappingActiveRecord
{
    /// <summary>永久资源标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织，查询必须同时校验完整厂区。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整资源厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>所属永久映射标识。</summary>
    public string MappingId { get; set; } = string.Empty;

    /// <summary>当前正式发布标识。</summary>
    public string ReleaseId { get; set; } = string.Empty;

    /// <summary>包括回滚在内单调递增，防ABA。</summary>
    public long ActivationRevision { get; set; }

    /// <summary>产生当前指针的事务事实。</summary>
    public string ActivationId { get; set; } = string.Empty;
}

/// <summary>激活或回滚的不可变当前绑定、审计和Outbox收据。</summary>
public sealed class MappingActivationRecord
{
    /// <summary>永久资源标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织，查询必须同时校验完整厂区。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整资源厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>所属永久映射标识。</summary>
    public string MappingId { get; set; } = string.Empty;

    /// <summary>不可变规范化原字节，不重新序列化替代。</summary>
    public byte[] CanonicalBytes { get; set; } = [];

    /// <summary>原字节SHA256小写hex。</summary>
    public string ContentHash { get; set; } = string.Empty;

    /// <summary>服务器记录创建时刻。</summary>
    public DateTimeOffset CreatedAtUtc { get; set; }

    /// <summary>唯一已批准提案。</summary>
    public string ProposalId { get; set; } = string.Empty;

    /// <summary>实际目标发布。</summary>
    public string ReleaseId { get; set; } = string.Empty;

    /// <summary>本次新鲜复核证明。</summary>
    public string CheckId { get; set; } = string.Empty;

    /// <summary>本次执行使用的当前兼容版本。</summary>
    public string BindingJson { get; set; } = string.Empty;

    /// <summary>单调激活修订。</summary>
    public long ActivationRevision { get; set; }
}

/// <summary>每次网络复核的不可变证明，失败和过期记录也保留。</summary>
public sealed class MappingActivationCheckRecord
{
    /// <summary>永久资源标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织，查询必须同时校验完整厂区。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整资源厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>所属永久映射标识。</summary>
    public string MappingId { get; set; } = string.Empty;

    /// <summary>不可变规范化原字节，不重新序列化替代。</summary>
    public byte[] CanonicalBytes { get; set; } = [];

    /// <summary>原字节SHA256小写hex。</summary>
    public string ContentHash { get; set; } = string.Empty;

    /// <summary>服务器记录创建时刻。</summary>
    public DateTimeOffset CreatedAtUtc { get; set; }

    /// <summary>被复核提案。</summary>
    public string ProposalId { get; set; } = string.Empty;

    /// <summary>受审绑定散列。</summary>
    public string BindingHash { get; set; } = string.Empty;

    /// <summary>不超过检查时刻后30秒。</summary>
    public DateTimeOffset ExpiresAtUtc { get; set; }

    /// <summary>真实七阶段聚合状态。</summary>
    public string Status { get; set; } = string.Empty;
}

/// <summary>持久验证任务、租约及fence，旧工作者不得提交结果。</summary>
public sealed class MappingJobRecord
{
    /// <summary>永久资源标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织，查询必须同时校验完整厂区。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整资源厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>所属永久映射标识。</summary>
    public string MappingId { get; set; } = string.Empty;

    /// <summary>CAS修订，成功写入后单调递增。</summary>
    public long Revision { get; set; } = 1;

    /// <summary>服务器记录创建时刻。</summary>
    public DateTimeOffset CreatedAtUtc { get; set; }

    /// <summary>验证或建议。</summary>
    public string Kind { get; set; } = string.Empty;

    /// <summary>持久任务状态。</summary>
    public string Status { get; set; } = "QUEUED";

    /// <summary>固定验证输入。</summary>
    public string RequestJson { get; set; } = string.Empty;

    /// <summary>内部提交会话证明。</summary>
    public string AuthorityJson { get; set; } = string.Empty;

    /// <summary>任务原始主体。</summary>
    public string SubmittedBy { get; set; } = string.Empty;

    /// <summary>每次租约接管递增的栅栏。</summary>
    public long Fence { get; set; }

    /// <summary>短租约截止。</summary>
    public DateTimeOffset? LeaseUntil { get; set; }

    /// <summary>已提交结果标识。</summary>
    public string? ResultId { get; set; }

    /// <summary>实际终态时间，运行中为空。</summary>
    public DateTimeOffset? CompletedAtUtc { get; set; }

    /// <summary>固定脱敏失败代码。</summary>
    public string? ErrorCode { get; set; }
}

/// <summary>与Active、审计同事务写入的至少一次通知。</summary>
public sealed class MappingOutboxRecord
{
    /// <summary>永久资源标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织，查询必须同时校验完整厂区。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整资源厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>所属永久映射标识。</summary>
    public string MappingId { get; set; } = string.Empty;

    /// <summary>服务器记录创建时刻。</summary>
    public DateTimeOffset CreatedAtUtc { get; set; }

    /// <summary>正式发布引用。</summary>
    public string ReleaseId { get; set; } = string.Empty;

    /// <summary>正式发布原字节散列。</summary>
    public string ManifestHash { get; set; } = string.Empty;

    /// <summary>消费者只接受更大的修订。</summary>
    public long ActivationRevision { get; set; }

    /// <summary>成功消费时间，失败则保持待投递。</summary>
    public DateTimeOffset? DispatchedAtUtc { get; set; }

    /// <summary>真实投递次数。</summary>
    public long Attempts { get; set; }
}

/// <summary>消费者按eventId唯一去重的持久收据。</summary>
public sealed class MappingOutboxReceiptRecord
{
    /// <summary>已消费eventId唯一标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属映射。</summary>
    public string MappingId { get; set; } = string.Empty;

    /// <summary>此通知的激活修订。</summary>
    public long ActivationRevision { get; set; }

    /// <summary>服务器记录创建时刻。</summary>
    public DateTimeOffset CreatedAtUtc { get; set; }
}

/// <summary>同主体、范围和操作幂等响应恢复，不跨主体泄漏。</summary>
public sealed class MappingCommandRecord
{
    /// <summary>永久资源标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织，查询必须同时校验完整厂区。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>完整资源厂区集合。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>所属永久映射标识。</summary>
    public string MappingId { get; set; } = string.Empty;

    /// <summary>服务器记录创建时刻。</summary>
    public DateTimeOffset CreatedAtUtc { get; set; }

    /// <summary>原始调用主体。</summary>
    public string SubjectId { get; set; } = string.Empty;

    /// <summary>固定操作名。</summary>
    public string Operation { get; set; } = string.Empty;

    /// <summary>原命令标识，同一组织不能换键重用。</summary>
    public string CommandId { get; set; } = string.Empty;

    /// <summary>请求幂等键。</summary>
    public string IdempotencyKey { get; set; } = string.Empty;

    /// <summary>完整请求规范化散列。</summary>
    public string PayloadHash { get; set; } = string.Empty;

    /// <summary>成功提交后可恢复的原始响应。</summary>
    public byte[] ResponseBytes { get; set; } = [];
}

/// <summary>治理通知消费者的单调版本投影，不是M4执行数据或正式语义事实。</summary>
public sealed class MappingNotificationRecord
{
    /// <summary>永久mapping身份，同时是唯一主键。</summary>
    public string MappingId { get; set; } = string.Empty;

    /// <summary>投影保留完整组织边界。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>最后接受的激活修订，只能增大。</summary>
    public long ActivationRevision { get; set; }

    /// <summary>该修订正式发布标识。</summary>
    public string ReleaseId { get; set; } = string.Empty;

    /// <summary>该发布原字节散列。</summary>
    public string ManifestHash { get; set; } = string.Empty;

    /// <summary>最后接受的通知，旧通知不能覆盖。</summary>
    public string EventId { get; set; } = string.Empty;
}
