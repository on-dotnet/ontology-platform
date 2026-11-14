using System.Security.Claims;
using System.Security.Cryptography;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.DataProtection;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Api.G4;

/// <summary>只解释治理已锁定的服务器票据，不再另开数据库连接。</summary>
public sealed class MappingSessionAuthority : IMappingSessionAuthority
{
    /// <summary>与服务器票据存储同purpose的保护器。</summary>
    private readonly IDataProtector protector;

    /// <summary>复用宿主证书keyring，不读取或返回令牌。</summary>
    public MappingSessionAuthority(IDataProtectionProvider protection)
    {
        protector = protection.CreateProtector("OntologyPlatform.Governance.ServerTicket.v1");
    }

    /// <summary>核验真实主体、组织、全部厂区、角色和票据期限，失败关闭。</summary>
    public bool Matches(byte[] protectedTicket, ActorContext expected, DateTimeOffset now)
    {
        try
        {
            // 票据从治理已锁定行传入，不接受HTTP正文中的票据或声明。
            var ticket = TicketSerializer.Default.Deserialize(protector.Unprotect(protectedTicket));
            // 与HTTP Actor比较完整安全声明集合，禁止换会话绕过主体检查。
            var principal = ticket?.Principal;
            return principal?.Identity?.IsAuthenticated == true && ticket!.Properties.ExpiresUtc > now
                && principal.FindFirstValue("sub") == expected.SubjectId
                && principal.FindFirstValue("organization_id") == expected.OrganizationId
                && principal.FindAll("site_ids").Select(value => value.Value).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal)
                    .SequenceEqual(expected.SiteIds.Order(StringComparer.Ordinal))
                && new[] { "platform.viewer", "platform.operator", "platform.auditor" }.Where(principal.IsInRole).Order(StringComparer.Ordinal)
                    .SequenceEqual(expected.Roles.Order(StringComparer.Ordinal));
        }
        catch (Exception error) when (error is CryptographicException or FormatException or InvalidOperationException)
        {
            return false;
        }
    }
}
