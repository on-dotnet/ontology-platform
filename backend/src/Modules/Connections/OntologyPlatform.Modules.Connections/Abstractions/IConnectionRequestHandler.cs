using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>HTTP边界之后的内部请求，外部不能提交Actor或会话引用。</summary>
public sealed record ConnectionInvocation
{
    /// <summary>固定服务端操作名。</summary>
    public required string Operation { get; init; }

    /// <summary>可信服务端身份。</summary>
    public required ActorContext Actor { get; init; }

    /// <summary>路由连接标识。</summary>
    public required string? Id { get; init; }

    /// <summary>路由子对象标识。</summary>
    public required string? ChildId { get; init; }

    /// <summary>已严格验证的请求DTO。</summary>
    public required object? Body { get; init; }

    /// <summary>原始If-Match。</summary>
    public required string? Etag { get; init; }

    /// <summary>受控分页游标。</summary>
    public required string? Cursor { get; init; }

    /// <summary>连接类型筛选。</summary>
    public required string? Type { get; init; }

    /// <summary>连接状态筛选。</summary>
    public required string? State { get; init; }

    /// <summary>内部可信会话引用。</summary>
    public required string SessionReference { get; init; }
}

/// <summary>提交后的应用回执，Host只映射状态、ETag和公开DTO。</summary>
public sealed record ConnectionReply
{
    /// <summary>公开结果对象。</summary>
    public required object Value { get; init; }

    /// <summary>HTTP状态码。</summary>
    public int StatusCode { get; init; } = 200;

    /// <summary>已绑定资源修订的强ETag。</summary>
    public string? Etag { get; init; }
}

/// <summary>连接应用边界，HTTP与未来传输复用同一受控服务。</summary>
public interface IConnectionRequestHandler
{
    /// <summary>执行当前固定操作，权限、版本、幂等和事务在应用内再次核验。</summary>
    Task<ConnectionReply> HandleAsync(ConnectionInvocation invocation, CancellationToken token);
}
