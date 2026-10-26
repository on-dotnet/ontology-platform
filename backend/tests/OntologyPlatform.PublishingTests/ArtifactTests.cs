using System.Text;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.PublishingTests;

/// <summary>真实RustFS SigV4及不可变条件写负例，不能以模拟服务替代。</summary>
[TestClass]
public sealed class ArtifactTests
{
    /// <summary>真实PUT/GET保持中文UTF8字节，重复相同内容可以重放。</summary>
    [TestMethod]
    public async Task ImmutableRoundtripAndDifferentContentRejected()
    {
        // 当前测试只访问新建RustFS隔离桶。
        using var fixture = new PublishingFixture();
        // 固定键用于实际覆盖攻击负例。
        var key = "releases/" + Guid.NewGuid().ToString("N") + "/source.ttl";
        // 中文和换行必须逐字节保留。
        var bytes = Encoding.UTF8.GetBytes("中文原始源\n");
        // 首次真实写入并GET验证。
        var artifact = await fixture.Artifacts.PutImmutableAsync(key, bytes, "text/turtle", default);
        CollectionAssert.AreEqual(bytes, await fixture.Artifacts.ReadVerifiedAsync(artifact, default));
        Assert.AreEqual(artifact, await fixture.Artifacts.PutImmutableAsync(key, bytes, "text/turtle", default));
        await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Artifacts.PutImmutableAsync(key, Encoding.UTF8.GetBytes("changed"), "text/turtle", default));
        CollectionAssert.AreEqual(bytes, await fixture.Artifacts.ReadVerifiedAsync(artifact, default));
    }

    /// <summary>并发不同字节只有一份可以永久占据同一个对象键。</summary>
    [TestMethod]
    public async Task ConcurrentDifferentBytesCannotOverwrite()
    {
        // 两个真实签名请求争夺同一新键。
        using var fixture = new PublishingFixture();
        // 每次测试使用独立服务器生成键。
        var key = "releases/" + Guid.NewGuid().ToString("N") + "/race.ttl";
        // 捕获每个实际写入结果，不人为串行化S3请求。
        async Task<ArtifactObject?> Write(string value)
        {
            try
            {
                return await fixture.Artifacts.PutImmutableAsync(key, Encoding.UTF8.GetBytes(value), "text/turtle", default);
            }
            catch (SemanticOperationException)
            {
                return null;
            }
        }
        // 真正并发执行原子条件写。
        var results = await Task.WhenAll(Write("first"), Write("second"));
        Assert.AreEqual(1, results.Count(value => value is not null));
        await fixture.Artifacts.ReadVerifiedAsync(results.Single(value => value is not null)!, default);
    }

    /// <summary>已有对象的错hash及根本不存在对象均明确不可用。</summary>
    [TestMethod]
    public async Task WrongHashAndMissingObjectFailClosed()
    {
        // 新建测试资源，不读取历史卷。
        using var fixture = new PublishingFixture();
        // 实际对象引用用于错版验证。
        var artifact = await fixture.Artifacts.PutImmutableAsync("releases/" + Guid.NewGuid().ToString("N") + "/sample.ttl", Encoding.UTF8.GetBytes("source"), "text/turtle", default);
        await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Artifacts.ReadVerifiedAsync(artifact with { Hash = new string('0', 64) }, default));
        await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Artifacts.ReadVerifiedAsync(artifact with { ObjectKey = "releases/" + Guid.NewGuid().ToString("N") + "/missing.ttl" }, default));
    }

    /// <summary>依赖超时映射为明确503，整个实际请求受五秒预算控制。</summary>
    [TestMethod]
    public async Task SlowDependencyBecomesUnavailable()
    {
        // 真实请求在测试网络门暂停，只注入延迟而非成功响应。
        using var fixture = new PublishingFixture();
        fixture.Gate = (_, token) => Task.Delay(TimeSpan.FromSeconds(30), token);
        // 真正HttpClient与模块总预算共同取消停滞请求。
        var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => fixture.Artifacts.PutImmutableAsync("releases/" + Guid.NewGuid().ToString("N") + "/slow.ttl", Encoding.UTF8.GetBytes("source"), "text/turtle", default));
        Assert.AreEqual(503, failure.Status);
        Assert.AreEqual("artifact_store_timeout", failure.Code);
    }

    /// <summary>调用者取消保持取消语义，不伪装依赖故障或成功。</summary>
    [TestMethod]
    public async Task CallerCancellationPropagates()
    {
        // 当前fixture仍绑定实际回环资源。
        using var fixture = new PublishingFixture();
        fixture.Gate = (_, token) => Task.Delay(TimeSpan.FromSeconds(30), token);
        // 明确取消仅作用当前请求。
        using var cancellation = new CancellationTokenSource(TimeSpan.FromMilliseconds(50));
        await Assert.ThrowsAsync<OperationCanceledException>(() => fixture.Artifacts.PutImmutableAsync("releases/" + Guid.NewGuid().ToString("N") + "/cancel.ttl", Encoding.UTF8.GetBytes("source"), "text/turtle", cancellation.Token));
    }

}
