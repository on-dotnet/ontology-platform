using System.Diagnostics;
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

    /// <summary>首次范围写入与降级并发时，等待写事务提交后仍必须拒绝删列。</summary>
    /// <returns>确定性锁等待、并发提交及真实迁移的验证任务。</returns>
    [TestMethod]
    public async Task ConcurrentFirstScopeWriteCannotBeLostByRollback()
    {
        // 本测试只操作显式临时PG中的全新随机数据库。
        var connection = Environment.GetEnvironmentVariable("G1_SEC_PG_CONNECTION");
        if (string.IsNullOrWhiteSpace(connection))
        {
            Assert.Inconclusive("NOT_RUN: 未注入本轮临时PG配置。");
        }
        // 数据库标识符完全由UUID生成，不接受用户输入。
        var name = "close_race_" + Guid.NewGuid().ToString("N");
        // 管理连接仅创建及删除本测试库，不查询任何开发数据。
        await using var admin = new NpgsqlConnection(connection);
        await admin.OpenAsync();
        // 建库操作只使用本测试UUID标识符。
        await using (var create = new NpgsqlCommand("CREATE DATABASE \"" + name + "\"", admin))
        {
            await create.ExecuteNonQueryAsync();
        }
        // 禁池确保所有并发连接的生命周期均由本测试控制。
        var settings = new NpgsqlConnectionStringBuilder(connection) { Database = name, Pooling = false };
        try
        {
            // 使用正式EF模型和迁移事务，不以手写DROP代替实际Down。
            var options = new DbContextOptionsBuilder<GovernanceDbContext>()
                .UseNpgsql(settings.ConnectionString, postgres => postgres.MigrationsHistoryTable("__EFMigrationsHistory", "governance")).Options;
            await using var database = new GovernanceDbContext(options);
            await database.Database.MigrateAsync();
            await database.Database.OpenConnectionAsync();
            // 真实迁移连接PID用于等待其阻写锁，避免依赖任意延时制造竞争。
            var migrationPid = ((NpgsqlConnection)database.Database.GetDbConnection()).ProcessID;
            // 观察连接只读取系统锁视图，不读取持有写锁的审计表。
            await using var observer = new NpgsqlConnection(settings.ConnectionString);
            await observer.OpenAsync();
            // 在并发事务开始前解析relation OID，随后锁查询不需要解析目标表。
            await using var relationQuery = new NpgsqlCommand("SELECT 'governance.audit_records'::regclass::oid", observer);
            // PostgreSQL对象标识不含业务数据或秘密。
            var relation = (uint)(await relationQuery.ExecuteScalarAsync())!;
            // 未提交的首条真实范围写入持有RowExclusive表锁。
            await using var writer = new NpgsqlConnection(settings.ConnectionString);
            await writer.OpenAsync();
            await using var transaction = await writer.BeginTransactionAsync();
            // 正式表的首条结构化审计在提交前保持不可见，构成真实竞争输入。
            await using (var insert = new NpgsqlCommand("""
                INSERT INTO governance.audit_records
                ("Id", "OccurredAtUtc", "Actor", "Action", "Resource", "Outcome", "TraceId", "CorrelationId", "OrganizationId", "SiteId", "ScopeSiteIds")
                VALUES ('race-scope-check', now(), 'synthetic-migration', 'platform.audit.read', 'platform.audit', 'allowed',
                '1234567890abcdef1234567890abcdef', 'race-check', 'org-demo', NULL, ARRAY['site-a','site-b']);
                """, writer, transaction))
            {
                await insert.ExecuteNonQueryAsync();
            }
            // 限定异常路径的最长等待，不把超时当作测试成功。
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(20));
            // 正式Down在原实现先做不可见快照检查，再因ALTER等待；修复后应先等锁再检查。
            var downgrade = database.GetService<IMigrator>().MigrateAsync("20261025062847_InitialGovernance", deadline.Token);
            // 精确等待该迁移PID对本表未授予的AccessExclusive，确保竞争窗口已经出现。
            await using var waiting = new NpgsqlCommand("""
                SELECT EXISTS (SELECT 1 FROM pg_locks
                WHERE pid = @pid AND relation = @relation AND mode = 'AccessExclusiveLock' AND NOT granted)
                """, observer);
            waiting.Parameters.AddWithValue("pid", migrationPid);
            waiting.Parameters.AddWithValue("relation", NpgsqlTypes.NpgsqlDbType.Oid, relation);
            // 单调计时只约束轮询上限，顺序由实际数据库锁状态决定。
            var elapsed = Stopwatch.StartNew();
            while (!(bool)(await waiting.ExecuteScalarAsync())!)
            {
                Assert.IsFalse(downgrade.IsCompleted, "Down应等待当前真实写事务。");
                Assert.IsTrue(elapsed.Elapsed < TimeSpan.FromSeconds(10), "未观察到确定的迁移锁等待。");
                await Task.Delay(10);
            }
            await transaction.CommitAsync();
            // 保存实际异常类型供后续断言，不读取或打印驱动原始消息。
            PostgresException? rejection = null;
            try
            {
                await downgrade;
            }
            // 只观察固定拒绝类型和SQLSTATE，不导出驱动消息。
            catch (PostgresException failure)
            {
                rejection = failure;
            }
            // 即便错误实现已成功删列，也先以系统目录给出不含秘密的确定性失败证据。
            await using var columnQuery = new NpgsqlCommand("""
                SELECT EXISTS (SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'governance' AND table_name = 'audit_records' AND column_name = 'ScopeSiteIds')
                """, observer);
            Assert.IsTrue((bool)(await columnQuery.ExecuteScalarAsync())!, "并发范围刚提交后，Down不得删除其范围列。");
            Assert.IsNotNull(rejection, "Down必须在写事务提交后重新检查并拒绝丢失审计事实。");
            Assert.AreEqual("P0001", rejection.SqlState);
            // 失败的迁移保持完整列值与最新历史，之后前向重入仍可正常读取。
            await database.Database.MigrateAsync();
            CollectionAssert.AreEqual(new[] { "site-a", "site-b" },
                (await database.AuditRecords.AsNoTracking().SingleAsync(row => row.Id == "race-scope-check")).ScopeSiteIds);
            Assert.IsTrue((await database.Database.GetAppliedMigrationsAsync()).Contains("20261025144246_AuditScopeSites"));
        }
        finally
        {
            // 清理严格限定本测试新库，不触及任何保留的开发卷。
            await using var drop = new NpgsqlCommand("DROP DATABASE \"" + name + "\" WITH (FORCE)", admin);
            await drop.ExecuteNonQueryAsync();
        }
    }

}
