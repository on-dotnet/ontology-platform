using System.Data.Common;
using System.Diagnostics;
using System.Net;
using Microsoft.AspNetCore.Builder;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Npgsql;
using OntologyPlatform.Api;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Modules.Agents;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.Ontology;
using OntologyPlatform.Modules.Publishing;

namespace OntologyPlatform.SecurityTests;

/// <summary>只操作本测试新建的PG容器，检验真实驱动握手和查询取消的墙钟界限及恢复。</summary>
[TestClass]
public sealed class G2ReadinessPostgresTests
{
    /// <summary>真实暂停PG后，连接/已打开连接的查询和调用方取消必须有界结束并可恢复。</summary>
    /// <param name="duringQuery">在真实连接打开后、查询发出前暂停PG。</param>
    /// <param name="cancelCaller">主动取消客户端，并等待宿主请求实际退出。</param>
    /// <returns>真实PG暂停与恢复验证任务。</returns>
    [TestMethod]
    [DataRow(false, false)]
    [DataRow(true, false)]
    [DataRow(true, true)]
    public async Task PausedPostgresCannotOutliveHealthBudget(bool duringQuery, bool cancelCaller)
    {
        // 每个用例自行新建随机容器，完整安全runner无需注入秘密或容器身份。
        await using var fixture = await FreshPostgres.StartAsync();
        // 连接仅存在当前进程内存，从不写证据或异常信息。
        var connection = fixture.Connection;
        // 生命周期命令只针对本用例拥有的随机容器。
        var container = fixture.Container;
        // 真正建技术探针空表，仅验证连通/超时，不冒充正式迁移验收。
        await using var setup = new NpgsqlConnection(connection);
        await setup.OpenAsync();
        // 所有表只被SELECT常量访问，不保存任何业务或认证材料。
        await using var command = new NpgsqlCommand("CREATE SCHEMA IF NOT EXISTS governance; CREATE SCHEMA IF NOT EXISTS ontology; CREATE SCHEMA IF NOT EXISTS publishing; CREATE SCHEMA IF NOT EXISTS agents; CREATE TABLE IF NOT EXISTS governance.server_sessions(x int); CREATE TABLE IF NOT EXISTS governance.audit_records(x int); CREATE TABLE IF NOT EXISTS governance.synthetic_resources(x int); CREATE TABLE IF NOT EXISTS ontology.\"Drafts\"(x int); CREATE TABLE IF NOT EXISTS publishing.\"ActiveReleases\"(x int); CREATE TABLE IF NOT EXISTS publishing.\"Outbox\"(x int); CREATE TABLE IF NOT EXISTS agents.\"Runs\"(x int); CREATE TABLE IF NOT EXISTS agents.\"Events\"(x int);", setup);
        await command.ExecuteNonQueryAsync();
        // 暂停动作仅挂在真实EF命令入口，数据库响应仍来自真实Npgsql网络传输。
        var pause = new PauseBeforeQuery(container!);
        // 完整路由宿主使用实际四个模块上下文与固定HTTP成功适配。
        var builder = WebApplication.CreateBuilder();
        builder.Logging.ClearProviders();
        builder.Configuration.AddInMemoryCollection(new Dictionary<string, string?> { ["G2:Enabled"] = "true", ["Semantics:ValidationOrigin"] = "http://jena.invalid", ["Publishing:S3Endpoint"] = "http://storage.invalid" });
        builder.Services.AddAntiforgery();
        builder.Services.AddScoped<AuditService>();
        builder.Services.AddDbContext<GovernanceDbContext>(options => options.UseNpgsql(connection).AddInterceptors(pause));
        builder.Services.AddDbContext<OntologyDbContext>(options => options.UseNpgsql(connection));
        builder.Services.AddDbContext<PublishingDbContext>(options => options.UseNpgsql(connection));
        builder.Services.AddDbContext<AgentsDbContext>(options => options.UseNpgsql(connection));
        builder.Services.AddHttpClient("g2-readiness").ConfigurePrimaryHttpMessageHandler(() => new HealthyHttp());
        // 所有模块仍通过生产路由绑定，不以自造健康响应替代产品探针。
        await using var app = builder.Build();
        // 请求退出信号验证客户端取消之后宿主没有遗留等待任务。
        var ended = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        app.Use(async (context, next) => { try { await next(context); } finally { ended.TrySetResult(); } });
        app.MapPlatformEndpoints(new PlatformSecurityOptions { HealthKey = "synthetic-readiness-test" });
        app.Urls.Add("http://127.0.0.1:0");
        await app.StartAsync();
        // 八秒保险期限用于明确复现旧驱动取消握手超过健康预算。
        using var client = new HttpClient { BaseAddress = new Uri(app.Urls.Single()), Timeout = TimeSpan.FromSeconds(8) };
        client.DefaultRequestHeaders.Add("X-Health-Key", "synthetic-readiness-test");
        Assert.AreEqual(HttpStatusCode.OK, (await client.GetAsync("/health/ready")).StatusCode);
        ended = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        try
        {
            if (duringQuery) pause.Armed = true;
            else await DockerAsync("pause", container!);
            // 调用方取消与整体预算分别执行，不能只观察HttpClient本地取消。
            using var caller = new CancellationTokenSource();
            // 测量整个实际健康请求及服务器退出，不以Task.WhenAny丢弃数据库任务。
            var elapsed = Stopwatch.StartNew();
            // 请求必须在finally恢复PG之前自行有界退出。
            var request = client.GetAsync("/health/ready", caller.Token);
            if (cancelCaller)
            {
                await pause.Paused.Task.WaitAsync(TimeSpan.FromSeconds(4));
                caller.Cancel();
                await Assert.ThrowsExactlyAsync<TaskCanceledException>(async () => await request);
            }
            else
            {
                // 标准503必须由生产代码形成，不能由测试超时转造。
                using var response = await request;
                Assert.AreEqual(HttpStatusCode.ServiceUnavailable, response.StatusCode);
            }
            await ended.Task.WaitAsync(TimeSpan.FromSeconds(3));
            Assert.IsTrue(elapsed.Elapsed < TimeSpan.FromSeconds(3), $"真实PG请求耗时{elapsed.Elapsed.TotalMilliseconds:F0}ms。");
            Console.WriteLine($"Real PostgreSQL pause: duringQuery={duringQuery}; callerCancellation={cancelCaller}; requestEnded=True; elapsedMs={elapsed.Elapsed.TotalMilliseconds:F0}");
        }
        finally
        {
            pause.Armed = false;
            await DockerAsync("unpause", container!);
        }
        Assert.AreEqual(HttpStatusCode.OK, (await client.GetAsync("/health/ready")).StatusCode);
        // 业务配置仍为默认超时及池化，健康探针不能修改注册的options或连接池。
        await using var scope = app.Services.CreateAsyncScope();
        // 只在内存断言配置，不输出连接串或密码。
        var original = new NpgsqlConnectionStringBuilder(scope.ServiceProvider.GetRequiredService<GovernanceDbContext>().Database.GetConnectionString());
        Assert.AreEqual(15, original.Timeout);
        Assert.AreEqual(2000, original.CancellationTimeout);
        Assert.IsTrue(original.Pooling);
    }

