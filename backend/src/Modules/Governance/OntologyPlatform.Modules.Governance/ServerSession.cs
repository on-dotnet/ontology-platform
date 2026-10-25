namespace OntologyPlatform.Modules.Governance;

/// <summary>保存加密服务器身份票据及不可滑动的有效期。</summary>
public sealed class ServerSession
{
    /// <summary>随机会话引用，不含身份或令牌。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>经共享DataProtection保护的服务器票据。</summary>
    public byte[] ProtectedTicket { get; set; } = [];

    /// <summary>固定会话失效的UTC时刻。</summary>
    public DateTimeOffset ExpiresAtUtc { get; set; } = default;

    /// <summary>注销撤销的UTC时刻，非空后不能复用。</summary>
    public DateTimeOffset? RevokedAtUtc { get; set; } = null;
}
