using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>本机开发Oracle的服务端固定信任配置，不能由请求覆盖。</summary>
public sealed class OracleAdapterOptions
{
    /// <summary>只含信任CA的任务私有文件wallet目录，不接受URL或SEPS。</summary>
    public required string WalletDirectory { get; init; }

    /// <summary>用于独立主机名/有效期验证的任务合成CA证书路径。</summary>
    public required string RootCertificatePath { get; init; }

    /// <summary>解密或触源前核对唯一PDB、账号、owner顺序与组织厂区。</summary>
    /// <param name="profile">公开请求配置。</param>
    /// <param name="scope">已经过主体授权检查的范围。</param>
    public static void Validate(OracleConnectionProfile profile, ResourceScope scope)
    {
        if (!profile.Tls) throw new SemanticOperationException(422, "connection_tls_untrusted");
        if (profile.Host != "oracle-source" || profile.Port != 2484 || profile.ServiceName != "FREEPDB1"
            || profile.Username != "FIXTURE_READER" || profile.AllowedOwners is not ["PRODUCTION", "CaseOwner"])
            throw new SemanticOperationException(403, "connection_network_forbidden");
        if (scope.OrganizationId != "org-demo" || scope.SiteIds is not ["site-a"])
            throw new SemanticOperationException(403, "connection_scope_forbidden");
    }
}
