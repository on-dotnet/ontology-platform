using OntologyPlatform.Contracts;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Modules.SemanticQuery;
using OntologyPlatform.Modules.Connections;
using System.Text.Json;
using OntologyPlatform.Modules.Agents;

namespace OntologyPlatform.AgentTests;

/// <summary>G4工具运行使用服务器预算，不继承客户端身份或旧G2载荷。</summary>
[TestClass]
public sealed class G4QueryMcpTests
{
    /// <summary>SDK字典转换之前检测重复包装键，防止最后一个值静默覆盖。</summary>
    [TestMethod]
    public void RawMcpRejectsDuplicateWrapperBeforeDictionaryConversion()
    {
        Assert.IsTrue(SemanticMcpTools.RawG4PayloadRejected(System.Text.Encoding.UTF8.GetBytes("{\"params\":{\"arguments\":{\"queryId\":\"first\",\"queryId\":\"second\"}}}")));
        Assert.IsFalse(SemanticMcpTools.RawG4PayloadRejected(System.Text.Encoding.UTF8.GetBytes("{\"params\":{\"arguments\":{\"queryId\":\"first\"}}}")));
        Assert.IsTrue(SemanticMcpTools.RawG4PayloadRejected(new byte[65537]));
    }

    /// <summary>恢复与执行同样消耗工具次数，第四次及期限后的调用必须拒绝。</summary>
    [TestMethod]
    public void QueryRunCountsEveryAttemptAndUsesOneDeadline()
    {
        // 固定可信运行起点，以显式时刻验证预算边界而不等待三十秒。
        var now = DateTimeOffset.UtcNow;
        // 运行引用仅由服务器创建，客户端工具参数没有runId入口。
        var run = new G4QueryRunReference(now);
        Assert.AreEqual(1, run.Reserve(now));
        Assert.AreEqual(2, run.Reserve(now.AddSeconds(10)));
        Assert.AreEqual(3, run.Reserve(now.AddSeconds(20)));
        Assert.Throws<SemanticOperationException>(() => run.Reserve(now.AddSeconds(21)));
        // 单次调用仍受同一绝对期限限制，不因重新进入工具而获得新三十秒。
        var expired = new G4QueryRunReference(now);
        Assert.Throws<SemanticOperationException>(() => expired.Reserve(now.AddSeconds(30)));
        Assert.AreNotEqual(run.RunId, expired.RunId);
    }
}

