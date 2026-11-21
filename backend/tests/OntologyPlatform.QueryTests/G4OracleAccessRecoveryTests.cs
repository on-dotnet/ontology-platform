using System.Data.Common;
using System.Security.Claims;
using System.Text.Json;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Api.G4;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.SemanticQuery;

namespace OntologyPlatform.QueryTests;

/// <summary>本次源ACL失败的准确维护复用隔离PostgreSQL，证明恢复不会放行旧fence。</summary>
public sealed partial class G4QueryRaceTests
{
    /// <summary>核FAILED原行、完整证明、审计失败回滚、准确恢复和同操作幂等；不修改原取消维护。</summary>
    [TestMethod]
    public async Task OracleAccessFailureMaintenanceInIsolatedPostgres()
    {
        // 原有测试库门禁还会验证服务器端数据库注释，不接受同名替代库。
        var connection = Environment.GetEnvironmentVariable("G4_QUERY_TEST_CONNECTION");
        Assert.IsFalse(string.IsNullOrWhiteSpace(connection));
        await G4QueryPersistenceTests.DemandIsolatedDatabaseAsync(connection!);
        await using var provider = new ServiceCollection()
            .AddDbContextFactory<G4QueryDbContext>(o => o.UseNpgsql(connection, n => n.MigrationsHistoryTable("__EFMigrationsHistory", "semantic_query")))
            .AddDbContextFactory<GovernanceDbContext>(o => o.UseNpgsql(connection, n => n.MigrationsHistoryTable("__EFMigrationsHistory", "governance")))
            .BuildServiceProvider();
        // 模块各自管理模型和写入；隔离库由外部测试驱动按准确身份释放。
        var queries = provider.GetRequiredService<IDbContextFactory<G4QueryDbContext>>();
        var governance = provider.GetRequiredService<IDbContextFactory<GovernanceDbContext>>();
        await using var db = await queries.CreateDbContextAsync();
        await using var gov = await governance.CreateDbContextAsync();
        await gov.Database.MigrateAsync();
        await db.Database.MigrateAsync();
        const string qid = G4OracleAccessMaintenanceProof.QueryId;
        const string cid = G4OracleAccessMaintenanceProof.ConnectionId;
        // 固定测试目标不覆盖同库先前未说明的行或审计。
        Assert.IsFalse(await db.Queries.AnyAsync(q => q.Id == qid));
        Assert.IsFalse(await gov.AuditRecords.AnyAsync(a => a.Resource == qid));
        // 真实 Cookie 会话和三项独立授权，计数器只代替本次外部 Oracle 开连接。
        var actor = new ActorContext
        {
            SubjectId = "oracle-test-reader",
            OrganizationId = "org-demo",
            SiteIds = ["site-a"],
            Roles = ["platform.viewer"],
            TraceId = "oracle-test-trace",
            CorrelationId = "oracle-test-call"
        };
        var scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = actor.SiteIds };
        var projection = new G4QueryProjection { ObjectRefs = ["production/assets"], FieldRefs = ["production/assets/1/id"] };
        var grants = new[] { "data.query.execute", "data.query.result.read", "data.query.evidence.read" }
            .Select(permission => new MappingAuthorizationGrant
            {
                Id = "grant-" + Guid.NewGuid().ToString("N"),
                SubjectId = actor.SubjectId,
                OrganizationId = actor.OrganizationId,
                SiteIds = actor.SiteIds,
                Permission = permission,
                ConnectionId = cid,
                ObjectRefs = projection.ObjectRefs,
                FieldRefs = projection.FieldRefs,
                ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(10)
            }).ToArray();
        gov.MappingAuthorizationGrants.AddRange(grants);
        await gov.SaveChangesAsync();
        // 测试使用真实治理票据和事务授权，不将测试身份写入实际任务库。
        var protection = new EphemeralDataProtectionProvider();
        var principal = new ClaimsPrincipal(new ClaimsIdentity(new[] { new Claim("sub", actor.SubjectId), new Claim("organization_id", actor.OrganizationId),
            new Claim("site_ids", "site-a"), new Claim(ClaimTypes.Role, "platform.viewer") }, "Cookies"));
        var tickets = new PostgresTicketStore(governance, protection, new HttpContextAccessor { HttpContext = new DefaultHttpContext { User = principal } }, TimeProvider.System);
        var ticket = await tickets.StoreAsync(new AuthenticationTicket(principal, new AuthenticationProperties { ExpiresUtc = DateTimeOffset.UtcNow.AddMinutes(10) }, "Cookies"));
        var authority = new QueryAuthorizationParticipant(new MappingAuthorizationParticipant(governance, new MappingSessionAuthority(protection), TimeProvider.System));
        var session = await authority.CaptureSessionAsync(actor, ticket, scope, CancellationToken.None);
        var query = new G4SemanticQuery
        {
            AssetId = "asset-1",
            OntologyReleaseId = "ontology-1",
            MappingReleaseIds = ["mapping-1"],
            CapabilityId = "g4_read_observations",
            CapabilityVersion = new string('a', 64),
            RelationshipIris = [],
            Depth = 1,
            MaxRows = 10,
            TimeoutMs = 5000,
            Filters = new G4QueryFilters()
        };
        var binding = Binding(session.AuthorizationEpoch) with { ConnectionId = cid };
        var state = new G4QueryState { Binding = binding, Scope = scope, Projections = [projection], RequiredProjections = [projection] };
        var request = G4QueryCanonical.Serialize(new { query, selectionQueryId = (string?)null });
        // 秒精度仅用于本隔离种子，使 PG 与 .NET 比较不因微秒截断产生偶然差异。
        var now = DateTimeOffset.FromUnixTimeSeconds(DateTimeOffset.UtcNow.ToUnixTimeSeconds());
        var row = new G4QueryRecord
        {
            Id = qid,
            OrganizationId = actor.OrganizationId,
            SubjectId = actor.SubjectId,
            SessionReference = ticket,
            ConnectionId = cid,
            IdempotencyKey = "omq-cancelled",
            RequestHash = G4QueryCanonical.Hash(request),
            RequestBytes = request,
            BindingBytes = G4QueryCanonical.Serialize(state),
            ExecutionStatus = "FAILED",
            CancelRequested = false,
            Fence = 2,
            LeaseOwner = G4OracleAccessMaintenanceProof.Owner,
            LeaseUntilUtc = now.AddMinutes(-2),
            CreatedAtUtc = now.AddMinutes(-3),
            CompletedAtUtc = now.AddMinutes(-2),
            DeadlineAtUtc = now.AddMinutes(-2),
            ExpiresAtUtc = now.AddHours(1)
        };
        // 同连接另一条本人历史行必须遵守相同准入，不能以 QueryId 区别规避封闭。
        var history = new G4QueryRecord
        {
            Id = "query-" + Guid.NewGuid().ToString("N"),
            OrganizationId = row.OrganizationId,
            SubjectId = row.SubjectId,
            SessionReference = ticket,
            ConnectionId = cid,
            IdempotencyKey = "omq-history",
            RequestHash = row.RequestHash,
            RequestBytes = request,
            BindingBytes = row.BindingBytes,
            ExecutionStatus = "FAILED",
            CancelRequested = false,
            Fence = 2,
            CreatedAtUtc = row.CreatedAtUtc,
            CompletedAtUtc = row.CompletedAtUtc,
            DeadlineAtUtc = row.DeadlineAtUtc,
            ExpiresAtUtc = row.ExpiresAtUtc
        };
        db.Queries.AddRange(row, history);
        await db.SaveChangesAsync();
        var audit = new TransactionalAuditWriter(governance);
        var failureId = await audit.WriteAsync(actor, new AuditCommand { Action = "data.query.execute", Resource = qid, Outcome = "failure", Scope = scope }, CancellationToken.None);
        // 所有断言都在同一准确隔离库；第二实例不代表操作系统进程重启。
        var bindings = new OracleTestBindings(binding, scope);
        var store = new G4QueryResultStore(queries, authority, bindings, audit, protection, TimeProvider.System);
        var second = new G4QueryResultStore(queries, authority, bindings, audit, protection, TimeProvider.System);
        var source = new OracleOpenCounter(projection);
        var execution = new G4QueryExecution(bindings, source, authority, second, TimeProvider.System);
        var deadline = now.AddMinutes(1);
        // 固定的本体类声明，真实根发布的外部服务本次不启动。
        var graph = new PublishedGraph(new ReleaseManifest(), new PublishedRdfData
        {
            OntologyTriples = [new RdfTriple
            { Subject = new RdfTerm { Kind = RdfTermKind.Iri, Value = "urn:omq:Asset" }, Predicate = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type",
                Object = new RdfTerm { Kind = RdfTermKind.Iri, Value = "http://www.w3.org/2002/07/owl#Class" } }]
        }, CancellationToken.None);
        Task<G4QueryDelivery> Read(ActorContext user, string id, bool result) =>
            execution.ReadAsync(user, ticket, id, result, false, deadline, (_, _) => Task.CompletedTask, CancellationToken.None);
        Task<G4QueryDelivery> Post(string key) => execution.ExecuteAsync(actor, ticket, query, key, null, graph, deadline, (_, _) => Task.CompletedTask, CancellationToken.None);
        foreach (var open in new Func<Task>[] { () => Post("new-omq"), () => Post(row.IdempotencyKey), () => Read(actor, qid, false),
            () => Read(actor, qid, true), () => Read(actor, history.Id, false),
            () => execution.ReadEvidenceAsync(actor, ticket, qid+":e-1", deadline, (_, _) => Task.CompletedTask, CancellationToken.None) })
        {
            Assert.AreEqual("query_capacity_exhausted", (await Assert.ThrowsAsync<SemanticOperationException>(open)).Code);
            Assert.AreEqual(0, source.Opens);
        }
        Assert.AreEqual(404, (await Assert.ThrowsAsync<SemanticOperationException>(() => Read(actor with { SubjectId = "other" }, qid, false))).Status);
        Assert.AreEqual(0, source.Opens);
        Assert.IsFalse(await store.ConfirmOracleCleanupAsync(qid, row.LeaseOwner, 1, 2, () => TimeSpan.FromMilliseconds(250), CancellationToken.None));
        Assert.IsFalse(await store.HeartbeatAsync(new G4QueryRecord { Id = qid, LeaseOwner = row.LeaseOwner, Fence = 1 }, CancellationToken.None));
        // 下面从隔离库真实原行生成摘要与数据库物理身份，并沿生产解析器验证同一结构。
        await db.Database.OpenConnectionAsync();
        await db.Database.ExecuteSqlRawAsync("SET TIME ZONE 'UTC'");
        var facts = JsonSerializer.Deserialize<string[]>((await db.Database.SqlQuery<string>($"""
            SELECT json_build_array((pg_control_system()).system_identifier::text,current_database(),current_user,
              encode(sha256(convert_to((to_jsonb(q)-'LeaseOwner'-'LeaseUntilUtc')::text,'UTF8')),'hex'),
              (SELECT encode(sha256(convert_to(to_jsonb(a)::text,'UTF8')),'hex') FROM governance.audit_records a WHERE a."Id"={failureId}))::text AS "Value"
            FROM semantic_query."Queries" q WHERE q."Id"={qid}
            """).SingleAsync()))!;
        var fields = new Dictionary<string, object>
        {
            ["taskId"] = "G4-ORACLE-MAPPING-QUERY-001",
            ["runId"] = "product-resume-01",
            ["operationId"] = Guid.NewGuid().ToString("N"),
            ["attemptId"] = Guid.NewGuid().ToString("N"),
            ["operatorId"] = "os-uid-501",
            ["systemIdentifier"] = facts[0],
            ["database"] = facts[1],
            ["databaseUser"] = facts[2],
            ["stableRowSha256"] = facts[3],
            ["failureAuditId"] = failureId,
            ["failureAuditSha256"] = facts[4],
            ["organizationId"] = "org-demo",
            ["queryId"] = qid,
            ["connectionId"] = cid,
            ["owner"] = G4OracleAccessMaintenanceProof.Owner,
            ["originalFence"] = 1,
            ["terminalFence"] = 2,
            ["sourceExecutionId"] = "b4b07ea50d304927975cd5d052ff58e4",
            ["parentCommandId"] = "04f23ea8cfe34868a8500b80164d86fb",
            ["sourceContainerId"] = G4OracleAccessMaintenanceProof.SourceContainer,
            ["platformContainerId"] = G4OracleAccessMaintenanceProof.PlatformContainer,
            ["createdUtc"] = row.CreatedAtUtc,
            ["completedUtc"] = row.CompletedAtUtc!,
            ["deadlineUtc"] = row.DeadlineAtUtc,
            ["leaseUntilUtc"] = row.LeaseUntilUtc!,
            ["verifiedUtc"] = now,
            ["validUntilUtc"] = now.AddMinutes(4),
            ["requestSha256"] = row.RequestHash,
            ["bindingSha256"] = G4QueryCanonical.Hash(row.BindingBytes),
            ["sealSha256"] = new string('a', 64),
            ["terminationProofSha256"] = new string('b', 64)
        };
        G4OracleAccessMaintenanceProof Proof(Dictionary<string, object> supplied)
        {
            // 仅测试进程可选隔离数据库；正式 CLI 固定原平台内容键。
            var bytes = JsonSerializer.SerializeToUtf8Bytes(supplied);
            return G4OracleAccessMaintenanceProof.Read(bytes, G4QueryCanonical.Hash(bytes), "os-uid-501", new string('a', 64), new string('b', 64), isolated: true);
        }
        async Task<string> Recover(G4OracleAccessMaintenanceProof authorized, ITransactionalAuditWriter writer)
        {
            await using var fresh = await queries.CreateDbContextAsync();
            return await G4OracleAccessMaintenance.RecoverAsync(fresh, writer, authorized,
                (c, t, ct) => OracleAccessMaintenance.ReadAuditAsync(governance, c, t, ct), CancellationToken.None);
        }
        foreach (var (field, wrong) in new (string, object)[] { ("queryId", history.Id), ("owner", "other"), ("terminalFence", 3), ("sourceContainerId", new string('0', 64)),
            ("platformContainerId", new string('0', 64)), ("sourceExecutionId", new string('0', 32)),
            ("parentCommandId", new string('0', 32)), ("verifiedUtc", now.AddMinutes(1)),
            ("validUntilUtc", now.AddSeconds(-1)), ("terminationProofSha256", new string('0', 64)) })
            Assert.ThrowsExactly<InvalidOperationException>(() => Proof(new(fields) { [field] = wrong }));
        await Assert.ThrowsAsync<InvalidOperationException>(() => Recover(Proof(new(fields) { ["stableRowSha256"] = new string('0', 64) }), audit));
        await Assert.ThrowsAsync<SemanticOperationException>(() => Recover(Proof(fields), new WriteThenFailAudit(audit)));
        Assert.AreEqual(row.LeaseOwner, (await db.Queries.AsNoTracking().SingleAsync(q => q.Id == qid)).LeaseOwner);
        Assert.AreEqual(0, await gov.AuditRecords.CountAsync(a => a.Resource == qid && a.Action == "data.query.cleanup.recover"));
        // 真实容量锁的共享持有者必须等已经登记的跨实例事务提交，然后再见到其最新状态。
        Assert.AreEqual("TASK_LEVEL_RECOVERY", await Recover(Proof(fields), audit));
        Assert.AreEqual("ALREADY_RECOVERED", await Recover(Proof(fields), audit));
        await Assert.ThrowsAsync<InvalidOperationException>(() => Recover(Proof(new(fields) { ["operationId"] = Guid.NewGuid().ToString("N") }), audit));
        Assert.AreEqual(1, await gov.AuditRecords.CountAsync(a => a.Resource == qid && a.Action == "data.query.cleanup.recover"));
        Assert.AreEqual(1, await gov.AuditRecords.CountAsync(a => a.Resource == qid && a.Action == "data.query.execute" && a.Outcome == "failure"));
        var after = await db.Queries.AsNoTracking().SingleAsync(q => q.Id == qid);
        Assert.IsNull(after.LeaseOwner);
        Assert.IsNull(after.LeaseUntilUtc);
        Assert.AreEqual(2L, after.Fence);
        Assert.AreEqual("FAILED", after.ExecutionStatus);
        Assert.AreEqual(0, after.ResultSize);
        // 原 fence1 必须在提交行锁处被拒绝，不能靠构造错误的结果提前短路。
        var executeProof = await authority.CaptureAsync(session with
        {
            ConnectionId = cid,
            Permission = "data.query.execute",
            ObjectRefs = projection.ObjectRefs,
            FieldRefs = projection.FieldRefs
        }, CancellationToken.None);
        var fixture = G4QueryTests.FixtureResult();
        var observed = (G4ObservationDatum)fixture.Data[0];
        var late = fixture with
        {
            Data = [observed with { Identity = observed.Identity with { OrganizationId = actor.OrganizationId, SiteId = "site-a" } }],
            Evidence = [fixture.Evidence[0] with { ConnectionId = cid, Scope = scope }],
            SubSources = [fixture.SubSources[0] with { ConnectionId = cid, WatermarkKind = "UNKNOWN" }]
        };
        var receipt = G4QueryTests.ReceiptFixture(qid, binding, late).Receipt with { AdapterVersion = "oracle-query-v1", WatermarkKind = "UNKNOWN", Watermark = null };
        var stale = new G4QueryRecord { Id = qid, LeaseOwner = G4OracleAccessMaintenanceProof.Owner, Fence = 1, RequestHash = row.RequestHash };
        var lost = await Assert.ThrowsAsync<SemanticOperationException>(() => store.CompleteAsync(stale, session, [executeProof], query, state, late,
            [new G4QueryStoredReceipt { Receipt = receipt, ReceiptHash = G4QueryCanonical.Hash(G4QueryCanonical.Serialize(receipt)) }], CancellationToken.None));
        Assert.AreEqual("query_execution_stale", lost.Code);
        Assert.IsFalse(await store.HeartbeatAsync(stale, CancellationToken.None));
        Assert.AreEqual(0, await gov.AuditRecords.CountAsync(a => a.Resource == qid && a.Action == "data.query.execute" && a.Outcome == "allowed"));
        // 在独立平台事务持有写者容量锁并发布已逾期的 RUNNING；共享进入者只能观察其提交后的状态。
        Task<G4OracleSourceOpen.IPermit> waiting;
        await using (var changing = await db.Database.BeginTransactionAsync())
        {
            await G4QueryResultStore.LockCapacityAsync(db, CancellationToken.None);
            await db.Queries.Where(q => q.Id == history.Id).ExecuteUpdateAsync(u => u.SetProperty(q => q.ExecutionStatus, "RUNNING")
                .SetProperty(q => q.CancelRequested, false).SetProperty(q => q.LeaseOwner, G4QueryResultStore.OracleOwnerPrefix + "isolated")
                .SetProperty(q => q.LeaseUntilUtc, now.AddSeconds(-1)));
            waiting = second.EnterOracleSourceAsync(cid, CancellationToken.None);
            await changing.CommitAsync();
        }
        Assert.AreEqual("query_capacity_exhausted", (await Assert.ThrowsAsync<SemanticOperationException>(() => waiting)).Code);
        Assert.AreEqual(0, source.Opens);
        // 这条同库测试控制行恢复其建立时的状态。真实目标保持只读后验。
        await db.Queries.Where(q => q.Id == history.Id).ExecuteUpdateAsync(u => u.SetProperty(q => q.ExecutionStatus, "FAILED")
            .SetProperty(q => q.CancelRequested, false).SetProperty(q => q.LeaseOwner, (string?)null).SetProperty(q => q.LeaseUntilUtc, (DateTimeOffset?)null));
        // 物理打开完成后仍在源方法内时，独立 writer 就须能获得容量锁。
        await G4OracleSourceOpen.RunAsync(await store.EnterOracleSourceAsync(cid, CancellationToken.None), async () =>
        {
            Assert.IsFalse(await db.Database.SqlQuery<bool>($"SELECT pg_try_advisory_xact_lock(73442001) AS \"Value\"").SingleAsync());
            await G4OracleSourceOpen.BeforePhysicalOpenAsync(CancellationToken.None);
            await G4OracleSourceOpen.AfterPhysicalOpenAsync();
            Assert.IsTrue(await db.Database.SqlQuery<bool>($"SELECT pg_try_advisory_xact_lock(73442001) AS \"Value\"").SingleAsync());
            return true;
        });
        // 解封后合法状态读取才到达受控源边界；撤授权后仍须拒绝且不得再打开。
        await Read(actor, qid, false);
        Assert.AreEqual(1, source.Opens);
        grants.Single(g => g.Permission == "data.query.result.read").RevokedAtUtc = DateTimeOffset.UtcNow;
        await gov.SaveChangesAsync();
        Assert.AreEqual(403, (await Assert.ThrowsAsync<SemanticOperationException>(() => Read(actor, qid, false))).Status);
        Assert.AreEqual(1, source.Opens);
    }

}
