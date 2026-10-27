using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.PublishingTests;

/// <summary>新绑定必须覆盖assessment，旧批准的字节算法必须保持。</summary>
[TestClass]
public sealed class G3BindingTests
{
    /// <summary>Semantics缺席时完全使用原G2字段顺序，不新增null。</summary>
    [TestMethod]
    public void LegacyBindingIsExactAndNewBindingIncludesSemantics()
    {
        // 最小legacy rollback合同不从新草稿取得绑定。
        var legacy = new ReleaseProposal { ProposalId = "legacy", Kind = ProposalKind.Rollback, AssetId = "asset", Scope = new ResourceScope { OrganizationId = "org", SiteIds = ["site"] }, TargetReleaseId = "release", TargetManifestHash = new string('a', 64), SubmittedBy = "author", SubmittedAtUtc = DateTimeOffset.UnixEpoch, ExpiresAtUtc = DateTimeOffset.UnixEpoch.AddHours(24) };
        // 原始匿名对象字段和声明顺序必须逐字保持。
        var json = JsonSerializer.Serialize(new { legacy.ProposalId, legacy.Kind, legacy.AssetId, legacy.Scope, legacy.DraftId, legacy.DraftRevision, legacy.Hashes, legacy.ValidationReportId, legacy.TargetReleaseId, legacy.TargetManifestHash, legacy.SubmittedBy, legacy.SubmittedAtUtc, legacy.ExpiresAtUtc });
        Assert.AreEqual(Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(json))), Binding(legacy));
        // 新发布hash必须在assessment变化时变化，不能复用原审批。
        var first = legacy with { Semantics = new PublicationSemantics { ProfileVersion = "1", ProfileHash = new string('b', 64), AssessmentId = "first", AssessmentHash = new string('c', 64) } };
        // 仅评估ID不同也必须改变批准绑定。
        var second = first with { Semantics = first.Semantics! with { AssessmentId = "second" } };
        Assert.AreNotEqual(Binding(first), Binding(second), "批准绑定遗漏assessment。");
    }

    /// <summary>只调用真实模块内部绑定实现，不在测试复制新算法。</summary>
    private static string Binding(ReleaseProposal proposal)
    {
        // 反射只用于测试内部确定性函数，生产类型仍唯一。
        var type = typeof(OntologyPlatform.Modules.Publishing.PublishingService).Assembly.GetType("OntologyPlatform.Modules.Publishing.PublishingRules")!;
        return (string)type.GetMethod("Binding", BindingFlags.Static | BindingFlags.NonPublic)!.Invoke(null, [proposal])!;
    }
}
