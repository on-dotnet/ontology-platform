using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Publishing.Domain;

namespace OntologyPlatform.Modules.Publishing;

/// <summary>固定审批内容，在外部回验后原子激活PG指针、治理审计及Outbox。</summary>
public sealed partial class PublishingService : IPublishingService
{
    /// <summary>仅写发布模块专属表。</summary>
    private readonly PublishingDbContext database;

    /// <summary>只通过Ontology应用用例读取草稿。</summary>
    private readonly IOntologyService ontology;

    /// <summary>由Ontology拥有同连接事务中的草稿锁定。</summary>
    private readonly IDraftPublicationReader drafts;

    /// <summary>审计仅由Governance自己的writer执行。</summary>
    private readonly ITransactionalAuditWriter audit;

    /// <summary>唯一真实SEM适配。</summary>
    private readonly ISemanticRuntime runtime;

    /// <summary>不可变S3对象边界。</summary>
    private readonly IReleaseArtifactStore artifacts;

    /// <summary>独立只读正式版本目录。</summary>
    private readonly IReleaseCatalog catalog;

    /// <summary>真实对象与图回验器。</summary>
    private readonly ReleaseVerifier verifier;

    /// <summary>审批有效期与激活事实时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>可选真实能力登记；未注册时版本数组为空。</summary>
    private readonly ISemanticGateway? gateway;

    /// <summary>显式注入模块应用边界，不依赖HTTP或其他模块表。</summary>
    public PublishingService(PublishingDbContext database, IOntologyService ontology, IDraftPublicationReader drafts, ITransactionalAuditWriter audit, ISemanticRuntime runtime, IReleaseArtifactStore artifacts, IReleaseCatalog catalog, ReleaseVerifier verifier, TimeProvider clock, ISemanticGateway? gateway = null)
    {
        this.database = database;
        this.ontology = ontology;
        this.drafts = drafts;
        this.audit = audit;
        this.runtime = runtime;
        this.artifacts = artifacts;
        this.catalog = catalog;
        this.verifier = verifier;
        this.clock = clock;
        this.gateway = gateway;
    }

    /// <summary>完整scope过滤真实提案，不返回未授权子厂区内容。</summary>
    public async Task<ReleaseProposal[]> ListProposalsAsync(ActorContext actor, CancellationToken cancellationToken)
    {
        PublishingRules.DemandRole(actor);
        // 先按组织在PG过滤，再按完整范围过滤。
        var rows = await database.Proposals.AsNoTracking().Where(row => row.OrganizationId == actor.OrganizationId).ToArrayAsync(cancellationToken);
        return rows.Where(row => PublishingRules.Covers(actor, Scope(row))).Select(row => JsonSerializer.Deserialize<ReleaseProposal>(row.ProposalJson)!).ToArray();
    }

