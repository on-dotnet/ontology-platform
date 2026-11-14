using System.Security.Cryptography;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>独立新鲜复核后原子激活或回滚，不修改历史MappingRelease。</summary>
public sealed class MappingActivationService
{
    /// <summary>Connections独占持久化。</summary>
    private readonly IDbContextFactory<ConnectionsDbContext> factory;

    /// <summary>复用应用命令、完整授权和幂等恢复。</summary>
    private readonly MappingApplicationService application;

    /// <summary>七项真实评估，外部IO全部在平台事务外。</summary>
    private readonly MappingValidationService validation;

    /// <summary>治理持有会话、授权及组织锁。</summary>
    private readonly IMappingAuthorizationAuthority authority;

    /// <summary>同物理事务的审计事实。</summary>
    private readonly ITransactionalAuditWriter audit;

    /// <summary>统一UTC时钟，用于30秒检查期限。</summary>
    private readonly TimeProvider clock;

    /// <summary>只组合本模块与稳定技术合同，不写本体事实。</summary>
    public MappingActivationService(IDbContextFactory<ConnectionsDbContext> factory, MappingApplicationService application,
        MappingValidationService validation, IMappingAuthorizationAuthority authority, ITransactionalAuditWriter audit, TimeProvider clock)
    {
        this.factory = factory;
        this.application = application;
        this.validation = validation;
        this.authority = authority;
        this.audit = audit;
        this.clock = clock;
    }

