namespace OntologyPlatform.Modules.Agents;

/// <summary>Agents模块独占的持久运行、预算与租约事实。</summary>
public sealed class RunRecord
{
    /// <summary>服务器生成的运行唯一标识。</summary>
    public string RunId { get; set; } = string.Empty;

    /// <summary>创建运行的可信主体。</summary>
    public string OwnerSubjectId { get; set; } = string.Empty;

    /// <summary>完整资源范围所属组织。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>固定发布所需的全部厂区。</summary>
    public string[] SiteIds { get; set; } = [];

    /// <summary>唯一资产快照的完整序列化值。</summary>
    public string SnapshotJson { get; set; } = string.Empty;

    /// <summary>后台执行所需的服务器可信身份。</summary>
    public string ActorJson { get; set; } = string.Empty;

    /// <summary>已固定发布版本的唯一语义计划。</summary>
    public string PlanJson { get; set; } = string.Empty;

    /// <summary>仅保留在受保护PG的用户正文。</summary>
    public string SourcePrompt { get; set; } = string.Empty;

    /// <summary>受租约与终态规则保护的运行状态。</summary>
    public string Status { get; set; } = "QUEUED";

    /// <summary>明确禁用或离线确定性模式。</summary>
    public string ProviderMode { get; set; } = "disabled";

    /// <summary>实际创建时间。</summary>
    public DateTimeOffset CreatedAtUtc { get; set; } = default;

    /// <summary>最近持久变更时间。</summary>
    public DateTimeOffset UpdatedAtUtc { get; set; } = default;

    /// <summary>首次执行确定的三十秒绝对预算。</summary>
    public DateTimeOffset? DeadlineUtc { get; set; } = null;

    /// <summary>最后已提交的单调事件序号。</summary>
    public long LastSeq { get; set; } = 0;

    /// <summary>独立取消命令已提交的事实。</summary>
    public bool CancelRequested { get; set; } = false;

    /// <summary>当前租约执行者。</summary>
    public string? LeaseOwner { get; set; } = null;

    /// <summary>当前租约的绝对失效时间。</summary>
    public DateTimeOffset? LeaseUntil { get; set; } = null;

    /// <summary>阻止旧执行者提交的单调令牌。</summary>
    public long FencingToken { get; set; } = 0;

    /// <summary>跨接管保留的已预留工具调用次数。</summary>
    public int ToolCalls { get; set; } = 0;

    /// <summary>创建请求的实际链路标识。</summary>
    public string TraceId { get; set; } = string.Empty;
}
