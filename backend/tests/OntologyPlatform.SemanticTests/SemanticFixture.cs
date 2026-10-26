using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SemanticTests;

/// <summary>显式连接脚本创建的隔离临时Jena，不读取历史运行环境。</summary>
internal static class SemanticFixture
{
    /// <summary>构造真实运行时；缺少隔离fixture为明确未运行。</summary>
    internal static JenaSemanticRuntime Runtime()
    {
        // 测试脚本只向当前进程提供随机回环URL，不含认证材料。
        var origin = Environment.GetEnvironmentVariable("G2_SEM_JENA_ORIGIN");
        if (origin is null) Assert.Inconclusive("NOT_RUN: 需要semantic-roundtrip.py创建的真实隔离Jena。");
        // 此容器配置分别提供内存验证及临时TDB2正式dataset。
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["Semantics:ValidationOrigin"] = origin + "/validation/", ["Semantics:PublishedOrigin"] = origin + "/ontology/"
        }).Build();
        // 真实工厂禁用重定向，任何外部URL不可能被跟随。
        var services = new ServiceCollection();
        services.AddHttpClient("ontology-jena").ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false });
        return new JenaSemanticRuntime(services.BuildServiceProvider().GetRequiredService<IHttpClientFactory>(), config, TimeProvider.System);
    }

    /// <summary>从版本化源码加载五类合成样例。</summary>
    internal static SourceBundle Sources()
    {
        // 脚本显式传入源码目录，避免依赖测试工作目录偶然性。
        var root = Environment.GetEnvironmentVariable("G2_SEM_SAMPLES") ?? throw new InvalidOperationException("缺少样例目录。");
        return new SourceBundle
        {
            OntologyTurtle = File.ReadAllText(Path.Combine(root, "ontology.ttl")),
            ShapesTurtle = File.ReadAllText(Path.Combine(root, "shapes.ttl")),
            VocabularyTurtle = File.ReadAllText(Path.Combine(root, "vocabulary.ttl")),
            DataTurtle = File.ReadAllText(Path.Combine(root, "data.ttl"))
        };
    }
}
