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
public sealed partial class G4QueryMafRuntimeTests
{
    /// <summary>通过标准Cookie格式和PG票据存储检查浏览器实际会话，输入仅经标准输入传入。</summary>
    [TestMethod]
    public async Task BrowserSessionsCoverRegisteredExecutionDeadline()
    {
        Assert.AreEqual("1", Environment.GetEnvironmentVariable("G4_BROWSER_PREFLIGHT"));
        // 仅当前合成M5身份可使用短检查。
        Assert.AreEqual("G4-M5-INTEGRATION-001:integration-01", Environment.GetEnvironmentVariable("G4_QUERY_RUNTIME_TEST"));
        // 使用既有只读运行配置构建正式DI，不启动宿主或后台任务。
        await using var app = OntologyPlatform.Api.PlatformApiHost.CreateApplication([], builder =>
        {
            builder.Logging.ClearProviders();
            builder.Configuration.AddJsonFile("/private/api/appsettings.json", optional: false);
        });
        // 两个参与者的当前Cookie仅存在进程内存，禁止输出原始输入。
        using var input = JsonDocument.Parse(await Console.In.ReadToEndAsync());
        // 使用正式认证scheme的格式和持久票据存储。
        var options = app.Services.GetRequiredService<Microsoft.Extensions.Options.IOptionsMonitor<Microsoft.AspNetCore.Authentication.Cookies.CookieAuthenticationOptions>>().Get("Cookies");
        // 180秒浏览器总命令上限加30秒预检界限，无无限TTL。
        var deadline = DateTimeOffset.UtcNow.AddSeconds(210);
        // 精确读取同一服务器会话的失效事实。
        await using var database = await app.Services.GetRequiredService<IDbContextFactory<OntologyPlatform.Modules.Governance.GovernanceDbContext>>().CreateDbContextAsync();
        // 仅收集非秘密前提观测，成功测试平台可能不转发Console输出。
        var observations = new List<object>();
        foreach (var item in input.RootElement.EnumerateArray())
        {
            // 使用与Cookie认证中间件相同的受保护引用解析路径。
            var reference = options.TicketDataFormat.Unprotect(item.GetProperty("cookie").GetString()!);
            // 原始会话键只用于内部准确定位。
            var key = reference?.Principal.FindFirst("Microsoft.AspNetCore.Authentication.Cookies-SessionId")?.Value;
            Assert.IsFalse(string.IsNullOrWhiteSpace(key));
            // 正式存储重新验证撤销及过期并解密原票据。
            var ticket = await options.SessionStore!.RetrieveAsync(key!);
            Assert.IsNotNull(ticket);
            Assert.AreEqual(item.GetProperty("subjectId").GetString(), ticket.Principal.FindFirst("sub")?.Value);
            Assert.IsTrue(ticket.Properties.ExpiresUtc > deadline);
            // 不读取或输出数据库中的保护票据字段。
            var session = await database.Sessions.Where(row => row.Id == key).Select(row => new { row.ExpiresAtUtc, row.RevokedAtUtc }).SingleAsync();
            Assert.IsNull(session.RevokedAtUtc);
            Assert.IsTrue(session.ExpiresAtUtc > deadline);
            observations.Add(new
            {
                @case = "M5_BROWSER_SESSION_READY",
                subjectId = item.GetProperty("subjectId").GetString(),
                session.ExpiresAtUtc,
                requiredUntilUtc = deadline,
                sessionHash = Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(key!)))
            });
        }
        // 只允许调用者预先登记的本任务临时目录内的固定报告名。
        var report = Environment.GetEnvironmentVariable("G4_BROWSER_REPORT")!;
        Assert.IsTrue(report.StartsWith("/tmp/m5-session-probe-", StringComparison.Ordinal) && Path.GetFileName(report) == "session-ready.json" && !report.Contains("..", StringComparison.Ordinal));
        await File.WriteAllTextAsync(report, JsonSerializer.Serialize(observations));
    }

    /// <summary>实际MAF恢复三次后拒绝第四次，真实PG只保存三个引用。</summary>
    [TestMethod]
    public async Task ActualMafUsesCurrentGatewayAndOnePersistentBudget()
    {
        Assert.IsTrue(Environment.GetEnvironmentVariable("G4_QUERY_RUNTIME_TEST") is "G4-M4-QUERY-001:query-impl-01" or "G4-M5-INTEGRATION-001:integration-01");
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
        // 只输出布尔资格，不输出会话引用、保护票据或密钥，供真实前提失败的短定位。
        await using var governance = await scope.ServiceProvider.GetRequiredService<Microsoft.EntityFrameworkCore.IDbContextFactory<OntologyPlatform.Modules.Governance.GovernanceDbContext>>().CreateDbContextAsync();
        // 精确关联当前查询的服务器记录，禁止用另一条活跃会话替换旧票据。
        var session = await governance.Sessions.SingleAsync(item => item.Id == row.SessionReference);
        // 在测试进程内复核正式purpose，仅打印各条件布尔值，不返回或保存票据正文。
        var readable = false;
        // 失败原因分开，不能以重新登录覆盖原失败。
        var claimsMatch = new Dictionary<string, bool>();
        try
        {
            // 与正式MappingSessionAuthority使用相同provider/purpose，不构造新的认证材料。
            var protector = Microsoft.AspNetCore.DataProtection.DataProtectionCommonExtensions.CreateProtector(scope.ServiceProvider.GetRequiredService<Microsoft.AspNetCore.DataProtection.IDataProtectionProvider>(), "OntologyPlatform.Governance.ServerTicket.v1");
            // 临时内存反序列化只用于确定正式匹配失败的具体条件。
            var ticket = Microsoft.AspNetCore.Authentication.TicketSerializer.Default.Deserialize(protector.Unprotect(session.ProtectedTicket))!;
            readable = true;
            claimsMatch["authenticated"] = ticket.Principal.Identity?.IsAuthenticated == true;
            claimsMatch["ticketLive"] = ticket.Properties.ExpiresUtc > DateTimeOffset.UtcNow;
            claimsMatch["ticketCoversExecution"] = ticket.Properties.ExpiresUtc > DateTimeOffset.UtcNow.AddSeconds(
                Environment.GetEnvironmentVariable("G4_QUERY_RUNTIME_TEST") == "G4-M5-INTEGRATION-001:integration-01" ? 80 : 0);
            claimsMatch["subject"] = ticket.Principal.FindFirst("sub")?.Value == actor.SubjectId;
            claimsMatch["organization"] = ticket.Principal.FindFirst("organization_id")?.Value == actor.OrganizationId;
            claimsMatch["sites"] = ticket.Principal.FindAll("site_ids").Select(claim => claim.Value).Distinct().Order().SequenceEqual(actor.SiteIds.Order());
            claimsMatch["roles"] = new[] { "platform.viewer", "platform.operator", "platform.auditor" }.Where(ticket.Principal.IsInRole).Order().SequenceEqual(actor.Roles.Order());
        }
        catch (System.Security.Cryptography.CryptographicException) { }
        Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new
        {
            @case = "M4_RUNTIME_AUTH_DIAGNOSTIC",
            readable,
            claimsMatch,
            sessionLive = session.RevokedAtUtc is null && session.ExpiresAtUtc > DateTimeOffset.UtcNow,
            ticketMatches = scope.ServiceProvider.GetRequiredService<IMappingSessionAuthority>().Matches(session.ProtectedTicket, actor, DateTimeOffset.UtcNow)
        }));
        if (Environment.GetEnvironmentVariable("G4_QUERY_AUTH_DIAGNOSTIC") == "1")
        {
            // 只读正式key元数据并在内存创建解密器，绝不输出ID、XML或秘密内容。
            var keys = scope.ServiceProvider.GetRequiredService<Microsoft.AspNetCore.DataProtection.KeyManagement.IKeyManager>().GetAllKeys();
            // 标准DataProtection封套的key标识只用于内部查找，输出仅为是否存在。
            var keyId = new Guid(session.ProtectedTicket.AsSpan(4, 16));
            // 精确引用可区分挂载缺失与密钥无法解封；诊断模式永远不充当PASS。
            var matching = keys.SingleOrDefault(item => item.KeyId == keyId);
            // 不记录异常正文，防止无意输出密钥材料。
            var encryptorReady = false;
            try { encryptorReady = matching?.CreateEncryptor() is not null; } catch (System.Security.Cryptography.CryptographicException) { }
            Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new
            {
                @case = "M4_KEY_METADATA_DIAGNOSTIC",
                discriminatorMatches = scope.ServiceProvider.GetRequiredService<Microsoft.Extensions.Options.IOptions<Microsoft.AspNetCore.DataProtection.DataProtectionOptions>>().Value.ApplicationDiscriminator == "OntologyPlatform.PlatformBff.v1",
                keysAvailable = keys.Count > 0,
                referencedKeyAvailable = matching is not null,
                encryptorReady
            }));
            Assert.Fail("DIAGNOSTIC_ONLY_NOT_ACCEPTANCE");
        }
        // 当前M5在正式读取之前明确拒绝原会话期限不足，避免其它权限错误掩盖本反例。
        var readyUntil = DateTimeOffset.UtcNow.AddSeconds(Environment.GetEnvironmentVariable("G4_QUERY_RUNTIME_TEST") == "G4-M5-INTEGRATION-001:integration-01" ? 80 : 0);
        if (Environment.GetEnvironmentVariable("G4_QUERY_RUNTIME_TEST") == "G4-M5-INTEGRATION-001:integration-01")
        {
            Assert.IsTrue(session.RevokedAtUtc is null && session.ExpiresAtUtc > readyUntil, "PREREQUISITE_STALE:query_session_deadline");
        }
        try { _ = await gateway.ReadG4Async(actor, row.SessionReference, queryId!, true, CancellationToken.None); }
        catch (SemanticOperationException error) { Assert.Fail("真实Gateway前提失败：" + error.Status + ":" + error.Code); }
        // 短前提使用同一精确查询服务器会话，不能用刚登录的新会话替代旧引用。
        if (Environment.GetEnvironmentVariable("G4_QUERY_PREFLIGHT_ONLY") == "1" || Environment.GetEnvironmentVariable("G4_QUERY_RUNTIME_TEST") == "G4-M5-INTEGRATION-001:integration-01")
        {
            Assert.IsTrue(readable && claimsMatch.Values.All(value => value));
            Assert.IsTrue(session.RevokedAtUtc is null && session.ExpiresAtUtc > readyUntil);
            Assert.IsTrue(scope.ServiceProvider.GetRequiredService<IMappingSessionAuthority>().Matches(session.ProtectedTicket, actor, DateTimeOffset.UtcNow));
            if (Environment.GetEnvironmentVariable("G4_QUERY_ABA_PROPOSAL") is { Length: > 0 } readyProposalId)
            {
                // 正式服务读取已批准B及准确审核证明，不执行激活或改写审核会话。
                var mappings = scope.ServiceProvider.GetRequiredService<MappingApplicationService>();
                // 必须仍为待激活的正式批准提案。
                var approved = await mappings.ReadProposalAsync(actor, row.SessionReference, readyProposalId, CancellationToken.None);
                Assert.AreEqual("APPROVED", approved.Status);
                Assert.IsTrue(approved.ExpiresAtUtc > readyUntil);
                // 当前指针与B的原批准基线完全相同，旧activation不得进入长链。
                var active = await mappings.ReadActiveAsync(actor, row.SessionReference, approved.MappingId, CancellationToken.None);
                Assert.AreEqual(approved.ExpectedActive.ReleaseId, active.MappingReleaseId);
                Assert.AreEqual(approved.ExpectedActive.ActivationRevision, active.ActivationRevision);
                // 同一模块上下文只读精确提案保存的原证明。
                await using var connections = await scope.ServiceProvider.GetRequiredService<IDbContextFactory<ConnectionsDbContext>>().CreateDbContextAsync();
                // 真实异人审核会话来自已保存决策，禁止伪造角色。
                var proposal = await connections.MappingProposals.AsNoTracking().SingleAsync(item => item.Id == readyProposalId);
                // 授权服务重新检查原审核会话和当前完整权限。
                var approval = JsonSerializer.Deserialize<MappingAuthorizationProof>(proposal.DecisionProofJson!, G4MappingJson.Options)!;
                Assert.AreNotEqual(actor.SubjectId, approval.Actor.SubjectId);
                // 原提交证明与审核证明一起复核，不能重捕获刷新其期限或epoch。
                var submit = JsonSerializer.Deserialize<MappingAuthorizationProof>(proposal.SubmitProofJson, G4MappingJson.Options)!;
                // 当前执行者的管理权限仍通过正式治理服务捕获，不能沿用提交者角色。
                _ = await scope.ServiceProvider.GetRequiredService<IMappingAuthorizationAuthority>().CaptureAsync(submit with
                {
                    Actor = actor,
                    SessionReference = row.SessionReference,
                    Permission = "mapping.activate",
                    ConnectionId = null,
                    ObjectRefs = [],
                    FieldRefs = [],
                    AuthorizationEpoch = 0
                }, CancellationToken.None);
                // 与正式激活一致的物理事务，结束即回滚，只检查原证明。
                await using var transaction = await connections.Database.BeginTransactionAsync();
                // 正式治理参与者保持组织锁、会话票据和完整当前grant语义。
                var authority = scope.ServiceProvider.GetRequiredService<IMappingAuthorizationAuthority>();
                // 按主体、会话及权限排序复核原证明，保持正式组织锁顺序。
                foreach (var proof in new[] { submit, approval }.OrderBy(item => item.Actor.SubjectId, StringComparer.Ordinal).ThenBy(item => item.SessionReference, StringComparer.Ordinal).ThenBy(item => item.Permission, StringComparer.Ordinal))
                {
                    // 原提交与异人审核会话必须覆盖同一执行界限，保留原会话引用。
                    var proofSession = await governance.Sessions.AsNoTracking().SingleAsync(item => item.Id == proof.SessionReference);
                    Assert.IsTrue(proofSession.RevokedAtUtc is null && proofSession.ExpiresAtUtc > readyUntil);
                    await authority.DemandInTransactionAsync(proof, connections.Database.GetDbConnection(), Microsoft.EntityFrameworkCore.Storage.DbContextTransactionExtensions.GetDbTransaction(transaction), CancellationToken.None);
                }
            }
            Console.WriteLine("M5_RUNTIME_PREREQUISITE_READY_NOT_PRODUCT_ACCEPTANCE");
            if (Environment.GetEnvironmentVariable("G4_QUERY_PREFLIGHT_ONLY") == "1")
            {
                return;
            }
        }
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
        // 仅显式准备的精确提案触发在途ABA，独立资格还要求实际案例原件。
        if (Environment.GetEnvironmentVariable("G4_QUERY_ABA_PROPOSAL") is { Length: > 0 } proposalId)
            await MappingAbaAfterRealReadAsync(scope.ServiceProvider, actor, row, database, proposalId);
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
            Console.WriteLine(JsonSerializer.Serialize(new { @case = "BINDING_AFTER_READ_DIAGNOSTIC", changed, error.Status, error.Code }));
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
