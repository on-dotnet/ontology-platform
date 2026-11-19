using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>在独立原生观察者已准备后测当期固定实体查询；同步窗口不进入产品 SQL。</summary>
[TestClass]
public sealed class OracleMappingWindowTests
{
    /// <summary>测量冻结查询的自然周期和实际取行数，为取消取证提供时间基线。</summary>
    [TestMethod]
    public async Task MeasureOneFixedEntityRead()
    {
        Assert.AreEqual("G4-ORACLE-MAPPING-QUERY-001", Environment.GetEnvironmentVariable("G4_ORACLE_MAPPING_TASK"));
        // 每个观察样本使用独立的物理会话和执行标记。
        var id = Guid.ParseExact(await File.ReadAllTextAsync("/run/sync/execution"), "N");
        // 本次只接受已经冻结的单行种子或正常读上限。
        var count = int.Parse(await File.ReadAllTextAsync("/run/sync/count"), CultureInfo.InvariantCulture);
        Assert.IsTrue(count is 1 or 100);
        // 这里只测源可观察性，夹具建立/同步适用 Mapping 实验的有界总时限。
        using var lifetime = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        // 客户端只持本次合成读者的信任材料。
        var adapter = new OracleSourceAdapter(new OracleAdapterOptions
        {
            RootCertificatePath = "/run/fixture/ca.pem", WalletDirectory = "/run/fixture/client-wallet"
        });
        // 管理员和观察者身份不会进入被测进程。
        var secret = await File.ReadAllTextAsync("/run/fixture/reader-password", lifetime.Token);
        // 分别记录握手/前提与固定读取，前者不能冒充 SQL 在途。
        var setup = Stopwatch.StartNew();
        await using var connection = await adapter.OpenMappingAsync(secret, id, lifetime.Token);
        // 已核同一物理事务，独立观察者随后识别这个会话。
        await using var transaction = await OracleSourceAdapter.BeginMappingAsync(connection, lifetime.Token);
        setup.Stop();
        await File.WriteAllTextAsync("/run/sync/armed", id.ToString("N"), lifetime.Token);
        while (!File.Exists("/run/sync/release"))
            await Task.Delay(1, lifetime.Token);
        // 只测一次真实生成的固定 SQL；没有延迟函数或变形执行计划。
        var start = DateTimeOffset.UtcNow;
        var elapsed = Stopwatch.StartNew();
        var rows = await OracleSourceAdapter.ReadMappingAsync(connection, transaction, false, lifetime.Token);
        elapsed.Stop();
        // 上界覆盖全部游标消费及释放。
        var finish = DateTimeOffset.UtcNow;
        Assert.AreEqual(count, rows.Count);
        Assert.AreEqual(1L, rows[0].Id);
        await transaction.CommitAsync(lifetime.Token);
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            execution = id.ToString("N"), setupMs = setup.Elapsed.TotalMilliseconds,
            fixedReadMs = elapsed.Elapsed.TotalMilliseconds, start, finish, count = rows.Count
        }));
    }
}
