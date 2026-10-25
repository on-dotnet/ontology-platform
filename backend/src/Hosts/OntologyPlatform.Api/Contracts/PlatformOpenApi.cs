using Microsoft.AspNetCore.OpenApi;
using Microsoft.OpenApi;

namespace OntologyPlatform.Api.Contracts;

/// <summary>为运行时生成文档声明冻结的服务器Cookie及内部探针身份，不改变运行授权。</summary>
public static class PlatformOpenApi
{
    /// <summary>将明确的会话和健康探针安全方案关联到实际生成的路由。</summary>
    /// <param name="options">正式API文档生成器选项。</param>
    /// <returns>原选项，便于宿主组合。</returns>
    public static OpenApiOptions AddPlatformContracts(this OpenApiOptions options)
    {
        options.AddDocumentTransformer((document, _, _) =>
        {
            document.Components ??= new OpenApiComponents();
            document.Components.SecuritySchemes ??= new Dictionary<string, IOpenApiSecurityScheme>();
            document.Components.SecuritySchemes["session"] = new OpenApiSecurityScheme
            {
                Type = SecuritySchemeType.ApiKey,
                In = ParameterLocation.Cookie,
                Name = ".OntologyPlatform.Session",
                Description = "仅包含受保护随机引用的HttpOnly BFF会话Cookie；令牌只留在服务器加密票据。"
            };
            document.Components.SecuritySchemes["health"] = new OpenApiSecurityScheme
            {
                Type = SecuritySchemeType.ApiKey,
                In = ParameterLocation.Header,
                Name = "X-Health-Key",
                Description = "仅由内部编排器持有的外置健康探针密钥。"
            };
            foreach (var path in document.Paths)
            {
                // 公开登录及CSRF领取路由不假标为必须已认证。
                var scheme = path.Key.StartsWith("/api/v1/platform/", StringComparison.Ordinal) || path.Key == "/auth/logout"
                    ? "session" : path.Key.StartsWith("/health/", StringComparison.Ordinal) ? "health" : null;
                if (scheme is null || path.Value.Operations is null)
                {
                    continue;
                }
                foreach (var operation in path.Value.Operations.Values)
                {
                    operation.Security = [new OpenApiSecurityRequirement { [new OpenApiSecuritySchemeReference(scheme, document)] = [] }];
                }
            }
            return Task.CompletedTask;
        });
        return options;
    }
}
