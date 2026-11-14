using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>单分支完成后的有界授权投影及真实读取回执，尚未成为对外响应。</summary>
public sealed record G4QueryBranchProjection
{
    /// <summary>逐行已映射来源观察时间；未登记时使用实际读取观察时间，不填补事件时间。</summary>
    public string[] ObservedTimes { get; init; } = [];

    /// <summary>只包含完整可验证的实体断言。</summary>
    public required G4EntityDatum[] Entities { get; init; }

    /// <summary>逐行来源，与实体和属性引用严格闭合。</summary>
    public required G4SourceEvidenceRef[] Evidence { get; init; }

    /// <summary>实际分支读取事实，hash在外列。</summary>
    public required G4QueryStoredReceipt Receipt { get; init; }
}

/// <summary>原子准入结果；重复键只引用已有执行，不再次访问外部源。</summary>
public sealed record G4QueryAdmission
{
    /// <summary>已提交查询记录。</summary>
    public required G4QueryRecord Record { get; init; }

    /// <summary>仅新建记录允许本实例执行源读取。</summary>
    public required bool Created { get; init; }
}

/// <summary>执行时固定的安全元数据，不包含源原始行或解密凭据。</summary>
public sealed record G4QueryState
{
    /// <summary>完整固定版本链。</summary>
    public required G4QueryBinding Binding { get; init; }

    /// <summary>已验证的范围交集。</summary>
    public required ResourceScope Scope { get; init; }

    /// <summary>恢复时必须逐个重新取得当前许可的完整投影。</summary>
    public required G4QueryProjection[] Projections { get; init; }

    /// <summary>零授权分支仍保留原计划字段依赖，用于将来恢复时取得当前完整许可。</summary>
    public G4QueryProjection[] RequiredProjections { get; init; } = [];

    /// <summary>已完成分支的安全回执与外置散列，同结果事务保存，不包含源原始行。</summary>
    public G4QueryStoredReceipt[] Receipts { get; init; } = [];
}

/// <summary>回执原件与其独立摘要分列存储，避免hash自包含。</summary>
public sealed record G4QueryStoredReceipt
{
    /// <summary>封闭的分支读取事实。</summary>
    public required G4SourceReadReceipt Receipt { get; init; }

    /// <summary>仅覆盖Receipt规范字节的SHA256。</summary>
    public required string ReceiptHash { get; init; }
}

/// <summary>只在服务端持久化的封闭读取回执，普通HTTP不能输出完整Binding。</summary>
public sealed record G4SourceReadReceipt
{
    /// <summary>冻结内部读取回执版本。</summary>
    public required string SchemaVersion { get; init; }

    /// <summary>随机不可猜的分支身份。</summary>
    public required string ReceiptId { get; init; }

    /// <summary>所属查询，禁止跨查询引用回执。</summary>
    public required string QueryId { get; init; }

    /// <summary>执行时完整不可变版本链。</summary>
    public required G4QueryBinding Binding { get; init; }

    /// <summary>固定源数据集身份。</summary>
    public required string SourceDatasetRef { get; init; }

    /// <summary>有界类型计划摘要，不保存SQL或查询秘密。</summary>
    public required string QueryPlanHash { get; init; }

    /// <summary>实际执行的查询适配器版本。</summary>
    public required string AdapterVersion { get; init; }

    /// <summary>本分支获准的完整组织厂区范围。</summary>
    public required ResourceScope Scope { get; init; }

    /// <summary>与subSource一致的六种分支状态。</summary>
    public required string Status { get; init; }

    /// <summary>本分支授权投影数量，不超过一百。</summary>
    public required int RowCount { get; init; }

    /// <summary>是否真实超过本分支预算。</summary>
    public required bool Limited { get; init; }

    /// <summary>真实水位类型，不暗示跨分支原子快照。</summary>
    public required string WatermarkKind { get; init; }

    /// <summary>实际PG事务快照或明确未知。</summary>
    public required string? Watermark { get; init; }

