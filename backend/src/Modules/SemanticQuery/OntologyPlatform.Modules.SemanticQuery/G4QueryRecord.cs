namespace OntologyPlatform.Modules.SemanticQuery;

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