    /// <summary>锁定当前验证草稿或权威旧manifest，并持久异人审批提案。</summary>
    public async Task<ReleaseProposal> CreateProposalAsync(ActorContext actor, CreateProposalRequest request, CancellationToken cancellationToken)
    {
        PublishingRules.DemandRole(actor, "platform.operator");
        PublishingRules.Command(request.Command);
        // 唯一合同检查发布/回滚互斥分支；应用调用不能绕过HTTP判别。
        ValidateWire(request);
        // 可空字段在共享传输合同中保留，业务层仍必须强制互斥分支与完整绑定。
        var validPublish = request.Kind == ProposalKind.Publish && !string.IsNullOrWhiteSpace(request.DraftId) && request.DraftRevision > 0 && request.Hashes is not null && !string.IsNullOrWhiteSpace(request.ValidationReportId) && request.TargetReleaseId is null && request.TargetManifestHash is null;
        // 回滚不能夹带草稿或报告字段把两条授权分支混合。
        var validRollback = request.Kind == ProposalKind.Rollback && request.DraftId is null && request.DraftRevision is null && request.Hashes is null && request.ValidationReportId is null && !string.IsNullOrWhiteSpace(request.TargetReleaseId) && IsHash(request.TargetManifestHash);
        if (!validPublish && !validRollback) throw new SemanticOperationException(422, "proposal_payload_invalid");
        // 发布草稿由Ontology授权；回滚范围先从PG正式版本事实取得。
        var draft = request.Kind == ProposalKind.Publish ? await ontology.ReadAsync(actor, request.DraftId!, cancellationToken) : null;
        // 回执恢复不依赖外部制品可用性，但目标必须是PG中真实已发布的版本。
        var target = request.Kind == ProposalKind.Rollback ? await database.Releases.AsNoTracking().SingleOrDefaultAsync(row => row.ReleaseId == request.TargetReleaseId && row.Published, cancellationToken) ?? throw new SemanticOperationException(404, "release_not_found") : null;
        // 真实源唯一确定资产和范围，客户端不能指定新asset或scope。
        var scope = draft?.Scope ?? new ResourceScope { OrganizationId = target!.OrganizationId, SiteIds = target.SiteIds };
        PublishingRules.DemandScope(actor, scope);
        return await WriteAsync(actor, scope, "release.proposal.create", request.Command, request, async token =>
        {
            // 新发布资格只取Ontology锁读的持久assessment，回滚完全不锁draft。
            DraftPublicationSnapshot? publication = null;
            if (draft is not null)
            {
                if (request.Command.ExpectedRevision != request.DraftRevision) throw new SemanticOperationException(409, "draft_revision_conflict");
                publication = await LockDraftAsync(actor, request.DraftId!, request.DraftRevision!.Value, request.Hashes!, request.ValidationReportId!, token);
                if (publication.Semantics is null) throw new SemanticOperationException(409, "assessment_required");
            }
            else
            {
                // 仅首次命令完整回验外部对象与图；已提交回执已在WriteAsync中核对主体和完整载荷。
                var verified = await catalog.ReadAsync(actor, target!.ReleaseId, token);
                if (verified.ManifestHash != request.TargetManifestHash) throw new SemanticOperationException(409, "rollback_binding_conflict");
            }
            // 固定24小时期限，所有审批和激活都以服务器时间再次判断。
            var now = clock.GetUtcNow();
            // 精确合同由服务端身份、校验事实和不可变目标组成。
            var proposal = new ReleaseProposal
            {
                ProposalId = Guid.NewGuid().ToString("N"),
                Kind = request.Kind,
                AssetId = draft?.AssetId ?? target!.AssetId,
                Scope = scope,
                DraftId = request.DraftId,
                DraftRevision = request.DraftRevision,
                Hashes = request.Hashes,
                ValidationReportId = request.ValidationReportId,
                Semantics = publication?.Semantics,
                TargetReleaseId = request.TargetReleaseId,
                TargetManifestHash = request.TargetManifestHash,
                SubmittedBy = actor.SubjectId,
                SubmittedAtUtc = now,
                ExpiresAtUtc = now.AddHours(24),
                Status = ProposalStatus.Pending,
                Revision = 1
            };
            database.Proposals.Add(new ProposalRecord { ProposalId = proposal.ProposalId, AssetId = proposal.AssetId, OrganizationId = scope.OrganizationId, SiteIds = scope.SiteIds, ProposalJson = JsonSerializer.Serialize(proposal), Revision = 1 });
            return (proposal, proposal.ProposalId);
        }, cancellationToken);
    }

