using System.Text.Json;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology.Domain;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>M1不可变策略内容与精确JSON散列规则。</summary>
public static class SemanticProfile
{
    /// <summary>每次返回独立DTO数组，调用方不能修改全局策略。</summary>
    public static SemanticSupportProfile Current()
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

    /// <summary>将assessment自己的hash置空后计算完整事实散列。</summary>
    public static string AssessmentHash(SemanticAssessment assessment) => OntologyRules.Hash(JsonSerializer.Serialize(assessment with { AssessmentHash = "" }));

    /// <summary>历史V2固定使用本轮策略，不允许自动升级到未来当前策略。</summary>
    internal static bool Matches(PublicationSemantics semantics)
    {
        // 本轮只有明确登记的版本1；未来版本须保留该历史实现。
        var profile = Current();
        return semantics.ProfileVersion == profile.Version && semantics.ProfileHash == profile.Hash;
    }
}
