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
            ["Semantics:ValidationOrigin"] = origin + "/validation/",
            ["Semantics:PublishedOrigin"] = origin + "/ontology/"
        }).Build();
        // 真实工厂禁用重定向，任何外部URL不可能被跟随。
        var services = new ServiceCollection();
        services.AddHttpClient("ontology-jena").ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false });
        return new JenaSemanticRuntime(services.BuildServiceProvider().GetRequiredService<IHttpClientFactory>(), config, TimeProvider.System);
    }

    /// <summary>从显式夹具加载五类合成样例；未注入为未运行，已配置但读取失败仍为测试失败。</summary>
    internal static SourceBundle Sources()
    {
        // 脚本显式传入源码目录，避免依赖测试工作目录偶然性。
        var root = Environment.GetEnvironmentVariable("G2_SEM_SAMPLES");
        if (root is null) Assert.Inconclusive("NOT_RUN: 需要semantic-roundtrip.py显式提供合成样例目录。");
        return new SourceBundle
        {
            OntologyTurtle = File.ReadAllText(Path.Combine(root, "ontology.ttl")),
            ShapesTurtle = File.ReadAllText(Path.Combine(root, "shapes.ttl")),
            VocabularyTurtle = File.ReadAllText(Path.Combine(root, "vocabulary.ttl")),
            DataTurtle = File.ReadAllText(Path.Combine(root, "data.ttl"))
        };
    }

    /// <summary>保留真实HTTP传输，只在指定阶段注入可取消延迟以验证并发/超时。</summary>
    internal static JenaSemanticRuntime RuntimeWithGate(Func<HttpRequestMessage, CancellationToken, Task> gate)
    {
        // 随机回环地址仍由同一临时真实Jena提供。
        var origin = Environment.GetEnvironmentVariable("G2_SEM_JENA_ORIGIN");
        if (origin is null) Assert.Inconclusive("NOT_RUN: 缺少隔离Jena。");
        // 所有响应都来自实际引擎，gate不提供任何模拟RDF或SHACL结果。
        var config = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["Semantics:ValidationOrigin"] = origin + "/validation/",
            ["Semantics:PublishedOrigin"] = origin + "/ontology/"
        }).Build();
        return new JenaSemanticRuntime(new TimingFactory(gate), config, TimeProvider.System);
    }

    /// <summary>为真实引擎连接增加确定性时序控制，绝不替换业务响应。</summary>
    private sealed class TimingFactory : IHttpClientFactory
    {
        /// <summary>发送前时序钩子。</summary>
        private readonly Func<HttpRequestMessage, CancellationToken, Task> gate;

        /// <summary>保存当前测试的时序钩子。</summary>
        public TimingFactory(Func<HttpRequestMessage, CancellationToken, Task> gate)
        {
            this.gate = gate;
        }

        /// <summary>返回禁用重定向的真实网络客户端。</summary>
        public HttpClient CreateClient(string name) => new(new TimingHandler(gate) { InnerHandler = new HttpClientHandler { AllowAutoRedirect = false, UseProxy = false } });
    }

    /// <summary>延迟真实请求，取消仍传到实际传输和清理。</summary>
    private sealed class TimingHandler : DelegatingHandler
    {
        /// <summary>发送前时序钩子。</summary>
        private readonly Func<HttpRequestMessage, CancellationToken, Task> gate;

        /// <summary>保存当前测试的时序钩子。</summary>
        public TimingHandler(Func<HttpRequestMessage, CancellationToken, Task> gate)
        {
            this.gate = gate;
        }

        /// <summary>执行时序控制后直接转发真实请求和真实响应。</summary>
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            await gate(request, cancellationToken);
            return await base.SendAsync(request, cancellationToken);
        }
    }
}