    /// <summary>独立审核者的决定绑定完整不可变提案，并采用提案修订CAS。</summary>
    public async Task<ReleaseProposal> DecideAsync(ActorContext actor, string proposalId, ApprovalDecisionRequest request, CancellationToken cancellationToken)
    {
        PublishingRules.DemandRole(actor, "platform.auditor");
        PublishingRules.Command(request.Command);
        ValidateWire(request);
        // 先读scope授权；事务内按同一提案主键重新锁定。
        var known = await FindProposalAsync(proposalId, false, cancellationToken);
        PublishingRules.DemandScope(actor, Scope(known));
        return await WriteAsync(actor, Scope(known), "release.approval.decide", request.Command, new { proposalId, request }, async token =>
        {
            // 先锁draft再锁proposal，与创建及激活统一顺序；auditor只做只读核验。
            var original = JsonSerializer.Deserialize<ReleaseProposal>(known.ProposalJson)!;
            if (original.Kind == ProposalKind.Publish && original.Semantics is null) throw new SemanticOperationException(409, "assessment_required");
            // 回滚保留旧绑定算法并不依赖当前草稿。
            var snapshot = original.Kind == ProposalKind.Publish ? await LockDraftAsync(actor, original.DraftId!, original.DraftRevision!.Value, original.Hashes!, original.ValidationReportId!, token) : null;
            var row = await FindProposalAsync(proposalId, true, token);
            // 审批资格与内容均从真实记录取得。
            var proposal = JsonSerializer.Deserialize<ReleaseProposal>(row.ProposalJson)!;
            CheckPublicationSemantics(proposal, snapshot);
            if (row.Revision != request.Command.ExpectedRevision || proposal.Status != ProposalStatus.Pending || row.Activated) throw new SemanticOperationException(409, "proposal_revision_conflict");
            if (proposal.ExpiresAtUtc <= clock.GetUtcNow()) throw new SemanticOperationException(409, "proposal_expired");
            if (!PublishingPolicy.CanApprove(actor.SubjectId, actor.Roles, proposal.SubmittedBy, clock.GetUtcNow(), proposal.ExpiresAtUtc)) throw new SemanticOperationException(403, "independent_approval_required");
            // 审批散列排除审批自身和可变状态，永久绑定原始授权内容。
            var decision = new ApprovalRecord { ApprovedBy = actor.SubjectId, Decision = request.Decision, DecidedAtUtc = clock.GetUtcNow(), BindingHash = PublishingRules.Binding(proposal) };
            // 仅PENDING可变一次，之后更改需要新提案和新异人决定。
            var result = proposal with { Approval = decision, Revision = proposal.Revision + 1, Status = request.Decision == ApprovalDecision.Approve ? ProposalStatus.Approved : ProposalStatus.Rejected };
            row.Revision = result.Revision;
            row.ProposalJson = JsonSerializer.Serialize(result);
            return (result, proposalId);
        }, cancellationToken);
    }

    /// <summary>只返回已成功激活过的版本，缺对象或图保持明确不可用。</summary>
    public async Task<ReleaseSummary[]> ListReleasesAsync(ActorContext actor, string? assetId, CancellationToken cancellationToken)
    {
        PublishingRules.DemandRole(actor);
        // 活动及历史正式版本都保留，同一资产不删除旧版。
        var rows = await database.Releases.AsNoTracking().Where(row => row.Published && row.OrganizationId == actor.OrganizationId && (assetId == null || row.AssetId == assetId)).ToArrayAsync(cancellationToken);
        // 每个正式版本复用唯一只读Catalog的授权和真实回验。
        var result = new List<ReleaseSummary>();
        // 每个已获完整范围授权的正式历史行都真实回验。
        foreach (var row in rows.Where(row => PublishingRules.Covers(actor, new ResourceScope { OrganizationId = row.OrganizationId, SiteIds = row.SiteIds })))
        {
            result.Add(await catalog.ReadAsync(actor, row.ReleaseId, cancellationToken));
        }
        return result.ToArray();
    }

