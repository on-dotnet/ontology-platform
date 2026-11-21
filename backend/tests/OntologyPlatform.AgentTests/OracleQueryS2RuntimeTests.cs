using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.SemanticQuery;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.AgentTests;

/// <summary>Oracle 本批真实四角色票据和已发布双表的在途激活验证，禁止借用其他任务配置。</summary>
public sealed partial class G4QueryMafRuntimeTests
{
    /// <summary>同一真实查询源读取之后完成正式B及A激活，原五秒期限内拒绝陈旧提交。</summary>
    [TestMethod]
    public Task OracleActivationRevisionRejectsInflightQuery() => OracleCurrentRuntimeAsync(true);

    /// <summary>正式连接编辑发生在同一查询源读取后，原截止内拒绝旧版本提交。</summary>
    [TestMethod]
    public Task OracleConnectionRevisionRejectsInflightQuery() => OracleCurrentRuntimeAsync(false);

    /// <summary>当前四角色票据与真实DI的共用入口，不替代任何正式安全参与者。</summary>
    private static async Task OracleCurrentRuntimeAsync(bool mappingAba)
    {
        Assert.AreEqual("G4-ORACLE-MAPPING-QUERY-001:product-resume-01", Environment.GetEnvironmentVariable("G4_QUERY_RUNTIME_TEST"));
        // 只消费当前替代API已经核定的只读配置和密钥环挂载。
        await using var app = OntologyPlatform.Api.PlatformApiHost.CreateApplication([], builder =>
        {
            builder.Logging.ClearProviders();
            builder.Configuration.AddJsonFile("/private/api/appsettings.json", optional: false);
        });
        // 实际治理数据库必须是本任务内网服务，不允许外部连接串替换。
        var target = new Npgsql.NpgsqlConnectionStringBuilder(app.Configuration.GetConnectionString("governance"));
        Assert.IsTrue(target.Host == "platform-pg" && target.Port == 5432 && target.Database == "mapping"
            && target.SslMode == Npgsql.SslMode.VerifyFull && app.Configuration["Security:KeyRingPath"] == "/keyring");
        // 当前浏览器密文只存在输入管道与本进程内存中。
        using var envelope = JsonDocument.Parse(await Console.In.ReadToEndAsync());
        // 与正式HTTP相同的Cookie和票据解析器。
        var options = app.Services.GetRequiredService<Microsoft.Extensions.Options.IOptionsMonitor<Microsoft.AspNetCore.Authentication.Cookies.CookieAuthenticationOptions>>().Get("Cookies");
        // 角色仅选择参与者，真实主体与权限仍由服务器票据和当前授权决定。
        var participants = new Dictionary<string, (ActorContext Actor, string Session)>(StringComparer.Ordinal);
        foreach (var participant in envelope.RootElement.GetProperty("roles").EnumerateArray()) // 四个真实登录会话，禁止客户端角色构造。
        {
            // 从正式保护票据取得准确服务器会话引用，永不输出。
            var key = options.TicketDataFormat.Unprotect(participant.GetProperty("cookie").GetString()!)?.Principal.FindFirst("Microsoft.AspNetCore.Authentication.Cookies-SessionId")?.Value;
            Assert.IsFalse(string.IsNullOrWhiteSpace(key));
            // 正式存储重新检查撤销和过期状态。
            var ticket = await options.SessionStore!.RetrieveAsync(key!);
            Assert.IsNotNull(ticket);
            // 主体来源于正式 Claims，不接受传入的权限声明。
            var actor = OntologyPlatform.Api.G2.G2Authorization.CreateActor(new Microsoft.AspNetCore.Http.DefaultHttpContext { User = ticket.Principal });
            Assert.AreEqual(participant.GetProperty("subjectId").GetString(), actor.SubjectId);
            participants.Add(participant.GetProperty("role").GetString()!, (actor, key!));
        }
        Assert.AreEqual(4, participants.Values.Select(row => row.Actor.SubjectId).Distinct(StringComparer.Ordinal).Count());
        Assert.AreEqual("5af20722-3900-4de9-b23a-7dcae3ca5927", participants["A"].Actor.SubjectId);
        Assert.AreEqual("650199ae-8bd4-430a-885d-71cd69b6781e", participants["B"].Actor.SubjectId);
        Assert.AreEqual("bcf7f7f8-6af0-4f94-a28c-1220461ee62e", participants["C"].Actor.SubjectId);
        Assert.AreEqual("f902a743-7079-4e22-a643-a51deb027e89", participants["Q"].Actor.SubjectId);
        // 独立作用域使用正式服务，不启动额外宿主或后台任务。
        await using var scope = app.Services.CreateAsyncScope();
        // 查询原件必须属于当前viewer同一服务器会话。
        await using var db = await scope.ServiceProvider.GetRequiredService<IDbContextFactory<G4QueryDbContext>>().CreateDbContextAsync();
        // 准确queryId仅定位本次先行健康读，不扫描其他主体业务。
        var queryId = envelope.RootElement.GetProperty("queryId").GetString()!;
        // 当前完整查询由正式HTTP生成并已持久化。
        var original = await db.Queries.AsNoTracking().SingleAsync(row => row.Id == queryId);
        Assert.AreEqual("COMPLETED", original.ExecutionStatus);
        Assert.AreEqual(participants["Q"].Actor.SubjectId, original.SubjectId);
        // 失败输出只能说明归属不符；MSTest 的值比较会将两个服务器会话引用写入双流。
        Assert.IsTrue(string.Equals(participants["Q"].Session, original.SessionReference, StringComparison.Ordinal),
            "Oracle 查询原件与本轮 reader 会话不一致。");
        // 用正式类型与规范编码闭合当前 HTTP 请求和准确持久行，选择上下文包含在散列内。
        var seedQuery = envelope.RootElement.GetProperty("query").Deserialize<G4SemanticQuery>(G4QueryJson.Options)!;
        Assert.AreEqual("g4_traverse_relationships", seedQuery.CapabilityId);
        Assert.IsNull(seedQuery.Filters.EntityIri);
        Assert.AreEqual("omq-entity-1", seedQuery.Filters.EntityExternalId);
        Assert.AreEqual(5000, seedQuery.TimeoutMs);
        // 健康查询的规范请求独立于存储重新计算，原字节和索引均须匹配。
        var requestHash = G4QueryCanonical.Hash(G4QueryCanonical.Serialize(new { query = seedQuery, selectionQueryId = (string?)null }));
        Assert.AreEqual(requestHash, G4QueryCanonical.Hash(original.RequestBytes));
        Assert.AreEqual(requestHash, original.RequestHash);
        Assert.AreEqual(envelope.RootElement.GetProperty("resultHash").GetString(), original.ResultHash);
        // 原件只保留摘要；当前正式会话引用始终留在进程内。
        var seedReceipt = new { queryId, requestHash, resultHash = original.ResultHash, subjectId = original.SubjectId,
            sessionHash = G4QueryCanonical.Hash(System.Text.Encoding.UTF8.GetBytes(participants["Q"].Session)) };
        if (mappingAba)
            await MappingAbaAfterRealReadAsync(scope.ServiceProvider, participants["Q"].Actor, original, db,
                envelope.RootElement.GetProperty("proposalId").GetString()!, participants["A"], participants["C"], participants["B"].Actor.SubjectId, participants["B"], seedReceipt);
        else
            await OracleConnectionRevisionAsync(scope.ServiceProvider, participants["Q"].Actor, original, participants["A"], seedReceipt);
    }

