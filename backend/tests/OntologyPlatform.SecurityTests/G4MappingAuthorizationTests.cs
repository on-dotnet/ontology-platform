using System.Security.Claims;
using System.Text;
using System.Security.Cryptography;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.EntityFrameworkCore.Storage;
using OntologyPlatform.Api.G4;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Modules.Connections;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;

namespace OntologyPlatform.SecurityTests;

/// <summary>完整范围与显式源许可边界；数据库竞态由任务实测补充。</summary>
[TestClass]
public sealed class G4MappingAuthorizationTests
{
    /// <summary>多厂授权可覆盖单厂，单厂授权不能拼接成多厂。</summary>
    [TestMethod]
    public void OneGrantMustCoverTheEntireScope()
    {
        // 固定时钟让过期判断确定且不依赖测试机器日期。
        var now = DateTimeOffset.Parse("2026-11-14T00:00:00Z");
        // 每个请求必须保留资源完整厂区。
        var proof = Proof(["A", "B"]);
        // 同一条授权完整覆盖才可成功。
        var grant = Grant(["A", "B"], now.AddMinutes(1));
        Assert.IsTrue(MappingAuthorizationParticipant.Covers(grant, proof, now));
        Assert.IsTrue(MappingAuthorizationParticipant.Covers(grant, proof with { Scope = proof.Scope with { SiteIds = ["A"] } }, now));
        grant.SiteIds = ["A"];
        Assert.IsFalse(MappingAuthorizationParticipant.Covers(grant, proof, now));
        grant.SiteIds = ["B"];
        Assert.IsFalse(MappingAuthorizationParticipant.Covers(grant, proof, now));
        grant.SiteIds = ["A", "B"];
        grant.RevokedAtUtc = now;
        Assert.IsFalse(MappingAuthorizationParticipant.Covers(grant, proof, now));
        grant.RevokedAtUtc = null;
        Assert.IsFalse(MappingAuthorizationParticipant.Covers(grant, proof, now.AddMinutes(1)));
    }

    /// <summary>源许可必须精确覆盖连接、表和字段，管理连接不代表业务数据读取。</summary>
    [TestMethod]
    public void SourceGrantCannotOmitFieldsOrUseAnotherConnection()
    {
        // 当前时刻仅用于租约判断。
        var now = DateTimeOffset.UtcNow;
        // 请求中的所有字段都必须落于同一grant。
        var proof = Proof(["A"]) with { Permission = "mapping.source.validate", ConnectionId = "source", ObjectRefs = ["table"], FieldRefs = ["table.id", "table.unit"] };
        // 普通许可不能替代源权限。
        var grant = Grant(["A"], now.AddMinutes(1));
        Assert.IsFalse(MappingAuthorizationParticipant.Covers(grant, proof, now));
        grant.Permission = proof.Permission;
        grant.ConnectionId = proof.ConnectionId;
        grant.ObjectRefs = proof.ObjectRefs;
        grant.FieldRefs = ["table.id"];
        Assert.IsFalse(MappingAuthorizationParticipant.Covers(grant, proof, now));
        grant.FieldRefs = proof.FieldRefs;
        Assert.IsTrue(MappingAuthorizationParticipant.Covers(grant, proof, now));
        grant.ConnectionId = "other";
        Assert.IsFalse(MappingAuthorizationParticipant.Covers(grant, proof, now));
    }

    /// <summary>默认查看者不能执行新操作，审核与激活角色不混淆。</summary>
    [TestMethod]
    public void RolesAndPermissionsRemainSeparate()
    {
        // 测试角色资格不伪造真实已授予权限。
        var actor = Proof(["A"]).Actor;
        Assert.IsFalse(MappingAuthorizationParticipant.RoleAllows(actor with { Roles = ["platform.viewer"] }, "mapping.activate"));
        Assert.IsFalse(MappingAuthorizationParticipant.RoleAllows(actor, "mapping.approve"));
        Assert.IsTrue(MappingAuthorizationParticipant.RoleAllows(actor, "mapping.activate"));
        Assert.IsTrue(MappingAuthorizationParticipant.RoleAllows(actor with { Roles = ["platform.auditor"] }, "mapping.approve"));
        Assert.IsFalse(MappingAuthorizationParticipant.RoleAllows(actor, "mapping.unregistered"));
    }

