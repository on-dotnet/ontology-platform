using System.Net;
using System.Net.Http.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using Npgsql;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Governance;

namespace OntologyPlatform.SecurityTests;

/// <summary>在本轮临时PG中验证真实物理事务、完整范围与持久拒绝审计。</summary>
[TestClass]
public sealed class G2AuditTransactionTests
{
    /// <summary>外层提交同时保存独立业务探针与治理审计；审计返回前对其他连接不可见。</summary>
    /// <returns>双上下文同事务提交验证任务。</returns>
    [TestMethod]
    public async Task SharedPhysicalTransactionCommitsBothAndPreservesMultisite()
    {
        // 每个测试仅访问本轮临时PG中新建的随机独立数据库。
        await using var fixture = await G2PgFixture.CreateAsync();
        // 业务探针只写本测试schema，模拟模块独占DbContext。
        await using var business = fixture.CreateProbe();
        // 外层事务明确控制业务与审计的共同提交或回滚。
        await using var transaction = await business.Database.BeginTransactionAsync();
        business.Probes.Add(new G2Probe { Id = "commit" });
        await business.SaveChangesAsync();
        // 写入器显式加入探针上下文同一个物理连接及原始DbTransaction。
        var id = await fixture.Writer.WriteAsync(G2PgFixture.Actor(), G2PgFixture.Command(), business.Database.GetDbConnection(), transaction.GetDbTransaction(), CancellationToken.None);
        Assert.AreEqual(0, await fixture.AuditCountAsync());
        Assert.AreEqual(0, await fixture.ProbeCountAsync());
        await transaction.CommitAsync();
        Assert.AreEqual(1, await fixture.ProbeCountAsync());
        // 使用新连接读取已提交事实，防止ChangeTracker造成假成功。
        await using var reader = fixture.CreateDbContext();
        // 新连接读取真实已提交审计，避免跟踪缓存掩盖持久化错误。
        var record = await reader.AuditRecords.AsNoTracking().SingleAsync(row => row.Id == id);
        CollectionAssert.AreEqual(new[] { "site-a", "site-b" }, record.ScopeSiteIds);
        Assert.IsNull(record.SiteId);
        Assert.AreEqual("org-demo", record.OrganizationId);
        Assert.AreEqual("fixture-subject", record.Actor);
    }

    /// <summary>调用方主动回滚时业务与审计必须共同消失。</summary>
    /// <returns>双上下文同事务回滚验证任务。</returns>
    [TestMethod]
    public async Task SharedPhysicalTransactionRollsBackBoth()
    {
        // 独立随机数据库避免受并发测试或历史审计影响。
        await using var fixture = await G2PgFixture.CreateAsync();
        // 独立业务上下文仅拥有本测试探针表。
        await using var business = fixture.CreateProbe();
        // 外层事务明确控制业务与审计的共同提交或回滚。
        await using var transaction = await business.Database.BeginTransactionAsync();
        business.Probes.Add(new G2Probe { Id = "rollback" });
        await business.SaveChangesAsync();
        await fixture.Writer.WriteAsync(G2PgFixture.Actor(), G2PgFixture.Command(), business.Database.GetDbConnection(), transaction.GetDbTransaction(), CancellationToken.None);
        await transaction.RollbackAsync();
        Assert.AreEqual(0, await fixture.AuditCountAsync());
        Assert.AreEqual(0, await fixture.ProbeCountAsync());
    }

    /// <summary>真实PG审计写失败后，即使业务方捕获异常也不能提交业务探针。</summary>
    /// <returns>故障注入与整个事务失败关闭验证任务。</returns>
    [TestMethod]
    public async Task AuditDatabaseFailureInvalidatesWholeBusinessTransaction()
    {
        // 故障触发器仅存在于本测试新建数据库，绝不修改开发栈。
        await using var fixture = await G2PgFixture.CreateAsync();
        // 故障注入上下文仅操作本次随机数据库。
        await using (var setup = fixture.CreateDbContext())
        {
            await setup.Database.ExecuteSqlRawAsync("""
                CREATE FUNCTION g2_probe.reject_audit() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN RAISE EXCEPTION 'synthetic audit rejection'; END $$;
                CREATE TRIGGER reject_audit BEFORE INSERT ON governance.audit_records
                FOR EACH ROW EXECUTE FUNCTION g2_probe.reject_audit();
                """);
        }
        // 独立业务上下文仅拥有本测试探针表。
        await using var business = fixture.CreateProbe();
        // 外层事务明确控制业务与审计的共同提交或回滚。
        await using var transaction = await business.Database.BeginTransactionAsync();
        business.Probes.Add(new G2Probe { Id = "audit-failure" });
        await business.SaveChangesAsync();
        await Assert.ThrowsExactlyAsync<DbUpdateException>(() => fixture.Writer.WriteAsync(G2PgFixture.Actor(), G2PgFixture.Command(), business.Database.GetDbConnection(), transaction.GetDbTransaction(), CancellationToken.None));
        // 驱动已完成整笔回滚，不能依靠业务调用者自觉再回滚才保证原子性。
        await Assert.ThrowsExactlyAsync<InvalidOperationException>(() => transaction.CommitAsync());
        Assert.AreEqual(0, await fixture.AuditCountAsync());
        Assert.AreEqual(0, await fixture.ProbeCountAsync());
    }

