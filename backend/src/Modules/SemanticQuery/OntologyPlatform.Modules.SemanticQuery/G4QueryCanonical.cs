using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>g4-query-c14n-v1仅服务查询规范字节，不重算历史映射或目录散列。</summary>
public static class G4QueryCanonical
{
    /// <summary>UTF8顺序与UTF16 ordinal不同，补充平面字符必须按实际编码比较。</summary>
    private static readonly IComparer<string> Utf8Order = Comparer<string>.Create((left, right) =>
        Encoding.UTF8.GetBytes(left).AsSpan().SequenceCompareTo(Encoding.UTF8.GetBytes(right)));

    /// <summary>验证并规范化结果的集合排序，返回无BOM无换行的原件。</summary>
    public static byte[] Result(G4QueryResultV1 result)
    {
        G4QueryRules.ValidateResult(result);
        // 仅对已通过正式模型的结构处理集合语义，不猜任意JSON数组。
        var node = JsonSerializer.SerializeToNode(result, G4QueryJson.Options)!;
        Normalize(node, string.Empty);
        // 节点转换只作为内存树，实际规范编码不使用默认JSON转义策略。
        var bytes = Value(JsonSerializer.SerializeToElement(node));
        if (bytes.Length > G4QueryRules.MaximumResultBytes) throw new SemanticOperationException(503, "query_result_invalid");
        return bytes;
    }

    /// <summary>单分支已授权投影按同一数据排序产生回执散列原件，不包含回执自身。</summary>
    public static byte[] Projection(G4QueryDatum[] data)
    {
        if (data.Length > 100) throw new SemanticOperationException(503, "query_result_invalid");
        foreach (var item in data) G4QueryRules.Validate(item);
        // 投影与总结果使用同一排序，避免回执散列依赖源返回顺序。
        var node = JsonSerializer.SerializeToNode(data, G4QueryJson.Options)!;
        Normalize(node, "data");
        return Value(JsonSerializer.SerializeToElement(node));
    }

    /// <summary>在行预算截断之前按最终规范业务键排序，不用事后排序掩盖错误前缀。</summary>
    public static G4QueryDatum[] OrderData(IEnumerable<G4QueryDatum> data) => data
        .Select(item => (Datum: item, Node: JsonSerializer.SerializeToNode(item, G4QueryJson.Options)!))
        .OrderBy(item => item.Node, Comparer<JsonNode>.Create((left, right) => CompareItem(left, right, "data")))
        .Select(item => item.Datum).ToArray();

    /// <summary>明确保持数组顺序的请求或内部对象规范编码，调用方负责其类型校验。</summary>
    public static byte[] Serialize<T>(T value) => Value(JsonSerializer.SerializeToElement(value, G4QueryJson.Options));

    /// <summary>递归按UTF8键序编码，只允许安全结构整数及精确字符串。</summary>
    public static byte[] Value(JsonElement value)
    {
        G4QueryRules.Unique(value);
        // 构造器不做换行或缩进，最大大小由业务调用方在用途边界约束。
        var buffer = new StringBuilder();
        Write(buffer, value);
        return new UTF8Encoding(false, true).GetBytes(buffer.ToString());
    }

    /// <summary>规范原件的稳定SHA256，不把散列字段加入原件自身。</summary>
    public static string Hash(byte[] bytes) => Convert.ToHexStringLower(SHA256.HashData(bytes));

    /// <summary>每种JSON节点只有一个编码方式，禁止指数、小数和非安全整数。</summary>
    private static void Write(StringBuilder buffer, JsonElement value)
    {
        switch (value.ValueKind)
        {
            case JsonValueKind.Object:
                buffer.Append('{');
                // 排序使用UTF8字节，不受当前文化影响。
                var properties = value.EnumerateObject().OrderBy(item => item.Name, Utf8Order).ToArray();
                for (var index = 0; index < properties.Length; index++)
                {
                    if (index > 0) buffer.Append(',');
                    String(buffer, properties[index].Name);
                    buffer.Append(':');
                    Write(buffer, properties[index].Value);
                }
                buffer.Append('}');
                break;
            case JsonValueKind.Array:
                buffer.Append('[');
                // 数组顺序由上层明确的合同集合规则决定。
                var position = 0;
                foreach (var item in value.EnumerateArray())
                {
                    if (position++ > 0) buffer.Append(',');
                    Write(buffer, item);
                }
                buffer.Append(']');
                break;
            case JsonValueKind.String:
                String(buffer, value.GetString()!);
                break;
            case JsonValueKind.Number:
                if (!value.TryGetInt64(out var number) || number is < -9007199254740991L or > 9007199254740991L)
                    throw new InvalidOperationException("查询规范字节只接受安全结构整数。");
                buffer.Append(number.ToString(CultureInfo.InvariantCulture));
                break;
            case JsonValueKind.True:
                buffer.Append("true");
                break;
            case JsonValueKind.False:
                buffer.Append("false");
                break;
            case JsonValueKind.Null:
                buffer.Append("null");
                break;
            default:
                throw new InvalidOperationException("查询规范字节存在未定义节点。");
        }
    }