/// <summary>只在当前任务受控容器读取既有正式查询；不迁移、清扫或修改运行库旧记录。</summary>
[TestClass]
public sealed class G4QueryMafRuntimeTests
{
    /// <summary>实际MAF恢复三次后拒绝第四次，真实PG只保存三个引用。</summary>
    [TestMethod]
    public async Task ActualMafUsesCurrentGatewayAndOnePersistentBudget()
    {
        Assert.AreEqual("G4-M4-QUERY-001:query-impl-01", Environment.GetEnvironmentVariable("G4_QUERY_RUNTIME_TEST"));
        // 准确查询ID来自本任务刚完成的真实OIDC查询，不导出Cookie或票据。
        var queryId = Environment.GetEnvironmentVariable("G4_QUERY_RUNTIME_QUERY_ID");
        Assert.IsFalse(string.IsNullOrWhiteSpace(queryId));
        // 构建正式宿主DI而不Start；因此不运行迁移、worker或后台过期清扫。
        await using var app = OntologyPlatform.Api.PlatformApiHost.CreateApplication([], builder =>
        {
            builder.Logging.ClearProviders();
            // 复用正式API只读配置挂载，测试平台工作目录不决定安全配置来源。
            builder.Configuration.AddJsonFile("/private/api/appsettings.json", optional: false);
            Microsoft.Extensions.Configuration.MemoryConfigurationBuilderExtensions.AddInMemoryCollection(builder.Configuration,
                new Dictionary<string, string?> { ["Agents:EnableDeterministicHarness"] = "true" });
        });
        Assert.IsTrue(app.Environment.EnvironmentName == "Development");
        // 所有factory、provider与消费者保持正式组合，不替换Gateway或查询绑定参与者。
        await using var scope = Microsoft.Extensions.DependencyInjection.ServiceProviderServiceExtensions.CreateAsyncScope(app.Services);
        // 正式查询模块工厂保持实际PG配置。
        var factory = Microsoft.Extensions.DependencyInjection.ServiceProviderServiceExtensions.GetRequiredService<Microsoft.EntityFrameworkCore.IDbContextFactory<OntologyPlatform.Modules.SemanticQuery.G4QueryDbContext>>(scope.ServiceProvider);
        // 独立上下文读取精确查询及当前运行计数。
        await using var database = await factory.CreateDbContextAsync();
        // 只读取明确当前合成主体和精确ID，绝不使用未来时钟或全表删除。
        var row = await Microsoft.EntityFrameworkCore.EntityFrameworkQueryableExtensions.SingleAsync(database.Queries, item => item.Id == queryId && item.OrganizationId == "org-demo");
        Assert.AreEqual("COMPLETED", row.ExecutionStatus);
        // 完整服务器票据仍由真实MappingSessionAuthority解密核验，此处不能伪造通过。
        var actor = System.Text.Json.JsonSerializer.Deserialize<ActorContext>(Environment.GetEnvironmentVariable("G4_QUERY_RUNTIME_ACTOR")!,
            new System.Text.Json.JsonSerializerOptions(System.Text.Json.JsonSerializerDefaults.Web))!;
        Assert.AreEqual(row.SubjectId, actor.SubjectId);
        Assert.AreEqual(row.OrganizationId, actor.OrganizationId);
        // 正式MAF执行器复用已注册工具边界。
        var executor = Microsoft.Extensions.DependencyInjection.ServiceProviderServiceExtensions.GetRequiredService<AgentRunExecutor>(scope.ServiceProvider);
        // Run引用与计数由查询模块持久化。
        var store = Microsoft.Extensions.DependencyInjection.ServiceProviderServiceExtensions.GetRequiredService<IG4QueryRunStore>(scope.ServiceProvider);
        // 恢复工具只接收已完成查询ID。
        var arguments = new Dictionary<string, System.Text.Json.JsonElement> { ["queryId"] = System.Text.Json.JsonSerializer.SerializeToElement(queryId) };
        // 先用同一正式Gateway短定位当前会话/源前提，错误只报告固定码而不输出安全材料。
        var gateway = Microsoft.Extensions.DependencyInjection.ServiceProviderServiceExtensions.GetRequiredService<ISemanticGateway>(scope.ServiceProvider);
        try { _ = await gateway.ReadG4Async(actor, row.SessionReference, queryId!, true, CancellationToken.None); }
        catch (SemanticOperationException error) { Assert.Fail("真实Gateway前提失败：" + error.Status + ":" + error.Code); }
        // 真正进入MAF函数调用循环，四次均由相同服务器引用计数。
        var result = await executor.RunG4DeterministicAsync(actor, row.SessionReference, "g4_query_result", arguments, store, 4, CancellationToken.None);
        Assert.AreEqual(4, result.Results.Length);
        Assert.IsTrue(result.Results.Take(3).All(item => item.IsError != true));
        Assert.IsTrue(result.Results[3].IsError == true);
        Assert.AreEqual("semantic_tool_rejected", ((ModelContextProtocol.Protocol.TextContentBlock)result.Results[3].Content.Single()).Text);
        // 完全同一个规范结果被恢复三次，不能重新执行源查询或复制进旧Run结果列。
        Assert.AreEqual(((ModelContextProtocol.Protocol.TextContentBlock)result.Results[0].Content.Single()).Text,
            ((ModelContextProtocol.Protocol.TextContentBlock)result.Results[2].Content.Single()).Text);
        // PG计数与引用均来自实际执行；第四次没有获得预算或引用槽位。
        var counts = await Microsoft.EntityFrameworkCore.EntityFrameworkQueryableExtensions.SingleAsync(
            Microsoft.EntityFrameworkCore.RelationalDatabaseFacadeExtensions.SqlQuery<int>(database.Database,
                $"SELECT \"ToolCalls\" AS \"Value\" FROM semantic_query.\"QueryRuns\" WHERE \"Id\" = {result.RunId}"));
        Assert.AreEqual(3, counts);
        // 实际PG数组长度验证只保存三个查询引用。
        var references = await Microsoft.EntityFrameworkCore.EntityFrameworkQueryableExtensions.SingleAsync(
            Microsoft.EntityFrameworkCore.RelationalDatabaseFacadeExtensions.SqlQuery<int>(database.Database,
                $"SELECT cardinality(\"QueryIds\") AS \"Value\" FROM semantic_query.\"QueryRuns\" WHERE \"Id\" = {result.RunId}"));
        Assert.AreEqual(3, references);
        // 当前绑定变化在真实源读取之后、最终结果提交之前发生；不替换真实绑定参与者。
        if (Environment.GetEnvironmentVariable("G4_QUERY_BINDING_RACE") == "1")
            await BindingChangeAfterRealReadAsync(scope.ServiceProvider, actor, row, database);
    }

