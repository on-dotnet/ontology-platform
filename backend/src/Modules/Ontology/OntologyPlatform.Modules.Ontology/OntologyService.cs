using System.Data.Common;
using System.Diagnostics;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology.Domain;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>持久源历史、精确修订CAS与Governance审计同物理事务的草稿用例。</summary>
public sealed class OntologyService : IOntologyService, IDraftPublicationReader
{
    /// <summary>草稿命令只记录固定动作、内容散列与结果，不输出源正文或理由。</summary>
    private static readonly ActivitySource Activities = new("OntologyPlatform.Ontology");

    /// <summary>只写ontology表的上下文。</summary>
    private readonly OntologyDbContext database;

    /// <summary>真实RIOT/SHACL适配器。</summary>
    private readonly ISemanticRuntime runtime;

    /// <summary>由治理模块拥有并加入同事务的审计写入器。</summary>
    private readonly ITransactionalAuditWriter audit;

    /// <summary>单一事实时间来源。</summary>
    private readonly TimeProvider clock;

    /// <summary>可选正式发布目录；S1没有发布模块时普通新资产仍能创建。</summary>
    private readonly IReleaseCatalog? releases;

    /// <summary>构造模块用例，不在构造过程中访问外部资源。</summary>
    /// <param name="database">专属模块上下文。</param>
    /// <param name="runtime">受控语义运行时。</param>
    /// <param name="audit">同事务审计边界。</param>
    /// <param name="clock">真实时间提供者。</param>
    /// <param name="releases">正式发布目录，仅从BaseRelease创建新草稿时必需。</param>
    public OntologyService(OntologyDbContext database, ISemanticRuntime runtime, ITransactionalAuditWriter audit, TimeProvider clock, IReleaseCatalog? releases = null)
    {
        this.database = database;
        this.runtime = runtime;
        this.audit = audit;
        this.clock = clock;
        this.releases = releases;
    }

    /// <summary>只返回完整scope获准的真实草稿，不按首厂扩大权限。</summary>
    public async Task<OntologyDraft[]> ListAsync(ActorContext actor, CancellationToken cancellationToken)
    {
        DemandRole(actor, false);
        // PostgreSQL数组包含运算在查询端过滤全部厂区，避免拉回未授权正文。
        var rows = await database.Drafts.AsNoTracking().Where(row => row.OrganizationId == actor.OrganizationId && row.SiteIds.All(site => actor.SiteIds.Contains(site))).OrderByDescending(row => row.UpdatedAtUtc).ToArrayAsync(cancellationToken);
        // 逐草稿显式映射准确当前修订，不把投影当权威源。
        var result = new List<OntologyDraft>();
        foreach (var row in rows) result.Add(await MapAsync(row, cancellationToken));
        return result.ToArray();
    }

