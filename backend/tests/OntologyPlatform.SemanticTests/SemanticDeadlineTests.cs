using System.Diagnostics;
using System.Text.Json;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.SemanticTests;

/// <summary>在真实验证图上记录调用方截止与依赖收尾的先后关系。</summary>
[TestClass]
public sealed class SemanticDeadlineTests
{
    /// <summary>提交前用已完成的 PUT 见证本次 DELETE 与原请求令牌的关系。</summary>
    [TestMethod]
    public async Task ObserveCleanupAtCallerDeadline()
    {
        // 时间从请求准入前计量；回环传输、运行时和实际图均使用正常配置。
        var elapsed = Stopwatch.StartNew();
        // 本次合成调用只拥有这一个短期限。
        using var caller = new CancellationTokenSource(TimeSpan.FromMilliseconds(450));
        // 只收集本次调用的随机临时图标识和单调时钟，不记录图内容。
        string? owned = null;
        // 后续 GET 进入时 PUT 已结束。
        double? afterPutMs = null;
        // 清理令牌的实际状态取自发送前的 HTTP 钩子。
        bool? deleteTokenCancelled = null;
        // 只观察准确临时图，全部等待均由本次方法实际 await。
        double? deleteMs = null;
        // 每个请求结束后钩子仍转发到同一真实 Fuseki。
        var runtime = SemanticFixture.RuntimeWithGate(async (request, token) =>
        {
            if (request.Method == HttpMethod.Put) owned = request.RequestUri!.Query;
            if (request.RequestUri!.Query != owned) return;
            if (request.Method == HttpMethod.Get)
            {
                afterPutMs = elapsed.Elapsed.TotalMilliseconds;
                await Task.Delay(TimeSpan.FromMilliseconds(650), token);
            }
            if (request.Method == HttpMethod.Delete)
            {
                deleteMs = elapsed.Elapsed.TotalMilliseconds;
                deleteTokenCancelled = token.IsCancellationRequested;
                await Task.Delay(TimeSpan.FromMilliseconds(35), token);
            }
        });
        await Assert.ThrowsAsync<OperationCanceledException>(() => runtime.AnalyzeAsync(
            new SourceBundle { OntologyTurtle = "<urn:rf:s> <urn:rf:p> 1 ." }, 1, caller.Token));
        // 原件使用显式测试输出目录，实际结束时刻包含真实 DELETE 等待。
        var facts = new { afterPutMs, deleteMs, deleteTokenCancelled, callerCancelled = caller.IsCancellationRequested,
            returnMs = elapsed.Elapsed.TotalMilliseconds, deadlineMs = 450, owned };
        if (Environment.GetEnvironmentVariable("DMQ_RF_OBSERVATION") is { } destination)
            await File.WriteAllBytesAsync(destination, JsonSerializer.SerializeToUtf8Bytes(facts));
        Assert.IsTrue(afterPutMs < 450 && deleteMs >= 445 && deleteTokenCancelled == false);
    }
}
