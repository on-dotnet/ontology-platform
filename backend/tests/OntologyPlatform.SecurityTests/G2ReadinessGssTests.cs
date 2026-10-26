using System.Data.Common;
using System.Diagnostics;
using System.Reflection;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;
using OntologyPlatform.Api.G2;
using OntologyPlatform.Modules.Governance;

namespace OntologyPlatform.SecurityTests;

/// <summary>在独立子进程验证真实健康options的GSS有效模式，不修改并行测试进程的环境。</summary>
[TestClass]
public sealed class G2ReadinessGssTests
{
    /// <summary>连接串显式值优先于环境，其次使用驱动默认；有效Require不能被健康优化降级。</summary>
    /// <returns>逐子进程覆盖配置优先级及实际驱动解析结果。</returns>
    [TestMethod]
    public async Task HealthOptionsPreserveEffectiveGssRequirement()
    {
        // 每种进程配置均不含网络凭证；显式Prefer仍允许原有健康优化。
        var cases = new[]
        {
            (Name: "environment-require", Environment: "require", Setting: "", Before: GssEncryptionMode.Require, After: GssEncryptionMode.Require),
            (Name: "explicit-disable", Environment: "require", Setting: ";GSS Encryption Mode=Disable", Before: GssEncryptionMode.Disable, After: GssEncryptionMode.Disable),
            (Name: "explicit-require", Environment: "disable", Setting: ";GSS Encryption Mode=Require", Before: GssEncryptionMode.Require, After: GssEncryptionMode.Require),
            (Name: "explicit-prefer", Environment: "require", Setting: ";GSS Encryption Mode=Prefer", Before: GssEncryptionMode.Prefer, After: GssEncryptionMode.Disable),
            (Name: "environment-prefer", Environment: "prefer", Setting: "", Before: GssEncryptionMode.Prefer, After: GssEncryptionMode.Disable),
            (Name: "environment-invalid", Environment: "invalid-mode", Setting: "", Before: GssEncryptionMode.Prefer, After: GssEncryptionMode.Disable),
            (Name: "default-prefer", Environment: (string?)null, Setting: "", Before: GssEncryptionMode.Prefer, After: GssEncryptionMode.Disable),
            (Name: "canonical-alias", Environment: "disable", Setting: ";GssEncryptionMode=Require", Before: GssEncryptionMode.Require, After: GssEncryptionMode.Require)
        };
        // 只有专用子进程标记选择直接检查；父进程从不写PGGSSENCMODE。
        var selected = Environment.GetEnvironmentVariable("ONTOLOGY_HOST_GSS_CASE");
        if (selected is not null)
        {
            // 子进程的环境在Npgsql初始化前已经冻结，避免静态缓存和并行污染。
            var item = cases.Single(value => value.Name == selected);
            // 观察真实Npgsql连接入口，阻止任何Kerberos或数据库网络访问。
            var observer = new OptionsObserver();
            // TLS要求保持VerifyFull，GSS环境变化不能顺带改动它。
            var original = "Host=127.0.0.1;Database=gss_options_fixture;SSL Mode=VerifyFull" + item.Setting;
            // 每个子进程有独立的服务提供程序及模块options。
            var services = new ServiceCollection();
            services.AddDbContext<GovernanceDbContext>(options => options.UseNpgsql(original).AddInterceptors(observer));
            // 只消费第一Governance连接探针，不冒充完整依赖健康。
            await using var provider = services.BuildServiceProvider();
            // 保持与生产相同请求作用域，健康副本不能改写原上下文。
            await using var scope = provider.CreateAsyncScope();
            Assert.AreEqual(item.Before, DriverMode(new NpgsqlConnectionStringBuilder(original)));
            Assert.IsFalse(await G2Readiness.CheckAsync(scope.ServiceProvider, CancellationToken.None));
            Assert.IsNotNull(observer.Seen);
            Assert.AreEqual(item.After, DriverMode(observer.Seen));
            Assert.AreEqual(SslMode.VerifyFull, observer.Seen.SslMode);
            Assert.AreEqual(original, scope.ServiceProvider.GetRequiredService<GovernanceDbContext>().Database.GetConnectionString());
            Assert.AreEqual(item.Environment, Environment.GetEnvironmentVariable("PGGSSENCMODE"));
            Assert.AreEqual(1, observer.Seen.Timeout);
            Assert.AreEqual(-1, observer.Seen.CancellationTimeout);
            Assert.IsFalse(observer.Seen.Pooling);
            Console.WriteLine($"GSS case={item.Name}; effectiveBefore={item.Before}; effectiveHealth={DriverMode(observer.Seen)}; TLS=VerifyFull; originalOptionsUnchanged=True");
            return;
        }
        // 记录父进程原环境，子进程返回后必须完全不变。
        var parentEnvironment = Environment.GetEnvironmentVariable("PGGSSENCMODE");
        // 子进程仅运行同一条测试，标记分支阻止递归启动。
        foreach (var item in cases)
        {
            // 不经shell传递参数，直接调用当前已构建测试程序集。
            var start = new ProcessStartInfo("dotnet") { RedirectStandardOutput = true, RedirectStandardError = true };
            start.ArgumentList.Add(typeof(G2ReadinessGssTests).Assembly.Location);
            start.ArgumentList.Add("--filter");
            start.ArgumentList.Add("FullyQualifiedName~G2ReadinessGssTests.HealthOptionsPreserveEffectiveGssRequirement");
            start.ArgumentList.Add("--output");
            start.ArgumentList.Add("Detailed");
            start.Environment["ONTOLOGY_HOST_GSS_CASE"] = item.Name;
            if (item.Environment is null) start.Environment.Remove("PGGSSENCMODE");
            else start.Environment["PGGSSENCMODE"] = item.Environment;
            // 本测试拥有并完整等待子进程，不留下环境变更或后台任务。
            using var process = Process.Start(start)!;
            // 同时排空管道，内容仅含无凭证协议和固定枚举。
            var output = process.StandardOutput.ReadToEndAsync();
            // 错误管道同样完整接收，测试失败保留真实断言信息。
            var error = process.StandardError.ReadToEndAsync();
            await process.WaitForExitAsync();
            Console.WriteLine(await output);
            Console.WriteLine(await error);
            Assert.AreEqual(0, process.ExitCode, $"独立GSS用例{item.Name}失败。");
            Console.WriteLine($"Isolated GSS case={item.Name}; expectedBefore={item.Before}; expectedHealth={item.After}; passed=True");
        }
        Assert.AreEqual(parentEnvironment, Environment.GetEnvironmentVariable("PGGSSENCMODE"));
    }