    /// <summary>人工批准后生成独立ActivationCheck，再以原基线CAS一次性提交。</summary>
    public async Task<MappingActivationReceipt> ActivateAsync(ActorContext actor, string session, string proposalId,
        MappingActivationRequest request, string? etag, CancellationToken token)
    {
        G4MappingRules.Command(request.Command, false);
        G4MappingRules.Hash(request.BindingHash);
        G4MappingRules.Active(request.ExpectedActive);
        // 原提案先按组织和全部scope授权，不接受客户端目标替换。
        var proposal = await application.LoadProposalAsync(actor, proposalId, token);
        // 严格判别原PUBLISH或ROLLBACK。
        var original = MappingApplicationService.Decode<MappingProposalCreateRequest>(proposal.RequestBytes);
        // 完整目标来自不可变修订或Release原字节。
        var target = MappingApplicationService.ProposalTarget(original);
        // 回滚不会从最新Draft取定义。
        var draft = await application.TargetAsync(actor, proposal.MappingId, target, token);
        // 当前激活者需精确action及全部实际源字段授权。
        var proofs = await application.AccessAsync(actor, session, draft, "mapping.activate", token);
        // 已成功提交后的断网恢复不重新访问源或追加审计。
        var replay = await application.ActivationReplayAsync(proposal.MappingId, draft.Scope, "activate:" + proposalId, request, etag, proofs, token);
        if (replay is not null)
        {
            return replay;
        }
        DemandApproved(proposal, original, request, etag);
        // 原提交和审核证明必须都存在，审核按subject而非session区别。
        var submit = MappingApplicationService.Decode<MappingAuthorizationProof>(proposal.SubmitProofJson);
        // 审核证明只能由异人审核命令创建。
        var review = MappingApplicationService.Decode<MappingAuthorizationProof>(proposal.DecisionProofJson!);
        // 提交、审核及激活者进入同一组织锁域；过期/撤权不能靠旧Actor通过。
        var parties = proofs.Concat([submit, review]).ToArray();
        await VerifyPartiesAsync(parties, token);
        // 原受审报告不可覆盖，验证其字节与逻辑hash。
        await using var lookup = await factory.CreateDbContextAsync(token);
        // 评估归属和原ID必须精确匹配提案。
        var assessment = await MappingApplicationService.AssessmentAsync(lookup, proposal.MappingId, original.Binding.AssessmentId, token);
        if (assessment.ExpiresAtUtc < proposal.ExpiresAtUtc || assessment.ExpiresAtUtc <= clock.GetUtcNow()
            || MappingApplicationService.Digest(assessment.Binding) != MappingApplicationService.Digest(original.Binding))
        {
            throw MappingApplicationService.Conflict();
        }
        // 网络新检查单独持久化，失败原件也保留供当前有权用户恢复。
        var check = await CheckAsync(actor, session, proposal, original, draft, target, assessment, proofs, token);
        if (check.Stages.Length != 7 || check.Stages.Any(stage => stage.Status != "PASS"))
        {
            throw new MappingActivationCheckException(check.CheckId, "mapping_activation_check_failed");
        }
        return await application.CommandAsync(proposal.MappingId, draft.Scope, draft.SourceConnectionId, "activate:" + proposalId, request,
            request.Command, etag, parties, async (db, cancellation) =>
            {
                // 组织/会话/授权、连接、mapping均已锁，读取最终提案状态。
                var current = await db.MappingProposals.SingleAsync(row => row.Id == proposalId, cancellation);
                DemandApproved(current, original, request, etag);
                if (check.ExpiresAtUtc <= clock.GetUtcNow() || clock.GetUtcNow() - check.CheckedAtUtc > TimeSpan.FromSeconds(30))
                {
                    throw new MappingActivationCheckException(check.CheckId, "mapping_activation_check_expired");
                }
                await application.CurrentAsync(db, draft, target, original.Binding, original.ExpectedActive, proofs[0].AuthorizationEpoch, cancellation);
                // Check必须是已独立提交且与当前提案绑定的同一原件。
                var storedCheck = await db.MappingActivationChecks.AsNoTracking().SingleAsync(row => row.Id == check.CheckId, cancellation);
                if (storedCheck.ProposalId != proposalId || storedCheck.BindingHash != proposal.BindingHash
                    || MappingApplicationService.Digest(MappingApplicationService.Original<MappingActivationCheck>(storedCheck.CanonicalBytes, storedCheck.ContentHash))
                        != MappingApplicationService.Digest(check))
                {
                    throw MappingApplicationService.Conflict();
                }
                // 当前指针锁受永久mapping根保护，首次不存在也不能双创建。
                var active = await db.MappingActives.SingleOrDefaultAsync(row => row.MappingId == proposal.MappingId, cancellation);
                if ((active?.ReleaseId) != request.ExpectedActive.ReleaseId || (active?.ActivationRevision ?? 0) != request.ExpectedActive.ActivationRevision)
                {
                    throw MappingApplicationService.Conflict();
                }
                // Release标识及hash仅由服务端原件决定。
                string releaseId;
                // 独立hash在生成canonical原件后计算，不写入原件自引用。
                string manifestHash;
                if (original is MappingPublishProposalRequest publish)
                {
                    releaseId = MappingApplicationService.NewId("release");
                    // 原发布保留原Assessment及异人审批事实，不改成新观察报告ID。
                    var manifest = new MappingReleaseManifest
                    {
                        SchemaVersion = "g4.mapping.v1",
                        MappingReleaseId = releaseId,
                        MappingId = proposal.MappingId,
                        Scope = draft.Scope,
                        OriginDraftId = publish.DraftId,
                        OriginDraftRevision = publish.DraftRevision,
                        Binding = original.Binding,
                        Mapping = draft.Mapping,
                        CreatedAtUtc = clock.GetUtcNow(),
                        ReviewReceipt = new MappingReviewReceipt
                        {
                            ProposalId = proposalId,
                            BindingHash = proposal.BindingHash,
                            SubmittedBy = proposal.SubmittedBy,
                            DecidedBy = proposal.DecidedBy!,
                            DecidedAtUtc = proposal.DecidedAtUtc!.Value
                        }
                    };
                    // canonical数组只产生一次，数据库hash约束检查相同字节。
                    var bytes = MappingCanonical.Serialize(manifest);
                    manifestHash = Convert.ToHexStringLower(SHA256.HashData(bytes));
                    db.MappingReleases.Add(new MappingReleaseRecord
                    {
                        Id = releaseId,
                        MappingId = proposal.MappingId,
                        OrganizationId = draft.Scope.OrganizationId,
                        SiteIds = draft.Scope.SiteIds,
                        CanonicalBytes = bytes,
                        ContentHash = manifestHash,
                        CreatedAtUtc = manifest.CreatedAtUtc
                    });
                }
                else
                {
                    // 回滚读取旧Release，绝不创建它的替代版本或覆盖旧绑定。
                    var rollback = (MappingRollbackProposalRequest)original;
                    // 同映射/组织范围再次确认，不借任意发布ID作为目标。
                    var old = await db.MappingReleases.AsNoTracking().SingleAsync(row => row.Id == rollback.TargetReleaseId
                        && row.MappingId == proposal.MappingId && row.OrganizationId == draft.Scope.OrganizationId, cancellation);
                    // 原字节与完整scope必须相同，不能裁剪旧制品。
                    var manifest = MappingApplicationService.Original<MappingReleaseManifest>(old.CanonicalBytes, old.ContentHash);
                    if (old.ContentHash != rollback.ManifestHash || MappingApplicationService.Digest(manifest.Scope) != MappingApplicationService.Digest(draft.Scope))
                    {
                        throw MappingApplicationService.Conflict();
                    }
                    releaseId = old.Id;
                    manifestHash = old.ContentHash;
                }
                // 三个新ID在同事务内固定，提交失败不成为对外事实。
                var activationId = MappingApplicationService.NewId("activation");
                // outbox只传映射身份及版本，不携带敏感源行。
                var eventId = MappingApplicationService.NewId("event");
                // revision包括回滚单调递增，不能以releaseId比较替代防ABA。
                var nextRevision = MappingApplicationService.Increment(active?.ActivationRevision ?? 0);
                // 审计由Governance写入同物理事务，返回未提交事实ID。
                var auditId = await audit.WriteAsync(actor, new AuditCommand
                {
                    Action = original is MappingPublishProposalRequest ? "mapping.activate" : "mapping.rollback",
                    Resource = "mapping:" + proposal.MappingId,
                    Outcome = "allowed",
                    Scope = draft.Scope
                }, db.Database.GetDbConnection(),
                    db.Database.CurrentTransaction!.GetDbTransaction(), cancellation);
                // 原回执只在外层事务成功提交后返回。
                var receipt = new MappingActivationReceipt
                {
                    ActivationId = activationId,
                    MappingId = proposal.MappingId,
                    ProposalId = proposalId,
                    Kind = proposal.Kind,
                    MappingReleaseId = releaseId,
                    ManifestHash = manifestHash,
                    PreviousReleaseId = active?.ReleaseId,
                    ActivationRevision = nextRevision,
                    AuditId = auditId,
                    OutboxEventId = eventId,
                    ActivatedAtUtc = clock.GetUtcNow()
                };
                // 回执原件不随当前Active改变。
                var receiptBytes = MappingCanonical.Serialize(receipt);
                db.MappingActivations.Add(new MappingActivationRecord
                {
                    Id = activationId,
                    MappingId = proposal.MappingId,
                    OrganizationId = draft.Scope.OrganizationId,
                    SiteIds = draft.Scope.SiteIds,
                    CanonicalBytes = receiptBytes,
                    ContentHash = Convert.ToHexStringLower(SHA256.HashData(receiptBytes)),
                    CreatedAtUtc = receipt.ActivatedAtUtc,
                    ProposalId = proposalId,
                    ReleaseId = releaseId,
                    CheckId = check.CheckId,
                    BindingJson = MappingApplicationService.Encode(original.Binding),
                    ActivationRevision = nextRevision
                });
                if (active is null)
                {
                    active = new MappingActiveRecord
                    {
                        Id = proposal.MappingId,
                        MappingId = proposal.MappingId,
                        OrganizationId = draft.Scope.OrganizationId,
                        SiteIds = draft.Scope.SiteIds
                    };
                    db.MappingActives.Add(active);
                }
                active.ReleaseId = releaseId;
                active.ActivationRevision = nextRevision;
                active.ActivationId = activationId;
                current.ActivationId = activationId;
                current.Revision = MappingApplicationService.Increment(current.Revision);
                db.MappingOutboxs.Add(new MappingOutboxRecord
                {
                    Id = eventId,
                    MappingId = proposal.MappingId,
                    OrganizationId = draft.Scope.OrganizationId,
                    SiteIds = draft.Scope.SiteIds,
                    CreatedAtUtc = receipt.ActivatedAtUtc,
                    ReleaseId = releaseId,
                    ManifestHash = manifestHash,
                    ActivationRevision = nextRevision
                });
                return receipt;
            }, original is MappingPublishProposalRequest ? "mapping.activate" : "mapping.rollback", token, auditWritten: true);
    }

