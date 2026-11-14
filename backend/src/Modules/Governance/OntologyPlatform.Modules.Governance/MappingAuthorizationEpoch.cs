namespace OntologyPlatform.Modules.Governance;

/// <summary>组织级单调授权版本；所有厂区集合共享此锁域。</summary>
public sealed class MappingAuthorizationEpoch
{
    /// <summary>唯一组织标识，也是行锁主键。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>任何授权变化递增，旧审批保守失效。</summary>
    public long Revision { get; set; } = 1;

}