    /// <summary>只对专用随机测试容器执行生命周期命令，不打印Docker或认证输出。</summary>
    /// <param name="operation">固定pause或unpause。</param>
    /// <param name="container">测试runner新建的专属容器。</param>
    /// <returns>等待Docker操作真实完成。</returns>
    private static async Task DockerAsync(string operation, string container)
    {
        // 子进程输出不进入测试日志；仅检查退出码。
        var start = new ProcessStartInfo("docker") { RedirectStandardOutput = true, RedirectStandardError = true };
        start.ArgumentList.Add(operation);
        start.ArgumentList.Add(container);
        // 完整等待所启动的进程，避免遗留Docker控制命令。
        using var process = Process.Start(start)!;
        await process.WaitForExitAsync();
        Assert.AreEqual(0, process.ExitCode, "本轮测试容器生命周期操作失败。");
    }

    /// <summary>自建并完整清理一个固定批准镜像的PG，绝不复用Master或G1共享运行时。</summary>
    private sealed class FreshPostgres : IAsyncDisposable
    {
        /// <summary>本用例唯一拥有的容器标识。</summary>
        internal string Container { get; }

        /// <summary>只供内存传递的随机连接配置。</summary>
        internal string Connection { get; private set; } = string.Empty;

        /// <summary>冻结新容器名，不接受外部运行时输入。</summary>
        /// <param name="container">新建容器的随机专用名字。</param>
        private FreshPostgres(string container) => Container = container;

