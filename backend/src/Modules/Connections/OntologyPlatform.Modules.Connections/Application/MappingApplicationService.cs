using Microsoft.AspNetCore.DataProtection;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>映射草稿、持久任务及审批的唯一应用入口，读写均重新核验完整授权。</summary>
public sealed class MappingApplicationService
{
    /// <summary>模块独占上下文，不使用跨模块Repository。</summary>
    private readonly IDbContextFactory<ConnectionsDbContext> factory;

    /// <summary>治理拥有会话、grant及组织epoch。</summary>
    private readonly IMappingAuthorizationAuthority authority;

    /// <summary>治理拥有并参与同物理事务的审计写者。</summary>
    private readonly ITransactionalAuditWriter audit;

    /// <summary>固定源与正式G3的实际评估服务。</summary>
    private readonly MappingValidationService validation;

    /// <summary>用途隔离的签名加密游标，不复用会话票据用途。</summary>
    private readonly IDataProtector cursorProtector;

    /// <summary>服务端统一时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>组合既有模块服务，不写本体或发布模块表。</summary>
    public MappingApplicationService(IDbContextFactory<ConnectionsDbContext> factory, IMappingAuthorizationAuthority authority,
        ITransactionalAuditWriter audit, MappingValidationService validation, TimeProvider clock, IDataProtectionProvider protection)
    {
        this.factory = factory;
        this.authority = authority;
        this.audit = audit;
        this.validation = validation;
        this.clock = clock;
        cursorProtector = protection.CreateProtector("OntologyPlatform.Mapping.Cursor.v1");
    }

    /// <summary>创建不可变第一修订；幂等身份由组织、完整scope及原命令确定。</summary>
    public async Task<MappingDraftView> CreateAsync(ActorContext actor, string session, MappingDraftCreateRequest request, CancellationToken token)
    {
        G4MappingRules.Scope(request.Scope);
        G4MappingRules.Command(request.Command, true);
        G4MappingRules.Definition(request.Mapping);
        G4MappingRules.Identifier(request.SourceConnectionId);
        G4MappingRules.Identifier(request.SourceCatalogSnapshotId);
        G4MappingRules.Identifier(request.OntologyReleaseId);
        G4MappingRules.Hash(request.OntologyManifestHash);
        // 同命令重放定位同永久资源；不把随机新ID变成重复副作用。
        var mappingId = "mapping-" + Digest(new { actor.OrganizationId, request.Scope, request.Command.IdempotencyKey })[..32];
        // 第一修订内容和长期绑定保持完整，后续编辑不能暗换源或本体。
        var draft = new MappingDraftView
        {
            SchemaVersion = "g4.mapping.v1",
            MappingId = mappingId,
            DraftId = "draft-" + mappingId,
            Scope = ConnectionApplicationService.Normalize(request.Scope),
            OntologyReleaseId = request.OntologyReleaseId,
            OntologyManifestHash = request.OntologyManifestHash,
            SourceConnectionId = request.SourceConnectionId,
            SourceCatalogSnapshotId = request.SourceCatalogSnapshotId,
            Revision = 1,
            MappingHash = Digest(request.Mapping),
            Mapping = request.Mapping,
            Status = "DRAFT",
            UpdatedAtUtc = clock.GetUtcNow()
        };
        // 动作和源列必须分别授权，每条grant均覆盖完整scope。
        var proofs = await AccessAsync(actor, session, draft, "mapping.edit", token);
        return await CommandAsync(mappingId, draft.Scope, draft.SourceConnectionId, "create", request, request.Command, null, proofs,
            async (db, cancellation) =>
            {
                if (await db.Mappings.AnyAsync(row => row.Id == mappingId, cancellation))
                {
                    throw Conflict();
                }
                db.Mappings.Add(new MappingRecord
                {
                    Id = mappingId,
                    OrganizationId = draft.Scope.OrganizationId,
                    SiteIds = draft.Scope.SiteIds,
                    DraftId = draft.DraftId,
                    CurrentRevisionId = RevisionId(mappingId, 1),
                    SourceConnectionId = draft.SourceConnectionId,
                    UpdatedAtUtc = draft.UpdatedAtUtc,
                    DisplayName = mappingId
                });
                AddRevision(db, actor.SubjectId, draft);
                return draft;
            }, "mapping.create", token);
    }

    /// <summary>读取固定修订或最新编辑头，历史原文不能裁剪后仍宣称原hash。</summary>
    public async Task<MappingDraftView> ReadDraftAsync(ActorContext actor, string session, string mappingId, long? revision, CancellationToken token)
    {
        // 先定位本组织的完整scope，未授权时不返回资源正文。
        var draft = await LoadDraftAsync(actor, mappingId, revision, token);
        await ReadAccessAsync(actor, session, draft, token);
        if (revision is null)
        {
            // 当前Draft允许状态投影，历史修订仍返回原保存DRAFT字节。
            await using var db = await factory.CreateDbContextAsync(token);
            // 只检查本修订PUBLISH任务，ROLLBACK报告不覆盖编辑状态。
            var jobs = await db.MappingJobs.AsNoTracking().Where(row => row.MappingId == mappingId)
                .OrderByDescending(row => row.CreatedAtUtc).ThenByDescending(row => row.Id).Take(50).ToArrayAsync(token);
            // 有界最近任务中精确匹配本修订目标。
            var job = jobs.FirstOrDefault(row => Decode<MappingJobInput>(row.RequestJson).Target is MappingPublishTarget publish && publish.DraftRevision == draft.Revision);
            if (job?.Status is "QUEUED" or "RUNNING")
            {
                draft = draft with { Status = "VALIDATING" };
            }
            else if (job?.Status == "SUCCEEDED" && job.ResultId is not null)
            {
                // 原报告的状态只在所有当前输入仍绑定时投影到Draft。
                var report = await AssessmentAsync(db, mappingId, job.ResultId, token);
                try
                {
                    // 授权epoch变化会使旧报告失去新鲜性。
                    var proof = await validation.CaptureAsync(actor, session, draft.Scope, "mapping.read", token);
                    await CurrentAsync(db, draft, report.Target, report.Binding, report.ExpectedActive, proof.AuthorizationEpoch, token);
                    draft = draft with { Status = report.ExpiresAtUtc <= clock.GetUtcNow() ? "NEEDS_REVIEW" : report.Status };
                }
                catch (SemanticOperationException error) when (error.Status == 409)
                {
                    draft = draft with { Status = "NEEDS_REVIEW" };
                }
            }
            else if (job?.Status == "FAILED")
            {
                draft = draft with { Status = "BLOCKED" };
            }
        }
        return draft;
    }

    /// <summary>CAS保存追加修订，不覆盖历史评估或旧Release。</summary>
    public async Task<MappingDraftView> PatchAsync(ActorContext actor, string session, string mappingId, MappingDraftPatchRequest request, string? etag, CancellationToken token)
    {
        G4MappingRules.Command(request.Command, false);
        G4MappingRules.Definition(request.Mapping);
        // 读取旧完整定义以核验源与权限，锁内仍需重新比较当前修订。
        var draft = await LoadDraftAsync(actor, mappingId, null, token);
        // 源字段授权按待保存内容重新求全集，不能沿用旧字段子集。
        var proofs = await AccessAsync(actor, session, draft with { Mapping = request.Mapping }, "mapping.edit", token);
        return await CommandAsync(mappingId, draft.Scope, draft.SourceConnectionId, "patch", request, request.Command, etag, proofs,
            async (db, cancellation) =>
            {
                // 组织锁与资源锁内重新读取，避免预读对象覆盖并发编辑。
                var current = await RootAsync(db, actor, mappingId, cancellation);
                Cas(etag, "mapping", current.Revision, request.Command);
                // 到达安全整数上限时拒绝，不溢出或丢失JS精度。
                var next = Increment(current.Revision);
                // 长期身份不从客户端patch接收。
                var saved = draft with
                {
                    Revision = next,
                    Mapping = request.Mapping,
                    MappingHash = Digest(request.Mapping),
                    Status = "DRAFT",
                    UpdatedAtUtc = clock.GetUtcNow()
                };
                current.Revision = next;
                current.CurrentRevisionId = RevisionId(mappingId, next);
                current.UpdatedAtUtc = saved.UpdatedAtUtc;
                AddRevision(db, actor.SubjectId, saved);
                return saved;
            }, "mapping.update", token);
    }

