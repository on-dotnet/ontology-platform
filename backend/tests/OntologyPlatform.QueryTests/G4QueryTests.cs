using System.Text;
using System.Text.Json;
using OntologyPlatform.Modules.SemanticQuery;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.QueryTests;

/// <summary>规范字节不依赖运行时文化、字段声明顺序或浏览器浮点格式。</summary>
[TestClass]
public sealed class G4QueryTests
{
    /// <summary>UTF8键顺序、控制符最小规则与精确字符串逐字节稳定。</summary>
    [TestMethod]
    public void CanonicalBytesPreservePreciseValuesAndUnicode()
    {
        // 补充平面字符与私用字符验证UTF8排序不同于UTF16 ordinal排序。
        using var input = JsonDocument.Parse("{\"𐀀\":0,\"\ue000\":1,\"value\":\"9007199254740993.20\",\"text\":\"中文\\n\\t/\"}");
        // 控制字符统一小写u00xx，非ASCII和斜线保真。
        var expected = "{\"text\":\"中文\\u000a\\u0009/\",\"value\":\"9007199254740993.20\",\"\ue000\":1,\"𐀀\":0}";
        CollectionAssert.AreEqual(Encoding.UTF8.GetBytes(expected), G4QueryCanonical.Value(input.RootElement));
        // 不允许一般JSON数字冒充安全结构整数。
        using var unsafeNumber = JsonDocument.Parse("{\"value\":9007199254740993}");
        Assert.Throws<InvalidOperationException>(() => G4QueryCanonical.Value(unsafeNumber.RootElement));
        using var fraction = JsonDocument.Parse("{\"value\":1.5}");
        Assert.Throws<InvalidOperationException>(() => G4QueryCanonical.Value(fraction.RootElement));
    }
    /// <summary>不同小数精度的同类型时间按真实时刻排序，不能按Z字符位置排序。</summary>
    [TestMethod]
    public void ProjectionSortsActualTimeAndRefusesMixedTimeKinds()
    {
        // 这里只验证规范排序，不以合成wire代替真实源证据。
        var first = new G4ObservationDatum
        {
            EntityIri = "urn:fixture:one", EvidenceIds = ["e-1"],
            Identity = new G4QueryIdentity { OrganizationId = "org-1", SiteId = "site-1", SourceNamespace = "fixture", ExternalId = "one", EffectiveTime = null },
            PropertyIri = "urn:fixture:value", Value = new G4Int64Value { Lexical = "1" }, Unit = null,
            EventTime = new G4QueryTime { Kind = "UTC", Lexical = "2026-11-14T00:00:03Z", FractionalDigits = 0 },
            ObservedAtUtc = "2026-11-14T00:00:04.000000Z", ValidTime = null
        };
        // 同秒稍晚100毫秒，但词法小数点排在Z之前。
        var later = first with { EventTime = first.EventTime with { Lexical = "2026-11-14T00:00:03.1Z", FractionalDigits = 1 } };
        using var ordered = JsonDocument.Parse(G4QueryCanonical.Projection([later, first]));
        Assert.AreEqual(first.EventTime.Lexical, ordered.RootElement[0].GetProperty("eventTime").GetProperty("lexical").GetString());
        // LOCAL与UTC没有已知可比较基准，不能自行换算或混排。
        var local = first with { EventTime = first.EventTime with { Kind = "LOCAL", Lexical = "2026-11-14T00:00:03" } };
        Assert.Throws<InvalidOperationException>(() => G4QueryCanonical.Projection([local, first]));
    }
}