    /// <summary>生成服务端资产身份，真实解析后提交草稿、源码、回执和审计。</summary>
    public async Task<OntologyDraft> CreateAsync(ActorContext actor, CreateDraftRequest request, CancellationToken cancellationToken)
    {
        DemandRole(actor, true);
        ValidateCommand(request.Command);
        // 完整范围规范化后参与幂等键和授权，重复厂区不得制造另一资产范围。
        var scope = Normalize(request.Scope);
        DemandScope(actor, scope);
        if (request.Command.ExpectedRevision != 0 || string.IsNullOrWhiteSpace(request.Name) || request.Name.Length > 200) throw new SemanticOperationException(422, "draft_request_invalid");
        // 已提交回执不依赖Jena当前可用性，重试直接返回同一业务事实。
        var replay = await ReplayAsync<OntologyDraft>(actor, scope, "ontology.create", request.Command, request with { Scope = scope }, cancellationToken);
        if (replay is not null) return replay;
        // 首次资产身份只能由服务器生成；clone只允许继承经重新授权的正式目录事实。
        var assetId = Guid.NewGuid().ToString("N");
        if (request.BaseReleaseId is not null)
        {
            if (releases is null) throw new SemanticOperationException(503, "release_catalog_unavailable");
            // 目录根据releaseId重新授权，而非从客户端推断assetId或第一厂区。
            var basis = await releases.ReadAsync(actor, request.BaseReleaseId, cancellationToken);
            // 完整且规范化的历史scope不得被clone请求缩小或扩大。
            var originalScope = Normalize(basis.Manifest.Scope);
            DemandScope(actor, originalScope);
            if (basis.Manifest.ReleaseId != request.BaseReleaseId || basis.Status is not (ReleaseStatus.Active or ReleaseStatus.Superseded)) throw new SemanticOperationException(409, "base_release_not_formal");
            if (scope.OrganizationId != originalScope.OrganizationId || !scope.SiteIds.SequenceEqual(originalScope.SiteIds, StringComparer.Ordinal)) throw new SemanticOperationException(403, "asset_scope_immutable");
            assetId = basis.Manifest.AssetId;
        }
        // 解析在PG短事务之前完成，外部请求不会持有草稿/审计表锁。
        var analysis = await runtime.AnalyzeAsync(request.Sources, 1, cancellationToken);
        return await WriteAsync<OntologyDraft>(actor, scope, "ontology.create", request.Command, request with { Scope = scope }, async token =>
        {
            // 新资产和草稿ID完全由服务器创建，客户端不能改变既有资产scope。
            var row = new DraftRecord { DraftId = Guid.NewGuid().ToString("N"), AssetId = assetId, BaseReleaseId = request.BaseReleaseId, OrganizationId = scope.OrganizationId, SiteIds = scope.SiteIds, Name = request.Name, OwnerSubjectId = actor.SubjectId, UpdatedAtUtc = clock.GetUtcNow() };
            database.Drafts.Add(row);
            database.Revisions.Add(Revision(row, request.Sources, analysis));
            return (Map(row, request.Sources, analysis), row.DraftId);
        }, cancellationToken);
    }

    /// <summary>只读取授权内草稿及对应完整源码，不依赖Jena在线。</summary>
    public async Task<OntologyDraft> ReadAsync(ActorContext actor, string draftId, CancellationToken cancellationToken)
    {
        DemandRole(actor, false);
        // 首先只读取头记录判定404/403，未授权时不取源码。
        var row = await FindAsync(draftId, false, cancellationToken);
        DemandScope(actor, Scope(row));
        return await MapAsync(row, cancellationToken);
    }

    /// <summary>按显式期望修订CAS追加完整源码，语法失败绝不创建坏修订。</summary>
    public async Task<OntologyDraft> SaveAsync(ActorContext actor, string draftId, SaveDraftRequest request, CancellationToken cancellationToken)
    {
        DemandRole(actor, true);
        ValidateCommand(request.Command);
        // 持久头提供真实范围；保存不能改asset/scope。
        var row = await FindAsync(draftId, false, cancellationToken);
        DemandScope(actor, Scope(row));
        // 保存重放也不重新调用Jena，已提交的同一命令保持可恢复。
        var replay = await ReplayAsync<OntologyDraft>(actor, Scope(row), "ontology.save", request.Command, new { draftId, request }, cancellationToken);
        if (replay is not null) return replay;
        // Jena在事务外验证，锁定后仍重新比较期望修订防止TOCTOU。
        var analysis = await runtime.AnalyzeAsync(request.Sources, request.Command.ExpectedRevision + 1, cancellationToken);
        return await SaveCoreAsync(actor, row, request.Command, request.Sources, analysis, "ontology.save", request, cancellationToken);
    }

