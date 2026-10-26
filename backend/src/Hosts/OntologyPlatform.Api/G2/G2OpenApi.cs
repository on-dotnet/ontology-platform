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
            foreach (var schema in parsed.Document.Components.Schemas)
            {
                document.Components.Schemas[schema.Key] = schema.Value;
            }
            foreach (var route in document.Paths)
            {
                if (!route.Key.StartsWith("/api/v1/", StringComparison.Ordinal) || route.Key.StartsWith("/api/v1/platform/", StringComparison.Ordinal)
                    || route.Value.Operations is null)
                {
                    continue;
                }
                foreach (var operation in route.Value.Operations)
                {
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
