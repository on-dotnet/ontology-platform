using System.Security.Claims;

namespace OntologyPlatform.Api.Security;

/// <summary>集中实施本地跳转与已验证平台声明的最小授权边界。</summary>
public static class SecurityBoundary
{
    /// <summary>只接受无歧义的站内绝对路径，拒绝编码后可绕过的地址。</summary>
    /// <param name="value">请求携带的返回路径。</param>
    /// <returns>路径安全且仅指向本站时为真。</returns>
    public static bool IsLocalReturnUrl(string? value)
    {
        if (string.IsNullOrEmpty(value))
        {
            return false;
        }

        // 同时检查解码后的路径，避免代理或浏览器重复解释转义分隔符。
        var decoded = Uri.UnescapeDataString(value);
        return decoded.StartsWith('/') && !decoded.StartsWith("//", StringComparison.Ordinal)
            && !decoded.Contains('\\') && !decoded.Any(char.IsControl);
    }

    /// <summary>读取资源必须具备批准的平台viewer或operator角色。</summary>
    /// <param name="principal">已验证的服务器身份。</param>
    /// <returns>具备资源读取权限时为真。</returns>
    public static bool CanReadResources(ClaimsPrincipal principal)
    {
        return principal.Identity?.IsAuthenticated == true
            && (principal.IsInRole("platform.viewer") || principal.IsInRole("platform.operator"));
    }

    /// <summary>组织和厂区必须同时落入身份提供者已签发的范围。</summary>
    /// <param name="principal">已验证的服务器身份。</param>
    /// <param name="organizationId">资源所属组织。</param>
    /// <param name="siteId">资源所属厂区。</param>
    /// <returns>身份同时覆盖组织及厂区时为真。</returns>
    public static bool HasScope(ClaimsPrincipal principal, string organizationId, string siteId)
    {
        return principal.Identity?.IsAuthenticated == true
            && principal.FindFirstValue("organization_id") == organizationId
            && principal.FindAll("site_ids").Any(claim => claim.Value == siteId);
    }
}