    /// <summary>对当前完整图执行精确编辑，再以相同期望修订CAS持久提交。</summary>
    public async Task<OntologyDraft> EditAsync(ActorContext actor, string draftId, EditDraftRequest request, CancellationToken cancellationToken)
    {
        DemandRole(actor, true);
        ValidateCommand(request.Command);
        // 当前真实源先授权，旧revision必须在编辑前失败。
        var row = await FindAsync(draftId, false, cancellationToken);
        DemandScope(actor, Scope(row));
        // 幂等重放先检查已提交回执，避免使用更新后的源再做旧编辑。
        var replay = await ReplayAsync<OntologyDraft>(actor, Scope(row), "ontology.edit", request.Command, new { draftId, request }, cancellationToken);
        if (replay is not null) return replay;
        if (row.Revision != request.Command.ExpectedRevision) throw new SemanticOperationException(409, "draft_revision_conflict");
        // 当前修订含无损权威源，不使用画布节点重建。
        var current = await MapAsync(row, cancellationToken);
        // 真实运行时只允许支持子集精确三元组变更。
        var sources = await runtime.ApplyEditAsync(current.Sources, request.Edit, cancellationToken);
        // 新投影从实际新源码重新解析产生。
        var analysis = await runtime.AnalyzeAsync(sources, request.Command.ExpectedRevision + 1, cancellationToken);
        return await SaveCoreAsync(actor, row, request.Command, sources, analysis, "ontology.edit", request, cancellationToken);
    }

    /// <summary>提供完整源码差异和可证明的三元组差异，空白节点不假称稳定对应。</summary>
    public async Task<DraftDiff> DiffAsync(ActorContext actor, string draftId, long fromRevision, CancellationToken cancellationToken)
    {
        // 读取当前及历史都继承当前草稿不可变scope授权。
        var current = await ReadAsync(actor, draftId, cancellationToken);
        // 旧修订不可变，不能由客户端提供旧hash替代数据库事实。
        var old = await database.Revisions.AsNoTracking().SingleOrDefaultAsync(row => row.DraftId == draftId && row.Revision == fromRevision, cancellationToken) ?? throw new SemanticOperationException(404, "revision_not_found");
        // 旧投影与原始源在同一次修订提交中形成。
        var projection = JsonSerializer.Deserialize<SemanticProjection>(old.ProjectionJson)!;
        // 空白节点标识是运行时局部身份，变化时仅提供源码差异和明确诊断。
        var blanks = projection.Triples.Concat(current.Projection.Triples).Any(triple => triple.Subject.Kind == RdfTermKind.Blank || triple.Object.Kind == RdfTermKind.Blank);
        return new DraftDiff
        {
            BaseRevision = fromRevision, TargetRevision = current.Revision, BaseHashes = projection.Hashes, TargetHashes = current.Hashes,
            AddedTriples = blanks ? [] : current.Projection.Triples.Except(projection.Triples).ToArray(),
            RemovedTriples = blanks ? [] : projection.Triples.Except(current.Projection.Triples).ToArray(),
            SourceDiff = old.SourcesJson == JsonSerializer.Serialize(current.Sources) ? "" : JsonSerializer.Serialize(new { before = JsonSerializer.Deserialize<SourceBundle>(old.SourcesJson), after = current.Sources }),
            UnsupportedDiagnostics = blanks ? [new SemanticDiagnostic { Code = "blank_diff_unsupported", Severity = DiagnosticSeverity.Warning, Message = "保留完整源码差异；空白节点对应的图同构差异未运行。" }] : []
        };
    }

    /// <summary>报告绑定真实revision/hash，短事务再次核查后与审计一并持久。</summary>
    public async Task<SemanticValidationReport> ValidateAsync(ActorContext actor, string draftId, ValidateDraftRequest request, CancellationToken cancellationToken)
    {
        DemandRole(actor, true);
        ValidateCommand(request.Command);
        // 读取与授权必须先于依赖执行，不能借验证泄露其他草稿。
        var current = await ReadAsync(actor, draftId, cancellationToken);
        // 已提交的同一校验命令返回同一报告，不重复外部验证/审计。
        var replay = await ReplayAsync<SemanticValidationReport>(actor, current.Scope, "ontology.validate", request.Command, new { draftId, request }, cancellationToken);
        if (replay is not null) return replay;
        if (request.Revision != current.Revision || request.Command.ExpectedRevision != current.Revision || request.Hashes != current.Hashes) throw new SemanticOperationException(409, "draft_revision_conflict");
        // 真实报告可含业务定位正文，但不会写普通遥测。
        var report = (await runtime.ValidateAsync(current.Sources, cancellationToken)) with { DraftId = draftId, Revision = current.Revision, Hashes = current.Hashes, TraceId = actor.TraceId };
        return await WriteAsync<SemanticValidationReport>(actor, current.Scope, "ontology.validate", request.Command, new { draftId, request }, async token =>
        {
            // 锁与CAS确保校验期间修改不能把旧报告登记为当前成功。
            var row = await FindAsync(draftId, true, token);
            if (row.Revision != current.Revision) throw new SemanticOperationException(409, "draft_revision_conflict");
            database.Validations.Add(new ValidationRecord { ReportId = report.ReportId, DraftId = draftId, Revision = report.Revision, BundleHash = report.Hashes.BundleHash, Conforms = report.Conforms, ReportJson = JsonSerializer.Serialize(report) });
            return (report, draftId);
        }, cancellationToken);
    }

