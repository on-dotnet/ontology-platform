using System.Text.Json;
using System.Text.Json.Serialization;

namespace OntologyPlatform.Contracts;

/// <summary>五类连接配置的唯一判别联合，M1仅PostgreSQL具备运行能力。</summary>
[JsonPolymorphic(TypeDiscriminatorPropertyName = "type")]
[JsonDerivedType(typeof(PgConnectionConfig), "POSTGRESQL")]
[JsonDerivedType(typeof(OracleConnectionConfig), "ORACLE")]
[JsonDerivedType(typeof(DorisConnectionConfig), "DORIS")]
[JsonDerivedType(typeof(TdengineConnectionConfig), "TDENGINE")]
[JsonDerivedType(typeof(WebApiConnectionConfig), "WEB_API")]
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public abstract record ConnectionConfig;

/// <summary>Pg类型化配置分支，禁止夹带连接串或身份字段。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record PgConnectionConfig : ConnectionConfig
{
    /// <summary>当前类型唯一的连接参数。</summary>
    public required PgConnectionProfile Profile { get; init; }
}

/// <summary>Oracle类型化配置分支，禁止夹带连接串或身份字段。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record OracleConnectionConfig : ConnectionConfig
{
    /// <summary>当前类型唯一的连接参数。</summary>
    public required OracleConnectionProfile Profile { get; init; }
}

/// <summary>Doris类型化配置分支，禁止夹带连接串或身份字段。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record DorisConnectionConfig : ConnectionConfig
{
    /// <summary>当前类型唯一的连接参数。</summary>
    public required DorisConnectionProfile Profile { get; init; }
}

/// <summary>Tdengine类型化配置分支，禁止夹带连接串或身份字段。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record TdengineConnectionConfig : ConnectionConfig
{
    /// <summary>当前类型唯一的连接参数。</summary>
    public required TdengineConnectionProfile Profile { get; init; }
}

/// <summary>WebApi类型化配置分支，禁止夹带连接串或身份字段。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record WebApiConnectionConfig : ConnectionConfig
{
    /// <summary>当前类型唯一的连接参数。</summary>
    public required WebApiConnectionProfile Profile { get; init; }
}

/// <summary>PostgreSQL受控连接配置，证书信任仅来自服务器。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record PgConnectionProfile
{
    /// <summary>源服务受控主机名。</summary>
    public required string Host { get; init; }

    /// <summary>源服务端口。</summary>
    public required int Port { get; init; }

    /// <summary>目标数据库名称。</summary>
    public required string Database { get; init; }

    /// <summary>只读源账号。</summary>
    public required string Username { get; init; }

    /// <summary>TLS身份验证模式。</summary>
    public required string SslMode { get; init; }

    /// <summary>允许发现的Schema集合。</summary>
    public required string[] AllowedSchemas { get; init; }
}

/// <summary>Oracle强制TLS的类型化配置，执行目标由服务端再次限定。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record OracleConnectionProfile
{
    /// <summary>服务器名称。</summary>
    public required string Host { get; init; }

    /// <summary>服务端口。</summary>
    public required int Port { get; init; }

    /// <summary>Oracle服务名称。</summary>
    public required string ServiceName { get; init; }

    /// <summary>账号名称。</summary>
    public required string Username { get; init; }

    /// <summary>是否要求加密。</summary>
    public required bool Tls { get; init; }

    /// <summary>允许的Owner集合。</summary>
    public required string[] AllowedOwners { get; init; }
}

/// <summary>Doris配置预览，本阶段不可连接。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record DorisConnectionProfile
{
    /// <summary>前端节点名称。</summary>
    public required string FeHost { get; init; }

    /// <summary>查询端口。</summary>
    public required int QueryPort { get; init; }

    /// <summary>目录名称。</summary>
    public required string Catalog { get; init; }

    /// <summary>数据库名称。</summary>
    public required string Database { get; init; }

    /// <summary>账号名称。</summary>
    public required string Username { get; init; }

    /// <summary>是否要求加密。</summary>
    public required bool Tls { get; init; }
}

/// <summary>TDengine配置预览，本阶段不可连接。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record TdengineConnectionProfile
{
    /// <summary>受控WebSocket地址。</summary>
    public required string WsUrl { get; init; }

    /// <summary>数据库名称。</summary>
    public required string Database { get; init; }

    /// <summary>时间精度。</summary>
    public required string TimePrecision { get; init; }

    /// <summary>时间区域。</summary>
    public required string? TimeZone { get; init; }
}