    /// <summary>同一查询真实读取后以正式连接编辑推进修订，拒绝旧绑定并在拒绝后正常恢复连接状态。</summary>
    private static async Task OracleConnectionRevisionAsync(IServiceProvider services, ActorContext reader, G4QueryRecord original,
        (ActorContext Actor, string Session) editor, object seedReceipt)
    {
        // 正式连接处理器执行真实权限、ETag、配置修订和审计事务。
        var connections = services.GetRequiredService<IConnectionRequestHandler>();
        // 所有编辑命令只使用operator的当前正式会话，查询仍由viewer执行。
        var invocation = new ConnectionInvocation { Operation = "get", Actor = editor.Actor, SessionReference = editor.Session,
            Id = original.ConnectionId, ChildId = null, Body = null, Etag = null, Cursor = null, Type = null, State = null };
        // 紧前正式视图提供不可伪造的CAS版本。
        var before = await connections.HandleAsync(invocation, CancellationToken.None);
        // 原显示名称保持，唯一业务变更是正式编辑推进配置修订并回到待测试状态。
        var view = (ConnectionView)before.Value;
        Assert.AreEqual("ACTIVE", view.State);
        // 一次随机命令只定位本用例新执行，不复用旧Q作为在途执行。
        var key = Guid.NewGuid().ToString();
        // 实际健康Q已保存正式请求，用它发起全新但同固定计划的Q。
        using var request = JsonDocument.Parse(original.RequestBytes);
        // 预算及语义参数与先行健康请求一致。
        var query = request.RootElement.GetProperty("query").Deserialize<G4SemanticQuery>(G4QueryJson.Options)!;
        Assert.AreEqual(5000, query.TimeoutMs);
        // 四个关键事件仅保存合成身份、版本和时钟，不导出票据或配置秘密。
        var evidence = new Dictionary<string, object?> { ["taskId"] = "G4-ORACLE-MAPPING-QUERY-001", ["resourceRun"] = "product-resume-01",
            ["runtimeSeed"] = seedReceipt, ["case"] = "CONNECTION_AFTER_READ", ["status"] = "FAIL", ["connectionId"] = original.ConnectionId, ["subjectId"] = reader.SubjectId };
        // 真实单调计时覆盖原Gateway调用及拒绝，恢复连接发生在计时之后。
        var elapsed = new System.Diagnostics.Stopwatch();
        // 正式提交是否已发生决定是否需要执行同一连接的正常test和enable。
        var changed = false;
        // 三个事件都来自同一调度进程及同一Q。
        var events = new List<object>();
        // 记录当前真实时刻而非预期时刻，消费者另核严格顺序及原截止。
        void Record(string phase) => events.Add(new { phase, sequence = events.Count + 1, queryId = evidence["queryId"],
            connectionId = original.ConnectionId, utc = DateTimeOffset.UtcNow, monotonicMs = elapsed.Elapsed.TotalMilliseconds });
        // 真实Oracle源与后验已退出，再在正式最终提交检查之前执行竞争命令。
        var execution = BeforeCommitExecution(services, async token =>
        {
            // 新数据库上下文读取实际准入行，拒绝源前失败冒充在途反例。
            await using var db = await services.GetRequiredService<IDbContextFactory<G4QueryDbContext>>().CreateDbContextAsync(token);
            // 只选本次随机key对应的准入Q。
            var running = await db.Queries.AsNoTracking().SingleAsync(row => row.IdempotencyKey == key, token);
            Assert.AreEqual("RUNNING", running.ExecutionStatus);
            // 正式绑定来自准入持久状态，不能用当前连接替代旧capture。
            var captured = G4QueryResultStore.ReadState(running).Binding;
            Assert.AreEqual(view.ConfigRevision.ToString(System.Globalization.CultureInfo.InvariantCulture), captured.ConnectionRevision);
            Assert.AreEqual(original.ConnectionId, captured.ConnectionId);
            Assert.IsFalse(string.IsNullOrWhiteSpace(running.LeaseOwner));
            Assert.IsTrue(running.Fence > 0);
            evidence["queryId"] = running.Id;
            evidence["mappingId"] = captured.MappingId;
            evidence["oldRevision"] = view.ConfigRevision;
            evidence["admittedAtUtc"] = running.CreatedAtUtc;
            evidence["deadlineAtUtc"] = running.DeadlineAtUtc;
            evidence["leaseOwnerHash"] = G4QueryCanonical.Hash(System.Text.Encoding.UTF8.GetBytes(running.LeaseOwner!));
            evidence["fence"] = running.Fence;
            Record("SOURCE_READ_COMPLETED");
            // 使用正常连接命令的真实审批范围，保持地址、凭据和显示名称不变。
            var reply = await connections.HandleAsync(invocation with { Operation = "patch", Etag = before.Etag,
                Body = new ConnectionPatchRequest { DisplayName = view.DisplayName, Command = Command(view.ConfigRevision) } }, token);
            changed = true;
            // 只记录公开版本和状态，不保存连接凭据字段。
            var updated = (ConnectionView)reply.Value;
            Assert.AreEqual(200, reply.StatusCode);
            Assert.AreEqual(view.ConfigRevision + 1, updated.ConfigRevision);
            Assert.AreEqual(view.SecretVersion, updated.SecretVersion);
            evidence["newRevision"] = updated.ConfigRevision;
            evidence["changedState"] = updated.State;
            Record("CONNECTION_PATCH_COMMITTED");
        });
        // 与HTTP/MCP/UI共享正式Gateway及不可重置绝对截止。
        var gateway = ActivatorUtilities.CreateInstance<SemanticGateway>(services, execution);
        try
        {
            elapsed.Start();
            // 接受既有连接状态或旧修订错误合同，不接受普通超时或提前拒绝。
            var error = await Assert.ThrowsAsync<SemanticOperationException>(() =>
                gateway.ExecuteG4Async(reader, original.SessionReference, query, key, null, CancellationToken.None));
            Record("COMMIT_REJECTED");
            elapsed.Stop();
            Assert.IsTrue(changed && (error.Status, error.Code) is (409, "query_binding_stale") or (403, "query_forbidden"));
            Assert.IsTrue(elapsed.Elapsed.TotalMilliseconds < 5000);
            // 独立新上下文按准确Q核对结果、来源及审计原子性。
            await using var fresh = await services.GetRequiredService<IDbContextFactory<G4QueryDbContext>>().CreateDbContextAsync();
            // 本次查询终态可能由既有租约终结机制随后处理，不能称作成功。
            var rejected = await fresh.Queries.AsNoTracking().SingleAsync(row => row.IdempotencyKey == key);
            Assert.IsTrue(DateTimeOffset.UtcNow < rejected.DeadlineAtUtc);
            Assert.AreNotEqual("COMPLETED", rejected.ExecutionStatus);
            Assert.IsNull(rejected.ResultHash);
            Assert.AreEqual(0, rejected.ResultSize);
            Assert.AreEqual(0, rejected.ResultCiphertext.Length);
            Assert.AreEqual(0, G4QueryResultStore.ReadState(rejected).Receipts.Length);
            // 治理审计由单独数据库上下文读取同一Q。
            await using var governance = await services.GetRequiredService<IDbContextFactory<OntologyPlatform.Modules.Governance.GovernanceDbContext>>().CreateDbContextAsync();
            // 只有成功执行审计为零才可声明无成功副作用。
            var allowed = await governance.AuditRecords.CountAsync(row => row.Resource == rejected.Id && row.Action == "data.query.execute" && row.Outcome == "allowed");
            Assert.AreEqual(0, allowed);
            evidence["executionStatus"] = rejected.ExecutionStatus;
            evidence["errorStatus"] = error.Status;
            evidence["errorCode"] = error.Code;
            evidence["resultHash"] = rejected.ResultHash;
            evidence["resultSize"] = rejected.ResultSize;
            evidence["ciphertextBytes"] = rejected.ResultCiphertext.Length;
            evidence["committedReadReceipts"] = 0;
            evidence["successfulQueryAudits"] = allowed;
            evidence["status"] = "PASS";
        }
        finally
        {
            elapsed.Stop();
            evidence["elapsedMs"] = elapsed.Elapsed.TotalMilliseconds;
            evidence["events"] = events;
            try
            {
                if (changed)
                {
                    // 恢复只在原Q已拒绝后进行，保持递增配置修订，不能记成提交前ABA。
                    var current = await connections.HandleAsync(invocation, CancellationToken.None);
                    // 重新取得正式当前版本，随后正常测试真实TLS源连接。
                    var currentView = (ConnectionView)current.Value;
                    await connections.HandleAsync(invocation with { Operation = "test", Etag = current.Etag,
                        Body = new ConnectionMutationCommand { Command = Command(currentView.ConfigRevision) } }, CancellationToken.None);
                    current = await connections.HandleAsync(invocation, CancellationToken.None);
                    currentView = (ConnectionView)current.Value;
                    // 正常启用必须消费刚取得的实际测试结果。
                    var restored = await connections.HandleAsync(invocation with { Operation = "enable", Etag = current.Etag,
                        Body = new ConnectionMutationCommand { Command = Command(currentView.ConfigRevision) } }, CancellationToken.None);
                    Assert.AreEqual("ACTIVE", ((ConnectionView)restored.Value).State);
                    evidence["restoredRevision"] = ((ConnectionView)restored.Value).ConfigRevision;
                    evidence["restoredAtUtc"] = DateTimeOffset.UtcNow;
                }
            }
            finally
            {
                // 只写本次已登记临时目录，失败原件也由宿主执行器保存。
                var resultFile = Environment.GetEnvironmentVariable("OMQ_RUNTIME_REPORT")!;
                Assert.IsTrue(System.Text.RegularExpressions.Regex.IsMatch(resultFile, "^/tmp/omq-s23-[a-f0-9]{32}/connection-inflight[.]json$"));
                await File.WriteAllTextAsync(resultFile, JsonSerializer.Serialize(evidence, new JsonSerializerOptions(JsonSerializerDefaults.Web)) + "\n");
            }
        }
    }
}
