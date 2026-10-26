using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.SemanticQuery;

namespace OntologyPlatform.QueryTests;

/// <summary>通过真实PG、Jena和RustFS发布后验证正式三能力、六态和来源边界。</summary>
[TestClass]
public sealed class GatewayTests
{
    /// <summary>正式模型来自真实OWL，能力版本实际绑定发布清单。</summary>
    [TestMethod]
    public async Task DescriptionUsesPublishedSchemaAndRegistry()
    {
        // 本次随机隔离资源及真实服务组合。
        using var fixture = new QueryFixture();
        // 先完成真实发布，查询不接受草稿。
        var release = await fixture.PublishAsync();
        // 读取正式模型，未知行业类不得写死在模块中。
        var result = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release, "describe_ontology"), default);
        Assert.AreEqual(SemanticQueryStatus.Found, result.Status);
        Assert.HasCount(5, result.Data.Single().Ontology!.ClassIris);
        Assert.HasCount(4, result.Data.Single().Ontology!.ObjectPropertyIris);
        Assert.HasCount(3, result.Snapshot.CapabilityVersions);
        Assert.AreEqual(fixture.Author.TraceId, result.TraceId);
    }

    /// <summary>唯一实体返回完整类型与真实hash/provenance，另一实例可重读稳定证据。</summary>
    [TestMethod]
    public async Task FoundEvidenceSurvivesNewServiceInstance()
    {
        // 每项测试独立组织和资产。
        using var fixture = new QueryFixture();
        // 正式发布含真实标准reification。
        var release = await fixture.PublishAsync();
        // 查询同一真实发布。
        var result = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default);
        Assert.AreEqual(SemanticQueryStatus.Found, result.Status);
        Assert.HasCount(1, result.Data);
        Assert.IsNotEmpty(result.Evidence);
        // 新scope产生全新EvidenceService，无进程缓存可依赖。
        using var scope = fixture.Provider.CreateScope();
        // 来源ID来自真实断言，而不是客户端指定object/hash。
        var evidence = await scope.ServiceProvider.GetRequiredService<IEvidenceService>().ReadAsync(fixture.Author, result.Evidence[0].EvidenceId, default);
        Assert.AreEqual(JsonSerializer.Serialize(result.Evidence[0]), JsonSerializer.Serialize(evidence));
        Assert.AreEqual(release.Manifest.ReleaseId, evidence.ModelVersion);
        Assert.AreEqual(release.Manifest.Hashes.DataHash, evidence.ContentHash);
        Assert.IsTrue(evidence.Synthetic);
        Assert.IsNull(evidence.MappingVersion);
    }

    /// <summary>同号两个厂保留不同IRI，只返回当前计划scope候选。</summary>
    [TestMethod]
    public async Task AmbiguousIdentityIsNeverStringJoined()
    {
        // 隔离正式发布包含双厂同号。
        using var fixture = new QueryFixture();
        // 完成发布再做业务查找。
        var release = await fixture.PublishAsync();
        // 不选厂区会得到两个获准候选。
        var result = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release) with { SiteId = null, MaxRows = 1 }, default);
        Assert.AreEqual(SemanticQueryStatus.Ambiguous, result.Status);
        Assert.HasCount(1, result.Candidates);
        Assert.IsTrue(result.Limited);
        Assert.IsEmpty(result.Data);
        // 明确厂区后只出现本站实体和证据。
        var selected = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default);
        Assert.IsTrue(selected.Data.All(value => value.Entity!.SiteId == "site-a"));
        Assert.IsTrue(selected.Evidence.All(value => value.Scope.SiteIds.SequenceEqual(["site-a"])));
    }

    /// <summary>已成功访问全部必需源但无业务匹配时才返回EMPTY。</summary>
    [TestMethod]
    public async Task MissingEntityIsEmpty()
    {
        // 新的真实服务组合。
        using var fixture = new QueryFixture();
        // 数据与来源都通过发布验证。
        var release = await fixture.PublishAsync();
        // SQL/SPARQL形状的业务号只作字面量等值匹配。
        var result = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release) with { ExternalId = "x' UNION SELECT * WHERE {?s ?p ?o}" }, default);
        Assert.AreEqual(SemanticQueryStatus.Empty, result.Status);
        Assert.IsEmpty(result.Data);
        Assert.IsEmpty(result.Evidence);
    }

    /// <summary>真实多对多关系与两端节点一致，行数预算确实截断且报告PARTIAL。</summary>
    [TestMethod]
    public async Task TraversalPreservesManyToManyAndBudget()
    {
        // 两个厂均有板坯到多轧制事件和多钢卷。
        using var fixture = new QueryFixture();
        // 完整发布确保源和图可用。
        var release = await fixture.PublishAsync();
        // 从板坯读取实际三层多对多子图。
        var plan = fixture.Plan(release, "traverse_relationships") with { ExternalId = "slab-1" };
        // 预算充足时包含上游和下游共七个实体与七条原始关系。
        var result = await fixture.Gateway.ExecuteAsync(fixture.Author, plan, default);
        Assert.AreEqual(SemanticQueryStatus.Found, result.Status);
        Assert.HasCount(7, result.Data.Where(value => value.Entity is not null).ToArray());
        Assert.HasCount(7, result.Data.Where(value => value.Relationship is not null).ToArray());
        Assert.IsTrue(result.Data.Where(value => value.Relationship is not null).All(value => result.Data.Any(node => node.Entity?.Iri == value.Relationship!.TargetIri)));
        // 同一版本小预算不能被实体与关系分组绕过。
        var partial = await fixture.Gateway.ExecuteAsync(fixture.Author, plan with { MaxRows = 2 }, default);
        Assert.AreEqual(SemanticQueryStatus.Partial, partial.Status);
        Assert.IsTrue(partial.Limited);
        Assert.IsTrue(partial.Data.Length <= 2);
    }

    /// <summary>缺失真实provenance不能伪造Evidence或返回完整FOUND。</summary>
    [TestMethod]
    public async Task MissingProvenanceIsPartial()
    {
        // 仅删除已知来源声明，不删除真实业务事实。
        using var fixture = new QueryFixture();
        // 原始synthetic样例可安全变换后重新真实发布。
        var source = fixture.Sources();
        // 只移除一个来源必需字段，SHACL业务约束仍有效。
        var changed = source with { DataTurtle = source.DataTurtle.Replace("op:sourceRecordId \"assertion-0\"", "op:unknownRecord \"assertion-0\"", StringComparison.Ordinal) };
        // 缺来源的发布也必须真实通过发布流程。
        var release = await fixture.PublishAsync(changed);
        // Gateway必须看出类型断言来源不完整。
        var result = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default);
        Assert.AreEqual(SemanticQueryStatus.Partial, result.Status);
        Assert.IsTrue(result.Diagnostics.Any(value => value.Code == "evidence_missing"));
    }

    /// <summary>明确目标不属于请求site时保留可信snapshot但不泄露数据。</summary>
    [TestMethod]
    public async Task ExplicitOutOfScopeEntityIsUnauthorized()
    {
        // 真实发布同时覆盖两个厂。
        using var fixture = new QueryFixture();
        // 请求主体拥有对象完整scope，但计划只选择site-a。
        var release = await fixture.PublishAsync();
        // 明确请求另厂IRI必须拒绝，不能悄悄扩大site。
        var result = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release) with { EntityIri = "urn:synthetic:" + fixture.Author.OrganizationId + ":site-b:local:heat-1" }, default);
        Assert.AreEqual(SemanticQueryStatus.Unauthorized, result.Status);
        Assert.IsEmpty(result.Data);
        Assert.IsEmpty(result.Candidates);
        Assert.IsEmpty(result.Evidence);
    }

    /// <summary>历史证据重新按完整发布scope授权，猜测ID和缩小scope不能绕过。</summary>
    [TestMethod]
    public async Task EvidenceIsReauthorizedAndIdsCannotChooseObjects()
    {
        // 每次证据读取都走Catalog和实际源校验。
        using var fixture = new QueryFixture();
        // 完整双厂发布。
        var release = await fixture.PublishAsync();
        // 先以合法主体取得可信证据。
        var result = await fixture.Gateway.ExecuteAsync(fixture.Author, fixture.Plan(release), default);
        // 后续主体少一个厂权限，不能通过旧证据绕过对象scope。
        var denied = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Evidence.ReadAsync(fixture.Author with { SiteIds = ["site-a"] }, result.Evidence[0].EvidenceId, default));
        Assert.AreEqual(403, denied.Status);
        // 畸形定位符不能成为任意URL或S3对象读取。
        var invalid = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Evidence.ReadAsync(fixture.Author, "https://evil.invalid/source", default));
        Assert.AreEqual(404, invalid.Status);
    }

    /// <summary>未知路径、危险IRI、错误能力版本和越界预算在应用层明确拒绝。</summary>
    [TestMethod]
    public async Task InvalidPlansAreRejected()
    {
        // 使用真实已发布目录检验应用层，不依赖HTTP保护。
        using var fixture = new QueryFixture();
        // 唯一资产和真实registry版本。
        var release = await fixture.PublishAsync();
        // 各种非法有限计划必须失败，不能返回EMPTY。
        var plan = fixture.Plan(release);
        foreach (var invalid in new[] { plan with { Depth = 6 }, plan with { MaxRows = 101 }, plan with { TimeoutMs = 5001 }, plan with { EntityIri = "urn:x> } UNION {?s ?p ?o}" }, plan with { CapabilityVersion = "v1" }, plan with { RelationshipIris = ["urn:unknown:relationship"] } })
        {
            // 验证服务端确定错误码与HTTP语义。
            var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Gateway.ExecuteAsync(fixture.Author, invalid, default));
            Assert.AreEqual(422, failure.Status);
        }
    }

    /// <summary>无活动发布时返回404，不能生成看似有效的空快照。</summary>
    [TestMethod]
    public async Task AbsentReleaseAndRoleAreExplicitErrors()
    {
        // 不创建任何发布即可验证前置错误。
        using var fixture = new QueryFixture();
        // 能力版本来自真实登记。
        var capability = fixture.Gateway.GetCapabilities().First();
        // 不存在的资产不会有默认成功snapshot。
        var plan = new SemanticQueryPlan { AssetId = "missing", CapabilityId = capability.Id, CapabilityVersion = capability.Version, Depth = 1, MaxRows = 1, TimeoutMs = 5000 };
        // Catalog真实查询当前PG。
        var absent = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Gateway.ExecuteAsync(fixture.Author, plan, default));
        Assert.AreEqual(404, absent.Status);
        // 角色简写不能获得完整platform角色权限。
        var denied = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Gateway.ExecuteAsync(fixture.Author with { Roles = ["viewer"] }, plan, default));
        Assert.AreEqual(403, denied.Status);
    }
}
