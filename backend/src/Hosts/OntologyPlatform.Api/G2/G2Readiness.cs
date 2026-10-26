using System.Data.Common;
using Microsoft.EntityFrameworkCore;
using Npgsql;
using OntologyPlatform.Modules.Agents;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.Ontology;
using OntologyPlatform.Modules.Publishing;

namespace OntologyPlatform.Api.G2;

/// <summary>受原健康密钥保护的G2技术就绪探针，不读取模型凭证或业务正文。</summary>
public static class G2Readiness
{
    /// <summary>以同一个两秒预算核实Governance、三个模块及固定Jena/RustFS依赖。</summary>
    /// <param name="services">当前请求作用域，不跨请求共享上下文。</param>
    /// <param name="cancellationToken">客户端取消继续传播。</param>
    /// <returns>全部真实技术探针成功时为真；不要求已存在发布或已配置付费模型。</returns>
    public static async Task<bool> CheckAsync(IServiceProvider services, CancellationToken cancellationToken)
    {
        // 单次健康检查整体最多两秒，不能因每个依赖重置超时而无限等待。
        using var budget = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        budget.CancelAfter(TimeSpan.FromSeconds(2));
        // Npgsql取消会另建连接发送CancelRequest；为该握手预留最多一秒，不能等主预算耗尽才开始。
        using var databaseBudget = CancellationTokenSource.CreateLinkedTokenSource(budget.Token);
        databaseBudget.CancelAfter(TimeSpan.FromSeconds(1));
        try
        {
            // Governance同样属于G2整体就绪边界，首个连接等待就必须受同一预算约束。
            await using var governance = new GovernanceDbContext(ProbeOptions<GovernanceDbContext>(services));
            await governance.Sessions.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(databaseBudget.Token);
            await governance.AuditRecords.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(databaseBudget.Token);
            await governance.Resources.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(databaseBudget.Token);
            // 只查询常量投影以验证表存在，不读取或输出任何持久业务正文。
            await using var ontology = new OntologyDbContext(ProbeOptions<OntologyDbContext>(services));
            await ontology.Drafts.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(databaseBudget.Token);
            // 活动指针和Outbox均为真实发布路径所必需。
            await using var publishing = new PublishingDbContext(ProbeOptions<PublishingDbContext>(services));
            await publishing.ActiveReleases.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(databaseBudget.Token);
            await publishing.Outbox.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(databaseBudget.Token);
            // 运行和事件必须同时可用，模型disabled是产品策略而非依赖故障。
            await using var agents = new AgentsDbContext(ProbeOptions<AgentsDbContext>(services));
            await agents.Runs.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(databaseBudget.Token);
            await agents.Events.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(databaseBudget.Token);
            // URI只从可信启动配置读取，不能由健康请求输入覆盖。
            var configuration = services.GetRequiredService<IConfiguration>();
            // 同一固定Jena进程的健康端点不接触用户图或SPARQL正文。
            var jena = new Uri(configuration["Semantics:ValidationOrigin"] ?? throw new InvalidOperationException("缺少语义就绪配置。"));
            // 对象健康路径固定且不携带签名密钥。
            var rustfs = new Uri(configuration["Publishing:S3Endpoint"] ?? throw new InvalidOperationException("缺少对象就绪配置。"));
            // 禁止代理和重定向的命名客户端由唯一组合根注册。
            using var client = services.GetRequiredService<IHttpClientFactory>().CreateClient("g2-readiness");
            // 两个请求均沿用同一剩余预算，不记录远端响应正文。
            using var semantic = await client.GetAsync(new Uri(jena.GetLeftPart(UriPartial.Authority) + "/$/ping"), HttpCompletionOption.ResponseHeadersRead, budget.Token);
            if (!semantic.IsSuccessStatusCode) return false;
            // RustFS readiness是真实服务端点，不能替代制品完整性回验。
            using var storage = await client.GetAsync(new Uri(rustfs, "/health/ready"), HttpCompletionOption.ResponseHeadersRead, budget.Token);
            return storage.IsSuccessStatusCode;
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested) { return false; }
        catch (HttpRequestException) { return false; }
        catch (DbException) when (!cancellationToken.IsCancellationRequested) { return false; }
        // EF默认执行策略会将驱动瞬时连接错误包装为InvalidOperationException，仍是依赖失败。
        catch (InvalidOperationException failure) when (failure.InnerException is DbException && !cancellationToken.IsCancellationRequested) { return false; }
    }

    /// <summary>复制各模块配置建立健康专用连接，不改变业务options、连接池或数据库写入边界。</summary>
    /// <typeparam name="T">本次技术探针对应的模块上下文。</typeparam>
    /// <param name="services">当前请求作用域的原始只读配置来源。</param>
    /// <returns>保留模型/拦截器的独立配置，驱动连接/命令/取消握手均有原生超时。</returns>
    private static DbContextOptions<T> ProbeOptions<T>(IServiceProvider services) where T : DbContext
    {
        // 原上下文只用于取得受信连接配置，不在其连接上运行或修改探针。
        var original = services.GetRequiredService<T>();
        // 取消握手使用连接Timeout，-1只跳过取消响应等待，二者必须同时限制。
        var connection = new NpgsqlConnectionStringBuilder(original.Database.GetConnectionString())
        {
            Timeout = 1,
            CommandTimeout = 1,
            CancellationTimeout = -1,
            Pooling = false,
            Multiplexing = false
        };
        // 先沿用驱动的显式连接串值；getter默认Prefer不能代表环境中的有效加密要求。
        var gssMode = connection.GssEncryptionMode;
        // Keys只枚举实际写入的规范键；ContainsKey/TryGetValue也会识别未显式赋值的支持键。
        if (!connection.Keys.Cast<string>().Contains("GSS Encryption Mode", StringComparer.OrdinalIgnoreCase))
        {
            // 与锁定驱动相同：未显式配置时才解析PGGSSENCMODE，非法环境值回到属性默认值。
            var environmentMode = Environment.GetEnvironmentVariable("PGGSSENCMODE");
            // 忽略大小写解析保持官方驱动的环境优先级，不改写当前进程环境。
            if (Enum.TryParse<GssEncryptionMode>(environmentMode, ignoreCase: true, out var configuredMode)) gssMode = configuredMode;
        }
        // 仅有效Prefer允许跳过可选重试；显式或环境Require必须保留，原TLS策略不变。
        connection.GssEncryptionMode = gssMode == GssEncryptionMode.Prefer ? GssEncryptionMode.Disable : gssMode;
        // typed options复制保留各模块模型及既有EF配置，UseNpgsql仅替换这份副本的连接参数。
        var options = new DbContextOptionsBuilder<T>(services.GetRequiredService<DbContextOptions<T>>());
        return options.UseNpgsql(connection.ConnectionString).Options;
    }
}
