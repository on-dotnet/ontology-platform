using System.Security.Cryptography;
using System.Text;

namespace OntologyPlatform.Modules.Ontology.Domain;

/// <summary>不依赖传输、存储或RDF运行时的草稿确定性规则。</summary>
public static class OntologyRules
{
    /// <summary>对完整UTF8源码计算小写SHA256，不归一化空白或字面量。</summary>
    /// <param name="source">原始字符串。</param>
    /// <returns>64位小写十六进制。</returns>
    public static string Hash(string source) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(source)));

    /// <summary>非空完整资源范围必须属于可信主体的所有厂区。</summary>
    /// <param name="organization">资源组织。</param>
    /// <param name="sites">资源完整厂区。</param>
    /// <param name="actorOrganization">可信组织。</param>
    /// <param name="actorSites">可信厂区。</param>
    /// <returns>是否完整授权。</returns>
    public static bool Covers(string organization, string[] sites, string actorOrganization, string[] actorSites) =>
        !string.IsNullOrWhiteSpace(organization) && organization == actorOrganization && sites.Length is >= 1 and <= 16 &&
        sites.All(site => !string.IsNullOrWhiteSpace(site) && actorSites.Contains(site, StringComparer.Ordinal));

    /// <summary>检查来源字符字节预算，避免大请求绕过RDF数量限制。</summary>
    /// <param name="sources">四类完整源码，可选词汇可以为空。</param>
    /// <returns>每源256KiB且合计1MiB时为真。</returns>
    public static bool WithinSourceBudget(params string?[] sources) =>
        sources.All(source => source is null || Encoding.UTF8.GetByteCount(source) <= 256 * 1024) &&
        sources.Sum(source => source is null ? 0 : Encoding.UTF8.GetByteCount(source)) <= 1024 * 1024;
}