        /// <summary>创建回环随机端口和tmpfs的新PG，失败时也清理所有权内容器。</summary>
        /// <returns>已经实际就绪的独立PG。</returns>
        internal static async Task<FreshPostgres> StartAsync()
        {
            // 随机名称确保与其他并行任务及保留容器无交集。
            var fixture = new FreshPostgres("g2-host-ready-" + Guid.NewGuid().ToString("N")[..12]);
            // 随机密码只通过子进程环境传递，不写命令参数或磁盘。
            var password = Convert.ToBase64String(System.Security.Cryptography.RandomNumberGenerator.GetBytes(32));
            try
            {
                await RunAsync(["run", "--detach", "--name", fixture.Container, "--env", "POSTGRES_PASSWORD", "--env", "POSTGRES_DB=readiness", "--publish", "127.0.0.1::5432", "--tmpfs", "/var/lib/postgresql", "postgres:18.6-trixie@sha256:edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6"], password);
                // Docker只返回公开回环映射，禁止inspect整个容器环境。
                var port = (await RunAsync(["port", fixture.Container, "5432/tcp"])).Output.Trim().Split(':')[^1];
                // 原始业务配置使用驱动默认超时，回归断言探针副本不会改变它。
                fixture.Connection = new NpgsqlConnectionStringBuilder { Host = "127.0.0.1", Port = int.Parse(port), Database = "readiness", Username = "postgres", Password = password }.ConnectionString;
                // 轮询真实PG入口，次数限制只用于fixture启动，不模拟产品超时。
                for (var attempt = 0; attempt < 120; attempt++)
                {
                    if ((await RunAsync(["exec", fixture.Container, "pg_isready", "-U", "postgres", "-d", "readiness"], requireSuccess: false)).Code == 0) return fixture;
                    await Task.Delay(250);
                }
                throw new AssertFailedException("本轮随机PG未在30秒内就绪。");
            }
            catch
            {
                await fixture.DisposeAsync();
                throw;
            }
        }

        /// <summary>先恢复再删除自己的临时容器，任何断言失败都不能遗留暂停进程。</summary>
        /// <returns>容器清理完成任务。</returns>
        public async ValueTask DisposeAsync()
        {
            await RunAsync(["unpause", Container], requireSuccess: false);
            await RunAsync(["rm", "--force", Container]);
        }

        /// <summary>在内存完整接收子进程输出，错误只报告固定类别，不输出环境或原始stderr。</summary>
        /// <param name="arguments">不含秘密的Docker参数。</param>
        /// <param name="password">仅run命令的进程级随机密码。</param>
        /// <param name="requireSuccess">就绪轮询和清理允许非零状态。</param>
        /// <returns>用于回环端口和就绪状态的内存结果。</returns>
        private static async Task<(int Code, string Output)> RunAsync(string[] arguments, string? password = null, bool requireSuccess = true)
        {
            // 所有子进程均被等待，输出不流入产品日志或测试证据。
            var start = new ProcessStartInfo("docker") { RedirectStandardOutput = true, RedirectStandardError = true };
            if (password is not null) start.Environment["POSTGRES_PASSWORD"] = password;
            // 参数分别传递，不经shell解释或拼接命令。
            foreach (var argument in arguments) start.ArgumentList.Add(argument);
            // 当前进程拥有并释放本次生命周期命令。
            using var process = Process.Start(start)!;
            // 同时排空两条管道，避免子进程因输出背压挂起。
            var output = process.StandardOutput.ReadToEndAsync();
            // stderr只排空，不返回或打印潜在底层诊断。
            var error = process.StandardError.ReadToEndAsync();
            await process.WaitForExitAsync();
            await error;
            if (requireSuccess) Assert.AreEqual(0, process.ExitCode, "专用PG测试容器操作失败。");
            return (process.ExitCode, await output);
        }
    }

    /// <summary>在真实数据库已打开的查询入口暂停容器，复现CancelRequest握手阻塞。</summary>
    /// <param name="container">当前用例唯一拥有的临时容器。</param>
    private sealed class PauseBeforeQuery(string container) : DbCommandInterceptor
    {
        /// <summary>是否只暂停下一次真实查询。</summary>
        internal bool Armed { get; set; }

        /// <summary>容器已实际暂停后允许客户端取消。</summary>
        internal TaskCompletionSource Paused { get; } = new(TaskCreationOptions.RunContinuationsAsynchronously);

        /// <summary>不替代任何数据库响应，仅控制暂停发生在连接后的确定时刻。</summary>
        /// <param name="command">实际EF只读命令。</param>
        /// <param name="eventData">真实命令上下文。</param>
        /// <param name="result">原生未抑制结果。</param>
        /// <param name="cancellationToken">生产取消令牌。</param>
        /// <returns>原样继续真实Npgsql执行。</returns>
        public override async ValueTask<InterceptionResult<DbDataReader>> ReaderExecutingAsync(DbCommand command, CommandEventData eventData, InterceptionResult<DbDataReader> result, CancellationToken cancellationToken = default)
        {
            if (Armed)
            {
                Armed = false;
                await DockerAsync("pause", container);
                Paused.TrySetResult();
            }
            return result;
        }
    }

    /// <summary>隔离与本缺陷无关的HTTP依赖，真实PG仍使用网络连接。</summary>
    private sealed class HealthyHttp : HttpMessageHandler
    {
        /// <summary>返回无正文的固定技术健康响应。</summary>
        /// <param name="request">生产健康请求。</param>
        /// <param name="cancellationToken">剩余预算。</param>
        /// <returns>HTTP成功适配，不能作为真实Jena/RustFS验收。</returns>
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
            => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK));
    }
}