    /// <summary>相同连接串的另一物理连接不能冒充共享事务。</summary>
    /// <returns>物理连接身份边界验证任务。</returns>
    [TestMethod]
    public async Task MatchingConnectionStringDoesNotCountAsSharedTransaction()
    {
        // 两个上下文来自同一配置但实际拥有不同连接。
        await using var fixture = await G2PgFixture.CreateAsync();
        // 第一物理连接提供真实外层事务。
        await using var first = fixture.CreateProbe();
        // 第二物理连接用于拒绝仅连接串相同的错误接入。
        await using var second = fixture.CreateProbe();
        // 外层事务明确控制业务与审计的共同提交或回滚。
        await using var transaction = await first.Database.BeginTransactionAsync();
        await second.Database.OpenConnectionAsync();
        await Assert.ThrowsExactlyAsync<InvalidOperationException>(() => fixture.Writer.WriteAsync(G2PgFixture.Actor(), G2PgFixture.Command(), second.Database.GetDbConnection(), transaction.GetDbTransaction(), CancellationToken.None));
        // writer已使外层事务整体失效，测试不能主动回滚替其掩盖前置失败。
        await Assert.ThrowsExactlyAsync<InvalidOperationException>(() => transaction.CommitAsync());
        Assert.AreEqual(0, await fixture.AuditCountAsync());
    }

    /// <summary>连接前置条件失败后调用方捕获异常也不能提交已经写入的业务。</summary>
    /// <param name="openForeignConnection">是否打开另一物理连接；否则覆盖连接未打开的前置失败。</param>
    /// <returns>真实业务写入、连接拒绝与整笔回滚的验证任务。</returns>
    [TestMethod]
    [DataRow(true)]
    [DataRow(false)]
    public async Task InvalidConnectionPreconditionInvalidatesExistingBusinessTransaction(bool openForeignConnection)
    {
        // 全部写入限定于本次临时PG的新建随机数据库。
        await using var fixture = await G2PgFixture.CreateAsync();
        // 原连接与事务拥有真实业务探针，不是空事务测试。
        await using var business = fixture.CreateProbe();
        // 另一上下文只有相同连接串，没有共享原事务的物理连接。
        await using var foreign = fixture.CreateProbe();
        // 此事务已经写入业务，因此审计的任何前置失败都必须使其不可提交。
        await using var transaction = await business.Database.BeginTransactionAsync();
        business.Probes.Add(new G2Probe { Id = "invalid-connection-precondition" });
        await business.SaveChangesAsync();
        if (openForeignConnection)
        {
            await foreign.Database.OpenConnectionAsync();
        }
        await Assert.ThrowsExactlyAsync<InvalidOperationException>(() => fixture.Writer.WriteAsync(
            G2PgFixture.Actor(), G2PgFixture.Command(), foreign.Database.GetDbConnection(), transaction.GetDbTransaction(), CancellationToken.None));
        // 不主动回滚替writer掩盖缺陷；尝试提交必须失败，两表在独立连接中均为空。
        await Assert.ThrowsExactlyAsync<InvalidOperationException>(() => transaction.CommitAsync());
        Assert.AreEqual(0, await fixture.ProbeCountAsync());
        Assert.AreEqual(0, await fixture.AuditCountAsync());
    }

