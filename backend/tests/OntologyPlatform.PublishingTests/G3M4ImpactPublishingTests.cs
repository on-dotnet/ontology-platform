using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.PublishingTests;

/// <summary>真实PG/Jena/RustFS上的影响审批四点绑定、基线与成功回执恢复。</summary>
[TestClass]
public sealed class G3M4ImpactPublishingTests
{
    /// <summary>新发布固定持久报告且目录可追溯，已成功回执不因报告随后到期或旧提案字段缺失失效。</summary>
    [TestMethod]
    public async Task PublicationTracesImpactAndRecoversSuccessfulReceipt()
    {
        // 全部成功路径都使用当前运行的真实三依赖。
        using var fixture = new PublishingFixture();
        // 当前fixture已通过真实assessment及INITIAL影响资格。
        var item = await fixture.ProposalAsync();
        // 真实异人批准绑定报告的全部字段。
        var approved = await fixture.ApproveAsync(item.Proposal);
        // 保存同一命令以验证精确重放。
        var request = PublishingFixture.Activation(approved);
        // 真实对象上传、图部署、双重回验及PG原子激活。
        var result = await fixture.Service.ActivateAsync(fixture.Author, request, default);
        // 目录由原ProposalId追溯，清单仍使用既有格式。
        var summary = await fixture.Catalog.ReadAsync(fixture.Author, result.ReleaseId, default);
        Assert.AreEqual(approved.Impact, summary.Impact);
        Assert.IsNotNull(summary.Impact);
        Assert.AreEqual(2, result.Manifest.SchemaVersion);
        Assert.AreEqual(approved.Semantics, result.Manifest.Semantics);
        Assert.AreEqual(ImpactBaselineKind.Initial, summary.Impact.BaselineKind);
        // 隔离测试将原提案模拟为已成功历史无Impact形式；不修改原清单字节。
        var row = await fixture.Database.Proposals.SingleAsync(value => value.ProposalId == approved.ProposalId);
        row.ProposalJson = JsonSerializer.Serialize(approved with { Impact = null });
        await fixture.Database.SaveChangesAsync();
        fixture.Clock.Offset = TimeSpan.FromHours(25);
        fixture.Gate = (_, _) => throw new HttpRequestException("Synthetic committed-receipt dependency failure");
        Assert.AreEqual(JsonSerializer.Serialize(result), JsonSerializer.Serialize(await fixture.Service.ActivateAsync(fixture.Author, request, default)));
        Assert.AreEqual(1, await fixture.Database.Outbox.CountAsync(value => value.ReleaseId == result.ReleaseId));
        Assert.AreEqual(1, await fixture.Database.Activations.CountAsync(value => value.AssetId == item.Draft.AssetId));
    }

    /// <summary>缺失、伪造、过期及跨修订报告不能创建新发布提案。</summary>
    /// <param name="scenario">只改变一个报告输入或其目标事实。</param>
    /// <param name="status">相应关口固定HTTP错误状态。</param>
    /// <param name="code">相应关口可解释业务错误码。</param>
    [TestMethod]
    [DataRow("missing", 422, "impact_required")]
    [DataRow("forged", 409, "impact_binding_conflict")]
    [DataRow("expired", 409, "impact_expired")]
    [DataRow("cross-version", 409, "impact_target_conflict")]
    public async Task ProposalRejectsUnboundReports(string scenario, int status, string code)
    {
        // 当前fixture每条负例都有原真实可发布事实。
        using var fixture = new PublishingFixture();
        // 原提案证明当前源码和评估真实可用。
        var item = await fixture.ProposalAsync();
        // 默认使用同一精确草稿目标及SHACL报告。
        var draft = item.Draft;
        // 真实SHACL/评估ID来自原已提交提案。
        var validation = item.Proposal.ValidationReportId!;
        if (scenario == "expired") await ExpireAsync(fixture, item.Proposal.Impact!.ReportId);
        if (scenario == "cross-version")
        {
            // 新字节修订及新assessment仍不能套用旧报告。
            draft = await fixture.Ontology.SaveAsync(fixture.Author, draft.DraftId, new SaveDraftRequest { Name = draft.Name, Sources = draft.Sources with { DataTurtle = draft.Sources.DataTurtle + "\n# new exact input\n" }, Command = PublishingFixture.Command(draft.Revision) }, default);
            // 真实验证使负例具体落在影响目标绑定，不被旧validation遮蔽。
            var report = await fixture.Ontology.ValidateAsync(fixture.Author, draft.DraftId, new ValidateDraftRequest { Revision = draft.Revision, Hashes = draft.Hashes, Command = PublishingFixture.Command(draft.Revision) }, default);
            validation = report.ReportId;
        }
        // 只有missing同时不提供两个可选字段，其余固定原报告ID。
        var request = new CreateProposalRequest { Kind = ProposalKind.Publish, DraftId = draft.DraftId, DraftRevision = draft.Revision, Hashes = draft.Hashes, ValidationReportId = validation, ImpactReportId = scenario == "missing" ? null : item.Proposal.Impact!.ReportId, ImpactHash = scenario == "missing" ? null : scenario == "forged" ? new string('0', 64) : item.Proposal.Impact!.CanonicalHash, Command = PublishingFixture.Command(draft.Revision) };
        // 错误码明确证明相应关口拒绝。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.CreateProposalAsync(fixture.Author, request, default));
        Assert.AreEqual(status, error.Status);
        Assert.AreEqual(code, error.Code);
    }

