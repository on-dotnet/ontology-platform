using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using OntologyPlatform.Api.G2;
using OntologyPlatform.Api.Security;

namespace OntologyPlatform.SecurityTests;

/// <summary>检验正式宿主组合的可信安全配置不会在模块适配层丢失。</summary>
[TestClass]
public sealed class G2CompositionTests
{
    /// <summary>共同guard必须取得宿主已经验证的同一个PublicOrigin，而非未绑定的默认空配置。</summary>
    [TestMethod]
    public void G2GuardUsesValidatedSecurityConfiguration()
    {
        // 不启动数据库或OIDC，此项仅复现实际组合根的选项注册缺口。
        var builder = WebApplication.CreateBuilder();
        builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?> { ["G2:Enabled"] = "true" });
        // 生产宿主先验证再注册此对象，本夹具只给无秘密入口值。
        var validated = new PlatformSecurityOptions { PublicOrigin = "http://localhost:15100" };
        builder.Services.AddSingleton(validated);
        builder.AddG2Modules();
        // 与正式guard解析相同的IOptions服务，不能仅比较原单例本身。
        using var provider = builder.Services.BuildServiceProvider();
        Assert.AreSame(validated, provider.GetRequiredService<IOptions<PlatformSecurityOptions>>().Value);
    }
}
