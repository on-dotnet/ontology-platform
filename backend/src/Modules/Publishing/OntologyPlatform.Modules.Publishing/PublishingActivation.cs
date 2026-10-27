using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Publishing;

/// <summary>发布准备、真实外部回验和最终短事务的显式协调。</summary>
public sealed partial class PublishingService
{
    /// <summary>同一命令先恢复已提交事实，再准备固定版本并严格CAS激活。</summary>
    public async Task<ReleaseActivation> ActivateAsync(ActorContext actor, ActivateReleaseRequest request, CancellationToken cancellationToken)
    {
        // 活动自动继承宿主当前Trace；标签仅使用固定阶段和值。
        using var activity = PublishingTelemetry.Activities.StartActivity("release.activate");
        PublishingRules.DemandRole(actor, "platform.operator");
        PublishingRules.Command(request.Command);
        ValidateWire(request);
        if (string.IsNullOrWhiteSpace(request.ProposalId) || request.ExpectedActivationRevision < 0) throw new SemanticOperationException(422, "activation_payload_invalid");
        // 即使重放也先重新授权当前可信主体的完整范围。
        var known = await FindProposalAsync(request.ProposalId, false, cancellationToken);
        PublishingRules.DemandScope(actor, Scope(known));
        // 发布/回滚分别具有独立固定审计及幂等操作空间。
        var proposal = JsonSerializer.Deserialize<ReleaseProposal>(known.ProposalJson)!;
        // 完整请求和主体绑定防止修改CAS参数后伪装重放。
        var action = proposal.Kind == ProposalKind.Publish ? "release.activate" : "release.rollback";
        // 幂等键不依赖当前活动值，响应丢失后仍能找到原事务。
        var key = PublishingRules.Key(proposal.Scope, action, request.Command.IdempotencyKey);
        // 载荷hash包括proposal和全部expected值及reason。
        var payloadHash = PublishingRules.Hash(JsonSerializer.Serialize(request));
        // 未接触外部服务前读取已提交回执，外部故障不阻断成功事实恢复。
        var receipt = await database.Commands.AsNoTracking().SingleOrDefaultAsync(row => row.Key == key, cancellationToken);
        if (receipt is not null)
        {
            CheckReplay(receipt, actor, payloadHash);
            if (receipt.ResultJson is not null) return JsonSerializer.Deserialize<ReleaseActivation>(receipt.ResultJson)!;
        }
        // 预留事务固定releaseId和manifest字节；同键并发只能得到同一版本。
        var prepared = await PrepareAsync(actor, request, proposal, key, payloadHash, cancellationToken);
        // 预留锁等待期间另一同键请求可能已经提交，再查回执避免重新访问故障外部依赖。
        var concurrentReceipt = await database.Commands.AsNoTracking().SingleAsync(row => row.Key == key, cancellationToken);
        if (concurrentReceipt.ResultJson is not null) return JsonSerializer.Deserialize<ReleaseActivation>(concurrentReceipt.ResultJson)!;
        try
        {
            if (proposal.Kind == ProposalKind.Publish && !prepared.Published)
            {
                // 所有源分别按固定内容hash键条件写，再回读精确字节。
                var sources = JsonSerializer.Deserialize<SourceBundle>(prepared.SourcesJson)!;
                // 固定manifest只包含源对象，不包含自身hash。
                var manifest = JsonSerializer.Deserialize<ReleaseManifest>(prepared.ManifestJson)!;
                // 源顺序由共享校验器定义，保持所有阶段一致。
                var contents = ReleaseVerifier.SourceContents(sources);
                // 索引绑定固定源对象顺序，防止回验时交换内容。
                for (var index = 0; index < contents.Length; index++)
                {
                    await artifacts.PutImmutableAsync(manifest.ArtifactObjects[index].ObjectKey, Encoding.UTF8.GetBytes(contents[index]), "text/turtle", cancellationToken);
                }
                // manifest本身独立hash-key对象，确保没有自包含hash循环。
                var manifestObject = JsonSerializer.Deserialize<ArtifactObject>(prepared.ManifestObjectJson)!;
                await artifacts.PutImmutableAsync(manifestObject.ObjectKey, Encoding.UTF8.GetBytes(prepared.ManifestJson), "application/json", cancellationToken);
                await verifier.VerifyArtifactsAsync(prepared, cancellationToken);
                await StateAsync(prepared.ReleaseId, "ARTIFACTS_VERIFIED", cancellationToken);
                await runtime.DeployAsync(manifest, sources, cancellationToken);
                await StateAsync(prepared.ReleaseId, "GRAPH_DEPLOYED", cancellationToken);
            }
            // 回滚只回读旧完整制品和图，绝不重建或覆盖历史图。
            await verifier.VerifyAsync(prepared, cancellationToken);
            if (!prepared.Published) await StateAsync(prepared.ReleaseId, "GRAPH_VERIFIED", cancellationToken);
            // 只有提交完成才计入成功结果。
            var result = await CommitActivationAsync(actor, request, proposal, prepared, key, payloadHash, action, cancellationToken);
            PublishingTelemetry.Record(proposal.Kind == ProposalKind.Publish ? "publish" : "rollback", "allowed", "commit");
            return result;
        }
        catch
        {
            PublishingTelemetry.Record(proposal.Kind == ProposalKind.Publish ? "publish" : "rollback", "failure", "prepare_or_commit");
            // 保留真实准备制品用于重试；失败标记不覆盖已经激活的并发成功事实。
            if (!prepared.Published)
            {
                try
                {
                    await StateAsync(prepared.ReleaseId, "FAILED_RETRYABLE", CancellationToken.None);
                }
                catch (Exception failure) when (failure is DbUpdateException or System.Data.Common.DbException)
                {
                }
            }
            throw;
        }
    }

