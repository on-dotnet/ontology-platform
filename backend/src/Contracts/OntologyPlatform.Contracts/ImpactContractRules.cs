using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace OntologyPlatform.Contracts;

/// <summary>冻结M4影响报告的纯内容身份，不依赖数据库、HTTP或推理引擎。</summary>
public static class ImpactContractRules
{
    /// <summary>显式资产影响执行器，算法或覆盖语义变化必须升级。</summary>
    public const string ExecutorVersion = "ontology-platform/g3-m4-impact/1";

    /// <summary>图预算及报告覆盖预算共同参与稳定输入身份。</summary>
    public const string BudgetIdentity = "graph128-search100000-ms5000-triples5000-report256-bytes8388608/1";

    /// <summary>只接受小写SHA256，不把任意标签或未知值当精确散列。</summary>
    /// <param name="value">待验证的合同散列。</param>
    /// <returns>满足准确编码时为真。</returns>
    public static bool IsHash(string? value) => value is { Length: 64 } && value.All(char.IsAsciiHexDigitLower);

    /// <summary>在昂贵比较前固定全部不可变输入，排除命令、时间和运行遥测。</summary>
    /// <param name="diff">服务器授权恢复的准确版本及四源身份。</param>
    /// <param name="kind">明确普通版本对或首次发布模式。</param>
    /// <param name="semantics">真实目标评估引用，缺席时不伪造。</param>
    /// <param name="profileVersion">准确策略版本。</param>
    /// <param name="profileHash">准确策略散列。</param>
    /// <returns>同一固定输入的SHA256身份。</returns>
    public static string InputFingerprint(VersionDiff diff, ImpactBaselineKind kind, PublicationSemantics? semantics, string profileVersion, string profileHash) =>
        HashDiff(diff, kind, new
        {
            SchemaVersion = 1,
            ExecutorVersion,
            BudgetIdentity,
            diff.AssetId,
            Scope = Scope(diff.Scope),
            diff.From,
            diff.To,
            diff.BaseHashes,
            diff.TargetHashes,
            diff.BaseManifestHash,
            diff.TargetManifestHash,
            BaselineKind = kind,
            TargetSemantics = semantics,
            ProfileVersion = profileVersion,
            ProfileHash = profileHash
        });

    /// <summary>对排序后的完整语义内容散列，首次ID/时效由持久envelope与审批另行绑定。</summary>
    /// <param name="report">不可变报告内容，调用过程不修改输入数组。</param>
    /// <returns>排除自身、时间与比较遥测后的准确内容散列。</returns>
    public static string CanonicalHash(ImpactReport report) => HashReport(report, new
    {
        report.SchemaVersion,
        report.InputFingerprint,
        report.ExecutorVersion,
        report.BudgetIdentity,
        report.BaselineKind,
        Diff = report.Diff with
        {
            Scope = Scope(report.Diff.Scope),
            Sources = report.Diff.Sources.OrderBy(source => source.SourceId, StringComparer.Ordinal).Select(source => source with
            {
                Graph = source.Graph with { ElapsedMilliseconds = 0, VisitedNodes = 0 },
                AddedTriples = Ordered(source.AddedTriples),
                RemovedTriples = Ordered(source.RemovedTriples)
            }).ToArray()
        },
        report.ProfileVersion,
        report.ProfileHash,
        report.TargetSemantics,
        ChangedIris = Strings(report.ChangedIris),
        AssetReferences = Strings(report.AssetReferences),
        KnownImpacts = Conclusions(report.KnownImpacts),
        Blockers = Conclusions(report.Blockers),
        UnknownCoverage = Conclusions(report.UnknownCoverage),
        report.PublishEligible
    });

    /// <summary>验证每源UTF8、四槽位和bundle一致性，不能把声称的hash当真实性。</summary>
    /// <param name="diff">从服务器固定版本恢复的完整差异。</param>
    public static void ValidateDiffIdentity(VersionDiff diff)
    {
        if (diff.Sources.Length != 4 || !diff.Sources.Select(source => source.SourceId).Order(StringComparer.Ordinal)
            .SequenceEqual(new[] { "data", "ontology", "shapes", "vocabulary" }, StringComparer.Ordinal))
            throw new JsonException("差异必须恰有四个唯一来源槽位。");
        // 每个独立来源槽位都须先通过原文与delta一致性检查。
        foreach (var source in diff.Sources) ValidateSourceIdentity(source);
        if (diff.BaseHashes != Hashes(diff.Sources, false) || diff.TargetHashes != Hashes(diff.Sources, true))
            throw new JsonException("四源槽位或bundle散列与原文不一致。");
        if (diff.From == diff.To && diff.BaseHashes != diff.TargetHashes)
            throw new JsonException("相同固定版本不能对应不同源内容。");
        if (diff.From.Kind == VersionRefKind.Release ? !IsHash(diff.BaseManifestHash) : diff.BaseManifestHash is not null)
            throw new JsonException("基础正式版本的清单身份不一致。");
        if (diff.To.Kind == VersionRefKind.Release ? !IsHash(diff.TargetManifestHash) : diff.TargetManifestHash is not null)
            throw new JsonException("目标正式版本的清单身份不一致。");
    }

