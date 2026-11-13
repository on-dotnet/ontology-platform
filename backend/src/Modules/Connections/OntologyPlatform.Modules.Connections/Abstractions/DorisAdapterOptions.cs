using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>本阶段只准入已批准本机合成目标，生产接入仍受G4阶段限制。</summary>
public sealed class DorisAdapterOptions
{
    /// <summary>仅由宿主提供的私有信任根路径，不接受HTTP覆盖。</summary>
    public required string RootCertificatePath { get; init; }

    /// <summary>在任何凭据消费和网络访问前拒绝目标或范围扩张。</summary>
    /// <param name="profile">调用方类型化配置。</param>
    /// <param name="scope">已经过主体权限检查的范围。</param>
    public static void Validate(DorisConnectionProfile profile, ResourceScope scope)
    {
        if (!profile.Tls) throw new SemanticOperationException(422, "connection_tls_untrusted");
        if (profile.FeHost != "localhost" || profile.QueryPort != 19030 || profile.Catalog != "internal"
            || profile.Database != "fixture" || profile.Username != "fixture_reader")
            throw new SemanticOperationException(403, "connection_network_forbidden");
        if (scope.OrganizationId != "org-demo" || scope.SiteIds is not ["site-a"])
            throw new SemanticOperationException(403, "connection_scope_forbidden");
    }
}
