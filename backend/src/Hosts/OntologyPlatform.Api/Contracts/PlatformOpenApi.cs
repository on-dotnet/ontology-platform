using System.Text.Json.Nodes;
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
            // 遍历实际生成的路由，仅给受保护边界声明对应身份方案。
            foreach (var path in document.Paths)
            {
                // 公开登录及CSRF领取路由不假标为必须已认证。
                var scheme = path.Key.StartsWith("/api/v1/platform/", StringComparison.Ordinal) || path.Key == "/auth/logout"
                    ? "session" : path.Key.StartsWith("/health/", StringComparison.Ordinal) ? "health" : null;
                if (path.Value.Operations is null)
                {
                    continue;
                }
                // 每个HTTP操作分别声明安全要求，避免继承全局误标公开入口。
                foreach (var operation in path.Value.Operations.Values)
                {
                    operation.OperationId = path.Key switch
                    {
                        "/api/v1/platform/me" => "getPlatformMe",
                        "/api/v1/platform/resources" => "listPlatformResources",
                        "/api/v1/platform/resources/{id}" => "getPlatformResource",
                        "/api/v1/platform/audit" => "listPlatformAudit",
                        "/auth/csrf" => "getCsrfToken",
                        "/auth/login" => "login",
                        "/auth/logout" => "logout",
                        _ => operation.OperationId
                    };
                    if (scheme is not null)
                    {
                        operation.Security = [new OpenApiSecurityRequirement { [new OpenApiSecuritySchemeReference(scheme, document)] = [] }];
                    }
                    if (path.Key == "/auth/logout")
                    {
                        operation.Description = "必须提供有效header或表单CSRF token至少一项；浏览器使用原生form POST顶层导航。";
                        operation.Parameters ??= [];
                        operation.Parameters.Add(new OpenApiParameter
                        {
                            Name = "X-CSRF-TOKEN",
                            In = ParameterLocation.Header,
                            Required = false,
                            Schema = new OpenApiSchema { Type = JsonSchemaType.String }
                        });
                        operation.RequestBody = new OpenApiRequestBody
                        {
                            Required = false,
                            Content = new Dictionary<string, OpenApiMediaType>
                            {
                                ["application/x-www-form-urlencoded"] = new()
                                {
                                    Schema = new OpenApiSchema
                                    {
                                        Type = JsonSchemaType.Object,
                                        Required = new HashSet<string> { "__RequestVerificationToken" },
                                        Properties = new Dictionary<string, IOpenApiSchema>
                                        {
                                            ["__RequestVerificationToken"] = new OpenApiSchema { Type = JsonSchemaType.String }
                                        }
                                    }
                                }
                            }
                        };
                    }
                    if (path.Key == "/api/v1/platform/audit")
                    {
                        operation.Parameters ??= [];
                        // 运行端点直接读取查询集合，显式补入实际校验的limit参数。
                        var limit = operation.Parameters.FirstOrDefault(parameter => parameter.Name == "limit");
                        if (limit is null)
                        {
                            limit = new OpenApiParameter { Name = "limit", In = ParameterLocation.Query, Required = false };
                            operation.Parameters.Add(limit);
                        }
                        // 已解析的参数定义使用与运行校验相同的1..100边界和默认20。
                        if (limit is OpenApiParameter parameter)
                        {
                            parameter.Schema = new OpenApiSchema { Type = JsonSchemaType.Integer, Minimum = "1", Maximum = "100", Default = JsonValue.Create(20) };
                        }
                    }
                    if (path.Key == "/auth/login")
                    {
                        // 实际登录在returnUrl缺失时使用本站根路径。
                        var destination = operation.Parameters?.FirstOrDefault(parameter => parameter.Name == "returnUrl");
                        // 这里只描述默认值，不扩大服务器允许的跳转目标。
                        if (destination is OpenApiParameter parameter)
                        {
                            parameter.Schema = new OpenApiSchema { Type = JsonSchemaType.String, Default = JsonValue.Create("/") };
                        }
                    }
                }
            }
            return Task.CompletedTask;
        });
        return options;
    }
}
