using System.Security.Claims;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Api.Security;

namespace OntologyPlatform.SecurityTests;

/// <summary>验证平台自己的重定向与厂区授权边界，防止外部输入扩大权限。</summary>
[TestClass]
public sealed class SecurityBoundaryTests
{
    /// <summary>外部、协议相对和反斜线地址必须拒绝，普通本地路径可保留。</summary>
    [TestMethod]
    public void ReturnAddressRejectsExternalAndAmbiguousPaths()
    {
        Assert.IsTrue(SecurityBoundary.IsLocalReturnUrl("/resources?siteId=site-a"));
        Assert.IsFalse(SecurityBoundary.IsLocalReturnUrl("//evil.invalid"));
        Assert.IsFalse(SecurityBoundary.IsLocalReturnUrl("/\\evil.invalid"));
        Assert.IsFalse(SecurityBoundary.IsLocalReturnUrl("https://evil.invalid"));
        Assert.IsFalse(SecurityBoundary.IsLocalReturnUrl("/\r\nx"));
        Assert.IsFalse(SecurityBoundary.IsLocalReturnUrl("/%2f%2fevil.invalid"));
    }

    /// <summary>身份声明只能授权同一组织和已声明厂区，角色也必须显式认可。</summary>
    [TestMethod]
    public void SiteScopeNeverAcceptsAnotherOrganizationOrSite()
    {
        // 构造已经由身份提供者验证的最小声明，资源范围独立于请求头。
        var principal = new ClaimsPrincipal(new ClaimsIdentity(new[]
        {
            new Claim("sub", "synthetic-viewer"),
            new Claim("organization_id", "org-demo"),
            new Claim("site_ids", "site-a"),
            new Claim(ClaimTypes.Role, "platform.viewer")
        }, "test"));
        Assert.IsTrue(SecurityBoundary.CanReadResources(principal));
        Assert.IsTrue(SecurityBoundary.HasScope(principal, "org-demo", "site-a"));
        Assert.IsFalse(SecurityBoundary.HasScope(principal, "org-demo", "site-b"));
        Assert.IsFalse(SecurityBoundary.HasScope(principal, "org-other", "site-a"));
        Assert.IsFalse(SecurityBoundary.CanReadResources(new ClaimsPrincipal(new ClaimsIdentity())));
    }
}
