using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>Oracle 正式读取的纯类型、关系和原目录字节资格反例，不触碰任何实例。</summary>
[TestClass]
public sealed class OracleMappingBindingTests
{
    /// <summary>同键异标度精确匹配；NULL、邻近值、跨厂与纳秒边界不会组成边。</summary>
    [TestMethod]
    public void OnlyExactKeysAndOverlappingHalfOpenIntervalsMatch()
    {
        // 父区间为两个微秒，子窗口可向前或向后偏移一个纳秒。
        var parent = Row("1.0", 12, 1, "2026-01-01T00:00:00.000001Z", "2026-01-01T00:00:00.000003Z");
        // 已知交叠的目标用于逐项替换单一输入。
        var target = Row("1.00", 13, 2, "2026-01-01T00:00:00.000002999Z", "2026-01-01T00:00:00.000005Z");
        Assert.IsTrue(OracleQueryReader.Matches(parent, target));
        target["FROM_TS"] = new G4UtcValue { Lexical = "2026-01-01T00:00:00.000003Z" };
        Assert.IsFalse(OracleQueryReader.Matches(parent, target));
        target["FROM_TS"] = new G4UtcValue { Lexical = "2026-01-01T00:00:00.000001Z" };
        target["SITE_ID"] = new G4StringValue { Lexical = "site-b" };
        Assert.IsFalse(OracleQueryReader.Matches(parent, target));
        target["SITE_ID"] = new G4StringValue { Lexical = "site-a" };
        target["JOIN_KEY"] = new G4DecimalValue { Precision = 13, Scale = 2, Lexical = "1.01" };
        Assert.IsFalse(OracleQueryReader.Matches(parent, target));
        target["JOIN_KEY"] = new G4NullValue { Lexical = null, DeclaredType = "decimal" };
        Assert.IsFalse(OracleQueryReader.Matches(parent, target));
        parent["JOIN_KEY"] = target["JOIN_KEY"];
        Assert.IsFalse(OracleQueryReader.Matches(parent, target));
    }

    /// <summary>只有准确原始对象、类型、顺序和 Oracle 元数据才可执行。</summary>
    [TestMethod]
    public void RejectsChangedPhysicalDeclarationsAndCatalogAlgorithm()
    {
        // 固定 Oracle 两表形状，不依赖其它连接器的类型或命名。
        var table = Entity();
        OracleMappingSourceValidator.RequireShape(table);
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.RequireShape(table with { Kind = "VIEW" }));
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.RequireShape(table with { Name = "omq_entity" }));
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.RequireShape(table with { Fields = table.Fields.Reverse().ToArray() }));
        // 精度变化仍在 CLR 能力以内，但不属于获准模板，必须拒绝。
        var different = table.Fields.ToArray();
        different[0] = different[0] with { Precision = 19 };
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.RequireShape(table with { Fields = different }));
        Assert.AreNotEqual(ConnectionApplicationService.CanonicalCatalog([table], "oracle-m2-v1").Fingerprint,
            ConnectionApplicationService.CanonicalCatalog([table], "pg-m1-v1").Fingerprint);
    }

    /// <summary>二十八位系数、尾空格、组合字符、六位时间和空值分别无损保留。</summary>
    [TestMethod]
    public void TypedCellsPreserveExactPrecisionAndText()
    {
        // 日期由无时区源值构造，精确到实际微秒。
        var instant = new DateTime(2026, 11, 19, 12, 0, 0, DateTimeKind.Unspecified).AddTicks(10);
        // 词法边界使用允许的二十八位有符号系数。
        var row = new OracleMappingRow(999999999999999999L, 1m, -9999999999999999999999.999999m, "org-demo", "site-a",
            "ST-1", "e\u0301 ", instant, instant.AddDays(1), instant, instant);
        // 一次实际转换结果同时供映射与查询消费。
        var fields = OracleMappingSourceValidator.Cells(row, Entity());
        Assert.AreEqual("999999999999999999", fields["ROW_ID"].Value);
        Assert.AreEqual("-9999999999999999999999.999999", fields["VAL"].Value);
        Assert.AreEqual("1.0", fields["JOIN_KEY"].Value);
        Assert.AreEqual("e\u0301 ", fields["LABEL"].Value);
        Assert.AreEqual("2026-11-19 12:00:00.000001", fields["EVENT_TS"].Value);
        Assert.IsNull(OracleMappingSourceValidator.Cells(row with { Value = null }, Entity())["VAL"].Value);
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.Cells(row with { JoinKey = 1.01m }, Entity()));
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.Cells(row with { Event = instant.AddTicks(1) }, Entity()));
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.Cells(row with { External = "id " }, Entity()));
        Assert.Throws<SemanticOperationException>(() => OracleMappingSourceValidator.Cells(row with { To = instant }, Entity()));
    }

    /// <summary>构造最小输入行，保持数字类型与声明，与 Oracle 物理行键无关。</summary>
    private static Dictionary<string, G4QueryValue> Row(string number, int precision, int scale, string from, string to) =>
        new(StringComparer.Ordinal)
        {
            ["JOIN_KEY"] = new G4DecimalValue { Precision = precision, Scale = scale, Lexical = number },
            ["ORG_ID"] = new G4StringValue { Lexical = "org-demo" }, ["SITE_ID"] = new G4StringValue { Lexical = "site-a" },
            ["FROM_TS"] = new G4UtcValue { Lexical = from }, ["TO_TS"] = new G4UtcValue { Lexical = to }
        };

    /// <summary>由测试自身依照已冻结 DDL 构造 Oracle 原始目录；生产验证器仍独立核对。</summary>
    private static CatalogObject Entity()
    {
        // 名称和顺序由原始 DDL 固定，不从被测实现读取。
        string[] names = ["ROW_ID", "JOIN_KEY", "VAL", "ORG_ID", "SITE_ID", "EXT_ID", "LABEL", "FROM_TS", "TO_TS", "EVENT_TS", "OBSERVED_TS"];
        return new CatalogObject { Schema = "PRODUCTION", Name = "OMQ_ENTITY", Kind = "TABLE", Fields = names.Select((name, i) => new CatalogField
        {
            Name = name, Ordinal = i + 1, NativeType = i < 3 ? "NUMBER" : i < 7 ? "VARCHAR2" : "TIMESTAMP(6)", Nullable = i is 1 or 2 or 6,
            Precision = i switch { 0 => 18, 1 => 12, 2 => 28, _ => null }, Scale = i switch { 0 => 0, 1 => 1, 2 or > 6 => 6, _ => null },
            OracleMetadata = new OracleColumnMetadata { DataTypeOwner = null, SupportStatus = "SUPPORTED", TimeZoneKind = "NONE",
                CharLength = i is >= 3 and <= 6 ? (i == 6 ? 48 : 32) : null, CharSemantics = i is >= 3 and <= 6 ? "CHAR" : null,
                ByteLength = i is >= 3 and <= 6 ? (i == 6 ? 192 : 128) : null, FractionalSecondsPrecision = i > 6 ? 6 : null }
        }).ToArray() };
    }
}
