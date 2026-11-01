namespace OntologyPlatform.Modules.Connections;

/// <summary>Connections模块独占的ConnectionCommandRecord持久记录，不映射外部源业务表。</summary>
public sealed class ConnectionCommandRecord
{
    /// <summary>失败预约的固定错误码，不携异常详情。</summary>
    public string? ErrorCode { get; set; }

    /// <summary>actor组织操作目标和幂等键SHA256。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>完整请求用途HMAC。</summary>
    public string RequestHash { get; set; } = string.Empty;

    /// <summary>执行前授权资源范围。</summary>
    public string ScopeJson { get; set; } = string.Empty;

    /// <summary>执行后授权资源范围。</summary>
    public string ResultScopeJson { get; set; } = string.Empty;

    /// <summary>原始固定回执不含明文秘密。</summary>
    public string ReceiptJson { get; set; } = string.Empty;

    /// <summary>创建时间。</summary>
    public DateTimeOffset CreatedAtUtc { get; set; } = default;
    /// <summary>原始响应强ETag，重放不替换为当前修订。</summary>
    public string? Etag { get; set; }

    /// <summary>原始成功状态码。</summary>
    public int StatusCode { get; set; } = 200;
}
