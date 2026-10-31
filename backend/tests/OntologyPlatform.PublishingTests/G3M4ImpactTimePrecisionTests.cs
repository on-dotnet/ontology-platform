using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.PublishingTests;

/// <summary>真实锁读报告envelope微秒精度正反例，不改变业务有效时间七位精度。</summary>
[TestClass]
public sealed class G3M4ImpactTimePrecisionTests
{
    /// <summary>同一非微秒时钟可取得发布影响绑定；真正早于assessment仍失败关闭。</summary>
    /// <param name="early">只在负例保持canonical自洽地注入真正提前的生成envelope。</param>
    [TestMethod]
    [DataRow(false)]
    [DataRow(true)]
    public async Task FixedSevenDigitClockUsesConsistentEnvelopePrecision(bool early)
    {
        // 使用当前实际秒构造固定.1234567，签名/依赖时间不偏移到未来机器时钟。
        var now = DateTimeOffset.UtcNow;
        // 本测试期间每次GetUtcNow严格相同且有七个非微秒tick。
        var fixedTime = new DateTimeOffset(now.Year, now.Month, now.Day, now.Hour, now.Minute, now.Second, TimeSpan.Zero).AddTicks(1234567);
        // 现有真实PG/Jena/RustFS fixture只增加可选TimeProvider注入。
        using var fixture = new PublishingFixture(new FixedClock(fixedTime));
        // 最小合法四源排除无关源/SHACL结构，业务日期仍未经过envelope归一。
        var sources = new SourceBundle { OntologyTurtle = "<urn:synthetic:precision:C> a <http://www.w3.org/2002/07/owl#Class> .", DataTurtle = "<urn:synthetic:precision:i> a <urn:synthetic:precision:C> ." };
        // 实际生产创建及assessment，不伪造成功评估。
        var draft = await fixture.Ontology.CreateAsync(fixture.Author, new CreateDraftRequest { Name = "Synthetic precision", Scope = new ResourceScope { OrganizationId = fixture.Author.OrganizationId, SiteIds = fixture.Author.SiteIds }, Sources = sources, Command = PublishingFixture.Command() }, default);
        // 原assessment保留七位原时间，报告PG envelope为微秒保存。
        var assessment = await ((IG3OntologyService)fixture.Ontology).AssessAsync(fixture.Author, draft.DraftId, new ValidateDraftRequest { Revision = 1, Hashes = draft.Hashes, Command = PublishingFixture.Command(1) }, default);
        // 真实Catalog确认本资产无active，INITIAL不能仅靠mock声称首次发布。
        var reference = new VersionRef { Kind = VersionRefKind.Draft, Id = draft.DraftId, Revision = 1 };
        // 精确assessment和源固定在持久报告。
        var report = await ((IG3ImpactService)fixture.Ontology).GenerateImpactAsync(fixture.Author, new GenerateImpactReportRequest { From = reference, To = reference, BaselineKind = ImpactBaselineKind.Initial, AssessmentId = assessment.AssessmentId, Command = PublishingFixture.Command(1) }, default);
        Assert.IsTrue(report.PublishEligible);
        Assert.AreEqual(7L, assessment.AssessedAtUtc.Ticks - report.GeneratedAtUtc.Ticks);
        if (early)
        {
            // 只在隔离PG注入实际提前1ms，期限同步保持<=生成+24h，canonical按合同仍自洽。
            using var mutationScope = fixture.Provider.CreateScope();
            // 数据仅写Ontology自己的测试记录，不改其它项目或生产。
            var ontology = mutationScope.ServiceProvider.GetRequiredService<OntologyDbContext>();
            // 持久索引和JSON都采用相同微秒值，负例不能靠普通hash或索引错误遮蔽时间检查。
            var row = await ontology.ImpactReports.SingleAsync(item => item.ReportId == report.ReportId);
            // canonical明确排除envelope，这里保留原固定输入及内容hash。
            var shifted = report with { GeneratedAtUtc = report.GeneratedAtUtc.AddMilliseconds(-1), ExpiresAtUtc = report.GeneratedAtUtc.AddMilliseconds(-1).AddHours(24) };
            Assert.AreEqual(report.CanonicalHash, ImpactContractRules.CanonicalHash(shifted));
            row.GeneratedAtUtc = shifted.GeneratedAtUtc;
            row.ExpiresAtUtc = shifted.ExpiresAtUtc;
            row.ReportJson = JsonSerializer.Serialize(shifted);
            await ontology.SaveChangesAsync();
        }
        // 使用发布方真实同物理事务，按现有draft锁次序核验。
        await using var transaction = await fixture.Database.Database.BeginTransactionAsync();
        // 同连接草稿reader的测试scope也明确释放，不留下未拥有上下文。
        using var draftScope = fixture.Provider.CreateScope();
        // 当前已锁草稿和真实评估是发布资格的唯一目标。
        var snapshot = await draftScope.ServiceProvider.GetRequiredService<IDraftPublicationReader>().LockForPublicationAsync(fixture.Author, draft.DraftId, 1, draft.Hashes, assessment.ValidationReportId, fixture.Database.Database.GetDbConnection(), transaction.GetDbTransaction(), default);
        // 当前测试只验真实资格锁读，不冒充已完成发布或Run执行。
        using var readerScope = fixture.Provider.CreateScope();
        // 真实模块接口按已冻结合同重用同一连接事务。
        var reader = readerScope.ServiceProvider.GetRequiredService<IImpactPublicationReader>();
        if (early)
        {
            // 真正比assessment早1ms仍不能因统一精度放行。
            var error = await Assert.ThrowsAsync<SemanticOperationException>(() => reader.LockForPublicationAsync(fixture.Author, report.ReportId, report.CanonicalHash, snapshot, fixture.Database.Database.GetDbConnection(), transaction.GetDbTransaction(), default));
            Assert.AreEqual("impact_binding_conflict", error.Code);
        }
        else
        {
            // 仅丢失7个100ns tick的原精度角点应返回精确可审批绑定。
            var binding = await reader.LockForPublicationAsync(fixture.Author, report.ReportId, report.CanonicalHash, snapshot, fixture.Database.Database.GetDbConnection(), transaction.GetDbTransaction(), default);
            Assert.AreEqual(report.CanonicalHash, binding.CanonicalHash);
            Assert.AreEqual(report.GeneratedAtUtc, binding.GeneratedAtUtc);
        }
        await transaction.RollbackAsync();
    }

    /// <summary>本测试唯一固定UTC来源，与机器时区/默认时间配置无关。</summary>
    private sealed class FixedClock : TimeProvider
    {
        /// <summary>构造时固定的七位精度UTC。</summary>
        private readonly DateTimeOffset value;

        /// <summary>保存一次受控时间，不修改系统时钟。</summary>
        internal FixedClock(DateTimeOffset value) => this.value = value;

        /// <summary>每次返回同一个已明确时区的时刻。</summary>
        public override DateTimeOffset GetUtcNow() => value;
    }
}