    /// <summary>仅确实单行可定位时为非空，多行不得造一个总记录键。</summary>
    public required string? SourceRecordRef { get; init; }

    /// <summary>记录、数据集、窗口或未知的实际证据精度。</summary>
    public required string Precision { get; init; }

    /// <summary>可靠UTC半开窗口或未知。</summary>
    public required G4QueryUtcInterval? ValidTime { get; init; }

    /// <summary>分支真实开始时间。</summary>
    public required string ReadStartedAtUtc { get; init; }

    /// <summary>真实结束时间，不用结果提交时间冒充。</summary>
    public required string ReadCompletedAtUtc { get; init; }

    /// <summary>只覆盖分支授权投影规范字节，不包含本回执或总结果。</summary>
    public required string? ResultHash { get; init; }

    /// <summary>可信服务器关联身份。</summary>
    public required string TraceId { get; init; }
}

/// <summary>待事务保存的密文与准确明文摘要，不承载解密后的业务对象。</summary>
public sealed record G4QueryProtectedResult
{
    /// <summary>绑定查询身份的认证密文。</summary>
    public required byte[] Ciphertext { get; init; }

    /// <summary>规范明文SHA256。</summary>
    public required string Hash { get; init; }

    /// <summary>规范明文长度，用于总容量约束。</summary>
    public required int Size { get; init; }
}

/// <summary>查询模块独占的恢复记录，业务值只保存为有界密文。</summary>
public sealed class G4QueryRecord
{
    /// <summary>服务器查询唯一身份。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>所属组织范围。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>可信创建主体。</summary>
    public string SubjectId { get; set; } = string.Empty;

    /// <summary>服务器会话哈希引用，不包含票据或令牌。</summary>
    public string SessionReference { get; set; } = string.Empty;

    /// <summary>本次固定单源连接。</summary>
    public string ConnectionId { get; set; } = string.Empty;

    /// <summary>主体和组织域内的命令幂等键。</summary>
    public string IdempotencyKey { get; set; } = string.Empty;

    /// <summary>请求与选择上下文规范字节SHA256。</summary>
    public string RequestHash { get; set; } = string.Empty;

    /// <summary>受控请求的准确原件，不保存源原始行。</summary>
    public byte[] RequestBytes { get; set; } = [];

    /// <summary>不可变版本绑定原件，保存后不静默换Active。</summary>
    public byte[] BindingBytes { get; set; } = [];

    /// <summary>批准合成结果的加密规范字节。</summary>
    public byte[] ResultCiphertext { get; set; } = [];

    /// <summary>成功结果明文规范字节SHA256，仅内部可见。</summary>
    public string? ResultHash { get; set; } = null;

    /// <summary>结果明文规范字节数量，用于任务总预算。</summary>
    public int ResultSize { get; set; } = 0;

    /// <summary>执行进度与业务六态分离。</summary>
    public string ExecutionStatus { get; set; } = "RUNNING";

    /// <summary>固定脱敏失败码，不保存异常正文。</summary>
    public string? ErrorCode { get; set; } = null;

    /// <summary>真实创建时刻。</summary>
    public DateTimeOffset CreatedAtUtc { get; set; } = default;

    /// <summary>源读取与提交共用绝对期限。</summary>
    public DateTimeOffset DeadlineAtUtc { get; set; } = default;

    /// <summary>合成结果不可延长的到期时间。</summary>
    public DateTimeOffset ExpiresAtUtc { get; set; } = default;

    /// <summary>已终结时间，执行中为空。</summary>
    public DateTimeOffset? CompletedAtUtc { get; set; } = null;

    /// <summary>本次跨实例执行租约截止。</summary>
    public DateTimeOffset? LeaseUntilUtc { get; set; } = null;

    /// <summary>当前持有实例身份。</summary>
    public string? LeaseOwner { get; set; } = null;

    /// <summary>每次取得租约单调递增，阻止迟到提交。</summary>
    public long Fence { get; set; } = 0;

    /// <summary>取消事务已提交的持久标志。</summary>
    public bool CancelRequested { get; set; } = false;

}