    /// <summary>短预留事务按draft→proposal固定内容；不在事务内等待S3/Jena。</summary>
    private async Task<ReleaseRecord> PrepareAsync(ActorContext actor, ActivateReleaseRequest request, ReleaseProposal known, string key, string payloadHash, CancellationToken token)
    {
        // 当前短事务显式协调发布表与同物理连接的其他模块writer。
        await using var transaction = await database.Database.BeginTransactionAsync(token);
        await LockKeyAsync(key, token);
        // 预留必须同主体同完整请求，不能把不同命令粘到已有制品。
        var command = await database.Commands.SingleOrDefaultAsync(row => row.Key == key, token);
        if (command is not null)
        {
            CheckReplay(command, actor, payloadHash);
            // 成功事实可能在事务外初查之后刚提交；固定版本仍从原回执取回。
            if (command.ReleaseId is not null)
            {
                return await database.Releases.AsNoTracking().SingleAsync(row => row.ReleaseId == command.ReleaseId, token);
            }
        }
        if (known.Kind == ProposalKind.Publish && known.Semantics is null) throw new SemanticOperationException(409, "assessment_required");
        // PUBLISH先由Ontology锁当前精确修订；ROLLBACK完全不触碰当前draft。
        var snapshot = known.Kind == ProposalKind.Publish ? await LockDraftAsync(actor, known.DraftId!, known.DraftRevision!.Value, known.Hashes!, known.ValidationReportId!, token) : null;
        // 既有提案锁保证不同command也不会生成不同releaseId。
        var proposalRow = await FindProposalAsync(request.ProposalId, true, token);
        // 重新从锁定数据库事实校验审批，不信任事务前副本。
        var proposal = JsonSerializer.Deserialize<ReleaseProposal>(proposalRow.ProposalJson)!;
        CheckPublicationSemantics(proposal, snapshot);
        DemandApproved(actor, proposalRow, proposal, request.Command.ExpectedRevision);
        // 一个发布提案永远只有一个准备版本；回滚则取得原版本行锁。
        var release = proposal.Kind == ProposalKind.Publish
            ? await database.Releases.SingleOrDefaultAsync(row => row.ProposalId == proposal.ProposalId, token)
            : await database.Releases.FromSqlInterpolated($"SELECT * FROM publishing.\"Releases\" WHERE \"ReleaseId\"={proposal.TargetReleaseId} FOR UPDATE").SingleOrDefaultAsync(token);
        if (proposal.Kind == ProposalKind.Rollback)
        {
            DemandRollback(proposal, release);
        }
        else if (release is null)
        {
            release = CreateRelease(proposal, snapshot!.Draft);
            database.Releases.Add(release);
        }
        database.Commands.Add(new PublishingCommandRecord { Key = key, PayloadHash = payloadHash, SubjectId = actor.SubjectId, ReleaseId = release!.ReleaseId });
        await database.SaveChangesAsync(token);
        await transaction.CommitAsync(token);
        database.ChangeTracker.Clear();
        return release;
    }

