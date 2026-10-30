using System.Globalization;
using System.Text.RegularExpressions;

namespace OntologyPlatform.Contracts;

/// <summary>有界时间模板的显式时区词法与半开区间关系，不执行时间推理。</summary>
public static class TemporalContractRules
{
    /// <summary>仅接受显式时区且精度可由本轮执行器完整表示的时间戳。</summary>
    /// <param name="text">源literal原始词法，空值仅代表未知。</param>
    /// <param name="instant">成功时的同一UTC时间点。</param>
    /// <returns>合法已知时间为真；无时区及未知值不推断。</returns>
    public static bool TryInstant(string? text, out DateTimeOffset instant)
    {
        instant = default;
        if (text is null || text.Length > 40 || !Regex.IsMatch(text,
            @"\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,7})?(?:Z|[+-](?:0[0-9]|1[0-4]):[0-5][0-9])\z",
            RegexOptions.CultureInvariant, TimeSpan.FromMilliseconds(100))) return false;
        return DateTimeOffset.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.None, out instant);
    }

    /// <summary>比较半开区间；未知端点只在能证明不相交时返回确定关系。</summary>
    /// <param name="leftFrom">左区间起点，null为未知。</param>
    /// <param name="leftTo">左区间终点，null为未知。</param>
    /// <param name="rightFrom">右区间起点，null为未知。</param>
    /// <param name="rightTo">右区间终点，null为未知。</param>
    /// <returns>无效、确定重叠、不相交或不确定的独立状态。</returns>
    public static TemporalRelation Compare(string? leftFrom, string? leftTo, string? rightFrom, string? rightTo)
    {
        // 固定槽位保留各端点的未知性，不替换为无穷或机器时间。
        string?[] values = [leftFrom, leftTo, rightFrom, rightTo];
        // 解析后的值只有相应源非空时才可用于关系判断。
        var points = new DateTimeOffset[4];
        for (var index = 0; index < values.Length; index++)
            if (values[index] is not null && !TryInstant(values[index], out points[index])) return TemporalRelation.Invalid;
        if (leftFrom is not null && leftTo is not null && points[0] >= points[1]
            || rightFrom is not null && rightTo is not null && points[2] >= points[3]) return TemporalRelation.Invalid;
        if (leftTo is not null && rightFrom is not null && points[1] <= points[2]
            || rightTo is not null && leftFrom is not null && points[3] <= points[0]) return TemporalRelation.Disjoint;
        return values.All(value => value is not null) ? TemporalRelation.Overlap : TemporalRelation.Indeterminate;
    }
}