    /// <summary>真实PG迁移、原字节不可变、同物理审计回滚及撤权后旧证明拒绝。</summary>
    [TestMethod]
    public async Task RealPostgresEnforcesImmutableHistoryAndCurrentAuthority()
    {
        // 只有本任务执行器注入新隔离数据库，不借历史KEEP运行资源。
        var connection = Environment.GetEnvironmentVariable("MAPPING_TEST_PG");
        if (string.IsNullOrWhiteSpace(connection))
        {
            Assert.Inconclusive("本测试需要本任务隔离PostgreSQL；缺环境不算PASS。");
        }
        // 独立真实PG会话模拟多个实例，主体限一及连接限二必须同时成立。
        var capacityOrganization = "capacity-" + Guid.NewGuid().ToString("N");
        await using (var first = await MappingValidationService.AcquireCapacityAsync(connection, capacityOrganization, "first", "source", CancellationToken.None))
        {
            // 同主体改用其他连接也不能绕过主体槽位。
            var sameSubject = await Assert.ThrowsAsync<SemanticOperationException>(() => MappingValidationService.AcquireCapacityAsync(connection,
                capacityOrganization, "first", "other-source", CancellationToken.None));
            Assert.AreEqual(429, sameSubject.Status);
            await using (var second = await MappingValidationService.AcquireCapacityAsync(connection, capacityOrganization, "second", "source", CancellationToken.None))
            {
                // 第三个不同主体仍受同连接的两个槽位限制。
                var excess = await Assert.ThrowsAsync<SemanticOperationException>(() => MappingValidationService.AcquireCapacityAsync(connection,
                    capacityOrganization, "third", "source", CancellationToken.None));
                Assert.AreEqual(429, excess.Status);
            }
            // 释放后的空位立即可用，失败路径没有遗留主体锁。
            await using var replacement = await MappingValidationService.AcquireCapacityAsync(connection, capacityOrganization, "third", "source", CancellationToken.None);
        }
        // 主体会话关闭后完全释放，不靠进程内计数或固定等待。
        await using (var reopened = await MappingValidationService.AcquireCapacityAsync(connection, capacityOrganization, "first", "source", CancellationToken.None))
        {
            Assert.IsNotNull(reopened);
        }
        // 每模块只迁移自己的schema和历史表。
        var governanceOptions = new DbContextOptionsBuilder<GovernanceDbContext>().UseNpgsql(connection,
            options => options.MigrationsHistoryTable("__EFMigrationsHistory", "governance")).Options;
        // Connections使用独立上下文但共享同一平台数据库。
        var connectionsOptions = new DbContextOptionsBuilder<ConnectionsDbContext>().UseNpgsql(connection,
            options => options.MigrationsHistoryTable("__EFMigrationsHistory", "connections")).Options;
        // 治理上下文负责实际授权、票据和审计事实。
        await using var governance = new GovernanceDbContext(governanceOptions);
        // 连接上下文负责实际映射历史及激活通知事实。
        await using var database = new ConnectionsDbContext(connectionsOptions);
        await governance.Database.MigrateAsync();
        await database.Database.MigrateAsync();
        // 必须真实往返PG，防止百纳秒时刻在提案散列后才被数据库静默截断。
        await using (var timestampConnection = new Npgsql.NpgsqlConnection(connection))
        {
            await timestampConnection.OpenAsync();
            // 固定尾数含非零第七位，确保回归覆盖原失败而非恰好整微秒。
            var precise = DateTimeOffset.Parse("2026-11-14T04:12:23.1234567Z");
            // 先规范化再用于关系列和受审散列。
            var stored = MappingApplicationService.DatabaseTime(precise);
            // 参数化往返查询核验数据库实际时间精度。
            await using var query = new Npgsql.NpgsqlCommand("SELECT @stamp::timestamptz", timestampConnection);
            query.Parameters.AddWithValue("stamp", stored);
            Assert.AreEqual(stored.UtcDateTime, await query.ExecuteScalarAsync());
            Assert.AreEqual(7L, precise.UtcTicks - stored.UtcTicks);
        }
        // 每次测试使用新scope，保留过去运行证据而非截断历史表。
        var suffix = Guid.NewGuid().ToString("N");
        // 真实主体使用随机合成组织隔离本次验证。
        var actor = Proof(["A"]).Actor with { OrganizationId = "org-" + suffix };
        // 真实DataProtection往返由宿主解析器验证，不以返回true替身替代。
        var protection = new EphemeralDataProtectionProvider();
        // 与生产Cookie相同的认证主体声明类型。
        var principal = new ClaimsPrincipal(new ClaimsIdentity(new[]
        {
            new Claim("sub", actor.SubjectId), new Claim("organization_id", actor.OrganizationId),
            new Claim("site_ids", "A"), new Claim("site_ids", "B"), new Claim(ClaimTypes.Role, "platform.operator")
        }, "Cookies"));
        // 使用生产同样的非池化DbContextFactory；参加外部连接的上下文不能放回上下文池。
        await using var services = new ServiceCollection().AddDbContextFactory<GovernanceDbContext>(options =>
            options.UseNpgsql(connection, postgres => postgres.MigrationsHistoryTable("__EFMigrationsHistory", "governance"))).BuildServiceProvider();
        // 真实DI工厂为每次事务创建新上下文，Npgsql连接池仍可复用空闲物理连接。
        var factory = services.GetRequiredService<IDbContextFactory<GovernanceDbContext>>();
        // 测试HTTP上下文只提供真实构造的已认证主体，不含外部令牌。
        var accessor = new HttpContextAccessor { HttpContext = new DefaultHttpContext { User = principal } };
        // 建立与注销均调用实际服务器票据存储。
        var tickets = new PostgresTicketStore(factory, protection, accessor, TimeProvider.System);
        // Ticket经过实际加密并写入PG。
        var sessionId = await tickets.StoreAsync(new AuthenticationTicket(principal,
            new AuthenticationProperties { ExpiresUtc = DateTimeOffset.UtcNow.AddMinutes(15) }, "Cookies"));
        // 单条AB授权覆盖资源A，撤销必须影响此资源。
        var grant = Grant(["A", "B"], DateTimeOffset.UtcNow.AddMinutes(15));
        grant.Id = "grant-" + suffix;
        grant.OrganizationId = actor.OrganizationId;
        governance.MappingAuthorizationGrants.Add(grant);
        await governance.SaveChangesAsync();
        // 参与者读取真实加密会话及触发器递增的组织版本。
        var authority = new MappingAuthorizationParticipant(factory, new MappingSessionAuthority(protection), TimeProvider.System);
        // 捕获输入不把客户端版本作为当前权限依据。
        var proof = await authority.CaptureAsync(Proof(["A"]) with
        {
            Actor = actor,
            SessionReference = sessionId,
            Scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = ["A"] }
        }, CancellationToken.None);
        Assert.IsTrue(proof.AuthorizationEpoch >= 2);
        // 为正式制品建立永久映射根，所有历史引用指向同一根。
        var mapping = new MappingRecord { Id = "mapping-" + suffix, OrganizationId = actor.OrganizationId, SiteIds = ["A"], DisplayName = "不可变测试", DraftId = "draft-" + suffix, SourceConnectionId = "synthetic", CurrentRevisionId = "revision-" + suffix, UpdatedAtUtc = DateTimeOffset.UtcNow };
        database.Mappings.Add(mapping);
        await database.SaveChangesAsync();
        // Canonical原字节及独立SHA都由生产实现产生。
        var bytes = MappingCanonical.Serialize(new { mappingId = mapping.Id });
        // 此处测试存储约束，不把合成小对象声称为业务Manifest。
        var release = new MappingReleaseRecord { Id = "release-" + suffix, MappingId = mapping.Id, OrganizationId = actor.OrganizationId, SiteIds = ["A"], CanonicalBytes = bytes, ContentHash = Convert.ToHexStringLower(SHA256.HashData(bytes)), CreatedAtUtc = DateTimeOffset.UtcNow };
        database.MappingReleases.Add(release);
        await database.SaveChangesAsync();
        await Assert.ThrowsAsync<Npgsql.PostgresException>(() => database.Database.ExecuteSqlInterpolatedAsync(
            $"UPDATE connections.\"MappingReleases\" SET \"ContentHash\" = {new string('0', 64)} WHERE \"Id\" = {release.Id}"));
        await Assert.ThrowsAsync<Npgsql.PostgresException>(() => database.Database.ExecuteSqlInterpolatedAsync(
            $"DELETE FROM connections.\"MappingReleases\" WHERE \"Id\" = {release.Id}"));
        Assert.AreEqual(release.ContentHash, (await database.MappingReleases.AsNoTracking().SingleAsync(row => row.Id == release.Id)).ContentHash);
        // 当前模型的幂等唯一域不包含主体，异主体相同key不能插入第二次成功。
        var command = new MappingCommandRecord
        {
            Id = "command-" + suffix,
            MappingId = mapping.Id,
            OrganizationId = actor.OrganizationId,
            SiteIds = ["A"],
            SubjectId = "actor-a",
            Operation = "test",
            CommandId = "command-id-" + suffix,
            IdempotencyKey = "same-key",
            PayloadHash = new string('a', 64),
            ResponseBytes = bytes,
            CreatedAtUtc = DateTimeOffset.UtcNow
        };
        database.MappingCommands.Add(command);
        await database.SaveChangesAsync();
        // 使用另一个上下文验证数据库唯一约束，不让失败追踪污染后续测试。
        await using (var duplicate = new ConnectionsDbContext(connectionsOptions))
        {
            duplicate.MappingCommands.Add(new MappingCommandRecord
            {
                Id = "other-" + suffix,
                MappingId = mapping.Id,
                OrganizationId = actor.OrganizationId,
                SiteIds = ["A"],
                SubjectId = "actor-b",
                Operation = "test",
                CommandId = "other-id-" + suffix,
                IdempotencyKey = "same-key",
                PayloadHash = new string('b', 64),
                ResponseBytes = bytes,
                CreatedAtUtc = DateTimeOffset.UtcNow
            });
            await Assert.ThrowsAsync<DbUpdateException>(() => duplicate.SaveChangesAsync());
        }
        // 两条真实持久激活及通知用于验证重复/乱序消费，不冒充完整业务激活验收。
        var eventIds = new[] { "event-first-" + suffix, "event-second-" + suffix };
        for (var index = 0; index < eventIds.Length; index++)
        {
            // 收据绑定实际outbox身份、对应manifestHash与单调版本。
            var receipt = new MappingActivationReceipt
            {
                ActivationId = "activation-" + index + "-" + suffix,
                MappingId = mapping.Id,
                ProposalId = "proposal-" + index + "-" + suffix,
                Kind = "PUBLISH",
                MappingReleaseId = release.Id,
                ManifestHash = release.ContentHash,
                PreviousReleaseId = index == 0 ? null : release.Id,
                ActivationRevision = index + 1,
                AuditId = "audit-" + suffix,
                OutboxEventId = eventIds[index],
                ActivatedAtUtc = DateTimeOffset.UtcNow
            };
            // canonical原字节仍受真实数据库触发器与SHA约束。
            var receiptBytes = MappingCanonical.Serialize(receipt);
            database.MappingActivations.Add(new MappingActivationRecord
            {
                Id = receipt.ActivationId,
                MappingId = mapping.Id,
                OrganizationId = actor.OrganizationId,
                SiteIds = ["A"],
                CanonicalBytes = receiptBytes,
                ContentHash = Convert.ToHexStringLower(SHA256.HashData(receiptBytes)),
                CreatedAtUtc = receipt.ActivatedAtUtc,
                ProposalId = receipt.ProposalId,
                ReleaseId = release.Id,
                CheckId = "check-" + suffix,
                BindingJson = "{}",
                ActivationRevision = index + 1
            });
            database.MappingOutboxs.Add(new MappingOutboxRecord
            {
                Id = eventIds[index],
                MappingId = mapping.Id,
                OrganizationId = actor.OrganizationId,
                SiteIds = ["A"],
                CreatedAtUtc = receipt.ActivatedAtUtc,
                ReleaseId = release.Id,
                ManifestHash = release.ContentHash,
                ActivationRevision = index + 1
            });
        }
        await database.SaveChangesAsync();
        // 生产同样的非池化Connections工厂，测试不伪造consumer实现。
        await using var consumers = new ServiceCollection().AddDbContextFactory<ConnectionsDbContext>(options => options.UseNpgsql(connection,
            postgres => postgres.MigrationsHistoryTable("__EFMigrationsHistory", "connections"))).BuildServiceProvider();
        // 实际消费者先处理第二条，再处理第一条，最后重复第二条。
        var dispatcher = new MappingOutboxDispatcher(consumers.GetRequiredService<IDbContextFactory<ConnectionsDbContext>>(), TimeProvider.System,
            Microsoft.Extensions.Logging.Abstractions.NullLogger<MappingOutboxDispatcher>.Instance);
        await dispatcher.DispatchAsync(eventIds[1], CancellationToken.None);
        await dispatcher.DispatchAsync(eventIds[0], CancellationToken.None);
        await dispatcher.DispatchAsync(eventIds[1], CancellationToken.None);
        Assert.AreEqual(2, await database.MappingOutboxReceipts.CountAsync(row => row.MappingId == mapping.Id));
        Assert.AreEqual(2L, (await database.MappingNotifications.AsNoTracking().SingleAsync(row => row.MappingId == mapping.Id)).ActivationRevision);
        Assert.AreEqual(eventIds[1], (await database.MappingNotifications.AsNoTracking().SingleAsync(row => row.MappingId == mapping.Id)).EventId);
        Assert.AreEqual(2L, (await database.MappingOutboxs.AsNoTracking().SingleAsync(row => row.Id == eventIds[1])).Attempts);
        // 事务中的业务变更及实际Governance审计共同回滚。
        string auditId;
        await using (var transaction = await database.Database.BeginTransactionAsync())
        {
            await authority.DemandInTransactionAsync(proof, database.Database.GetDbConnection(), transaction.GetDbTransaction(), CancellationToken.None);
            await database.Mappings.Where(row => row.Id == mapping.Id).ExecuteUpdateAsync(update => update.SetProperty(row => row.Revision, 2));
            auditId = await new TransactionalAuditWriter(factory).WriteAsync(actor,
                new AuditCommand { Action = "mapping.update", Resource = mapping.Id, Outcome = "allowed", Scope = proof.Scope },
                database.Database.GetDbConnection(), transaction.GetDbTransaction(), CancellationToken.None);
            await transaction.RollbackAsync();
        }
        Assert.IsFalse(await governance.AuditRecords.AnyAsync(row => row.Id == auditId));
        Assert.AreEqual(1, (await database.Mappings.AsNoTracking().SingleAsync(row => row.Id == mapping.Id)).Revision);
        // 已获得组织锁的事务先提交：真实注销必须等待同一锁，不能在中途改变会话。
        await using (var transaction = await database.Database.BeginTransactionAsync())
        {
            await authority.DemandInTransactionAsync(proof, database.Database.GetDbConnection(), transaction.GetDbTransaction(), CancellationToken.None);
            // 异步注销使用独立真实PG连接，不用假锁或内存同步替代。
            var revoke = tickets.RemoveAsync(sessionId);
            // 第三条连接观测实际数据库Lock等待，防止以Task调度延迟冒充竞争证明。
            await using var observer = new Npgsql.NpgsqlConnection(connection);
            await observer.OpenAsync();
            // 固定查询只读本测试数据库会话状态，不读取业务行或密码。
            await using var waiting = new Npgsql.NpgsqlCommand("SELECT count(*) FROM pg_stat_activity WHERE datname = current_database() AND wait_event_type = 'Lock' AND query LIKE '%MappingAuthorizationEpochs%'", observer);
            // 只给锁观察一秒，低于生产两秒lock_timeout。
            var observedWait = false;
            // 每次读取真实等待状态，不能靠固定sleep宣称已经发生竞态。
            for (var attempt = 0; attempt < 20; attempt++)
            {
                if (Convert.ToInt64(await waiting.ExecuteScalarAsync()) > 0)
                {
                    observedWait = true;
                    break;
                }
                await Task.Delay(25);
            }
            if (revoke.IsFaulted)
            {
                await revoke;
            }
            Assert.IsTrue(observedWait, "注销必须等待真实组织行锁。");
            Assert.IsFalse(revoke.IsCompleted);
            await transaction.CommitAsync();
            await revoke;
        }
        // 注销先于下一事务提交：旧授权证明必须被当前会话事实拒绝。
        await using (var transaction = await database.Database.BeginTransactionAsync())
        {
            await Assert.ThrowsAsync<SemanticOperationException>(() => authority.DemandInTransactionAsync(proof,
                database.Database.GetDbConnection(), transaction.GetDbTransaction(), CancellationToken.None));
        }
        Assert.IsNull(await tickets.RetrieveAsync(sessionId));
        Assert.IsTrue((await governance.MappingAuthorizationEpochs.AsNoTracking().SingleAsync(row => row.OrganizationId == actor.OrganizationId)).Revision > proof.AuthorizationEpoch);
    }

    /// <summary>只构造内部形状，不冒充真实会话。</summary>
    private static MappingAuthorizationProof Proof(string[] sites) => new()
    {
        Actor = new ActorContext { SubjectId = "alice", OrganizationId = "org", SiteIds = ["A", "B"], Roles = ["platform.operator"], TraceId = "trace", CorrelationId = "correlation" },
        SessionReference = new string('a', 64),
        Scope = new ResourceScope { OrganizationId = "org", SiteIds = sites },
        Permission = "mapping.edit",
        ConnectionId = null,
        ObjectRefs = [],
        FieldRefs = [],
        AuthorizationEpoch = 1,
        ExpiresAtUtc = DateTimeOffset.MaxValue
    };

    /// <summary>授权实例始终属于一个主体及一个完整组织范围。</summary>
    private static MappingAuthorizationGrant Grant(string[] sites, DateTimeOffset expires) => new()
    {
        Id = "grant",
        SubjectId = "alice",
        OrganizationId = "org",
        SiteIds = sites,
        Permission = "mapping.edit",
        ExpiresAtUtc = expires
    };
}
