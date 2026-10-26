using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.Ontology;
using OntologyPlatform.Modules.Publishing;

namespace OntologyPlatform.PublishingTests;

/// <summary>只使用脚本当前创建的临时PG、RustFS和Jena；所有正常执行均为真实依赖。</summary>
internal sealed class PublishingFixture : IDisposable
{
    /// <summary>测试根服务容器。</summary>
    internal ServiceProvider Provider { get; }

    /// <summary>当前测试的独立应用scope。</summary>
    private readonly IServiceScope scope;

    /// <summary>测试可推进的服务端审批时钟。</summary>
    internal TestClock Clock { get; } = new();

    /// <summary>每个测试独立组织，避免故障触发器或活动指针互扰。</summary>
    internal ActorContext Author { get; } = new() { SubjectId = "author", OrganizationId = "pub-" + Guid.NewGuid().ToString("N"), SiteIds = ["site-a", "site-b"], Roles = ["platform.operator"], TraceId = Guid.NewGuid().ToString("N"), CorrelationId = Guid.NewGuid().ToString("N") };

    /// <summary>独立审核者沿用同完整scope。</summary>
    internal ActorContext Reviewer => Author with { SubjectId = "reviewer", Roles = ["platform.auditor"] };

    /// <summary>实际发布用例。</summary>
    internal IPublishingService Service => scope.ServiceProvider.GetRequiredService<IPublishingService>();

    /// <summary>实际草稿用例。</summary>
    internal IOntologyService Ontology => scope.ServiceProvider.GetRequiredService<IOntologyService>();

    /// <summary>测试仅在自己的临时库注入触发器和检查真实事实。</summary>
    internal PublishingDbContext Database => scope.ServiceProvider.GetRequiredService<PublishingDbContext>();

    /// <summary>正式目录使用真实对象与图。</summary>
    internal IReleaseCatalog Catalog => scope.ServiceProvider.GetRequiredService<IReleaseCatalog>();

    /// <summary>真实S3适配。</summary>
    internal IReleaseArtifactStore Artifacts => scope.ServiceProvider.GetRequiredService<IReleaseArtifactStore>();

    /// <summary>在真实HTTP传输前后仅注入失败，不伪造成功结果。</summary>
    internal Func<HttpRequestMessage, CancellationToken, Task>? Gate { get; set; }

