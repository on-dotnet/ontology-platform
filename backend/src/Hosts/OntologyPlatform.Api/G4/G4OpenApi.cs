using System.Text.Json.Nodes;
using OntologyPlatform.Contracts;
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
        options.AddDocumentTransformer((document, _, _) =>
        {
            document.Servers = [new OpenApiServer { Url = "/" }];
            return Task.CompletedTask;
        });
        options.AddSchemaTransformer((schema, context, _) =>
        {
            // G4运行入口禁用Web的数字字符串宽容选项，文档必须一致。
            var type = Nullable.GetUnderlyingType(context.JsonTypeInfo.Type) ?? context.JsonTypeInfo.Type;
            if (type == typeof(int) || type == typeof(long))
            {
                schema.Type = JsonSchemaType.Integer | (Nullable.GetUnderlyingType(context.JsonTypeInfo.Type) is null ? 0 : JsonSchemaType.Null);
                schema.Pattern = null;
            }
            if (type == typeof(OracleColumnMetadata) && schema.Properties is not null)
            {
                // 显式枚举与DTO setter保持同一合同，不把未知字符串描述为受支持值。
                var values = new Dictionary<string, string[]>
                {
                    ["charSemantics"] = ["BYTE", "CHAR"],
                    ["timeZoneKind"] = ["NONE", "WITH_TIME_ZONE", "WITH_LOCAL_TIME_ZONE", "UNKNOWN"],
                    ["supportStatus"] = ["SUPPORTED", "METADATA_ONLY", "UNSUPPORTED"]
                };
                foreach (var entry in values)
                {
                    if (schema.Properties.TryGetValue(entry.Key, out var property) && property is OpenApiSchema concrete)
                    {
                        concrete.Enum = entry.Value.Select(value => (JsonNode)JsonValue.Create(value)!).ToList();
                        if (entry.Key == "charSemantics") concrete.Enum.Add(null!);
                    }
                }
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
