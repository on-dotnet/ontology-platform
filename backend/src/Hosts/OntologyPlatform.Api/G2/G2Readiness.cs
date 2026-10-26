using System.Data.Common;
using Microsoft.EntityFrameworkCore;
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
        try
        {
            // Governance同样属于G2整体就绪边界，首个连接等待就必须受同一预算约束。
            var governance = services.GetRequiredService<GovernanceDbContext>();
            await governance.Sessions.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(budget.Token);
            await governance.AuditRecords.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(budget.Token);
            await governance.Resources.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(budget.Token);
            // 只查询常量投影以验证表存在，不读取或输出任何持久业务正文。
            var ontology = services.GetRequiredService<OntologyDbContext>();
            await ontology.Drafts.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(budget.Token);
            // 活动指针和Outbox均为真实发布路径所必需。
            var publishing = services.GetRequiredService<PublishingDbContext>();
            await publishing.ActiveReleases.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(budget.Token);
            await publishing.Outbox.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(budget.Token);
            // 运行和事件必须同时可用，模型disabled是产品策略而非依赖故障。
            var agents = services.GetRequiredService<AgentsDbContext>();
            await agents.Runs.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(budget.Token);
            await agents.Events.AsNoTracking().Select(_ => 1).Take(1).ToArrayAsync(budget.Token);
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
    }
}
