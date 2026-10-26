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
    /// <summary>完整正式宿主导出要求五个CAS入口声明强If-Match，并准确公开发布错误。</summary>
    [TestMethod]
    public async Task ProductionHostDocumentsStrongRevisionAndPublishingProblems()
    {
        // 本fixture自建证书和临时密钥目录，不读取现有开发runtime。
        using var fixture = new SecurityHostFixture();
        // 全部路由由正式组合根发现；只使用明确不可达的回环依赖配置。
        await using var app = fixture.Create(overrides: new Dictionary<string, string?> { ["G2:Enabled"] = "true" });
        await app.StartAsync();
        // 公开文档不需OIDC或业务写入，本测试也不宣称那些链路通过。
        using var client = fixture.CreateClient(app);
        client.DefaultRequestHeaders.Host = "localhost:15100";
        // 原始实际运行文档保留为公开协议导出供生成与审查。
        var content = await client.GetStringAsync("/openapi/v1.json");
        await File.WriteAllTextAsync(Path.Combine(Path.GetTempPath(), "g2-final-production.openapi.json"), content);
        Assert.AreEqual(content, await client.GetStringAsync("/openapi/v1.json"));
        // 逐个验证生产路径，不从静态表生成伪路由。
        var document = JsonNode.Parse(content)!;
        // 路径和方法只用于断言真实文档，不参与生成运行路由。
        foreach (var (path, method) in new[]
        {
            ("/api/v1/ontology-drafts/{id}", "put"),
            ("/api/v1/ontology-drafts/{id}/edits", "post"),
            ("/api/v1/approvals/{id}/decisions", "post"),
            ("/api/v1/release-activations", "post"),
            ("/api/v1/execution-runs/{id}/cancel", "post")
        })
        {
            // 每个CAS操作必须公开强ETag格式和缺失/冲突错误。
            var operation = document["paths"]![path]![method]!;
            // 只接受唯一必需请求头，不能把弱标签或body revision描述为等价。
            var header = operation["parameters"]!.AsArray().SingleOrDefault(value => value!["name"]!.GetValue<string>() == "If-Match");
            Assert.IsNotNull(header, path);
            Assert.IsTrue(header["required"]!.GetValue<bool>());
            Assert.AreEqual("^\"[0-9]+\"$", header["schema"]!["pattern"]!.GetValue<string>());
            // 两种前置失败都必须保留平台错误的关联字段。
            foreach (var status in new[] { 409, 428 })
            {
                Assert.AreEqual("#/components/schemas/PlatformProblem", operation["responses"]?[status.ToString()]?["content"]?["application/problem+json"]?["schema"]?["$ref"]?.GetValue<string>(), path);
            }
        }
        // 两个发布CAS端点必须描述全部实际安全和业务失败。
        foreach (var path in new[] { "/api/v1/approvals/{id}/decisions", "/api/v1/release-activations" })
        {
            // 状态码逐项取自共同guard和对应应用服务。
            foreach (var status in new[] { 400, 401, 403, 404, 409, 422, 428, 500, 503 })
            {
                Assert.AreEqual("#/components/schemas/PlatformProblem", document["paths"]![path]!["post"]!["responses"]?[status.ToString()]?["content"]?["application/problem+json"]?["schema"]?["$ref"]?.GetValue<string>(), path);
            }
        }
    }

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
