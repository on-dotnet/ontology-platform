using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>连接纵向用例唯一入口；元数据命令与治理审计共享短PG事务。</summary>
public sealed partial class ConnectionApplicationService : IConnectionRequestHandler
{
    /// <summary>模块独立上下文工厂。</summary>
    private readonly IDbContextFactory<ConnectionsDbContext> factory;

    /// <summary>治理模块拥有的同事务审计。</summary>
    private readonly ITransactionalAuditWriter audit;

    /// <summary>唯一真实源适配器。</summary>
    private readonly IPgSourceAdapter adapter;

    /// <summary>只在服务端使用的AEAD服务。</summary>
    private readonly ConnectionSecretCipher cipher;

    /// <summary>后台任务实时身份重验。</summary>
    private readonly IConnectionSessionAuthority authority;

    /// <summary>服务器明确批准的空public合成例外，默认关闭。</summary>
    private readonly bool allowEmptyPublic;

    /// <summary>统一可测试UTC时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>依赖均由Master组合，不跨模块写治理表。</summary>
    public ConnectionApplicationService(IDbContextFactory<ConnectionsDbContext> factory, ITransactionalAuditWriter audit,
        IPgSourceAdapter adapter, ConnectionSecretCipher cipher, IConnectionSessionAuthority authority, TimeProvider clock, PgAdapterOptions options)
    {
        this.factory = factory;
        this.audit = audit;
        this.adapter = adapter;
        this.cipher = cipher;
        this.authority = authority;
        this.clock = clock;
        // 同步复制服务器上限；只有精确B显式允许空public，默认A不受后续数组修改影响。
        var serverSchemas = options.AllowedSchemas?.ToArray();
        allowEmptyPublic = serverSchemas switch
        {
            ["production"] => false,
            ["production", "public"] => true,
            _ => throw new PgSourceException("connection_network_forbidden")
        };
    }

    /// <summary>执行固定操作并重新检查身份角色；未来传输不能绕过HTTP已做的字段规则。</summary>
    public async Task<ConnectionReply> HandleAsync(ConnectionInvocation invocation, CancellationToken token)
    {
        DemandActor(invocation.Actor, invocation.Operation is not ("list" or "get" or "probe" or "job" or "catalogs" or "catalog"));
        if (invocation.Body is not null) G4ConnectionRules.Validate(invocation.Body);
        return invocation.Operation switch
        {
            "list" => await ListAsync(invocation, token),
            "get" => await GetAsync(invocation, token),
            "intake" => await IntakeAsync(invocation, token),
            "create" => await CreateAsync(invocation, token),
            "patch" or "rotate" or "disable" => await EditAsync(invocation, token),
            "draft-test" or "test" => await ProbeAsync(invocation, token),
            "probe" => await ReadProbeAsync(invocation, token),
            "enable" => await EnableAsync(invocation, token),
            "discover" => await DiscoverAsync(invocation, token),
            "job" or "cancel" => await JobAsync(invocation, token),
            "catalogs" or "catalog" => await CatalogAsync(invocation, token),
            _ => throw new SemanticOperationException(422, "connection_profile_invalid")
        };
    }

    /// <summary>序列化唯一公共DTO，秘密正文仅用于内存HMAC。</summary>
    internal static string Encode<T>(T value) => JsonSerializer.Serialize(value, G4ConnectionJson.Options);

    /// <summary>读取服务端自己持久化的严格DTO。</summary>
    internal static T Decode<T>(string value) => JsonSerializer.Deserialize<T>(value, G4ConnectionJson.Options)!;