    /// <summary>由Ontology在发布方同物理事务中锁定，只读核验当前修订与成功报告。</summary>
    public async Task<DraftPublicationSnapshot> LockForPublicationAsync(ActorContext actor, string draftId, long revision, SourceHashes hashes, string reportId, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken)
    {
        DemandRole(actor, true);
        if (transaction.Connection != connection) throw new SemanticOperationException(409, "transaction_connection_mismatch");
        // 独立上下文使用同一已打开物理连接，不创建第二条连接或提交调用方事务。
        var options = new DbContextOptionsBuilder<OntologyDbContext>().UseNpgsql(connection).Options;
        // Ontology只拥有自己的读取锁，Publishing不可直接访问表。
        await using var enlisted = new OntologyDbContext(options);
        await enlisted.Database.UseTransactionAsync(transaction, cancellationToken);
        // 固定draft→proposal→active顺序中的第一把行锁。
        var row = await enlisted.Drafts.FromSqlInterpolated($"SELECT * FROM ontology.\"Drafts\" WHERE \"DraftId\"={draftId} FOR UPDATE").SingleOrDefaultAsync(cancellationToken) ?? throw new SemanticOperationException(404, "draft_not_found");
        DemandScope(actor, Scope(row));
        if (row.Revision != revision) throw new SemanticOperationException(409, "draft_revision_conflict");
        // 真正历史源码与校验事实都由本模块读取。
        var source = await enlisted.Revisions.AsNoTracking().SingleAsync(record => record.DraftId == draftId && record.Revision == revision, cancellationToken);
        // 校验报告必须精确匹配当前源，不使用客户端conforms字段。
        var validation = await enlisted.Validations.AsNoTracking().SingleOrDefaultAsync(record => record.ReportId == reportId && record.DraftId == draftId && record.Revision == revision, cancellationToken);
        if (JsonSerializer.Deserialize<SourceHashes>(source.HashesJson) != hashes || validation is null || !validation.Conforms || validation.BundleHash != hashes.BundleHash) throw new SemanticOperationException(409, "validation_binding_conflict");
        return new DraftPublicationSnapshot { Draft = Map(row, source), Validation = JsonSerializer.Deserialize<SemanticValidationReport>(validation.ReportJson)! };
    }

    /// <summary>保存/结构编辑共用CAS追加实现，不允许跨模块写入或原地覆盖源历史。</summary>
    private Task<OntologyDraft> SaveCoreAsync(ActorContext actor, DraftRecord known, CommandContext command, SourceBundle sources, SemanticAnalysis analysis, string action, object request, CancellationToken cancellationToken) =>
        WriteAsync<OntologyDraft>(actor, Scope(known), action, command, new { draftId = known.DraftId, request }, async token =>
        {
            // 事务内最新头是唯一CAS依据，事务外预读仅用于解析和授权。
            var row = await FindAsync(known.DraftId, true, token);
            DemandScope(actor, Scope(row));
            if (row.Revision != command.ExpectedRevision) throw new SemanticOperationException(409, "draft_revision_conflict");
            row.Revision++;
            row.UpdatedAtUtc = clock.GetUtcNow();
            database.Revisions.Add(Revision(row, sources, analysis));
            return (Map(row, sources, analysis), row.DraftId);
        }, cancellationToken);

