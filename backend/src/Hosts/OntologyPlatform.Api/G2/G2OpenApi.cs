using Microsoft.AspNetCore.OpenApi;
using Microsoft.OpenApi;

namespace OntologyPlatform.Api.G2;

/// <summary>将唯一模型生成的严格Schema关联到真实发现的端点，不从静态文档伪造路由。</summary>
public static class G2OpenApi
{
    /// <summary>修正原生生成器无法推断的判别及回调约束，同时公开实际写入防伪头。</summary>
    /// <param name="options">当前运行文档生成配置。</param>
    /// <returns>同一选项供组合根继续注册。</returns>
    public static OpenApiOptions AddG2Contracts(this OpenApiOptions options)
    {
        options.AddDocumentTransformer(async (document, _, cancellationToken) =>
        {
            if (!document.Paths.Keys.Any(path => path.StartsWith("/api/v1/ontology-drafts", StringComparison.Ordinal)))
            {
                return;
            }
            // 此资源只包含DTO的机器生成Schema，没有任何假造产品路径。
            await using var source = typeof(G2OpenApi).Assembly.GetManifestResourceStream("OntologyPlatform.G2OpenApiSchemas.json")
                ?? throw new InvalidOperationException("G2生成Schema资源缺失。");
            // 官方OpenAPI解析器保留oneOf、null和const，不手写第二套业务DTO。
            var parsed = await OpenApiDocument.LoadAsync(source, "json", cancellationToken: cancellationToken);
            if (parsed.Document?.Components?.Schemas is null || parsed.Diagnostic?.Errors.Count > 0)
            {
                throw new InvalidOperationException("G2生成Schema资源无效。");
            }
            document.Components ??= new OpenApiComponents();
            document.Components.Schemas ??= new Dictionary<string, IOpenApiSchema>();
            // 逐个保留唯一生成组件，框架已有引用按同名组件输出。
            foreach (var schema in parsed.Document.Components.Schemas)
            {
                document.Components.Schemas[schema.Key] = schema.Value;
            }
            // 这里只检查实际发现的路由，不从静态Schema生成任何产品入口。
            foreach (var route in document.Paths)
            {
                if (!route.Key.StartsWith("/api/v1/", StringComparison.Ordinal) || route.Key.StartsWith("/api/v1/platform/", StringComparison.Ordinal)
                    || route.Value.Operations is null)
                {
                    continue;
                }
                // 每种写入方法独立声明与运行边界一致的防伪要求。
                foreach (var operation in route.Value.Operations)
                {
                    // 只有实际guard要求CAS的五个操作才声明强修订前置条件。
                    var requiresRevision = (operation.Key == HttpMethod.Put && route.Key == "/api/v1/ontology-drafts/{id}")
                        || (operation.Key == HttpMethod.Post && route.Key is "/api/v1/ontology-drafts/{id}/edits" or "/api/v1/ontology-drafts/{id}/vocabulary-edits" or "/api/v1/ontology-drafts/{id}/assessments" or "/api/v1/approvals/{id}/decisions" or "/api/v1/release-activations" or "/api/v1/execution-runs/{id}/cancel");
                    if (requiresRevision)
                    {
                        operation.Value.Parameters ??= [];
                        operation.Value.Parameters.Add(new OpenApiParameter
                        {
                            Name = "If-Match",
                            In = ParameterLocation.Header,
                            Required = true,
                            Description = "必需的强ETag，格式为带双引号的十进制修订，必须与Command.expectedRevision相同；缺失428，旧值或不匹配409。",
                            Schema = new OpenApiSchema { Type = JsonSchemaType.String, Pattern = "^\"[0-9]+\"$" }
                        });
                    }
                    // G2实际安全边界返回平台Problem，不能公开仅含原生ProblemDetails的弱化结构。
                    if (operation.Value.Responses is not null)
                    {
                        // 状态解析只消费真实响应元数据；逐项绑定同一安全错误结构。
                        foreach (var response in operation.Value.Responses.Where(item => int.TryParse(item.Key, out var status) && status >= 400))
                        {
                            if (response.Value is OpenApiResponse concrete)
                            {
                                concrete.Content = new Dictionary<string, OpenApiMediaType>
                                {
                                    ["application/problem+json"] = new() { Schema = new OpenApiSchemaReference("PlatformProblem", document) }
                                };
                            }
                        }
                    }
                    if (operation.Key == HttpMethod.Post || operation.Key == HttpMethod.Put || operation.Key == HttpMethod.Delete || operation.Key == HttpMethod.Patch)
                    {
                        operation.Value.Parameters ??= [];
                        operation.Value.Parameters.Add(new OpenApiParameter
                        {
                            Name = "X-CSRF-TOKEN",
                            In = ParameterLocation.Header,
                            Required = true,
                            Description = "从同源/auth/csrf领取并与会话关联的防伪令牌。",
                            Schema = new OpenApiSchema { Type = JsonSchemaType.String }
                        });
                    }
                }
            }
        });
        return options;
    }
}
