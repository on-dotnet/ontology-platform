using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>内部PG类型化执行边界，不接受SQL、URL或客户端任意表列。</summary>
public interface IG4PgQueryReader
{
    /// <summary>每次分支用独立只读事务；共享绝对截止，保留平台提交预算。</summary>
    Task<G4SourceQueryRead> ReadAsync(PgConnectionProfile profile, string secret, G4QueryBindingContext context,
        string entityBindingId, G4SemanticQuery query, DateTimeOffset deadlineAtUtc, CancellationToken cancellationToken);
}