    /// <summary>外部全回验后短事务原子锁定CAS、Governance审计、回执及Outbox。</summary>
    private async Task<ReleaseActivation> CommitActivationAsync(ActorContext actor, ActivateReleaseRequest request, ReleaseProposal known, ReleaseRecord prepared, string key, string payloadHash, string action, CancellationToken token)
    {
        database.ChangeTracker.Clear();
        // 当前短事务显式协调发布表与同物理连接的其他模块writer。
        await using var transaction = await database.Database.BeginTransactionAsync(token);
        await LockKeyAsync(key, token);
        // 锁内先恢复并发同命令成功结果，避免重复审核消费及重复审计。
        var command = await database.Commands.SingleAsync(row => row.Key == key, token);
        CheckReplay(command, actor, payloadHash);
        if (command.ResultJson is not null) return JsonSerializer.Deserialize<ReleaseActivation>(command.ResultJson)!;
        // 与审核/准备保持相同锁顺序，外部操作耗时不能延长assessment有效期。
        var snapshot = known.Kind == ProposalKind.Publish ? await LockDraftAsync(actor, known.DraftId!, known.DraftRevision!.Value, known.Hashes!, known.ValidationReportId!, token) : null;
        // 严格保持draft→proposal→active或proposal→旧release→active顺序。
        var proposalRow = await FindProposalAsync(request.ProposalId, true, token);
        // 事务内重核审批绑定和到期时间，外部准备耗时不能延长授权。
        var proposal = JsonSerializer.Deserialize<ReleaseProposal>(proposalRow.ProposalJson)!;
        CheckPublicationSemantics(proposal, snapshot);
        DemandApproved(actor, proposalRow, proposal, request.Command.ExpectedRevision);
        // 正式版本行在active之前锁，回滚不得绕过目标hash绑定。
        var release = await database.Releases.FromSqlInterpolated($"SELECT * FROM publishing.\"Releases\" WHERE \"ReleaseId\"={prepared.ReleaseId} FOR UPDATE").SingleAsync(token);
        if (release.ManifestHash != prepared.ManifestHash || release.ManifestJson != prepared.ManifestJson || command.ReleaseId != release.ReleaseId) throw new SemanticOperationException(409, "manifest_binding_conflict");
        if (proposal.Kind == ProposalKind.Rollback) DemandRollback(proposal, release);
        // 首次active尚无行时也按永久asset串行；之后仍使用数据库CAS列。
        await LockKeyAsync("active:" + proposal.AssetId, token);
        // 当前活动指针必须同时匹配ID和单调revision，防止ABA。
        var active = await database.ActiveReleases.SingleOrDefaultAsync(row => row.AssetId == proposal.AssetId, token);
        if ((active?.Revision ?? 0) != request.ExpectedActivationRevision || active?.ReleaseId != request.ExpectedActiveReleaseId) throw new SemanticOperationException(409, "activation_revision_conflict");
        if (active is not null && (active.OrganizationId != proposal.Scope.OrganizationId || !active.SiteIds.SequenceEqual(proposal.Scope.SiteIds))) throw new SemanticOperationException(409, "asset_scope_conflict");
        // 只在全部检查后构造递增修订，旧版本和旧Run快照完全保留。
        var revision = checked((active?.Revision ?? 0) + 1);
        // 审计writer与当前发布上下文显式共享同一物理连接和事务。
        var auditId = await audit.WriteAsync(actor, new AuditCommand { Action = action, Resource = release.ReleaseId, Outcome = "allowed", Scope = proposal.Scope }, database.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
        // 唯一事件ID也成为消费者去重主键。
        var eventId = Guid.NewGuid().ToString("N");
        // 精确持久时间和Trace来自服务器执行上下文。
        var now = clock.GetUtcNow();
        // 完整回执只在commit之后对外返回，丢响应按原JSON恢复。
        var result = new ReleaseActivation { ActivationId = Guid.NewGuid().ToString("N"), ActivationRevision = revision, ReleaseId = release.ReleaseId, PreviousReleaseId = active?.ReleaseId, ManifestHash = release.ManifestHash, Manifest = JsonSerializer.Deserialize<ReleaseManifest>(release.ManifestJson)!, AuditId = auditId, OutboxEventId = eventId, ActivatedAtUtc = now, TraceId = actor.TraceId };
        if (active is null)
        {
            active = new ActiveReleaseRecord { AssetId = proposal.AssetId, OrganizationId = proposal.Scope.OrganizationId, SiteIds = proposal.Scope.SiteIds };
            database.ActiveReleases.Add(active);
        }
        active.ReleaseId = release.ReleaseId;
        active.Revision = revision;
        release.Published = true;
        release.State = "ACTIVE";
        release.TraceId = actor.TraceId;
        proposalRow.Activated = true;
        command.ResultJson = JsonSerializer.Serialize(result);
        database.Activations.Add(new ActivationRecord { ActivationId = result.ActivationId, AssetId = proposal.AssetId, Revision = revision, ReleaseId = release.ReleaseId, ResultJson = command.ResultJson });
        database.Outbox.Add(new OutboxRecord { EventId = eventId, ReleaseId = release.ReleaseId, ActivationRevision = revision, EventType = proposal.Kind == ProposalKind.Publish ? "release.activated" : "release.rolled_back", PayloadHash = release.ManifestHash, CreatedAtUtc = now, NextAttemptAtUtc = now });
        try
        {
            await database.SaveChangesAsync(token);
            await transaction.CommitAsync(token);
            return result;
        }
        finally
        {
            database.ChangeTracker.Clear();
        }
    }

    /// <summary>从已锁草稿生成一次不可变清单，能力版本只来自已注册真实网关。</summary>
    private ReleaseRecord CreateRelease(ReleaseProposal proposal, OntologyDraft draft)
    {
        // GuidN完全由服务器生成，图IRI和对象命名空间不可由客户端注入。
        var id = Guid.NewGuid().ToString("N");
        // 本体和数据图永久按发布隔离。
        var ontologyGraph = "urn:ontology-platform:release:" + id + ":ontology";
        // 事实图与本体图共用同一发布身份。
        var dataGraph = "urn:ontology-platform:release:" + id + ":data";
        // 源对象使用内容散列键，字节长度用UTF8计量。
        var objects = ReleaseVerifier.SourceContents(draft.Sources).Select((value, index) => new ArtifactObject { ObjectKey = "releases/" + id + "/source-" + index + "-" + PublishingRules.Hash(value) + ".ttl", Hash = PublishingRules.Hash(value), SizeBytes = Encoding.UTF8.GetByteCount(value), ContentType = "text/turtle" }).ToArray();
        // 未实现mapping/metric/rule保持空；未注册QRY时不虚构capability版本。
        var snapshot = new AssetVersionSnapshot { ReleaseId = id, OntologyHash = draft.Hashes.OntologyHash, ShapesHash = draft.Hashes.ShapesHash, VocabularyHash = draft.Hashes.VocabularyHash, DataHash = draft.Hashes.DataHash, OntologyGraphIri = ontologyGraph, DataGraphIri = dataGraph, CapabilityVersions = gateway?.GetCapabilities().OrderBy(value => value.Id, StringComparer.Ordinal).Select(value => new AssetVersion { AssetId = value.Id, Version = value.Version }).ToArray() ?? [] };
        // 固定创建时间及序列化字节在所有重试中保留不变。
        var manifest = new ReleaseManifest { SchemaVersion = 2, Semantics = proposal.Semantics ?? throw new SemanticOperationException(409, "assessment_required"), ReleaseId = id, AssetId = draft.AssetId, Scope = draft.Scope, DraftId = draft.DraftId, Revision = draft.Revision, Hashes = draft.Hashes, OntologyGraphIri = ontologyGraph, DataGraphIri = dataGraph, Snapshot = snapshot, ArtifactObjects = objects, CreatedAtUtc = clock.GetUtcNow() };
        // 清单hash仅在PG和独立对象引用中保存，避免自包含循环。
        var json = JsonSerializer.Serialize(manifest);
        // 权威UTF8字节hash用于回滚审批和对象回验。
        var hash = PublishingRules.Hash(json);
        return new ReleaseRecord { ReleaseId = id, ProposalId = proposal.ProposalId, AssetId = draft.AssetId, OrganizationId = draft.Scope.OrganizationId, SiteIds = draft.Scope.SiteIds, ManifestJson = json, ManifestHash = hash, SourcesJson = JsonSerializer.Serialize(draft.Sources), ManifestObjectJson = JsonSerializer.Serialize(new ArtifactObject { ObjectKey = "releases/" + id + "/manifest-" + hash + ".json", Hash = hash, SizeBytes = Encoding.UTF8.GetByteCount(json), ContentType = "application/json" }) };
    }

    /// <summary>所有准备与最终提交都重新检查完整审批身份、内容、状态和有效期。</summary>
    private void DemandApproved(ActorContext actor, ProposalRecord row, ReleaseProposal proposal, long expectedRevision)
    {
        PublishingRules.DemandScope(actor, proposal.Scope);
        if (row.Activated || row.Revision != expectedRevision) throw new SemanticOperationException(409, "proposal_revision_conflict");
        if (proposal.ExpiresAtUtc <= clock.GetUtcNow()) throw new SemanticOperationException(409, "proposal_expired");
        if (proposal.Status != ProposalStatus.Approved || proposal.Approval is null || proposal.Approval.Decision != ApprovalDecision.Approve || proposal.Approval.ApprovedBy == proposal.SubmittedBy || proposal.Approval.BindingHash != PublishingRules.Binding(proposal)) throw new SemanticOperationException(409, "approval_required");
    }

    /// <summary>回滚只能命中同asset和完整scope的已正式发布目标。</summary>
    private static void DemandRollback(ReleaseProposal proposal, ReleaseRecord? release)
    {
        if (release is null || !release.Published || release.ManifestHash != proposal.TargetManifestHash || release.AssetId != proposal.AssetId || release.OrganizationId != proposal.Scope.OrganizationId || !release.SiteIds.SequenceEqual(proposal.Scope.SiteIds)) throw new SemanticOperationException(409, "rollback_binding_conflict");
    }

    /// <summary>准备状态仅更新尚未正式激活的版本，不允许失败覆盖并发成功。</summary>
    private Task StateAsync(string releaseId, string state, CancellationToken token) => database.Releases.Where(row => row.ReleaseId == releaseId && !row.Published).ExecuteUpdateAsync(update => update.SetProperty(row => row.State, state), token);
}
