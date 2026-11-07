using System.Text.Json;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>固定合成数据合同的有界验证与目录投影；原始响应值不进入目录。</summary>
public static class WebJsonCatalog
{
    /// <summary>完整HTTP正文的字节预算。</summary>
    public const int MaximumBytes = 2 * 1024 * 1024;

    /// <summary>按登记的逻辑视图合同校验真实JSON，不从样本猜测类型或精度。</summary>
    /// <param name="body">当前响应字节，仅在调用内存中处理。</param>
    /// <param name="token">调用方取消与截止信号。</param>
    /// <returns>固定合同元数据；空数据数组仍是已声明视图而非空目录。</returns>
    public static CatalogObject[] Parse(byte[] body, CancellationToken token = default)
    {
        token.ThrowIfCancellationRequested();
        if (body.Length > MaximumBytes) throw new PgSourceException("catalog_budget_exceeded");
        try
        {
            // 深度、注释与尾逗号均严格有界，精确数字不转double。
            using var document = JsonDocument.Parse(body, new JsonDocumentOptions { MaxDepth = 16, AllowTrailingCommas = false, CommentHandling = JsonCommentHandling.Disallow });
            // 本操作只接受完整数组；不接收任何远端schema或分页指令。
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Array || root.GetArrayLength() > 1000) throw new PgSourceException("catalog_budget_exceeded");
            // 每条数据只校验，不写入任何目录、审计或日志。
            foreach (var item in root.EnumerateArray())
            {
                token.ThrowIfCancellationRequested();
                if (item.ValueKind != JsonValueKind.Object) throw new PgSourceException("catalog_permission_limited");
                // 精确属性集合同时拒绝missing、unknown和重复属性。
                var properties = item.EnumerateObject().ToArray();
                if (properties.Length != 3 || properties.Select(value => value.Name).Distinct(StringComparer.Ordinal).Count() != 3
                    || !item.TryGetProperty("id", out var id) || !item.TryGetProperty("label", out var label) || !item.TryGetProperty("reading", out var reading))
                    throw new PgSourceException("catalog_permission_limited");
                if (id.ValueKind != JsonValueKind.Number || id.GetRawText().Length > 128 || id.GetRawText().Any(value => value is '.' or 'e' or 'E')
                    || label.ValueKind != JsonValueKind.String || label.GetString()!.Length > 256
                    || reading.ValueKind is not (JsonValueKind.Null or JsonValueKind.Number)
                    || reading.ValueKind == JsonValueKind.Number && reading.GetRawText().Length > 128)
                    throw new PgSourceException("catalog_permission_limited");
            }
            token.ThrowIfCancellationRequested();
            return [new CatalogObject
            {
                Schema = "web_api", Name = "fixture_items", Kind = "VIEW",
                Fields =
                [
                    new CatalogField { Name = "id", NativeType = "json:integer", Nullable = false, Ordinal = 1, Precision = null, Scale = null },
                    new CatalogField { Name = "label", NativeType = "json:string", Nullable = false, Ordinal = 2, Precision = null, Scale = null },
                    new CatalogField { Name = "reading", NativeType = "json:number", Nullable = true, Ordinal = 3, Precision = null, Scale = null }
                ]
            }];
        }
        catch (JsonException) { throw new PgSourceException("catalog_permission_limited"); }
    }
}
