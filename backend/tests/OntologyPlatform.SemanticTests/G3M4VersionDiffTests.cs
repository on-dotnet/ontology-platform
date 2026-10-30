using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SemanticTests;

/// <summary>同一次真实RIOT/M1预算的四源差异与PG历史来源绑定。</summary>
[TestClass]
public sealed class G3M4VersionDiffTests
{
    /// <summary>原文BOM换行、语言、datatype和各源真实统计完整保留。</summary>
    [TestMethod]
    public async Task FourSourcesKeepExactTextHashesAndGroundDelta()
    {
        // 四源都发生明确原文变化，不能只比较Ontology画布投影。
        var left = new SourceBundle { OntologyTurtle = "\ufeff<urn:C> a <http://www.w3.org/2002/07/owl#Class> .\r\n", ShapesTurtle = "# before shape\n", VocabularyTurtle = "<urn:v> <urn:label> \"甲\"@zh .", DataTurtle = "<urn:item> <urn:value> \"01\"^^<http://www.w3.org/2001/XMLSchema#integer> ." };
        // 类型化词法变化仍准确反映在源码和真实图差异，不归一为显示数字。
        var right = left with { OntologyTurtle = left.OntologyTurtle + "<urn:D> a <http://www.w3.org/2002/07/owl#Class> .\n", ShapesTurtle = "# after shape\n", VocabularyTurtle = "<urn:v> <urn:label> \"乙\"@zh .", DataTurtle = "<urn:item> <urn:value> \"02\"^^<http://www.w3.org/2001/XMLSchema#integer> ." };
        // 真实运行时复用同一预算输出四槽位结果。
        var result = await ((IG3VersionDiffRuntime)SemanticFixture.Runtime()).DiffSourcesAsync(left, right, default);
        Assert.AreEqual(4, result.Length);
        Assert.AreEqual(left.OntologyTurtle, result[0].BaseText);
        Assert.AreEqual(right.OntologyTurtle, result[0].TargetText);
        Assert.IsTrue(result.All(item => item.SourceChanged));
        Assert.AreEqual(TripleDeltaStatus.Exact, result[0].TripleDeltaStatus);
        Assert.AreEqual(1, result[0].BaseTripleCount);
        Assert.AreEqual(2, result[0].TargetTripleCount);
        Assert.AreEqual(1, result[0].AddedTriples.Length);
        Assert.AreEqual(TripleDeltaStatus.Equivalent, result[1].TripleDeltaStatus);
        Assert.AreEqual("zh", result[2].AddedTriples.Single().Object.Language);
        Assert.AreEqual("02", result[3].AddedTriples.Single().Object.Value);
        Assert.IsTrue(result.All(item => item.AddedTriples.Concat(item.RemovedTriples).All(triple => triple.Subject.Kind == RdfTermKind.Iri && triple.Object.Kind != RdfTermKind.Blank)));
        foreach (var source in result) ImpactContractRules.ValidateSourceIdentity(source);
    }

