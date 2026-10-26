using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Publishing;

namespace OntologyPlatform.PublishingTests;

/// <summary>应用入口在触碰任何依赖前阻断混合或缺失的发布/回滚字段。</summary>
[TestClass]
public sealed class ProposalContractTests
{
    /// <summary>可空传输字段不意味着允许混合分支，失败须先于任何外部调用。</summary>
    [TestMethod]
    [DataRow("missing-publish")]
    [DataRow("mixed-rollback")]
    [DataRow("hash-invalid")]
    public async Task InvalidDiscriminatedRequestRejectedBeforeDependencies(string condition)
    {
        // 此测试刻意不提供外部依赖；合法请求必须由真实集成测试验证。
        var service = new PublishingService(null!, null!, null!, null!, null!, null!, null!, null!, TimeProvider.System);
        // 合法可信角色通过第一道边界，避免负例因其他原因失败。
        var actor = new ActorContext { SubjectId = "author", OrganizationId = "org", SiteIds = ["site-a"], Roles = ["platform.operator"], TraceId = "trace", CorrelationId = "correlation" };
        // 三个输入分别缺发布绑定、混入草稿字段或携带非法hash。
        var request = condition switch
        {
            "missing-publish" => new CreateProposalRequest { Kind = ProposalKind.Publish, Command = PublishingFixture.Command() },
            "mixed-rollback" => new CreateProposalRequest { Kind = ProposalKind.Rollback, DraftId = "draft", TargetReleaseId = "release", TargetManifestHash = new string('a', 64), Command = PublishingFixture.Command() },
            _ => new CreateProposalRequest { Kind = ProposalKind.Rollback, TargetReleaseId = "release", TargetManifestHash = "not-a-hash", Command = PublishingFixture.Command() }
        };
        // 若访问任何未提供依赖会得到NullReference而非成功伪证。
        var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => service.CreateProposalAsync(actor, request, default));
        Assert.AreEqual(422, failure.Status);
        Assert.AreEqual("proposal_payload_invalid", failure.Code);
    }
}
