using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using Npgsql;
using OntologyPlatform.Modules.Governance;

namespace OntologyPlatform.SecurityTests;

/// <summary>在本轮临时PG的独立数据库验证范围迁移、拒绝丢失与恢复。</summary>
[TestClass]
public sealed class AuditScopeMigrationTests
{
    /// <summary>旧审计保持未知；真实数组往返，存在新范围时拒绝破坏性降级。</summary>
    /// <returns>专用数据库创建、迁移、恢复与删除的完整任务。</returns>
    [TestMethod]
    public async Task ScopeMigrationPreservesLegacyAndRefusesDestructiveRollback()
    {
        // 仅接收显式隔离测试配置，不探测开发栈或历史凭证。
        var connection = Environment.GetEnvironmentVariable("G1_SEC_PG_CONNECTION");
        if (string.IsNullOrWhiteSpace(connection))
        {
            Assert.Inconclusive("NOT_RUN: 未注入本轮临时PG配置。");
        }
        // 随机数据库名只由测试生成，可安全作为引用标识符。
        var name = "close_scope_" + Guid.NewGuid().ToString("N");
        // 控制连接仅用于在当前临时PG创建、清理本测试数据库。
        await using var admin = new NpgsqlConnection(connection);
        await admin.OpenAsync();
        // 不通过用户输入构建标识符；UUID命名的数据库不可能覆盖已有库。
        await using (var create = new NpgsqlCommand("CREATE DATABASE \"" + name + "\"", admin))
        {
            await create.ExecuteNonQueryAsync();
        }
        // 保留原连接其他属性，禁池避免清理时存在自身空闲连接。
        var settings = new NpgsqlConnectionStringBuilder(connection) { Database = name, Pooling = false };
        try
        {
            // 迁移历史与生产相同，属于Governance模块，不用EnsureCreated替代。
            var options = new DbContextOptionsBuilder<GovernanceDbContext>()
                .UseNpgsql(settings.ConnectionString, postgres => postgres.MigrationsHistoryTable("__EFMigrationsHistory", "governance")).Options;
            await using var database = new GovernanceDbContext(options);
            // 显式回到旧版schema以证明从真实历史状态升级，而非只建最新表。
            var migrator = database.GetService<IMigrator>();
            await migrator.MigrateAsync("20261025062847_InitialGovernance");
            await database.Database.ExecuteSqlRawAsync("""
                INSERT INTO governance.audit_records
                ("Id", "OccurredAtUtc", "Actor", "Action", "Resource", "Outcome", "TraceId", "CorrelationId", "OrganizationId", "SiteId")
                VALUES ('legacy-scope-check', now(), 'synthetic-migration', 'platform.resource.read', 'platform.resources', 'allowed',
                '1234567890abcdef1234567890abcdef', 'migration-check', 'org-demo', 'site-a');
                """);
            await migrator.MigrateAsync();
            // 原始旧记录必须仍为未知，不能按历史首厂伪造完整范围。
            var legacy = await database.AuditRecords.AsNoTracking().SingleAsync(row => row.Id == "legacy-scope-check");
            Assert.IsNull(legacy.ScopeSiteIds);
            Assert.AreEqual("site-a", legacy.SiteId);
            // 无新范围事实时允许安全降级，旧审计内容仍保留。
            await migrator.MigrateAsync("20261025062847_InitialGovernance");
            await migrator.MigrateAsync();
            Assert.AreEqual(1, await database.AuditRecords.CountAsync());
            // 明确空范围也属于不可丢失事实，不能作为无值列静默删除。
            database.AuditRecords.Add(new AuditRecord
            {
                Id = "empty-scope-check",
                Actor = "synthetic-migration",
                Action = "platform.audit.read",
                Resource = "platform.audit",
                Outcome = "allowed",
                OrganizationId = "org-demo",
                ScopeSiteIds = []
            });
            await database.SaveChangesAsync();
            await Assert.ThrowsExactlyAsync<PostgresException>(() => migrator.MigrateAsync("20261025062847_InitialGovernance"));
            database.ChangeTracker.Clear();
            Assert.AreEqual(0, (await database.AuditRecords.SingleAsync(row => row.Id == "empty-scope-check")).ScopeSiteIds!.Length);
            // 测试清理仅针对本库本行，移除后验证多厂数组同样阻止有损降级。
            await database.AuditRecords.Where(row => row.Id == "empty-scope-check").ExecuteDeleteAsync();
            database.AuditRecords.Add(new AuditRecord
            {
                Id = "multi-scope-check",
                Actor = "synthetic-migration",
                Action = "platform.audit.read",
                Resource = "platform.audit",
                Outcome = "allowed",
                OrganizationId = "org-demo",
                ScopeSiteIds = ["site-a", "site-b"]
            });
            await database.SaveChangesAsync();
            await Assert.ThrowsExactlyAsync<PostgresException>(() => migrator.MigrateAsync("20261025062847_InitialGovernance"));
            database.ChangeTracker.Clear();
            // 被拒绝的Down事务必须保持最新schema和完整数组，前向重入无副作用。
            await migrator.MigrateAsync();
            CollectionAssert.AreEqual(new[] { "site-a", "site-b" },
                (await database.AuditRecords.AsNoTracking().SingleAsync(row => row.Id == "multi-scope-check")).ScopeSiteIds);
            Assert.IsTrue((await database.Database.GetAppliedMigrationsAsync()).Contains("20261025144246_AuditScopeSites"));
            Assert.IsNull((await database.AuditRecords.AsNoTracking().SingleAsync(row => row.Id == "legacy-scope-check")).ScopeSiteIds);
        }
        finally
        {
            // 只删除本测试随机新建库，不停止或清空任何共享开发卷。
            await using var drop = new NpgsqlCommand("DROP DATABASE \"" + name + "\" WITH (FORCE)", admin);
            await drop.ExecuteNonQueryAsync();
        }
    }
}
