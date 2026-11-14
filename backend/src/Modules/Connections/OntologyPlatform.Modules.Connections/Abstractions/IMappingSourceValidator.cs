using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>映射专用源读取；只接受已固定目录和类型化定义，不接受SQL。</summary>
public interface IMappingSourceValidator
{
    /// <summary>正文读取前验证真实源列SELECT许可与目录；不读取业务行。</summary>
    Task VerifyAccessAsync(PgConnectionProfile profile, string secret, CatalogSnapshotView snapshot,
        MappingDefinition mapping, ResourceScope scope, CancellationToken cancellationToken, CatalogSnapshotView? originSnapshot = null);

    /// <summary>在一个只读可重复读事务内校验目录、源ACL并读取完整有界集合。</summary>
    /// <param name="profile">服务器限定的PG连接配置。</param>
    /// <param name="secret">当前绑定版本的内存凭据。</param>
    /// <param name="snapshot">正式保存的不可变目录。</param>
    /// <param name="mapping">固定映射定义。</param>
    /// <param name="scope">全部请求厂区，不得采样裁剪。</param>
    /// <param name="cancellationToken">共享总期限及取消。</param>
    /// <param name="originSnapshot">历史定义原目录，用于当前目录兼容性逐字段核验。</param>
    /// <returns>仅内存中的完整源集合和实测证据，不可直接发送给UI。</returns>
    Task<MappingSourceObservation> ReadAsync(PgConnectionProfile profile, string secret, CatalogSnapshotView snapshot,
        MappingDefinition mapping, ResourceScope scope, CancellationToken cancellationToken, CatalogSnapshotView? originSnapshot = null);
}

/// <summary>源单元格使用原生类型及精确字符串，不经double丢精度。</summary>
public sealed record MappingSourceCell
{
    /// <summary>固定目录原生类型。</summary>
    public required string NativeType { get; init; }

    /// <summary>精确规范值；数据库null保留null，不转换成空字符串或零。</summary>
    public required string? Value { get; init; }
}

/// <summary>单张注册表的完整限定行，未经脱敏不离开验证器。</summary>
public sealed record MappingSourceTable
{
    /// <summary>精确快照数据集引用。</summary>
    public required MappingDatasetRef Dataset { get; init; }

    /// <summary>完整限定集合，不能把LIMIT哨兵截断后称完整。</summary>
    public required Dictionary<string, MappingSourceCell>[] Rows { get; init; }
}

/// <summary>一次真实只读源事务的内存证据，不持久化原始业务行。</summary>
public sealed record MappingSourceObservation
{
    /// <summary>实际读取表和完整限定行。</summary>
    public required MappingSourceTable[] Tables { get; init; }

    /// <summary>原目录算法生成的当前指纹。</summary>
    public required string CatalogFingerprint { get; init; }

    /// <summary>观察源事务的固定标识，只用于证据散列。</summary>
    public required string TransactionSnapshot { get; init; }

    /// <summary>实测开始时间。</summary>
    public required DateTimeOffset StartedAtUtc { get; init; }

    /// <summary>实测结束时间。</summary>
    public required DateTimeOffset FinishedAtUtc { get; init; }

    /// <summary>当前执行器已验证的TLS、只读角色及逐字段ACL。</summary>
    public required bool SecurityVerified { get; init; }
}
