using OntologyPlatform.ServiceDefaults;

namespace OntologyPlatform.InfrastructureApi;

/// <summary>
/// 用于验证基础设施公共默认值的最小非业务 API 宿主。
/// </summary>
public static class InfrastructureApiHost
{
    /// <summary>
    /// 构建只包含开发健康路由的 Web 应用，不连接业务数据源。
    /// </summary>
    /// <param name="args">宿主环境、监听地址等标准命令行参数。</param>
    /// <returns>由调用方启动和释放的 Web 应用。</returns>
    public static WebApplication CreateApplication(string[] args)
    {
        // 使用标准配置管道，允许 Aspire 注入服务发现和 OTLP 配置。
        var builder = WebApplication.CreateBuilder(args);
        builder.AddServiceDefaults();

        // 将健康路由限定在公共服务默认值的开发环境规则内。
        var application = builder.Build();
        application.MapDefaultEndpoints();
        return application;
    }

    /// <summary>
    /// 启动非业务健康宿主并等待正常终止。
    /// </summary>
    /// <param name="args">传递给 ASP.NET Core 的启动参数。</param>
    /// <returns>宿主停止并释放后的异步任务。</returns>
    public static async Task Main(string[] args)
    {
        // 入口负责释放宿主，测试直接使用同一构建方法。
        await using var application = CreateApplication(args);
        await application.RunAsync();
    }
}