/// <summary>Web API配置预览，本阶段不发送请求。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record WebApiConnectionProfile
{
    /// <summary>已批准源站。</summary>
    public required string BaseOrigin { get; init; }

    /// <summary>已批准操作标识。</summary>
    public required string OperationId { get; init; }

    /// <summary>只读HTTP方法。</summary>
    public required string Method { get; init; }

    /// <summary>已批准相对路径。</summary>
    public required string ApprovedPath { get; init; }

    /// <summary>认证方式。</summary>
    public required string Authentication { get; init; }

    /// <summary>分页策略。</summary>
    public required string Pagination { get; init; }

    /// <summary>服务器网络策略引用。</summary>
    public required string HostPolicyRef { get; init; }
}

/// <summary>创建草稿，禁止自动启用。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record ConnectionCreateRequest
{
    /// <summary>连接显示名称。</summary>
    public required string DisplayName { get; init; }

    /// <summary>客户端申请的组织厂区子集。</summary>
    public required ResourceScope ScopeSelection { get; init; }

    /// <summary>唯一类型化配置。</summary>
    public required ConnectionConfig Config { get; init; }

    /// <summary>仅专用密钥入口签发的引用。</summary>
    public required string? SecretRef { get; init; }

    /// <summary>创建修订为零的命令。</summary>
    public required CommandContext Command { get; init; }
}

/// <summary>CAS编辑非秘密配置，成功后旧Probe失效。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record ConnectionPatchRequest
{
    /// <summary>新的显示名称。</summary>
    public string? DisplayName { get; init; }

    /// <summary>新的授权范围子集。</summary>
    public ResourceScope? ScopeSelection { get; init; }

    /// <summary>新的类型化配置。</summary>
    public ConnectionConfig? Config { get; init; }

    /// <summary>包含正修订的编辑命令。</summary>
    public required CommandContext Command { get; init; }
}

/// <summary>专用敏感入口请求，禁止普通日志序列化。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record ConnectionSecretIntakeRequest
{
    /// <summary>仅服务器内存处理的合成凭据。</summary>
    public required string SecretValue { get; init; }

    /// <summary>密钥使用范围。</summary>
    public required ResourceScope ScopeSelection { get; init; }

    /// <summary>唯一批准的凭据用途。</summary>
    public required string Purpose { get; init; }

    /// <summary>密钥签发命令。</summary>
    public required CommandContext Command { get; init; }
}

/// <summary>只返回一次短寿命引用，不回显密钥。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record SecretIntakeReceipt
{
    /// <summary>随机不透明引用。</summary>
    public required string SecretRef { get; init; }

    /// <summary>未绑定引用过期时间。</summary>
    public required DateTimeOffset ExpiresAtUtc { get; init; }

    /// <summary>允许绑定次数。</summary>
    public required int UsageLimit { get; init; }

    /// <summary>凭据版本。</summary>
    public required long CredentialVersion { get; init; }
}

/// <summary>未保存草稿的真实只读探测请求。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record ConnectionDraftProbeRequest
{
    /// <summary>探测所选授权范围。</summary>
    public required ResourceScope ScopeSelection { get; init; }

    /// <summary>待测试的唯一配置。</summary>
    public required ConnectionConfig Config { get; init; }

    /// <summary>未绑定且有效的秘密引用。</summary>
    public required string SecretRef { get; init; }

    /// <summary>探测幂等命令。</summary>
    public required CommandContext Command { get; init; }
}

/// <summary>原子CAS轮换凭据并撤销旧探测。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record ConnectionRotateSecretRequest
{
    /// <summary>新签发的未绑定秘密引用。</summary>
    public required string SecretRef { get; init; }

    /// <summary>正修订轮换命令。</summary>
    public required CommandContext Command { get; init; }
}

/// <summary>连接与发现任务的版本化变更命令。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record ConnectionMutationCommand
{
    /// <summary>包含幂等键与当前修订的命令。</summary>
    public required CommandContext Command { get; init; }
}

