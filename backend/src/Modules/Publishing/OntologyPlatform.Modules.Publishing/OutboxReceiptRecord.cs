namespace OntologyPlatform.Modules.Publishing;

/// <summary>事件消费者唯一去重回执，不参与活动指针切换。</summary>
public sealed class OutboxReceiptRecord
{
    /// <summary>已消费事件唯一主键。</summary>
    public string EventId { get; set; } = string.Empty;

    /// <summary>经真实调和版本。</summary>
    public string ReleaseId { get; set; } = string.Empty;

    /// <summary>消费验证的清单散列。</summary>
    public string ManifestHash { get; set; } = string.Empty;

    /// <summary>实际制品和图验证完成时间。</summary>
    public DateTimeOffset VerifiedAtUtc { get; set; } = default;
}
