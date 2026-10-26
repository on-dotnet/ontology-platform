using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;
using Npgsql;
using OntologyPlatform.Modules.Publishing;

namespace OntologyPlatform.PublishingTests;

/// <summary>实际Master迁移的空库Down、历史保护和并发锁拒绝，不使用EnsureCreated。</summary>
[TestClass]
public sealed class PublishingMigrationTests
{
    /// <summary>只在脚本新建PG容器内创建独立数据库，真实验证迁移保护。</summary>
    [TestMethod]
    [DataRow("empty")]
    [DataRow("nonempty")]
    [DataRow("concurrent")]
    public async Task ActualMigrationDownGuard(string mode)
    {
        // 只接受本次隔离脚本明确注入的连接；不读取历史配置或凭证文件。
        var connection = Environment.GetEnvironmentVariable("G2_PUB_PG");
        if (connection is null) Assert.Inconclusive("NOT_RUN: 缺少当前临时PG。");
        // 服务端生成数据库名，不允许用户输入或共用现有数据库。
        var name = "pubdown_" + Guid.NewGuid().ToString("N");
        // 当前临时PG根连接仅负责本测试数据库生命周期。
        await using var admin = new NpgsqlConnection(connection);
        await admin.OpenAsync();
        // SQL标识由固定前缀及hex组成，不能参数化的数据库DDL不会接受外部值。
        await using (var create = new NpgsqlCommand("CREATE DATABASE \"" + name + "\"", admin)) await create.ExecuteNonQueryAsync();
        try
        {
            // 禁止池化，确保仅本测试连接生命周期参与Down并发检查。
            var builder = new NpgsqlConnectionStringBuilder(connection) { Database = name, Pooling = false };
            // 与生产工厂完全相同的模块schema和迁移历史。
            var options = new DbContextOptionsBuilder<PublishingDbContext>().UseNpgsql(builder.ConnectionString, database => database.MigrationsHistoryTable("__EFMigrationsHistory", "publishing")).Options;
            // 第一个上下文实际应用Master生成的迁移。
            await using var database = new PublishingDbContext(options);
            await database.Database.MigrateAsync();
            Assert.AreEqual(1, (await database.Database.GetAppliedMigrationsAsync()).Count());
            if (mode == "empty")
            {
                await database.GetService<IMigrator>().MigrateAsync("0");
                Assert.AreEqual(0, (await database.Database.GetAppliedMigrationsAsync()).Count());
                await database.Database.MigrateAsync();
                Assert.AreEqual(1, (await database.Database.GetAppliedMigrationsAsync()).Count());
            }
            else if (mode == "nonempty")
            {
                database.Commands.Add(new PublishingCommandRecord { Key = "persisted-fact", PayloadHash = new string('a', 64), SubjectId = "fixture" });
                await database.SaveChangesAsync();
                // 非空事实必须让真正Down失败，不能删表再回滚伪装成功。
                var failure = await Assert.ThrowsAsync<Exception>(() => database.GetService<IMigrator>().MigrateAsync("0"));
                Assert.IsInstanceOfType<PostgresException>(failure.GetBaseException());
                Assert.AreEqual(1, await database.Commands.CountAsync());
                Assert.AreEqual(1, (await database.Database.GetAppliedMigrationsAsync()).Count());
            }
            else
            {
                // 空库也先持有真实写事务表锁，Down的NOWAIT必须立即失败。
                await using var transaction = await database.Database.BeginTransactionAsync();
                await database.Database.ExecuteSqlRawAsync("LOCK TABLE publishing.\"Commands\" IN ROW EXCLUSIVE MODE");
                // 第二物理连接运行迁移，不能与持锁上下文共享事务。
                await using var other = new PublishingDbContext(options);
                // 实际数据库错误码证明是锁竞争拒绝，而非无迁移或连接错误。
                var failure = await Assert.ThrowsAsync<Exception>(() => other.GetService<IMigrator>().MigrateAsync("0"));
                Assert.IsInstanceOfType<PostgresException>(failure.GetBaseException());
                Assert.AreEqual("55P03", ((PostgresException)failure.GetBaseException()).SqlState);
                await transaction.RollbackAsync();
                Assert.AreEqual(1, (await database.Database.GetAppliedMigrationsAsync()).Count());
            }
        }
        finally
        {
            // 仅删除本方法刚创建的随机测试库，原governance库和其他任务不受影响。
            await using var drop = new NpgsqlCommand("DROP DATABASE \"" + name + "\" WITH (FORCE)", admin);
            await drop.ExecuteNonQueryAsync();
        }
    }
}