    /// <summary>调度持久验证任务；刷新GET不触发源IO或重复POST。</summary>
    public async Task<MappingJobView> ValidateAsync(ActorContext actor, string session, string mappingId, MappingValidateRequest request, string? etag, CancellationToken token)
    {
        G4MappingRules.Command(request.Command, false);
        // 回滚目标来自历史原字节，调度CAS只约束当前编辑头。
        var draft = await TargetAsync(actor, mappingId, request.Target, token);
        // 工作者保存真实服务器会话证明，不能只保存客户端Actor。
        var proofs = await AccessAsync(actor, session, draft, "mapping.validate", token);
        return await CommandAsync(mappingId, draft.Scope, draft.SourceConnectionId, "validate", request, request.Command, etag, proofs,
            async (db, cancellation) =>
            {
                // 当前头CAS对PUBLISH和ROLLBACK均适用，目标内容判断另分支。
                var root = await RootAsync(db, actor, mappingId, cancellation);
                Cas(etag, "mapping", root.Revision, request.Command);
                if (request.Target is MappingPublishTarget publish && publish.DraftRevision != root.Revision)
                {
                    throw Conflict();
                }
                // 固定目标及完整定义快照，重启后不能换成最新草稿。
                var job = new MappingJobRecord
                {
                    Id = NewId("job"),
                    MappingId = mappingId,
                    OrganizationId = draft.Scope.OrganizationId,
                    SiteIds = draft.Scope.SiteIds,
                    CreatedAtUtc = clock.GetUtcNow(),
                    Kind = "VALIDATE",
                    SubmittedBy = actor.SubjectId,
                    RequestJson = Encode(new MappingJobInput { Draft = draft, Target = request.Target }),
                    AuthorityJson = Encode(proofs[0])
                };
                db.MappingJobs.Add(job);
                return JobView(job);
            }, "mapping.validate.start", token);
    }

    /// <summary>读取任务持久状态，不将租约超时误当成功。</summary>
    public async Task<MappingJobView> ReadJobAsync(ActorContext actor, string session, string jobId, CancellationToken token)
    {
        // 查询始终先按组织隔离。
        await using var db = await factory.CreateDbContextAsync(token);
        // 未授权ID不可泄漏所属映射。
        var job = await db.MappingJobs.AsNoTracking().SingleOrDefaultAsync(row => row.Id == jobId && row.OrganizationId == actor.OrganizationId, token)
            ?? throw Forbidden();
        // 固定目标正文同时用于当前全字段授权。
        var input = Decode<MappingJobInput>(job.RequestJson);
        await ReadAccessAsync(actor, session, input.Draft, token);
        return JobView(job);
    }

    /// <summary>原提交者CAS取消任务；旧工作者必须通过fence才能提交。</summary>
    public async Task<MappingJobView> CancelJobAsync(ActorContext actor, string session, string jobId, MappingCommandRequest request, string? etag, CancellationToken token)
    {
        G4MappingRules.Command(request.Command, false);
        // 预读只用于定位授权scope，状态仍在事务内重读。
        await using var lookup = await factory.CreateDbContextAsync(token);
        // 不允许跨主体取消，即使另有编辑权限。
        var found = await lookup.MappingJobs.AsNoTracking().SingleOrDefaultAsync(row => row.Id == jobId && row.OrganizationId == actor.OrganizationId, token)
            ?? throw Forbidden();
        if (found.SubmittedBy != actor.SubjectId)
        {
            throw Forbidden();
        }
        // 当前动作和字段权限必须仍有效。
        var input = Decode<MappingJobInput>(found.RequestJson);
        // 此证明只供短事务复核，不延长任务旧租约。
        var proofs = await AccessAsync(actor, session, input.Draft, "mapping.validate", token);
        return await CommandAsync(found.MappingId, input.Draft.Scope, input.Draft.SourceConnectionId, "cancel-job:" + jobId, request,
            request.Command, etag, proofs, async (db, cancellation) =>
            {
                // 同映射锁内重新读取任务CAS状态。
                var job = await db.MappingJobs.SingleAsync(row => row.Id == jobId, cancellation);
                Cas(etag, "job", job.Revision, request.Command);
                if (job.Status is not ("QUEUED" or "RUNNING"))
                {
                    throw Conflict();
                }
                job.Status = "CANCELLED";
                job.Revision = Increment(job.Revision);
                job.Fence = Increment(job.Fence);
                job.CompletedAtUtc = clock.GetUtcNow();
                job.LeaseUntil = null;
                return JobView(job);
            }, "mapping.validate.cancel", token);
    }

    /// <summary>同组织、scope、epoch和固定快照的有界列表，签名游标不允许跨页面重用。</summary>
    public async Task<MappingPage<T>> ListAsync<T>(ActorContext actor, string session, ResourceScope scope, string endpoint,
        string? mappingId, string? status, string? connectionId, long? revision, string? targetReleaseId, string? proposalId,
        string? cursor, int limit, CancellationToken token)
    {
        G4MappingRules.Scope(scope);
        if (limit is < 1 or > 50 || revision.HasValue && targetReleaseId is not null)
        {
            throw new SemanticOperationException(400, "mapping_payload_invalid");
        }
        // 审核队列需要额外review grant，普通详情不能借队列跨用户枚举。
        var proof = await validation.CaptureAsync(actor, session, scope, endpoint == "proposals" ? "mapping.review" : "mapping.read", token);
        // 所有筛选及列表实例绑定在签名中，limit变化也从首页开始。
        var identity = Digest(new { actor.SubjectId, scope, endpoint, mappingId, status, connectionId, revision, targetReleaseId, proposalId, limit });
        // 此上下文只读取Connections内列表索引。
        await using var db = await factory.CreateDbContextAsync(token);
        // 首屏使用真实PG可见性水位，即使同一时间戳也不纳入后来新建对象。
        var page = cursor is null ? new MappingCursorState
        {
            Identity = identity,
            Epoch = proof.AuthorizationEpoch,
            Snapshot = await db.Database.SqlQuery<string>($"SELECT pg_current_snapshot()::text AS \"Value\"").SingleAsync(token),
            ExpiresAtUtc = clock.GetUtcNow().AddMinutes(5),
            AfterId = string.Empty,
            AfterTime = DateTimeOffset.MinValue
        } : ReadCursor(cursor);
        if (page.Identity != identity || page.Epoch != proof.AuthorizationEpoch || page.ExpiresAtUtc <= clock.GetUtcNow())
        {
            throw new SemanticOperationException(409, "mapping_cursor_stale");
        }
        // 所有表名由固定分支选择，游标快照只作为SQL参数。
        IQueryable<MappingListCandidate> candidates = endpoint switch
        {
            "mappings" => db.MappingRevisions.FromSqlInterpolated($"SELECT * FROM connections.\"MappingRevisions\" WHERE pg_visible_in_snapshot(xmin::text::xid8, {page.Snapshot}::pg_snapshot)")
                .Where(row => row.OrganizationId == scope.OrganizationId && row.Revision == 1 && row.SiteIds.All(site => scope.SiteIds.Contains(site)))
                .Select(row => new MappingListCandidate { Id = row.MappingId, CreatedAtUtc = row.CreatedAtUtc }),
            "proposals" => db.MappingProposals.FromSqlInterpolated($"SELECT * FROM connections.\"MappingProposals\" WHERE pg_visible_in_snapshot(xmin::text::xid8, {page.Snapshot}::pg_snapshot)")
                .Where(row => row.OrganizationId == scope.OrganizationId && row.SiteIds.All(site => scope.SiteIds.Contains(site))
                    && (mappingId == null || row.MappingId == mappingId))
                .Select(row => new MappingListCandidate { Id = row.Id, CreatedAtUtc = row.CreatedAtUtc }),
            "releases" => db.MappingReleases.FromSqlInterpolated($"SELECT * FROM connections.\"MappingReleases\" WHERE pg_visible_in_snapshot(xmin::text::xid8, {page.Snapshot}::pg_snapshot)")
                .Where(row => row.OrganizationId == scope.OrganizationId && row.SiteIds.All(site => scope.SiteIds.Contains(site)) && (mappingId == null || row.MappingId == mappingId))
                .Select(row => new MappingListCandidate { Id = row.Id, CreatedAtUtc = row.CreatedAtUtc }),
            "assessments" => db.MappingAssessments.FromSqlInterpolated($"SELECT * FROM connections.\"MappingAssessments\" WHERE pg_visible_in_snapshot(xmin::text::xid8, {page.Snapshot}::pg_snapshot)")
                .Where(row => row.OrganizationId == scope.OrganizationId && row.SiteIds.All(site => scope.SiteIds.Contains(site)) && row.MappingId == mappingId
                    && (!revision.HasValue || row.TargetKind == "PUBLISH" && row.TargetRevision == revision.Value)
                    && (targetReleaseId == null || row.TargetKind == "ROLLBACK" && row.TargetId == targetReleaseId))
                .Select(row => new MappingListCandidate { Id = row.Id, CreatedAtUtc = row.CreatedAtUtc }),
            "checks" => db.MappingActivationChecks.FromSqlInterpolated($"SELECT * FROM connections.\"MappingActivationChecks\" WHERE pg_visible_in_snapshot(xmin::text::xid8, {page.Snapshot}::pg_snapshot)")
                .Where(row => row.OrganizationId == scope.OrganizationId && row.SiteIds.All(site => scope.SiteIds.Contains(site)) && row.ProposalId == proposalId)
                .Select(row => new MappingListCandidate { Id = row.Id, CreatedAtUtc = row.CreatedAtUtc }),
            _ => throw new SemanticOperationException(400, "mapping_payload_invalid")
        };
        // 每页最多扫描五十个候选，不能为了填满可见项无界遍历或回源。
        var rows = await candidates.Where(row => row.CreatedAtUtc > page.AfterTime || row.CreatedAtUtc == page.AfterTime && string.Compare(row.Id, page.AfterId) > 0)
            .OrderBy(row => row.CreatedAtUtc).ThenBy(row => row.Id).Take(limit + 1).ToArrayAsync(token);
        // 只有当前完全可见对象进入响应，跳过对象不披露名称和计数。
        var values = new List<T>();
        foreach (var row in rows.Take(limit))
        {
            try
            {
                // 分支明确指定响应合同类型，不能将任意数据库实体序列化出去。
                object value;
                switch (endpoint)
                {
                    case "mappings":
                        // 最新状态只投影，固定首修订用于稳定分页排序。
                        var draft = await ReadDraftAsync(actor, session, row.Id, null, token);
                        if (connectionId is not null && draft.SourceConnectionId != connectionId || status is not null && draft.Status != status)
                        {
                            continue;
                        }
                        // 列表仅返回ID和状态，不返回完整映射正文。
                        var active = await db.MappingActives.AsNoTracking().SingleOrDefaultAsync(item => item.MappingId == row.Id, token);
                        value = new MappingListItem
                        {
                            MappingId = row.Id,
                            Scope = draft.Scope,
                            Revision = draft.Revision,
                            Status = draft.Status,
                            ActiveReleaseId = active?.ReleaseId
                        };
                        break;
                    case "proposals":
                        // 过期和漂移属于当前投影，不能按持久PENDING/APPROVED漏筛或错筛。
                        var proposal = await ReadProposalAsync(actor, session, row.Id, token);
                        if (status is not null && proposal.Status != status)
                        {
                            continue;
                        }
                        value = proposal;
                        break;
                    case "releases":
                        value = await ReadReleaseAsync(actor, session, row.Id, token);
                        break;
                    case "assessments":
                        value = await ReadAssessmentAsync(actor, session, row.Id, token);
                        break;
                    default:
                        // Check读取复用原提案目标权限，不自动重跑检查。
                        var check = await db.MappingActivationChecks.AsNoTracking().SingleAsync(item => item.Id == row.Id, token);
                        _ = await ReadProposalAsync(actor, session, check.ProposalId, token);
                        value = Original<MappingActivationCheck>(check.CanonicalBytes, check.ContentHash);
                        break;
                }
                values.Add((T)value);
            }
            catch (SemanticOperationException error) when (error.Status is 403 or 422)
            {
                // 未授权或源无法证明可见的完整对象不能进入列表。
            }
        }
        // 列表IO结束重新核grant与epoch，不能把撤权前收集结果返回。
        var after = await validation.CaptureAsync(actor, session, scope, proof.Permission, token);
        if (after.AuthorizationEpoch != proof.AuthorizationEpoch)
        {
            throw Forbidden();
        }
        return new MappingPage<T>
        {
            Items = values.ToArray(),
            NextCursor = rows.Length <= limit ? null :
            cursorProtector.Protect(Encode(page with { AfterId = rows[limit - 1].Id, AfterTime = rows[limit - 1].CreatedAtUtc }))
        };
    }

