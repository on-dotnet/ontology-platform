using System.Data.Common;
using System.Diagnostics;
using System.Net;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Builder;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using OntologyPlatform.Api;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Modules.Governance;

namespace OntologyPlatform.SecurityTests;

/// <summary>用真实健康路由和EF连接拦截器检验前置Governance访问同样受整体预算约束。</summary>
[TestClass]
public sealed class G2ReadinessTests
{
    /// <summary>首个Governance连接阻塞时，G2应在两秒预算内结束并返回标准503。</summary>
    /// <returns>真实Kestrel健康请求验证任务。</returns>
    [TestMethod]
    public async Task G2BudgetIncludesFirstGovernanceConnection()
    {
        // 拦截器只模拟连接等待，不使用外部PG或历史认证材料。
        var blocker = new BlockingConnection();
        // G2启用时预算必须从Governance之前开始。
        await using var app = BuildApp(true, blocker);
        await app.StartAsync();
        // 客户端保险期限大于预算；旧实现直到保险取消才结束。
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()), Timeout = TimeSpan.FromSeconds(5) };
        client.DefaultRequestHeaders.Add("X-Health-Key", "synthetic-readiness-test");
        // 计时包含真实HTTP、路由和EF连接等待。
        var elapsed = Stopwatch.StartNew();
        // 真实响应必须在预算耗尽时形成标准依赖不可用结果。
        using var response = await client.GetAsync("/health/ready");
        Assert.AreEqual(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        Assert.IsTrue(elapsed.Elapsed >= TimeSpan.FromSeconds(1.5) && elapsed.Elapsed < TimeSpan.FromSeconds(4), $"实际等待{elapsed.Elapsed.TotalSeconds:F3}秒。");
        Assert.IsTrue(blocker.Cancelled);
        Console.WriteLine($"Synthetic blocked Governance: elapsedMs={elapsed.Elapsed.TotalMilliseconds:F0}; status={(int)response.StatusCode}; cancelled={blocker.Cancelled}");
        // 机器码区分依赖失败和内部错误，不暴露连接信息。
        var problem = JsonNode.Parse(await response.Content.ReadAsStringAsync())!;
        Assert.AreEqual("g2_dependency_unavailable", problem["code"]!.GetValue<string>());
    }

    /// <summary>调用方取消不能被两秒预算吞掉；禁用G2仍保持原健康路径传播取消。</summary>
    /// <param name="enabled">是否启用G2预算。</param>
    /// <returns>真实HTTP调用方取消传播验证任务。</returns>
    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public async Task CallerCancellationStillReachesGovernance(bool enabled)
    {
        // 每个测试使用独立等待器，避免并发串扰。
        var blocker = new BlockingConnection();
        // 生产映射函数保持原G1分支可用。
        await using var app = BuildApp(enabled, blocker);
        await app.StartAsync();
        // 请求进入连接等待后才主动取消，避免仅验证连接前的取消。
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()) };
        client.DefaultRequestHeaders.Add("X-Health-Key", "synthetic-readiness-test");
        // 客户端取消只影响本次健康请求。
        using var cancelled = new CancellationTokenSource();
        // 保留正在进行的真实HTTP任务以观察传播。
        var request = client.GetAsync("/health/ready", cancelled.Token);
        await blocker.Entered.Task.WaitAsync(TimeSpan.FromSeconds(4));
        cancelled.Cancel();
        await Assert.ThrowsExactlyAsync<TaskCanceledException>(async () => await request);
        await blocker.CancellationObserved.Task.WaitAsync(TimeSpan.FromSeconds(4));
        Assert.IsTrue(blocker.Cancelled);
    }

    /// <summary>创建只有公开健康路由的隔离宿主，不启动应用后台worker。</summary>
    /// <param name="enabled">选择实际G2或历史健康分支。</param>
    /// <param name="blocker">可观察的EF连接等待器。</param>
    /// <returns>使用真实生产路由的Kestrel应用。</returns>
    private static WebApplication BuildApp(bool enabled, BlockingConnection blocker)
    {
        // 配置仅包含无认证能力的合成地址和固定测试键。
        var builder = WebApplication.CreateBuilder();
        builder.Logging.ClearProviders();
        builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?> { ["G2:Enabled"] = enabled.ToString() });
        builder.Services.AddScoped<AuditService>();
        builder.Services.AddAntiforgery();
        builder.Services.AddDbContext<GovernanceDbContext>(options => options.UseNpgsql("Host=127.0.0.1;Database=readiness_fixture").AddInterceptors(blocker));
        // 实际MapPlatformEndpoints负责选择预算和响应映射。
        var app = builder.Build();
        app.MapPlatformEndpoints(new PlatformSecurityOptions { HealthKey = "synthetic-readiness-test" });
        app.Urls.Add("http://127.0.0.1:0");
        return app;
    }

    /// <summary>在网络连接前等待取消，检验真实EF查询接收到的token而不模拟查询结果。</summary>
    private sealed class BlockingConnection : DbConnectionInterceptor
    {
        /// <summary>连接等待是否真正收到取消。</summary>
        internal bool Cancelled { get; private set; }

        /// <summary>标记请求已进入Governance数据库访问。</summary>
        internal TaskCompletionSource Entered { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        /// <summary>标记EF已观察到请求或预算取消。</summary>
        internal TaskCompletionSource CancellationObserved { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        /// <summary>阻塞真实连接入口直到生产传入的取消token触发。</summary>
        /// <param name="connection">尚未打开的真实数据库连接。</param>
        /// <param name="eventData">EF当前连接上下文。</param>
        /// <param name="result">原生连接拦截结果。</param>
        /// <param name="cancellationToken">来自生产查询的取消令牌。</param>
        /// <returns>取消时抛出原生取消异常，不返回虚构数据库结果。</returns>
        public override async ValueTask<InterceptionResult> ConnectionOpeningAsync(DbConnection connection, ConnectionEventData eventData, InterceptionResult result, CancellationToken cancellationToken = default)
        {
            Entered.TrySetResult();
            try
            {
                await Task.Delay(Timeout.InfiniteTimeSpan, cancellationToken);
            }
            catch (OperationCanceledException)
            {
                Cancelled = true;
                CancellationObserved.TrySetResult();
                throw;
            }
            return result;
        }
    }
}
