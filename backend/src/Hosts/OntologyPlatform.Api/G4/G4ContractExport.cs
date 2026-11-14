using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;

namespace OntologyPlatform.Api.G4;

/// <summary>从实际ASP.NET路由与C#DTO导出OpenAPI，仅监听临时回环端口后退出。</summary>
public static class G4ContractExport
{
    /// <summary>生成前端唯一合同输入；不启动数据库、身份或连接业务服务。</summary>
    public static async Task WriteAsync(string path)
    {
        // 独立导出Host只有路由元数据，不提供认证或产品成功替身。
        var builder = WebApplication.CreateBuilder();
        builder.Logging.ClearProviders();
        builder.WebHost.UseUrls("http://127.0.0.1:0");
        builder.Services.AddOpenApi("g4", options => options.AddG4Contracts());
        await using var app = builder.Build();
        app.MapG4Endpoints();
        app.MapMappingEndpoints();
        app.MapOpenApi();
        await app.StartAsync();
        try
        {
            // 从真实运行的原生OpenAPI入口读取DTO与route模型。
            var address = app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single();
            using var client = new HttpClient();
            // 仅调用本进程回环元数据地址，不执行任何业务请求。
            var document = await client.GetStringAsync(address + "/openapi/g4.json");
            await File.WriteAllTextAsync(path, document + "\n");
        }
        finally
        {
            await app.StopAsync();
        }
    }
}