    /// <summary>不调用模型的人工候选入口，响应不自动保存或批准任何映射。</summary>
    public async Task<MappingSuggestionView> SuggestionsAsync(ActorContext actor, string session, string mappingId,
        MappingSuggestionRequest request, string? etag, CancellationToken token)
    {
        G4MappingRules.Command(request.Command, false);
        if (request.Mode != "OFF")
        {
            throw new SemanticOperationException(422, "mapping_model_not_enabled");
        }
        // 明确人工模式仍要求当前编辑及源字段许可。
        var draft = await LoadDraftAsync(actor, mappingId, null, token);
        // 明确元数据候选不冒充实样证据。
        var proofs = await AccessAsync(actor, session, draft, "mapping.edit", token);
        // 网络读取在短事务外，提交时重核当前主体、源grant和草稿CAS。
        var suggestions = await validation.SuggestAsync(actor, draft, token);
        // 幂等原回执也须经过当前可见候选校验，不能直接返回旧字段。
        var result = await CommandAsync(mappingId, draft.Scope, draft.SourceConnectionId, "suggestions", request, request.Command, etag, proofs,
            async (db, cancellation) =>
            {
                // 保存命令回执以便同键恢复，草稿本身没有变化。
                var root = await RootAsync(db, actor, mappingId, cancellation);
                Cas(etag, "mapping", root.Revision, request.Command);
                return suggestions;
            }, "mapping.update", token, auditWritten: true);
        // 旧幂等回执也必须受当前可见字段限制；不能重放历史已撤权候选正文。
        MappingValidationService.DemandVisibleCandidates(result, suggestions);
        return result;
    }

    /// <summary>比较两个明确历史修订，GET不写入任何当前状态。</summary>
    public async Task<MappingDiffView> DiffAsync(ActorContext actor, string session, string mappingId, long? fromRevision, long? toRevision,
        string? fromReleaseId, string? toReleaseId, CancellationToken token)
    {
        // 原始比较对象及其hash在严格分支中取得。
        object before;
        // 新对象仍来自固定版本，不默认最新。
        object after;
        // 两个hash说明实际被比较的原件身份。
        string fromHash;
        // 发布差异比较整个Manifest，修订差异比较Definition。
        string toHash;
        if (fromRevision.HasValue && toRevision.HasValue && fromReleaseId is null && toReleaseId is null)
        {
            // 每个读取都验证完整当前ACL，不能以左边权限代替右边。
            var first = await ReadDraftAsync(actor, session, mappingId, fromRevision, token);
            // 右边修订不存在时不能用当前头替代。
            var second = await ReadDraftAsync(actor, session, mappingId, toRevision, token);
            before = first.Mapping;
            after = second.Mapping;
            fromHash = first.MappingHash;
            toHash = second.MappingHash;
        }
        else if (fromRevision is null && toRevision is null && fromReleaseId is not null && toReleaseId is not null)
        {
            // 完整历史原件保持各自canonical身份。
            var first = await ReadReleaseAsync(actor, session, fromReleaseId, token);
            // 不能跨mapping借用目标Release。
            var second = await ReadReleaseAsync(actor, session, toReleaseId, token);
            if (first.Manifest.MappingId != mappingId || second.Manifest.MappingId != mappingId)
            {
                throw Conflict();
            }
            before = first.Manifest;
            after = second.Manifest;
            fromHash = first.ManifestHash;
            toHash = second.ManifestHash;
        }
        else
        {
            throw new SemanticOperationException(400, "mapping_payload_invalid");
        }
        // 数组顺序按canonical固定，业务复合键顺序仍有意义。
        using var left = JsonDocument.Parse(MappingCanonical.Serialize(before));
        // 右边内容独立规范化，差异不会由JSON对象键序引起。
        using var right = JsonDocument.Parse(MappingCanonical.Serialize(after));
        // 限定两个一MiB对象，差异数量再受预算限制。
        var changes = new List<MappingDifference>();
        Differences(left.RootElement, right.RootElement, string.Empty, changes);
        return new MappingDiffView { MappingId = mappingId, FromHash = fromHash, ToHash = toHash, Changes = changes.ToArray() };
    }

    /// <summary>对象递归精确比较；数组保留整体有序语义，不模糊匹配业务键。</summary>
    private static void Differences(JsonElement before, JsonElement after, string path, List<MappingDifference> changes)
    {
        if (before.ValueKind == JsonValueKind.Object && after.ValueKind == JsonValueKind.Object)
        {
            foreach (var name in before.EnumerateObject().Select(item => item.Name).Union(after.EnumerateObject().Select(item => item.Name)).Order(StringComparer.Ordinal))
            {
                // JSON指针需要转义斜线和波浪符，不能拼成不准确路径。
                var child = path + "/" + name.Replace("~", "~0", StringComparison.Ordinal).Replace("/", "~1", StringComparison.Ordinal);
                // 缺字段保持Undefined，与显式null不同。
                var hasBefore = before.TryGetProperty(name, out var oldValue);
                // 两侧存在性独立记录。
                var hasAfter = after.TryGetProperty(name, out var newValue);
                if (hasBefore && hasAfter)
                {
                    Differences(oldValue, newValue, child, changes);
                }
                else
                {
                    changes.Add(new MappingDifference
                    {
                        Path = child,
                        BeforeExists = hasBefore,
                        AfterExists = hasAfter,
                        Before = hasBefore ? oldValue.Clone() : null,
                        After = hasAfter ? newValue.Clone() : null
                    });
                }
            }
        }
        else if (!JsonElement.DeepEquals(before, after))
        {
            changes.Add(new MappingDifference { Path = path, BeforeExists = true, AfterExists = true, Before = before.Clone(), After = after.Clone() });
        }
        if (changes.Count > 256)
        {
            throw new SemanticOperationException(422, "mapping_diff_budget_exceeded");
        }
    }