    /// <summary>审批、准备、最终提交及失败预留重试均复核当前持久报告期限。</summary>
    /// <param name="stage">通过真实传输在指定发布关口之后注入过期。</param>
    [TestMethod]
    [DataRow("approval")]
    [DataRow("prepare")]
    [DataRow("final")]
    [DataRow("retry")]
    public async Task EveryPublicationBoundaryRechecksImpact(string stage)
    {
        // 不伪造成功依赖，仅修改当前测试自己持久报告的envelope。
        using var fixture = new PublishingFixture();
        // 原报告、评估、源码和权限全部有效。
        var item = await fixture.ProposalAsync();
        if (stage == "approval")
        {
            await ExpireAsync(fixture, item.Proposal.Impact!.ReportId);
            // 原assessment未到期，拒绝必须来自报告期限。
            var error = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.ApproveAsync(item.Proposal));
            Assert.AreEqual("impact_expired", error.Code);
            return;
        }
        // 三个激活关口先取得真实异人批准。
        var approved = await fixture.ApproveAsync(item.Proposal);
        // 同一命令在失败预留重试中必须保持。
        var request = PublishingFixture.Activation(approved);
        if (stage == "prepare") await ExpireAsync(fixture, approved.Impact!.ReportId);
        if (stage == "final")
        {
            // 准备事务已提交，第一次真实S3写前仅过期原报告，随后仍执行真实传输。
            var injected = false;
            fixture.Gate = async (message, _) =>
            {
                if (!injected && message.Method == HttpMethod.Put && message.RequestUri!.AbsolutePath.Contains("/source-", StringComparison.Ordinal))
                {
                    injected = true;
                    await ExpireAsync(fixture, approved.Impact!.ReportId);
                }
            };
        }
        if (stage == "retry")
        {
            fixture.Gate = (message, _) => message.Method == HttpMethod.Put ? throw new HttpRequestException("Synthetic prepared transport failure") : Task.CompletedTask;
            await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.ActivateAsync(fixture.Author, request, default));
            fixture.Gate = null;
            await ExpireAsync(fixture, approved.Impact!.ReportId);
        }
        // 未提交的失败与过期永远不能形成active/Outbox事实。
        var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.ActivateAsync(fixture.Author, request, default));
        Assert.AreEqual("impact_expired", failure.Code);
        Assert.AreEqual(0, await fixture.Database.ActiveReleases.CountAsync(value => value.AssetId == item.Draft.AssetId));
        Assert.AreEqual(0, await fixture.Database.Outbox.CountAsync(value => fixture.Database.Releases.Any(release => release.ReleaseId == value.ReleaseId && release.AssetId == item.Draft.AssetId)));
    }

    /// <summary>assessment本身或受控profile漂移后，原影响提案不能取得审核决定。</summary>
    /// <param name="profile">是否模拟同一测试评估的受控历史profile身份变化。</param>
    [TestMethod]
    [DataRow(false)]
    [DataRow(true)]
    public async Task ApprovalRejectsChangedAssessmentOrProfile(bool profile)
    {
        // 原提案先由当前生产服务取得完整真实资格。
        using var fixture = new PublishingFixture();
        // 固定报告及提案持有同一个原评估内容hash。
        var item = await fixture.ProposalAsync();
        using (var mutation = fixture.Provider.CreateScope())
        {
            // 故障注入仅更新当前测试自己的Ontology评估，保留其ID、源码及真实SHACL事实。
            var ontology = mutation.ServiceProvider.GetRequiredService<OntologyDbContext>();
            // 持久原评估是实际Validate产生，不能伪造conforms成功。
            var row = await ontology.Assessments.SingleAsync(value => value.AssessmentId == item.Proposal.Semantics!.AssessmentId);
            // 原事实完成后刻意改变待核验的评估envelope或策略身份。
            var assessment = JsonSerializer.Deserialize<SemanticAssessment>(row.AssessmentJson)!;
            // 精确历史策略来自已有永久工厂，不发明未知profile或修改公共合同。
            var legacy = SemanticProfile.LegacyM3();
            // 两种负例都重新计算评估自身hash，避免只测无效JSON/hash遮蔽真实绑定漂移。
            var changed = profile ? assessment with { ProfileVersion = legacy.Version, ProfileHash = legacy.Hash, AssessmentHash = "" } : assessment with { AssessedAtUtc = assessment.AssessedAtUtc.AddTicks(-10), AssessmentHash = "" };
            changed = changed with { AssessmentHash = SemanticProfile.AssessmentHash(changed) };
            row.AssessmentJson = JsonSerializer.Serialize(changed);
            await ontology.SaveChangesAsync();
        }
        // 当前同事务draft reader与原提案/报告绑定共同失败关闭。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.ApproveAsync(item.Proposal));
        Assert.AreEqual(409, error.Status);
        Assert.AreEqual("assessment_binding_conflict", error.Code);
    }

    /// <summary>两份INITIAL批准不能在已产生active后沿用首次基线，旧无报告待批也不能继续。</summary>
    [TestMethod]
    public async Task InitialApprovalCannotSurviveActiveBaselineOrMissingBinding()
    {
        // 同一真实资产的两个INITIAL报告输入幂等复用，但提案不同。
        using var fixture = new PublishingFixture();
        // 第一个真实INITIAL待批。
        var item = await fixture.ProposalAsync();
        // 第二个真实INITIAL待批在激活前同样有效。
        var second = await fixture.ProposalForAsync(item.Draft);
        // 第三个用作旧待批缺失报告兼容负例。
        var legacy = await fixture.ProposalForAsync(item.Draft);
        // 仅在当前隔离测试行模拟旧未激活提案，不伪造成功审批。
        var row = await fixture.Database.Proposals.SingleAsync(value => value.ProposalId == legacy.ProposalId);
        row.ProposalJson = JsonSerializer.Serialize(legacy with { Impact = null });
        await fixture.Database.SaveChangesAsync();
        Assert.AreEqual("impact_required", (await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.ApproveAsync(legacy))).Code);
        // 两个合法提案都先完成独立批准。
        var firstApproved = await fixture.ApproveAsync(item.Proposal);
        // 第二批准发生在基线仍为空时。
        var secondApproved = await fixture.ApproveAsync(second);
        // 第一个真实正式版本改变active基线。
        var active = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(firstApproved), default);
        // 提交当前正确CAS以确保拒绝来自INITIAL基线，不是旧活动修订。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(secondApproved, active), default));
        Assert.AreEqual("impact_baseline_conflict", error.Code);
        Assert.AreEqual(1, await fixture.Database.Activations.CountAsync(value => value.AssetId == item.Draft.AssetId));
    }

    /// <summary>仅隔离测试将envelope改为真实已过期，canonical/索引保持一致且assessment仍有效。</summary>
    private static async Task ExpireAsync(PublishingFixture fixture, string reportId)
    {
        // 独立context避免和发布事务共享ChangeTracker或连接。
        using var scope = fixture.Provider.CreateScope();
        // 当前测试自己的Ontology记录，不跨模块生产写入。
        var database = scope.ServiceProvider.GetRequiredService<OntologyDbContext>();
        // 从持久原文获取当前报告而非构造假成功内容。
        var row = await database.ImpactReports.SingleAsync(value => value.ReportId == reportId);
        // 固定内容和hash不动，仅过期envelope按合同不进入canonical。
        var report = JsonSerializer.Deserialize<ImpactReport>(row.ReportJson)!;
        // 显式微秒对齐保持PostgreSQL envelope与JSON精确一致。
        var now = DateTimeOffset.UtcNow;
        // 过期值与生成值均在过去且顺序正确，不触发无关索引或hash错误。
        var expiry = new DateTimeOffset(now.Ticks - now.Ticks % 10, TimeSpan.Zero).AddMinutes(-1);
        // 报告固定输入/内容保持原值，assessment本身不变。
        var expired = report with { GeneratedAtUtc = expiry.AddMinutes(-1), ExpiresAtUtc = expiry };
        Assert.AreEqual(report.CanonicalHash, ImpactContractRules.CanonicalHash(expired));
        row.GeneratedAtUtc = expired.GeneratedAtUtc;
        row.ExpiresAtUtc = expired.ExpiresAtUtc;
        row.ReportJson = JsonSerializer.Serialize(expired);
        await database.SaveChangesAsync();
    }
}