    /// <summary>单源原文和hash逐字节一致，可信delta不得含不稳定空白节点。</summary>
    /// <param name="source">精确来源槽位。</param>
    public static void ValidateSourceIdentity(SourceVersionDiff source)
    {
        if (source.SourceId is not ("ontology" or "shapes" or "vocabulary" or "data")
            || source.SourceId != "vocabulary" && (source.BaseText is null || source.TargetText is null)
            || source.BaseHash != TextHash(source.BaseText) || source.TargetHash != TextHash(source.TargetText)
            || source.SourceChanged != !string.Equals(source.BaseText, source.TargetText, StringComparison.Ordinal)
            || source.BaseTripleCount < 0 || source.TargetTripleCount < 0
            || source.AddedTriples.Concat(source.RemovedTriples).Any(triple => !Ground(triple))
            || source.Graph.Status == GraphComparisonStatus.Equivalent
                && (source.TripleDeltaStatus != TripleDeltaStatus.Equivalent || source.AddedTriples.Length > 0 || source.RemovedTriples.Length > 0)
            || source.Graph.Status == GraphComparisonStatus.Indeterminate && source.TripleDeltaStatus != TripleDeltaStatus.Indeterminate
            || source.TripleDeltaStatus == TripleDeltaStatus.Equivalent && source.Graph.Status != GraphComparisonStatus.Equivalent
            || source.Graph.Status == GraphComparisonStatus.Different && source.TripleDeltaStatus == TripleDeltaStatus.Exact
                && source.AddedTriples.Length == 0 && source.RemovedTriples.Length == 0)
            throw new JsonException("来源原文、散列、变化位或可信地面delta不一致。");
    }

    /// <summary>证据只使用稳定命名定位；blank细节保留原文，不冒充可靠证据项。</summary>
    /// <param name="evidence">结论引用的明确版本与源。</param>
    public static void ValidateEvidence(ImpactEvidenceReference evidence)
    {
        if (evidence.SourceId is not ("ontology" or "shapes" or "vocabulary" or "data" or "bundle")
            || !IsHash(evidence.SourceHash) || evidence.Triple is not null && !Ground(evidence.Triple)
            || evidence.FocusIri is not null && !NamedIri(evidence.FocusIri)
            || evidence.Path is not null && !NamedIri(evidence.Path)
            || evidence.Line is <= 0 || evidence.Column is <= 0)
            throw new JsonException("证据来源或稳定命名定位无效。");
    }

    /// <summary>canonical前检查输入与每项结论的真实源hash绑定，不代替RIOT语义解析。</summary>
    /// <param name="report">服务器构造或持久读回的报告。</param>
    public static void ValidateReportIdentity(ImpactReport report)
    {
        ValidateDiffIdentity(report.Diff);
        if (report.SchemaVersion != 1 || report.ExecutorVersion != ExecutorVersion || report.BudgetIdentity != BudgetIdentity
            || !IsHash(report.ProfileHash) || report.TargetSemantics is not null
                && (report.TargetSemantics.ProfileVersion != report.ProfileVersion || report.TargetSemantics.ProfileHash != report.ProfileHash)
            || report.InputFingerprint != InputFingerprint(report.Diff, report.BaselineKind, report.TargetSemantics, report.ProfileVersion, report.ProfileHash))
            throw new JsonException("报告固定输入或执行器策略身份不一致。");
        // 三类结论逐项核验，不能让未知或阻断项缺少真实证据。
        foreach (var conclusion in report.KnownImpacts.Concat(report.Blockers).Concat(report.UnknownCoverage))
        {
            if (conclusion.Evidence.Length == 0) throw new JsonException("每个影响结论必须有真实源或bundle证据。");
            // 每项证据只能绑定本次固定基础或目标来源。
            foreach (var evidence in conclusion.Evidence)
            {
                ValidateEvidence(evidence);
                // 删除结论绑定基础源，新增结论绑定目标源，不推断另一版本。
                var hashes = evidence.Version == report.Diff.From ? report.Diff.BaseHashes
                    : evidence.Version == report.Diff.To ? report.Diff.TargetHashes : null;
                if (hashes is null || evidence.SourceHash != SourceHash(hashes, evidence.SourceId))
                    throw new JsonException("结论证据未绑定报告固定版本的真实来源hash。");
            }
        }
        if (report.Blockers.Any(item => !item.Blocking) || report.PublishEligible
            && (report.TargetSemantics is null || report.Diff.To.Kind != VersionRefKind.Draft || report.Blockers.Length > 0 || report.UnknownCoverage.Any(item => item.Blocking)
                || report.Diff.Sources.Any(source => source.Graph.Status == GraphComparisonStatus.Indeterminate || source.TripleDeltaStatus == TripleDeltaStatus.Indeterminate)))
            throw new JsonException("技术资格不能覆盖阻断或实际未知影响。");
    }