    /// <summary>读取已保存检查只做当前授权，不触发新的激活或七阶段运行。</summary>
    public async Task<MappingActivationCheck> ReadCheckAsync(ActorContext actor, string session, string checkId, CancellationToken token)
    {
        G4MappingRules.Identifier(checkId);
        // 只读检查原件必须属于当前组织。
        await using var db = await factory.CreateDbContextAsync(token);
        // 未授权对象不披露存在性。
        var row = await db.MappingActivationChecks.AsNoTracking().SingleOrDefaultAsync(item => item.Id == checkId && item.OrganizationId == actor.OrganizationId, token)
            ?? throw MappingApplicationService.Forbidden();
        // 提案详情负责原目标的当前平台和真实源字段ACL。
        _ = await application.ReadProposalAsync(actor, session, row.ProposalId, token);
        return MappingApplicationService.Original<MappingActivationCheck>(row.CanonicalBytes, row.ContentHash);
    }

    /// <summary>重新评估的观察值可以变化，但所有受审版本与语义不变量必须完全相同。</summary>
    private async Task<MappingActivationCheck> CheckAsync(ActorContext actor, string session, MappingProposalRecord proposal,
        MappingProposalCreateRequest original, MappingDraftView draft, MappingValidationTarget target, MappingAssessmentView assessment,
        MappingAuthorizationProof[] proofs, CancellationToken token)
    {
        // 正常结果或失败摘要都独立持久化，不覆盖原Assessment。
        MappingAssessmentView? observed = null;
        // 固定安全错误码，不保存源SQL异常正文。
        string? failure = null;
        try
        {
            observed = await validation.AssessAsync(actor, session, draft, target, "mapping.activate", token);
        }
        catch (SemanticOperationException error) when (error.Status != 403)
        {
            failure = error.Code;
        }
        catch (OperationCanceledException) when (!token.IsCancellationRequested)
        {
            failure = "mapping_assessment_budget_exceeded";
        }
        // 新报告的观察ID/hash不替代原受审ID；其他全部版本逐字段比较。
        if (observed is not null && (MappingApplicationService.Digest(observed.Binding with
        {
            AssessmentId = original.Binding.AssessmentId,
            ValidationHash = original.Binding.ValidationHash
        }) != MappingApplicationService.Digest(original.Binding)
            || observed.SemanticResultHash != assessment.SemanticResultHash
            || MappingApplicationService.Digest(observed.ExpectedActive) != MappingApplicationService.Digest(original.ExpectedActive)))
        {
            failure = "mapping_approval_stale";
        }
        // 即使源失败也如实标记七项NOT_RUN，不复制原报告的PASS。
        var stages = observed?.Stages ?? new[] { "SCHEMA", "IDENTITY", "TIME_UNIT", "SECURITY", "EXECUTABILITY", "RECONCILIATION", "IMPACT" }
            .Select(stage => new MappingStageResult
            {
                Stage = stage,
                Status = "NOT_RUN",
                IssueCodes = [failure ?? "mapping_check_unavailable"],
                EvidenceHash = MappingApplicationService.Digest(new { stage, failure })
            }).ToArray();
        if (failure is not null && observed is not null)
        {
            stages = stages.Select(stage => stage.Stage == "IMPACT" ? stage with { Status = "FAIL", IssueCodes = [.. stage.IssueCodes, failure] } : stage).ToArray();
        }
        // 检查时钟在真实网络观察结束后取值，期限不超过原提案。
        var now = clock.GetUtcNow();
        // 新证据只包含本轮摘要和时间，不改变原审批bindingHash。
        var check = new MappingActivationCheck
        {
            CheckId = MappingApplicationService.NewId("check"),
            ProposalId = proposal.Id,
            BindingHash = proposal.BindingHash,
            AssessmentId = original.Binding.AssessmentId,
            CheckedBinding = original.Binding,
            CheckedAtUtc = now,
            ExpiresAtUtc = new[] { now.AddSeconds(30), proposal.ExpiresAtUtc }.Min(),
            Stages = stages,
            SemanticResultHash = observed?.SemanticResultHash ?? MappingApplicationService.Digest(new { status = "NOT_RUN", failure }),
            EvidenceHash = MappingApplicationService.Digest(new { observed = observed?.EvidenceHash, failure, now, stages })
        };
        // 保存检查采用独立短事务，因此后续CAS失败也保留这次观察事实。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        deadline.CancelAfter(TimeSpan.FromSeconds(5));
        // 只有Connections写自己的检查表。
        await using var db = await factory.CreateDbContextAsync(deadline.Token);
        // 当前调用权限再次核验，撤权错误不附带checkId给未授权者。
        await using var transaction = await db.Database.BeginTransactionAsync(deadline.Token);
        foreach (var proof in proofs.OrderBy(item => item.Permission, StringComparer.Ordinal))
        {
            await authority.DemandInTransactionAsync(proof, db.Database.GetDbConnection(), transaction.GetDbTransaction(), deadline.Token);
        }
        // 检查原件使用唯一字节数组，触发器检查不可变和hash。
        var bytes = MappingCanonical.Serialize(check);
        db.MappingActivationChecks.Add(new MappingActivationCheckRecord
        {
            Id = check.CheckId,
            MappingId = proposal.MappingId,
            OrganizationId = draft.Scope.OrganizationId,
            SiteIds = draft.Scope.SiteIds,
            CanonicalBytes = bytes,
            ContentHash = Convert.ToHexStringLower(SHA256.HashData(bytes)),
            CreatedAtUtc = now,
            ProposalId = proposal.Id,
            BindingHash = proposal.BindingHash,
            ExpiresAtUtc = check.ExpiresAtUtc,
            Status = stages.All(stage => stage.Status == "PASS") ? "PASS" : "FAILED"
        });
        await db.SaveChangesAsync(deadline.Token);
        await transaction.CommitAsync(deadline.Token);
        return check;
    }

