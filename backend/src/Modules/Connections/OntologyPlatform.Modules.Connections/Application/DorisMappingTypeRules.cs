using System.Globalization;
using System.Text.RegularExpressions;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>限定合成 Doris 数据的无损转换，不从宿主时区或浮点表示推导源值。</summary>
internal static class DorisMappingTypeRules
{
    /// <summary>验证十进制原始文本与已观测目录精度，返回固定小数位的查询值。</summary>
    /// <param name="text">源端定点数的完整十进制文本。</param>
    /// <param name="precision">真实元数据声明的总位数。</param>
    /// <param name="scale">真实元数据声明的小数位数。</param>
    /// <returns>保留源声明精度与标度的值。</returns>
    internal static G4DecimalValue DecimalValue(string text, int precision, int scale)
    {
        if (precision is < 1 or > 28 || scale < 0 || scale > precision || text.Length > 32
            || !Regex.IsMatch(text, @"\A-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\z", RegexOptions.CultureInvariant))
        {
            throw Invalid();
        }

        // 整数和小数位分别检查，避免 Parse 或格式化隐式舍入超出声明的输入。
        var digits = text.AsSpan(text[0] == '-' ? 1 : 0);
        // 无小数点时所有字符均为整数部分。
        var point = digits.IndexOf('.');
        // 表示零的前置位不占 DECIMAL(p,p) 的整数精度。
        var integer = point < 0 ? digits : digits[..point];
        if ((integer.SequenceEqual("0") ? 0 : integer.Length) > precision - scale
            || (point < 0 ? 0 : digits.Length - point - 1) != scale
            || !decimal.TryParse(text, NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint,
                CultureInfo.InvariantCulture, out var value))
        {
            throw Invalid();
        }

        return new G4DecimalValue
        {
            Lexical = value == 0 ? 0m.ToString($"F{scale}", CultureInfo.InvariantCulture) : text,
            Precision = precision,
            Scale = scale
        };
    }

    /// <summary>把 DATETIMEV2(6) 本地业务词法按已批准的 Etc/UTC 映射解释为 UTC 瞬间。</summary>
    /// <param name="text">未附带时区的六位微秒源值。</param>
    /// <param name="spec">发布绑定的时区和精度策略。</param>
    /// <returns>可用于既有半开区间比较的精确 UTC 值。</returns>
    internal static DateTimeOffset Instant(string text, MappingTemporalSpec spec)
    {
        if (spec.TimezonePolicy.Kind != "REGISTERED_ZONE" || spec.TimezonePolicy.ZoneId != "Etc/UTC"
            || spec.Precision != "MICROSECOND" || !DateTime.TryParseExact(text, "yyyy-MM-dd HH:mm:ss.ffffff",
                CultureInfo.InvariantCulture, DateTimeStyles.None, out var local))
        {
            throw Invalid();
        }

        return new DateTimeOffset(local, TimeSpan.Zero);
    }

    /// <summary>返回固定拒绝码，避免将业务原值或元数据正文写入错误响应。</summary>
    private static SemanticOperationException Invalid() => new(422, "mapping_source_type_invalid");
}
