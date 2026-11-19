using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Text.Json;
using Oracle.ManagedDataAccess.Client;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>独立 Oracle 观察者确认同一次固定 SQL 活动后，立即对同一个驱动命令请求真正取消。</summary>
[TestClass]
public sealed class OracleMappingCancelProbeTests
{
    /// <summary>只发送一次定向取消，区分命中、自然结束及原预算耗尽，始终等待物理释放。</summary>
    [TestMethod]
    public async Task AttemptDirectedCancelOnObservedExecution()
    {
        Assert.AreEqual("G4-ORACLE-MAPPING-QUERY-001", Environment.GetEnvironmentVariable("G4_ORACLE_MAPPING_TASK"));
        // 控制器冻结本次唯一运行标记与独立源 IP。
        var id = Guid.ParseExact(await File.ReadAllTextAsync("/run/sync/execution"), "N");
        var peer = IPAddress.Parse(await File.ReadAllTextAsync("/run/sync/source-ip"));
        // 在单一 source-internal 网络内监听固定观察信号；容器没有宿主端口映射。
        using var signals = new UdpClient(new IPEndPoint(IPAddress.Any, 28761));
        var secret = await File.ReadAllTextAsync("/run/fixture/reader-password");
        var adapter = new OracleSourceAdapter(new OracleAdapterOptions
        {
            RootCertificatePath = "/run/fixture/ca.pem", WalletDirectory = "/run/fixture/client-wallet"
        });
        await File.WriteAllTextAsync("/run/sync/armed", id.ToString("N"));
        // 观察者必须先独立完成认证。此等待发生在被测源分支打开前。
        using var arm = new CancellationTokenSource(TimeSpan.FromSeconds(8));
        Assert.AreEqual("READY", await SignalAsync(signals, id, peer, arm.Token));
        // 分支从验证、物理连接打开前计时，工作阶段预留原一秒中的 250ms 给释放。
        var origin = Stopwatch.GetTimestamp();
        var startedUtc = DateTimeOffset.UtcNow;
        using var work = new CancellationTokenSource(TimeSpan.FromMilliseconds(750));
        using var branch = new CancellationTokenSource(TimeSpan.FromSeconds(1));
        // 所有探针事件由同一进程单调记录；UTC 用于与独立的源采样核对。
        double? cancelStart = null, cancelReturned = null, received = null, readEnded = null;
        DateTimeOffset? sentUtc = null, receivedUtc = null, readDoneUtc = null;
        int? sourceError = null, rows = null;
        string? notice = null;
        var commandTimeout = -1;
        // 状态 0 未开始，1 工作中，2 取消已占用命令，3 命令已经返回。
        int state = 0;
        await using (var connection = await adapter.OpenMappingAsync(secret, id, work.Token))
        await using (var transaction = await OracleSourceAdapter.BeginMappingAsync(connection, work.Token))
        using (var command = OracleSourceAdapter.CreateMappingCommand(connection, transaction, false))
        {
            commandTimeout = command.CommandTimeout;
            // 独立只读观察者返回同次源身份后由接收线程定向调用 Cancel，与业务读并行。
            var delivery = Task.Run(async () =>
            {
                try
                {
                    notice = await SignalAsync(signals, id, peer, branch.Token);
                    received = Stopwatch.GetElapsedTime(origin).TotalMilliseconds;
                    receivedUtc = DateTimeOffset.UtcNow;
                    if (notice == "ACTIVE" && Interlocked.CompareExchange(ref state, 2, 1) == 1)
                    {
                        sentUtc = DateTimeOffset.UtcNow;
                        cancelStart = Stopwatch.GetElapsedTime(origin).TotalMilliseconds;
                        command.Cancel();
                        cancelReturned = Stopwatch.GetElapsedTime(origin).TotalMilliseconds;
                    }
                }
                catch (OperationCanceledException) when (branch.IsCancellationRequested)
                {
                    notice = "NO_SIGNAL_IN_BRANCH";
                }
            });
            Volatile.Write(ref state, 1);
            try
            {
                rows = (await OracleSourceAdapter.ConsumeMappingAsync(command, work.Token)).Count;
            }
            catch (OracleException error)
            {
                sourceError = error.Number;
            }
            finally
            {
                Interlocked.Exchange(ref state, 3);
                readDoneUtc = DateTimeOffset.UtcNow;
                readEnded = Stopwatch.GetElapsedTime(origin).TotalMilliseconds;
                // 先结束本次命令和受控回滚，再释放物理连接。禁止迟到的 Cancel 瞄准下一条 SQL。
                await delivery;
                await transaction.RollbackAsync(branch.Token);
            }
        }
        var end = Stopwatch.GetElapsedTime(origin).TotalMilliseconds;
        Console.WriteLine(JsonSerializer.Serialize(new
        {
            execution = id.ToString("N"), startedUtc, notice, receivedUtc, sentUtc, readDoneUtc,
            received, cancelStart, cancelReturned, readEnded, cleanupEnded = end, sourceError, rows,
            commandTimeout, workDeadlineMs = 750, branchDeadlineMs = 1000
        }));
        Assert.IsTrue(end <= 1000, "Physical cleanup exceeded the original branch deadline");
        Assert.IsTrue(rows == 100 || sourceError == 1013, "Expected native success or Oracle cancellation");
    }

    /// <summary>只接收准确源 IP 和同次执行标记，不接受另一次执行或其他内部客户端的控制信号。</summary>
    /// <param name="socket">本探针临时 UDP 端点。</param>
    /// <param name="execution">准确执行身份。</param>
    /// <param name="peer">独立源观察程序所在容器地址。</param>
    /// <param name="token">观察准备或源分支的既有期限。</param>
    /// <returns>已绑定身份的源观察分类。</returns>
    private static async Task<string> SignalAsync(UdpClient socket, Guid execution, IPAddress peer, CancellationToken token)
    {
        var message = await socket.ReceiveAsync(token);
        Assert.AreEqual(peer, message.RemoteEndPoint.Address);
        var parts = Encoding.ASCII.GetString(message.Buffer).Trim().Split('|');
        Assert.AreEqual(2, parts.Length);
        Assert.AreEqual(execution.ToString("N"), parts[0]);
        return parts[1];
    }
}