    /// <summary>调用锁定Npgsql程序集的真实有效模式解析器，避免测试复制生产优先级算法。</summary>
    /// <param name="settings">实际连接options或未修改的原业务配置。</param>
    /// <returns>驱动按显式连接串、环境、默认顺序取得的实际模式。</returns>
    private static GssEncryptionMode DriverMode(NpgsqlConnectionStringBuilder settings)
    {
        // 反射只用于测试锁定驱动的纯内存函数，不进入产品实现或网络认证。
        var resolver = typeof(NpgsqlConnection).Assembly.GetType("Npgsql.Internal.NpgsqlConnector")!
            .GetMethod("GetGssEncMode", BindingFlags.Static | BindingFlags.NonPublic)!;
        return (GssEncryptionMode)resolver.Invoke(null, [settings])!;
    }

    /// <summary>在连接打开前截取生产克隆的options并等待预算取消，不模拟驱动解析结果。</summary>
    private sealed class OptionsObserver : DbConnectionInterceptor
    {
        /// <summary>生产传入真实连接的参数副本，不包含密码。</summary>
        internal NpgsqlConnectionStringBuilder? Seen { get; private set; }

        /// <summary>阻止本测试建立网络连接，直接观察生产配置并沿用真实预算退出。</summary>
        /// <param name="connection">生产准备打开的Npgsql连接。</param>
        /// <param name="eventData">当前EF连接上下文。</param>
        /// <param name="result">原生连接拦截结果。</param>
        /// <param name="cancellationToken">生产预算令牌。</param>
        /// <returns>预算取消时退出，不返回假健康数据。</returns>
        public override async ValueTask<InterceptionResult> ConnectionOpeningAsync(DbConnection connection, ConnectionEventData eventData, InterceptionResult result, CancellationToken cancellationToken = default)
        {
            Seen = new NpgsqlConnectionStringBuilder(connection.ConnectionString);
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
            return result;
        }
    }
}
