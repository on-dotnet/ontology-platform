namespace OntologyPlatform.Modules.Publishing;

/// <summary>激活事务内写入并由带fence租约的后台工作者调和。</summary>
public sealed class OutboxRecord
{
    /// <summary>消费者去重唯一事件。</summary>
    public string EventId { get; set; } = string.Empty;

    /// <summary>事件固定正式版本。</summary>
    public string ReleaseId { get; set; } = string.Empty;

    /// <summary>事件固定活动修订。</summary>
    public long ActivationRevision { get; set; } = 0;

    /// <summary>固定事件类型。</summary>
    public string EventType { get; set; } = "release.activated";

    /// <summary>固定清单的校验散列。</summary>
    public string PayloadHash { get; set; } = string.Empty;

    /// <summary>事务事件创建时间。</summary>
    public DateTimeOffset CreatedAtUtc { get; set; } = default;

    /// <summary>真实调和尝试次数。</summary>
    public int Attempts { get; set; } = 0;

    /// <summary>下一次允许调和时间。</summary>
    public DateTimeOffset NextAttemptAtUtc { get; set; } = default;

    /// <summary>真正验证及消费成功时间。</summary>
    public DateTimeOffset? DispatchedAtUtc { get; set; } = null;

    /// <summary>当前随机worker身份。</summary>
    public string? LeaseOwner { get; set; } = null;

    /// <summary>租约过期后允许恢复。</summary>
    public DateTimeOffset? LeaseUntilUtc { get; set; } = null;

    /// <summary>每次接管递增防止过期worker提交。</summary>
    public long FencingToken { get; set; } = 0;
}
