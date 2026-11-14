using System.Text;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;
using OntologyPlatform.Modules.SemanticQuery;

namespace OntologyPlatform.QueryTests;

/// <summary>真实PG迁移与新作用域回读证明规范字节存储不依赖进程内对象。</summary>
[TestClass]
public sealed class G4QueryPersistenceTests
{
    /// <summary>缺少当前任务TLS数据库输入必须失败，不能跳过后报告PASS。</summary>
    [TestMethod]
    public async Task ExactBytesRoundTripThroughFreshOfficialContext()
    {
        // 只有受控M4驱动为本任务合成数据库提供进程内连接配置。
        var connection = Environment.GetEnvironmentVariable("G4_QUERY_TEST_CONNECTION");
        Assert.IsFalse(string.IsNullOrWhiteSpace(connection), "M4真实数据库尚未准入，不能用内存替身通过。");
        await DemandIsolatedDatabaseAsync(connection!);
        // 正式模块注册路径和生产生命周期保持一致。
        var configuration = new ConfigurationBuilder().AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["ConnectionStrings:governance"] = connection,
            ["G4:QueryEnabled"] = "true"
        }).Build();
        // 容器仅提供依赖集合，不替换正式DbContext工厂。
        var services = new ServiceCollection();
        services.AddLogging();
        services.AddSemanticQueryModule(configuration);
        // 验证所有生命周期，禁止测试偷偷把工厂换成单例上下文。
        await using var provider = services.BuildServiceProvider(new ServiceProviderOptions { ValidateScopes = true });
        // 本测试行身份仅属于当前Run，不覆盖其他任务数据。
        var id = Guid.NewGuid().ToString("N");
        // 独占测试目录只在本任务短命容器tmpfs中存活，不借用宿主认证keyring。
        var keyDirectory = new DirectoryInfo(Path.Combine(Path.GetTempPath(), "g4-query-result-" + id));
        keyDirectory.Create();
        // 使用文件keyring产生密文；第二个provider必须重新读取文件才能恢复。
        var encryption = DataProtectionProvider.Create(keyDirectory, options => options.SetApplicationName("G4-M4-QUERY-001"));
        // 业务结果保留超过JS安全范围的decimal以及固定微秒精度。
        var protectedResult = G4QueryResultStore.Protect(encryption, id, G4QueryTests.FixtureResult());
        // bytea原件包含超过JS安全整数的decimal及固定微秒词法。
        var bytes = Encoding.UTF8.GetBytes("{\"decimal\":\"9007199254740993.20\",\"time\":\"2026-11-14T01:02:03.123456Z\"}");
        await using (var scope = provider.CreateAsyncScope())
        {
            // 使用正式工厂和已提交迁移，不能使用EnsureCreated。
            var factory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<G4QueryDbContext>>();
            await using var db = await factory.CreateDbContextAsync();
            await db.Database.MigrateAsync();
            db.Queries.Add(new G4QueryRecord
            {
                Id = id, OrganizationId = "org-1", SubjectId = "actor-1", IdempotencyKey = id,
                RequestHash = new string('a', 64), RequestBytes = bytes, CreatedAtUtc = DateTimeOffset.UtcNow,
                ResultCiphertext = protectedResult.Ciphertext, ResultHash = protectedResult.Hash, ResultSize = protectedResult.Size,
                ExpiresAtUtc = DateTimeOffset.UtcNow.AddHours(24), DeadlineAtUtc = DateTimeOffset.UtcNow.AddSeconds(5)
            });
            await db.SaveChangesAsync();
        }
        await using (var scope = provider.CreateAsyncScope())
        {
            // 新作用域产生新DbContext，读取真实已提交bytea。
            var factory = scope.ServiceProvider.GetRequiredService<IDbContextFactory<G4QueryDbContext>>();
            await using var db = await factory.CreateDbContextAsync();
            // 准确主键与组织限定避免跨任务取到同名行。
            var row = await db.Queries.AsNoTracking().SingleAsync(value => value.Id == id && value.OrganizationId == "org-1");
            CollectionAssert.AreEqual(bytes, row.RequestBytes);
            // 独立provider不共享内存密钥缓存，真实数据库回读后恢复同一规范原件。
            var decryption = DataProtectionProvider.Create(keyDirectory, options => options.SetApplicationName("G4-M4-QUERY-001"));
            CollectionAssert.AreEqual(G4QueryCanonical.Result(G4QueryTests.FixtureResult()),
                G4QueryResultStore.Unprotect(decryption, id, row.ResultCiphertext, row.ResultHash!));
            Assert.AreEqual(protectedResult.Size, row.ResultSize);
            Assert.IsFalse(row.ResultCiphertext.AsSpan().SequenceEqual(G4QueryCanonical.Result(G4QueryTests.FixtureResult())));
            Assert.AreEqual("RUNNING", row.ExecutionStatus);
            Assert.IsTrue((await db.Database.GetAppliedMigrationsAsync()).Contains("20261114000000_G4QueryPersistence"));
            await db.Queries.Where(value => value.Id == id).ExecuteDeleteAsync();
            Assert.IsFalse(await db.Queries.AnyAsync(value => value.Id == id));
        }
        // 只删除本测试创建的准确临时目录，宿主及其他任务keyring保持不变。
        keyDirectory.Delete(recursive: true);
    }

    /// <summary>任何迁移或未来时钟维护前，核对真实数据库名称及任务独占标记，拒绝运行库。</summary>
    internal static async Task DemandIsolatedDatabaseAsync(string connectionString)
    {
        // 客户端连接串检查先于连接，避免意外向运行库发送迁移。
        var builder = new NpgsqlConnectionStringBuilder(connectionString);
        Assert.IsTrue(System.Text.RegularExpressions.Regex.IsMatch(builder.Database ?? string.Empty, @"\Am4_query_test_[0-9a-f]{12}\z"), "必须使用独立测试库。");
        // 真实服务端身份与创建时所有权注释必须同时一致，不能只相信传入名称。
        await using var connection = new NpgsqlConnection(connectionString);
        await connection.OpenAsync();
        // 只读元数据确认该连接确实进入本任务为本次测试新建的数据库。
        await using var command = new NpgsqlCommand("SELECT current_database(), shobj_description(oid, 'pg_database') FROM pg_database WHERE datname = current_database()", connection);
        await using var reader = await command.ExecuteReaderAsync();
        Assert.IsTrue(await reader.ReadAsync());
        Assert.AreEqual(builder.Database, reader.GetString(0));
        Assert.AreEqual("G4-M4-QUERY-001:query-impl-01:" + builder.Database![14..], reader.GetString(1));
    }

}
