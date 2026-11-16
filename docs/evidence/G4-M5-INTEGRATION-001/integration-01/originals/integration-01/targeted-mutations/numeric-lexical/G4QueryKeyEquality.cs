using System.Globalization;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>关系键的精确值相等独立于输出表示；不修改词法、声明精度或规范字节。</summary>
internal static class G4QueryKeyEquality
{
    /// <summary>仅比较已批准的同类型值，numeric使用28位范围内无损decimal；空值不形成关系。</summary>
    internal static bool Equal(G4QueryValue left, G4QueryValue right)
    {
        try
        {
            G4QueryRules.Value(left);
            G4QueryRules.Value(right);
            if (left is G4NullValue || right is G4NullValue) return false;
            if (left.GetType() != right.GetType()) throw new SemanticOperationException(503, "query_source_indeterminate");
            if (left is G4DecimalValue && right is G4DecimalValue)
            {
                // 冻结合同先验证precision≤28及scale、整数容量和词法，decimal解析不会舍入或经过浮点。
                var first = decimal.Parse(left.Lexical!, NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture);
                // 只在比较时解释数值，不把解析值写回源行或结果。
                var second = decimal.Parse(right.Lexical!, NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture);
                return string.Equals(left.Lexical, right.Lexical, StringComparison.Ordinal);
            }
            return string.Equals(left.Lexical, right.Lexical, StringComparison.Ordinal);
        }
        catch (Exception error) when (error is SemanticOperationException or FormatException or OverflowException)
        {
            // 源值不能证明相等时保留明确不确定边界，禁止输出完整FOUND/EMPTY伪装成功。
            throw new SemanticOperationException(503, "query_source_indeterminate");
        }
    }
}
