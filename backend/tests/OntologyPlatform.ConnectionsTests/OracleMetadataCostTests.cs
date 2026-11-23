using System.Diagnostics;
using System.Runtime.InteropServices;
using System.Text.Json;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;
using Oracle.ManagedDataAccess.Client;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>独立测试宿主测量真实物理连接的元数据成本，不创建平台查询。</summary>
[TestClass]
public sealed class OracleMetadataCostTests
{
    /// <summary>从首次 TLS 前的同一单调起点计量工作和退出，失败也导出全部已观察分段。</summary>
    [TestMethod]
    public async Task MeasureBoundMetadataOnly()
    {
        Assert.AreEqual("G4-ORACLE-MAPPING-QUERY-001", Environment.GetEnvironmentVariable("G4_ORACLE_MAPPING_TASK"));
        // 本次执行号同时作为准确源 ClientId。
        var execution = Guid.ParseExact(await File.ReadAllTextAsync("/run/sync/execution"), "N");
        // 冻结的当前目录在两轮生产方法中分别复核。
        var snapshot = JsonSerializer.Deserialize<CatalogSnapshotView>(await File.ReadAllBytesAsync("/run/sync/catalog.json"),
            G4ConnectionJson.Options) ?? throw new InvalidDataException();
        // 专用 reader 文件仅在受限测试进程内传给原生连接适配器。
        var secret = await File.ReadAllTextAsync("/run/fixture/reader-password");
        // 使用同一 TCPS 端点、可信 CA 和只读钱包。
        var adapter = new OracleSourceAdapter(new() { RootCertificatePath = "/run/fixture/ca.pem", WalletDirectory = "/run/fixture/client-wallet" });
        using var trace = new G4OracleQueryTrace(execution);
        // 两个诊断期限以首次 TLS 前的同一起点为准。
        var origin = Stopwatch.GetTimestamp();
        using var work = new CancellationTokenSource(TimeSpan.FromSeconds(8) - Stopwatch.GetElapsedTime(origin));
        // 零代表未观察到工作令牌触发。
        long cutoff = 0;
        using var signal = work.Token.Register(() => Interlocked.CompareExchange(ref cutoff, Stopwatch.GetTimestamp(), 0));
        // 保存仅属于本样本的连接，finally 中等待真实驱动释放。
        OracleConnection? connection = null;
        string? failure = null; // 工作失败的固定类别。
        int? number = null; // 驱动原生错误号。
        string? disposeFailure = null; // 释放异常独立记录。
        long workEnd; // 最后一个工作步骤返回或抛出时刻。
        try
        {
            connection = await adapter.OpenMappingAsync(secret, execution, work.Token, verifyAccess: false);
            if (!await OracleSourceAdapter.MappingAccessMatchesAsync(connection, work.Token)) throw new InvalidDataException();
            // 两次目录确认的物理键及 NLS 结果需要一致。
            var shape = await OracleMappingSourceValidator.CheckCatalogAsync(connection, snapshot, work.Token);
            await OracleSourceAdapter.VerifyMappingAccessAsync(connection, work.Token, post: true);
            if (shape != await OracleMappingSourceValidator.CheckCatalogAsync(connection, snapshot, work.Token, post: true))
                throw new InvalidDataException();
        }
        catch (Exception error)
        {
            failure = error switch { OracleException => "oracle", OperationCanceledException => "cancelled", _ => "failed" };
            number = (error as OracleException)?.Number;
        }
        finally
        {
            workEnd = Stopwatch.GetTimestamp();
            try
            {
                if (connection is not null)
                    await G4OracleQueryTrace.ObserveAsync("disposeConnection", () => connection.DisposeAsync().AsTask());
            }
            catch (Exception error) { disposeFailure = error is OperationCanceledException ? "cancelled" : "failed"; }
        }
        // 源会话退出另由控制器核实。
        var end = Stopwatch.GetTimestamp();
        // 每次只向专属同步目录发布一次有界原件，不输出任何连接参数或行。
        await using var output = new FileStream("/run/sync/metadata.json", FileMode.CreateNew, FileAccess.Write, FileShare.None);
        await JsonSerializer.SerializeAsync(output, new { origin, workEnd, end, cutoff, failure, number, disposeFailure,
            frequency = Stopwatch.Frequency, process = Environment.ProcessId, runtime = RuntimeInformation.FrameworkDescription,
            architecture = RuntimeInformation.ProcessArchitecture.ToString(), connections = typeof(OracleSourceAdapter).Module.ModuleVersionId,
            contracts = typeof(G4OracleQueryTrace).Module.ModuleVersionId, odp = typeof(OracleConnection).Module.ModuleVersionId,
            source = trace.Snapshot() });
        Assert.IsTrue(failure is null && disposeFailure is null && Stopwatch.GetElapsedTime(origin, workEnd) <= TimeSpan.FromSeconds(8)
            && Stopwatch.GetElapsedTime(origin, end) <= TimeSpan.FromSeconds(10), "组件运行或退出超出诊断期限。");
    }
}