    /// <summary>同事务锁定幂等键，业务/回执/Governance审计全部成功后才commit。</summary>
    private async Task<T> WriteAsync<T>(ActorContext actor, ResourceScope scope, string action, CommandContext command, object payload, Func<CancellationToken, Task<(T Result, string Resource)>> mutation, CancellationToken token) where T : class
    {
        // Trace通过当前Activity自动关联，禁止将组织/主体作为低基数指标标签。
        using var activity = Activities.StartActivity("ontology.command");
        activity?.SetTag("ontology.operation", action);
        // 完整规范scope和固定操作参与幂等键，不使用第一厂区替代。
        var key = CommandKey(scope, action, command.IdempotencyKey);
        // 完整命令含reason/revision与载荷散列，异payload重放明确409。
        var payloadHash = OntologyRules.Hash(JsonSerializer.Serialize(payload));
        await using var transaction = await database.Database.BeginTransactionAsync(token);
        // 跨进程事务级advisory lock串行同一幂等键，事务结束自动释放。
        await database.Database.ExecuteSqlInterpolatedAsync($"SELECT pg_advisory_xact_lock(hashtextextended({key}, 0))", token);
        // 事务锁内重新读取，防止并发响应丢失导致重复副作用。
        var replay = await database.Commands.AsNoTracking().SingleOrDefaultAsync(row => row.Key == key, token);
        if (replay is not null)
        {
            if (replay.PayloadHash != payloadHash || replay.SubjectId != actor.SubjectId) throw new SemanticOperationException(409, "idempotency_conflict");
            return JsonSerializer.Deserialize<T>(replay.ResultJson)!;
        }
        try
        {
            // 模块拥有的变更产生结果和受控资源ID。
            var result = await mutation(token);
            database.Commands.Add(new CommandRecord { Key = key, PayloadHash = payloadHash, SubjectId = actor.SubjectId, ResultJson = JsonSerializer.Serialize(result.Result) });
            await database.SaveChangesAsync(token);
            await audit.WriteAsync(actor, new AuditCommand { Action = action, Resource = result.Resource, Outcome = "allowed", Scope = scope }, database.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
            await transaction.CommitAsync(token);
            activity?.SetTag("ontology.outcome", "committed");
            activity?.SetStatus(ActivityStatusCode.Ok);
            return result.Result;
        }
        catch (DbUpdateConcurrencyException) { throw new SemanticOperationException(409, "draft_revision_conflict"); }
        finally { database.ChangeTracker.Clear(); }
    }

    /// <summary>读取已提交回执用于避免重复运行昂贵的外部操作，仍严格核查主体和载荷。</summary>
    private async Task<T?> ReplayAsync<T>(ActorContext actor, ResourceScope scope, string action, CommandContext command, object payload, CancellationToken token) where T : class
    {
        // 相同完整范围/操作/幂等键定位真实已提交回执。
        var key = CommandKey(scope, action, command.IdempotencyKey);
        // 未提交记录在默认隔离级别不可见。
        var replay = await database.Commands.AsNoTracking().SingleOrDefaultAsync(row => row.Key == key, token);
        if (replay is null) return null;
        if (replay.PayloadHash != OntologyRules.Hash(JsonSerializer.Serialize(payload)) || replay.SubjectId != actor.SubjectId) throw new SemanticOperationException(409, "idempotency_conflict");
        return JsonSerializer.Deserialize<T>(replay.ResultJson)!;
    }

    /// <summary>按需取得当前草稿头行锁，固定SQL只使用参数。</summary>
    private async Task<DraftRecord> FindAsync(string draftId, bool locked, CancellationToken token) =>
        await (locked ? database.Drafts.FromSqlInterpolated($"SELECT * FROM ontology.\"Drafts\" WHERE \"DraftId\"={draftId} FOR UPDATE") : database.Drafts.AsNoTracking().Where(row => row.DraftId == draftId)).SingleOrDefaultAsync(token)
        ?? throw new SemanticOperationException(404, "draft_not_found");

    /// <summary>显式读取当前不可变修订，不重新序列化Turtle。</summary>
    private async Task<OntologyDraft> MapAsync(DraftRecord row, CancellationToken token) => Map(row,
        await database.Revisions.AsNoTracking().SingleAsync(revision => revision.DraftId == row.DraftId && revision.Revision == row.Revision, token));

    /// <summary>将完整历史记录映射到同revision读模型。</summary>
    private static OntologyDraft Map(DraftRecord row, DraftRevisionRecord revision) => Map(row, JsonSerializer.Deserialize<SourceBundle>(revision.SourcesJson)!, new SemanticAnalysis { Hashes = JsonSerializer.Deserialize<SourceHashes>(revision.HashesJson)!, Projection = JsonSerializer.Deserialize<SemanticProjection>(revision.ProjectionJson)! });

    /// <summary>明确映射草稿头和同修订源/投影，不隐式生成领域属性。</summary>
    private static OntologyDraft Map(DraftRecord row, SourceBundle sources, SemanticAnalysis analysis) => new()
    {
        DraftId = row.DraftId, AssetId = row.AssetId, Scope = Scope(row), BaseReleaseId = row.BaseReleaseId, Revision = row.Revision,
        Etag = "\"" + row.Revision.ToString(System.Globalization.CultureInfo.InvariantCulture) + "\"", Name = row.Name, Sources = sources,
        Hashes = analysis.Hashes, OwnerSubjectId = row.OwnerSubjectId, UpdatedAtUtc = row.UpdatedAtUtc, Projection = analysis.Projection
    };

    /// <summary>生成永久保存的完整源修订记录。</summary>
    private static DraftRevisionRecord Revision(DraftRecord row, SourceBundle sources, SemanticAnalysis analysis) => new()
    {
        DraftId = row.DraftId, Revision = row.Revision, SourcesJson = JsonSerializer.Serialize(sources), HashesJson = JsonSerializer.Serialize(analysis.Hashes), ProjectionJson = JsonSerializer.Serialize(analysis.Projection)
    };

    /// <summary>头记录完整范围，无任何首厂简化。</summary>
    private static ResourceScope Scope(DraftRecord row) => new() { OrganizationId = row.OrganizationId, SiteIds = row.SiteIds };

    /// <summary>Ordinal去重排序厂区，并限制未授权空值。</summary>
    private static ResourceScope Normalize(ResourceScope scope)
    {
        if (scope is null || scope.SiteIds is null || scope.SiteIds.Length is < 1 or > 16 || string.IsNullOrWhiteSpace(scope.OrganizationId) || scope.SiteIds.Any(string.IsNullOrWhiteSpace)) throw new SemanticOperationException(422, "scope_invalid");
        return scope with { SiteIds = scope.SiteIds.Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray() };
    }

    /// <summary>完整范围越界时返回403，不能降为某一子厂区成功。</summary>
    private static void DemandScope(ActorContext actor, ResourceScope scope)
    {
        if (!OntologyRules.Covers(scope.OrganizationId, scope.SiteIds, actor.OrganizationId, actor.SiteIds)) throw new SemanticOperationException(403, "scope_denied");
    }

    /// <summary>REST之外的应用调用同样强制角色边界。</summary>
    private static void DemandRole(ActorContext actor, bool write)
    {
        if (string.IsNullOrWhiteSpace(actor.SubjectId) || (write ? !actor.Roles.Contains("platform.operator", StringComparer.Ordinal) : !actor.Roles.Any(role => role is "platform.viewer" or "platform.operator" or "platform.auditor"))) throw new SemanticOperationException(403, "role_denied");
    }

    /// <summary>命令标识与理由使用固定预算，不记录正文。</summary>
    private static void ValidateCommand(CommandContext command)
    {
        if (command is null || string.IsNullOrWhiteSpace(command.CommandId) || command.CommandId.Length > 64 || string.IsNullOrWhiteSpace(command.IdempotencyKey) || command.IdempotencyKey.Length > 64 || string.IsNullOrWhiteSpace(command.Reason) || command.Reason.Length > 500 || command.ExpectedRevision < 0) throw new SemanticOperationException(422, "command_invalid");
    }

    /// <summary>通过结构化JSON避免分隔符碰撞，绑定规范完整范围。</summary>
    private static string CommandKey(ResourceScope scope, string action, string key) => OntologyRules.Hash(JsonSerializer.Serialize(new { scope = Normalize(scope), action, key }));
}
