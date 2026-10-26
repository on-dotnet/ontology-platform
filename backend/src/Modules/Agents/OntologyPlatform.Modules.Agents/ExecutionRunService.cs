using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Agents;

/// <summary>持久运行唯一用例；每次变更与治理审计共享真实PG事务。</summary>
public sealed class ExecutionRunService
{
    /// <summary>唯一合同序列化选项，入出均触发合同回调。</summary>
    internal static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);

    /// <summary>每个操作拥有短生命周期数据库连接。</summary>
    private readonly IDbContextFactory<AgentsDbContext> factory;

    /// <summary>治理拥有的同事务写入器。</summary>
    private readonly ITransactionalAuditWriter audit;

    /// <summary>创建时固定一次权威正式版本。</summary>
    private readonly IReleaseCatalog catalog;

    /// <summary>同一个正式查询能力注册及执行器。</summary>
    private readonly ISemanticGateway gateway;

    /// <summary>默认关闭的显式本地测试提供者开关。</summary>
    private readonly bool deterministicEnabled;

    /// <summary>可验证的UTC时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>只接收模块边界，不自行复制查询或跨模块表写入。</summary>
    public ExecutionRunService(IDbContextFactory<AgentsDbContext> factory, ITransactionalAuditWriter audit, IReleaseCatalog catalog, ISemanticGateway gateway, IConfiguration configuration, TimeProvider clock, IHostEnvironment? environment = null)
    {
        this.factory = factory;
        this.audit = audit;
        this.catalog = catalog;
        this.gateway = gateway;
        deterministicEnabled = environment?.IsDevelopment() == true && configuration.GetValue<bool>("Agents:EnableDeterministicHarness");
        this.clock = clock;
    }

    /// <summary>当前宿主仍为Development且明确启用harness时才允许worker执行。</summary>
    internal bool DeterministicEnabled => deterministicEnabled;

    /// <summary>验证提供者及受控计划、固定正式快照，原子提交运行与幂等回执。</summary>
    public async Task<ExecutionRun> CreateAsync(ActorContext actor, CreateRunRequest request, CancellationToken token)
    {
        DemandActor(actor);
        _ = Encode(request);
        DemandCommand(request.Command);
        // 散列完整请求，包含正文、计划、提供者及全部命令字段。
        var hash = Hash(Encode(request));
        // 每次调用使用自己的连接与事务，不持有跨外部调用的行锁。
        await using var database = await factory.CreateDbContextAsync(token);
        // 精确payload重试先定位同owner/组织的回执，随后必须重新授权完整持久scope。
        // 此路径不读取active、当前工具版本或模型配置，响应丢失后仍可恢复真实已提交事实。
        var prior = await database.Commands.AsNoTracking().Where(command => command.PayloadHash == hash
            && database.Runs.Any(run => run.RunId == command.RunId && run.OwnerSubjectId == actor.SubjectId && run.OrganizationId == actor.OrganizationId))
            .FirstOrDefaultAsync(token);
        if (prior is not null) return await ReplayAsync(database, actor, prior, hash, token);
        if (request.ProviderMode == ProviderMode.ApprovedModel || request.ProviderMode == ProviderMode.Deterministic && !deterministicEnabled)
            throw new SemanticOperationException(503, "provider_not_configured");
        if (Encoding.UTF8.GetByteCount(request.Prompt) > 256 * 1024 || request.Plan.TimeoutMs is < 100 or > 5000
            || request.Plan.Depth is < 1 or > 5 || request.Plan.MaxRows is < 1 or > 100
            || !gateway.GetCapabilities().Any(value => value.Id == request.Plan.CapabilityId && value.Version == request.Plan.CapabilityVersion))
            throw new SemanticOperationException(422, "run_plan_invalid");
        // 正式目录本身再次授权并验证真实不可变发布。
        var release = await catalog.ResolveAsync(actor, request.Plan.AssetId, request.Plan.ReleaseId, token);
        DemandScope(actor, release.Manifest.Scope);
        // 幂等键绑定正式资源的完整范围，不绑定可变化的调用者授权超集。
        var scopeKey = Hash(Encode(new ResourceScope { OrganizationId = release.Manifest.Scope.OrganizationId, SiteIds = release.Manifest.Scope.SiteIds.Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray() }));
        // 同scope同操作同键仍绑定完整payload；不同payload的重用明确409。
        var key = CommandKey(actor, "create:" + scopeKey, request.Command.IdempotencyKey);
        // 计划中的版本只能来自正式目录，不接受客户端快照。
        var plan = request.Plan with { ReleaseId = release.Manifest.Snapshot.ReleaseId };
        // 唯一服务器时间关联创建与初始状态。
        var now = clock.GetUtcNow();
        // 新运行的所有身份和范围均来源于服务器可信值。
        var row = new RunRecord
        {
            RunId = Guid.NewGuid().ToString("N"),
            OwnerSubjectId = actor.SubjectId,
            OrganizationId = release.Manifest.Scope.OrganizationId,
            SiteIds = release.Manifest.Scope.SiteIds.Order(StringComparer.Ordinal).Distinct(StringComparer.Ordinal).ToArray(),
            SnapshotJson = Encode(release.Manifest.Snapshot),
            ActorJson = Encode(actor),
            PlanJson = Encode(plan),
            SourcePrompt = request.Prompt,
            ProviderMode = request.ProviderMode == ProviderMode.Deterministic ? "deterministic" : "disabled",
            CreatedAtUtc = now,
            UpdatedAtUtc = now,
            TraceId = actor.TraceId
        };
        // 同幂等键的并发创建以PG advisory事务锁串行化，绝不依赖进程锁。
        await using var transaction = await database.Database.BeginTransactionAsync(token);
        await LockCommandAsync(database, key, token);
        prior = await database.Commands.AsNoTracking().SingleOrDefaultAsync(value => value.Key == key, token);
        if (prior is not null) return await ReplayAsync(database, actor, prior, hash, token);
        database.Runs.Add(row);
        // 保存真实初始回执，同payload重复返回这一回执。
        var result = Map(row);
        database.Commands.Add(new RunCommandRecord { Key = key, PayloadHash = hash, RunId = row.RunId, ReceiptJson = Encode(result) });
        await CommitAsync(database, actor, row, "execution.run.create", token);
        return result;
    }

    /// <summary>只列出owner及完整范围可访问的运行，不返回任何Prompt。</summary>
    public async Task<ExecutionRun[]> ListAsync(ActorContext actor, CancellationToken token)
    {
        DemandActor(actor);
        // 不跟踪只读记录，完整scope仍在服务端逐项校验。
        await using var database = await factory.CreateDbContextAsync(token);
        // 组织及owner先由PG过滤，避免跨租户列表泄漏。
        var rows = await database.Runs.AsNoTracking().Where(value => value.OwnerSubjectId == actor.SubjectId && value.OrganizationId == actor.OrganizationId)
            .OrderByDescending(value => value.CreatedAtUtc).Take(200).ToArrayAsync(token);
        return rows.Where(value => Covers(actor, Scope(value))).Select(Map).ToArray();
    }

    /// <summary>按owner及完整范围读取真实运行快照，旧Run不重新查询active。</summary>
    public async Task<ExecutionRun> ReadAsync(ActorContext actor, string runId, CancellationToken token)
    {
        // 读取仅依赖持久Run，不重跑工具。
        await using var database = await factory.CreateDbContextAsync(token);
        // 每次均重新取PG事实，不以进程缓存作授权依据。
        var row = await FindAsync(database, runId, false, token);
        DemandOwner(actor, row);
        return Map(row);
    }

    /// <summary>持久取消与唯一终态事件原子提交；旧修订拒绝且运行原样保留。</summary>
    public async Task<ExecutionRun> CancelAsync(ActorContext actor, string runId, CancelRunRequest request, CancellationToken token)
    {
        DemandCommand(request.Command);
        // 整个请求参与幂等绑定，包括预期修订与理由。
        var hash = Hash(Encode(request));
        // 取消键绑定运行、主体及完整授权范围。
        var key = CommandKey(actor, "cancel:" + runId, request.Command.IdempotencyKey);
        // 取消仅持有一个短事务，不等待正在执行的工具。
        await using var database = await factory.CreateDbContextAsync(token);
        // 与事件append使用同一行锁顺序，只有一个终态能够提交。
        await using var transaction = await database.Database.BeginTransactionAsync(token);
        await LockCommandAsync(database, key, token);
        // 先检查已提交命令，避免相同重试被推进的seq拒绝。
        var prior = await database.Commands.AsNoTracking().SingleOrDefaultAsync(value => value.Key == key, token);
        if (prior is not null) return await ReplayAsync(database, actor, prior, hash, token);
        // 运行行锁阻止worker在取消检查与提交之间插入终态。
        var row = await FindAsync(database, runId, true, token);
        DemandOwner(actor, row);
        if (request.Command.ExpectedRevision != row.LastSeq) throw new SemanticOperationException(409, "revision_conflict");
        if (!Terminal(row.Status))
        {
            row.CancelRequested = true;
            row.FencingToken++;
            AddEvent(database, row, new RunCancelledPayload { Status = ExecutionStatus.Cancelled, Code = "cancelled", TotalToolCalls = row.ToolCalls });
        }
        // 回执保留实际终态，不制造第二次取消事实。
        var result = Map(row);
        database.Commands.Add(new RunCommandRecord { Key = key, PayloadHash = hash, RunId = row.RunId, ReceiptJson = Encode(result) });
        await CommitAsync(database, actor, row, "execution.run.cancel", token);
        return result;
    }

    /// <summary>PG分页返回已提交事件；游标跨Run、负数或超前必须显式拒绝。</summary>
    public async Task<ExecutionEvent[]> EventsAsync(ActorContext actor, string runId, long after, CancellationToken token)
    {
        // 每轮新上下文读取持久事实，历史与后续事件之间没有订阅切换窗口。
        await using var database = await factory.CreateDbContextAsync(token);
        // 用当前PG快照验证完整范围和游标。
        var row = await FindAsync(database, runId, false, token);
        DemandOwner(actor, row);
        if (after < 0) throw new SemanticOperationException(400, "cursor_invalid");
        if (after > row.LastSeq) throw new SemanticOperationException(409, "cursor_ahead");
        // 有界批次限制慢客户端所占内存，不持有事务。
        var values = await database.Events.AsNoTracking().Where(value => value.RunId == runId && value.Seq > after)
            .OrderBy(value => value.Seq).Take(16).Select(value => value.EnvelopeJson).ToArrayAsync(token);
        return values.Select(Decode<ExecutionEvent>).ToArray();
    }

    /// <summary>以PG行锁和SKIP LOCKED竞争一个可执行或租约失效的运行。</summary>
    public async Task<RunRecord?> ClaimAsync(string workerId, CancellationToken token)
    {
        // 独立上下文确保多个worker在不同连接竞争真实锁。
        await using var database = await factory.CreateDbContextAsync(token);
        // claim/start事件与审计构成同一个原子提交。
        await using var transaction = await database.Database.BeginTransactionAsync(token);
        // 由可信时钟给出租约候选边界。
        var now = clock.GetUtcNow();
        // 只竞争活跃候选，避免持锁等待另一worker。
        var rows = await database.Runs.FromSqlInterpolated($"SELECT * FROM agents.\"Runs\" WHERE \"Status\" IN ('QUEUED','RUNNING') AND (\"LeaseUntil\" IS NULL OR \"LeaseUntil\" <= {now}) ORDER BY \"CreatedAtUtc\" FOR UPDATE SKIP LOCKED LIMIT 1").ToArrayAsync(token);
        // 没有候选时由后台短延时再次检查PG。
        var row = rows.SingleOrDefault();
        if (row is null) return null;
        row.LeaseOwner = workerId;
        row.LeaseUntil = now.AddSeconds(10);
        row.FencingToken++;
        row.DeadlineUtc ??= now.AddSeconds(30);
        if (row.Status == "QUEUED")
        {
            row.Status = "RUNNING";
            AddEvent(database, row, new RunStartedPayload { ProviderMode = Map(row).ProviderMode, CapabilityIds = [Decode<SemanticQueryPlan>(row.PlanJson).CapabilityId], MaxToolCalls = 3, TimeoutMs = 30000 });
        }
        await CommitAsync(database, Decode<ActorContext>(row.ActorJson), row, "execution.run.start", token);
        return row;
    }

    /// <summary>定期续租并检查取消/fence；失效时阻止下游继续执行。</summary>
    public async Task<bool> RenewAsync(string runId, string owner, long fence, CancellationToken token)
    {
        // 单条条件更新既是续租CAS也是持久取消检查。
        await using var database = await factory.CreateDbContextAsync(token);
        // 不延长Run的三十秒总预算。
        var now = clock.GetUtcNow();
        return await database.Runs.Where(value => value.RunId == runId && value.Status == "RUNNING" && !value.CancelRequested
            && value.LeaseOwner == owner && value.FencingToken == fence && value.LeaseUntil > now && value.DeadlineUtc > now)
            .ExecuteUpdateAsync(update => update.SetProperty(value => value.LeaseUntil, now.AddSeconds(10)), token) == 1;
    }

    /// <summary>受fencing保护地追加唯一类型事件；工具预留、预算和终态同事务。</summary>
    public async Task<bool> AppendAsync(string runId, string owner, long fence, ExecutionPayload payload, CancellationToken token)
    {
        // 每个事件只持有自身短事务，不包含网络或模型调用。
        await using var database = await factory.CreateDbContextAsync(token);
        // 行锁负责单调seq和唯一终态，fence再防旧worker。
        await using var transaction = await database.Database.BeginTransactionAsync(token);
        // 读取当前行，不能用claim时的跟踪副本判定租约。
        var row = await FindAsync(database, runId, true, token);
        if (row.Status != "RUNNING" || row.CancelRequested || row.LeaseOwner != owner || row.FencingToken != fence || row.LeaseUntil <= clock.GetUtcNow()) return false;
        // 返回值表示调用者原事件被接受；内部预算改写为失败不能授权后续工具继续。
        var requestedPayload = payload;
        if (row.DeadlineUtc <= clock.GetUtcNow() && payload is not RunFailedPayload)
            payload = new RunFailedPayload { Status = ExecutionStatus.Failed, Code = "run_timeout", TotalToolCalls = row.ToolCalls };
        if (payload is ToolStartedPayload)
        {
            if (row.ToolCalls >= 3) payload = new RunFailedPayload { Status = ExecutionStatus.Failed, Code = "tool_budget_exceeded", TotalToolCalls = row.ToolCalls };
            else row.ToolCalls++;
        }
        AddEvent(database, row, payload);
        await CommitAsync(database, Decode<ActorContext>(row.ActorJson), row, row.Status switch { "FAILED" => "execution.run.fail", "COMPLETED" => "execution.run.complete", _ => "execution.run.tool" }, token);
        return !Terminal(row.Status) || ReferenceEquals(payload, requestedPayload)
            && (payload is RunCompletedPayload && row.Status == "COMPLETED" || payload is RunFailedPayload && row.Status == "FAILED");
    }

    /// <summary>严格解析Last-Event-ID，拒绝其他Run及非规范十进制序号。</summary>
    public static long ParseCursor(string runId, string? cursor)
    {
        if (string.IsNullOrEmpty(cursor)) return 0;
        // 只有指定Run前缀和非负规范整数能映射到持久事件。
        var prefix = runId + ":";
        if (!cursor.StartsWith(prefix, StringComparison.Ordinal) || !long.TryParse(cursor.AsSpan(prefix.Length), NumberStyles.None, CultureInfo.InvariantCulture, out var seq)
            || seq < 0 || cursor != prefix + seq.ToString(CultureInfo.InvariantCulture)) throw new SemanticOperationException(400, "cursor_invalid");
        return seq;
    }

    /// <summary>终态判断复用于worker和流关闭，不将禁用提供者当成功。</summary>
    public static bool Terminal(string status) => status is "COMPLETED" or "FAILED" or "CANCELLED";

    /// <summary>唯一DTO序列化主动执行所有入出合同回调。</summary>
    internal static string Encode<T>(T value) => JsonSerializer.Serialize(value, Json);

    /// <summary>唯一DTO反序列化主动执行所有入出合同回调。</summary>
    internal static T Decode<T>(string value) => JsonSerializer.Deserialize<T>(value, Json)!;

    /// <summary>同一个固定资源范围投影，不泄漏Prompt。</summary>
    private static ResourceScope Scope(RunRecord row) => new() { OrganizationId = row.OrganizationId, SiteIds = row.SiteIds };

    /// <summary>映射唯一公共运行合同，禁止返回内部身份或正文列。</summary>
    private static ExecutionRun Map(RunRecord row) => new()
    {
        RunId = row.RunId,
        OwnerSubjectId = row.OwnerSubjectId,
        Scope = Scope(row),
        Snapshot = Decode<AssetVersionSnapshot>(row.SnapshotJson),
        Status = Enum.Parse<ExecutionStatus>(row.Status, true),
        ProviderMode = row.ProviderMode == "deterministic" ? ProviderMode.Deterministic : ProviderMode.Disabled,
        CreatedAtUtc = row.CreatedAtUtc,
        UpdatedAtUtc = row.UpdatedAtUtc,
        LastSeq = row.LastSeq,
        CancelRequested = row.CancelRequested,
        LeaseOwner = row.LeaseOwner,
        LeaseUntil = row.LeaseUntil,
        FencingToken = row.FencingToken,
        TraceId = row.TraceId
    };

    /// <summary>可信平台角色在直接调用和HTTP之间保持一致。</summary>
    private static void DemandActor(ActorContext actor)
    {
        if (string.IsNullOrWhiteSpace(actor.SubjectId) || !actor.Roles.Any(value => value is "platform.viewer" or "platform.operator" or "platform.auditor")) throw new SemanticOperationException(403, "role_denied");
    }

    /// <summary>要求同组织且完整资源厂区是当前授权子集。</summary>
    private static bool Covers(ActorContext actor, ResourceScope scope) => actor.OrganizationId == scope.OrganizationId && scope.SiteIds.Length is > 0 and <= 16 && scope.SiteIds.All(value => actor.SiteIds.Contains(value, StringComparer.Ordinal));

    /// <summary>所有读取及写入统一执行完整scope授权。</summary>
    private static void DemandScope(ActorContext actor, ResourceScope scope)
    {
        DemandActor(actor);
        if (!Covers(actor, scope)) throw new SemanticOperationException(403, "scope_denied");
    }

    /// <summary>即使同组织管理员也不能读取他人运行正文事件。</summary>
    private static void DemandOwner(ActorContext actor, RunRecord row)
    {
        DemandScope(actor, Scope(row));
        if (actor.SubjectId != row.OwnerSubjectId) throw new SemanticOperationException(403, "run_owner_denied");
    }

    /// <summary>模块入口也校验命令，不依赖端点替它验证。</summary>
    private static void DemandCommand(CommandContext command)
    {
        if (string.IsNullOrWhiteSpace(command.CommandId) || command.CommandId.Length > 64 || string.IsNullOrWhiteSpace(command.IdempotencyKey) || command.IdempotencyKey.Length > 64
            || string.IsNullOrWhiteSpace(command.Reason) || command.Reason.Length > 500 || command.ExpectedRevision < 0) throw new SemanticOperationException(400, "invalid_command");
    }

    /// <summary>规范身份范围及操作的无碰撞结构化键。</summary>
    private static string CommandKey(ActorContext actor, string operation, string key) => Hash(Encode(new { actor.SubjectId, actor.OrganizationId, Operation = operation, Key = key }));

    /// <summary>SHA256只用于内部幂等绑定，不输出正文。</summary>
    private static string Hash(string text) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(text)));

    /// <summary>并发相同幂等键在数据库事务中串行，锁冲突最多降低并发。</summary>
    private static Task<int> LockCommandAsync(AgentsDbContext database, string key, CancellationToken token) => database.Database.ExecuteSqlInterpolatedAsync($"SELECT pg_advisory_xact_lock(hashtextextended({key}, 0))", token);

    /// <summary>读锁由服务端固定SQL产生，只参数化Run标识。</summary>
    private static async Task<RunRecord> FindAsync(AgentsDbContext database, string runId, bool locked, CancellationToken token)
    {
        // 行锁查询不能经First额外包装而改变FOR UPDATE语义。
        var rows = locked ? await database.Runs.FromSqlInterpolated($"SELECT * FROM agents.\"Runs\" WHERE \"RunId\" = {runId} FOR UPDATE").ToArrayAsync(token)
            : await database.Runs.AsNoTracking().Where(value => value.RunId == runId).ToArrayAsync(token);
        return rows.SingleOrDefault() ?? throw new SemanticOperationException(404, "run_not_found");
    }

    /// <summary>重放先重新授权当前运行，再返回原提交回执。</summary>
    private static async Task<ExecutionRun> ReplayAsync(AgentsDbContext database, ActorContext actor, RunCommandRecord command, string hash, CancellationToken token)
    {
        DemandOwner(actor, await FindAsync(database, command.RunId, false, token));
        if (command.PayloadHash != hash) throw new SemanticOperationException(409, "idempotency_conflict");
        return Decode<ExecutionRun>(command.ReceiptJson);
    }

    /// <summary>追加预算内事件，预留最后一个位置用于可靠预算失败终态。</summary>
    private void AddEvent(AgentsDbContext database, RunRecord row, ExecutionPayload payload)
    {
        // 同行锁保护的下一序号同时绑定eventId和Envelope。
        var seq = row.LastSeq + 1;
        // 先构造完整事件再测量真实UTF8序列化尺寸。
        var envelope = Envelope(row, payload, seq);
        // 非终态最多511条，第512条必须为终态，永远保留失败回执位置。
        var serialized = Encode(envelope);
        if (Encoding.UTF8.GetByteCount(serialized) > 128 * 1024 || payload is MessageDeltaPayload message && message.Text.Length > 4096
            || seq >= 512 && payload is not (RunCompletedPayload or RunCancelledPayload or RunFailedPayload))
        {
            payload = new RunFailedPayload { Status = ExecutionStatus.Failed, Code = "event_budget_exceeded", TotalToolCalls = row.ToolCalls };
            envelope = Envelope(row, payload, seq);
            serialized = Encode(envelope);
        }
        if (seq > 512) throw new InvalidOperationException("持久事件预算不变量被破坏。");
        row.LastSeq = seq;
        row.UpdatedAtUtc = envelope.OccurredAtUtc;
        row.Status = payload switch { RunFailedPayload => "FAILED", RunCompletedPayload => "COMPLETED", RunCancelledPayload => "CANCELLED", _ => row.Status };
        if (Terminal(row.Status))
        {
            row.LeaseOwner = null;
            row.LeaseUntil = null;
        }
        database.Events.Add(new RunEventRecord { RunId = row.RunId, Seq = seq, EventId = envelope.EventId, EnvelopeJson = serialized });
    }

    /// <summary>事件类型只能从唯一强类型载荷导出，固定相同snapshot。</summary>
    private ExecutionEvent Envelope(RunRecord row, ExecutionPayload payload, long seq) => new()
    {
        RunId = row.RunId,
        Seq = seq,
        EventId = row.RunId + ":" + seq.ToString(CultureInfo.InvariantCulture),
        SchemaVersion = 1,
        OccurredAtUtc = clock.GetUtcNow(),
        Snapshot = Decode<AssetVersionSnapshot>(row.SnapshotJson),
        Payload = payload,
        EventType = payload switch { RunStartedPayload => "run.started", ToolStartedPayload => "tool.started", ToolCompletedPayload => "tool.completed", EvidenceAddedPayload => "evidence.added", MessageDeltaPayload => "message.delta", RunCompletedPayload => "run.completed", RunFailedPayload => "run.failed", RunCancelledPayload => "run.cancelled", _ => throw new InvalidOperationException("未授权事件类型。") }
    };

    /// <summary>业务与Governance审计在同连接同事务内保存，提交后才可返回。</summary>
    private async Task CommitAsync(AgentsDbContext database, ActorContext actor, RunRecord row, string action, CancellationToken token)
    {
        await database.SaveChangesAsync(token);
        await audit.WriteAsync(actor, new AuditCommand { Action = action, Resource = row.RunId, Scope = Scope(row), Outcome = row.Status == "FAILED" ? "failure" : "allowed" }, database.Database.GetDbConnection(), database.Database.CurrentTransaction!.GetDbTransaction(), token);
        await database.Database.CurrentTransaction!.CommitAsync(token);
    }
}
