using System.Data;
using System.Data.Common;
using System.Diagnostics;
using System.Net;
using Microsoft.AspNetCore.Builder;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using OntologyPlatform.Api;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Modules.Agents;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.Ontology;
using OntologyPlatform.Modules.Publishing;

namespace OntologyPlatform.SecurityTests;

/// <summary>以可控延迟隔离数据库和HTTP传输，检验真实健康路由跨阶段不重置预算。</summary>
[TestClass]
public sealed class G2ReadinessBudgetTests
{
    /// <summary>八次表探针及两个HTTP依赖共用一个预算；前面已耗时不能在后续重新获得两秒。</summary>
    /// <returns>真实Kestrel路由的跨阶段取消验证任务。</returns>
    [TestMethod]
    public async Task DatabaseAndBothHttpDependenciesShareRemainingBudget()
    {
        // EF执行拦截仅提供空技术探针数据，不代表真实PG表或产品查询已通过。
        var queries = new DelayedQueries();
        // 隔离网络连接，所有实际等待都发生在可取消的命令/HTTP传输入口。
        var connections = new SuppressedConnections();
        // 两个HTTP请求分别消耗850毫秒，连同八次70毫秒查询超过整体两秒。
        var http = new DelayedHttp();
        // 生产路由与真实模块上下文保持不变，仅外部I/O由可控传输适配。
        var builder = WebApplication.CreateBuilder();
        builder.Logging.ClearProviders();
        builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["G2:Enabled"] = "true",
            ["Semantics:ValidationOrigin"] = "http://jena.invalid",
            ["Publishing:S3Endpoint"] = "http://storage.invalid"
        });
        builder.Services.AddAntiforgery();
        builder.Services.AddScoped<AuditService>();
        builder.Services.AddDbContext<GovernanceDbContext>(options => Configure(options, queries, connections));
        builder.Services.AddDbContext<OntologyDbContext>(options => Configure(options, queries, connections));
        builder.Services.AddDbContext<PublishingDbContext>(options => Configure(options, queries, connections));
        builder.Services.AddDbContext<AgentsDbContext>(options => Configure(options, queries, connections));
        builder.Services.AddHttpClient("g2-readiness").ConfigurePrimaryHttpMessageHandler(() => http);
        // 调用实际映射函数检验治理探针与G2分支整体控制流。
        await using var app = builder.Build();
        app.MapPlatformEndpoints(new PlatformSecurityOptions { HealthKey = "synthetic-readiness-test" });
        app.Urls.Add("http://127.0.0.1:0");
        await app.StartAsync();
        // 客户端保险期限大于预算，不能代替生产取消机制。
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()), Timeout = TimeSpan.FromSeconds(5) };
        client.DefaultRequestHeaders.Add("X-Health-Key", "synthetic-readiness-test");
        // 记录含HTTP及EF等待的实际墙钟时间。
        var elapsed = Stopwatch.StartNew();
        // 若每阶段重新计时，这个请求会在约2.26秒返回200，违反整体预算。
        using var response = await client.GetAsync("/health/ready");
        Assert.AreEqual(HttpStatusCode.ServiceUnavailable, response.StatusCode);
        Assert.AreEqual(8, queries.Count);
        CollectionAssert.AreEqual(new[] { "/$/ping", "/health/ready" }, http.Paths.ToArray());
        Assert.IsTrue(http.Cancelled);
        Assert.IsTrue(elapsed.Elapsed >= TimeSpan.FromSeconds(1.5) && elapsed.Elapsed < TimeSpan.FromSeconds(4));
        Console.WriteLine($"Synthetic dependency budget: queries={queries.Count}; http={http.Paths.Count}; elapsedMs={elapsed.Elapsed.TotalMilliseconds:F0}; status={(int)response.StatusCode}; storageCancelled={http.Cancelled}");
    }

    /// <summary>注册原生Npgsql及测试I/O拦截，不引入新的EF提供程序或产品依赖。</summary>
    /// <param name="options">各模块独立上下文的配置。</param>
    /// <param name="queries">只对技术探针返回空读取器的命令入口。</param>
    /// <param name="connections">防止本测试触及真实网络连接。</param>
    private static void Configure(DbContextOptionsBuilder options, DelayedQueries queries, SuppressedConnections connections)
        => options.UseNpgsql("Host=127.0.0.1;Database=readiness_fixture").AddInterceptors(queries, connections);

    /// <summary>跳过外部连接，后续命令同样由测试拦截器处理。</summary>
    private sealed class SuppressedConnections : DbConnectionInterceptor
    {
        /// <summary>阻止测试访问真实PG，不把连接抑制视作实际健康证明。</summary>
        /// <param name="connection">未打开的真实连接。</param>
        /// <param name="eventData">本次连接上下文。</param>
        /// <param name="result">原生拦截结果。</param>
        /// <param name="cancellationToken">生产探针预算令牌。</param>
        /// <returns>仅对本测试抑制网络打开。</returns>
        public override ValueTask<InterceptionResult> ConnectionOpeningAsync(DbConnection connection, ConnectionEventData eventData, InterceptionResult result, CancellationToken cancellationToken = default)
            => ValueTask.FromResult(InterceptionResult.Suppress());
    }

    /// <summary>每次查询消耗真实可取消时间，空技术结果只驱动健康控制流。</summary>
    private sealed class DelayedQueries : DbCommandInterceptor
    {
        /// <summary>实际进入执行入口的技术探针数量。</summary>
        internal int Count { get; private set; }

        /// <summary>在真实EF异步命令入口等待，再返回无业务记录的读取器。</summary>
        /// <param name="command">本次EF生成的只读命令。</param>
        /// <param name="eventData">本次命令上下文。</param>
        /// <param name="result">原生读取拦截结果。</param>
        /// <param name="cancellationToken">生产查询传入的剩余预算令牌。</param>
        /// <returns>仅供本测试继续控制流的空读取器。</returns>
        public override async ValueTask<InterceptionResult<DbDataReader>> ReaderExecutingAsync(DbCommand command, CommandEventData eventData, InterceptionResult<DbDataReader> result, CancellationToken cancellationToken = default)
        {
            Count++;
            await Task.Delay(TimeSpan.FromMilliseconds(70), cancellationToken);
            return InterceptionResult<DbDataReader>.SuppressWithResult(new DataTable().CreateDataReader());
        }
    }

    /// <summary>以真实可取消延迟模拟两个固定健康端点，不访问任何外部服务。</summary>
    private sealed class DelayedHttp : HttpMessageHandler
    {
        /// <summary>实际进入HTTP传输的固定路径顺序。</summary>
        internal List<string> Paths { get; } = [];

        /// <summary>最后一个依赖是否收到整体预算取消。</summary>
        internal bool Cancelled { get; private set; }

        /// <summary>每个端点等待850毫秒，最后一个必须被剩余预算中断。</summary>
        /// <param name="request">真实生产客户端发出的固定健康请求。</param>
        /// <param name="cancellationToken">HTTP客户端收到的剩余预算令牌。</param>
        /// <returns>预算足够时返回合成成功，否则传播取消。</returns>
        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Paths.Add(request.RequestUri!.AbsolutePath);
            try
            {
                await Task.Delay(TimeSpan.FromMilliseconds(850), cancellationToken);
            }
            catch (OperationCanceledException)
            {
                Cancelled = true;
                throw;
            }
            return new HttpResponseMessage(HttpStatusCode.OK);
        }
    }
}