    /// <summary>独立审计在返回ID前持久提交，并保真单厂与明确空范围。</summary>
    /// <returns>独立提交及范围边界验证任务。</returns>
    [TestMethod]
    public async Task StandaloneAuditCommitsBeforeReturningAndKeepsScopeSemantics()
    {
        // 三种范围使用同一正式审计模型，不把空集合写成未知null。
        await using var fixture = await G2PgFixture.CreateAsync();
        // 逐个验证明确空集合、单厂和多厂三种范围语义。
        foreach (var sites in new[] { Array.Empty<string>(), new[] { "site-a" }, new[] { "site-a", "site-b" } })
        {
            // 仅当前命令范围变化；可信身份仍保留两个厂的全部权限。
            var command = G2PgFixture.Command() with { Scope = new ResourceScope { OrganizationId = "org-demo", SiteIds = sites } };
            // 只有正式写入器完成保存或提交之后才取得审计标识。
            var id = await fixture.Writer.WriteAsync(G2PgFixture.Actor(), command, CancellationToken.None);
            // 独立读取上下文用于观察已经提交的数据库事实。
            await using var reader = fixture.CreateDbContext();
            // 新连接读取真实已提交审计，避免跟踪缓存掩盖持久化错误。
            var record = await reader.AuditRecords.AsNoTracking().SingleAsync(row => row.Id == id);
            CollectionAssert.AreEqual(sites, record.ScopeSiteIds);
            Assert.AreEqual(sites.Length == 1 ? sites[0] : null, record.SiteId);
        }
        Assert.AreEqual(3, await fixture.AuditCountAsync());
    }

    /// <summary>真实HTTP角色拒绝在返回403前提交治理审计，完整双厂范围不丢失。</summary>
    /// <returns>Kestrel到真实治理PG的拒绝验证任务。</returns>
    [TestMethod]
    public async Task HttpAuthorizationDenialPersistsAuditBefore403()
    {
        // 将正式writer注册到只存在于测试程序集的固定身份宿主。
        await using var fixture = await G2PgFixture.CreateAsync();
        // 真实Kestrel宿主绑定本次随机库的正式审计写入器。
        await using var host = await G2HttpFixture.StartAsync("platform.viewer", audit: fixture.Writer);
        // 真实HTTP响应仅用于状态和公开错误边界断言。
        using var response = await host.Client.PostAsJsonAsync("/write", G2HttpFixture.Command());
        Assert.AreEqual(HttpStatusCode.Forbidden, response.StatusCode);
        Assert.AreEqual(0, host.BusinessCalls);
        // 独立读取上下文用于观察已经提交的数据库事实。
        await using var reader = fixture.CreateDbContext();
        // 新连接读取真实已提交审计，避免跟踪缓存掩盖持久化错误。
        var record = await reader.AuditRecords.AsNoTracking().SingleAsync();
        Assert.AreEqual("authorization.denied", record.Action);
        Assert.AreEqual("denied", record.Outcome);
        CollectionAssert.AreEqual(new[] { "site-a", "site-b" }, record.ScopeSiteIds);
        Assert.IsNull(record.SiteId);
    }
}

/// <summary>仅消费显式临时PG配置并拥有单个随机测试数据库的上下文工厂。</summary>
internal sealed class G2PgFixture : IDbContextFactory<GovernanceDbContext>, IAsyncDisposable
{
    /// <summary>本测试创建的随机数据库名，不由外部输入控制。</summary>
    private readonly string databaseName = "g2_sec_" + Guid.NewGuid().ToString("N");

    /// <summary>只用于创建与删除本测试库的临时PG控制连接。</summary>
    private NpgsqlConnection control = null!;

    /// <summary>本测试随机数据库的连接配置，永不输出。</summary>
    private string connection = string.Empty;

    /// <summary>生产治理事务审计写入器。</summary>
    public TransactionalAuditWriter Writer => new(this);

    /// <summary>创建随机数据库，执行真实治理迁移并建立测试专属业务探针schema。</summary>
    /// <returns>可供本测试使用且负责清理的fixture。</returns>
    public static async Task<G2PgFixture> CreateAsync()
    {
        // 缺配置不连接任何默认开发数据库，更不把无测试视为通过。
        var supplied = Environment.GetEnvironmentVariable("G1_SEC_PG_CONNECTION");
        if (string.IsNullOrWhiteSpace(supplied))
        {
            Assert.Inconclusive("NOT_RUN: 未注入本轮临时PG配置。");
        }
        // 所有写操作限于此新建随机库，临时连接值只留在内存。
        var fixture = new G2PgFixture { control = new NpgsqlConnection(supplied) };
        await fixture.control.OpenAsync();
        // 数据库名完全由UUID生成，创建仅限本次测试的新库。
        await using (var create = new NpgsqlCommand("CREATE DATABASE \"" + fixture.databaseName + "\"", fixture.control))
        {
            await create.ExecuteNonQueryAsync();
        }
        fixture.connection = new NpgsqlConnectionStringBuilder(supplied) { Database = fixture.databaseName, Pooling = false }.ConnectionString;
        try
        {
            // 治理上下文执行正式迁移，不以EnsureCreated替代迁移链。
            await using var governance = fixture.CreateDbContext();
            await governance.Database.MigrateAsync();
            await governance.Database.ExecuteSqlRawAsync("CREATE SCHEMA g2_probe; CREATE TABLE g2_probe.business_probe (\"Id\" text PRIMARY KEY)");
            return fixture;
        }
        catch
        {
            await fixture.DisposeAsync();
            throw;
        }
    }