    /// <summary>blank重命名同构无delta，实际blank变化不得把随机label写入可信delta。</summary>
    [TestMethod]
    public async Task BlankIsomorphismAndChangedBlankScopesRemainExplicit()
    {
        // 左图的blank身份只属于这一次左源解析。
        var left = new SourceBundle { OntologyTurtle = "_:a <urn:p> _:b . _:b <urn:value> \"甲\" . <urn:named> <urn:value> \"old\" ." };
        // 重命名不等于图变化，原文hash变化仍须显示。
        var renamed = left with { OntologyTurtle = left.OntologyTurtle.Replace("_:a", "_:x", StringComparison.Ordinal).Replace("_:b", "_:y", StringComparison.Ordinal) };
        // 当前生产比较器不是按label相等判同构。
        var runtime = (IG3VersionDiffRuntime)SemanticFixture.Runtime();
        // 同构图不输出虚假的blank差异。
        var same = (await runtime.DiffSourcesAsync(left, renamed, default))[0];
        Assert.IsTrue(same.SourceChanged);
        Assert.AreEqual(GraphComparisonStatus.Equivalent, same.Graph.Status);
        Assert.AreEqual(TripleDeltaStatus.Equivalent, same.TripleDeltaStatus);
        Assert.IsEmpty(same.AddedTriples);
        // 同时改变一个blank事实与一个地面事实，只有地面项可靠可定位。
        var changed = renamed with { OntologyTurtle = renamed.OntologyTurtle.Replace("甲", "乙", StringComparison.Ordinal).Replace("old", "new", StringComparison.Ordinal) };
        // 没有无预算二次解析，当前总预算同时给出统计/delta。
        var diff = (await runtime.DiffSourcesAsync(left, changed, default))[0];
        Assert.AreEqual(GraphComparisonStatus.Different, diff.Graph.Status);
        Assert.AreEqual(TripleDeltaStatus.Indeterminate, diff.TripleDeltaStatus);
        Assert.AreEqual("new", diff.AddedTriples.Single().Object.Value);
        Assert.AreEqual("old", diff.RemovedTriples.Single().Object.Value);
        Assert.AreEqual(left.OntologyTurtle, diff.BaseText);
        ImpactContractRules.ValidateSourceIdentity(diff);
    }

    /// <summary>缺词汇和空词汇图同为空，但原文及hash身份必须不同。</summary>
    [TestMethod]
    public async Task AbsentVocabularyAndEmptyFileHaveDifferentSourceIdentity()
    {
        // 明确null与空字符串，不能以同空图抹去来源差异。
        var left = new SourceBundle { VocabularyTurtle = null };
        // 原文为空仍是实际存在文档，有自己的UTF8 hash。
        var right = left with { VocabularyTurtle = "" };
        // 同一次真实比较保持两个不同来源身份。
        var source = (await ((IG3VersionDiffRuntime)SemanticFixture.Runtime()).DiffSourcesAsync(left, right, default))[2];
        Assert.IsNull(source.BaseHash);
        Assert.IsNotNull(source.TargetHash);
        Assert.IsTrue(source.SourceChanged);
        Assert.AreEqual(TripleDeltaStatus.Equivalent, source.TripleDeltaStatus);
        Assert.AreEqual(0, source.BaseTripleCount);
        Assert.AreEqual(0, source.TargetTripleCount);
    }

    /// <summary>总取消/blank预算耗尽撤回全部四源结论，不能0统计冒充未解析。</summary>
    [TestMethod]
    [DataRow(false)]
    [DataRow(true)]
    public async Task SharedBudgetFailureIsIndeterminateForAllFourSources(bool cancelled)
    {
        // 129个独立blank超过已冻结128上限，即使同源也不得走no-op绕过。
        var source = new SourceBundle { OntologyTurtle = string.Join('\n', Enumerable.Range(0, 129).Select(index => "_:b" + index + " <urn:p> \"value\" .")) };
        // 请求取消明确传入同一解析/比较预算。
        using var stop = new CancellationTokenSource();
        if (cancelled) stop.Cancel();
        // 真实运行时返回每源未知，不把部分先过图伪装为完成。
        var result = await ((IG3VersionDiffRuntime)SemanticFixture.Runtime()).DiffSourcesAsync(source, source, stop.Token);
        Assert.IsTrue(result.All(item => item.Graph.Status == GraphComparisonStatus.Indeterminate && item.TripleDeltaStatus == TripleDeltaStatus.Indeterminate && item.AddedTriples.Length == 0 && item.RemovedTriples.Length == 0));
        if (cancelled) Assert.IsTrue(result.All(item => item.BaseTripleCount is null && item.TargetTripleCount is null));
        foreach (var item in result) ImpactContractRules.ValidateSourceIdentity(item);
    }

