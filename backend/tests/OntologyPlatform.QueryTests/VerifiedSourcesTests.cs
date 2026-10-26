using System.Security.Cryptography;
using System.Text;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.SemanticQuery;

namespace OntologyPlatform.QueryTests;

/// <summary>真实S3源对象与已发布清单槽位、hash及严格UTF8绑定的边界验证。</summary>
[TestClass]
public sealed class VerifiedSourcesTests
{
    /// <summary>真实发布的四源和可选词汇缺席三源均无损恢复。</summary>
    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public async Task RestoresActualPublishedSources(bool vocabulary)
    {
        // 正式发布路径包含真实RIOT、SHACL、PG、S3及图部署。
        using var fixture = new QueryFixture();
        // 可选源只控制是否正式提交，不伪造任何发布事实。
        var expected = fixture.Sources() with { VocabularyTurtle = vocabulary ? fixture.Sources().VocabularyTurtle : null };
        // 真实目录返回授权清单。
        var release = await fixture.PublishAsync(expected);
        Assert.AreEqual(expected, await new VerifiedReleaseSources(fixture.Artifacts).ReadAsync(release.Manifest, default));
    }

    /// <summary>即使对象自报hash有效，交换槽位或快照与源hash错配仍失败关闭。</summary>
    [TestMethod]
    [DataRow("slots")]
    [DataRow("snapshot")]
    [DataRow("bundle")]
    [DataRow("key")]
    public async Task RejectsManifestSourceBindingMismatch(string mutation)
    {
        // 原始对象均来自真实正式发布，变异只针对调用边界的清单参数。
        using var fixture = new QueryFixture();
        // 所有正常前提先真实完成。
        var release = await fixture.PublishAsync();
        // 克隆数组避免修改此前发布事实对象。
        var manifest = release.Manifest with { ArtifactObjects = [.. release.Manifest.ArtifactObjects] };
        switch (mutation)
        {
            case "slots": (manifest.ArtifactObjects[0], manifest.ArtifactObjects[1]) = (manifest.ArtifactObjects[1], manifest.ArtifactObjects[0]); break;
            case "snapshot": manifest = manifest with { Snapshot = manifest.Snapshot with { DataHash = new string('0', 64) } }; break;
            case "bundle": manifest = manifest with { Hashes = manifest.Hashes with { BundleHash = new string('0', 64) } }; break;
            case "key": manifest.ArtifactObjects[0] = manifest.ArtifactObjects[0] with { ObjectKey = "unbound-source.ttl" }; break;
        }
        // 用真实对象适配器，绑定错误不应靠可解析Turtle掩盖。
        var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => new VerifiedReleaseSources(fixture.Artifacts).ReadAsync(manifest, default));
        Assert.AreEqual(503, failure.Status);
    }

    /// <summary>真实S3保存的hash一致非法UTF8必须拒绝，不能替换字符后交解析器。</summary>
    [TestMethod]
    public async Task RejectsHashValidInvalidUtf8()
    {
        // 本测试只验证源恢复边界，不宣称畸形源是合法正式发布。
        using var fixture = new QueryFixture();
        // 先取得四源与正式槽位命名所需的真实授权上下文。
        var release = await fixture.PublishAsync();
        // 非法双字节UTF8，实际写入本轮临时S3。
        byte[] bytes = [0xc3, 0x28];
        // 自报hash与实际bytes确实相同，隔离严格解码检查。
        var hash = Convert.ToHexStringLower(SHA256.HashData(bytes));
        // 新不可变对象不覆盖此前发布内容。
        var artifact = await fixture.Artifacts.PutImmutableAsync($"releases/{release.Manifest.ReleaseId}/source-3-{hash}.ttl", bytes, "text/turtle", default);
        // 仅构造组件负例输入；不写PG清单、不激活不合法发布。
        var hashes = release.Manifest.Hashes with { DataHash = hash };
        hashes = hashes with { BundleHash = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join('\n', hashes.OntologyHash, hashes.ShapesHash, hashes.VocabularyHash ?? "absent", hashes.DataHash)))) };
        // 其他绑定均合法，使错误只能来自实际字节解码。
        var manifest = release.Manifest with { Hashes = hashes, Snapshot = release.Manifest.Snapshot with { DataHash = hash }, ArtifactObjects = [.. release.Manifest.ArtifactObjects[..3], artifact] };
        // 真实GET验证hash之后仍必须严格解码失败。
        var failure = await Assert.ThrowsAsync<SemanticOperationException>(() => new VerifiedReleaseSources(fixture.Artifacts).ReadAsync(manifest, default));
        Assert.AreEqual(503, failure.Status);
        Assert.AreEqual("published_source_encoding_invalid", failure.Code);
    }
}
