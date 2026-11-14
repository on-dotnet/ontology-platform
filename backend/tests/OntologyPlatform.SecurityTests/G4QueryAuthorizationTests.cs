using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;

namespace OntologyPlatform.SecurityTests;

/// <summary>新查询许可必须显式授予，管理或映射验证权限不能替代。</summary>
[TestClass]
public sealed class G4QueryAuthorizationTests
{
    /// <summary>业务只读角色仍必须拥有同连接同字段的单条完整grant。</summary>
    [TestMethod]
    public void ExplicitQueryGrantCoversOnlyExactSourceProjection()
    {
        // 固定测试时钟排除真实时钟边界对权限断言的干扰。
        var now = new DateTimeOffset(2026, 11, 14, 0, 0, 0, TimeSpan.Zero);
        // 角色只是前置条件，不包含任何默认query授权。
        var actor = new ActorContext { SubjectId = "a", OrganizationId = "org", SiteIds = ["site"], Roles = ["platform.viewer"], TraceId = "trace" };
        // 查询证明只声明当前有界投影，不包含客户端身份扩张。
        var proof = new MappingAuthorizationProof
        {
            Actor = actor, Scope = new ResourceScope { OrganizationId = "org", SiteIds = ["site"] },
            SessionReference = new string('a', 64), Permission = "data.query.execute", ConnectionId = "connection",
            ObjectRefs = ["table"], FieldRefs = ["field"], AuthorizationEpoch = 1, ExpiresAtUtc = now.AddSeconds(5)
        };
        // 一条完整grant覆盖本请求全部字段。
        var grant = new MappingAuthorizationGrant
        {
            Id = "grant", SubjectId = "a", OrganizationId = "org", Permission = "data.query.execute",
            ConnectionId = "connection", SiteIds = ["site"], ObjectRefs = ["table"], FieldRefs = ["field"], ExpiresAtUtc = now.AddMinutes(1)
        };
        Assert.IsTrue(QueryAuthorizationParticipant.RoleAllows(actor, proof.Permission));
        Assert.IsTrue(QueryAuthorizationParticipant.Covers(grant, proof, now));
        grant.Permission = "mapping.source.validate";
        Assert.IsFalse(QueryAuthorizationParticipant.Covers(grant, proof, now));
        grant.Permission = "data.query.execute";
        grant.FieldRefs = [];
        Assert.IsFalse(QueryAuthorizationParticipant.Covers(grant, proof, now));
        grant.FieldRefs = ["field"];
        grant.RevokedAtUtc = now;
        Assert.IsFalse(QueryAuthorizationParticipant.Covers(grant, proof, now));
        Assert.IsFalse(QueryAuthorizationParticipant.RoleAllows(actor with { Roles = ["viewer"] }, proof.Permission));
    }
}