    /// <summary>业务、回执和Governance审计同事务提交，同键并发按PG锁串行。</summary>
    private async Task<T> WriteAsync<T>(ActorContext actor, ResourceScope scope, string action, CommandContext command, object payload, Func<CancellationToken, Task<(T Result, string Resource)>> mutation, CancellationToken token) where T : class
    {
        // 结构化完整范围防止分隔符和首厂区碰撞。
        var key = PublishingRules.Key(scope, action, command.IdempotencyKey);
        // 原样完整请求及command参与绑定，修改reason也不是相同命令。
        var hash = PublishingRules.Hash(JsonSerializer.Serialize(payload));
        // 此事务将本模块事实、幂等回执及治理审计绑定成一次提交。
        await using var transaction = await database.Database.BeginTransactionAsync(token);
        await LockKeyAsync(key, token);
        // 相同命令在锁后只返回实际提交的持久回执。
        var replay = await database.Commands.SingleOrDefaultAsync(row => row.Key == key, token);
        if (replay is not null)
        {
            CheckReplay(replay, actor, hash);
            if (replay.ResultJson is not null) return JsonSerializer.Deserialize<T>(replay.ResultJson)!;
        }
        try
        {
            // 只由明确用例委托修改本模块事实。
            var result = await mutation(token);
            database.Commands.Add(new PublishingCommandRecord { Key = key, PayloadHash = hash, SubjectId = actor.SubjectId, ResultJson = JsonSerializer.Serialize(result.Result) });
            await database.SaveChangesAsync(token);
            await audit.WriteAsync(actor, new AuditCommand { Action = action, Resource = result.Resource, Outcome = "allowed", Scope = scope }, database.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
            await transaction.CommitAsync(token);
            return result.Result;
        }
        finally
        {
            database.ChangeTracker.Clear();
        }
    }

    /// <summary>由Ontology在当前同物理PG事务内只读锁定草稿，不跨模块写表。</summary>
    private Task<DraftPublicationSnapshot> LockDraftAsync(ActorContext actor, string draftId, long revision, SourceHashes hashes, string reportId, CancellationToken token) => drafts.LockForPublicationAsync(actor, draftId, revision, hashes, reportId, database.Database.GetDbConnection(), database.Database.CurrentTransaction!.GetDbTransaction(), token);

    /// <summary>每个发布阶段重新比较锁读的评估绑定，旧提案不能直接新激活。</summary>
    private static void CheckPublicationSemantics(ReleaseProposal proposal, DraftPublicationSnapshot? snapshot)
    {
        if (proposal.Kind != ProposalKind.Publish) return;
        if (proposal.Semantics is null || snapshot?.Semantics is null) throw new SemanticOperationException(409, "assessment_required");
        if (proposal.Semantics != snapshot.Semantics) throw new SemanticOperationException(409, "assessment_binding_conflict");
    }

    /// <summary>仅参数化主键取锁，锁定顺序由调用用例明确安排。</summary>
    private async Task<ProposalRecord> FindProposalAsync(string proposalId, bool locked, CancellationToken token) => await
        (locked ? database.Proposals.FromSqlInterpolated($"SELECT * FROM publishing.\"Proposals\" WHERE \"ProposalId\"={proposalId} FOR UPDATE") : database.Proposals.AsNoTracking().Where(row => row.ProposalId == proposalId)).SingleOrDefaultAsync(token) ?? throw new SemanticOperationException(404, "proposal_not_found");

    /// <summary>数据库事务级锁自动随事务释放，支持多进程同键串行。</summary>
    private Task LockKeyAsync(string key, CancellationToken token) => database.Database.ExecuteSqlInterpolatedAsync($"SELECT pg_advisory_xact_lock(hashtextextended({key}, 0))", token);

    /// <summary>主体或任何载荷变化都不能读取另一命令的回执。</summary>
    private static void CheckReplay(PublishingCommandRecord row, ActorContext actor, string hash)
    {
        if (row.SubjectId != actor.SubjectId || row.PayloadHash != hash) throw new SemanticOperationException(409, "idempotency_conflict");
    }

    /// <summary>真实提案存储的完整资源范围。</summary>
    private static ResourceScope Scope(ProposalRecord row) => new() { OrganizationId = row.OrganizationId, SiteIds = row.SiteIds };

    /// <summary>固定清单SHA256必须为64位小写十六进制。</summary>
    private static bool IsHash(string? hash) => hash is { Length: 64 } && hash.All(value => char.IsAsciiDigit(value) || value is >= 'a' and <= 'f');

    /// <summary>对非HTTP调用也执行唯一DTO的严格非空和枚举校验。</summary>
    private static void ValidateWire<T>(T request)
    {
        try
        {
            JsonSerializer.Serialize(request);
        }
        catch (JsonException)
        {
            throw new SemanticOperationException(422, "proposal_payload_invalid");
        }
    }
}
