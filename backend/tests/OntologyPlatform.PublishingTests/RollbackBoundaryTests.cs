using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.PublishingTests;

/// <summary>回滚拥有独立审核边界，不能借旧版本绕过身份、期限或绑定。</summary>
[TestClass]
public sealed class RollbackBoundaryTests
{
    /// <summary>真实旧版本回滚对自批、过期和数据库目标内容篡改均失败关闭。</summary>
    [TestMethod]
    [DataRow("self")]
    [DataRow("expiry")]
    [DataRow("binding")]
    public async Task RollbackRequiresFreshIndependentBoundApproval(string condition)
    {
        // 当前测试实际发布正式R1。
        using var fixture = new PublishingFixture();
        // 所有合法前置依赖都真实运行。
        var item = await fixture.ProposalAsync();
        // 正式manifest来自真实成功事务。
        var first = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(await fixture.ApproveAsync(item.Proposal)), default);
        // 草稿推进不应阻止合法回滚，负例只针对审核边界。
        await fixture.Ontology.SaveAsync(fixture.Author, item.Draft.DraftId, new SaveDraftRequest { Sources = item.Draft.Sources with { DataTurtle = item.Draft.Sources.DataTurtle + "\n# draft advanced\n" }, Command = PublishingFixture.Command(1) }, default);
        // 独立回滚提案固定旧完整manifest，所有draft字段保持null。
        var proposal = await fixture.Service.CreateProposalAsync(fixture.Author, new CreateProposalRequest { Kind = ProposalKind.Rollback, TargetReleaseId = first.ReleaseId, TargetManifestHash = first.ManifestHash, Command = PublishingFixture.Command() }, default);
        if (condition == "self")
        {
            // 双角色提交者仍无法审批自己创建的ROLLBACK。
            var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.DecideAsync(fixture.Author with { Roles = ["platform.operator", "platform.auditor"] }, proposal.ProposalId, new ApprovalDecisionRequest { Decision = ApprovalDecision.Approve, Command = PublishingFixture.Command(1) }, default));
            Assert.AreEqual(403, failure.Status);
        }
        else
        {
            // 合法独立审批先建立正确基础。
            var approved = await fixture.ApproveAsync(proposal);
            if (condition == "expiry") fixture.Clock.Offset = TimeSpan.FromHours(25);
            else
            {
                // 模拟当前测试库中目标被篡改，保留原批准hash以验证最终绑定核验。
                var changed = approved with { TargetManifestHash = new string('0', 64) };
                await fixture.Database.Proposals.Where(row => row.ProposalId == proposal.ProposalId).ExecuteUpdateAsync(update => update.SetProperty(row => row.ProposalJson, JsonSerializer.Serialize(changed)));
            }
            // 失败必须是服务端明确409，不因当前草稿revision2而误判。
            var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(approved, first), default));
            Assert.AreEqual(409, failure.Status);
            Assert.AreEqual(condition == "expiry" ? "proposal_expired" : "approval_required", failure.Code);
        }
        Assert.AreEqual(1, await fixture.Database.Activations.CountAsync(row => row.AssetId == item.Draft.AssetId));
        Assert.AreEqual(first.ReleaseId, (await fixture.Database.ActiveReleases.AsNoTracking().SingleAsync(row => row.AssetId == item.Draft.AssetId)).ReleaseId);
    }

    /// <summary>旧完整版本回滚的外部回验、审计和Outbox失败都必须保留当前R2。</summary>
    [TestMethod]
    [DataRow("artifact")]
    [DataRow("audit")]
    [DataRow("outbox")]
    public async Task RollbackFailurePreservesCurrentAndSameCommandRecovers(string phase)
    {
        // 真实两版保证回滚失败有可观察的当前正确版本。
        using var fixture = new PublishingFixture();
        // R1使用真实来源、SHACL和异人审批。
        var item = await fixture.ProposalAsync();
        // 固定旧版本manifest供回滚。
        var old = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(await fixture.ApproveAsync(item.Proposal)), default);
        // 当前草稿推进后重新真实发布R2。
        var updated = await fixture.Ontology.SaveAsync(fixture.Author, item.Draft.DraftId, new SaveDraftRequest { Sources = item.Draft.Sources with { OntologyTurtle = item.Draft.Sources.OntologyTurtle + "\n# rollback failure scenario\n" }, Command = PublishingFixture.Command(1) }, default);
        // R2是回滚失败时必须保留的活动事实。
        var current = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(await fixture.ApproveAsync(await fixture.ProposalForAsync(updated)), old), default);
        // 针对旧R1创建全新独立批准。
        var proposal = await fixture.ApproveAsync(await fixture.Service.CreateProposalAsync(fixture.Author, new CreateProposalRequest { Kind = ProposalKind.Rollback, TargetReleaseId = old.ReleaseId, TargetManifestHash = old.ManifestHash, Command = PublishingFixture.Command() }, default));
        // 保存相同命令用于真实失败恢复。
        var request = PublishingFixture.Activation(proposal, current);
        if (phase == "artifact")
        {
            fixture.Gate = (message, _) => message.Method == HttpMethod.Get && message.RequestUri!.AbsolutePath.Contains(old.ReleaseId, StringComparison.Ordinal) ? throw new HttpRequestException("isolated old artifact failure") : Task.CompletedTask;
        }
        else
        {
            // 持有同物理连接，通过参数化session值限制本测试回滚事件。
            await fixture.Database.Database.OpenConnectionAsync();
            await fixture.Database.Database.ExecuteSqlInterpolatedAsync($"SELECT set_config('g2.pub_rollback_org', {fixture.Author.OrganizationId}, false)");
            await fixture.Database.Database.ExecuteSqlInterpolatedAsync($"SELECT set_config('g2.pub_rollback_release', {old.ReleaseId}, false)");
            await fixture.Database.Database.ExecuteSqlRawAsync("""
                CREATE FUNCTION publishing.pub_rollback_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN
                IF (to_jsonb(NEW)->>'Action'='release.rollback' AND to_jsonb(NEW)->>'OrganizationId'=current_setting('g2.pub_rollback_org', true))
                OR (to_jsonb(NEW)->>'EventType'='release.rolled_back' AND to_jsonb(NEW)->>'ReleaseId'=current_setting('g2.pub_rollback_release', true))
                THEN RAISE EXCEPTION 'isolated rollback fixture failure'; END IF; RETURN NEW; END $$
                """);
            // 固定DDL，不允许外部表名或范围拼接。
            var createTrigger = phase == "audit" ? "CREATE TRIGGER pub_rollback_fault BEFORE INSERT ON governance.audit_records FOR EACH ROW EXECUTE FUNCTION publishing.pub_rollback_fail()" : "CREATE TRIGGER pub_rollback_fault BEFORE INSERT ON publishing.\"Outbox\" FOR EACH ROW EXECUTE FUNCTION publishing.pub_rollback_fail()";
            await fixture.Database.Database.ExecuteSqlRawAsync(createTrigger);
        }
        try
        {
            if (phase == "artifact")
            {
                // 对象不可用必须明确503，而不是把旧图存在当作足够条件。
                var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.ActivateAsync(fixture.Author, request, default));
                Assert.AreEqual(503, failure.Status);
            }
            else await Assert.ThrowsAsync<DbUpdateException>(() => fixture.Service.ActivateAsync(fixture.Author, request, default));
            Assert.AreEqual(current.ReleaseId, (await fixture.Database.ActiveReleases.AsNoTracking().SingleAsync(row => row.AssetId == item.Draft.AssetId)).ReleaseId);
            Assert.AreEqual(2, await fixture.Database.Activations.CountAsync(row => row.AssetId == item.Draft.AssetId));
            // 治理自身writer已经写入的审计也必须与失败激活一起回滚。
            var audits = await fixture.Database.Database.SqlQuery<int>($"SELECT COUNT(*)::int AS \"Value\" FROM governance.audit_records WHERE \"OrganizationId\"={fixture.Author.OrganizationId} AND \"Action\"='release.rollback'").SingleAsync();
            Assert.AreEqual(0, audits);
        }
        finally
        {
            fixture.Gate = null;
            if (phase != "artifact")
            {
                // 清理仅本测试创建的固定触发器及函数。
                var dropTrigger = phase == "audit" ? "DROP TRIGGER pub_rollback_fault ON governance.audit_records" : "DROP TRIGGER pub_rollback_fault ON publishing.\"Outbox\"";
                await fixture.Database.Database.ExecuteSqlRawAsync(dropTrigger);
                await fixture.Database.Database.ExecuteSqlRawAsync("DROP FUNCTION publishing.pub_rollback_fail()");
            }
        }
        // 目标未重建、未变更，原批准命令可以在故障解除后安全重试。
        var restored = await fixture.Service.ActivateAsync(fixture.Author, request, default);
        Assert.AreEqual(old.ManifestHash, restored.ManifestHash);
        Assert.AreEqual(3, restored.ActivationRevision);
        Assert.AreEqual(current.ManifestHash, (await fixture.Catalog.ReadAsync(fixture.Author, current.ReleaseId, default)).ManifestHash);
    }

}