    /// <summary>IO前统一按主体和会话排序验证三方，任何失败整笔回滚。</summary>
    private async Task VerifyPartiesAsync(MappingAuthorizationProof[] proofs, CancellationToken token)
    {
        // 前置事务仅授权，不跨网络保留行锁。
        await using var db = await factory.CreateDbContextAsync(token);
        // Governance负责组织行锁与数据库两秒锁等待上限。
        await using var transaction = await db.Database.BeginTransactionAsync(token);
        foreach (var proof in proofs.OrderBy(item => item.Actor.SubjectId, StringComparer.Ordinal).ThenBy(item => item.SessionReference, StringComparer.Ordinal).ThenBy(item => item.Permission, StringComparer.Ordinal))
        {
            await authority.DemandInTransactionAsync(proof, db.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
        }
    }

    /// <summary>固定批准、异人、CAS、期限和原Active基线全部成立才允许激活。</summary>
    private void DemandApproved(MappingProposalRecord proposal, MappingProposalCreateRequest original, MappingActivationRequest request, string? etag)
    {
        MappingApplicationService.Cas(etag, "proposal", proposal.Revision, request.Command);
        if (proposal.Status != "APPROVED" || proposal.ActivationId is not null || proposal.DecidedBy is null || proposal.DecisionProofJson is null
            || proposal.DecidedBy == proposal.SubmittedBy || proposal.ExpiresAtUtc <= clock.GetUtcNow()
            || proposal.BindingHash != request.BindingHash || MappingApplicationService.Digest(request.ExpectedActive) != MappingApplicationService.Digest(original.ExpectedActive))
        {
            throw MappingApplicationService.Conflict();
        }
    }
}