    /// <summary>游标签名校验失败不泄漏DataProtection内部错误。</summary>
    private MappingCursorState ReadCursor(string cursor)
    {
        try
        {
            if (cursor.Length > 8192)
            {
                throw new CryptographicException();
            }
            return Decode<MappingCursorState>(cursorProtector.Unprotect(cursor));
        }
        catch (Exception error) when (error is CryptographicException or JsonException or FormatException)
        {
            throw new SemanticOperationException(409, "mapping_cursor_stale");
        }
    }

    /// <summary>读取原Assessment，当前源权限缩减不能通过旧报告泄漏字段。</summary>
    public async Task<MappingAssessmentView> ReadAssessmentAsync(ActorContext actor, string session, string assessmentId, CancellationToken token)
    {
        G4MappingRules.Identifier(assessmentId);
        // 同组织过滤先于报告正文解析。
        await using var db = await factory.CreateDbContextAsync(token);
        // 原件永远保留固定Mapping目标。
        var row = await db.MappingAssessments.AsNoTracking().SingleOrDefaultAsync(item => item.Id == assessmentId && item.OrganizationId == actor.OrganizationId, token)
            ?? throw Forbidden();
        // 两种hash校验都必须通过。
        var report = await AssessmentAsync(db, row.MappingId, assessmentId, token);
        // 固定目标不是当前最新草稿。
        var draft = await TargetAsync(actor, row.MappingId, report.Target, token);
        await ReadAccessAsync(actor, session, draft, token);
        return report;
    }

    /// <summary>历史正式原件与当前可用性投影分离，永不更新Manifest。</summary>
    public async Task<MappingReleaseView> ReadReleaseAsync(ActorContext actor, string session, string releaseId, CancellationToken token)
    {
        G4MappingRules.Identifier(releaseId);
        // 在本模块读取原件，不借Publishing保存MappingRelease。
        await using var db = await factory.CreateDbContextAsync(token);
        // 未授权组织一律不披露存在性。
        var row = await db.MappingReleases.AsNoTracking().SingleOrDefaultAsync(item => item.Id == releaseId && item.OrganizationId == actor.OrganizationId, token)
            ?? throw Forbidden();
        // 先校验不可变原字节，再定位完整源字段权限。
        var manifest = Original<MappingReleaseManifest>(row.CanonicalBytes, row.ContentHash);
        // 回滚目标只是读取历史定义的严格内部判别。
        var draft = await TargetAsync(actor, row.MappingId, new MappingRollbackTarget { TargetReleaseId = row.Id, ManifestHash = row.ContentHash }, token);
        // 当前指针独立读取，历史release存在不代表仍在使用。
        var active = await db.MappingActives.AsNoTracking().SingleOrDefaultAsync(item => item.MappingId == row.MappingId, token);
        // 活跃制品使用本次Activation的兼容Binding，不用旧Manifest秘密版本执行。
        var reasons = active?.ReleaseId == releaseId ? await UsabilityAsync(actor, session, draft, active, token) : new[] { "mapping_release_inactive" };
        // 只读取编辑头修订用于后续调度CAS，不读取最新草稿字段或定义。
        var currentRevision = await db.Mappings.Where(item => item.Id == row.MappingId).Select(item => item.Revision).SingleAsync(token);
        // 可用性投影会容忍失效前提，但原件正文必须在全部异步观察之后再次核实当前字段权限。
        await ReadAccessAsync(actor, session, draft, token);
        return new MappingReleaseView
        {
            Manifest = manifest,
            ManifestHash = row.ContentHash,
            ReadOnly = true,
            Projection = new MappingReleaseProjection
            {
                CurrentDraftRevision = currentRevision,
                Active = active?.ReleaseId == releaseId,
                ActivationRevision = active?.ActivationRevision ?? 0,
                Usable = reasons.Length == 0,
                ReasonCodes = reasons,
                ObservedAtUtc = clock.GetUtcNow()
            }
        };
    }

    /// <summary>源不可用时仍可返回已授权的非敏感指针摘要，不返回历史字段正文。</summary>
    public async Task<MappingActiveView> ReadActiveAsync(ActorContext actor, string session, string mappingId, CancellationToken token)
    {
        // 根scope和mapping.read先验证，404不会泄漏未授权资源。
        await using var db = await factory.CreateDbContextAsync(token);
        // 永久根只用于scope，不读取最新Draft作为旧Release替代。
        var root = await RootAsync(db, actor, mappingId, token);
        // 摘要访问必须仍有明确读取grant。
        var proof = await validation.CaptureAsync(actor, session, new ResourceScope { OrganizationId = root.OrganizationId, SiteIds = root.SiteIds }, "mapping.read", token);
        // 没有指针才是404，源下线不是没有指针。
        var active = await db.MappingActives.AsNoTracking().SingleOrDefaultAsync(row => row.MappingId == mappingId, token)
            ?? throw new SemanticOperationException(404, "mapping_active_missing");
        // 原hash来自不可变Release存储，响应不包含原定义。
        var release = await db.MappingReleases.AsNoTracking().SingleAsync(row => row.Id == active.ReleaseId, token);
        // 固定目标用于尝试核实当前可用性，无法核验时不返回字段内容。
        var draft = await TargetAsync(actor, mappingId, new MappingRollbackTarget { TargetReleaseId = release.Id, ManifestHash = release.ContentHash }, token);
        // 当前状态只说明最后观察窗口，不承诺源未来不变。
        var reasons = await UsabilityAsync(actor, session, draft, active, token);
        // 网络检查之后再次确认当前摘要许可，撤权立即403。
        var after = await validation.CaptureAsync(actor, session, proof.Scope, "mapping.read", token);
        if (after.AuthorizationEpoch != proof.AuthorizationEpoch)
        {
            throw Forbidden();
        }
        return new MappingActiveView
        {
            MappingId = mappingId,
            MappingReleaseId = active.ReleaseId,
            ManifestHash = release.ContentHash,
            ActivationRevision = active.ActivationRevision,
            Usable = reasons.Length == 0,
            ReasonCodes = reasons
        };
    }

    /// <summary>只检查当前使用前提，不把激活前旧Active基线拿来判定激活后的指针。</summary>
    private async Task<string[]> UsabilityAsync(ActorContext actor, string session, MappingDraftView draft, MappingActiveRecord active, CancellationToken token)
    {
        try
        {
            // 当前字段grant与源实际SELECT权限缺一不可。
            var proofs = await AccessAsync(actor, session, draft, "mapping.read", token);
            await validation.VerifyReadAccessAsync(draft, token);
            // 使用本次激活持久的兼容版本，历史Manifest保持原样。
            await using var db = await factory.CreateDbContextAsync(token);
            // 只有成功激活才存在对应当前绑定原件。
            var activation = await db.MappingActivations.AsNoTracking().SingleAsync(row => row.Id == active.ActivationId, token);
            // 当前Binding来自同事务Activation，不从客户端状态重建。
            var binding = Decode<MappingVersionBinding>(activation.BindingJson);
            // 真实连接和目录要素必须仍与激活时一致。
            var current = await validation.InputsAsync(draft, token);
            return current.Connection.Revision != binding.ConnectionRevision || current.Connection.ConfigHash != binding.ConfigHash
                || current.Connection.SecretVersion != binding.SecretVersion || current.Current.SnapshotId != binding.SourceCatalogSnapshotId
                || current.Current.SchemaFingerprint != binding.SourceCatalogFingerprint || proofs[0].AuthorizationEpoch != binding.AuthorizationEpoch
                ? ["mapping_revalidation_required"] : [];
        }
        catch (SemanticOperationException)
        {
            return ["mapping_revalidation_required"];
        }
    }