    /// <summary>创建仅拥有治理表的真实上下文。</summary>
    /// <returns>全新未打开连接的治理上下文。</returns>
    public GovernanceDbContext CreateDbContext()
    {
        return new GovernanceDbContext(new DbContextOptionsBuilder<GovernanceDbContext>()
            .UseNpgsql(connection, postgres => postgres.MigrationsHistoryTable("__EFMigrationsHistory", "governance")).Options);
    }

    /// <summary>创建只能写测试专属schema的业务探针上下文。</summary>
    /// <returns>全新业务探针上下文。</returns>
    public G2ProbeContext CreateProbe() => new(new DbContextOptionsBuilder<G2ProbeContext>().UseNpgsql(connection).Options);

    /// <summary>用独立连接观察已提交审计总数。</summary>
    /// <returns>数据库实际持久行数。</returns>
    public async Task<int> AuditCountAsync()
    {
        // 新上下文避免跟踪缓存与当前未提交事务污染观察。
        await using var reader = CreateDbContext();
        return await reader.AuditRecords.CountAsync();
    }

    /// <summary>用独立连接观察已提交业务探针总数。</summary>
    /// <returns>数据库实际持久行数。</returns>
    public async Task<int> ProbeCountAsync()
    {
        // 只读取本测试schema，不查其他模块表。
        await using var reader = CreateProbe();
        return await reader.Probes.CountAsync();
    }

    /// <summary>提供固定可信双厂身份，不读取用户凭证。</summary>
    /// <returns>合成服务器主体。</returns>
    public static ActorContext Actor() => new()
    {
        SubjectId = "fixture-subject",
        OrganizationId = "org-demo",
        SiteIds = ["site-a", "site-b"],
        Roles = ["platform.operator"],
        TraceId = "fixture-trace",
        CorrelationId = "fixture-correlation"
    };

    /// <summary>提供批准的固定事件及完整双厂范围。</summary>
    /// <returns>合成合法审计命令。</returns>
    public static AuditCommand Command() => new()
    {
        Action = "ontology.create",
        Resource = "fixture-draft",
        Outcome = "allowed",
        Scope = new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a", "site-b"] }
    };

    /// <summary>只删除本测试随机库并释放控制连接，不碰共享开发卷。</summary>
    /// <returns>清理完成任务。</returns>
    public async ValueTask DisposeAsync()
    {
        // 删除对象仅为本测试创建的随机库，不影响开发数据。
        await using var drop = new NpgsqlCommand("DROP DATABASE \"" + databaseName + "\" WITH (FORCE)", control);
        await drop.ExecuteNonQueryAsync();
        await control.DisposeAsync();
    }
}

/// <summary>完全隔离于产品模块的事务业务探针。</summary>
internal sealed class G2Probe
{
    /// <summary>测试生成的唯一探针标识。</summary>
    public string Id { get; set; } = string.Empty;
}

/// <summary>仅拥有测试专属业务探针schema的EF上下文。</summary>
internal sealed class G2ProbeContext : DbContext
{
    /// <summary>以临时数据库选项创建隔离探针上下文。</summary>
    /// <param name="options">测试临时PG选项。</param>
    public G2ProbeContext(DbContextOptions<G2ProbeContext> options) : base(options)
    {
    }

    /// <summary>只属于当前测试的业务探针行。</summary>
    public DbSet<G2Probe> Probes => Set<G2Probe>();

    /// <summary>把测试探针限制在临时schema，不映射任何产品模块表。</summary>
    /// <param name="modelBuilder">探针模型构建器。</param>
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.Entity<G2Probe>().ToTable("business_probe", "g2_probe").HasKey(value => value.Id);
    }
}
