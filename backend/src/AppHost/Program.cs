using Aspire.Hosting;
using Microsoft.Extensions.Configuration;

namespace OntologyPlatform.AppHost;

/// <summary>
/// 只编排本地开发资源与健康验证宿主的 Aspire 入口。
/// </summary>
internal static class Program
{
    /// <summary>
    /// 创建并运行当前授权内的开发资源模型。
    /// </summary>
    /// <param name="args">Aspire 标准宿主启动参数。</param>
    /// <returns>编排宿主停止后的异步任务。</returns>
    internal static async Task Main(string[] args)
    {
        // 将路径解析、秘密参数和容器生命周期交给 Aspire 标准宿主。
        var builder = DistributedApplication.CreateBuilder(args);
        if (builder.Configuration.GetValue<bool>("Wave2:Enabled"))
        {
            builder.AddWave2Infrastructure();
        }
        else
        {
            builder.AddDevelopmentInfrastructure();
        }
        await builder.Build().RunAsync();
    }
}