    /// <summary>仅完整、当前且未到期Assessment可以形成一次性固定提案。</summary>
    public async Task<MappingProposalView> ProposeAsync(ActorContext actor, string session, string mappingId, MappingProposalCreateRequest request, CancellationToken token)
    {
        G4MappingRules.Validate(request);
        // 发布与回滚目标在公开合同和加载路径上均分离。
        var target = ProposalTarget(request);
        // 固定目标用于完整源字段授权，不接收客户端替代正文。
        var draft = await TargetAsync(actor, mappingId, target, token);
        if (Digest(request.Scope) != Digest(draft.Scope))
        {
            throw Forbidden();
        }
        // 提交权限不等审核或激活权限。
        var proofs = await AccessAsync(actor, session, draft, "mapping.submit", token);
        return await CommandAsync<MappingProposalView>(mappingId, draft.Scope, draft.SourceConnectionId, "propose", request, request.Command, null, proofs,
            async (db, cancellation) =>
            {
                // 锁内重读不可变报告，禁止客户端自报通过。
                var report = await AssessmentAsync(db, mappingId, request.Binding.AssessmentId, cancellation);
                if (report.Status != "READY_FOR_PROPOSAL" || report.Stages.Length != 7 || report.Stages.Any(stage => stage.Status != "PASS"))
                {
                    throw new SemanticOperationException(422, "mapping_assessment_incomplete");
                }
                if (Digest(report.Binding) != Digest(request.Binding) || Digest(report.Target) != Digest(target)
                    || Digest(report.ExpectedActive) != Digest(request.ExpectedActive) || report.MappingId != mappingId)
                {
                    throw Conflict();
                }
                // 期限不得延长至任何原评估或当前提交授权之后。
                var now = clock.GetUtcNow();
                if (request.ExpiresAtUtc <= now || report.ExpiresAtUtc <= now)
                {
                    throw new SemanticOperationException(409, "mapping_approval_stale");
                }
                if (request.ExpiresAtUtc > now.AddHours(24) || request.ExpiresAtUtc > proofs.Min(item => item.ExpiresAtUtc)
                    || request.ExpiresAtUtc > report.ExpiresAtUtc)
                {
                    throw new SemanticOperationException(422, "mapping_expiry_invalid");
                }
                await CurrentAsync(db, draft, target, request.Binding, request.ExpectedActive, proofs[0].AuthorizationEpoch, cancellation);
                if (request is MappingPublishProposalRequest publish && publish.DraftId != draft.DraftId)
                {
                    throw Conflict();
                }
                // 公开原文排除内部session证明，固定服务器时间与主体。
                var proposal = new MappingProposalRecord
                {
                    Id = NewId("proposal"),
                    MappingId = mappingId,
                    OrganizationId = draft.Scope.OrganizationId,
                    SiteIds = draft.Scope.SiteIds,
                    CreatedAtUtc = DatabaseTime(now),
                    Kind = request is MappingPublishProposalRequest ? "PUBLISH" : "ROLLBACK",
                    RequestBytes = MappingCanonical.Serialize<MappingProposalCreateRequest>(request),
                    SubmittedBy = actor.SubjectId,
                    SubmitProofJson = Encode(proofs[0]),
                    ExpiresAtUtc = DatabaseTime(request.ExpiresAtUtc)
                };
                proposal.BindingHash = ProposalHash(ProposalView(proposal));
                db.MappingProposals.Add(proposal);
                return ProposalView(proposal);
            }, "mapping.proposal.create", token);
    }

    /// <summary>固定提案详情始终使用当前读取与源字段权限。</summary>
    public async Task<MappingProposalView> ReadProposalAsync(ActorContext actor, string session, string proposalId, CancellationToken token)
    {
        // 不向其它组织披露提案存在性。
        var proposal = await LoadProposalAsync(actor, proposalId, token);
        // 读历史受审目标，不能换成当前草稿的字段许可。
        var request = Decode<MappingProposalCreateRequest>(proposal.RequestBytes);
        // 精确判别分支决定固定正文来源。
        var draft = await TargetAsync(actor, proposal.MappingId, ProposalTarget(request), token);
        await ReadAccessAsync(actor, session, draft, token);
        // 终态回执和原决定保持历史事实，过期只改变投影。
        var view = ProposalView(proposal);
        if (proposal.ActivationId is not null)
        {
            // 唯一Activation原件不从Active当前值倒推。
            await using var db = await factory.CreateDbContextAsync(token);
            // 同一提案只能一份成功激活原件。
            var activation = await db.MappingActivations.AsNoTracking().SingleAsync(row => row.Id == proposal.ActivationId, token);
            view = view with { Activation = Original<MappingActivationReceipt>(activation.CanonicalBytes, activation.ContentHash) };
        }
        if (proposal.ActivationId is null && proposal.Status is "PENDING" or "APPROVED")
        {
            if (proposal.ExpiresAtUtc <= clock.GetUtcNow())
            {
                return view with { Status = "EXPIRED" };
            }
            try
            {
                // 只读当前版本投影，不写提案状态或抹去原异人决定。
                await using var current = await factory.CreateDbContextAsync(token);
                // 当前读取权限epoch用于识别原审批失效，读权限不替代原submit权限。
                var access = await validation.CaptureAsync(actor, session, draft.Scope, "mapping.read", token);
                await CurrentAsync(current, draft, ProposalTarget(request), request.Binding, request.ExpectedActive, access.AuthorizationEpoch, token);
            }
            catch (SemanticOperationException error) when (error.Status == 409)
            {
                return view with { Status = "STALE" };
            }
        }
        return view;
    }

    /// <summary>异人审核固定目标；换浏览器或session不能绕过主体自批检查。</summary>
    public async Task<MappingProposalView> DecideAsync(ActorContext actor, string session, string proposalId, MappingDecisionRequest request, string? etag, CancellationToken token)
    {
        G4MappingRules.Command(request.Command, false);
        G4MappingRules.Hash(request.BindingHash);
        if (request.Decision is not ("APPROVE" or "REJECT"))
        {
            throw new SemanticOperationException(400, "mapping_payload_invalid");
        }
        // 事务外只作授权定位，事务内再检查状态和CAS。
        var found = await LoadProposalAsync(actor, proposalId, token);
        if (found.SubmittedBy == actor.SubjectId)
        {
            throw new SemanticOperationException(403, "mapping_self_review_forbidden");
        }
        // 固定原提案目标，不以当前Draft替代ROLLBACK。
        var original = Decode<MappingProposalCreateRequest>(found.RequestBytes);
        // 完整目标正文按当前字段ACL核验。
        var draft = await TargetAsync(actor, found.MappingId, ProposalTarget(original), token);
        // 审核角色与显式approve grant必须同时成立。
        var proofs = await AccessAsync(actor, session, draft, "mapping.approve", token);
        proofs = [.. proofs, Decode<MappingAuthorizationProof>(found.SubmitProofJson)];
        return await CommandAsync<MappingProposalView>(found.MappingId, draft.Scope, draft.SourceConnectionId, "decide:" + proposalId, request,
            request.Command, etag, proofs, async (db, cancellation) =>
            {
                // 锁内查询使并发批准或取消只成功一次。
                var proposal = await db.MappingProposals.SingleAsync(row => row.Id == proposalId, cancellation);
                Cas(etag, "proposal", proposal.Revision, request.Command);
                if (proposal.Status != "PENDING" || proposal.BindingHash != request.BindingHash || proposal.ExpiresAtUtc <= clock.GetUtcNow())
                {
                    throw Conflict();
                }
                await CurrentAsync(db, draft, ProposalTarget(original), original.Binding, original.ExpectedActive, proofs[0].AuthorizationEpoch, cancellation);
                proposal.DecidedBy = actor.SubjectId;
                proposal.DecidedAtUtc = DatabaseTime(clock.GetUtcNow());
                proposal.DecisionProofJson = Encode(proofs[0]);
                proposal.DecisionJson = Encode(new MappingDecision
                {
                    DecidedBy = actor.SubjectId,
                    DecidedAtUtc = proposal.DecidedAtUtc.Value,
                    Decision = request.Decision,
                    Reason = request.Command.Reason,
                    BindingHash = proposal.BindingHash
                });
                proposal.Status = request.Decision == "APPROVE" ? "APPROVED" : "REJECTED";
                proposal.Revision = Increment(proposal.Revision);
                return ProposalView(proposal);
            }, "mapping.decision", token);
    }

    /// <summary>提交者取消未激活提案，不能撤销已提交正式历史。</summary>
    public async Task<MappingProposalView> CancelProposalAsync(ActorContext actor, string session, string proposalId, MappingCommandRequest request, string? etag, CancellationToken token)
    {
        G4MappingRules.Command(request.Command, false);
        // 取消仍需当前授权，不能用旧session推断主体。
        var found = await LoadProposalAsync(actor, proposalId, token);
        if (found.SubmittedBy != actor.SubjectId)
        {
            throw Forbidden();
        }
        // 原目标完整读取以避免字段权限缩水后取回原回执。
        var draft = await TargetAsync(actor, found.MappingId, ProposalTarget(Decode<MappingProposalCreateRequest>(found.RequestBytes)), token);
        // 当前submit权限允许取消本人提案。
        var proofs = await AccessAsync(actor, session, draft, "mapping.submit", token);
        return await CommandAsync<MappingProposalView>(found.MappingId, draft.Scope, draft.SourceConnectionId, "cancel-proposal:" + proposalId,
            request, request.Command, etag, proofs, async (db, cancellation) =>
            {
                // 最新行状态而非事务外预读决定是否可取消。
                var proposal = await db.MappingProposals.SingleAsync(row => row.Id == proposalId, cancellation);
                Cas(etag, "proposal", proposal.Revision, request.Command);
                if (proposal.Status is not ("PENDING" or "APPROVED") || proposal.ActivationId is not null)
                {
                    throw Conflict();
                }
                proposal.Status = "CANCELLED";
                proposal.Revision = Increment(proposal.Revision);
                return ProposalView(proposal);
            }, "mapping.proposal.cancel", token);
    }

