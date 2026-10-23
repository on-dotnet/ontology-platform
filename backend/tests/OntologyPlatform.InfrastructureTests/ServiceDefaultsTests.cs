using System.Net;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Hosting;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.InfrastructureApi;
using OntologyPlatform.ServiceDefaults;

namespace OntologyPlatform.InfrastructureTests;

/// <summary>
/// 通过真实回环 HTTP 请求验证最小宿主和公共服务默认值的运行行为。
/// </summary>
[TestClass]
public sealed class ServiceDefaultsTests
{
    /// <summary>
    /// 开发宿主同时提供就绪和存活端点，且不暴露业务根路由。
    /// </summary>
    /// <returns>端点请求和宿主释放完成后的异步任务。</returns>
    [TestMethod]
    public async Task DevelopmentHostExposesOnlyHealthEndpoints()
    {
        // 使用随机回环端口隔离并发测试，不依赖 Docker 或固定机器端口。
        await using var application = InfrastructureApiHost.CreateApplication(
            ["--environment", "Development", "--urls", "http://127.0.0.1:0"]);
        await application.StartAsync();

        // 使用实际监听地址访问 Kestrel，覆盖路由映射和健康检查中间件。
        using var client = CreateClient(application);
        Assert.AreEqual(HttpStatusCode.OK, (await client.GetAsync("/health")).StatusCode);
        Assert.AreEqual(HttpStatusCode.OK, (await client.GetAsync("/alive")).StatusCode);
        Assert.AreEqual(HttpStatusCode.NotFound, (await client.GetAsync("/")).StatusCode);
    }

    /// <summary>
    /// 就绪检查失败时必须返回不可用，但不误判宿主存活状态。
    /// </summary>
    /// <returns>完成负例探测后的异步任务。</returns>
    [TestMethod]
    public async Task UnhealthyDependencyFailsReadinessWithoutFailingLiveness()
    {
        // 为负例建立真实开发宿主，注入一个确定性失败的依赖检查。
        var builder = WebApplication.CreateBuilder(new WebApplicationOptions
        {
            EnvironmentName = Environments.Development,
            Args = ["--urls", "http://127.0.0.1:0"]
        });
        builder.AddServiceDefaults();
        builder.Services.AddHealthChecks().AddCheck(
            "unavailable-dependency", () => HealthCheckResult.Unhealthy("测试依赖不可用"));

        // 启动实际 HTTP 管道，验证 live 标签会排除依赖检查。
        await using var application = builder.Build();
        application.MapDefaultEndpoints();
        await application.StartAsync();

        // 分别请求两个探针，防止将依赖故障扩散成进程存活故障。
        using var client = CreateClient(application);
        Assert.AreEqual(HttpStatusCode.ServiceUnavailable, (await client.GetAsync("/health")).StatusCode);
        Assert.AreEqual(HttpStatusCode.OK, (await client.GetAsync("/alive")).StatusCode);
    }

    /// <summary>
    /// 生产环境默认不公开开发探针，避免无意扩大宿主访问面。
    /// </summary>
    /// <returns>完成生产环境路由探测后的异步任务。</returns>
    [TestMethod]
    public async Task ProductionHostDoesNotExposeDevelopmentHealthEndpoints()
    {
        // 显式指定生产环境以验证开发探针的环境边界。
        await using var application = InfrastructureApiHost.CreateApplication(
            ["--environment", "Production", "--urls", "http://127.0.0.1:0"]);
        await application.StartAsync();

        // 使用真实请求证明路由不存在，而不是只检查配置对象。
        using var client = CreateClient(application);
        Assert.AreEqual(HttpStatusCode.NotFound, (await client.GetAsync("/health")).StatusCode);
        Assert.AreEqual(HttpStatusCode.NotFound, (await client.GetAsync("/alive")).StatusCode);
    }

    /// <summary>
    /// 默认 HTTP 客户端能够把逻辑服务名解析到配置中的真实端点。
    /// </summary>
    /// <returns>服务发现请求和宿主释放完成后的异步任务。</returns>
    [TestMethod]
    public async Task DefaultHttpClientResolvesConfiguredServiceEndpoint()
    {
        // 下游仍为真实健康宿主，使测试不依赖模拟处理器。
        await using var application = InfrastructureApiHost.CreateApplication(
            ["--environment", "Development", "--urls", "http://127.0.0.1:0"]);
        await application.StartAsync();

        // 读取 Kestrel 分配的地址，作为配置式服务发现的候选端点。
        var address = GetAddress(application);
        // 客户端宿主单独配置逻辑名称，不注入具体 HttpMessageHandler。
        var builder = Host.CreateApplicationBuilder();
        builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["services:probe:http:0"] = address
        });
        builder.AddServiceDefaults();

        // 构建真实服务容器以覆盖默认发现和弹性处理器的注册。
        using var host = builder.Build();
        // 从工厂创建客户端，验证默认管道而非直接访问物理地址。
        using var client = host.Services.GetRequiredService<IHttpClientFactory>().CreateClient();
        // 请求逻辑服务名，成功响应证明地址解析进入实际 HTTP 管道。
        using var response = await client.GetAsync("http://probe/alive");
        Assert.AreEqual(HttpStatusCode.OK, response.StatusCode);
    }

    /// <summary>
    /// 创建指向已启动宿主的回环客户端。
    /// </summary>
    /// <param name="application">已经完成启动的测试宿主。</param>
    /// <returns>由调用方释放的 HTTP 客户端。</returns>
    private static HttpClient CreateClient(WebApplication application)
    {
        return new HttpClient
        {
            BaseAddress = new Uri(GetAddress(application)),
            Timeout = TimeSpan.FromSeconds(10)
        };
    }

    /// <summary>
    /// 读取 Kestrel 动态绑定的唯一监听地址。
    /// </summary>
    /// <param name="application">已启动且只绑定一个回环地址的宿主。</param>
    /// <returns>可供测试客户端访问的绝对地址。</returns>
    private static string GetAddress(WebApplication application)
    {
        return application.Services.GetRequiredService<IServer>()
            .Features.Get<IServerAddressesFeature>()!.Addresses.Single();
    }
}
