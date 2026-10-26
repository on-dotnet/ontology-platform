using System.Net.Http.Headers;
using System.Text;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Publishing;

namespace OntologyPlatform.PublishingTests;

/// <summary>已激活后真实图损坏必须不可用，调和失败不能偷偷切版。</summary>
[TestClass]
public sealed class PublishedIntegrityTests
{
    /// <summary>真实篡改临时Jena固定图，Catalog和Outbox都失败关闭，恢复后同事件重试。</summary>
    [TestMethod]
    public async Task DamagedPublishedGraphUnavailableAndReconciliationRetries()
    {
        // 测试只连接当前脚本临时Jena，不操作历史或生产数据。
        using var fixture = new PublishingFixture();
        // 准备实际可验证来源。
        var item = await fixture.ProposalAsync();
        // 真正事务成功后再破坏外部图，验证不宣称跨服务ACID。
        var active = await fixture.Service.ActivateAsync(fixture.Author, PublishingFixture.Activation(await fixture.ApproveAsync(item.Proposal)), default);
        // 图URL来自服务器固定manifest而非任意用户URL。
        var graphUrl = Environment.GetEnvironmentVariable("G2_PUB_JENA") + "/ontology/data?graph=" + Uri.EscapeDataString(active.Manifest.DataGraphIri);
        // 真实HTTP故障施加仅针对本测试专属发布图。
        using var client = new HttpClient(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false });
        // 替换为合法但错误的数据图，避免只测语法失败。
        using var content = new StringContent("<urn:wrong> <urn:wrong> <urn:wrong> .", Encoding.UTF8, "text/turtle");
        // 真正Jena写入后再执行Catalog读取。
        using var response = await client.PutAsync(graphUrl, content);
        Assert.IsTrue(response.IsSuccessStatusCode);
        // 错版不能成为EMPTY，也不能自动返回其他发布。
        var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Catalog.ReadAsync(fixture.Author, active.ReleaseId, default));
        Assert.AreEqual(503, failure.Status);
        await fixture.Database.Outbox.Where(row => row.EventId == active.OutboxEventId).ExecuteUpdateAsync(update => update.SetProperty(row => row.CreatedAtUtc, DateTimeOffset.UnixEpoch));
        // 调和也检查真实图，而不是仅看到PG状态便派发成功。
        using var worker = new ReleaseOutboxDispatcher(fixture.Provider.GetRequiredService<IServiceScopeFactory>(), fixture.Clock);
        Assert.IsTrue(await worker.DispatchOnceAsync(default));
        Assert.AreEqual(0, await fixture.Database.Receipts.CountAsync(row => row.EventId == active.OutboxEventId));
        Assert.AreEqual(active.ReleaseId, (await fixture.Database.ActiveReleases.AsNoTracking().SingleAsync(row => row.AssetId == item.Draft.AssetId)).ReleaseId);
        // 测试恢复为完全相同固定版本，产品接口没有公开修复或故障endpoint。
        await fixture.Provider.GetRequiredService<ISemanticRuntime>().DeployAsync(active.Manifest, item.Draft.Sources, default);
        await fixture.Database.Outbox.Where(row => row.EventId == active.OutboxEventId).ExecuteUpdateAsync(update => update.SetProperty(row => row.NextAttemptAtUtc, DateTimeOffset.UtcNow.AddSeconds(-1)));
        Assert.IsTrue(await worker.DispatchOnceAsync(default));
        Assert.AreEqual(1, await fixture.Database.Receipts.CountAsync(row => row.EventId == active.OutboxEventId));
        Assert.AreEqual(active.ManifestHash, (await fixture.Catalog.ReadAsync(fixture.Author, active.ReleaseId, default)).ManifestHash);
    }
}