    /// <summary>当前平台输入在组织锁下逐项复核，源网络已在评估阶段完成。</summary>
    internal async Task CurrentAsync(ConnectionsDbContext db, MappingDraftView draft, MappingValidationTarget target, MappingVersionBinding binding,
        MappingExpectedActive expected, long epoch, CancellationToken token)
    {
        // 稳定mapping身份和完整scope不可被其它资源冒充。
        var root = await db.Mappings.SingleAsync(row => row.Id == draft.MappingId, token);
        if (root.OrganizationId != draft.Scope.OrganizationId || !root.SiteIds.Order(StringComparer.Ordinal).SequenceEqual(draft.Scope.SiteIds.Order(StringComparer.Ordinal))
            || root.SourceConnectionId != binding.SourceConnectionId || Digest(draft.Mapping) != binding.MappingHash
            || draft.OntologyReleaseId != binding.OntologyReleaseId || draft.OntologyManifestHash != binding.OntologyManifestHash
            || binding.AuthorizationEpoch != epoch || target is MappingPublishTarget publish && root.Revision != publish.DraftRevision)
        {
            throw Conflict();
        }
        // 连接写者使用同一advisory锁，轮换不能与提交交错。
        var connection = await db.Connections.SingleAsync(row => row.Id == binding.SourceConnectionId, token);
        if (connection.State != "ACTIVE" || connection.Revision != binding.ConnectionRevision || connection.ConfigHash != binding.ConfigHash
            || connection.SecretVersion != binding.SecretVersion || binding.AdapterVersion != "pg-mapping-v1"
            || binding.ExecutorVersion != "mapping-validator-v1" || binding.CanonicalVersion != "mapping-c14n-v1")
        {
            throw Conflict();
        }
        // 当前完整目录必须仍为受审原件，不接受静默重新扫描后的替代ID。
        var catalog = await db.CatalogSnapshots.AsNoTracking().Where(row => row.ConnectionId == connection.Id
            && row.ConfigHash == connection.ConfigHash && row.SecretVersion == connection.SecretVersion)
            .OrderByDescending(row => row.CapturedAtUtc).ThenByDescending(row => row.Id).FirstOrDefaultAsync(token);
        if (catalog is null || catalog.Id != binding.SourceCatalogSnapshotId
            || ConnectionApplicationService.Decode<CatalogSnapshotView>(catalog.ViewJson).SchemaFingerprint != binding.SourceCatalogFingerprint)
        {
            throw Conflict();
        }
        // 当前Active与全产品依赖索引共同决定原影响分析是否仍成立。
        var impact = await validation.ImpactAsync(draft, token);
        if (impact.Hash != binding.ImpactHash || Digest(impact.Active) != Digest(expected))
        {
            throw Conflict();
        }
    }

    /// <summary>固定Assessment原字节及内部validationHash均独立重算。</summary>
    internal static async Task<MappingAssessmentView> AssessmentAsync(ConnectionsDbContext db, string mappingId, string assessmentId, CancellationToken token)
    {
        // 请求ID必须与当前永久映射关联，不能借用另一映射的PASS。
        var row = await db.MappingAssessments.AsNoTracking().SingleOrDefaultAsync(item => item.Id == assessmentId && item.MappingId == mappingId, token)
            ?? throw new SemanticOperationException(409, "mapping_assessment_missing");
        // 原件字节校验与逻辑受审散列校验分列。
        var report = Original<MappingAssessmentView>(row.CanonicalBytes, row.ContentHash);
        if (MappingValidationService.AssessmentHash(report) != report.Binding.ValidationHash)
        {
            throw new SemanticOperationException(409, "mapping_artifact_integrity_failed");
        }
        return report;
    }

    /// <summary>读取同组织的原提案；调用者随后核验完整scope与源权限。</summary>
    internal async Task<MappingProposalRecord> LoadProposalAsync(ActorContext actor, string proposalId, CancellationToken token)
    {
        G4MappingRules.Identifier(proposalId);
        // 内部持久证明不作为公开DTO返回。
        await using var db = await factory.CreateDbContextAsync(token);
        // 本组织过滤先于任何正文解析。
        var proposal = await db.MappingProposals.AsNoTracking().SingleOrDefaultAsync(row => row.Id == proposalId && row.OrganizationId == actor.OrganizationId, token)
            ?? throw Forbidden();
        ConnectionApplicationService.DemandScope(actor, new ResourceScope { OrganizationId = proposal.OrganizationId, SiteIds = proposal.SiteIds });
        if (ProposalHash(ProposalView(proposal)) != proposal.BindingHash)
        {
            throw new SemanticOperationException(409, "mapping_artifact_integrity_failed");
        }
        return proposal;
    }

    /// <summary>严格分支转换，不容许回滚混入草稿修订条件。</summary>
    internal static MappingValidationTarget ProposalTarget(MappingProposalCreateRequest request) => request switch
    {
        MappingPublishProposalRequest publish => new MappingPublishTarget { DraftRevision = publish.DraftRevision },
        MappingRollbackProposalRequest rollback => new MappingRollbackTarget { TargetReleaseId = rollback.TargetReleaseId, ManifestHash = rollback.ManifestHash },
        _ => throw new SemanticOperationException(400, "mapping_payload_invalid")
    };

    /// <summary>提案只投影安全字段，内部会话和源行永不进入JSON。</summary>
    internal static MappingProposalView ProposalView(MappingProposalRecord row)
    {
        // 固定请求只有严格PUBLISH/ROLLBACK两种，不转换成松散字典。
        var request = Decode<MappingProposalCreateRequest>(row.RequestBytes);
        // 暂用分支初始化器随后填入共有不可变与变化字段。
        MappingProposalView view = request switch
        {
            MappingPublishProposalRequest publish => new MappingPublishProposalView
            {
                DraftId = publish.DraftId,
                DraftRevision = publish.DraftRevision,
                SchemaVersion = request.SchemaVersion,
                ProposalId = row.Id,
                MappingId = row.MappingId,
                ProposalRevision = row.Revision,
                Scope = request.Scope,
                Binding = request.Binding,
                ExpectedActive = request.ExpectedActive,
                SubmittedBy = row.SubmittedBy,
                SubmittedAtUtc = row.CreatedAtUtc,
                ExpiresAtUtc = row.ExpiresAtUtc,
                Status = row.Status,
                Decision = row.DecisionJson is null ? null : Decode<MappingDecision>(row.DecisionJson),
                BindingHash = row.BindingHash,
                Activation = null
            },
            MappingRollbackProposalRequest rollback => new MappingRollbackProposalView
            {
                TargetReleaseId = rollback.TargetReleaseId,
                ManifestHash = rollback.ManifestHash,
                SchemaVersion = request.SchemaVersion,
                ProposalId = row.Id,
                MappingId = row.MappingId,
                ProposalRevision = row.Revision,
                Scope = request.Scope,
                Binding = request.Binding,
                ExpectedActive = request.ExpectedActive,
                SubmittedBy = row.SubmittedBy,
                SubmittedAtUtc = row.CreatedAtUtc,
                ExpiresAtUtc = row.ExpiresAtUtc,
                Status = row.Status,
                Decision = row.DecisionJson is null ? null : Decode<MappingDecision>(row.DecisionJson),
                BindingHash = row.BindingHash,
                Activation = null
            },
            _ => throw new SemanticOperationException(409, "mapping_artifact_integrity_failed")
        };
        return view;
    }

    /// <summary>提案散列只覆盖冻结字段，决定与当前状态不能自引用。</summary>
    internal static string ProposalHash(MappingProposalView view)
    {
        // 用基类判别序列化保留kind，排除明确列出的变化字段。
        var fields = JsonSerializer.SerializeToElement(view, G4MappingJson.Options).EnumerateObject()
            .Where(field => field.Name is not ("status" or "decision" or "activation" or "proposalRevision" or "bindingHash"))
            .ToDictionary(field => field.Name, field => field.Value, StringComparer.Ordinal);
        return Digest(fields);
    }