    /// <summary>先核验输入再算输入身份，避免唯一输入查询复用伪造hash。</summary>
    private static string HashDiff<T>(VersionDiff diff, ImpactBaselineKind kind, T value)
    {
        ValidateDiffIdentity(diff);
        if (kind == ImpactBaselineKind.Initial && (diff.From != diff.To || diff.To.Kind != VersionRefKind.Draft))
            throw new JsonException("INITIAL必须明确自比同一固定草稿修订。");
        return Hash(value);
    }

    /// <summary>先核验报告内容和引用再算canonical hash，拒绝不稳定blank与未绑定证据。</summary>
    private static string HashReport<T>(ImpactReport report, T value)
    {
        ValidateReportIdentity(report);
        return Hash(value);
    }

    /// <summary>仅命名主体及非blank客体组成可可靠比较的地面三元组。</summary>
    private static bool Ground(RdfTriple triple) => triple.Subject.Kind == RdfTermKind.Iri && NamedIri(triple.Subject.Value)
        && NamedIri(triple.Predicate) && (triple.Object.Kind == RdfTermKind.Iri && NamedIri(triple.Object.Value)
            || triple.Object.Kind == RdfTermKind.Literal);

    /// <summary>命名定位必须为绝对IRI，只验证而不改变原始Unicode、大小写或转义。</summary>
    private static bool NamedIri(string value) => !string.IsNullOrEmpty(value) && !value.Any(char.IsWhiteSpace)
        && Uri.TryCreate(value, UriKind.Absolute, out _);

    /// <summary>根据固定源名读取准确hash，不把缺词汇当空文件。</summary>
    private static string? SourceHash(SourceHashes hashes, string source) => source switch
    {
        "ontology" => hashes.OntologyHash,
        "shapes" => hashes.ShapesHash,
        "vocabulary" => hashes.VocabularyHash,
        "data" => hashes.DataHash,
        "bundle" => hashes.BundleHash,
        _ => null
    };

    /// <summary>从四个已校验槽位重算原合同顺序的组合身份。</summary>
    private static SourceHashes Hashes(SourceVersionDiff[] sources, bool target)
    {
        // 按来源名索引，不依赖调用方数组枚举顺序。
        var values = sources.ToDictionary(source => source.SourceId, source => target ? source.TargetHash : source.BaseHash, StringComparer.Ordinal);
        return new SourceHashes { OntologyHash = values["ontology"]!, ShapesHash = values["shapes"]!, VocabularyHash = values["vocabulary"], DataHash = values["data"]!,
            BundleHash = TextHash(string.Join('\n', values["ontology"], values["shapes"], values["vocabulary"] ?? "absent", values["data"]))! };
    }

    /// <summary>原始UTF8身份不归一化换行、BOM或Unicode。</summary>
    private static string? TextHash(string? value) => value is null ? null : Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(value)));

    /// <summary>完整范围采用明确ordinal排序，不依赖机器文化或首厂区。</summary>
    private static ResourceScope Scope(ResourceScope scope) => scope with { SiteIds = Strings(scope.SiteIds) };

    /// <summary>命名IRI及引用按原始字符串去重排序，不清洗大小写或词法。</summary>
    private static string[] Strings(IEnumerable<string> values) => values.Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray();

    /// <summary>完整RdfTerm及证据按稳定JSON键去重排序，语言和datatype不省略。</summary>
    private static T[] Ordered<T>(IEnumerable<T> values) => values.DistinctBy(value => JsonSerializer.Serialize(value), StringComparer.Ordinal)
        .OrderBy(value => JsonSerializer.Serialize(value), StringComparer.Ordinal).ToArray();

    /// <summary>结论内的证据和引用同样排序，避免枚举顺序影响内容身份。</summary>
    private static ImpactConclusion[] Conclusions(IEnumerable<ImpactConclusion> values) => Ordered(values.Select(value => value with
    {
        AffectedIris = Strings(value.AffectedIris),
        AssetReferences = Strings(value.AssetReferences),
        Evidence = Ordered(value.Evidence)
    }));

    /// <summary>锁定SDK的默认JSON字节顺序及UTF8共同构成已版本化canonical算法。</summary>
    private static string Hash<T>(T value) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(value))));
}
