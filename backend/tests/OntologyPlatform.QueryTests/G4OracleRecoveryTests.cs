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

/// <summary>准确维护只在已有驱动创建且证实归属的隔离 PostgreSQL 执行。</summary>
public sealed partial class G4QueryRaceTests
{
    /// <summary>核正式处理入口、过期产品确认、同事务故障回滚、准确恢复和同操作幂等。</summary>
    [TestMethod]
    public async Task OracleMaintenanceAndClosedSourcePathsInIsolatedPostgres()
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
        const string qid = G4OracleMaintenanceProof.QueryId;
        const string cid = G4OracleMaintenanceProof.ConnectionId;
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
            ExecutionStatus = "CANCELLED",
            CancelRequested = true,
            Fence = 2,
            LeaseOwner = G4OracleMaintenanceProof.Owner,
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
            ExecutionStatus = "CANCELLED",
            CancelRequested = true,
            Fence = 2,
            CreatedAtUtc = row.CreatedAtUtc,
            CompletedAtUtc = row.CompletedAtUtc,
            DeadlineAtUtc = row.DeadlineAtUtc,
            ExpiresAtUtc = row.ExpiresAtUtc
        };
        db.Queries.AddRange(row, history);
        await db.SaveChangesAsync();
        var audit = new TransactionalAuditWriter(governance);
        var cancelId = await audit.WriteAsync(actor, new AuditCommand { Action = "data.query.cancel", Resource = qid, Outcome = "allowed", Scope = scope }, CancellationToken.None);
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
        Assert.IsFalse(await store.ConfirmOracleCleanupAsync(qid, row.LeaseOwner, 1, 2, CancellationToken.None));
        Assert.IsFalse(await store.HeartbeatAsync(new G4QueryRecord { Id = qid, LeaseOwner = row.LeaseOwner, Fence = 1 }, CancellationToken.None));
        // 下面从隔离库真实原行生成摘要与数据库物理身份，并沿生产解析器验证同一结构。
        await db.Database.OpenConnectionAsync();
        await db.Database.ExecuteSqlRawAsync("SET TIME ZONE 'UTC'");
        var facts = JsonSerializer.Deserialize<string[]>((await db.Database.SqlQuery<string>($"""
            SELECT json_build_array((pg_control_system()).system_identifier::text,current_database(),current_user,
              encode(sha256(convert_to((to_jsonb(q)-'LeaseOwner'-'LeaseUntilUtc')::text,'UTF8')),'hex'),
              (SELECT encode(sha256(convert_to(to_jsonb(a)::text,'UTF8')),'hex') FROM governance.audit_records a WHERE a."Id"={cancelId}))::text AS "Value"
            FROM semantic_query."Queries" q WHERE q."Id"={qid}
            """).SingleAsync()))!;
        var fields = new Dictionary<string, object>
        {
            ["taskId"] = "G4-ORACLE-MAPPING-QUERY-001",
            ["runId"] = "implementation-01",
            ["operationId"] = Guid.NewGuid().ToString("N"),
            ["attemptId"] = Guid.NewGuid().ToString("N"),
            ["operatorId"] = "os-uid-501",
            ["systemIdentifier"] = facts[0],
            ["database"] = facts[1],
            ["databaseUser"] = facts[2],
            ["stableRowSha256"] = facts[3],
            ["cancelAuditId"] = cancelId,
            ["cancelAuditSha256"] = facts[4],
            ["organizationId"] = "org-demo",
            ["queryId"] = qid,
            ["connectionId"] = cid,
            ["owner"] = G4OracleMaintenanceProof.Owner,
            ["originalFence"] = 1,
            ["terminalFence"] = 2,
            ["clientId"] = "0e224578b55b4b479d98d3fa4ff1ac46",
            ["instanceId"] = 1,
            ["conId"] = 3,
            ["sid"] = 60,
            ["serial"] = 51748,
            ["audsid"] = 50045,
            ["sqlId"] = "dum3m3c96vc07",
            ["sqlExecId"] = 16777219,
            ["sourceContainerId"] = G4OracleMaintenanceProof.SourceContainer,
            ["platformContainerId"] = G4OracleMaintenanceProof.PlatformContainer,
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
        G4OracleMaintenanceProof Proof(Dictionary<string, object> supplied)
        {
            // 仅测试进程可选隔离数据库；正式 CLI 固定原平台内容键。
            var bytes = JsonSerializer.SerializeToUtf8Bytes(supplied);
            return G4OracleMaintenanceProof.Read(bytes, G4QueryCanonical.Hash(bytes), "os-uid-501", new string('a', 64), new string('b', 64), isolated: true);
        }
        async Task<string> Recover(G4OracleMaintenanceProof authorized, ITransactionalAuditWriter writer)
        {
            await using var fresh = await queries.CreateDbContextAsync();
            return await G4OracleMaintenance.RecoverAsync(fresh, writer, authorized,
                (c, t, ct) => OracleS0Maintenance.ReadAuditAsync(governance, c, t, ct), CancellationToken.None);
        }
        foreach (var (field, wrong) in new (string, object)[] { ("queryId", history.Id), ("owner", "other"), ("terminalFence", 3), ("terminationProofSha256", new string('0', 64)) })
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
        Assert.AreEqual(1, await gov.AuditRecords.CountAsync(a => a.Resource == qid && a.Action == "data.query.cancel"));
        var after = await db.Queries.AsNoTracking().SingleAsync(q => q.Id == qid);
        Assert.IsNull(after.LeaseOwner);
        Assert.IsNull(after.LeaseUntilUtc);
        Assert.AreEqual(2L, after.Fence);
        Assert.AreEqual("CANCELLED", after.ExecutionStatus);
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
        var stale = new G4QueryRecord { Id = qid, LeaseOwner = G4OracleMaintenanceProof.Owner, Fence = 1, RequestHash = row.RequestHash };
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
        await db.Queries.Where(q => q.Id == history.Id).ExecuteUpdateAsync(u => u.SetProperty(q => q.ExecutionStatus, "CANCELLED")
            .SetProperty(q => q.CancelRequested, true).SetProperty(q => q.LeaseOwner, (string?)null).SetProperty(q => q.LeaseUntilUtc, (DateTimeOffset?)null));
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

    /// <summary>提供唯一 Oracle 绑定，使正式查询的历史、重放和新准入都到达同一连接门禁。</summary>
    private sealed class OracleTestBindings : IG4QueryBindingReader
    {
        /// <summary>只替换测试的 Mapping/目录边界；源打开次数另用物理入口计数。</summary>
        private readonly G4QueryBindingContext context;

        /// <summary>构造一个明确根和无其他分支的测试发布。</summary>
        public OracleTestBindings(G4QueryBinding binding, ResourceScope scope)
        {
            // 当前测试不会读取外部目录和审核材料；这些字段不用于替代授权或当前版本。
            var entity = new MappingEntityBinding
            {
                Id = "asset",
                EntityClassIri = "urn:omq:Asset",
                IdentitySpecId = "identity",
                TemporalSpecId = "time",
                DatasetRef = null!,
                ScopeFields = null!
            };
            // 源分发仍由真正执行器读取这份 Oracle 类型标签。
            var version = new MappingVersionBinding
            {
                SourceType = "ORACLE",
                SourceConnectionId = binding.ConnectionId,
                AdapterVersion = "oracle-mapping-v1",
                ExecutorVersion = "oracle-mapping-validator-v1",
                CanonicalVersion = "mapping-canonical-v1",
                SecretVersion = 1,
                AuthorizationEpoch = 1,
                ConnectionRevision = 1,
                ConfigHash = binding.ConfigHash,
                SourceCatalogSnapshotId = binding.OriginalCatalogSnapshotId,
                SourceCatalogFingerprint = binding.OriginalCatalogFingerprint,
                OntologyReleaseId = binding.OntologyReleaseId,
                OntologyManifestHash = binding.ManifestHash,
                MappingHash = binding.ManifestHash,
                ValidationHash = binding.ManifestHash,
                ImpactHash = binding.ManifestHash,
                AssessmentId = "assessment"
            };
            context = new G4QueryBindingContext
            {
                Binding = binding,
                Scope = scope,
                CurrentCatalog = null!,
                OriginalCatalog = null!,
                Manifest = new MappingReleaseManifest
                {
                    SchemaVersion = "1",
                    MappingReleaseId = binding.MappingReleaseId,
                    MappingId = binding.MappingId,
                    Scope = scope,
                    OriginDraftId = "draft",
                    OriginDraftRevision = 1,
                    Binding = version,
                    ReviewReceipt = null!,
                    CreatedAtUtc = DateTimeOffset.UtcNow,
                    Mapping = new MappingDefinition { Entities = [entity], Properties = [], Relations = [], IdentitySpecs = [], TemporalSpecs = [], Conversions = [], UnitSpecs = [] }
                }
            };
        }

        /// <summary>返回一致的当前测试版本；真实治理会话及 grant 由外层工厂处理。</summary>
        public Task<G4QueryBindingContext> CaptureAsync(ActorContext actor, G4SemanticQuery query, long epoch, CancellationToken token) => Task.FromResult(context);

        /// <summary>拒绝测试范围与固定连接不一致的历史定位。</summary>
        public Task<G4QueryBindingContext> ReadHistoricalAsync(ActorContext actor, G4QueryBinding binding, ResourceScope scope, CancellationToken token)
        {
            Assert.AreEqual(context.Binding.ConnectionId, binding.ConnectionId);
            Assert.AreEqual(context.Scope.OrganizationId, scope.OrganizationId);
            return Task.FromResult(context);
        }

        /// <summary>确保新执行使用来自实际准入事务的连接。</summary>
        public Task VerifyInTransactionAsync(ActorContext actor, G4SemanticQuery query, G4QueryBinding expected, DbConnection connection, DbTransaction transaction, CancellationToken token)
        {
            Assert.AreSame(connection, transaction.Connection);
            Assert.AreEqual(context.Binding.ConnectionId, expected.ConnectionId);
            return Task.CompletedTask;
        }

        /// <summary>历史恢复的 ACL 收据在真实短事务中消费。</summary>
        public Task VerifyHistoricalAccessInTransactionAsync(ActorContext actor, G4QueryConnectionAccess access, DbConnection connection, DbTransaction transaction, CancellationToken token)
        {
            Assert.AreSame(connection, transaction.Connection);
            Assert.AreEqual(context.Binding.ConnectionId, access.ConnectionId);
            return Task.CompletedTask;
        }
    }

    /// <summary>真实 PG 准入的源计数器。只在物理打开同步点通过后增加，不实际创建 Oracle 会话。</summary>
    private sealed class OracleOpenCounter(G4QueryProjection projection) : IG4SourceQueryReader
    {
        /// <summary>经共享容量事务核验的模拟源打开次数。</summary>
        public int Opens { get; private set; }

        /// <summary>返回测试账号获准的完整投影。</summary>
        public G4QueryProjection DescribeProjection(G4QueryBindingContext context, string entityBindingId) => projection;

        /// <summary>消费生产源适配器使用的相同物理打开/交锁入口。</summary>
        public async Task<G4QueryConnectionAccess> VerifyAccessAsync(G4QueryBindingContext context, MappingAuthorizationProof proof, string entityBindingId, DateTimeOffset deadline, CancellationToken token)
        {
            await G4OracleSourceOpen.BeforePhysicalOpenAsync(token);
            Opens++;
            await G4OracleSourceOpen.AfterPhysicalOpenAsync();
            return new G4QueryConnectionAccess
            {
                ConnectionId = context.Binding.ConnectionId,
                Revision = 1,
                SecretVersion = 1,
                ConfigHash = context.Binding.ConfigHash,
                Scope = context.Scope,
                Projection = projection,
                CheckedAtUtc = DateTimeOffset.UtcNow
            };
        }

        /// <summary>受阻的新正式执行不能到达源执行点。</summary>
        public Task<G4SourceQueryRead> ReadAsync(G4QueryBindingContext context, MappingAuthorizationProof proof, string entityBindingId, G4SemanticQuery query,
            DateTimeOffset deadline, CancellationToken token, G4QueryBranchFilter? branch = null) =>
            throw new AssertFailedException("封闭期间进入了源执行。");
    }
}
