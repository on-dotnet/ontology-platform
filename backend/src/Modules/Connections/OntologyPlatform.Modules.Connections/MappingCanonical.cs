using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>mapping-c14n-v1固定字节协议，不修改G3或旧目录的序列化规则。</summary>
public static class MappingCanonical
{
    /// <summary>这些数组按唯一id视为集合，其余数组保留业务顺序。</summary>
    private static readonly HashSet<string> BindingSets = new(StringComparer.Ordinal)
    {
        "entities", "properties", "relations", "identitySpecs", "temporalSpecs", "conversions", "unitSpecs"
    };

    /// <summary>生成无BOM、无尾换行的规范UTF8字节。</summary>
    /// <param name="value">经类型及重复键检查的JSON树。</param>
    /// <returns>不超过一MiB的规范字节。</returns>
    public static byte[] Bytes(JsonElement value)
    {
        // 文本构造不使用当前机器区域设置。
        var builder = new StringBuilder();
        Write(value, builder, null);
        // 严格编码器拒绝无效UTF16代理项，不能替换成问号后继续散列。
        var bytes = new UTF8Encoding(false, true).GetBytes(builder.ToString());
        if (bytes.Length > G4MappingRules.MaximumBytes)
        {
            throw new SemanticOperationException(422, "mapping_payload_too_large");
        }
        return bytes;
    }

    /// <summary>以小写hex表示SHA256，不含synthetic或算法前缀。</summary>
    /// <param name="value">固定JSON语义树。</param>
    /// <returns>64位小写散列。</returns>
    public static string Hash(JsonElement value) => Convert.ToHexStringLower(SHA256.HashData(Bytes(value)));

    /// <summary>先使用唯一wire选项再规范化类型化对象。</summary>
    /// <typeparam name="T">固定合同类型。</typeparam>
    /// <param name="value">需要持久化的不可变对象。</param>
    /// <returns>规范字节。</returns>
    public static byte[] Serialize<T>(T value) => Bytes(JsonSerializer.SerializeToElement(value, G4MappingJson.Options));

    /// <summary>递归输出对象、集合与精确标量，不接受浮点数字。</summary>
    /// <param name="value">当前节点。</param>
    /// <param name="builder">当前字节对应的文本。</param>
    /// <param name="propertyName">用于区分集合与有序数组的字段名。</param>
    private static void Write(JsonElement value, StringBuilder builder, string? propertyName)
    {
        switch (value.ValueKind)
        {
            case JsonValueKind.Object:
                // UTF8序与UTF16 ordinal在补充平面字符处可能不同，显式使用字节比较。
                var properties = value.EnumerateObject().OrderBy(item => item.Name, Comparer<string>.Create(CompareUtf8)).ToArray();
                if (properties.Select(item => item.Name).Distinct(StringComparer.Ordinal).Count() != properties.Length)
                {
                    throw new SemanticOperationException(400, "mapping_payload_invalid");
                }
                builder.Append('{');
                for (var index = 0; index < properties.Length; index++)
                {
                    if (index > 0) builder.Append(',');
                    String(properties[index].Name, builder);
                    builder.Append(':');
                    Write(properties[index].Value, builder, properties[index].Name);
                }
                builder.Append('}');
                break;
            case JsonValueKind.Array:
                // 仅明确登记的集合可以排序，复合外部键及关系键顺序必须保持。
                var values = value.EnumerateArray().ToArray();
                if (propertyName == "siteIds" || propertyName is not null && BindingSets.Contains(propertyName))
                {
                    // 集合唯一键必须存在且是字符串，不从数组位置合成id。
                    var keyed = values.Select(item => (Key: propertyName == "siteIds" ? item.GetString() : item.GetProperty("id").GetString(), Value: item)).ToArray();
                    if (keyed.Any(item => string.IsNullOrEmpty(item.Key)) || keyed.Select(item => item.Key).Distinct(StringComparer.Ordinal).Count() != keyed.Length)
                    {
                        throw new SemanticOperationException(400, "mapping_payload_invalid");
                    }
                    values = keyed.OrderBy(item => item.Key!, Comparer<string>.Create(CompareUtf8)).Select(item => item.Value).ToArray();
                }
                builder.Append('[');
                for (var index = 0; index < values.Length; index++)
                {
                    if (index > 0) builder.Append(',');
                    Write(values[index], builder, null);
                }
                builder.Append(']');
                break;
            case JsonValueKind.String:
                String(value.GetString()!, builder);
                break;
            case JsonValueKind.Number:
                // decimal作为字符串传输，JSON数字只容纳可精确往返的整数。
                var raw = value.GetRawText();
                if (!value.TryGetInt64(out var number) || number < -G4MappingRules.MaximumRevision || number > G4MappingRules.MaximumRevision
                    || raw != number.ToString(CultureInfo.InvariantCulture))
                {
                    throw new SemanticOperationException(400, "mapping_payload_invalid");
                }
                builder.Append(raw);
                break;
            case JsonValueKind.True:
                builder.Append("true");
                break;
            case JsonValueKind.False:
                builder.Append("false");
                break;
            case JsonValueKind.Null:
                builder.Append("null");
                break;
            default:
                throw new SemanticOperationException(400, "mapping_payload_invalid");
        }
    }

    /// <summary>按精确UTF8字节比较，不进行Unicode规范化。</summary>
    private static int CompareUtf8(string left, string right) => Encoding.UTF8.GetBytes(left).AsSpan().SequenceCompareTo(Encoding.UTF8.GetBytes(right));

    /// <summary>固定字符串转义，控制字符全部采用小写四位转义。</summary>
    /// <param name="value">精确Unicode字符串。</param>
    /// <param name="builder">输出缓冲。</param>
    private static void String(string value, StringBuilder builder)
    {
        // 先验证代理项，不允许EnumerateRunes悄悄替换无效值。
        _ = new UTF8Encoding(false, true).GetByteCount(value);
        builder.Append('"');
        foreach (var character in value)
        {
            if (character == '"' || character == '\\')
            {
                builder.Append('\\').Append(character);
            }
            else if (character < 0x20)
            {
                builder.Append("\\u").Append(((int)character).ToString("x4", CultureInfo.InvariantCulture));
            }
            else
            {
                builder.Append(character);
            }
        }
        builder.Append('"');
    }
}
