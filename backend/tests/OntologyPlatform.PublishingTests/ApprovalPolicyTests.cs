using OntologyPlatform.Modules.Publishing.Domain;

namespace OntologyPlatform.PublishingTests;

/// <summary>验证异人、完整角色和到期瞬间的确定性边界。</summary>
[TestClass]
public sealed class ApprovalPolicyTests
{
    /// <summary>双角色也不能审核自身提交的提案。</summary>
    [TestMethod]
    public void SelfApprovalDenied() => Assert.IsFalse(PublishingPolicy.CanApprove("author", ["platform.auditor", "platform.operator"], "author", DateTimeOffset.UnixEpoch, DateTimeOffset.UnixEpoch.AddHours(1)));

    /// <summary>短角色名称不能替代已验证的完整角色。</summary>
    [TestMethod]
    public void ShortRoleDenied() => Assert.IsFalse(PublishingPolicy.CanApprove("reviewer", ["auditor"], "author", DateTimeOffset.UnixEpoch, DateTimeOffset.UnixEpoch.AddHours(1)));

    /// <summary>到期瞬间即失效，不能多获得一个时钟刻度。</summary>
    [TestMethod]
    public void ExactExpiryDenied() => Assert.IsFalse(PublishingPolicy.CanApprove("reviewer", ["platform.auditor"], "author", DateTimeOffset.UnixEpoch, DateTimeOffset.UnixEpoch));

    /// <summary>独立完整角色在期限内具备审核资格。</summary>
    [TestMethod]
    public void IndependentAuditorAllowed() => Assert.IsTrue(PublishingPolicy.CanApprove("reviewer", ["platform.auditor"], "author", DateTimeOffset.UnixEpoch, DateTimeOffset.UnixEpoch.AddHours(1)));
}