    /// <summary>PG固定两个历史修订、同版本no-op、跨资产与持久hash篡改失败关闭。</summary>
    [TestMethod]
    public async Task VersionDiffBindsActualPersistedSourcesAndRejectsCrossAssetOrTamper()
    {
        // 明确当前隔离PG，来源不会来自旧runtime或客户端hash。
        var connection = Environment.GetEnvironmentVariable("G2_SEM_PG_CONNECTION") ?? throw new AssertInconclusiveException("NOT_RUN: real PG required");
        // 使用真实模块上下文和真实同事务审计。
        await using var database = new OntologyDbContext(new DbContextOptionsBuilder<OntologyDbContext>().UseNpgsql(connection).Options);
        // 真实审计writer复用原Governance写入边界。
        var service = new OntologyService(database, SemanticFixture.Runtime(), new TransactionalAuditWriter(new PooledDbContextFactory<GovernanceDbContext>(new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(connection).Options)), TimeProvider.System);
        // 当前可信双厂主体，不从request传actor。
        var actor = new ActorContext { SubjectId = Guid.NewGuid().ToString("N"), OrganizationId = "org-demo", SiteIds = ["site-a", "site-b"], Roles = ["platform.operator"], TraceId = "test", CorrelationId = "test" };
        // 最小完整源由真实RIOT创建。
        var draft = await service.CreateAsync(actor, new CreateDraftRequest { Name = "Synthetic B diff", Scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = actor.SiteIds }, Sources = G3M4IdentityTimeTests.Sources(""), Command = Command(0) }, default);
        // 后续修订故意只变data，避免Ontology投影掩盖另外三源。
        var target = await service.SaveAsync(actor, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = draft.Sources with { DataTurtle = draft.Sources.DataTurtle + "<urn:extra> <urn:p> \"new\" ." }, Command = Command(1) }, default);
        // 版本引用必须准确指定已保存修订，而不是读取当前草稿替代。
        var request = new CompareVersionsRequest { From = Ref(draft.DraftId, 1), To = Ref(draft.DraftId, 2) };
        // 真实HTTP以外应用用例也执行同一严格合同。
        var diff = await service.DiffAsync(actor, request, default);
        Assert.AreEqual(draft.Hashes, diff.BaseHashes);
        Assert.AreEqual(target.Hashes, diff.TargetHashes);
        Assert.AreEqual(draft.Sources.DataTurtle, diff.Sources[3].BaseText);
        Assert.AreEqual(1, diff.Sources[3].AddedTriples.Length);
        Assert.IsTrue((await service.DiffAsync(actor, request with { From = request.To }, default)).Sources.All(item => !item.SourceChanged && item.Graph.Status == GraphComparisonStatus.Equivalent));
        Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.DiffAsync(actor with { SiteIds = ["site-a"] }, request, default))).Status);
        // 另一个服务器资产不能因scope相同而被当作同一版本系列。
        var other = await service.CreateAsync(actor, new CreateDraftRequest { Name = "Other asset", Scope = draft.Scope, Sources = draft.Sources, Command = Command(0) }, default);
        Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => service.DiffAsync(actor, request with { To = Ref(other.DraftId, 1) }, default))).Status);
        // 隔离数据库故障注入：只改SourcesJson而不改真实已存HashesJson。
        var row = await database.Revisions.SingleAsync(item => item.DraftId == draft.DraftId && item.Revision == 1);
        row.SourcesJson = JsonSerializer.Serialize(draft.Sources with { DataTurtle = "# tampered historical source" });
        await database.SaveChangesAsync();
        Assert.AreEqual("revision_source_binding_invalid", (await Assert.ThrowsAsync<SemanticOperationException>(() => service.DiffAsync(actor, request, default))).Code);
    }

    /// <summary>准确草稿引用不接受当前修订省略。</summary>
    private static VersionRef Ref(string draftId, long revision) => new() { Kind = VersionRefKind.Draft, Id = draftId, Revision = revision };

    /// <summary>新的明确意图产生独立幂等命令。</summary>
    private static CommandContext Command(long revision) => new() { CommandId = Guid.NewGuid().ToString("N"), IdempotencyKey = Guid.NewGuid().ToString("N"), ExpectedRevision = revision, Reason = "Synthetic fixed version diff" };
}