/// <summary>不包含秘密引用或密文的连接视图。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record ConnectionView
{
    /// <summary>连接标识。</summary>
    public required string Id { get; init; }

    /// <summary>显示名称。</summary>
    public required string DisplayName { get; init; }

    /// <summary>已授权资源范围。</summary>
    public required ResourceScope Scope { get; init; }

    /// <summary>非秘密受控配置。</summary>
    public required ConnectionConfig Config { get; init; }

    /// <summary>资源CAS修订。</summary>
    public required long ConfigRevision { get; init; }

    /// <summary>DRAFT或ACTIVE或DISABLED。</summary>
    public required string State { get; init; }

    /// <summary>凭据是否已绑定。</summary>
    public required bool SecretConfigured { get; init; }

    /// <summary>当前凭据版本。</summary>
    public required long SecretVersion { get; init; }

    /// <summary>当前完整探测是否仍有效。</summary>
    public required bool ProbeFresh { get; init; }

    /// <summary>最近探测标识。</summary>
    public required string? LastProbeId { get; init; }

    /// <summary>最近更新时刻。</summary>
    public required DateTimeOffset UpdatedAtUtc { get; init; }
}

/// <summary>真实探测的一个阶段，未观测不能标通过。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record ConnectionProbeStage
{
    /// <summary>NETWORK或TLS或AUTH或READ_ONLY或METADATA。</summary>
    public required string Name { get; init; }

    /// <summary>PASS或FAIL或NOT_VERIFIED或NOT_RUN。</summary>
    public required string Status { get; init; }

    /// <summary>阶段实际耗时毫秒。</summary>
    public required long DurationMs { get; init; }

    /// <summary>固定脱敏诊断码。</summary>
    public required string? DiagnosticCode { get; init; }
}

/// <summary>不可变探测报告及当前失效投影。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record ConnectionProbeView
{
    /// <summary>探测标识。</summary>
    public required string ProbeId { get; init; }

    /// <summary>已保存连接标识，草稿为空。</summary>
    public required string? ConnectionId { get; init; }

    /// <summary>配置绑定SHA256。</summary>
    public required string ConfigHash { get; init; }

    /// <summary>使用的凭据版本。</summary>
    public required long SecretVersion { get; init; }

    /// <summary>探测授权范围。</summary>
    public required ResourceScope Scope { get; init; }

    /// <summary>探测状态，独立于连接状态。</summary>
    public required string Status { get; init; }

    /// <summary>五个固定阶段。</summary>
    public required ConnectionProbeStage[] Stages { get; init; }

    /// <summary>开始时刻。</summary>
    public required DateTimeOffset StartedAtUtc { get; init; }

    /// <summary>完成时刻。</summary>
    public required DateTimeOffset? CompletedAtUtc { get; init; }

    /// <summary>有效性截止。</summary>
    public required DateTimeOffset ExpiresAtUtc { get; init; }

    /// <summary>脱敏关联标识。</summary>
    public required string TraceId { get; init; }

    /// <summary>是否已经失效。</summary>
    public required bool Stale { get; init; }
}

/// <summary>原生列类型与精度元数据，不包含业务行。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record CatalogField
{
    /// <summary>列名称。</summary>
    public required string Name { get; init; }

    /// <summary>保真原生类型。</summary>
    public required string NativeType { get; init; }

    /// <summary>是否允许空值。</summary>
    public required bool Nullable { get; init; }

    /// <summary>列序号。</summary>
    public required int Ordinal { get; init; }

    /// <summary>原生精度。</summary>
    public required int? Precision { get; init; }

    /// <summary>原生小数位。</summary>
    public required int? Scale { get; init; }

    /// <summary>Oracle专属类型信息；旧连接器和旧快照不输出该字段。</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public OracleColumnMetadata? OracleMetadata { get; init; }

}

/// <summary>Oracle数据字典的保真列元数据，不读取列值或默认表达式。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record OracleColumnMetadata
{
    /// <summary>字典字符长度语义的精确可空值。</summary>
    private string? charSemantics;

    /// <summary>经精确枚举检查的时区语义，不以缺省值冒充已知。</summary>
    private string timeZoneKind = null!;

    /// <summary>经精确枚举检查的支持状态，不以缺省值冒充支持。</summary>
    private string supportStatus = null!;

    /// <summary>用户定义类型的原始owner；内置类型为null。</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.Never)]
    public required string? DataTypeOwner { get; init; }

    /// <summary>字典声明的字节长度；缺失不推断为零。</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.Never)]
    public required int? ByteLength { get; init; }

    /// <summary>字符长度，与字节长度分列。</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.Never)]
    public required int? CharLength { get; init; }

    /// <summary>BYTE或CHAR语义；非字符列为null。</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.Never)]
    public required string? CharSemantics
    {
        get => charSemantics;
        init => charSemantics = value is null or "BYTE" or "CHAR" ? value
            : throw new System.Text.Json.JsonException("Oracle字符长度语义无效。");
    }

    /// <summary>TIMESTAMP小数秒位数；缺失保留null。</summary>
    [JsonIgnore(Condition = JsonIgnoreCondition.Never)]
    public required int? FractionalSecondsPrecision { get; init; }

    /// <summary>显式时区类别，仅接受冻结的大写值，缺失或非法值拒绝解析。</summary>
    public required string TimeZoneKind
    {
        get => timeZoneKind;
        init => timeZoneKind = value is "NONE" or "WITH_TIME_ZONE" or "WITH_LOCAL_TIME_ZONE" or "UNKNOWN"
            ? value : throw new System.Text.Json.JsonException("Oracle时区类别无效。");
    }

    /// <summary>显式支持状态；旧快照缺省整个元数据时保持未知。</summary>
    public required string SupportStatus
    {
        get => supportStatus;
        init => supportStatus = value is "SUPPORTED" or "METADATA_ONLY" or "UNSUPPORTED"
            ? value : throw new System.Text.Json.JsonException("Oracle类型支持状态无效。");
    }
}

