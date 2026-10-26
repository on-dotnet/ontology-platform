using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.QueryTests;

/// <summary>真实发布后的依赖故障、恢复、完整性、取消和固定版本测试。</summary>
[TestClass]
public sealed class QueryFaultTests
{
    /// <summary>正式快照取得后传输失败返回UNAVAILABLE，故障移除即恢复原版。</summary>
    [TestMethod]
    public async Task DependencyFailureAfterSnapshotIsUnavailableAndRecoverable()
    {
        // 先使用真实PG、S3和Jena建立完整可用发布。
        using var fixture = new QueryFixture();
        // 只有完整真实发布才可以取得可信snapshot。
        var release = await fixture.PublishAsync();
        // 检查点在真实Catalog完成后才故障，不能模拟成功依赖。
        var gateway = fixture.AfterResolve(() => { fixture.Gate = (_, _) => throw new HttpRequestException("fixture failure"); return Task.CompletedTask; });
        // 下游真实HTTP发送失败不能变成EMPTY。
        var result = await gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default);
        Assert.AreEqual(SemanticQueryStatus.Unavailable, result.Status);
        Assert.AreEqual(release.Manifest.ReleaseId, result.Snapshot.ReleaseId);
        Assert.IsEmpty(result.Data);
        fixture.Gate = null;
        Assert.AreEqual(SemanticQueryStatus.Found, (await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default)).Status);
    }

    /// <summary>真实对象读取字节损坏必须被hash拒绝；证据不能绕过回验。</summary>
    [TestMethod]
    public async Task CorruptedSourceHashFailsQueryAndEvidence()
    {
        // 原始成功路径仍使用全部真实依赖。
        using var fixture = new QueryFixture();
        // 先取得稳定真实证据定位。
        var release = await fixture.PublishAsync();
        // 此前取得的证据不能信任旧hash结果。
        var found = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default);
        fixture.CorruptResponse = (request, response) =>
        {
            if (request.Method == HttpMethod.Get && request.RequestUri!.AbsolutePath.EndsWith(found.Evidence[0].SourceObjectKey, StringComparison.Ordinal))
            {
                response.Content.Dispose();
                response.Content = new StringContent("corrupted isolated synthetic source", Encoding.UTF8, "text/turtle");
            }
        };
        // Catalog尚未交出可信快照时以明确503失败。
        var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default));
        Assert.AreEqual(503, failure.Status);
        // Evidence也执行真实GET和hash，不复用答案中的旧校验。
        var evidenceFailure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Evidence.ReadAsync(fixture.Author, found.Evidence[0].EvidenceId, default));
        Assert.AreEqual(503, evidenceFailure.Status);
        fixture.CorruptResponse = null;
        Assert.AreEqual(SemanticQueryStatus.Found, (await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default)).Status);
    }

    /// <summary>真实Jena图丢失或篡改不返回EMPTY，恢复固定源后同发布可读。</summary>
    [TestMethod]
    [DataRow(false)]
    [DataRow(true)]
    public async Task ChangedOrMissingGraphIsUnavailable(bool remove)
    {
        // 当前测试只修改自己生成的发布图。
        using var fixture = new QueryFixture();
        // 正式图由真正发布流程创建。
        var release = await fixture.PublishAsync();
        // 随机新回环Jena资源，不访问历史配置或生产。
        using var client = new HttpClient(new HttpClientHandler { UseProxy = false });
        // 仅服务器生成graph IRI经过标准URL转义。
        var target = Environment.GetEnvironmentVariable("G2_QRY_JENA") + "/ontology/data?graph=" + Uri.EscapeDataString(release.Manifest.DataGraphIri);
        // 真正删除或覆盖当前测试的图，不能用替身模拟丢失。
        using var response = remove ? await client.DeleteAsync(target) : await client.PutAsync(target, new StringContent("<urn:changed> <urn:predicate> <urn:object> .", Encoding.UTF8, "text/turtle"));
        response.EnsureSuccessStatusCode();
        // 完整性回验失败不能退化为空结果。
        var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default));
        Assert.AreEqual(503, failure.Status);
        // 用同一正式源恢复原图，不切换版本或伪造状态。
        using var restored = await client.PutAsync(target, new StringContent(fixture.Sources().DataTurtle, Encoding.UTF8, "text/turtle"));
        restored.EnsureSuccessStatusCode();
        Assert.AreEqual(SemanticQueryStatus.Found, (await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default)).Status);
    }

    /// <summary>用户取消向真实HTTP链路传播，超时则保持明确业务UNAVAILABLE。</summary>
    [TestMethod]
    public async Task CancellationAndBudgetReachDependency()
    {
        // 无代理真实资源及独立发布。
        using var fixture = new QueryFixture();
        // 正式发布与schema版本先到位。
        var release = await fixture.PublishAsync();
        // 检测依赖真实收到的取消信号。
        var observedCancellation = false;
        // 仅在正式snapshot之后延迟真实HTTP发送。
        var gateway = fixture.AfterResolve(() =>
        {
            fixture.Gate = async (_, token) =>
            {
                try { await Task.Delay(TimeSpan.FromSeconds(10), token); }
                catch (OperationCanceledException) { observedCancellation = true; throw; }
            };
            return Task.CompletedTask;
        });
        // 预算计时器实际取消等待，不只是比较输入数字。
        var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => gateway.ExecuteAsync(fixture.Author, fixture.Plan(release) with { TimeoutMs = 1000 }, default));
        Assert.AreEqual(503, failure.Status);
        Assert.IsTrue(observedCancellation);
        fixture.Gate = null;
        // 显式用户取消与内部预算超时保持不同语义。
        using var cancellation = new CancellationTokenSource();
        // 真实Catalog之后取消，保证不是仅入口检查。
        var cancelled = fixture.AfterResolve(() => { cancellation.Cancel(); return Task.CompletedTask; });
        await Assert.ThrowsAsync<OperationCanceledException>(() => cancelled.ExecuteAsync(fixture.Author, fixture.Plan(release), cancellation.Token));
    }

    /// <summary>查询固定R1后真实激活R2，请求不混版，后续请求取得R2。</summary>
    [TestMethod]
    public async Task ConcurrentActivationCannotChangeRequestSnapshot()
    {
        // 所有版本均通过真实审批、源回验和PG CAS。
        using var fixture = new QueryFixture();
        // 正式R1。
        var first = await fixture.PublishAsync();
        // 当前草稿按真实revision推进。
        var draft = await fixture.Ontology.ReadAsync(fixture.Author, first.Manifest.DraftId, default);
        // 注释改变源字节和hash但不假造业务事实。
        var updated = await fixture.Ontology.SaveAsync(fixture.Author, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = draft.Sources with { DataTurtle = draft.Sources.DataTurtle + "\n# revision two\n" }, Command = QueryFixture.Command(draft.Revision) }, default);
        // 异人审批第二版准备好，在查询固定之后激活。
        var proposal = await fixture.ApproveAsync(await fixture.ProposalForAsync(updated));
        // 确定活动指针CAS前提。
        var request = new ActivateReleaseRequest { ProposalId = proposal.ProposalId, ExpectedActivationRevision = first.ActivationRevision, ExpectedActiveReleaseId = first.Manifest.ReleaseId, Command = QueryFixture.Command(proposal.Revision) };
        // 回调只执行真实Publishing，没有替身snapshot。
        var gateway = fixture.AfterResolve(async () => { await fixture.Service.ActivateAsync(fixture.Author, request, default); });
        // 本次Gateway必须继续R1。
        var running = await gateway.ExecuteAsync(fixture.Author, fixture.Plan(first), default);
        Assert.AreEqual(first.Manifest.ReleaseId, running.Snapshot.ReleaseId);
        // 下个请求真实读取新active。
        var next = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(first), default);
        Assert.AreNotEqual(first.Manifest.ReleaseId, next.Snapshot.ReleaseId);
        // 显式历史R1仍可授权读取，源hash保持旧值。
        var historical = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(first) with { ReleaseId = first.Manifest.ReleaseId }, default);
        Assert.AreEqual(first.Manifest.Snapshot.DataHash, historical.Snapshot.DataHash);
        Assert.AreEqual(JsonSerializer.Serialize(running.Snapshot), JsonSerializer.Serialize(historical.Snapshot));
    }

    /// <summary>真实PG审计事实成功后才返回查询结果，固定记录无源正文。</summary>
    [TestMethod]
    public async Task QueryAndEvidenceCommitIndependentAudit()
    {
        // 真实治理库，测试直接读持久事实而非替身计数。
        using var fixture = new QueryFixture();
        // 合法真实发布。
        var release = await fixture.PublishAsync();
        // 读取查询与证据分别产生独立审计事实。
        var result = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default);
        await fixture.Evidence.ReadAsync(fixture.Author, result.Evidence[0].EvidenceId, default);
        // PG执行真实计数，组织与Trace仅作参数不拼接SQL。
        var count = await fixture.Database.Database.SqlQuery<int>($"SELECT COUNT(*)::int AS \"Value\" FROM governance.audit_records WHERE \"OrganizationId\"={fixture.Author.OrganizationId} AND \"TraceId\"={fixture.Author.TraceId} AND \"Action\" IN ('semantic.query','semantic.evidence.read') AND \"Outcome\"='allowed'").SingleAsync();
        Assert.AreEqual(2, count);
    }

    /// <summary>反向谱系也保留原始关系方向，受控遍历可由钢卷追到炉次。</summary>
    [TestMethod]
    public async Task ReverseLineageUsesActualEdges()
    {
        // 同一个真实标准合成图，不额外制造反向事实。
        using var fixture = new QueryFixture();
        // 实际发布有正向谓词，逆向读取不能伪造谓词。
        var release = await fixture.PublishAsync();
        // 从下游钢卷向已有关联邻接遍历。
        var result = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release, "traverse_relationships") with { ExternalId = "coil-1" }, default);
        Assert.IsTrue(result.Data.Any(value => value.Entity?.ExternalId == "heat-1"));
        Assert.IsTrue(result.Data.Any(value => value.Relationship?.PredicateIri == "urn:synthetic:metals:producesCoil"));
    }
    /// <summary>跨厂真实关系不能泄露另一端，缺关系时只保留真实实体。</summary>
    [TestMethod]
    public async Task CrossSiteEdgesAndMissingRelationshipsDoNotInventFacts()
    {
        // 两个厂均发布在同一获准对象，但计划只选择一个厂。
        using var fixture = new QueryFixture();
        // 添加一条真实跨厂RDF关系后重新完整发布。
        var sources = fixture.Sources();
        // 受控合成IRI来自当前测试组织，绝不连接外部数据。
        var prefix = "urn:synthetic:" + fixture.Author.OrganizationId;
        // 业务Shape允许多对多，Gateway仍必须过滤计划site另一端。
        var release = await fixture.PublishAsync(sources with { DataTurtle = sources.DataTurtle + "\n<" + prefix + ":site-a:local:heat-1> <urn:synthetic:metals:castIn> <" + prefix + ":site-b:local:cast-1> .\n" });
        // 两端授权必须在遍历前执行，不能仅过滤最终节点。
        var result = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release, "traverse_relationships"), default);
        Assert.IsTrue(result.Data.Where(value => value.Entity is not null).All(value => value.Entity!.SiteId == "site-a"));
        Assert.IsFalse(result.Data.Any(value => value.Relationship?.TargetIri.Contains(":site-b:", StringComparison.Ordinal) == true));
        // 指定合法但从当前实体不存在的关系时不造边。
        var missing = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release, "traverse_relationships") with { RelationshipIris = ["urn:synthetic:metals:producesCoil"] }, default);
        Assert.AreEqual(SemanticQueryStatus.Found, missing.Status);
        Assert.HasCount(1, missing.Data);
        Assert.IsNotNull(missing.Data[0].Entity);
    }

    /// <summary>组织越权、声明厂区越权及历史版越权在读取外部依赖前拒绝。</summary>
    [TestMethod]
    public async Task DeclaredScopeIsAuthorizedBeforeExternalReads()
    {
        // 发布对象真实存在，故障门用于证明拒绝前没有外部访问。
        using var fixture = new QueryFixture();
        // 同一真实版本供各种授权负例使用。
        var release = await fixture.PublishAsync();
        fixture.Gate = (_, _) => throw new AssertFailedException("授权前不应读取外部资源");
        foreach (var actor in new[] { fixture.Author with { OrganizationId = "other-org" }, fixture.Author with { SiteIds = ["site-b"] }, fixture.Author with { Roles = ["auditor"] } })
        {
            // 显式历史版必须和当前版一样重新授权完整范围。
            var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Gateway.ExecuteAsync(actor, fixture.Plan(release) with { ReleaseId = release.Manifest.ReleaseId }, default));
            Assert.AreEqual(403, failure.Status);
        }
    }
    /// <summary>深度预算省略真实可访问邻接时明确PARTIAL，不能声称完整子图。</summary>
    [TestMethod]
    public async Task DepthBudgetReportsIncompleteGraph()
    {
        // 真实图存在至少四跳的来源链。
        using var fixture = new QueryFixture();
        // 当前发布包含完整链路。
        var release = await fixture.PublishAsync();
        // 只允许一跳必须报告尚有被截断的真实路径。
        var result = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release, "traverse_relationships") with { Depth = 1 }, default);
        Assert.AreEqual(SemanticQueryStatus.Partial, result.Status);
        Assert.IsTrue(result.Limited);
        Assert.HasCount(3, result.Data);
    }

    /// <summary>真实PG审计写失败时业务不能回报成功，异常正文不透出。</summary>
    [TestMethod]
    public async Task AuditFailureIsUnavailableAndRecovers()
    {
        // 当前测试随机组织限制触发器影响范围。
        using var fixture = new QueryFixture();
        // 先完成无故障真实发布。
        var release = await fixture.PublishAsync();
        // 组织ID由测试随机生成且限定安全字符，仅DDL标识范围内使用。
        Assert.IsTrue(fixture.Author.OrganizationId.All(character => char.IsAsciiLetterOrDigit(character) || character == '-'));
        // 保存受控DDL再执行，任何客户端输入均不可进入此测试函数。
        var createFailure = "CREATE OR REPLACE FUNCTION governance.query_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN IF NEW.\"OrganizationId\" = '" + fixture.Author.OrganizationId + "' AND NEW.\"Action\" = 'semantic.query' THEN RAISE EXCEPTION 'isolated sensitive diagnostic'; END IF; RETURN NEW; END $$";
        await fixture.Database.Database.ExecuteSqlRawAsync(createFailure);
        await fixture.Database.Database.ExecuteSqlRawAsync("CREATE TRIGGER query_fault BEFORE INSERT ON governance.audit_records FOR EACH ROW EXECUTE FUNCTION governance.query_fail()");
        try
        {
            // 只有安全503可公开，不能把原始PG异常返回调用方。
            var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default));
            Assert.AreEqual(503, failure.Status);
        }
        finally
        {
            await fixture.Database.Database.ExecuteSqlRawAsync("DROP TRIGGER query_fault ON governance.audit_records");
            await fixture.Database.Database.ExecuteSqlRawAsync("DROP FUNCTION governance.query_fail()");
        }
        Assert.AreEqual(SemanticQueryStatus.Found, (await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default)).Status);
    }
}