    /// <summary>成功激活重放先检查当前平台权限，再恢复原收据，不重新运行源验证。</summary>
    internal async Task<MappingActivationReceipt?> ActivationReplayAsync(string mappingId, ResourceScope scope, string operation,
        MappingActivationRequest request, string? etag, MappingAuthorizationProof[] proofs, CancellationToken token)
    {
        // 回执只有ID和审计事实，没有历史字段正文；当前完整平台grant仍必需。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        deadline.CancelAfter(TimeSpan.FromSeconds(5));
        // 幂等键算法与CommandAsync完全相同。
        var key = Digest(new { scope, mappingId, operation, request.Command.IdempotencyKey });
        // 完整payload包括If-Match，修改任何命令输入都会冲突。
        var payloadHash = Digest(new { payload = JsonSerializer.SerializeToElement(request, G4MappingJson.Options), etag });
        // 短事务只读回执并锁当前授权，不执行源IO。
        await using var db = await factory.CreateDbContextAsync(deadline.Token);
        // Governance参与者必须加入调用方物理事务。
        await using var transaction = await db.Database.BeginTransactionAsync(deadline.Token);
        foreach (var proof in proofs.OrderBy(item => item.Permission, StringComparer.Ordinal))
        {
            await authority.DemandInTransactionAsync(proof, db.Database.GetDbConnection(), transaction.GetDbTransaction(), deadline.Token);
        }
        // 原成功回执不可变，读到即已提交；查不到由正式Command处理并发。
        var previous = await db.MappingCommands.AsNoTracking().SingleOrDefaultAsync(row => row.Id == key, deadline.Token);
        if (previous is null)
        {
            return null;
        }
        if (previous.SubjectId != proofs[0].Actor.SubjectId || previous.PayloadHash != payloadHash || previous.CommandId != request.Command.CommandId)
        {
            throw new SemanticOperationException(409, "mapping_idempotency_conflict");
        }
        return Decode<MappingActivationReceipt>(previous.ResponseBytes);
    }

