using System.Net;
using Npgsql;

namespace OntologyPlatform.Api.Security;

/// <summary>保存正式安全入口所需的显式配置并实施失败关闭验证。</summary>
public sealed class PlatformSecurityOptions
{
    /// <summary>OIDC可信签发者的绝对地址。</summary>
    public string Authority { get; set; } = string.Empty;

    /// <summary>本轮专用OIDC客户端标识。</summary>
    public string ClientId { get; set; } = string.Empty;

    /// <summary>运行时注入的机密客户端秘密。</summary>
    public string ClientSecret { get; set; } = string.Empty;

    /// <summary>经验证的外部入口，不采用请求Host推导。</summary>
    public string PublicOrigin { get; set; } = string.Empty;

    /// <summary>两个实例共享的受限持久密钥目录。</summary>
    public string KeyRingPath { get; set; } = string.Empty;

    /// <summary>用于加密共享密钥环的外置PFX路径。</summary>
    public string CertificatePath { get; set; } = string.Empty;

    /// <summary>运行时注入的证书密码，不进入日志。</summary>
    public string CertificatePassword { get; set; } = string.Empty;

    /// <summary>内部编排健康探针凭据。</summary>
    public string HealthKey { get; set; } = string.Empty;

    /// <summary>明确可信的单跳代理IP，空集合默认不信任转发头。</summary>
    public string[] TrustedProxies { get; set; } = [];

    /// <summary>在启动前验证可信入口、秘密和持久加密配置，不记录配置值。</summary>
    /// <param name="development">是否允许仅回环的开发HTTP。</param>
    /// <param name="connection">模块数据库运行时连接。</param>
    /// <exception cref="InvalidOperationException">配置不完整或跨越安全边界。</exception>
    public void Validate(bool development, string? connection)
    {
        if (!IsSecureEndpoint(Authority, development) || !IsSecureEndpoint(PublicOrigin, development)
            || !Uri.TryCreate(PublicOrigin, UriKind.Absolute, out var origin)
            || origin.AbsolutePath != "/" || !string.IsNullOrEmpty(origin.Query)
            || !string.IsNullOrEmpty(origin.Fragment)
            || string.IsNullOrWhiteSpace(ClientId) || ClientId.Any(char.IsControl)
            || string.IsNullOrWhiteSpace(ClientSecret) || HealthKey.Length < 24
            || string.IsNullOrWhiteSpace(CertificatePassword)
            || !Path.IsPathFullyQualified(KeyRingPath) || !Directory.Exists(KeyRingPath)
            || !Path.IsPathFullyQualified(CertificatePath) || !File.Exists(CertificatePath)
            || TrustedProxies.Any(value => !IPAddress.TryParse(value, out _)))
        {
            throw new InvalidOperationException("平台安全配置无效；需要显式可信入口及共享加密持久化配置。");
        }

        try
        {
            // 运行时不接受缺密码或多主机歧义连接；绝不将连接字符串写入错误。
            var database = new NpgsqlConnectionStringBuilder(connection ?? string.Empty);
            if (string.IsNullOrWhiteSpace(database.Host) || string.IsNullOrWhiteSpace(database.Database)
                || string.IsNullOrWhiteSpace(database.Username) || string.IsNullOrWhiteSpace(database.Password))
            {
                throw new ArgumentException("模块连接缺少必需字段。");
            }
        }
        catch (ArgumentException)
        {
            throw new InvalidOperationException("Governance运行时连接配置无效。");
        }
    }

    /// <summary>只允许HTTPS或开发回环HTTP，并排除地址内凭据与片段。</summary>
    /// <param name="value">待验证的OIDC或平台入口。</param>
    /// <param name="development">开发环境标志。</param>
    /// <returns>满足传输及地址约束时为真。</returns>
    private static bool IsSecureEndpoint(string value, bool development)
    {
        return Uri.TryCreate(value, UriKind.Absolute, out var address)
            && string.IsNullOrEmpty(address.UserInfo) && string.IsNullOrEmpty(address.Fragment)
            && string.IsNullOrEmpty(address.Query)
            && (address.Scheme == Uri.UriSchemeHttps
                || (development && address.Scheme == Uri.UriSchemeHttp && address.IsLoopback));
    }
}