    /// <summary>非秘密内容的稳定SHA256。</summary>
    internal static string Hash(string value) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));

    /// <summary>范围的集合顺序规范化，避免等价请求产生不同资源身份。</summary>
    internal static ResourceScope Normalize(ResourceScope scope) => scope with { SiteIds = scope.SiteIds.Order(StringComparer.Ordinal).ToArray() };

    /// <summary>从持久行取得真实资源授权范围。</summary>
    internal static ResourceScope Scope(ConnectionRecord row) => new() { OrganizationId = row.OrganizationId, SiteIds = row.SiteIds };

    /// <summary>只允许真实operator写入，读需operator或auditor；不信任客户端角色。</summary>
    internal static void DemandActor(ActorContext actor, bool write)
    {
        if (string.IsNullOrWhiteSpace(actor.SubjectId) || string.IsNullOrWhiteSpace(actor.OrganizationId)
            || !actor.Roles.Contains("platform.operator") && (write || !actor.Roles.Contains("platform.auditor")))
            throw new SemanticOperationException(403, "connection_scope_forbidden");
    }

    /// <summary>完整厂区必须属于同一可信组织，交集不足不静默缩减请求。</summary>
    internal static void DemandScope(ActorContext actor, ResourceScope scope)
    {
        G4ConnectionRules.Scope(scope);
        if (scope.OrganizationId != actor.OrganizationId || scope.SiteIds.Any(site => !actor.SiteIds.Contains(site, StringComparer.Ordinal)))
            throw new SemanticOperationException(403, "connection_scope_forbidden");
    }

    /// <summary>唯一受控PG运行子集，其他配置只能用于表单预览。</summary>
    private PgConnectionProfile Pg(ConnectionConfig config)
    {
        G4ConnectionRules.Config(config);
        if (config is not PgConnectionConfig pg) throw new SemanticOperationException(422, "connector_not_enabled");
        if (pg.Profile.SslMode != "VerifyFull") throw new SemanticOperationException(422, "connection_tls_untrusted");
        if (pg.Profile.Host != "pg-source" || pg.Profile.Port != 5432 || pg.Profile.Database != "fixture"
            || pg.Profile.Username != "fixture_reader" || (pg.Profile.AllowedSchemas is not ["production"] && !(allowEmptyPublic && pg.Profile.AllowedSchemas is ["production", "public"])))
            throw new SemanticOperationException(403, "connection_network_forbidden");
        return pg.Profile;
    }

    /// <summary>资源不存在或范围不符统一拒绝，未授权调用不会得到资源详情。</summary>
    private static async Task<ConnectionRecord> FindAsync(ConnectionsDbContext db, ActorContext actor, string? id, CancellationToken token)
    {
        // 组织在数据库过滤，跨组织记录不进入内存。
        var row = await db.Connections.SingleOrDefaultAsync(value => value.Id == id && value.OrganizationId == actor.OrganizationId, token)
            ?? throw new SemanticOperationException(403, "connection_scope_forbidden");
        DemandScope(actor, Scope(row));
        return row;
    }

    /// <summary>在同物理PG事务内对准确命令或连接键串行化，不使用进程内锁代持久CAS。</summary>
    internal static Task LockAsync(ConnectionsDbContext db, string key, CancellationToken token)
        => db.Database.ExecuteSqlInterpolatedAsync($"SELECT pg_advisory_xact_lock(hashtextextended({key}, 0))", token);

    /// <summary>强ETag绑定真实资源修订与规范化配置内容。</summary>
    internal static string Etag(ConnectionRecord row) => $"\"{row.Revision}-{row.ConfigHash}\"";

    /// <summary>仅没有幂等回执的新命令执行CAS，旧命令重放不重复副作用。</summary>
    private static void Cas(ConnectionInvocation call, ConnectionRecord row, CommandContext command)
    {
        if (call.Etag is null) throw new SemanticOperationException(428, "revision_required");
        if (!System.Text.RegularExpressions.Regex.IsMatch(call.Etag, "^\"[1-9][0-9]*-[0-9a-f]{64}\"$"))
            throw new SemanticOperationException(400, "invalid_revision");
        if (call.Etag != Etag(row) || command.ExpectedRevision != row.Revision)
            throw new SemanticOperationException(409, "connection_version_conflict");
    }

    /// <summary>包含显示名和范围的配置散列，任何编辑均使旧测试不可重新使用。</summary>
    private static void Rehash(ConnectionRecord row) => row.ConfigHash = Hash(Encode(new { row.DisplayName, Scope = Normalize(Scope(row)), Config = Decode<ConnectionConfig>(row.ConfigJson) }));

    /// <summary>不可变原回执的当前访问授权仍必须重验。</summary>
    private async Task<ConnectionReply?> ReplayAsync(ConnectionsDbContext db, ConnectionInvocation call, string key, string requestHash, Type type, CancellationToken token)
    {
        // 回执只能由完整actor/组织/操作/目标键定位，不能跨scope扫描猜测。
        var previous = await db.ConnectionCommands.AsNoTracking().SingleOrDefaultAsync(value => value.Id == key, token);
        if (previous is null) return null;
        DemandScope(call.Actor, Decode<ResourceScope>(previous.ScopeJson));
        DemandScope(call.Actor, Decode<ResourceScope>(previous.ResultScopeJson));
        if (previous.RequestHash != requestHash) throw new SemanticOperationException(409, "connection_version_conflict");
        if (previous.StatusCode == 102) throw new SemanticOperationException(previous.CreatedAtUtc.AddSeconds(20) <= clock.GetUtcNow() ? 503 : 409, "connection_source_unavailable");
        if (previous.ErrorCode is not null) throw new SemanticOperationException(previous.StatusCode, previous.ErrorCode);
        // 专用签发回执只能在未绑定且未过期期间恢复引用。
        if (type == typeof(SecretIntakeReceipt))
        {
            // Ref不从任何普通GET或连接响应公开。
            var receipt = Decode<SecretIntakeReceipt>(previous.ReceiptJson);
            _ = await UnboundSecretAsync(db, call.Actor, receipt.SecretRef, Decode<ResourceScope>(previous.ScopeJson), token);
        }
        return new ConnectionReply { Value = JsonSerializer.Deserialize(previous.ReceiptJson, type, G4ConnectionJson.Options)!, Etag = previous.Etag, StatusCode = previous.StatusCode };
    }

    /// <summary>在短事务内执行唯一命令、固定原回执和治理审计。</summary>
    private async Task<ConnectionReply> CommandAsync<T>(ConnectionInvocation call, CommandContext command, string action, int status,
        Func<ConnectionsDbContext, CancellationToken, Task<(T Value, ResourceScope Before, ResourceScope After, string? Etag)>> execute, CancellationToken token)
    {
        // 稳定键不会随资源scope编辑改变，正文及前后scope仍完整绑定。
        var key = CommandKey(call, command);
        // 包括If-Match和完整正文的用途HMAC，不存低熵秘密的裸散列。
        var requestHash = cipher.RequestHash(Encode(new { call.Body, call.Etag }));
        await using var db = await factory.CreateDbContextAsync(token);
        await using var transaction = await db.Database.BeginTransactionAsync(token);
        await LockAsync(db, key, token);
        // 已成功命令优先重放，再处理新命令CAS。
        var replay = await ReplayAsync(db, call, key, requestHash, typeof(T), token);
        if (replay is not null) return replay;
        if (call.Id is not null) await LockAsync(db, "connection:" + call.Id, token);
        // 每个用例在锁内重新查询当前资源，不使用客户端旧投影。
        var result = await execute(db, token);
        DemandScope(call.Actor, result.Before);
        DemandScope(call.Actor, result.After);
        db.ConnectionCommands.Add(new ConnectionCommandRecord
        {
            Id = key,
            RequestHash = requestHash,
            ScopeJson = Encode(result.Before),
            ResultScopeJson = Encode(result.After),
            ReceiptJson = Encode(result.Value),
            CreatedAtUtc = clock.GetUtcNow(),
            Etag = result.Etag,
            StatusCode = status
        });
        await SaveAuditAsync(db, call.Actor, action, call.Id ?? "new", result.After, token);
        await transaction.CommitAsync(token);
        return new ConnectionReply { Value = result.Value!, Etag = result.Etag, StatusCode = status };
    }

    /// <summary>幂等查找键不携敏感原始输入，也不依赖可能已变化的scope。</summary>
    private static string CommandKey(ConnectionInvocation call, CommandContext command)
        => Hash(Encode(new { call.Actor.SubjectId, call.Actor.OrganizationId, call.Operation, call.Id, call.ChildId, command.IdempotencyKey }));

    /// <summary>业务Save与Governance共同提交，审计失败使全部变更回滚。</summary>
    internal async Task SaveAuditAsync(ConnectionsDbContext db, ActorContext actor, string action, string resource, ResourceScope scope, CancellationToken token)
    {
        await db.SaveChangesAsync(token);
        await audit.WriteAsync(actor, new AuditCommand { Action = action, Resource = "connection:" + resource, Outcome = "allowed", Scope = scope },
            db.Database.GetDbConnection(), db.Database.CurrentTransaction!.GetDbTransaction(), token);
    }

    /// <summary>有资格启用的报告必须为完整五阶段、当前版本和有效期限。</summary>
    private async Task<bool> FreshAsync(ConnectionsDbContext db, ConnectionRecord row, CancellationToken token)
    {
        if (row.State == "DISABLED" || row.LastProbeId is null) return false;
        // 源报告不可变，是否stale是依据当前事实的投影。
        var probe = await db.ConnectionProbes.AsNoTracking().SingleOrDefaultAsync(value => value.Id == row.LastProbeId, token);
        if (probe is null || probe.ConfigHash != row.ConfigHash || probe.SecretVersion != row.SecretVersion || probe.ExpiresAtUtc <= clock.GetUtcNow()) return false;
        // TEST_OK与五阶段全PASS同时成立，不能只信状态文本。
        var report = Decode<ConnectionProbeView>(probe.ReportJson);
        return report.Status == "TEST_OK" && report.Stages.Length == 5 && report.Stages.All(stage => stage.Status == "PASS");
    }

    /// <summary>operator可见非秘密配置，auditor只得到固定脱敏只读投影。</summary>
    private async Task<ConnectionView> ViewAsync(ConnectionsDbContext db, ActorContext actor, ConnectionRecord row, CancellationToken token)
    {
        // 所有已存连接本阶段均是经过验证的PG配置。
        var config = Decode<ConnectionConfig>(row.ConfigJson);
        if (!actor.Roles.Contains("platform.operator") && config is PgConnectionConfig pg)
            config = pg with { Profile = pg.Profile with { Host = "redacted", Database = "redacted", Username = "redacted", AllowedSchemas = ["redacted"] } };
        return new ConnectionView
        {
            Id = row.Id,
            DisplayName = row.DisplayName,
            Scope = Scope(row),
            Config = config,
            ConfigRevision = row.Revision,
            State = row.State,
            SecretConfigured = true,
            SecretVersion = row.SecretVersion,
            ProbeFresh = await FreshAsync(db, row, token),
            LastProbeId = row.LastProbeId,
            UpdatedAtUtc = row.UpdatedAtUtc
        };
    }

    /// <summary>分页游标只编码固定ID，非法格式不能变为SQL。</summary>
    private static string Cursor(string? cursor)
    {
        if (string.IsNullOrEmpty(cursor)) return string.Empty;
        try
        {
            // 仅32位随机ID可作有界键集分页。
            var value = Encoding.UTF8.GetString(Convert.FromBase64String(cursor));
            if (value.Length == 32 && value.All(char.IsAsciiHexDigit)) return value;
        }
        catch (FormatException) { }
        throw new SemanticOperationException(422, "connection_profile_invalid");
    }

    /// <summary>授权先在PG过滤，再进行50项键集分页。</summary>
    private async Task<ConnectionReply> ListAsync(ConnectionInvocation call, CancellationToken token)
    {
        // 不同连接类型尚无已保存对象，合法非PG筛选返回真实空集合。
        if (!string.IsNullOrEmpty(call.Type) && call.Type is not ("POSTGRESQL" or "ORACLE" or "DORIS" or "TDENGINE" or "WEB_API"))
            throw new SemanticOperationException(422, "connection_profile_invalid");
        if (!string.IsNullOrEmpty(call.State) && call.State is not ("DRAFT" or "ACTIVE" or "DISABLED"))
            throw new SemanticOperationException(422, "connection_profile_invalid");
        await using var db = await factory.CreateDbContextAsync(token);
        // 游标是非敏感随机主键，不包含数据库地址或秘密引用。
        var after = Cursor(call.Cursor);
        // 资源完整site集合必须被当前actor覆盖。
        var query = db.Connections.Where(row => row.OrganizationId == call.Actor.OrganizationId && row.SiteIds.All(site => call.Actor.SiteIds.Contains(site)));
        if (!string.IsNullOrEmpty(call.State)) query = query.Where(row => row.State == call.State);
        if (!string.IsNullOrEmpty(call.Type) && call.Type != "POSTGRESQL") query = query.Where(row => false);
        if (after.Length > 0) query = query.Where(row => string.Compare(row.Id, after) > 0);
        // 多取一项仅用于判断下一页，不返回越界对象。
        var rows = await query.OrderBy(row => row.Id).Take(51).ToArrayAsync(token);
        // 单项映射仍检查真实Probe新鲜度。
        var items = new List<ConnectionView>();
        foreach (var row in rows.Take(50)) items.Add(await ViewAsync(db, call.Actor, row, token));
        return new ConnectionReply { Value = new ConnectionListPage { Items = items.ToArray(), NextCursor = rows.Length > 50 ? Convert.ToBase64String(Encoding.UTF8.GetBytes(rows[49].Id)) : null } };
    }

    /// <summary>刷新读取权威存储状态与当前ETag。</summary>
    private async Task<ConnectionReply> GetAsync(ConnectionInvocation call, CancellationToken token)
    {
        await using var db = await factory.CreateDbContextAsync(token);
        // 先组织与资源范围授权，再构造任何公开字段。
        var row = await FindAsync(db, call.Actor, call.Id, token);
        return new ConnectionReply { Value = await ViewAsync(db, call.Actor, row, token), Etag = Etag(row) };
    }
}
