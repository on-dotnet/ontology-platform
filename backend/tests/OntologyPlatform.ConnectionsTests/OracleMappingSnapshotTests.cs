using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>用真实 TCPS 驱动和并发合成写者验证只读事务、源类型和固定读取窗口。</summary>
[TestClass]
public sealed class OracleMappingSnapshotTests
{
    /// <summary>同一只读事务保留旧行，新事务在同会话看见独立写者已提交的新值。</summary>
    [TestMethod]
    public async Task FixedReadsHoldOneSnapshotAcrossIndependentCommit()
    {
        // 由独立任务探针只读挂载准确 reader 引用，不读取管理凭证。
        var folder = "/run/fixture";
        // 任务身份与工作目录由控制器在实际容器内固定。
        Assert.AreEqual("G4-ORACLE-MAPPING-QUERY-001", Environment.GetEnvironmentVariable("G4_ORACLE_MAPPING_TASK"));
        // 真实驱动纳入 Mapping 的既有评估时间上限。
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(30));
        // 每次运行的独立执行身份用于源端校对。
        var execution = Guid.NewGuid();
        // 同一任务合成 CA 与只含 CA 的专用钱包。
        var adapter = new OracleSourceAdapter(new OracleAdapterOptions
        {
            RootCertificatePath = Path.Combine(folder, "ca.pem"),
            WalletDirectory = Path.Combine(folder, "client-wallet")
        });
        // 从专用 fixture 文件读取，不把口令加入输出或环境变量。
        var secret = await File.ReadAllTextAsync(Path.Combine(folder, "reader-password"), deadline.Token);
        // 贯穿两次真实事务的同一物理连接。
        await using var connection = await adapter.OpenMappingAsync(secret, execution, deadline.Token);
        Assert.IsFalse(connection.Pipelining);
        // 第一个固定查询的实测周期包含执行、取行及游标释放。
        var started = Stopwatch.StartNew();
        // 分支第一条业务 SQL 确立只读事务。
        await using (var first = await OracleSourceAdapter.BeginMappingAsync(connection, deadline.Token))
        {
            Assert.IsFalse(connection.AutoCommit);
            started.Restart();
            // 源实体采用 NUMBER(28,6)，读取和比较均不用浮点。
            var entity = (await OracleSourceAdapter.ReadMappingAsync(connection, first, false, deadline.Token)).Single();
            Console.WriteLine(JsonSerializer.Serialize(new { execution, fixedReadMs = started.Elapsed.TotalMilliseconds, entity.Id }));
            Assert.AreEqual(1L, entity.Id);
            Assert.AreEqual(1m, entity.JoinKey);
            Assert.AreEqual(9999999999999999999999.999999m, entity.Value);
            Assert.AreEqual("org-demo", entity.Organization);
            Assert.AreEqual("site-a", entity.Site);
            Assert.AreEqual("omq-entity-1", entity.External);
            Assert.AreEqual("entity", entity.Label);
            Assert.AreEqual("2026-01-01T00:00:00.000001", entity.From.ToString("yyyy-MM-ddTHH:mm:ss.ffffff", CultureInfo.InvariantCulture));
            Assert.AreEqual("2026-02-01T00:00:00.000001", entity.To.ToString("yyyy-MM-ddTHH:mm:ss.ffffff", CultureInfo.InvariantCulture));
            Assert.AreEqual("2026-01-02T00:00:00.123456", entity.Event.ToString("yyyy-MM-ddTHH:mm:ss.ffffff", CultureInfo.InvariantCulture));
            Assert.AreEqual("2026-01-02T00:00:01.654321", entity.Observed.ToString("yyyy-MM-ddTHH:mm:ss.ffffff", CultureInfo.InvariantCulture));
            // 写者通过隔离同步目录接收当前事务已读的独立信号。
            await File.WriteAllTextAsync("/run/sync/first-read", execution.ToString("N"), deadline.Token);
            while (!File.Exists("/run/sync/committed"))
                await Task.Delay(10, deadline.Token);
            // 确认是本次合成写者的已提交变更。
            Assert.AreEqual(execution.ToString("N"), await File.ReadAllTextAsync("/run/sync/committed", deadline.Token));
            // 同一事务复读同一键，不能看见写者的新值。
            var stillOld = (await OracleSourceAdapter.ReadMappingAsync(connection, first, false, deadline.Token)).Single();
            Assert.AreEqual(entity, stillOld);
            // 第二表与实体表同一事务，关系数值比较保持十进制等价。
            var target = (await OracleSourceAdapter.ReadMappingAsync(connection, first, true, deadline.Token)).Single();
            Assert.AreEqual(2L, target.Id);
            Assert.AreEqual(entity.JoinKey, target.JoinKey);
            Assert.AreEqual(-entity.Value, target.Value);
            await first.CommitAsync(deadline.Token);
        }
        // 新事务应看见准确键已提交的更新。
        await using var fresh = await OracleSourceAdapter.BeginMappingAsync(connection, deadline.Token);
        // 再次调用相同的固定 SQL，排除查询差异。
        var visible = (await OracleSourceAdapter.ReadMappingAsync(connection, fresh, false, deadline.Token)).Single();
        Assert.AreEqual("entity-after-commit", visible.Label);
        await fresh.CommitAsync(deadline.Token);
    }
}