    /// <summary>短事务固定所有授权、资源版本、幂等回执与同物理审计。</summary>
    internal async Task<T> CommandAsync<T>(string mappingId, ResourceScope scope, string connectionId, string operation, object payload,
        CommandContext command, string? etag, MappingAuthorizationProof[] proofs,
        Func<ConnectionsDbContext, CancellationToken, Task<T>> execute, string action, CancellationToken token, bool auditWritten = false)
    {
        // 平台短事务总期限包含授权锁与审计，外部网络不得进入委托。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        deadline.CancelAfter(TimeSpan.FromSeconds(5));
        token = deadline.Token;
        // 原请求包含If-Match及命令ID，重放不能改变预期版本或理由。
        var payloadHash = Digest(new { payload = JsonSerializer.SerializeToElement(payload, payload.GetType(), G4MappingJson.Options), etag });
        // 幂等唯一性不能包含主体，否则其他主体会重复执行同一个键。
        var key = Digest(new { scope, mappingId, operation, command.IdempotencyKey });
        // 使用非池化上下文支持Governance加入同一个物理连接事务。
        await using var db = await factory.CreateDbContextAsync(token);
        // 组织epoch是所有跨site操作的第一把锁。
        await using var transaction = await db.Database.BeginTransactionAsync(token);
        foreach (var proof in proofs.OrderBy(item => item.Actor.SubjectId, StringComparer.Ordinal).ThenBy(item => item.SessionReference, StringComparer.Ordinal).ThenBy(item => item.Permission, StringComparer.Ordinal))
        {
            if (Digest(proof.Scope) != Digest(scope) || proof.Actor.OrganizationId != scope.OrganizationId)
            {
                throw Forbidden();
            }
            await authority.DemandInTransactionAsync(proof, db.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
        }
        await ConnectionApplicationService.LockAsync(db, "connection:" + connectionId, token);
        await ConnectionApplicationService.LockAsync(db, "mapping:" + mappingId, token);
        // 原回执只有原主体、同payload和commandId才可恢复；先复核当前权限。
        var previous = await db.MappingCommands.AsNoTracking().SingleOrDefaultAsync(row => row.Id == key, token);
        if (previous is not null)
        {
            if (previous.SubjectId != proofs[0].Actor.SubjectId || previous.PayloadHash != payloadHash || previous.CommandId != command.CommandId)
            {
                throw new SemanticOperationException(409, "mapping_idempotency_conflict");
            }
            return Decode<T>(previous.ResponseBytes);
        }
        if (await db.MappingCommands.AnyAsync(row => row.OrganizationId == scope.OrganizationId && row.CommandId == command.CommandId, token))
        {
            throw new SemanticOperationException(409, "mapping_idempotency_conflict");
        }
        // 用例在锁内完成CAS并追加业务记录。
        var result = await execute(db, token);
        db.MappingCommands.Add(new MappingCommandRecord
        {
            Id = key,
            OrganizationId = scope.OrganizationId,
            SiteIds = scope.SiteIds,
            MappingId = mappingId,
            CreatedAtUtc = clock.GetUtcNow(),
            SubjectId = proofs[0].Actor.SubjectId,
            Operation = operation,
            CommandId = command.CommandId,
            IdempotencyKey = command.IdempotencyKey,
            PayloadHash = payloadHash,
            ResponseBytes = MappingCanonical.Serialize(result)
        });
        await db.SaveChangesAsync(token);
        if (!auditWritten)
        {
            _ = await audit.WriteAsync(proofs[0].Actor, new AuditCommand { Action = action, Resource = "mapping:" + mappingId, Outcome = "allowed", Scope = scope },
                db.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
        }
        await transaction.CommitAsync(token);
        return result;
    }

    /// <summary>读取服务端原字节并独立校验散列，避免损坏持久内容被当作原件。</summary>
    internal static T Original<T>(byte[] bytes, string hash)
    {
        if (Convert.ToHexStringLower(SHA256.HashData(bytes)) != hash)
        {
            throw new SemanticOperationException(409, "mapping_artifact_integrity_failed");
        }
        return Decode<T>(bytes);
    }

    /// <summary>读取完整历史正文前检查平台授权、真实源ACL，再复核平台epoch。</summary>
    internal async Task ReadAccessAsync(ActorContext actor, string session, MappingDraftView draft, CancellationToken token)
    {
        try
        {
            // 先权限后网络，未授权者不能触发源检查。
            var before = await AccessAsync(actor, session, draft, "mapping.read", token);
            await validation.VerifyReadAccessAsync(draft, token);
            // IO期间的撤权不能因旧预读证明而放行。
            var after = await AccessAsync(actor, session, draft, "mapping.read", token);
            if (before[0].AuthorizationEpoch != after[0].AuthorizationEpoch)
            {
                throw Forbidden();
            }
        }
        catch (SemanticOperationException error) when (error.Status is 409 or 422)
        {
            // 包含网络前InputsAsync失败；连接停用/目录失效不能作为编辑冲突保留旧正文。
            throw new SemanticOperationException(403, "mapping_source_access_unverified");
        }
    }

    /// <summary>动作与实际源字段全集分别捕获，必须处于相同组织授权版本。</summary>
    internal async Task<MappingAuthorizationProof[]> AccessAsync(ActorContext actor, string session, MappingDraftView draft, string permission, CancellationToken token)
    {
        // 先动作授权再读源绑定，避免无权者通过目录差异探测资源。
        var action = await validation.CaptureAsync(actor, session, draft.Scope, permission, token);
        // 字段权限按照固定目录及完整选择表求全集。
        var input = await validation.InputsAsync(draft, token);
        // 源字段当前许可不由管理连接角色替代。
        var source = await validation.CaptureSourceAsync(actor, session, draft.Scope, draft.SourceConnectionId, draft.Mapping, input.Current, token);
        if (action.AuthorizationEpoch != source.AuthorizationEpoch)
        {
            throw new SemanticOperationException(409, "mapping_authorization_stale");
        }
        return [action, source];
    }

    /// <summary>目标解析严格区分当前PUBLISH与历史ROLLBACK，后者不要求最新Draft相同。</summary>
    internal async Task<MappingDraftView> TargetAsync(ActorContext actor, string mappingId, MappingValidationTarget target, CancellationToken token)
    {
        if (target is MappingPublishTarget publish)
        {
            G4MappingRules.Revision(publish.DraftRevision);
            return await LoadDraftAsync(actor, mappingId, publish.DraftRevision, token);
        }
        if (target is not MappingRollbackTarget rollback)
        {
            throw new SemanticOperationException(400, "mapping_payload_invalid");
        }
        G4MappingRules.Identifier(rollback.TargetReleaseId);
        G4MappingRules.Hash(rollback.ManifestHash);
        // 历史原件必须同组织、同mapping且hash逐字节相等。
        await using var db = await factory.CreateDbContextAsync(token);
        // 不把任意同org Release借到另一个映射。
        var row = await db.MappingReleases.AsNoTracking().SingleOrDefaultAsync(item => item.Id == rollback.TargetReleaseId
            && item.MappingId == mappingId && item.OrganizationId == actor.OrganizationId, token) ?? throw Forbidden();
        if (row.ContentHash != rollback.ManifestHash)
        {
            throw Conflict();
        }
        // 回滚只使用历史定义与原目录，不修改历史绑定。
        var manifest = Original<MappingReleaseManifest>(row.CanonicalBytes, row.ContentHash);
        ConnectionApplicationService.DemandScope(actor, manifest.Scope);
        G4MappingRules.Definition(manifest.Mapping);
        // 字段引用保留编写时目录；Binding目录是发布前新检查，不能替换原引用。
        var originalCatalogs = manifest.Mapping.Entities.Select(entity => entity.DatasetRef.SnapshotId).Distinct(StringComparer.Ordinal).ToArray();
        if (originalCatalogs.Length != 1)
        {
            throw Conflict();
        }
        return new MappingDraftView
        {
            SchemaVersion = manifest.SchemaVersion,
            MappingId = mappingId,
            DraftId = manifest.OriginDraftId,
            Scope = manifest.Scope,
            OntologyReleaseId = manifest.Binding.OntologyReleaseId,
            OntologyManifestHash = manifest.Binding.OntologyManifestHash,
            SourceConnectionId = manifest.Binding.SourceConnectionId,
            SourceCatalogSnapshotId = originalCatalogs[0],
            Revision = manifest.OriginDraftRevision,
            MappingHash = manifest.Binding.MappingHash,
            Mapping = manifest.Mapping,
            Status = "DRAFT",
            UpdatedAtUtc = manifest.CreatedAtUtc
        };
    }

    /// <summary>加载不可变修订；当前状态投影绝不回填进旧修订原文。</summary>
    internal async Task<MappingDraftView> LoadDraftAsync(ActorContext actor, string mappingId, long? revision, CancellationToken token)
    {
        G4MappingRules.Identifier(mappingId);
        // 每个读使用独立上下文，避免共享追踪返回过时对象。
        await using var db = await factory.CreateDbContextAsync(token);
        // 长期身份负责完整资源scope，不能只比较厂区交集。
        var root = await RootAsync(db, actor, mappingId, token);
        // 未指定修订才使用当前头，深链历史永远固定其修订。
        var id = revision.HasValue ? RevisionId(mappingId, revision.Value) : root.CurrentRevisionId;
        // 历史原件的模块归属与MappingID再次核对。
        var row = await db.MappingRevisions.AsNoTracking().SingleOrDefaultAsync(item => item.Id == id && item.MappingId == mappingId, token)
            ?? throw Forbidden();
        return Original<MappingDraftView>(row.CanonicalBytes, row.ContentHash);
    }

    /// <summary>事务内加载真实根与完整scope，跨组织统一拒绝。</summary>
    internal static async Task<MappingRecord> RootAsync(ConnectionsDbContext db, ActorContext actor, string mappingId, CancellationToken token)
    {
        // 本组织过滤进入SQL，跨组织行不得进入应用层。
        var root = await db.Mappings.SingleOrDefaultAsync(row => row.Id == mappingId && row.OrganizationId == actor.OrganizationId, token)
            ?? throw Forbidden();
        ConnectionApplicationService.DemandScope(actor, new ResourceScope { OrganizationId = root.OrganizationId, SiteIds = root.SiteIds });
        return root;
    }

    /// <summary>追加完整规范化修订原件，数据库触发器防修改与删除。</summary>
    private static void AddRevision(ConnectionsDbContext db, string subject, MappingDraftView draft)
    {
        // canonical字节生成一次，hash与保存对象均绑定同一数组。
        var bytes = MappingCanonical.Serialize(draft);
        db.MappingRevisions.Add(new MappingRevisionRecord
        {
            Id = RevisionId(draft.MappingId, draft.Revision),
            MappingId = draft.MappingId,
            OrganizationId = draft.Scope.OrganizationId,
            SiteIds = draft.Scope.SiteIds,
            Revision = draft.Revision,
            DraftId = draft.DraftId,
            CanonicalBytes = bytes,
            ContentHash = Convert.ToHexStringLower(SHA256.HashData(bytes)),
            CreatedAtUtc = draft.UpdatedAtUtc,
            CreatedBy = subject
        });
    }

    /// <summary>任务读取模型从持久状态生成，不根据内存工作者猜测完成。</summary>
    internal static MappingJobView JobView(MappingJobRecord job) => new()
    {
        JobId = job.Id,
        MappingId = job.MappingId,
        Revision = job.Revision,
        Target = Decode<MappingJobInput>(job.RequestJson).Target,
        Status = job.Status,
        AssessmentId = job.ResultId,
        IssueCodes = job.ErrorCode is null ? [] : [job.ErrorCode],
        CreatedAtUtc = job.CreatedAtUtc,
        CompletedAtUtc = job.CompletedAtUtc
    };

    /// <summary>强ETag与正文预期修订必须同时匹配。</summary>
    internal static void Cas(string? etag, string kind, long revision, CommandContext command)
    {
        if (etag is null)
        {
            throw new SemanticOperationException(428, "revision_required");
        }
        if (etag != $"\"{kind}:{revision}\"" || command.ExpectedRevision != revision)
        {
            throw Conflict();
        }
    }

    /// <summary>生成有界且不可碰撞的服务器对象标识。</summary>
    internal static string NewId(string prefix) => prefix + "-" + Guid.NewGuid().ToString("N");

    /// <summary>保存修订的确定性身份，不使用排序不稳定的显示名。</summary>
    internal static string RevisionId(string mapping, long revision) => mapping + ":" + revision.ToString(System.Globalization.CultureInfo.InvariantCulture);

    /// <summary>严格递增，超出JSON安全整数上界拒绝。</summary>
    internal static long Increment(long value) => value >= G4MappingRules.MaximumRevision ? throw Conflict() : checked(value + 1);

    /// <summary>受审关系列在散列前统一到PostgreSQL微秒精度，保持初次响应、重读和原审核回执完全一致。</summary>
    /// <param name="value">服务器UTC时刻或已经校验的绝对截止。</param>
    /// <returns>只向下截断不足一微秒的UTC值，不延长任何授权期限。</returns>
    public static DateTimeOffset DatabaseTime(DateTimeOffset value) => new(value.UtcTicks - value.UtcTicks % 10, TimeSpan.Zero);

    /// <summary>规范字节散列，与HTTP重序列化无关。</summary>
    internal static string Digest<T>(T value) => MappingValidationService.Digest(value);

    /// <summary>内部持久JSON沿映射严格UTC与封闭合同。</summary>
    internal static string Encode<T>(T value) => JsonSerializer.Serialize(value, G4MappingJson.Options);

    /// <summary>读取服务端自己保存的严格内部模型。</summary>
    internal static T Decode<T>(string value) => JsonSerializer.Deserialize<T>(value, G4MappingJson.Options)
        ?? throw new SemanticOperationException(409, "mapping_artifact_integrity_failed");

    /// <summary>原件只由准确字节反序列化，不重建替代原hash。</summary>
    internal static T Decode<T>(byte[] value) => JsonSerializer.Deserialize<T>(value, G4MappingJson.Options)
        ?? throw new SemanticOperationException(409, "mapping_artifact_integrity_failed");

    /// <summary>统一当前版本冲突，不泄漏SQL或底层异常。</summary>
    internal static SemanticOperationException Conflict() => new(409, "mapping_version_conflict");

    /// <summary>未授权资源不返回存在性细节。</summary>
    internal static SemanticOperationException Forbidden() => new(403, "mapping_forbidden");
}

/// <summary>持久工作者固定输入，包含完整目标而不是最新头引用。</summary>
internal sealed record MappingJobInput
{
    /// <summary>不可变定义与长期身份。</summary>
    public required MappingDraftView Draft { get; init; }

    /// <summary>发布或回滚目标。</summary>
    public required MappingValidationTarget Target { get; init; }
}


/// <summary>有界列表索引，只从数据库投影标识和不可变创建时间。</summary>
internal sealed record MappingListCandidate
{
    /// <summary>对象标识。</summary>
    public required string Id { get; init; }

    /// <summary>创建时刻排序键。</summary>
    public required DateTimeOffset CreatedAtUtc { get; init; }
}

/// <summary>签名游标内部载荷，不能由HTTP正文直接构造。</summary>
internal sealed record MappingCursorState
{
    /// <summary>主体、scope、端点及全部筛选的散列。</summary>
    public required string Identity { get; init; }

    /// <summary>首次授权组织版本。</summary>
    public required long Epoch { get; init; }

    /// <summary>首屏真实PG事务可见性快照。</summary>
    public required string Snapshot { get; init; }

    /// <summary>五分钟固定截止，不在翻页续期。</summary>
    public required DateTimeOffset ExpiresAtUtc { get; init; }

    /// <summary>最后已扫描对象ID。</summary>
    public required string AfterId { get; init; }

    /// <summary>最后已扫描创建时间。</summary>
    public required DateTimeOffset AfterTime { get; init; }
}
