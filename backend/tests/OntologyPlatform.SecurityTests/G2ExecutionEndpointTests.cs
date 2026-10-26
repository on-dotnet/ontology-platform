using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Builder;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using OntologyPlatform.Api.Contracts;
using OntologyPlatform.Api.G2;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Agents;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SecurityTests;

/// <summary>从实际Run端点生成真实Kestrel文档，避免夹具自行声明响应掩盖生产元数据缺失。</summary>
[TestClass]
public sealed class G2ExecutionEndpointTests
{
    /// <summary>实际五个Run操作必须公开精确响应、原生事件流及发送响应头前的错误合同。</summary>
    /// <returns>真实公开OpenAPI文档的HTTP验证任务。</returns>
    [TestMethod]
    public async Task ActualRunRoutesDescribeResponsesAndNativeEventStream()
    {
        // 只启动公开协议宿主，不访问OIDC、数据库或任何私有运行配置。
        var builder = WebApplication.CreateBuilder(new WebApplicationOptions { ApplicationName = typeof(G2ExecutionEndpointTests).Assembly.GetName().Name });
        builder.Logging.ClearProviders();
        builder.Services.AddOpenApi(options => options.AddPlatformContracts());
        builder.Services.AddScoped<ExecutionRunService>();
        builder.Services.AddScoped<IOntologyService, OntologyService>();
        // 所有被测路由均调用生产映射函数，不在测试中补Produces。
        await using var app = builder.Build();
        app.MapExecutionEndpoints();
        app.MapOntologyEndpoints();
        app.MapOpenApi();
        app.Urls.Add("http://127.0.0.1:0");
        await app.StartAsync();
        // Kestrel动态端口隔离并发测试。
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
        // 原始文档只含公共协议，保存到临时文件供失败诊断。
        var content = await client.GetStringAsync("/openapi/v1.json");
        await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "g2-actual-execution-openapi.json"), content);
        // 检查实际路由的响应引用，而不只检查components里存在DTO。
        var document = JsonNode.Parse(content)!;
        // 每个操作的成功与错误集合来自实际guard和Run服务。
        var cases = new[]
        {
            (Path: "/api/v1/execution-runs", Method: "get", Schema: "ExecutionRun", Array: true, Errors: new[] { 401, 403, 503, 500 }),
            (Path: "/api/v1/execution-runs", Method: "post", Schema: "ExecutionRun", Array: false, Errors: new[] { 400, 401, 403, 409, 422, 503, 500 }),
            (Path: "/api/v1/execution-runs/{id}", Method: "get", Schema: "ExecutionRun", Array: false, Errors: new[] { 401, 403, 404, 503, 500 }),
            (Path: "/api/v1/execution-runs/{id}/cancel", Method: "post", Schema: "ExecutionRun", Array: false, Errors: new[] { 400, 401, 403, 404, 409, 428, 503, 500 }),
            (Path: "/api/v1/execution-runs/{id}/events", Method: "get", Schema: "ExecutionEvent", Array: false, Errors: new[] { 400, 401, 403, 404, 409, 503, 500 })
        };
        // 逐项验证实际路由，防止组件存在但响应未关联的回归。
        foreach (var item in cases)
        {
            // SSE的schema描述每条data中的事件封套，媒体类型保留原生协议。
            var operation = document["paths"]![item.Path]![item.Method]!;
            // 成功响应必须存在实际媒体类型及唯一DTO引用。
            var media = item.Schema == "ExecutionEvent" ? "text/event-stream" : "application/json";
            // 丢失元数据时这里明确失败，而非由null访问造成测试错误。
            var success = operation["responses"]?["200"]?["content"]?[media]?["schema"];
            Assert.IsNotNull(success, $"{item.Method} {item.Path} 缺少{media}响应Schema。");
            if (item.Array)
            {
                Assert.AreEqual("array", success["type"]!.GetValue<string>());
                success = success["items"]!;
            }
            Assert.AreEqual("#/components/schemas/" + item.Schema, success["$ref"]!.GetValue<string>());
            // 每个已声明错误均须保留标准Problem的完整字段。
            foreach (var status in item.Errors)
            {
                Assert.AreEqual("#/components/schemas/PlatformProblem", operation["responses"]?[status.ToString()]?["content"]?["application/problem+json"]?["schema"]?["$ref"]?.GetValue<string>(), $"{item.Method} {item.Path} 缺少{status}标准错误。");
            }
            Assert.IsTrue(operation["security"]!.AsArray().Any(value => value!["session"] is not null));
            if (item.Method == "post")
            {
                Assert.IsTrue(operation["parameters"]!.AsArray().Any(value => value!["name"]!.GetValue<string>() == "X-CSRF-TOKEN" && value["required"]!.GetValue<bool>()));
            }
        }
        Assert.AreEqual(9, document["components"]!["schemas"]!["ExecutionEvent"]!["oneOf"]!.AsArray().Count);
    }
}
