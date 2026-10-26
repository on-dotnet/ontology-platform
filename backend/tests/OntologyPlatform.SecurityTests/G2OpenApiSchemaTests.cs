using System.Net.Http.Json;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using OntologyPlatform.Api.Contracts;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.SecurityTests;

/// <summary>通过真实Kestrel导出验证强类型业务协议的判别联合，不能用静态文件代替运行文档。</summary>
[TestClass]
public sealed class G2OpenApiSchemaTests
{
    /// <summary>实际文档必须拒绝数据混合分支和事件版本漂移，并公开写入防伪要求。</summary>
    /// <returns>真实HTTP导出检查任务。</returns>
    [TestMethod]
    public async Task RuntimeSchemaPreservesWireUnionsAndWriteHeaders()
    {
        // 隔离宿主仅验证原生API文档转换，不伪装OIDC或产品服务验收。
        var builder = WebApplication.CreateBuilder(new WebApplicationOptions { ApplicationName = typeof(G2OpenApiSchemaTests).Assembly.GetName().Name });
        builder.Logging.ClearProviders();
        builder.Services.AddOpenApi(options => options.AddPlatformContracts());
        // 使用真实端点参数和返回类型触发框架Schema生成。
        await using var app = builder.Build();
        app.MapPost("/api/v1/ontology-drafts", (CreateDraftRequest request) => Results.Ok(request)).Produces<SemanticDatum>();
        app.MapGet("/api/v1/execution-runs/{id}/events", (string id) => Results.Ok(id)).Produces<ExecutionEvent>();
        app.MapOpenApi();
        app.Urls.Add("http://127.0.0.1:0");
        await app.StartAsync();
        // 端口由Kestrel分配，HTTP正文仅为公开协议。
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
        // 真正取回框架输出，禁止直接把bootstrap作为产品结果断言。
        using var response = await client.GetAsync("/openapi/v1.json");
        // 本夹具仅含公开DTO，将原始文档保留到临时目录便于比对实际导出。
        var content = await response.Content.ReadAsStringAsync();
        await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "g2-openapi-schema-fixture.json"), content);
        Assert.AreEqual(200, (int)response.StatusCode);
        // 显式解析公开文档，错误不能被客户端泛型包装掩盖。
        var document = JsonNode.Parse(content) ?? throw new AssertFailedException("OpenAPI文档缺失。");
        // 两类联合和固定literal是跨REST/MCP/SSE消费者的共同安全边界。
        var schemas = document["components"]!["schemas"]!;
        Assert.AreEqual(3, schemas["SemanticDatum"]!["oneOf"]!.AsArray().Count);
        Assert.AreEqual(9, schemas["ExecutionEvent"]!["oneOf"]!.AsArray().Count);
        Assert.AreEqual(1, schemas["ExecutionEvent"]!["oneOf"]![0]!["properties"]!["schemaVersion"]!["enum"]![0]!.GetValue<int>());
        Assert.AreEqual("COMPLETED", schemas["RunCompletedPayload"]!["properties"]!["status"]!["const"]!.GetValue<string>());
        // 写入凭据不只声明会话，还必须准确列出服务器真正读取的防伪头。
        var operation = document["paths"]!["/api/v1/ontology-drafts"]!["post"]!;
        Assert.IsTrue(operation["parameters"]!.AsArray().Any(value => value!["name"]!.GetValue<string>() == "X-CSRF-TOKEN" && value["required"]!.GetValue<bool>()));
    }
}
