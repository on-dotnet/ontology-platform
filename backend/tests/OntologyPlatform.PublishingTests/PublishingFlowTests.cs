using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.Publishing;

namespace OntologyPlatform.PublishingTests;

/// <summary>通过真实PG、治理writer、Jena和RustFS验证发布与旧完整版本回滚。</summary>
[TestClass]
public sealed class PublishingFlowTests
{
    /// <summary>实际两版发布后当前草稿已推进仍允许审批回滚R1，旧固定快照不改变。</summary>
    [TestMethod]
    public async Task PublishTwoVersionsRollbackOldCompleteManifestAndReplay()
    {
        // 当前测试独占组织和资产范围。
        using var fixture = new PublishingFixture();
        // 所有草稿和报告来自真实应用服务与Jena。
        var first = await fixture.ProposalAsync();
        // 独立审核者批准R1精确绑定。
        var approved = await fixture.ApproveAsync(first.Proposal);
        // 保存原命令验证响应丢失后的精确恢复。
        var request = PublishingFixture.Activation(approved);
        // R1实际完成S3/图/PG原子激活。
        var r1 = await fixture.Service.ActivateAsync(fixture.Author, request, default);
        Assert.AreEqual(1, r1.ActivationRevision);
        Assert.AreEqual(fixture.Author.TraceId, r1.TraceId);
        Assert.AreEqual(0, r1.Manifest.Snapshot.CapabilityVersions.Length);
        // 当前草稿发生真实新修订；原始源注释变化也有不同字节hash。
        var draft2 = await fixture.Ontology.SaveAsync(fixture.Author, first.Draft.DraftId, new SaveDraftRequest { Sources = first.Draft.Sources with { OntologyTurtle = first.Draft.Sources.OntologyTurtle + "\n# revision two\n" }, Command = PublishingFixture.Command(1) }, default);
        // R2必须重新真实验证和异人批准。
        var second = await fixture.ApproveAsync(await fixture.ProposalForAsync(draft2));
        // 新版本使用R1的完整活动CAS。
        var r2 = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(second, r1), default);
        Assert.AreEqual(2, r2.ActivationRevision);
        Assert.AreNotEqual(r1.ManifestHash, r2.ManifestHash);
        // 回滚只绑定旧正式manifest，当前草稿仍为revision2。
        var rollback = await fixture.Service.CreateProposalAsync(fixture.Author, new CreateProposalRequest { Kind = ProposalKind.Rollback, TargetReleaseId = r1.ReleaseId, TargetManifestHash = r1.ManifestHash, Command = PublishingFixture.Command() }, default);
        // 回滚必须独立重新审批，不能沿用原发布批准。
        var rollbackApproved = await fixture.ApproveAsync(rollback);
        // 正式回滚使用当前R2指针CAS，递增而不是回退revision。
        var restored = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(rollbackApproved, r2), default);
        Assert.AreEqual(r1.ManifestHash, restored.ManifestHash);
        Assert.AreEqual(3, restored.ActivationRevision);
        // ABA后releaseId再次相同也不能使用旧activationRevision绕过CAS。
        var abaProposal = await fixture.ApproveAsync(await fixture.Service.CreateProposalAsync(fixture.Author, new CreateProposalRequest { Kind = ProposalKind.Rollback, TargetReleaseId = r2.ReleaseId, TargetManifestHash = r2.ManifestHash, Command = PublishingFixture.Command() }, default));
        // 旧R1快照的ID吻合当前active，但revision1已经失效。
        var abaFailure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(abaProposal, r1), default));
        Assert.AreEqual("activation_revision_conflict", abaFailure.Code);
        Assert.AreEqual(2, (await fixture.Ontology.ReadAsync(fixture.Author, first.Draft.DraftId, default)).Revision);
        Assert.AreEqual(r2.ManifestHash, (await fixture.Catalog.ReadAsync(fixture.Author, r2.ReleaseId, default)).ManifestHash);
        Assert.AreEqual(r1.ManifestHash, (await fixture.Catalog.ResolveAsync(fixture.Author, first.Draft.AssetId, null, default)).ManifestHash);
        // 响应丢失重放即使依赖故障仍返回原已提交事实，不产生第二审计/Outbox。
        fixture.Gate = (_, _) => throw new HttpRequestException("test transport failure");
        Assert.AreEqual(JsonSerializer.Serialize(r1), JsonSerializer.Serialize(await fixture.Service.ActivateAsync(fixture.Author, request, default)));
        await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.ActivateAsync(fixture.Author, request with { ExpectedActivationRevision = 3 }, default));
        Assert.AreEqual(3, await fixture.Database.Activations.CountAsync(row => row.AssetId == first.Draft.AssetId));
        Assert.AreEqual(3, await fixture.Database.Outbox.CountAsync(row => row.ReleaseId == r1.ReleaseId || row.ReleaseId == r2.ReleaseId));
        fixture.Gate = null;
        // 真正Outbox消费者回验所有历史事件；旧事件不会把active切回旧通知值。
        var dispatcher = new ReleaseOutboxDispatcher(fixture.Provider.GetRequiredService<IServiceScopeFactory>(), fixture.Clock);
        while (await dispatcher.DispatchOnceAsync(default)) { }
        Assert.AreEqual(3, await fixture.Database.Receipts.CountAsync(row => row.ReleaseId == r1.ReleaseId || row.ReleaseId == r2.ReleaseId));
        Assert.IsFalse(await dispatcher.DispatchOnceAsync(default));
        Assert.AreEqual(3, (await fixture.Catalog.ResolveAsync(fixture.Author, first.Draft.AssetId, null, default)).ActivationRevision);
    }

    /// <summary>审核不允许自批、短角色和完整范围的部分厂区。</summary>
    [TestMethod]
    [DataRow("self", 403)]
    [DataRow("role", 403)]
    [DataRow("scope", 403)]
    [DataRow("expiry", 409)]
    public async Task ApprovalBoundaries(string condition, int status)
    {
        // 每条负例独立真实提案。
        using var fixture = new PublishingFixture();
        // 首先建立合法待审批事实，避免测试仅因不存在而失败。
        var item = await fixture.ProposalAsync();
        // 只改变当前负例对应的可信测试主体字段。
        var reviewer = condition switch
        {
            "self" => fixture.Author with { Roles = ["platform.operator", "platform.auditor"] },
            "role" => fixture.Reviewer with { Roles = ["auditor"] },
            "scope" => fixture.Reviewer with { SiteIds = ["site-a"] },
            _ => fixture.Reviewer
        };
        if (condition == "expiry") fixture.Clock.Offset = TimeSpan.FromHours(25);
        // 观察明确业务拒绝，而不是任意异常即通过。
        var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.DecideAsync(reviewer, item.Proposal.ProposalId, new ApprovalDecisionRequest { Decision = ApprovalDecision.Approve, Command = PublishingFixture.Command(1) }, default));
        Assert.AreEqual(status, failure.Status);
        Assert.AreEqual(0, await fixture.Database.Activations.CountAsync(row => row.AssetId == item.Draft.AssetId));
    }

    /// <summary>未批准、已拒绝、过期、修改后旧批准及错误CAS均不能激活。</summary>
    [TestMethod]
    [DataRow("pending")]
    [DataRow("rejected")]
    [DataRow("expiry")]
    [DataRow("changed")]
    [DataRow("cas")]
    public async Task ActivationBoundaries(string condition)
    {
        // 真正运行所有前置依赖。
        using var fixture = new PublishingFixture();
        // 合法真实提案作为负例基础。
        var item = await fixture.ProposalAsync();
        // pending负例保留原状态，其他负例取得实际审核决定。
        var proposal = condition == "pending" ? item.Proposal : await fixture.Service.DecideAsync(fixture.Reviewer, item.Proposal.ProposalId, new ApprovalDecisionRequest { Decision = condition == "rejected" ? ApprovalDecision.Reject : ApprovalDecision.Approve, Command = PublishingFixture.Command(1) }, default);
        if (condition == "expiry") fixture.Clock.Offset = TimeSpan.FromHours(25);
        if (condition == "changed") await fixture.Ontology.SaveAsync(fixture.Author, item.Draft.DraftId, new SaveDraftRequest { Sources = item.Draft.Sources with { DataTurtle = item.Draft.Sources.DataTurtle + "\n# advanced\n" }, Command = PublishingFixture.Command(1) }, default);
        // 错误活动修订必须在最终事务CAS时拒绝。
        var request = PublishingFixture.Activation(proposal) with { ExpectedActivationRevision = condition == "cas" ? 9 : 0 };
        // 每个负例都有明确409，外部服务正常不掩盖业务结果。
        var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.ActivateAsync(fixture.Author, request, default));
        Assert.AreEqual(409, failure.Status);
        Assert.AreEqual(0, await fixture.Database.Activations.CountAsync(row => row.AssetId == item.Draft.AssetId));
    }

    /// <summary>回滚目标散列篡改不能创建提案。</summary>
    [TestMethod]
    public async Task TamperedRollbackTargetRejected()
    {
        // 独立环境中的实际正式R1。
        using var fixture = new PublishingFixture();
        // 合法草稿与审批。
        var item = await fixture.ProposalAsync();
        // 创建真实不可变目标。
        var active = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(await fixture.ApproveAsync(item.Proposal)), default);
        // 仅篡改完整清单hash，不能沿用其他有效绑定。
        var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.CreateProposalAsync(fixture.Author, new CreateProposalRequest { Kind = ProposalKind.Rollback, TargetReleaseId = active.ReleaseId, TargetManifestHash = new string('0', 64), Command = PublishingFixture.Command() }, default));
        Assert.AreEqual("rollback_binding_conflict", failure.Code);
        Assert.AreEqual(1, (await fixture.Catalog.ReadAsync(fixture.Author, active.ReleaseId, default)).ActivationRevision);
    }
}
