using System.Text.Json.Serialization;

namespace OntologyPlatform.Contracts;

/// <summary>只允许冻结文本协议枚举，拒绝数值和未登记值。</summary>
/// <typeparam name="TEnum">具有明确协议文本的枚举。</typeparam>
public sealed class StrictStringEnumConverter<TEnum> : JsonStringEnumConverter<TEnum> where TEnum : struct, Enum
{
    /// <summary>关闭框架默认允许整数的兼容行为，避免未定义状态穿透边界。</summary>
    public StrictStringEnumConverter() : base(namingPolicy: null, allowIntegerValues: false)
    {
    }
}