    /// <summary>通过环境获取本轮新建资源，不读取历史凭证文件。</summary>
    internal PublishingFixture()
    {
        // 缺少显式隔离环境应标NOT_RUN，而不是调用历史运行资源。
        var connection = Environment.GetEnvironmentVariable("G2_PUB_PG");
        if (connection is null) Assert.Inconclusive("NOT_RUN: 请通过release-faults.py创建隔离资源。");
        // 临时服务地址来自同一次脚本运行。
        var jena = Environment.GetEnvironmentVariable("G2_PUB_JENA");
        // 签名配置只在进程内存在，测试输出不展示其值。
        var configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["ConnectionStrings:governance"] = connection,
            ["Semantics:ValidationOrigin"] = jena + "/validation/",
            ["Semantics:PublishedOrigin"] = jena + "/ontology/",
            ["Publishing:S3Endpoint"] = Environment.GetEnvironmentVariable("G2_PUB_S3"),
            ["Publishing:AccessKey"] = Environment.GetEnvironmentVariable("RUSTFS_ACCESS_KEY"),
            ["Publishing:SecretKey"] = Environment.GetEnvironmentVariable("RUSTFS_SECRET_KEY"),
            ["Publishing:Bucket"] = "g2-pub-tests"
        }).Build();
        // 保持实际生产模块组合，ValidateOnBuild也验证没有Catalog依赖环。
        var services = new ServiceCollection();
        services.AddSingleton<IConfiguration>(configuration);
        services.AddSingleton<TimeProvider>(Clock);
        services.AddDbContextFactory<GovernanceDbContext>(options => options.UseNpgsql(connection, database => database.MigrationsHistoryTable("__EFMigrationsHistory", "governance")));
        services.AddSingleton<ITransactionalAuditWriter, TransactionalAuditWriter>();
        services.AddOntologyModule(configuration);
        services.AddPublishingModule(configuration);
        services.AddHttpClient("ontology-jena").ConfigurePrimaryHttpMessageHandler(() => new FaultGateHandler(this));
        services.AddHttpClient("publishing-s3").ConfigurePrimaryHttpMessageHandler(() => new FaultGateHandler(this));
        Provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateOnBuild = true, ValidateScopes = true });
        scope = Provider.CreateScope();
    }

    /// <summary>正常源码来自已提交Synthetic样例，包含真实OWL/SHACL及来源。</summary>
    internal static SourceBundle Sources()
    {
        // 路径由脚本显式传入，避免cwd差异。
        var root = Environment.GetEnvironmentVariable("G2_PUB_SAMPLES")!;
        return new SourceBundle { OntologyTurtle = File.ReadAllText(Path.Combine(root, "ontology.ttl")), ShapesTurtle = File.ReadAllText(Path.Combine(root, "shapes.ttl")), VocabularyTurtle = File.ReadAllText(Path.Combine(root, "vocabulary.ttl")), DataTurtle = File.ReadAllText(Path.Combine(root, "data.ttl")) };
    }

    /// <summary>每个命令唯一键，调用者可保存对象验证精确重放。</summary>
    internal static CommandContext Command(long revision = 0) => new() { CommandId = Guid.NewGuid().ToString("N"), IdempotencyKey = Guid.NewGuid().ToString("N"), ExpectedRevision = revision, Reason = "Synthetic发布验证" };

    /// <summary>真实创建、解析、保存并SHACL验证固定草稿。</summary>
    internal async Task<(OntologyDraft Draft, ReleaseProposal Proposal)> ProposalAsync()
    {
        // 创建当前测试专属完整scope草稿。
        var draft = await Ontology.CreateAsync(Author, new CreateDraftRequest { Name = "Synthetic", Scope = new ResourceScope { OrganizationId = Author.OrganizationId, SiteIds = Author.SiteIds }, Sources = Sources(), Command = Command() }, default);
        return (draft, await ProposalForAsync(draft));
    }

    /// <summary>指定当前草稿必须取得真实成功报告再提交。</summary>
    internal async Task<ReleaseProposal> ProposalForAsync(OntologyDraft draft)
    {
        // 真正调用Jena SHACL，禁止自造conforms事实。
        var report = await Ontology.ValidateAsync(Author, draft.DraftId, new ValidateDraftRequest { Revision = draft.Revision, Hashes = draft.Hashes, Command = Command(draft.Revision) }, default);
        Assert.IsTrue(report.Conforms);
        return await Service.CreateProposalAsync(Author, new CreateProposalRequest { Kind = ProposalKind.Publish, DraftId = draft.DraftId, DraftRevision = draft.Revision, Hashes = draft.Hashes, ValidationReportId = report.ReportId, Command = Command(draft.Revision) }, default);
    }

    /// <summary>通过独立审核者真实决定审批。</summary>
    internal Task<ReleaseProposal> ApproveAsync(ReleaseProposal proposal) => Service.DecideAsync(Reviewer, proposal.ProposalId, new ApprovalDecisionRequest { Decision = ApprovalDecision.Approve, Command = Command(proposal.Revision) }, default);

    /// <summary>构造精确提案修订及活动CAS命令。</summary>
    internal static ActivateReleaseRequest Activation(ReleaseProposal proposal, ReleaseActivation? previous = null) => new() { ProposalId = proposal.ProposalId, ExpectedActivationRevision = previous?.ActivationRevision ?? 0, ExpectedActiveReleaseId = previous?.ReleaseId, Command = Command(proposal.Revision) };

    /// <summary>释放请求scope和所有HTTP池。</summary>
    public void Dispose()
    {
        scope.Dispose();
        Provider.Dispose();
    }

    /// <summary>测试时钟只推进审批时间，不改系统全局时钟。</summary>
    internal sealed class TestClock : TimeProvider
    {
        /// <summary>本测试批准时间偏移。</summary>
        internal TimeSpan Offset { get; set; }

        /// <summary>实际UTC加测试偏移，签名测试默认零偏移。</summary>
        public override DateTimeOffset GetUtcNow() => DateTimeOffset.UtcNow + Offset;
    }

    /// <summary>失败注入后仍执行原生真实HTTP，不产生任何假成功响应。</summary>
    private sealed class FaultGateHandler : DelegatingHandler
    {
        /// <summary>当前隔离fixture的动态失败门。</summary>
        private readonly PublishingFixture fixture;

        /// <summary>禁用代理和重定向。</summary>
        internal FaultGateHandler(PublishingFixture fixture) : base(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false }) => this.fixture = fixture;

        /// <summary>仅在明确测试时故障，其余调用直接真实传输。</summary>
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            if (fixture.Gate is not null) await fixture.Gate(request, token);
            return await base.SendAsync(request, token);
        }
    }
}
