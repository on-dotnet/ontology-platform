using OntologyPlatform.Api.G2;

namespace OntologyPlatform.Api;

/// <summary>正式平台API宿主的进程入口。</summary>
public static class Program
{
    /// <summary>验证安全配置、执行显式开发初始化并运行宿主。</summary>
    /// <param name="args">宿主配置参数，秘密应由运行时环境注入。</param>
    /// <returns>服务停止后完成的任务。</returns>
    public static async Task Main(string[] args)
    {
        // 宿主独立于开发InfraAPI，正式提供身份、资源和探针。
        await using var app = PlatformApiHost.CreateApplication(args);
        await PlatformApiHost.InitializeDevelopmentAsync(app);
        await G2Composition.InitializeG2DevelopmentAsync(app);
        await app.RunAsync();
    }
}
