using System.Text.Json;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology.Domain;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>显式注册不可变M1历史与M2当前策略，使用精确JSON散列回验。</summary>
public static class SemanticProfile
{
    /// <summary>每次返回独立DTO数组，调用方不能修改全局策略。</summary>
    public static SemanticSupportProfile LegacyM1()
    {
        // 名称顺序严格对应已冻结二十项矩阵。
        string[] names = ["IRI/namespace", "Class", "子类", "对象属性", "数据属性", "domain/range", "annotation/lang", "individual", "equivalentClass", "disjointWith", "inverseOf", "属性特征", "some/all", "hasValue", "cardinality", "交并补", "propertyChain", "imports", "身份公理", "事件时间"];
        // 仅现有基本编辑白名单标BASIC，命名公理声明仅源码可编辑。
        var capabilities = names.Select((name, index) => new SemanticCapabilitySupport
        {
            Id = (index + 1).ToString("D2", System.Globalization.CultureInfo.InvariantCulture),
            Name = name,
            Edit = index is >= 1 and <= 7 ? "BASIC" : "SOURCE",
            Preserve = "EXACT",
            Publish = index < 11 ? "SUPPORTED" : "BLOCKED",
            Validation = index < 11 ? "ASSERTED" : "NOT_SUPPORTED",
            Reason = index < 8 ? "仅已登记的显式命名事实和基本谓词；原文逐字保留，不执行OWL推理。" : index < 11 ? "仅命名IRI对的源码公理声明；不提供结构改写或推理，不声称逻辑一致性。" : index == 19 ? "M1未实现OWL-Time模板；保留源码并阻断发布。" : "源码原样保留；复杂OWL、公理闭包和推理尚未实现，阻断结构改写与发布。"
        }).ToArray();
        // Hash为空时按生成DTO声明顺序序列化；策略版本变化必须新增显式分支。
        var profile = new SemanticSupportProfile { ProfileId = "ontology-platform/g3-m1", Version = "1", Hash = "", ReasoningMode = "ASSERTED_ONLY", Capabilities = capabilities, ComparisonBudget = new GraphComparisonBudget { MaxBlankNodes = 128, MaxSearchNodes = 100000, TimeoutMilliseconds = 5000 } };
        return profile with { Hash = OntologyRules.Hash(JsonSerializer.Serialize(profile)) };
    }

    /// <summary>当前M2仅扩展命名公理的结构编辑能力，原发布语义不变。</summary>
    public static SemanticSupportProfile LegacyM2()
    {
        // 独立构造历史DTO，防止调用方改变共享策略或历史散列。
        var legacy = LegacyM1();
        // 仅09至11从SOURCE升级为BASIC；01的IRI命名空间仍走源码保存。
        var capabilities = legacy.Capabilities.Select(item => item.Id is "09" or "10" or "11"
            ? item with { Edit = "BASIC", Reason = "仅两端显式类型匹配的命名IRI公理支持精确结构改写；不执行推理，不声称逻辑一致性。" }
            : item).ToArray();
        // Hash空值序列化顺序与历史算法一致，版本显式升级而不覆盖v1。
        var profile = legacy with { Version = "2", Hash = "", Capabilities = capabilities };
        return profile with { Hash = OntologyRules.Hash(JsonSerializer.Serialize(profile)) };
    }

    /// <summary>v3在原二十项后登记SKOS治理和Synthetic单位引用，不执行换算或OWL推理。</summary>
    public static SemanticSupportProfile Current()
    {
        // 原v2全部DTO字段保持不变，仅新策略新增两项显式能力。
        var legacy = LegacyM2();
        // 本轮两项能力使用平台治理而不是推理或换算宣称。
        var capabilities = legacy.Capabilities.Concat(new[] { "SKOS术语与标准治理", "Synthetic单位与量纲引用" }.Select((name, index) => new SemanticCapabilitySupport { Id = (21 + index).ToString(System.Globalization.CultureInfo.InvariantCulture), Name = name, Edit = "BASIC", Preserve = "EXACT", Publish = "SUPPORTED", Validation = "ASSERTED", Reason = "仅有界显式事实与平台域治理；保留来源版本，不执行OWL推理或通用单位换算。" })).ToArray();
        // 按原DTO声明顺序散列，旧profile从不重写。
        var profile = legacy with { Version = "3", Hash = "", Capabilities = capabilities };
        return profile with { Hash = OntologyRules.Hash(JsonSerializer.Serialize(profile)) };
    }

    /// <summary>将assessment自己的hash置空后计算完整事实散列。</summary>
    public static string AssessmentHash(SemanticAssessment assessment) => OntologyRules.Hash(JsonSerializer.Serialize(assessment with { AssessmentHash = "" }));

    /// <summary>历史V2清单只接受显式登记的版本和精确散列，不自动升级。</summary>
    internal static bool Matches(PublicationSemantics semantics)
    {
        // 每个版本保留自己的完整内容，篡改版本或散列均不能回验。
        var profile = semantics.ProfileVersion switch { "1" => LegacyM1(), "2" => LegacyM2(), "3" => Current(), _ => null };
        return profile is not null && semantics.ProfileHash == profile.Hash;
    }
}