    /// <summary>合成源故障包装只在真实PG读取完成后调用正式连接编辑用例，验证最终版本复核。</summary>
    private static async Task BindingChangeAfterRealReadAsync(IServiceProvider services, ActorContext actor, G4QueryRecord original, G4QueryDbContext database)
    {
        // 正式应用服务完成所有CAS、凭据绑定及事务审计，测试不直接修改连接表。
        var connections = services.GetRequiredService<IConnectionRequestHandler>();
        // 每次正式连接命令共享当前服务器身份与会话。
        var invocation = new ConnectionInvocation { Operation = "get", Actor = actor, Id = original.ConnectionId, ChildId = null,
            Body = null, Etag = null, Cursor = null, Type = null, State = null, SessionReference = original.SessionReference };
        // 真实连接读取提供CAS修订与ETag。
        var current = await connections.HandleAsync(invocation, CancellationToken.None);
        // 当前连接视图仅用于构造正式编辑命令。
        var view = (ConnectionView)current.Value;
        Assert.AreEqual("ACTIVE", view.State);
        // 原请求已通过正式持久合同，新的执行仍绑定同一正式映射。
        using var request = System.Text.Json.JsonDocument.Parse(original.RequestBytes);
        // 从原请求恢复原能力与固定映射计划。
        var query = request.RootElement.GetProperty("query").Deserialize<G4SemanticQuery>(G4QueryJson.Options)!;
        // 新幂等键区分本次真实在途执行。
        var key = Guid.NewGuid().ToString();
        // 只有实际完成连接编辑才允许进入恢复流程。
        var changed = false;
        // 包装保留真实查询适配器、TLS、源事务、回执和所有原字段值。
        var source = new AfterReadSource(services.GetRequiredService<IG4SourceQueryReader>(), async token =>
        {
            // 正式编辑完成后确认配置修订真实推进。
            var reply = await connections.HandleAsync(invocation with { Operation = "patch", Etag = current.Etag,
                Body = new ConnectionPatchRequest { DisplayName = view.DisplayName, Command = Command(view.ConfigRevision) } }, token);
            changed = true;
            Assert.IsTrue(((ConnectionView)reply.Value).ConfigRevision > view.ConfigRevision);
        });
        // 唯一替换是合成读取完成后的调度故障；其余依赖取正式DI真实实例。
        var execution = new G4QueryExecution(services.GetRequiredService<IG4QueryBindingReader>(), source,
            services.GetRequiredService<IG4QueryAuthorizationAuthority>(), services.GetRequiredService<G4QueryResultStore>(), TimeProvider.System);
        // 除读取后调度点外全部依赖仍为正式DI组件。
        var gateway = new SemanticGateway(services.GetRequiredService<IReleaseCatalog>(), services.GetRequiredService<ISemanticRuntime>(),
            services.GetRequiredService<CapabilityRegistry>(), services.GetRequiredService<IAuditTrail>(), TimeProvider.System,
            services.GetRequiredService<VerifiedReleaseSources>(), execution);
        try
        {
            // 提交复核必须抛出权限或绑定失效，而非成功结果。
            var error = await Assert.ThrowsAsync<SemanticOperationException>(() => gateway.ExecuteG4Async(actor, original.SessionReference, query, key, null, CancellationToken.None));
            Assert.IsTrue(changed && error.Status is 403 or 409);
            // 真正准入过的Query必须保持无成功结果，不能靠入口提前拒绝冒充并发提交保护。
            var rejected = await database.Queries.AsNoTracking().SingleAsync(item => item.IdempotencyKey == key);
            Assert.AreNotEqual("COMPLETED", rejected.ExecutionStatus);
            Assert.AreEqual(0, rejected.ResultCiphertext.Length);
        }
        finally
        {
            if (changed)
            {
                // 恢复同一合成连接走真实TLS probe和enable；不把DISABLED终态强行复活。
                current = await connections.HandleAsync(invocation, CancellationToken.None);
                view = (ConnectionView)current.Value;
                await connections.HandleAsync(invocation with { Operation = "test", Etag = current.Etag,
                    Body = new ConnectionMutationCommand { Command = Command(view.ConfigRevision) } }, CancellationToken.None);
                current = await connections.HandleAsync(invocation, CancellationToken.None);
                view = (ConnectionView)current.Value;
                await connections.HandleAsync(invocation with { Operation = "enable", Etag = current.Etag,
                    Body = new ConnectionMutationCommand { Command = Command(view.ConfigRevision) } }, CancellationToken.None);
            }
        }
    }

