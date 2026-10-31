using Microsoft.AspNetCore.Builder;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using OntologyPlatform.Api.G2;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SecurityTests;

/// <summary>在首个真实HTTP请求前使用正式组合根解析M5服务，遗漏注册必须失败。</summary>
[TestClass]
public sealed class G3M5CompositionTests
{
    /// <summary>真实服务与运行时解析为同一模块实例，不连接外部服务。</summary>
    [TestMethod]
    public void ActualCompositionResolvesBothExpressionContracts()
    {
        // 合成启动配置只用于构造，不包含实际凭证或数据库连接。
        var builder = Builder();
        // 作用域与实际请求相同，构造期间不能触发PG、Jena或对象存储请求。
        using var provider = builder.Services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });
        // M5用例继续复用现有模块，不能注册替代伪服务。
        using var scope = provider.CreateScope();
        Assert.AreSame(scope.ServiceProvider.GetRequiredService<OntologyService>(), scope.ServiceProvider.GetRequiredService<IG3ExpressionService>());
        Assert.AreSame(scope.ServiceProvider.GetRequiredService<JenaSemanticRuntime>(), scope.ServiceProvider.GetRequiredService<IG3ExpressionRuntime>());
    }

    /// <summary>删除任何一个实际注册都在短组合检查失败，不等容器或业务请求。</summary>
    [TestMethod]
    public void MissingExpressionRegistrationFailsBeforeAnyRequest()
    {
        // 两项接口逐项删除并验证实际容器的失败，不依赖静态登记字符串。
        foreach (var missing in new[] { typeof(IG3ExpressionService), typeof(IG3ExpressionRuntime) })
        {
            // 每次使用完整独立组合，避免另一个负例污染注册状态。
            var builder = Builder();
            builder.Services.RemoveAll(missing);
            // 不启动Web或外部服务，真实容器解析必须明确拒绝缺失合同。
            using var provider = builder.Services.BuildServiceProvider();
            using var scope = provider.CreateScope();
            Assert.ThrowsExactly<InvalidOperationException>(() => scope.ServiceProvider.GetRequiredService(missing));
        }
    }

    /// <summary>按正式宿主顺序注册治理工厂及G2模块，仅使用明确Synthetic输入。</summary>
    /// <returns>尚未启动的应用构造器。</returns>
    private static WebApplicationBuilder Builder()
    {
        // 不监听端口、不创建真实连接；所有外部地址固定本机回环。
        var builder = WebApplication.CreateBuilder();
        builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["G2:Enabled"] = "true",
            ["ConnectionStrings:governance"] = "Host=127.0.0.1;Database=synthetic_composition",
            ["Semantics:ValidationOrigin"] = "http://127.0.0.1:3030/validation",
            ["Semantics:PublishedOrigin"] = "http://127.0.0.1:3030/ontology",
            ["Publishing:S3Endpoint"] = "http://127.0.0.1:9000/",
            ["Publishing:AccessKey"] = "synthetic-access",
            ["Publishing:SecretKey"] = "synthetic-signing-fixture",
            ["Publishing:Bucket"] = "synthetic-composition"
        });
        builder.Services.AddSingleton(new PlatformSecurityOptions { PublicOrigin = "http://localhost:15100" });
        builder.Services.AddDbContextFactory<GovernanceDbContext>(options => options.UseNpgsql(builder.Configuration.GetConnectionString("governance")));
        builder.AddG2Modules();
        return builder;
    }
}
