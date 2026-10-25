namespace OntologyPlatform.Modules.Governance;

/// <summary>用于真实开发授权演示的明确合成资源。</summary>
public sealed class SyntheticResource
{
    /// <summary>开发资源稳定标识。</summary>
    public string Id { get; set; } = string.Empty;

    /// <summary>合成资源中文名称。</summary>
    public string Name { get; set; } = string.Empty;

    /// <summary>所属组织范围。</summary>
    public string OrganizationId { get; set; } = string.Empty;

    /// <summary>所属厂区范围。</summary>
    public string SiteId { get; set; } = string.Empty;

    /// <summary>明确标识合成开发来源。</summary>
    public string Status { get; set; } = "SyntheticDevelopment";
}
