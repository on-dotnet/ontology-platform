using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Publishing;

namespace OntologyPlatform.PublishingTests;

/// <summary>真实已激活版本基础上的外部故障和PG逐点原子回滚矩阵。</summary>
[TestClass]
public sealed class PublicationFaultTests
{
    /// <summary>外部失败保留旧active，移除故障后同命令恢复固定准备版本。</summary>
    [TestMethod]
    [DataRow("s3-write")]
    [DataRow("s3-read")]
    [DataRow("jena-write")]
    [DataRow("jena-read")]
    [DataRow("jena-shacl")]
    public async Task ExternalPhaseFailurePreservesOldActiveAndRetry(string phase)
    {
        // 所有成功路径使用真实资源，故障只作用本fixture的真实传输。
        using var fixture = new PublishingFixture();
        // 建立已激活旧版作为原子性观察基线。
        var first = await fixture.ProposalAsync();
        // 正式R1确实包含S3对象及Jena图。
        var old = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(await fixture.ApproveAsync(first.Proposal)), default);
        // 第二版需要独立草稿修订与审批。
        var updated = await fixture.Ontology.SaveAsync(fixture.Author, first.Draft.DraftId, new SaveDraftRequest { Name = first.Draft.Name, Sources = first.Draft.Sources with { DataTurtle = first.Draft.Sources.DataTurtle + "\n# second publication\n" }, Command = PublishingFixture.Command(1) }, default);
        // 新命令固定当前R1和修订1。
        var request = PublishingFixture.Activation(await fixture.ApproveAsync(await fixture.ProposalForAsync(updated)), old);
        // 在明确外部阶段注入真实客户端传输失败，不伪造成功结果。
        fixture.Gate = (message, _) =>
        {
            // 只匹配服务器控制的固定路径和方法。
            var path = message.RequestUri!.AbsolutePath;
            // 精确故障阶段用于验证各边界不会切active。
            var fail = phase switch
            {
                "s3-write" => path.Contains("/releases/", StringComparison.Ordinal) && message.Method == HttpMethod.Put,
                "s3-read" => path.Contains("/releases/", StringComparison.Ordinal) && message.Method == HttpMethod.Get,
                "jena-write" => path == "/ontology/data" && message.Method == HttpMethod.Put,
                "jena-read" => path == "/ontology/data" && message.Method == HttpMethod.Get,
                _ => path == "/validation/shacl" && message.Method == HttpMethod.Post
            };
            if (fail) throw new HttpRequestException("isolated transport failure");
            return Task.CompletedTask;
        };
        await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.ActivateAsync(fixture.Author, request, default));
        fixture.Gate = null;
        Assert.AreEqual(old.ReleaseId, (await fixture.Catalog.ResolveAsync(fixture.Author, first.Draft.AssetId, null, default)).Manifest.ReleaseId);
        Assert.AreEqual(1, await fixture.Database.Activations.CountAsync(row => row.AssetId == first.Draft.AssetId));
        // 已持久准备版本在重试中不变，失败制品可以按相同字节恢复。
        var reserved = await fixture.Database.Releases.AsNoTracking().SingleAsync(row => row.ProposalId == request.ProposalId);
        Assert.AreEqual("FAILED_RETRYABLE", reserved.State);
        // 故障移除后真正执行尚未完成的对象/图/事务。
        var recovered = await fixture.Service.ActivateAsync(fixture.Author, request, default);
        Assert.AreEqual(reserved.ReleaseId, recovered.ReleaseId);
        Assert.AreEqual(2, recovered.ActivationRevision);
        Assert.AreEqual(1, await fixture.Database.Outbox.CountAsync(row => row.EventId == recovered.OutboxEventId));
    }

    /// <summary>PG实际触发器在关键写点抛错，治理审计和active/事件共同回滚。</summary>
    [TestMethod]
    [DataRow("active")]
    [DataRow("activation")]
    [DataRow("audit")]
    [DataRow("outbox")]
    public async Task PostgreSqlWriteFailureRollsBackWholeActivation(string phase)
    {
        // 每个故障在全新测试scope中运行，触发器仅匹配本资产/组织。
        using var fixture = new PublishingFixture();
        // 准备合法真实草稿和审核。
        var item = await fixture.ProposalAsync();
        // 保留精确命令以便移除PG故障后恢复。
        var request = PublishingFixture.Activation(await fixture.ApproveAsync(item.Proposal));
        // 此fixture持续持有当前物理连接，故障scope只对当前请求有效。
        await fixture.Database.Database.OpenConnectionAsync();
        await fixture.Database.Database.ExecuteSqlInterpolatedAsync($"SELECT set_config('g2.pub_fault_asset', {item.Draft.AssetId}, false)");
        await fixture.Database.Database.ExecuteSqlInterpolatedAsync($"SELECT set_config('g2.pub_fault_org', {fixture.Author.OrganizationId}, false)");
        // 触发器函数完全固定，scope通过PG参数绑定而不是拼入DDL。
        const string functionSql = """
            CREATE OR REPLACE FUNCTION publishing.pub_fail() RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
              IF (TG_ARGV[0]='audit' AND to_jsonb(NEW)->>'OrganizationId'=current_setting('g2.pub_fault_org', true) AND to_jsonb(NEW)->>'Action'='release.activate')
                 OR (TG_ARGV[0]='outbox' AND EXISTS (SELECT 1 FROM publishing."Releases" r WHERE r."ReleaseId"=to_jsonb(NEW)->>'ReleaseId' AND r."AssetId"=current_setting('g2.pub_fault_asset', true)))
                 OR (TG_ARGV[0]='asset' AND to_jsonb(NEW)->>'AssetId'=current_setting('g2.pub_fault_asset', true))
              THEN RAISE EXCEPTION 'isolated fixture failure'; END IF;
              RETURN NEW;
            END $$
            """;
        // 每个DDL都是完整固定常量，没有任意标识拼接。
        var triggerSql = phase switch
        {
            "active" => "CREATE TRIGGER pub_fault BEFORE INSERT OR UPDATE ON publishing.\"ActiveReleases\" FOR EACH ROW EXECUTE FUNCTION publishing.pub_fail('asset')",
            "activation" => "CREATE TRIGGER pub_fault BEFORE INSERT OR UPDATE ON publishing.\"Activations\" FOR EACH ROW EXECUTE FUNCTION publishing.pub_fail('asset')",
            "audit" => "CREATE TRIGGER pub_fault BEFORE INSERT OR UPDATE ON governance.audit_records FOR EACH ROW EXECUTE FUNCTION publishing.pub_fail('audit')",
            _ => "CREATE TRIGGER pub_fault BEFORE INSERT OR UPDATE ON publishing.\"Outbox\" FOR EACH ROW EXECUTE FUNCTION publishing.pub_fail('outbox')"
        };
        // 对应清理也只来自固定表白名单。
        var dropSql = phase switch
        {
            "active" => "DROP TRIGGER pub_fault ON publishing.\"ActiveReleases\"",
            "activation" => "DROP TRIGGER pub_fault ON publishing.\"Activations\"",
            "audit" => "DROP TRIGGER pub_fault ON governance.audit_records",
            _ => "DROP TRIGGER pub_fault ON publishing.\"Outbox\""
        };
        await fixture.Database.Database.ExecuteSqlRawAsync(functionSql);
        await fixture.Database.Database.ExecuteSqlRawAsync(triggerSql);
        try
        {
            await Assert.ThrowsExactlyAsync<DbUpdateException>(() => fixture.Service.ActivateAsync(fixture.Author, request, default));
            Assert.AreEqual(0, await fixture.Database.ActiveReleases.CountAsync(row => row.AssetId == item.Draft.AssetId));
            Assert.AreEqual(0, await fixture.Database.Activations.CountAsync(row => row.AssetId == item.Draft.AssetId));
            // 审计即使先写也不能在发布失败后独立保留allowed成功事实。
            var audits = await fixture.Database.Database.SqlQuery<int>($"SELECT COUNT(*)::int AS \"Value\" FROM governance.audit_records WHERE \"OrganizationId\"={fixture.Author.OrganizationId} AND \"Action\"='release.activate'").SingleAsync();
            Assert.AreEqual(0, audits);
        }
        finally
        {
            await fixture.Database.Database.ExecuteSqlRawAsync(dropSql);
            await fixture.Database.Database.ExecuteSqlRawAsync("DROP FUNCTION publishing.pub_fail()");
        }
        // 原命令同release重试成功后只有一份审计、激活和事件。
        var result = await fixture.Service.ActivateAsync(fixture.Author, request, default);
        Assert.AreEqual(1, result.ActivationRevision);
        Assert.AreEqual(1, await fixture.Database.Outbox.CountAsync(row => row.EventId == result.OutboxEventId));
    }

    /// <summary>并发相同命令最终共享同一回执、审计与事件。</summary>
    [TestMethod]
    public async Task ConcurrentIdenticalActivationReturnsSameFact()
    {
        // 两个应用scope共享真实数据库和HTTP服务，EF上下文互相独立。
        using var fixture = new PublishingFixture();
        // 基础提案由独立主体批准。
        var item = await fixture.ProposalAsync();
        // 两个请求传递完全相同的业务载荷与幂等键。
        var request = PublishingFixture.Activation(await fixture.ApproveAsync(item.Proposal));
        // 并发请求一独占自己的EF跟踪器。
        using var scope1 = fixture.Provider.CreateScope();
        // 并发请求二不复用请求一数据库上下文。
        using var scope2 = fixture.Provider.CreateScope();
        // 真正并发走两次应用协调，允许可重试外部阶段竞争后读取提交事实。
        async Task<ReleaseActivation> Activate(IServiceScope scope)
        {
            // 独立上下文应用服务不会复用另一个请求的跟踪实体。
            var service = scope.ServiceProvider.GetRequiredService<IPublishingService>();
            try
            {
                return await service.ActivateAsync(fixture.Author, request, default);
            }
            catch (SemanticOperationException failure) when (failure.Status == 503)
            {
                return await service.ActivateAsync(fixture.Author, request, default);
            }
        }
        // 同时提交真实命令而非串行调用。
        var results = await Task.WhenAll(Activate(scope1), Activate(scope2));
        Assert.AreEqual(results[0].ActivationId, results[1].ActivationId);
        Assert.AreEqual(results[0].AuditId, results[1].AuditId);
        Assert.AreEqual(results[0].OutboxEventId, results[1].OutboxEventId);
        Assert.AreEqual(1, await fixture.Database.Activations.CountAsync(row => row.AssetId == item.Draft.AssetId));
    }

    /// <summary>并发不同提案竞争同一资产初始CAS，仅一版可激活且失败不产生审计/Outbox。</summary>
    [TestMethod]
    public async Task ConcurrentDifferentProposalsOnlyOneCasWinner()
    {
        // 各请求使用独立EF上下文，但共同竞争真实同资产指针。
        using var fixture = new PublishingFixture();
        // 两个不同提案都绑定同一个已验证当前草稿。
        var item = await fixture.ProposalAsync();
        // 第一合法审核事实。
        var first = await fixture.ApproveAsync(item.Proposal);
        // 第二独立提案取得另一合法审核事实。
        var second = await fixture.ApproveAsync(await fixture.ProposalForAsync(item.Draft));
        // 请求一的独立数据库跟踪范围。
        using var scope1 = fixture.Provider.CreateScope();
        // 请求二不复用请求一的上下文。
        using var scope2 = fixture.Provider.CreateScope();
        // 只接受真实CAS冲突作为失败，依赖异常不能伪装成正确并发结论。
        async Task<ReleaseActivation?> Activate(IServiceScope scope, ReleaseProposal proposal)
        {
            try
            {
                return await scope.ServiceProvider.GetRequiredService<IPublishingService>().ActivateAsync(fixture.Author, PublishingFixture.Activation(proposal), default);
            }
            catch (SemanticOperationException failure) when (failure.Code == "activation_revision_conflict")
            {
                return null;
            }
        }
        // 同时准备不同固定版本并竞争活动修订0。
        var results = await Task.WhenAll(Activate(scope1, first), Activate(scope2, second));
        Assert.AreEqual(1, results.Count(value => value is not null));
        Assert.AreEqual(1, await fixture.Database.Activations.CountAsync(row => row.AssetId == item.Draft.AssetId));
        // 唯一获胜回执对应真正可回验的版本。
        var winner = results.Single(value => value is not null)!;
        Assert.AreEqual(winner.ManifestHash, (await fixture.Catalog.ResolveAsync(fixture.Author, item.Draft.AssetId, null, default)).ManifestHash);
        Assert.AreEqual(1, await fixture.Database.Outbox.CountAsync(row => row.ReleaseId == winner.ReleaseId));
    }

}