/// <summary>源角色和允许Schema交集内的可见对象。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record CatalogObject
{
    /// <summary>Schema名称。</summary>
    public required string Schema { get; init; }

    /// <summary>对象名称。</summary>
    public required string Name { get; init; }

    /// <summary>TABLE或VIEW。</summary>
    public required string Kind { get; init; }

    /// <summary>可见字段集合。</summary>
    public required CatalogField[] Fields { get; init; }
}

/// <summary>不可变目录快照及当前过期状态投影。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record CatalogSnapshotView
{
    /// <summary>快照标识。</summary>
    public required string SnapshotId { get; init; }

    /// <summary>来源连接标识。</summary>
    public required string ConnectionId { get; init; }

    /// <summary>捕获时配置修订。</summary>
    public required long ConfigRevision { get; init; }

    /// <summary>捕获时凭据版本。</summary>
    public required long SecretVersion { get; init; }

    /// <summary>捕获范围。</summary>
    public required ResourceScope Scope { get; init; }

    /// <summary>排序规范化内容SHA256。</summary>
    public required string SchemaFingerprint { get; init; }

    /// <summary>捕获时间。</summary>
    public required DateTimeOffset CapturedAtUtc { get; init; }

    /// <summary>READY或PARTIAL或STALE。</summary>
    public required string Status { get; init; }

    /// <summary>授权可见元数据。</summary>
    public required CatalogObject[] Objects { get; init; }
}

/// <summary>可恢复且可取消的持久发现任务。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record CatalogDiscoveryJobView
{
    /// <summary>任务标识。</summary>
    public required string JobId { get; init; }

    /// <summary>来源连接。</summary>
    public required string ConnectionId { get; init; }

    /// <summary>请求配置修订。</summary>
    public required long ConfigRevision { get; init; }

    /// <summary>持久任务状态。</summary>
    public required string Status { get; init; }

    /// <summary>创建时间。</summary>
    public required DateTimeOffset CreatedAtUtc { get; init; }

    /// <summary>终态时间。</summary>
    public required DateTimeOffset? CompletedAtUtc { get; init; }

    /// <summary>产生的快照标识。</summary>
    public required string? SnapshotId { get; init; }

    /// <summary>脱敏关联标识。</summary>
    public required string TraceId { get; init; }
}

/// <summary>授权过滤后的有界连接分页。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record ConnectionListPage
{
    /// <summary>当前页面。</summary>
    public required ConnectionView[] Items { get; init; }

    /// <summary>下一页不透明游标。</summary>
    public required string? NextCursor { get; init; }
}

/// <summary>授权过滤后的目录历史分页。</summary>
[JsonUnmappedMemberHandling(JsonUnmappedMemberHandling.Disallow)]
public sealed record CatalogSnapshotListPage
{
    /// <summary>当前页面。</summary>
    public required CatalogSnapshotView[] Items { get; init; }

    /// <summary>下一页不透明游标。</summary>
    public required string? NextCursor { get; init; }
}

/// <summary>M1独立严格JSON边界，不改变G2历史序列化选项。</summary>
public static class G4ConnectionJson
{
    /// <summary>拒绝数字字符串、大小写别名和非空字段的null，未知字段由DTO拒绝。</summary>
    public static JsonSerializerOptions Options { get; } = new(JsonSerializerDefaults.Web)
    {
        NumberHandling = JsonNumberHandling.Strict,
        PropertyNameCaseInsensitive = false,
        RespectNullableAnnotations = true
    };
}