    /// <summary>控制字符固定小写u00xx，其他只转义引号与反斜线。</summary>
    private static void String(StringBuilder buffer, string text)
    {
        _ = new UTF8Encoding(false, true).GetByteCount(text);
        buffer.Append('"');
        foreach (var character in text)
        {
            if (character < 32) buffer.Append("\\u00").Append(((int)character).ToString("x2", CultureInfo.InvariantCulture));
            else if (character is '"' or '\\') buffer.Append('\\').Append(character);
            else buffer.Append(character);
        }
        buffer.Append('"');
    }

    /// <summary>已批准结果集合归一化；业务值本身不trim、不Unicode归一化。</summary>
    private static void Normalize(JsonNode node, string property)
    {
        if (node is JsonObject map)
        {
            foreach (var pair in map) if (pair.Value is not null) Normalize(pair.Value, pair.Key);
        }
        else if (node is JsonArray array)
        {
            foreach (var child in array) if (child is not null) Normalize(child, string.Empty);
            if (property is "evidenceIds" or "typeIris" or "entityTypeIris" or "mappingReleaseIds" or "sourceCatalogSnapshotIds" or "domainIris" or "rangeIris" or "siteIds")
            {
                // 语义集合按UTF8排序并去重；普通业务数组不自动去重。
                var strings = array.Select(item => item!.GetValue<string>()).Distinct(StringComparer.Ordinal).Order(Utf8Order).ToArray();
                array.Clear();
                foreach (var text in strings) array.Add(text);
            }
            else if (property is "data" or "properties" or "candidates" or "evidence" or "subSources")
            {
                // 同业务排序键时完整规范字节作稳定次序，只合并完全相同项。
                var ordered = array.Select(item => item!.DeepClone()).OrderBy(item => item,
                    Comparer<JsonNode>.Create((left, right) => CompareItem(left, right, property))).ToArray();
                array.Clear();
                // data才有精确字节去重语义，其他数组唯一性由结果守卫验证。
                var seen = new HashSet<string>(StringComparer.Ordinal);
                foreach (var item in ordered)
                {
                    if (property != "data" || seen.Add(Convert.ToBase64String(Value(JsonSerializer.SerializeToElement(item))))) array.Add(item);
                }
            }
        }
    }

    /// <summary>数据按冻结的六级业务键排序，再用完整规范字节消除并列不确定性。</summary>
    private static int CompareItem(JsonNode left, JsonNode right, string property)
    {
        // 路径固定来自服务器合同，不接受动态表达式或任意脚本。
        var paths = property switch
        {
            "data" => new[] { "kind", "entityIri", "propertyIri", "eventTime.lexical", "relationshipIri", "target.entityIri" },
            "properties" => ["propertyIri"],
            "candidates" => ["entityIri"],
            "evidence" => ["evidenceId"],
            "subSources" => ["sourceReadReceiptId"],
            _ => Array.Empty<string>()
        };
        foreach (var path in paths)
        {
            // 比较结果非零即确定顺序，空值采用冻结空串键。
            var order = path == "eventTime.lexical" ? CompareTime(left, right) : Utf8Order.Compare(Key(left, path), Key(right, path));
            if (order != 0) return order;
        }
        return Value(JsonSerializer.SerializeToElement(left)).AsSpan().SequenceCompareTo(Value(JsonSerializer.SerializeToElement(right)));
    }

    /// <summary>同一种类的实际时刻按九位精确小数比较，不将LOCAL猜成UTC。</summary>
    private static int CompareTime(JsonNode left, JsonNode right)
    {
        // 无事件时间用空键排序，不以观察时刻补齐。
        var leftTime = left["eventTime"];
        // 左右值已经通过Time词法校验，之后不再解析为浮点。
        var rightTime = right["eventTime"];
        if (leftTime is null || rightTime is null) return leftTime is null ? (rightTime is null ? 0 : -1) : 1;
        if (Key(leftTime, "kind") != Key(rightTime, "kind")) throw new InvalidOperationException("查询不能混合未知可比性的时间种类。");
        return string.CompareOrdinal(TimeKey(leftTime), TimeKey(rightTime));
    }

    /// <summary>日期保留日期，时刻小数仅补零比较，不改变结果中的原始词法。</summary>
    private static string TimeKey(JsonNode time)
    {
        // 正式合同已限制时间种类、实际公历和最多九位小数。
        var lexical = Key(time, "lexical");
        if (Key(time, "kind") == "DATE") return lexical;
        // 去掉UTC标记后固定补齐九位，避免无小数Z与小数点的词法误序。
        var local = Key(time, "kind") == "UTC" ? lexical[..^1] : lexical;
        return local[..19] + "." + (local.Length == 19 ? string.Empty : local[20..]).PadRight(9, '0');
    }

    /// <summary>仅提取固定路径的可空字符串，不替换缺失业务值。</summary>
    private static string Key(JsonNode node, string path)
    {
        foreach (var part in path.Split('.'))
        {
            if (node is not JsonObject map || map[part] is not { } next) return string.Empty;
            node = next;
        }
        return node.GetValue<string>();
    }
}