    /// <summary>固定合成编辑用途，随机命令和幂等标识不会覆盖既有业务命令。</summary>
    private static CommandContext Command(long revision) => new() { CommandId = Guid.NewGuid().ToString(), IdempotencyKey = Guid.NewGuid().ToString(),
        ExpectedRevision = revision, Reason = "M4 synthetic in-flight binding verification" };

    /// <summary>仅替换真实源返回后的合成调度点，所有读取和历史ACL检查委托正式适配器。</summary>
    private sealed class AfterReadSource(IG4SourceQueryReader actual, Func<CancellationToken, Task> afterRead) : IG4SourceQueryReader
    {
        /// <summary>一次执行只注入一次绑定变化。</summary>
        private int invoked;

        /// <summary>完整权限投影直接来自正式映射读取器。</summary>
        public G4QueryProjection DescribeProjection(G4QueryBindingContext context, string entityBindingId) => actual.DescribeProjection(context, entityBindingId);

        /// <summary>历史ACL核验完全委托正式服务，不改写结果。</summary>
        public Task<G4QueryConnectionAccess> VerifyAccessAsync(G4QueryBindingContext context, MappingAuthorizationProof proof, string entityBindingId,
            DateTimeOffset deadlineAtUtc, CancellationToken cancellationToken) => actual.VerifyAccessAsync(context, proof, entityBindingId, deadlineAtUtc, cancellationToken);

        /// <summary>取得真实PG行及回执后才改变当前绑定，随后返回原读取事实。</summary>
        public async Task<G4SourceQueryRead> ReadAsync(G4QueryBindingContext context, MappingAuthorizationProof proof, string entityBindingId,
            G4SemanticQuery query, DateTimeOffset deadlineAtUtc, CancellationToken cancellationToken, G4QueryBranchFilter? branch = null)
        {
            // 真实PG返回值保持原样，故障仅改变返回后的调度。
            var read = await actual.ReadAsync(context, proof, entityBindingId, query, deadlineAtUtc, cancellationToken, branch);
            Assert.IsTrue(read.Rows.Length > 0);
            if (Interlocked.Increment(ref invoked) == 1) await afterRead(cancellationToken);
            return read;
        }
    }

}
