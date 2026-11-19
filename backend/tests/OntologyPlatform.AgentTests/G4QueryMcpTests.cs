using System.Diagnostics;
using MySqlConnector;
using OntologyPlatform.Modules.Publishing;
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
    /// <summary>在本任务真实四主体会话中，测试一条已读取 Doris 实体的查询经历两次正式激活。</summary>
    [TestMethod]
    public Task DorisActivationRevisionRejectsInflightQuery() => RunDorisRaceAsync("aba");

    /// <summary>真实 Doris 读取返回后撤执行权限，原查询的提交与审计都须拒绝。</summary>
    [TestMethod]
    public Task DorisRevocationRejectsInflightQuery() => RunDorisRaceAsync("grant");

    /// <summary>真实源读取完成后使当前合成 Q 会话到期，提交须拒绝且原期限须准确恢复。</summary>
    [TestMethod]
    public Task DorisExpiredSessionRejectsInflightQuery() => RunDorisRaceAsync("session");

    /// <summary>固定实体读取返回后、目录后验发出前，对同一合成目录执行真实列改名。</summary>
    [TestMethod]
    public Task DorisTableChangeRejectsInflightRows() => RunDorisRaceAsync("ddl");

    /// <summary>在真实实体读取之后用 A 的正式会话轮换该合成连接的秘密版本。</summary>
    [TestMethod]
    public Task DorisRotatedCredentialRejectsInflightQuery() => RunDorisRaceAsync("rotate");

    /// <summary>在正常 Doris 读取后只锁本次查询行，实测最终提交对五秒总期限的处理。</summary>
    [TestMethod]
    public Task DorisLockedCommitHonorsRealDeadline() => RunDorisRaceAsync("deadline");

    /// <summary>平台库自身的短锁等待先于总期限耗尽时，准确返回登记的拒绝。</summary>
    [TestMethod]
    public Task DorisCommitRejectsPlatformLockTimeout() => RunDorisRaceAsync("lock");

    /// <summary>真实数据行已读完时中断本次源连接，后验失败不得交付旧行或 EMPTY。</summary>
    [TestMethod]
    public Task DorisDroppedConnectionDiscardsUnverifiedRows() => RunDorisRaceAsync("disconnect");

    /// <summary>在正式取消路径验证真实发布对象受损、槽位或快照错配及当前授权拒绝。</summary>
    [TestMethod]
    public Task CancelRequiresSingleVerifiedReleaseBatch() => RunDorisRaceAsync("batch");

    /// <summary>只调度一次真实查询的首个源分支，供另一正式 HTTP 请求在 BE 活动时提交取消。</summary>
    [TestMethod]
    public Task DorisSourceOverlapsVerifiedCancellation() => RunDorisRaceAsync("overlap");

    /// <summary>使用正式宿主和服务器票据，仅在受控的竞争阶段切换授权或版本。</summary>
    private static async Task RunDorisRaceAsync(string scenario)
    {
        Assert.AreEqual("G4-DORIS-MAPPING-QUERY-001:implementation-01", Environment.GetEnvironmentVariable("G4_QUERY_RUNTIME_TEST"));
        // 只加载本任务现有受限运行配置，实际源和平台适配器均由正式宿主组合。
        var root = DorisRuntimeRoot();
        Assert.IsTrue(File.Exists(Path.Combine(root, "docs/tasks/G4-DORIS-MAPPING-QUERY-001.md")));
        // 与已准入 API 相同的运行目录、证书和平台地址。
        var config = Path.Combine(root, ".tools/security/g4-doris-mapping-query-001/implementation-01/runtime/api/appsettings.json");
        await using var app = OntologyPlatform.Api.PlatformApiHost.CreateApplication([], builder =>
        {
            builder.Logging.ClearProviders();
            builder.Configuration.AddJsonFile(config, optional: false);
        });
        Assert.AreEqual("Development", app.Environment.EnvironmentName);
        // 四个刚登录的浏览器会话只经标准输入传入，不写入回执。
        using var envelope = JsonDocument.Parse(await Console.In.ReadToEndAsync());
        // 使用正式 Cookie scheme 的密文解封及平台票据读取。
        var options = app.Services.GetRequiredService<Microsoft.Extensions.Options.IOptionsMonitor<Microsoft.AspNetCore.Authentication.Cookies.CookieAuthenticationOptions>>().Get("Cookies");
        // 角色名称只用于选取合成参与者，真实身份及权限来自已验证服务器票据。
        var participants = new Dictionary<string, (ActorContext Actor, string Session)>(StringComparer.Ordinal);
        foreach (var participant in envelope.RootElement.GetProperty("roles").EnumerateArray())
        {
            // 根据浏览器密文定位同一条正式服务器会话。
            var key = options.TicketDataFormat.Unprotect(participant.GetProperty("cookie").GetString()!)?.Principal.FindFirst("Microsoft.AspNetCore.Authentication.Cookies-SessionId")?.Value;
            Assert.IsFalse(string.IsNullOrWhiteSpace(key));
            // 正式存储拒绝撤销或到期会话。
            var ticket = await options.SessionStore!.RetrieveAsync(key!);
            Assert.IsNotNull(ticket);
            // 正常 HTTP 授权路径从服务器 Claims 生成实际 ActorContext。
            var actor = OntologyPlatform.Api.G2.G2Authorization.CreateActor(new Microsoft.AspNetCore.Http.DefaultHttpContext { User = ticket.Principal });
            Assert.AreEqual(participant.GetProperty("subjectId").GetString(), actor.SubjectId);
            participants.Add(participant.GetProperty("role").GetString()!, (actor, key!));
        }
        Assert.AreEqual(4, participants.Values.Select(p => p.Actor.SubjectId).Distinct(StringComparer.Ordinal).Count());
        // 读取当前查询引用，和同一次真实 Q 会话直接关联。
        var queryId = envelope.RootElement.GetProperty("queryId").GetString()!;
        // B 的真实审批提案由刚完成的浏览器准备流程给出。
        var proposalId = scenario == "aba" ? envelope.RootElement.GetProperty("proposalId").GetString() : null;
        // 只启动正式应用服务所需的作用域，没有另起宿主或修改运行结构。
        await using var scope = app.Services.CreateAsyncScope();
        // 用单独平台库上下文按准确 queryId 定位受控前件。
        await using var db = await scope.ServiceProvider.GetRequiredService<IDbContextFactory<G4QueryDbContext>>().CreateDbContextAsync();
        // Q 必须是先前真实读取的实际主体及会话。
        var original = await db.Queries.AsNoTracking().SingleAsync(q => q.Id == queryId);
        Assert.AreEqual("COMPLETED", original.ExecutionStatus);
        Assert.AreEqual(participants["Q"].Actor.SubjectId, original.SubjectId);
        if (scenario == "overlap")
        {
            // 原记录仅提供当前 Q 已执行的固定查询模板，新请求始终使用刚核验的当前会话。
            await RunOverlappingSourceAsync(scope.ServiceProvider, participants["Q"].Actor, participants["Q"].Session,
                original, envelope.RootElement.GetProperty("key").GetGuid());
            return;
        }
        Assert.IsTrue(participants["Q"].Session == original.SessionReference, "DORIS_QUERY_SESSION_MISMATCH");
        if (scenario == "aba")
            await MappingAbaAfterRealReadAsync(scope.ServiceProvider, participants["Q"].Actor, original, db, proposalId!,
                participants["A"], participants["C"], participants["B"].Actor.SubjectId);
        else if (scenario == "batch")
            await VerifyCancelBatchFaultsAsync(scope.ServiceProvider, participants["Q"].Actor, original);
        else if (scenario is "deadline" or "lock")
            await VerifyContendedCommitDeadlineAsync(scope.ServiceProvider, participants["Q"].Actor, original, db, scenario == "deadline");
        else if (scenario == "rotate")
            await RotateDorisDuringCommitAsync(scope.ServiceProvider, participants["Q"].Actor, participants["A"], original, db, envelope.RootElement.GetProperty("rotation"));
        else if (scenario is "ddl" or "disconnect")
            await VerifyDorisPostcheckFailureAsync(scope.ServiceProvider, participants["Q"].Actor, original, db, scenario == "disconnect");
        else
            await DenyDorisCommitAfterReadAsync(scope.ServiceProvider, participants["Q"].Actor, original, db, scenario == "session");
    }

    /// <summary>等待独立观察者确认取消事务已到达准确行锁，然后调用原源读取器。</summary>
    private static async Task RunOverlappingSourceAsync(IServiceProvider services, ActorContext actor, string session,
        G4QueryRecord original, Guid key)
    {
        // 原发布绑定及五秒请求体来自先前持久化的正式请求。
        using var document = JsonDocument.Parse(original.RequestBytes);
        // 压力试验使用已批准的全表有序实体投影，不使用任何人工 SQL 延迟。
        var previous = document.RootElement.GetProperty("query").Deserialize<G4SemanticQuery>(G4QueryJson.Options)!;
        Assert.AreEqual("g4_resolve_entity", previous.CapabilityId);
        Assert.AreEqual(5000, previous.TimeoutMs);
        // 只清除外部身份过滤，沿用登记的组织及站点。
        var query = previous with { Filters = new G4QueryFilters { SiteId = "site-a" }, RelationshipIris = [] };
        // 准确键对应只含时序事实的临时许可文件。
        var directory = Path.Combine(DorisRuntimeRoot(), "artifacts/workflow/G4-DORIS-MAPPING-QUERY-001/implementation-01");
        // 保存同一分支的真实单调时钟，包含等待同步点的时间。
        var branch = new Stopwatch();
        // 驱动输出握手、准确计划和清理事件，独立旁路用真实 FE 连接号对账。
        using var trace = new Activity("dmq.verified.overlap").Start();
        // 源返回时保存耗时，上层观察器释放和网关返回以更保守的全段上界验证。
        var readMs = 0d;
        // 唯一允许改变的部分是执行调度，权鉴、租约观察、命令和取消均委托正式实现。
        var source = new ScheduledSource(services.GetRequiredService<IG4SourceQueryReader>(), async token =>
        {
            branch.Start();
            // 此文件只能由已确认正式取消事务确在等待该行锁的独立观察者产生。
            var permit = Path.Combine(directory, "overlap-permit-" + key + ".json");
            while (!File.Exists(permit) && branch.ElapsedMilliseconds < 550) await Task.Delay(1, token);
            Assert.IsTrue(File.Exists(permit), "CANCEL_TRANSACTION_DID_NOT_REACH_ROW");
        }, () => readMs = branch.Elapsed.TotalMilliseconds);
        // 独立执行实例与 HTTP 宿主各用正式平台服务及同一数据库。
        var execution = ActivatorUtilities.CreateInstance<G4QueryExecution>(services, source, TimeProvider.System);
        // 仍由正式语义网关重新核权限及发布绑定。
        var gateway = ActivatorUtilities.CreateInstance<SemanticGateway>(services, execution);
        // 度量从完整执行请求开始至错误返回的实际耗时。
        var elapsed = Stopwatch.StartNew();
        try
        {
            await gateway.ExecuteG4Async(actor, session, query, key.ToString(), null, CancellationToken.None);
            Assert.Fail("CANCELLED_SOURCE_RETURNED_SUCCESS");
        }
        catch (SemanticOperationException error)
        {
            // 仅输出绑定、稳定错误和耗时，供跨进程见证核对。
            var events = trace.Events.Where(e => e.Name.StartsWith("doris.", StringComparison.Ordinal))
                .Select(e => new { e.Name, e.Timestamp, tags = e.Tags.Where(t => t.Key is "thread" or "source.thread" or "auxiliary.thread" or "template.sha256").ToDictionary(t => t.Key, t => t.Value) }).ToArray();
            // 原错误按稳定码记录，平台持久状态、同一 BE 取消及清理预算由独立旁路分别判定。
            var result = new { key, error.Status, error.Code, readMs, branchMs = branch.Elapsed.TotalMilliseconds, elapsedMs = elapsed.Elapsed.TotalMilliseconds, events };
            await File.WriteAllTextAsync(Path.Combine(directory, "overlap-execute-" + key + ".json"), JsonSerializer.Serialize(result, G4QueryJson.Options));
            Assert.IsTrue((error.Status, error.Code) is (409, "query_execution_stale") or (503, "query_timeout"));
            Assert.IsTrue(events.Any(e => e.Name == "doris.plan.submitted") && events.Any(e => e.Name == "doris.kill.acknowledged")
                && events.Any(e => e.Name == "doris.driver.ended"));
            Assert.IsTrue(branch.Elapsed.TotalMilliseconds is > 0 and <= 1000 && result.elapsedMs <= 5000);
        }
    }

    /// <summary>在分支的真实期限内调度读取开始，并记录真实读取释放时刻。</summary>
    private sealed class ScheduledSource(IG4SourceQueryReader actual, Func<CancellationToken, Task> wait, Action finished) : IG4SourceQueryReader
    {
        /// <summary>沿用真实字段投影。</summary>
        public G4QueryProjection DescribeProjection(G4QueryBindingContext context, string entityBindingId) => actual.DescribeProjection(context, entityBindingId);

        /// <summary>沿用真实当前字段访问检查。</summary>
        public Task<G4QueryConnectionAccess> VerifyAccessAsync(G4QueryBindingContext context, MappingAuthorizationProof proof, string entityBindingId,
            DateTimeOffset deadlineAtUtc, CancellationToken cancellationToken) => actual.VerifyAccessAsync(context, proof, entityBindingId, deadlineAtUtc, cancellationToken);

        /// <summary>调度等待与原源访问共用同一绝对截止及平台产生的令牌。</summary>
        public async Task<G4SourceQueryRead> ReadAsync(G4QueryBindingContext context, MappingAuthorizationProof proof, string entityBindingId,
            G4SemanticQuery query, DateTimeOffset deadlineAtUtc, CancellationToken cancellationToken, G4QueryBranchFilter? branch = null)
        {
            try
            {
                await wait(cancellationToken);
                return await actual.ReadAsync(context, proof, entityBindingId, query, deadlineAtUtc, cancellationToken, branch);
            }
            finally { finished(); }
        }
    }

    /// <summary>在真实 PG、RustFS 与 Fuseki 的只读结果上注入单项故障，各次取消须单独重新核验。</summary>
    private static async Task VerifyCancelBatchFaultsAsync(IServiceProvider services, ActorContext reader, G4QueryRecord original)
    {
        // 准确资产和发布来自该 Q 已成功执行的固定实体查询。
        using var doc = JsonDocument.Parse(original.RequestBytes);
        // 不在测试中重建本体或 Mapping 快照。
        var query = doc.RootElement.GetProperty("query").Deserialize<G4SemanticQuery>(G4QueryJson.Options)!;
        // 只损坏一次请求中已经真实回读的 Turtle 对象，不改底层不可变字节。
        var storage = new CorruptSourceRead(services.GetRequiredService<IReleaseArtifactStore>());
        // 使用原发布目录、正式 DB 上下文、原图核验；只置换故障对象读取边界。
        var guarded = new PublishingCatalog(services.GetRequiredService<PublishingDbContext>(),
            new ReleaseVerifier(storage,services.GetRequiredService<ISemanticRuntime>()));
        // 精确范围缺失时在访问 S3/Jena 前拒绝。
        var forbidden = await Assert.ThrowsAsync<SemanticOperationException>(() =>
            guarded.ReadVerifiedBatchAsync(reader with { SiteIds=[] },query.AssetId,query.OntologyReleaseId,default));
        Assert.AreEqual((403,"scope_denied"),(forbidden.Status,forbidden.Code));
        Assert.AreEqual(0,storage.Reads);
        // 当前范围恢复后真正读取 RustFS，原始 PG 字节比较必须捕捉到这次故障。
        var damaged = await Assert.ThrowsAsync<SemanticOperationException>(() =>
            guarded.ReadVerifiedBatchAsync(reader,query.AssetId,query.OntologyReleaseId,default));
        Assert.AreEqual((503,"artifact_binding_mismatch"),(damaged.Status,damaged.Code));
        Assert.IsGreaterThan(0,storage.Reads);
        // 每种变异都先重新调用正式目录并验证同批实际图，然后仅改变这次返回给网关的材料。
        var actual = (IVerifiedReleaseBatchCatalog)services.GetRequiredService<IReleaseCatalog>();
        foreach (var fault in new[] { "slots", "snapshot", "bytes" })
        {
            // 将同一查询交给正式取消服务，故障应早于已完成冲突及持久变更。
            var gateway = ActivatorUtilities.CreateInstance<SemanticGateway>(services,new AlteredBatchCatalog(actual,fault));
            // 只接受原槽位/快照/散列绑定错误，不接受 409 来假冒已发现故障。
            var error = await Assert.ThrowsAsync<SemanticOperationException>(() => gateway.CancelG4Async(reader,original.SessionReference,original.Id,default));
            Assert.AreEqual((503,"published_source_binding_invalid"),(error.Status,error.Code));
        }
        // 未注入故障的下一次请求仍须真实重验，已完成查询应恢复为原 409。
        var normal = await Assert.ThrowsAsync<SemanticOperationException>(() =>
            services.GetRequiredService<ISemanticGateway>().CancelG4Async(reader,original.SessionReference,original.Id,default));
        Assert.AreEqual((409,"query_already_finished"),(normal.Status,normal.Code));
    }

    /// <summary>测试专属只读适配器，在真实 S3 GET 后仅损坏交给验证器的副本。</summary>
    private sealed class CorruptSourceRead(IReleaseArtifactStore inner) : IReleaseArtifactStore
    {
        /// <summary>核实权限拒绝发生于外部读取之前。</summary>
        public int Reads { get; private set; }

        /// <summary>此故障入口不提供写操作。</summary>
        public Task<ArtifactObject> PutImmutableAsync(string key,ReadOnlyMemory<byte> content,string type,CancellationToken token) =>
            throw new InvalidOperationException("READ_ONLY_FIXTURE");

        /// <summary>从准确对象真实读取，对源码单字节变异，清单原件保留。</summary>
        public async Task<byte[]> ReadVerifiedAsync(ArtifactObject artifact,CancellationToken token)
        {
            Reads++;
            // 每次取得独立字节数组，避免测试变异影响共享对象。
            var bytes = (await inner.ReadVerifiedAsync(artifact,token)).ToArray();
            if (artifact.ContentType == "text/turtle" && bytes.Length > 0) bytes[0] ^= 1;
            return bytes;
        }
    }

    /// <summary>仅在真实的本次已校验批次上修改测试副本，验证消费端仍核对同槽位及快照。</summary>
    private sealed class AlteredBatchCatalog(IVerifiedReleaseBatchCatalog actual,string fault) : IReleaseCatalog, IVerifiedReleaseBatchCatalog
    {
        /// <summary>此反例应直接进入显式固定发布批次入口。</summary>
        public Task<ReleaseSummary> ReadAsync(ActorContext actor,string releaseId,CancellationToken token) => throw new InvalidOperationException("UNEXPECTED_LEGACY_READ");

        /// <summary>禁止用回退重复读隐藏批次校验故障。</summary>
        public Task<ReleaseSummary> ResolveAsync(ActorContext actor,string assetId,string? releaseId,CancellationToken token) => throw new InvalidOperationException("UNEXPECTED_LEGACY_READ");

        /// <summary>真实权限、原件和图回读先完成，再构造确定的单项反例。</summary>
        public async Task<(ReleaseManifest Manifest,byte[][] SourceObjects,PublishedRdfData Graph)> ReadVerifiedBatchAsync(ActorContext actor,string assetId,string releaseId,CancellationToken token)
        {
            // 每次从正式目录读取，不复用上一个请求。
            var batch = await actual.ReadVerifiedBatchAsync(actor,assetId,releaseId,token);
            if (fault == "slots") (batch.SourceObjects[0],batch.SourceObjects[1]) = (batch.SourceObjects[1],batch.SourceObjects[0]);
            else if (fault == "snapshot") batch.Manifest = batch.Manifest with { Snapshot = batch.Manifest.Snapshot with { DataHash=new string('0',64) } };
            else batch.SourceObjects[0][0] ^= 1;
            return batch;
        }
    }

    /// <summary>用独立 PG 事务占住本次租约行，实测真实总期限含最终提交且无成功副作用。</summary>
    private static async Task VerifyContendedCommitDeadlineAsync(IServiceProvider services, ActorContext actor,
        G4QueryRecord original, G4QueryDbContext db, bool nearDeadline)
    {
        // 新幂等身份只用于原先已成功的固定实体读取。
        var key = Guid.NewGuid().ToString();
        // 取浏览器实际输入的同一查询体。
        using var doc = JsonDocument.Parse(original.RequestBytes);
        // 合成 Q 的原查询使用完整五秒总期限。
        var query = doc.RootElement.GetProperty("query").Deserialize<G4SemanticQuery>(G4QueryJson.Options)!;
        Assert.AreEqual(5000, query.TimeoutMs);
        // 用与产品事务分离的上下文持有这一个查询行的锁。
        await using var blocker = await services.GetRequiredService<IDbContextFactory<G4QueryDbContext>>().CreateDbContextAsync();
        // 此事务绝不写入业务行，测试退出后回滚释放行锁。
        await using var transaction = await blocker.Database.BeginTransactionAsync();
        await blocker.Database.ExecuteSqlRawAsync("SET LOCAL idle_in_transaction_session_timeout = '7s'");
        // 平台只观测由这一准确后端阻塞的活动事务。
        var pid = await blocker.Database.SqlQuery<int>($"SELECT pg_backend_pid() AS \"Value\"").SingleAsync();
        // 单个信号携带真实锁定的查询和当时读取的截止时间。
        var held = new TaskCompletionSource<G4QueryRecord>(TaskCreationOptions.RunContinuationsAsynchronously);
        // 原读取与授权不替换，仅在正式查询结果事务取得授权锁之前锁定准确租约。
        var execution = BeforeCommitExecution(services, async token =>
        {
            // 仅本次 key、org 和真实 Q 对应的行可被试验占锁。
            var rows = await blocker.Queries.FromSqlInterpolated(
                $"SELECT * FROM semantic_query.\"Queries\" WHERE \"IdempotencyKey\"={key} AND \"SubjectId\"={actor.SubjectId} AND \"OrganizationId\"={actor.OrganizationId} FOR UPDATE")
                .AsNoTracking().ToArrayAsync(token);
            Assert.HasCount(1, rows);
            Assert.AreEqual("RUNNING",rows[0].ExecutionStatus);
            held.SetResult(rows[0]);
            if (nearDeadline)
            {
                // 只在总截止反例调度真实提交，留八百毫秒使总期限先于平台两秒锁超时。
                var delay = rows[0].DeadlineAtUtc - DateTimeOffset.UtcNow - TimeSpan.FromMilliseconds(800);
                Assert.IsGreaterThan(TimeSpan.Zero,delay);
                await Task.Delay(delay,token);
            }
        });
        // Gateway 的真实时钟与取消令牌贯穿提交及审计。
        var gateway = ActivatorUtilities.CreateInstance<SemanticGateway>(services,execution);
        // 测量调用起点及实际错误返回时刻。
        var started = DateTimeOffset.UtcNow;
        // 单调时钟检查实际调用返回上界，包含取消传播及回滚。
        var measurement = Stopwatch.StartNew();
        // 在保持真实五秒限额时，仅在测试层等待独立的持锁证明。
        var running = gateway.ExecuteG4Async(actor,original.SessionReference,query,key,null,CancellationToken.None);
        // 精确租约记录载明同一查询的绝对期限。
        var first = await Task.WhenAny(held.Task, running).WaitAsync(TimeSpan.FromSeconds(5));
        if (first == running) await running;
        Assert.IsTrue(held.Task.IsCompletedSuccessfully);
        // 只有实际持锁后才进入独立等锁观察。
        var lease = await held.Task;
        // 实际 PG 等锁证明防止将普通到期误归因于本试验。
        DateTimeOffset? blocked = null;
        while (!running.IsCompleted && DateTimeOffset.UtcNow < lease.DeadlineAtUtc)
        {
            if (await db.Database.SqlQuery<int>($"SELECT count(*)::int AS \"Value\" FROM pg_stat_activity WHERE {pid}=ANY(pg_blocking_pids(pid)) AND state='active' AND query LIKE '%FOR UPDATE%'").SingleAsync() > 0)
            {
                blocked = DateTimeOffset.UtcNow;
                break;
            }
            await Task.Delay(10);
        }
        // 看门狗仅约束测试收尾；不改变产品五秒截止。
        var denial = await Assert.ThrowsAsync<SemanticOperationException>(() => running.WaitAsync(TimeSpan.FromSeconds(2) + (lease.DeadlineAtUtc > DateTimeOffset.UtcNow ? lease.DeadlineAtUtc - DateTimeOffset.UtcNow : TimeSpan.Zero)));
        // 回滚准确持锁事务后再读取真实持久状态。
        measurement.Stop();
        var deniedAt = DateTimeOffset.UtcNow;
        await transaction.RollbackAsync();
        Assert.IsNotNull(blocked);
        Assert.IsTrue(deniedAt < lease.DeadlineAtUtc && measurement.Elapsed.TotalMilliseconds <= query.TimeoutMs);
        if (nearDeadline) Assert.IsTrue(deniedAt >= lease.DeadlineAtUtc.AddMilliseconds(-125));
        Assert.AreEqual((503,"query_timeout"),(denial.Status,denial.Code));
        // 没有晚到结果、来源回执或成功执行审计。
        var row = await db.Queries.AsNoTracking().SingleAsync(item => item.Id == lease.Id);
        Assert.AreNotEqual("COMPLETED",row.ExecutionStatus);
        Assert.AreEqual(0,row.ResultCiphertext.Length);
        Assert.AreEqual(0,G4QueryResultStore.ReadState(row).Receipts.Length);
        // 治理库单独读回同一 queryId 的审计。
        await using var governance = await services.GetRequiredService<IDbContextFactory<OntologyPlatform.Modules.Governance.GovernanceDbContext>>().CreateDbContextAsync();
        // 只核验成功审计，后台失联收尾可再单独观测。
        var allowed = await governance.AuditRecords.CountAsync(item => item.Resource == row.Id && item.Action == "data.query.execute" && item.Outcome == "allowed");
        Assert.AreEqual(0,allowed);
        // 明确区分产品截止、取消传播耗时及调用返回时间。
        var result = new { queryId = row.Id, key, nearDeadline, scheduledRemainingMs = nearDeadline ? 800 : (int?)null, started, blocked, row.DeadlineAtUtc, deniedAt, elapsedMs = measurement.Elapsed.TotalMilliseconds,
            denial.Status, denial.Code, row.ExecutionStatus, resultBytes=row.ResultCiphertext.Length, receipts=0, successAudits=allowed };
        await File.WriteAllTextAsync(Path.Combine(DorisRuntimeRoot(),"artifacts/workflow/G4-DORIS-MAPPING-QUERY-001/implementation-01",
            "contended-deadline-"+key+".json"),JsonSerializer.Serialize(result,new JsonSerializerOptions(JsonSerializerDefaults.Web)));
    }

    /// <summary>从同一读取的真实绑定取连接 ID，在原租约最终检查之前执行正式轮换事务。</summary>
    private static async Task RotateDorisDuringCommitAsync(IServiceProvider services, ActorContext reader,
        (ActorContext Actor, string Session) editor, G4QueryRecord original, G4QueryDbContext db, JsonElement rotation)
    {
        // 只对已准入的前件查询所绑定的实际任务连接操作。
        var binding = G4QueryResultStore.ReadState(original).Binding;
        Assert.AreEqual(binding.ConnectionId, rotation.GetProperty("connectionId").GetString());
        // 源连接当前修订与请求中已捕获的修订必须一致。
        var revision = rotation.GetProperty("revision").GetInt64();
        Assert.AreEqual(binding.ConnectionRevision, revision.ToString(System.Globalization.CultureInfo.InvariantCulture));
        // 旧版本与回调提交的新版本分开记录。
        var version = rotation.GetProperty("version").GetInt64();
        Assert.AreEqual(binding.SecretVersion, version.ToString(System.Globalization.CultureInfo.InvariantCulture));
        // 只对这一条独立、正常的实体查询调度一次轮换。
        var key = Guid.NewGuid().ToString();
        // 真实浏览器产生的原始查询包含本次作用域。
        using var doc = JsonDocument.Parse(original.RequestBytes);
        // 不更改固定计划或原有时间限额。
        var query = doc.RootElement.GetProperty("query").Deserialize<G4SemanticQuery>(G4QueryJson.Options)!;
        // 公开证据只记录版本及事务先后，密钥正文与引用仅留在内存。
        DateTimeOffset? afterRead = null;
        // 仅在正式连接服务提交后设置，异常路径不匹配门禁。
        DateTimeOffset? rotatedAt = null;
        // 成功变更必须来自独立请求、A 的真实会话与强 ETag。
        var execution = BeforeCommitExecution(services, async token =>
        {
            afterRead = DateTimeOffset.UtcNow;
            // 使用标准绑定、会话权限、一次性引用、版本 CAS、审计和事务。
            var reply = await services.GetRequiredService<IConnectionRequestHandler>().HandleAsync(new ConnectionInvocation
            {
                Id = binding.ConnectionId, Actor = editor.Actor, SessionReference = editor.Session, Operation = "rotate",
                Etag = rotation.GetProperty("etag").GetString(), ChildId = null, Cursor = null, Type = null, State = null,
                Body = new ConnectionRotateSecretRequest { SecretRef = rotation.GetProperty("reference").GetString()!, Command = Command(revision) }
            }, token);
            rotatedAt = DateTimeOffset.UtcNow;
            Assert.AreEqual(200, reply.StatusCode);
            // 版本和修订必须分别增加，不能将编辑显示名称当成轮换。
            var current = (ConnectionView)reply.Value;
            Assert.AreEqual(version + 1, current.SecretVersion);
            Assert.AreEqual(revision + 1, current.ConfigRevision);
        });
        // 原查询使用同一正式 Gateway 与真实平台存储。
        var gateway = ActivatorUtilities.CreateInstance<SemanticGateway>(services, execution);
        // 未提交的旧绑定须被当前平台权限或绑定检查准确拒绝。
        var denied = await Assert.ThrowsAsync<SemanticOperationException>(() =>
            gateway.ExecuteG4Async(reader, original.SessionReference, query, key, null, CancellationToken.None));
        // 在读取后、轮换后、五秒期限前记录实际拒绝时刻。
        var deniedAt = DateTimeOffset.UtcNow;
        Assert.IsTrue((denied.Status, denied.Code) is (409, "query_binding_stale") or (403, "query_forbidden"));
        // 随机幂等键只定位这一次竞态。
        var row = await db.Queries.AsNoTracking().SingleAsync(item => item.IdempotencyKey == key);
        Assert.IsTrue(afterRead <= rotatedAt && rotatedAt <= deniedAt && deniedAt < row.DeadlineAtUtc);
        Assert.AreNotEqual("COMPLETED", row.ExecutionStatus);
        Assert.IsNull(row.ResultHash);
        Assert.AreEqual(0, row.ResultCiphertext.Length);
        Assert.AreEqual(0, G4QueryResultStore.ReadState(row).Receipts.Length);
        // 用正式治理库独立读回该查询的成功审计数。
        await using var governance = await services.GetRequiredService<IDbContextFactory<OntologyPlatform.Modules.Governance.GovernanceDbContext>>().CreateDbContextAsync();
        // 测试仅接受同一查询没有成功副作用的结果。
        var allowed = await governance.AuditRecords.CountAsync(item => item.Resource == row.Id && item.Action == "data.query.execute" && item.Outcome == "allowed");
        Assert.AreEqual(0, allowed);
        // 摘要不含轮换请求、引用或凭据。
        var result = new { queryId = row.Id, key, binding.ConnectionId, oldVersion = version, newVersion = version + 1, oldRevision = revision,
            newRevision = revision + 1, afterRead, rotatedAt, deniedAt, row.DeadlineAtUtc, denied.Status, denied.Code,
            row.ExecutionStatus, resultBytes = row.ResultCiphertext.Length, receipts = 0, successAudits = allowed };
        await File.WriteAllTextAsync(Path.Combine(DorisRuntimeRoot(), "artifacts/workflow/G4-DORIS-MAPPING-QUERY-001/implementation-01",
            "rotation-inflight-" + key + ".json"), JsonSerializer.Serialize(result, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
    }

    /// <summary>在同一次分支后验取证，限定真实 DDL 或本次准确连接断开，沿用正式计时与授权。</summary>
    private static async Task VerifyDorisPostcheckFailureAsync(IServiceProvider services, ActorContext actor,
        G4QueryRecord original, G4QueryDbContext db, bool disconnect)
    {
        // 使用浏览器已成功执行的同一固定实体计划，仅幂等键不同。
        using var request = JsonDocument.Parse(original.RequestBytes);
        // 真实服务器存储的请求准确绑定当前合成根。
        var query = request.RootElement.GetProperty("query").Deserialize<G4SemanticQuery>(G4QueryJson.Options)!;
        // 随机键关联源读取、拒绝及平台审计。
        var key = Guid.NewGuid().ToString();
        // 验证端只使用同一只读账号及固定 TLS 地址，不接受外部服务器或连接号。
        var sourceDirectory = Path.Combine(DorisRuntimeRoot(), ".tools/security/g4-doris-mapping-query-001/implementation-01-source");
        // 独立验证端只为传输故障场景创建，严守原 CA 和无池会话。
        await using var observer = disconnect ? new MySqlConnection(new MySqlConnectionStringBuilder
        {
            Server = "localhost", Port = 19030, UserID = "fixture_reader", Password = await File.ReadAllTextAsync(Path.Combine(sourceDirectory, "reader.pass")),
            SslMode = MySqlSslMode.VerifyFull, SslCa = Path.Combine(sourceDirectory,"tls","ca.pem"), Pooling = false, ConnectionTimeout = 2, DefaultCommandTimeout = 1
        }.ConnectionString) : null;
        if (observer is not null) await observer.OpenAsync();
        // 独占本次测试的诊断范围，生产代码原有事件分别标记提交和读取完成。
        using var trace = new Activity("dmq.inflight.catalog").Start();
        // 保留精确竞争时刻及驱动后验的目标身份。
        DateTimeOffset? changedAt = null;
        // 只让本测试的一次后续驱动命令触发竞争。
        var armed = 1;
        // 限定于同 trace 且产品已读完数据的第一个真实后验命令。
        using var listener = new ActivityListener
        {
            ShouldListenTo = source => source.Name == "MySqlConnector",
            Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllData,
            ActivityStarted = operation =>
            {
                if (operation.TraceId != trace.TraceId || !trace.Events.Any(row => row.Name == "doris.plan.rows_finished")
                    || Interlocked.Exchange(ref armed, 0) != 1) return;
                if (observer is not null)
                {
                    // 物理线程必须同时与真实握手和此 trace 的固定投影提交事件对应。
                    var sourceThread = (int)trace.Events.Single(e => e.Name == "doris.plan.submitted").Tags.Single(t => t.Key == "thread").Value!;
                    // 独立通道不得误中自己、辅助连接或其他测试的源连接。
                    var handshake = trace.Events.Single(e => e.Name == "doris.cancel.ready");
                    Assert.AreEqual(sourceThread,handshake.Tags.Single(t => t.Key == "source.thread").Value);
                    Assert.AreNotEqual(sourceThread,handshake.Tags.Single(t => t.Key == "auxiliary.thread").Value);
                    Assert.AreNotEqual(sourceThread,observer.ServerThread);
                    // 故障只发生在本次已读取数据的同账号会话；生产代码没有这条入口。
                    using var interrupt = observer.CreateCommand();
                    interrupt.CommandText = "KILL CONNECTION " + sourceThread.ToString(System.Globalization.CultureInfo.InvariantCulture);
                    interrupt.ExecuteNonQuery();
                    changedAt = DateTimeOffset.UtcNow;
                    return;
                }
                // 控制器只接受固定动作，准确 tablet、fixture 和宿主已在本次试验前绑定。
                var start = new ProcessStartInfo("python3") { WorkingDirectory = DorisRuntimeRoot(), UseShellExecute = false };
                foreach (var arg in new[] { "-B", "scripts/maintenance/workflow_doris_s1.py", "ddl-fixture", "--ddl-action", "rename" })
                    start.ArgumentList.Add(arg);
                // 有界等待真实竞争命令；分支的原始一秒计时持续运行。
                using var control = Process.Start(start)!;
                if (control.WaitForExit(2000) && control.ExitCode == 0) changedAt = DateTimeOffset.UtcNow;
            }
        };
        ActivitySource.AddActivityListener(listener);
        // 生产注册的 Gateway、源适配器、事务及审计均不替换。
        var gateway = (SemanticGateway)services.GetRequiredService<ISemanticGateway>();
        if (disconnect)
        {
            // 正式聚合器必须丢弃后验未完成的数据，并保留真实的六态语义。
            var delivery = await gateway.ExecuteG4Async(actor,original.SessionReference,query,key,null,CancellationToken.None);
            // 解析正式线形结果，只验状态、数量和公开来源回执。
            using var wire = JsonDocument.Parse(delivery.ResultBytes!);
            // 传输中断没有已完成的可信前缀。
            var body = wire.RootElement;
            Assert.IsNotNull(changedAt);
            Assert.AreEqual("UNAVAILABLE",body.GetProperty("status").GetString());
            Assert.AreEqual(0,body.GetProperty("data").GetArrayLength());
            Assert.AreEqual(0,body.GetProperty("evidence").GetArrayLength());
            Assert.IsFalse(body.GetProperty("subSources").EnumerateArray().Any(branch =>
                branch.TryGetProperty("sourceReadReceiptId",out var id) && id.ValueKind == JsonValueKind.String));
            // 从实际持久层核对未生成成功来源回执，分列业务与执行状态。
            var stored = await db.Queries.AsNoTracking().SingleAsync(q => q.IdempotencyKey == key);
            Assert.AreEqual(0,G4QueryResultStore.ReadState(stored).Receipts.Length);
            // 查询在真实总期限内返回，并按原始 trace 对账投影已读完。
            var finishedAt = DateTimeOffset.UtcNow;
            Assert.IsTrue(finishedAt < stored.DeadlineAtUtc);
            // 报告不含源值或账号材料。
            var observed = new { queryId=stored.Id, key, sourceReadDone=trace.Events.Single(e=>e.Name=="doris.plan.rows_finished").Timestamp,
                sourceThread=trace.Events.Single(e=>e.Name=="doris.plan.submitted").Tags.Single(t=>t.Key=="thread").Value,
                changedAt,finishedAt,stored.DeadlineAtUtc,stored.ExecutionStatus,semanticStatus=body.GetProperty("status").GetString(),rows=0,evidence=0,receipts=0 };
            await File.WriteAllTextAsync(Path.Combine(DorisRuntimeRoot(),"artifacts/workflow/G4-DORIS-MAPPING-QUERY-001/implementation-01",
                "disconnected-"+key+".json"),JsonSerializer.Serialize(observed,new JsonSerializerOptions(JsonSerializerDefaults.Web)));
            return;
        }
        // 错误要能单独归因于当前目录变化，普通超时和无法连接均不算通过。
        var denial = await Assert.ThrowsAsync<SemanticOperationException>(() =>
            gateway.ExecuteG4Async(actor, original.SessionReference, query, key, null, CancellationToken.None));
        // 查询必须在真实分支和总期限内拒绝，未持久化旧目录下的结果或来源回执。
        var deniedAt = DateTimeOffset.UtcNow;
        Assert.IsNotNull(changedAt);
        Assert.AreEqual(422, denial.Status);
        Assert.AreEqual("mapping_source_shape_invalid", denial.Code);
        // 从独立的正式查询记录确认调用身份及结果。
        var row = await db.Queries.AsNoTracking().SingleAsync(item => item.IdempotencyKey == key);
        Assert.AreNotEqual("COMPLETED", row.ExecutionStatus);
        Assert.AreEqual(0, row.ResultCiphertext.Length);
        Assert.AreEqual(0, G4QueryResultStore.ReadState(row).Receipts.Length);
        // 独立治理上下文按同一查询标识检查成功副作用。
        await using var governance = await services.GetRequiredService<IDbContextFactory<OntologyPlatform.Modules.Governance.GovernanceDbContext>>().CreateDbContextAsync();
        // 统计仅针对当前结果及准确动作。
        var allowed = await governance.AuditRecords.CountAsync(item => item.Resource == row.Id && item.Action == "data.query.execute" && item.Outcome == "allowed");
        Assert.AreEqual(0, allowed);
        // 两个事件来自正式实体读取，准确关联模板、线程及该次原始数据读完时刻。
        var submitted = trace.Events.Single(item => item.Name == "doris.plan.submitted");
        // 记录原始数据读完到目录后验的受控竞争，不声称 DDL 与 BE 数据扫描同时运行。
        var read = trace.Events.Single(item => item.Name == "doris.plan.rows_finished");
        Assert.IsTrue(submitted.Timestamp <= read.Timestamp && read.Timestamp <= changedAt && changedAt <= deniedAt && deniedAt < row.DeadlineAtUtc);
        // 只输出源事件、准确标识与计数，参数与原始业务值不进入报告。
        var result = new { queryId = row.Id, key, submitted = submitted.Timestamp, template = submitted.Tags.Single(item => item.Key == "template.sha256").Value,
            thread = submitted.Tags.Single(item => item.Key == "thread").Value, read = read.Timestamp, changedAt, deniedAt,
            row.DeadlineAtUtc, denial.Code, denial.Status, row.ExecutionStatus, resultBytes = row.ResultCiphertext.Length, receipts = 0, successAudits = allowed };
        await File.WriteAllTextAsync(Path.Combine(DorisRuntimeRoot(), "artifacts/workflow/G4-DORIS-MAPPING-QUERY-001/implementation-01",
            "ddl-inflight-" + key + ".json"), JsonSerializer.Serialize(result, new JsonSerializerOptions(JsonSerializerDefaults.Web)));
    }

    /// <summary>精确撤销本任务同一主体的两条合成来源授权，复用独立事务与恢复台账。</summary>
    private static async Task ChangeDorisGrantAsync(string action, CancellationToken token)
    {
        // 准确脚本只接受预注册的撤销与恢复操作，不传递秘密或 SQL。
        var start = new System.Diagnostics.ProcessStartInfo("python3")
        {
            WorkingDirectory = DorisRuntimeRoot(), UseShellExecute = false,
            RedirectStandardOutput = true, RedirectStandardError = true
        };
        foreach (var arg in new[] {"-B", "scripts/maintenance/workflow_doris_s1.py", "permission", "--permission", action})
            start.ArgumentList.Add(arg);
        // 只检查退出状态与固定脱敏回执，私有错误流不会打印到测试输出。
        using var process = System.Diagnostics.Process.Start(start)!;
        // 同步排空两流，避免子进程阻塞或把环境内容带入公开报告。
        var output = process.StandardOutput.ReadToEndAsync();
        // 失败只记录固定断言，保持详细错误原件由原执行器管理。
        var error = process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync(token);
        await Task.WhenAll(output,error);
        Assert.AreEqual(0,process.ExitCode,"DORIS_GRANT_CONTROL_FAILED");
    }

    /// <summary>复用真实 Gateway，在同一已读取查询的结果事务取得锁前，由另一事务撤权。</summary>
    private static async Task DenyDorisCommitAfterReadAsync(IServiceProvider services, ActorContext actor, G4QueryRecord original, G4QueryDbContext db, bool expireSession)
    {
        // 原请求与当前 Q 和已激活根绑定完全相同，随机命令启动一次新的实际读取。
        using var doc = JsonDocument.Parse(original.RequestBytes);
        // 持久请求已经过正式 DTO 验证。
        var query = doc.RootElement.GetProperty("query").Deserialize<G4SemanticQuery>(G4QueryJson.Options)!;
        // 当前测试唯一路径精确关联在途行与审计。
        var key = Guid.NewGuid().ToString();
        // 这两个时刻分别界定已完成真实读取、撤权已提交。
        DateTimeOffset? afterRead = null;
        // 撤权返回须早于拒绝，不能以事后观测替代提交顺序。
        DateTimeOffset? revoked = null;
        // 这条上下文只在真实测试主体的会话失效及审计读回中使用，不参与产品提交事务。
        await using var governance = await services.GetRequiredService<IDbContextFactory<OntologyPlatform.Modules.Governance.GovernanceDbContext>>().CreateDbContextAsync();
        // 用准确主键和原始期限进行比较更新，避免覆盖另一笔撤销或续期。
        var currentSession = governance.Sessions.Where(row => row.Id == original.SessionReference && row.RevokedAtUtc == null);
        // 只读取有效期限，不接触保护票据或其他会话。
        var originalExpiry = await currentSession.Select(row => row.ExpiresAtUtc).SingleAsync();
        Assert.IsTrue(originalExpiry > DateTimeOffset.UtcNow.AddSeconds(10));
        // 固定到整秒以和 PG 的微秒精度进行准确比较，恢复时保持原绝对期限。
        var expiredAt = DateTimeOffset.FromUnixTimeSeconds(DateTimeOffset.UtcNow.ToUnixTimeSeconds() - 1);
        // 复用不替换安全参与者的在途调度。
        var execution = BeforeCommitExecution(services, async token =>
        {
            afterRead = DateTimeOffset.UtcNow;
            if (expireSession)
            {
                Assert.AreEqual(1, await currentSession.Where(row => row.ExpiresAtUtc == originalExpiry)
                    .ExecuteUpdateAsync(setters => setters.SetProperty(row => row.ExpiresAtUtc, expiredAt), token));
            }
            else
            {
                await ChangeDorisGrantAsync("revoke-execute", token);
            }
            revoked = DateTimeOffset.UtcNow;
        });
        // 正式 Gateway、宿主根语义、源适配器、平台事务和审计全部使用真实实现。
        var gateway = ActivatorUtilities.CreateInstance<SemanticGateway>(services, execution);
        try
        {
            // 接受合同登记的显式权限或绑定拒绝，不接受容量、超时或普通执行故障。
            var rejected = await Assert.ThrowsAsync<SemanticOperationException>(() => gateway.ExecuteG4Async(actor, original.SessionReference, query, key, null, CancellationToken.None));
            Assert.AreEqual(403, rejected.Status);
            Assert.AreEqual("query_forbidden", rejected.Code);
            Assert.IsNotNull(revoked);
            // 只取当前命令和这一笔成功审计计数。
            var stored = await db.Queries.AsNoTracking().SingleAsync(q => q.IdempotencyKey == key);
            // 真实数据库状态与成功审计需一起为零。
            var allowed = await governance.AuditRecords.CountAsync(a => a.Resource == stored.Id && a.Action == "data.query.execute" && a.Outcome == "allowed");
            Assert.AreNotEqual("COMPLETED",stored.ExecutionStatus);
            Assert.AreEqual(0,stored.ResultCiphertext.Length);
            Assert.IsNull(stored.ResultHash);
            Assert.AreEqual(0,G4QueryResultStore.ReadState(stored).Receipts.Length);
            Assert.AreEqual(0,allowed);
            // 记录公开时序与准确失败码，不含来源行与会话引用。
            var result = new { queryId=stored.Id, stored.CreatedAtUtc, stored.DeadlineAtUtc, afterRead, revoked,
                rejectedAt=DateTimeOffset.UtcNow, rejected.Code, rejected.Status, stored.ExecutionStatus,
                resultBytes=stored.ResultCiphertext.Length, stored.ResultHash, receipts=0, successAudits=allowed };
            Assert.IsTrue(result.rejectedAt < stored.DeadlineAtUtc);
            await File.WriteAllTextAsync(Path.Combine(DorisRuntimeRoot(), "artifacts/workflow/G4-DORIS-MAPPING-QUERY-001/implementation-01",
                (expireSession ? "session-inflight-" : "grant-inflight-")+key+".json"), JsonSerializer.Serialize(result,new JsonSerializerOptions(JsonSerializerDefaults.Web)));
        }
        finally
        {
            if (expireSession && revoked.HasValue)
            {
                Assert.AreEqual(1, await currentSession.Where(row => row.ExpiresAtUtc == expiredAt)
                    .ExecuteUpdateAsync(setters => setters.SetProperty(row => row.ExpiresAtUtc, originalExpiry)));
                Assert.AreEqual(originalExpiry, await currentSession.Select(row => row.ExpiresAtUtc).SingleAsync());
            }
            else if (revoked.HasValue)
            {
                await ChangeDorisGrantAsync("restore-execute", CancellationToken.None);
            }
        }
    }

    /// <summary>从当前受控测试程序集找回实际仓库根目录，兼容 MTP 改变工作目录。</summary>
    private static string DorisRuntimeRoot()
    {
        // 程序集必须位于正式构建所在工作树，在根目录复核任务卡身份。
        var directory = new DirectoryInfo(AppContext.BaseDirectory);
        while (directory is not null && !File.Exists(Path.Combine(directory.FullName, "docs/tasks/G4-DORIS-MAPPING-QUERY-001.md")))
            directory = directory.Parent;
        return directory?.FullName ?? throw new InvalidOperationException("DORIS_TEST_WORKTREE_MISSING");
    }

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

    /// <summary>只在真实源成功返回后激活一次提交前调度，源分支与观察者正常完成。</summary>
    private static G4QueryExecution BeforeCommitExecution(IServiceProvider services, Func<CancellationToken, Task> competingCommand)
    {
        // 所有授权检查仍由正常的正式实例执行。
        var authority = services.GetRequiredService<IG4QueryAuthorizationAuthority>();
        // 每个测试独享标记，避免把其他查询及准入阶段认作目标提交。
        var ready = 0;
        // 只切换已登记的调度点，不替换数据库事务、加密、fence 或审计。
        var scheduled = new ScheduledAuthority(authority, token =>
            Interlocked.Exchange(ref ready, 0) == 1 ? competingCommand(token) : Task.CompletedTask);
        // 使用所有正式构造依赖，只在第一次最终授权检查开始前运行并发命令。
        var store = ActivatorUtilities.CreateInstance<G4QueryResultStore>(services, scheduled);
        // 真实读取器返回后只记录已完成，耗时的竞争不在这个分支计时内。
        var source = new AfterReadSource(services.GetRequiredService<IG4SourceQueryReader>(), _ =>
        {
            Interlocked.Exchange(ref ready, 1);
            return Task.CompletedTask;
        });
        return new G4QueryExecution(services.GetRequiredService<IG4QueryBindingReader>(), source, authority, store, TimeProvider.System);
    }

    /// <summary>保留全部正式权限参与者，仅在获取事务授权锁之前提供确定性的竞争调度。</summary>
    private sealed class ScheduledAuthority(IG4QueryAuthorizationAuthority actual, Func<CancellationToken, Task> beforeCheck) : IG4QueryAuthorizationAuthority
    {
        /// <summary>当前会话证明始终来自正式权限实现。</summary>
        public Task<MappingAuthorizationProof> CaptureSessionAsync(ActorContext actor, string sessionReference, ResourceScope scope, CancellationToken token) =>
            actual.CaptureSessionAsync(actor, sessionReference, scope, token);

        /// <summary>实际事务中的会话锁与授权检查在竞争提交之后执行。</summary>
        public async Task DemandSessionInTransactionAsync(MappingAuthorizationProof proof, System.Data.Common.DbConnection connection,
            System.Data.Common.DbTransaction transaction, CancellationToken token)
        {
            await beforeCheck(token);
            await actual.DemandSessionInTransactionAsync(proof, connection, transaction, token);
        }

        /// <summary>全部字段授权证明继续由正式服务捕获。</summary>
        public Task<MappingAuthorizationProof> CaptureAsync(MappingAuthorizationProof request, CancellationToken token) => actual.CaptureAsync(request, token);

        /// <summary>使用相同物理事务验证字段投影和组织授权版本。</summary>
        public Task DemandInTransactionAsync(MappingAuthorizationProof proof, System.Data.Common.DbConnection connection,
            System.Data.Common.DbTransaction transaction, CancellationToken token) => actual.DemandInTransactionAsync(proof, connection, transaction, token);
    }

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

        /// <summary>取得真实源行及回执后才改变当前绑定，随后返回原读取事实。</summary>
        public async Task<G4SourceQueryRead> ReadAsync(G4QueryBindingContext context, MappingAuthorizationProof proof, string entityBindingId,
            G4SemanticQuery query, DateTimeOffset deadlineAtUtc, CancellationToken cancellationToken, G4QueryBranchFilter? branch = null)
        {
            // 真实源返回值保持原样，故障仅改变返回后的调度。
            var read = await actual.ReadAsync(context, proof, entityBindingId, query, deadlineAtUtc, cancellationToken, branch);
            Assert.IsTrue(read.Rows.Length > 0);
            if (Interlocked.Increment(ref invoked) == 1) await afterRead(cancellationToken);
            return read;
        }
    }

}
