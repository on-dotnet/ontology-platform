using System.Data.Common;
using System.Globalization;
using System.Security.Claims;
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

/// <summary>真实PG、真实票据和治理参与者验证查询提交边界；映射材料校验另由S1真实发布验证。</summary>
[TestClass]
[DoNotParallelize]
public sealed class G4QueryRaceTests
{
    /// <summary>当前授权撤销先提交时，旧证明不能写成功结果或成功审计。</summary>
    [TestMethod]
    public async Task RevocationBlocksAtomicResultAndAudit()
    {
        // 只接受本轮受控容器传入的合成PG，不跳过真实验证。
        var connection = Environment.GetEnvironmentVariable("G4_QUERY_TEST_CONNECTION");
        Assert.IsFalse(string.IsNullOrWhiteSpace(connection));
        await G4QueryPersistenceTests.DemandIsolatedDatabaseAsync(connection!);
        // 治理与查询各用自己模型工厂，共享实际物理数据库事务。
        await using var provider = new ServiceCollection()
            .AddDbContextFactory<GovernanceDbContext>(options => options.UseNpgsql(connection, postgres => postgres.MigrationsHistoryTable("__EFMigrationsHistory", "governance")))
            .AddDbContextFactory<G4QueryDbContext>(options => options.UseNpgsql(connection, postgres => postgres.MigrationsHistoryTable("__EFMigrationsHistory", "semantic_query")))
            .BuildServiceProvider();
        // 正式治理工厂使授权参与者加入事务时保持模块写表边界。
        var governanceFactory = provider.GetRequiredService<IDbContextFactory<GovernanceDbContext>>();
        // 正式查询工厂用于真实状态与密文存储。
        var queryFactory = provider.GetRequiredService<IDbContextFactory<G4QueryDbContext>>();
        await using var governance = await governanceFactory.CreateDbContextAsync();
        await governance.Database.MigrateAsync();
        await using var queryDatabase = await queryFactory.CreateDbContextAsync();
        await queryDatabase.Database.MigrateAsync();
        // 随机组织只属于本测试，不清理或修改历史任务行。
        var suffix = Guid.NewGuid().ToString("N");
        // 与真实Cookie票据使用完全一致的服务器声明。
        var actor = new ActorContext { SubjectId = "query-user", OrganizationId = "query-test-" + suffix, SiteIds = ["site-1"],
            Roles = ["platform.viewer"], TraceId = "trace-1", CorrelationId = "correlation-1" };
        // 本测试明确使用合成身份，不声称经过外部IdP登录。
        var principal = new ClaimsPrincipal(new ClaimsIdentity(new[]
        {
            new Claim("sub", actor.SubjectId), new Claim("organization_id", actor.OrganizationId),
            new Claim("site_ids", "site-1"), new Claim(ClaimTypes.Role, "platform.viewer")
        }, "Cookies"));
        // 票据加密仍调用正式存储和正式解密校验，不能用永远返回true的替身。
        var protection = new EphemeralDataProtectionProvider();
        // HttpContext只承载合成已认证主体，不接受客户端proof。
        var accessor = new HttpContextAccessor { HttpContext = new DefaultHttpContext { User = principal } };
        // 正式票据存储使测试能覆盖当前PG会话撤销状态。
        var tickets = new PostgresTicketStore(governanceFactory, protection, accessor, TimeProvider.System);
        // 服务器返回的是不可逆会话引用，原ticket不输出到证据。
        var sessionId = await tickets.StoreAsync(new AuthenticationTicket(principal,
            new AuthenticationProperties { ExpiresUtc = DateTimeOffset.UtcNow.AddMinutes(15) }, "Cookies"));
        // 每个真实源投影都需要单条完整授权，本测试不从viewer自动授予。
        var grant = new MappingAuthorizationGrant { Id = "query-grant-" + suffix, SubjectId = actor.SubjectId,
            OrganizationId = actor.OrganizationId, SiteIds = ["site-1"], Permission = "data.query.execute", ConnectionId = "connection-1",
            ObjectRefs = ["production/assets"], FieldRefs = ["production/assets/1/id"], ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(15) };
        governance.MappingAuthorizationGrants.Add(grant);
        await governance.SaveChangesAsync();
        // 使用实际治理参与者、数据库epoch触发器及宿主票据校验器。
        var authority = new QueryAuthorizationParticipant(new MappingAuthorizationParticipant(governanceFactory, new MappingSessionAuthority(protection), TimeProvider.System));
        // 安全范围来自当前服务器主体，不来自自由客户端声明。
        var scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = actor.SiteIds };
        // session-only不授予源读取，只为事务提供当前组织epoch。
        var session = await authority.CaptureSessionAsync(actor, sessionId, scope, CancellationToken.None);
        // 完整单条源grant的真实捕获，不能直接伪造epoch。
        var proof = await authority.CaptureAsync(session with { ConnectionId = grant.ConnectionId, ObjectRefs = grant.ObjectRefs, FieldRefs = grant.FieldRefs }, CancellationToken.None);
        // 本测试明确隔离映射复核，不能据此证明真实发布或S1端到端通过。
        var binding = Binding(session.AuthorizationEpoch);
        // 存储元数据固定真实字段集合，撤权后不能换成空投影。
        var state = new G4QueryState { Binding = binding, Scope = scope, Projections = [new G4QueryProjection { ObjectRefs = grant.ObjectRefs, FieldRefs = grant.FieldRefs }] };
        // 共用存储实现与实际事务审计写入器。
        var bindingReader = new FixedBindingReader();
        // 事务实现必须区分新执行与原查询幂等恢复。
        var store = new G4QueryResultStore(queryFactory, authority, bindingReader, new TransactionalAuditWriter(governanceFactory), protection, TimeProvider.System);
        // 请求形状遵守正式封闭合同，但不在本测试访问源。
        var query = new G4SemanticQuery { AssetId = "asset-1", OntologyReleaseId = "ontology-1", MappingReleaseIds = ["mapping-1"],
            CapabilityId = "g4_read_observations", CapabilityVersion = new string('a',64), RelationshipIris = [], Depth = 1, MaxRows = 10, TimeoutMs = 5000, Filters = new G4QueryFilters() };
        // 准入后只有本实例持有本次fence，数据库真实保存RUNNING。
        var admission = await store.AdmitAsync(session, [proof], query, state, suffix, null, "instance-1", DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None);
        try
        {
            Assert.IsTrue(admission.Created);
            bindingReader.RejectNewExecution = true;
            // 同键同请求只返回同一已登记执行，不再次占用主体槽位。
            var repeated = await store.AdmitAsync(session, [proof], query, state, suffix, null, "instance-2", DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None);
            Assert.IsFalse(repeated.Created);
            Assert.AreEqual(admission.Record.Id, repeated.Record.Id);
            bindingReader.RejectNewExecution = false;
            // 第二个新键不能绕过每主体一个在途的PG容量约束。
            var capacity = await Assert.ThrowsAsync<SemanticOperationException>(() => store.AdmitAsync(session, [proof], query, state,
                suffix + "-other", null, "instance-2", DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None));
            Assert.AreEqual(429, capacity.Status);
            // 仅替换测试结果scope与真实测试组织相符，不把wire fixture当源证据。
            var fixture = G4QueryTests.FixtureResult();
            // 数据及来源同时使用同一组织，避免被其他形状错误掩盖授权反例。
            var result = fixture with
            {
                Data = [((G4ObservationDatum)fixture.Data[0]) with { Identity = ((G4ObservationDatum)fixture.Data[0]).Identity with { OrganizationId = actor.OrganizationId } }],
                Evidence = [fixture.Evidence[0] with { Scope = scope }]
            };
            // 回执仅为事务测试材料，明确不是源执行证据。
            var receipts = new[] { G4QueryTests.ReceiptFixture(admission.Record.Id, binding, result) };
            // 不能只校验lease中的hash：传给提交的实际query也必须与准入原件一致。
            var changed = query with { Filters = new G4QueryFilters { EntityExternalId = "different-entity" } };
            // 即使范围、版本和授权全部相同，也必须拒绝换请求后提交到旧queryId。
            var mismatch = await Assert.ThrowsAsync<SemanticOperationException>(() => store.CompleteAsync(admission.Record, session, [proof], changed, state, result, receipts, CancellationToken.None));
            Assert.AreEqual(409, mismatch.Status);
            // 真实数据库撤销触发组织epoch递增，旧证明不可继续提交。
            grant.RevokedAtUtc = DateTimeOffset.UtcNow;
            await governance.SaveChangesAsync();
            // 失败必须来自当前授权，不能仅靠后续租约自然超时。
            var denied = await Assert.ThrowsAsync<SemanticOperationException>(() => store.CompleteAsync(admission.Record, session, [proof], query, state, result, receipts, CancellationToken.None));
            Assert.AreEqual(403, denied.Status);
            // 新上下文检查整笔事务没有残留成功数据或成功审计。
            var saved = await queryDatabase.Queries.AsNoTracking().SingleAsync(row => row.Id == admission.Record.Id);
            Assert.AreEqual("RUNNING", saved.ExecutionStatus);
            Assert.AreEqual(0, saved.ResultCiphertext.Length);
            Assert.IsNull(saved.ResultHash);
            Assert.IsFalse(await governance.AuditRecords.AnyAsync(row => row.Resource == admission.Record.Id && row.Action == "data.query.execute"));
            await queryDatabase.Queries.Where(row => row.Id == admission.Record.Id).ExecuteDeleteAsync();
            // 重新授权必须产生新epoch及新Query，不允许复活失败执行的旧证明。
            grant.RevokedAtUtc = null;
            await governance.SaveChangesAsync();
            // 新执行重新捕获当前会话和完整grant。
            var restoredSession = await authority.CaptureSessionAsync(actor, sessionId, scope, CancellationToken.None);
            // 原字段集合保持一致，但授权版本必须来自真实数据库。
            var restoredProof = await authority.CaptureAsync(restoredSession with { ConnectionId = grant.ConnectionId, ObjectRefs = grant.ObjectRefs, FieldRefs = grant.FieldRefs }, CancellationToken.None);
            // 新查询使用新版本绑定；旧历史结果从不被重写。
            var restoredState = state with { Binding = Binding(restoredSession.AuthorizationEpoch) };
            // 新键明确发起一次执行，不隐式重跑前一个queryId。
            var committed = await store.AdmitAsync(restoredSession, [restoredProof], query, restoredState, suffix + "-fresh", null,
                "instance-2", DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None);
            try
            {
                // 故障发生在真实审计INSERT之后，必须连同密文和回执一起回滚。
                var failingAuditStore = new G4QueryResultStore(queryFactory, authority, bindingReader,
                    new WriteThenFailAudit(new TransactionalAuditWriter(governanceFactory)), protection, TimeProvider.System);
                // 当前grant、Binding和结果都合法，避免其他拒绝条件遮蔽审计故障。
                var auditFailure = await Assert.ThrowsAsync<SemanticOperationException>(() => failingAuditStore.CompleteAsync(committed.Record,
                    restoredSession, [restoredProof], query, restoredState, result,
                    [G4QueryTests.ReceiptFixture(committed.Record.Id, restoredState.Binding, result)], CancellationToken.None));
                Assert.AreEqual("synthetic_audit_unavailable", auditFailure.Code);
                // 独立上下文只看已提交状态，不能读同一跟踪对象假装回滚。
                var rolledBack = await queryDatabase.Queries.AsNoTracking().SingleAsync(row => row.Id == committed.Record.Id);
                Assert.AreEqual("RUNNING", rolledBack.ExecutionStatus);
                Assert.AreEqual(0, rolledBack.ResultCiphertext.Length);
                Assert.AreEqual(0, G4QueryResultStore.ReadState(rolledBack).Receipts.Length);
                Assert.IsFalse(await governance.AuditRecords.AnyAsync(row => row.Resource == committed.Record.Id));
                await store.CompleteAsync(committed.Record, restoredSession, [restoredProof], query, restoredState, result,
                    [G4QueryTests.ReceiptFixture(committed.Record.Id, restoredState.Binding, result)], CancellationToken.None);
                // 新上下文同时看到COMPLETED、密文、回执及治理成功审计。
                var complete = await queryDatabase.Queries.AsNoTracking().SingleAsync(row => row.Id == committed.Record.Id);
                Assert.AreEqual("COMPLETED", complete.ExecutionStatus);
                CollectionAssert.AreEqual(G4QueryCanonical.Result(result), G4QueryResultStore.Unprotect(protection, complete.Id, complete.ResultCiphertext, complete.ResultHash!));
                Assert.IsTrue(await governance.AuditRecords.AnyAsync(row => row.Resource == complete.Id && row.Action == "data.query.execute" && row.Outcome == "allowed"));
                // 已完成历史记录恢复不能再要求当前Active回到原发布。
                bindingReader.RejectNewExecution = true;
                // 恢复仍使用当前真实完整grant，并保持原queryId与结果hash。
                var historical = await store.AdmitAsync(restoredSession, [restoredProof], query, restoredState, suffix + "-fresh", null,
                    "instance-3", DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None);
                Assert.IsFalse(historical.Created);
                Assert.AreEqual(complete.Id, historical.Record.Id);
                Assert.AreEqual(complete.ResultHash, historical.Record.ResultHash);
                // 成功先提交时取消不能销毁历史结果。
                var finished = await Assert.ThrowsAsync<SemanticOperationException>(() => store.CancelAsync(complete.Id, restoredSession, [restoredProof], CancellationToken.None));
                Assert.AreEqual(409, finished.Status);
                // 无result.read grant不能用execute证明换标签恢复结果，也不能留下读取成功审计。
                var access = new G4QueryConnectionAccess { ConnectionId = restoredState.Binding.ConnectionId, Revision = 1,
                    ConfigHash = restoredState.Binding.ConfigHash, SecretVersion = 1, Scope = scope,
                    Projection = restoredState.Projections[0], CheckedAtUtc = DateTimeOffset.UtcNow };
                // 当前证明的字段集合相同不等于真实数据库存在另一项许可。
                var fabricatedRead = restoredProof with { Permission = "data.query.result.read" };
                var noRead = await Assert.ThrowsAsync<SemanticOperationException>(() => store.ReadAuthorizedAsync(complete.Id, restoredSession,
                    [restoredProof], [fabricatedRead], [], [access], true, false, CancellationToken.None));
                Assert.AreEqual(403, noRead.Status);
                Assert.IsFalse(await governance.AuditRecords.AnyAsync(row => row.Resource == complete.Id && row.Action == "data.query.read"));
                // 显式授予同一完整投影的读取许可后，必须重新捕获真实epoch。
                var readGrant = new MappingAuthorizationGrant { Id = "query-read-" + suffix, SubjectId = actor.SubjectId,
                    OrganizationId = actor.OrganizationId, SiteIds = ["site-1"], Permission = "data.query.result.read", ConnectionId = grant.ConnectionId,
                    ObjectRefs = grant.ObjectRefs, FieldRefs = grant.FieldRefs, ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(15) };
                governance.MappingAuthorizationGrants.Add(readGrant);
                await governance.SaveChangesAsync();
                restoredSession = await authority.CaptureSessionAsync(actor, sessionId, scope, CancellationToken.None);
                restoredProof = await authority.CaptureAsync(restoredSession with { ConnectionId = grant.ConnectionId,
                    ObjectRefs = grant.ObjectRefs, FieldRefs = grant.FieldRefs }, CancellationToken.None);
                // 读取许可仍由真实参与者捕获，不使用上面的伪造证明。
                var readProof = await authority.CaptureAsync(restoredProof with { Permission = "data.query.result.read" }, CancellationToken.None);
                // 此处仅隔离Connections当前版本核验，不声称已执行真实源ACL检查。
                var recovered = await store.ReadAuthorizedAsync(complete.Id, restoredSession, [restoredProof], [readProof], [],
                    [access with { CheckedAtUtc = DateTimeOffset.UtcNow }], true, false, CancellationToken.None);
                CollectionAssert.AreEqual(G4QueryCanonical.Result(result), recovered.ResultBytes!);
                Assert.AreEqual(complete.ResultHash, recovered.View.ResultHash);
                Assert.AreEqual(1, bindingReader.HistoricalChecks);
                Assert.AreEqual(1, await governance.AuditRecords.CountAsync(row => row.Resource == complete.Id && row.Action == "data.query.read"));
                // 撤销读取许可先提交后，旧读取证明不能重放缓存字节或补成功审计。
                readGrant.RevokedAtUtc = DateTimeOffset.UtcNow;
                await governance.SaveChangesAsync();
                // execute仍有效，但组织epoch已经变化。
                var revokedRead = await Assert.ThrowsAsync<SemanticOperationException>(() => store.ReadAuthorizedAsync(complete.Id,
                    restoredSession, [restoredProof], [readProof], [], [access], true, false, CancellationToken.None));
                Assert.AreEqual(403, revokedRead.Status);
                Assert.AreEqual(1, await governance.AuditRecords.CountAsync(row => row.Resource == complete.Id && row.Action == "data.query.read"));
                restoredSession = await authority.CaptureSessionAsync(actor, sessionId, scope, CancellationToken.None);
                restoredProof = await authority.CaptureAsync(restoredSession with { ConnectionId = grant.ConnectionId,
                    ObjectRefs = grant.ObjectRefs, FieldRefs = grant.FieldRefs }, CancellationToken.None);
                restoredState = restoredState with { Binding = Binding(restoredSession.AuthorizationEpoch) };
                // 可控时间只驱动后台保留期；不把过期票据伪装成仍有访问授权。
                var expiryStore = new G4QueryResultStore(queryFactory, authority, bindingReader, new TransactionalAuditWriter(governanceFactory), protection,
                    new FixedTime(DateTimeOffset.UtcNow.AddHours(25)));
                Assert.IsTrue(await expiryStore.SweepAsync(CancellationToken.None) >= 1);
                // 二十四小时之后原结果字节和请求值已清除，安全回执暂留。
                var expired = await queryDatabase.Queries.AsNoTracking().SingleAsync(row => row.Id == complete.Id);
                Assert.AreEqual(0, expired.ResultCiphertext.Length);
                Assert.AreEqual(0, expired.RequestBytes.Length);
                Assert.AreEqual(0, expired.ResultSize);
                Assert.IsTrue(expired.BindingBytes.Length > 0);
                // 七天后准确记录彻底移除，治理无值删除审计独立保留。
                var retentionStore = new G4QueryResultStore(queryFactory, authority, bindingReader, new TransactionalAuditWriter(governanceFactory), protection,
                    new FixedTime(DateTimeOffset.UtcNow.AddDays(8)));
                Assert.IsTrue(await retentionStore.SweepAsync(CancellationToken.None) >= 1);
                Assert.IsFalse(await queryDatabase.Queries.AnyAsync(row => row.Id == complete.Id));
                Assert.AreEqual(2, await governance.AuditRecords.CountAsync(row => row.Resource == complete.Id && row.Action == "data.query.expire"));
            }
            finally
            {
                // 只回收本测试准确新查询，成功审计按治理规则保留。
                await queryDatabase.Queries.Where(row => row.Id == committed.Record.Id).ExecuteDeleteAsync();
            }
            bindingReader.RejectNewExecution = false;
            // 新独立查询用于验证相反提交顺序，不重用成功结果的身份。
            var cancelling = await store.AdmitAsync(restoredSession, [restoredProof], query, restoredState, suffix + "-cancel", null,
                "instance-2", DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None);
            try
            {
                // 取消必须提交CANCELLED及审计后才返回。
                var cancelled = await store.CancelAsync(cancelling.Record.Id, restoredSession, [restoredProof], CancellationToken.None);
                Assert.AreEqual("CANCELLED", cancelled.ExecutionStatus);
                Assert.IsTrue(cancelled.Fence > cancelling.Record.Fence);
                // 原worker即使完成源读取也不能再保存成功结果。
                var late = await Assert.ThrowsAsync<SemanticOperationException>(() => store.CompleteAsync(cancelling.Record, restoredSession, [restoredProof], query, restoredState, result,
                    [G4QueryTests.ReceiptFixture(cancelling.Record.Id, restoredState.Binding, result)], CancellationToken.None));
                Assert.AreEqual(409, late.Status);
                Assert.IsFalse(await store.HeartbeatAsync(cancelling.Record, CancellationToken.None));
                Assert.IsTrue(await governance.AuditRecords.AnyAsync(row => row.Resource == cancelling.Record.Id && row.Action == "data.query.cancel"));
                Assert.IsFalse(await governance.AuditRecords.AnyAsync(row => row.Resource == cancelling.Record.Id && row.Action == "data.query.execute"));
            }
            finally
            {
                // 准确身份回收，不清空任何共享或历史表。
                await queryDatabase.Queries.Where(row => row.Id == cancelling.Record.Id).ExecuteDeleteAsync();
            }
        }
        finally
        {
            // 失败反例同样只回收本测试准确查询身份，避免占用后续任务容量。
            await queryDatabase.Queries.Where(row => row.Id == admission.Record.Id).ExecuteDeleteAsync();
            await tickets.RemoveAsync(sessionId);
        }
    }

    /// <summary>真实PG跨上下文执行连接二槽/任务四槽；失联维护仅终结状态，旧fence不能续租。</summary>
    [TestMethod]
    public async Task ConnectionAndTaskCapacityAndLostLeaseAreAtomic()
    {
        // 仅消费当前任务显式提供的合成平台库。
        var connection = Environment.GetEnvironmentVariable("G4_QUERY_TEST_CONNECTION");
        Assert.IsFalse(string.IsNullOrWhiteSpace(connection));
        await G4QueryPersistenceTests.DemandIsolatedDatabaseAsync(connection!);
        // 两模块各自保持正式工厂与写表边界。
        await using var provider = new ServiceCollection()
            .AddDbContextFactory<GovernanceDbContext>(options => options.UseNpgsql(connection, postgres => postgres.MigrationsHistoryTable("__EFMigrationsHistory", "governance")))
            .AddDbContextFactory<G4QueryDbContext>(options => options.UseNpgsql(connection, postgres => postgres.MigrationsHistoryTable("__EFMigrationsHistory", "semantic_query")))
            .BuildServiceProvider();
        // 查询服务每次调用独立上下文，容量不依赖进程内锁。
        var queryFactory = provider.GetRequiredService<IDbContextFactory<G4QueryDbContext>>();
        // 当前票据、grant和审计全部使用真实治理模型。
        var governanceFactory = provider.GetRequiredService<IDbContextFactory<GovernanceDbContext>>();
        await using var governance = await governanceFactory.CreateDbContextAsync();
        await using var database = await queryFactory.CreateDbContextAsync();
        await governance.Database.MigrateAsync();
        await database.Database.MigrateAsync();
        // 随机组织和连接身份防止与本轮其他真实HTTP查询混淆。
        var suffix = Guid.NewGuid().ToString("N");
        // 当前测试所有记录都归属于这一明确组织。
        var organization = "capacity-" + suffix;
        // 真票据加密只在本测试内存中，不落盘或输出。
        var protection = new EphemeralDataProtectionProvider();
        // 五个不同主体用于分别触发连接及任务约束。
        var actors = Enumerable.Range(0, 5).Select(index => new ActorContext { SubjectId = "actor-" + index,
            OrganizationId = organization, SiteIds = ["site-1"], Roles = ["platform.viewer"], TraceId = "trace-1", CorrelationId = "correlation-1" }).ToArray();
        // 会话身份完全由正式票据存储生成。
        var sessions = new List<(PostgresTicketStore Store, string Id)>();
        // 精确跟踪本测试实际准入的查询ID，失败时同样执行白名单清理。
        var admissions = new List<G4QueryAdmission>();
        // 全部grant先完成，后续捕获固定同一个真实授权epoch。
        var grants = actors.SelectMany(actor => Enumerable.Range(1, 3).Select(index => new MappingAuthorizationGrant
        {
            Id = "capacity-grant-" + suffix + actor.SubjectId + index, SubjectId = actor.SubjectId, OrganizationId = organization,
            SiteIds = ["site-1"], Permission = "data.query.execute", ConnectionId = "capacity-connection-" + suffix + index,
            ObjectRefs = ["production/assets"], FieldRefs = ["production/assets/1/id"], ExpiresAtUtc = DateTimeOffset.UtcNow.AddMinutes(15)
        })).ToArray();
        governance.MappingAuthorizationGrants.AddRange(grants);
        await governance.SaveChangesAsync();
        // 存储测试仍明确替换映射参与者，不将它冒充正式源/映射HTTP证明。
        var authority = new QueryAuthorizationParticipant(new MappingAuthorizationParticipant(governanceFactory, new MappingSessionAuthority(protection), TimeProvider.System));
        // 不同实例名共用真实平台PG容量锁。
        var store = new G4QueryResultStore(queryFactory, authority, new FixedBindingReader(), new TransactionalAuditWriter(governanceFactory), protection, TimeProvider.System);
        try
        {
            foreach (var actor in actors)
            {
                // 每主体拥有独立可信认证票据，角色不替代显式grant。
                var principal = new ClaimsPrincipal(new ClaimsIdentity(new[] { new Claim("sub", actor.SubjectId),
                    new Claim("organization_id", organization), new Claim("site_ids", "site-1"), new Claim(ClaimTypes.Role, "platform.viewer") }, "Cookies"));
                // 正式PostgresTicketStore确保会话检查不使用恒真替身。
                var tickets = new PostgresTicketStore(governanceFactory, protection,
                    new HttpContextAccessor { HttpContext = new DefaultHttpContext { User = principal } }, TimeProvider.System);
                sessions.Add((tickets, await tickets.StoreAsync(new AuthenticationTicket(principal,
                    new AuthenticationProperties { ExpiresUtc = DateTimeOffset.UtcNow.AddMinutes(15) }, "Cookies"))));
            }
            // 每次准入重新捕获真实proof，查询本身不访问外部源。
            async Task<G4QueryAdmission> Admit(int actorIndex, int connectionIndex)
            {
                // 本例明确的非空连接身份供grant匹配和固定Binding共同使用。
                var connectionId = "capacity-connection-" + suffix + connectionIndex;
                // 连接/字段集合必须由一条完整grant覆盖。
                var grant = grants.Single(item => item.SubjectId == actors[actorIndex].SubjectId && item.ConnectionId == connectionId);
                // 请求scope与真实票据相同，不拼多条grant。
                var scope = new ResourceScope { OrganizationId = organization, SiteIds = ["site-1"] };
                // session-only与字段许可分开捕获。
                var session = await authority.CaptureSessionAsync(actors[actorIndex], sessions[actorIndex].Id, scope, CancellationToken.None);
                // 当前完整执行许可来自真实数据库。
                var proof = await authority.CaptureAsync(session with { ConnectionId = grant.ConnectionId, ObjectRefs = grant.ObjectRefs, FieldRefs = grant.FieldRefs }, CancellationToken.None);
                // 每条新查询使用不同键，不能因幂等重放绕过本次容量反例。
                var query = new G4SemanticQuery { AssetId = "asset-1", OntologyReleaseId = "ontology-1", MappingReleaseIds = ["mapping-1"],
                    CapabilityId = "g4_resolve_entity", CapabilityVersion = new string('a', 64), RelationshipIris = [], Depth = 1, MaxRows = 10, TimeoutMs = 5000, Filters = new G4QueryFilters() };
                // 映射仅为明确替身材料，连接身份仍对应实际授权grant。
                var state = new G4QueryState { Binding = Binding(session.AuthorizationEpoch) with { ConnectionId = connectionId }, Scope = scope,
                    Projections = [new G4QueryProjection { ObjectRefs = grant.ObjectRefs, FieldRefs = grant.FieldRefs }] };
                return await store.AdmitAsync(session, [proof], query, state, Guid.NewGuid().ToString("N"), null,
                    "instance-" + actorIndex, DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None);
            }
            admissions.Add(await Admit(0, 1));
            admissions.Add(await Admit(1, 1));
            Assert.AreEqual(429, (await Assert.ThrowsAsync<SemanticOperationException>(() => Admit(2, 1))).Status);
            admissions.Add(await Admit(2, 2));
            admissions.Add(await Admit(3, 2));
            Assert.AreEqual(429, (await Assert.ThrowsAsync<SemanticOperationException>(() => Admit(4, 3))).Status);
            Assert.AreEqual(4, await database.Queries.CountAsync(row => row.OrganizationId == organization && row.ExecutionStatus == "RUNNING"));
            // 只推进该维护实例时钟，既有lease到期后不得重新发起任何源查询。
            var sweeper = new G4QueryResultStore(queryFactory, authority, new FixedBindingReader(), new TransactionalAuditWriter(governanceFactory), protection,
                new FixedTime(DateTimeOffset.UtcNow.AddSeconds(6)));
            await sweeper.SweepAsync(CancellationToken.None);
            foreach (var admission in admissions)
            {
                // 跨上下文确认FAILED、无密文以及递增fence；旧执行引用无法续租。
                var saved = await database.Queries.AsNoTracking().SingleAsync(row => row.Id == admission.Record.Id);
                Assert.AreEqual("FAILED", saved.ExecutionStatus);
                Assert.IsTrue(saved.Fence > admission.Record.Fence);
                Assert.AreEqual(0, saved.ResultCiphertext.Length);
                Assert.IsFalse(await store.HeartbeatAsync(admission.Record, CancellationToken.None));
            }
        }
        finally
        {
            await database.Queries.Where(row => row.OrganizationId == organization).ExecuteDeleteAsync();
            foreach (var session in sessions) await session.Store.RemoveAsync(session.Id);
            await governance.MappingAuthorizationGrants.Where(row => row.OrganizationId == organization).ExecuteDeleteAsync();
            Assert.AreEqual(0, await database.Queries.CountAsync(row => row.OrganizationId == organization));
        }
    }

    /// <summary>真实审计写入后注入故障，验证调用方事务确实回滚审计及结果。</summary>
    private sealed class WriteThenFailAudit(ITransactionalAuditWriter actual) : ITransactionalAuditWriter
    {
        /// <summary>先写同一物理PG事务，再在提交前抛出固定合成故障。</summary>
        public async Task<string> WriteAsync(ActorContext actor, AuditCommand command, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken)
        {
            await actual.WriteAsync(actor, command, connection, transaction, cancellationToken);
            throw new SemanticOperationException(503, "synthetic_audit_unavailable");
        }
    }

    /// <summary>只供事务边界测试的固定材料，不声称是真实MappingRelease。</summary>
    internal static G4QueryBinding Binding(long epoch) => new()
    {
        MappingId = "mapping-root", MappingReleaseId = "mapping-1", ManifestHash = new string('b',64),
        OriginalCatalogSnapshotId = "catalog-original", OriginalCatalogFingerprint = new string('c',64),
        ActivationId = "activation-1", ActivationRevision = "1", CurrentCatalogSnapshotId = "catalog-current", CurrentCatalogFingerprint = new string('c',64),
        ConnectionId = "connection-1", ConnectionRevision = "1", ConfigHash = new string('d',64), SecretVersion = "1",
        OntologyReleaseId = "ontology-1", AuthorizationEpoch = epoch.ToString(CultureInfo.InvariantCulture), CapabilityVersion = new string('a',64)
    };

    /// <summary>保留期测试的确定性服务器时钟，不修改宿主或数据库全局时间。</summary>
    private sealed class FixedTime : TimeProvider
    {
        /// <summary>该测试步骤唯一观察时刻。</summary>
        private readonly DateTimeOffset now;

        /// <summary>调用方明确给出要验证的期限之后时刻。</summary>
        public FixedTime(DateTimeOffset now) => this.now = now;

        /// <summary>只替换维护时钟，不创建或延长任何会话。</summary>
        public override DateTimeOffset GetUtcNow() => now;
    }

    /// <summary>唯一测试替身仅隔离Connections材料，授权与审计始终执行真实实现。</summary>
    private sealed class FixedBindingReader : IG4QueryBindingReader
    {
        /// <summary>模拟Active已经变化，只有新执行应触发此检查。</summary>
        public bool RejectNewExecution { get; set; }

        /// <summary>只计数历史连接参与者确已被调用，不替代真实PG源权限证明。</summary>
        public int HistoricalChecks { get; private set; }

        /// <summary>只验证使用同一物理短事务；完整Connections路径由真实S1验收覆盖。</summary>
        public Task VerifyHistoricalAccessInTransactionAsync(ActorContext actor, G4QueryConnectionAccess access, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken)
        {
            Assert.AreSame(connection, transaction.Connection);
            cancellationToken.ThrowIfCancellationRequested();
            HistoricalChecks++;
            return Task.CompletedTask;
        }

        /// <summary>该测试不允许捕获映射，防止误称为完整源路径。</summary>
        public Task<G4QueryBindingContext> CaptureAsync(ActorContext actor, G4SemanticQuery query, long authorizationEpoch, CancellationToken cancellationToken) =>
            throw new NotSupportedException("此测试只覆盖持久事务。");

        /// <summary>只接受真实同连接平台事务，不读取或修改Connections表。</summary>
        public Task VerifyInTransactionAsync(ActorContext actor, G4SemanticQuery query, G4QueryBinding expected, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken)
        {
            Assert.AreSame(connection, transaction.Connection);
            cancellationToken.ThrowIfCancellationRequested();
            if (RejectNewExecution) throw new SemanticOperationException(409, "query_binding_stale");
            return Task.CompletedTask;
        }
    }
}
