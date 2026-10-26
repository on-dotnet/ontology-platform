using System.Reflection;
using System.Text.Json;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.SemanticQuery;
namespace OntologyPlatform.QueryTests;
/// <summary>验证真实模块登记和严格输出Schema，未实现时必须失败。</summary>
[TestClass]
public sealed class RegistryTests
{
    /// <summary>登记入口必须存在，且注册共享Gateway与证据合同。</summary>
    [TestMethod]
    public void ModuleRegistersSharedContracts()
    {
        // 反射只用于红例发现入口，不提供任何替身实现。
        var assembly = Assembly.Load("OntologyPlatform.Modules.SemanticQuery");
        // 唯一模块注册方法由实际产品程序集提供。
        var method = assembly.GetTypes().SelectMany(type => type.GetMethods()).SingleOrDefault(value => value.Name == "AddSemanticQueryModule");
        Assert.IsNotNull(method, "正式Query模块尚未实现");
        // 无需连接外部资源即可验证注册合同。
        var services = new ServiceCollection();
        method.Invoke(null, [services, new ConfigurationBuilder().Build()]);
        Assert.IsTrue(services.Any(value => value.ServiceType == typeof(ISemanticGateway)));
        Assert.IsTrue(services.Any(value => value.ServiceType == typeof(IEvidenceService)));
    }

    /// <summary>输出Schema保留全部真实定义、联合、null和严格未知字段边界。</summary>
    [TestMethod]
    public void SchemaUsesCompleteGeneratedClosureAndStableVersions()
    {
        // 两个新registry模拟独立服务实例。
        var first = new CapabilityRegistry().Read();
        // 版本来自稳定精确Schema，不受实例创建时间影响。
        var second = new CapabilityRegistry().Read();
        Assert.HasCount(3, first);
        Assert.AreEqual(JsonSerializer.Serialize(first), JsonSerializer.Serialize(second));
        foreach (var capability in first)
        {
            Assert.HasCount(64, capability.Version);
            Assert.AreEqual(100, capability.InputSchema.Properties.Single(value => value.Name == "timeoutMs").Minimum);
            // 原始Schema必须有唯一完整结果及其嵌套联合。
            var definitions = capability.OutputSchema.GetProperty("$defs");
            Assert.IsTrue(definitions.TryGetProperty("SemanticQueryResult", out _));
            Assert.IsTrue(definitions.GetProperty("SemanticDatum").TryGetProperty("oneOf", out _));
            Assert.IsFalse(definitions.GetProperty("EvidenceRef").GetProperty("additionalProperties").GetBoolean());
            Assert.IsFalse(capability.OutputSchema.GetRawText().Contains("#/components/", StringComparison.Ordinal));
        }
    }
}
