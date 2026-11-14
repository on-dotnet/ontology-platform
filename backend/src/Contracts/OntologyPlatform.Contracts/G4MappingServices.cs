using System.Data.Common;

namespace OntologyPlatform.Contracts;

/// <summary>内部授权证明，绝不作为HTTP响应暴露会话引用。</summary>
public sealed record MappingAuthorizationProof
{
    /// <summary>当前可信主体及角色。</summary>
    public required ActorContext Actor { get; init; }

    /// <summary>服务器票据引用，只由宿主提取。</summary>
    public required string SessionReference { get; init; }

    /// <summary>完整资源范围。</summary>
    public required ResourceScope Scope { get; init; }

    /// <summary>此证明的唯一注册操作。</summary>
    public required string Permission { get; init; }

    /// <summary>源验证许可的精确连接，其他权限为空。</summary>
    public required string? ConnectionId { get; init; }

    /// <summary>源验证需要的全体数据集。</summary>
    public required string[] ObjectRefs { get; init; }

    /// <summary>源验证需要的全体字段。</summary>
    public required string[] FieldRefs { get; init; }

    /// <summary>捕获时组织授权版本。</summary>
    public required long AuthorizationEpoch { get; init; }

    /// <summary>不可延长的短期证明期限。</summary>
    public required DateTimeOffset ExpiresAtUtc { get; init; }
}

/// <summary>宿主负责解密票据，治理模块不依赖HTTP或认证SDK。</summary>
public interface IMappingSessionAuthority
{
    /// <summary>解密并核验票据中的固定主体，无法验证时失败关闭。</summary>
    /// <param name="protectedTicket">治理表读取的加密字节。</param>
    /// <param name="expected">预期主体、组织、厂区及角色。</param>
    /// <param name="now">统一UTC时钟。</param>
    /// <returns>当前票据与预期声明完全一致时为真。</returns>
    bool Matches(byte[] protectedTicket, ActorContext expected, DateTimeOffset now);
}

/// <summary>治理授权捕获与同物理事务复核，所有写者按组织锁顺序进入。</summary>
public interface IMappingAuthorizationAuthority
{
    /// <summary>以真实服务器会话和完整源白名单捕获当前短期证明。</summary>
    /// <param name="request">待捕获请求，版本零表示读取当前版本。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>经过数据库验证的不可延长期限证明。</returns>
    Task<MappingAuthorizationProof> CaptureAsync(MappingAuthorizationProof request, CancellationToken cancellationToken);

    /// <summary>锁组织、会话和授权并复核全部当前事实，不提交调用方事务。</summary>
    /// <param name="proof">此前捕获的固定输入。</param>
    /// <param name="connection">已打开的调用方连接。</param>
    /// <param name="transaction">同物理事务。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>授权完成；失败时抛出安全错误。</returns>
    Task DemandInTransactionAsync(MappingAuthorizationProof proof, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken);
}

/// <summary>当前有权请求的复核失败定位，传输层只公开固定code及检查ID。</summary>
public sealed class MappingActivationCheckException : Exception
{
    /// <summary>不拼接源异常或业务值，检查ID只来自服务器生成。</summary>
    public MappingActivationCheckException(string checkId, string code) : base("映射激活复核未通过。")
    {
        CheckId = checkId;
        Code = code;
    }

    /// <summary>已独立提交的检查原件ID。</summary>
    public string CheckId { get; }

    /// <summary>固定脱敏机器代码。</summary>
    public string Code { get; }
}
