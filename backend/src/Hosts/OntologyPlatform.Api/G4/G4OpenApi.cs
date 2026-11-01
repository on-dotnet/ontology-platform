using Microsoft.AspNetCore.OpenApi;
using Microsoft.OpenApi;

namespace OntologyPlatform.Api.G4;

/// <summary>让原生OpenAPI反映G4专用严格数字与必填判别，不改变G2文档或序列化。</summary>
public static class G4OpenApi
{
    /// <summary>仅用于G4文档的产品模型投影规则。</summary>
    public static OpenApiOptions AddG4Contracts(this OpenApiOptions options)
    {
        options.ShouldInclude = description => description.GroupName == "g4";
        options.AddSchemaTransformer((schema, context, _) =>
        {
            // G4运行入口禁用Web的数字字符串宽容选项，文档必须一致。
            var type = Nullable.GetUnderlyingType(context.JsonTypeInfo.Type) ?? context.JsonTypeInfo.Type;
            if (type == typeof(int) || type == typeof(long))
            {
                schema.Type = JsonSchemaType.Integer | (Nullable.GetUnderlyingType(context.JsonTypeInfo.Type) is null ? 0 : JsonSchemaType.Null);
                schema.Pattern = null;
            }
            if (schema.Properties?.ContainsKey("type") == true)
            {
                schema.Required ??= new HashSet<string>();
                schema.Required.Add("type");
            }
            return Task.CompletedTask;
        });
        return options;
    }
}
