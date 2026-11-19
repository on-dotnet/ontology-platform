using System.Diagnostics;
using System.Net;
using Microsoft.Extensions.Logging;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Ontology;

namespace OntologyPlatform.SemanticTests;

/// <summary>在实际验证图上核对服务器绝对截止、提前断开、准确清理归属及槽位回收。</summary>
[TestClass]
public sealed class SemanticDeadlineTests
{
    /// <summary>只保存捕获的临时图告警，不记录图内容、用户输入或认证材料。</summary>
    private sealed class CleanupLog : ILogger<JenaSemanticRuntime>
    {
        /// <summary>未确认的准确图 IRI。</summary>
        internal List<string> Graphs { get; } = [];

        /// <summary>测试记录不建立额外日志范围。</summary>
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        /// <summary>只处理清理告警。</summary>
        public bool IsEnabled(LogLevel logLevel) => logLevel == LogLevel.Warning;

        /// <summary>从结构化日志读取服务端生成的准确 IRI。</summary>
        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            if (state is IEnumerable<KeyValuePair<string, object?>> fields)
                Graphs.AddRange(fields.Where(field => field.Key == "Graph").Select(field => (string)field.Value!));
        }
    }

    /// <summary>所有等待有上限；测试在 finally 中单独回读和恢复本次确切所有的临时图。</summary>
    [TestMethod]
    [DataRow("healthy")]
    [DataRow("short")]
    [DataRow("multi-delete")]
    [DataRow("disconnect")]
    [DataRow("deadline")]
    [DataRow("slow-delete")]
    [DataRow("failed-delete")]
    [DataRow("already-expired")]
    public async Task WorkAndCleanupRespectOriginalDeadline(string scenario)
    {
        // 每个场景使用一份新源，运行时为其随机生成独占临时图。
        var source = new SourceBundle { OntologyTurtle = "<urn:rf:s> <urn:rf:p> 1 .", DataTurtle = scenario == "multi-delete" ? "<urn:rf:d> <urn:rf:p> 2 ." : "" };
        // 一一匹配实际 HTTP 写入、删除及未确认记录。
        var owned = new HashSet<Uri>();
        // 已经完成 PUT、进入后续验证的图数。
        var verifiedPuts = 0;
        // 发往验证 dataset 的精确删除次数。
        var deletes = 0;
        // 捕获生产构造函数消费的结构化清理日志。
        var log = new CleanupLog();
        // 用户断开和服务器截止分开控制。
        using var caller = new CancellationTokenSource();
        // 一个绝对截止从进入所有依赖前开始，已经过期的情况不能触及 HTTP。
        var expires = DateTimeOffset.UtcNow.AddMilliseconds(scenario == "already-expired" ? -1 : scenario == "short" ? 100 : 650);
        // 真实 PUT 之后才在 GET 或 DELETE 上安排有界延迟。
        var runtime = SemanticFixture.RuntimeWithGate(async (request, token) =>
        {
            if (request.Method == HttpMethod.Put) owned.Add(request.RequestUri!);
            if (!owned.Contains(request.RequestUri!)) return;
            if (request.Method == HttpMethod.Get)
            {
                verifiedPuts++;
                if (scenario == "disconnect") caller.Cancel();
                if (scenario == "deadline") await Task.Delay(TimeSpan.FromMilliseconds(900), token);
            }
            if (request.Method == HttpMethod.Delete)
            {
                deletes++;
                Assert.IsTrue(DateTimeOffset.UtcNow < expires);
                if (scenario == "failed-delete" || (scenario == "multi-delete" && deletes == 1)) throw new HttpRequestException("synthetic delete unavailable");
                if (scenario == "slow-delete") await Task.Delay(TimeSpan.FromMilliseconds(900), token);
            }
        }, log);
        try
        {
            using (new SemanticReadDeadline(expires))
            {
                // 包含断开、异常和返回前真实 HTTP 收尾的墙钟时间。
                var watch = Stopwatch.StartNew();
                if (scenario is "healthy" or "short") await runtime.AnalyzeAsync(source, 1, caller.Token);
                else if (scenario == "disconnect")
                    await Assert.ThrowsAsync<OperationCanceledException>(() => runtime.AnalyzeAsync(source, 1, caller.Token));
                else
                {
                    // 服务器超时和删除传输失败必须有各自可观察的失败语义。
                    var error = await Assert.ThrowsAsync<SemanticOperationException>(() => runtime.AnalyzeAsync(source, 1, caller.Token));
                    Assert.AreEqual(scenario is "failed-delete" or "multi-delete" ? "semantic_unavailable" : "semantic_timeout", error.Code);
                }
                Assert.IsTrue(scenario == "already-expired" || DateTimeOffset.UtcNow < expires, $"Elapsed {watch.Elapsed}");
            }
            Assert.AreEqual(scenario == "already-expired", owned.Count == 0);
            if (scenario == "multi-delete") Assert.AreEqual(2, owned.Count);
            Assert.AreEqual(owned.Count, verifiedPuts);
            Assert.AreEqual(owned.Count, deletes);
            // 对响应未知与确认删除分别读取实际图，避免把未确认误计成已删除。
            using var client = new HttpClient(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(1) };
            foreach (var graph in owned)
            {
                using var response = await client.GetAsync(graph);
                // SendAsync 的查询参数只包含当前运行时随机生成的临时图名。
                var iri = Uri.UnescapeDataString(graph.Query["?graph=".Length..]);
                Assert.AreEqual(scenario is "failed-delete" or "slow-delete" || (scenario == "multi-delete" && graph == owned.First()), log.Graphs.Contains(iri));
                Assert.AreEqual(log.Graphs.Contains(iri) ? HttpStatusCode.OK : HttpStatusCode.NotFound, response.StatusCode);
            }
        }
        finally
        {
            // 由测试直接清除自身未确认的准确图；不扫描、清除或重启其他持有服务。
            using var client = new HttpClient(new HttpClientHandler { UseProxy = false, AllowAutoRedirect = false }) { Timeout = TimeSpan.FromSeconds(1) };
            foreach (var graph in owned)
            {
                using var response = await client.DeleteAsync(graph);
                Assert.IsTrue(response.IsSuccessStatusCode || response.StatusCode == HttpStatusCode.NotFound);
            }
        }
        // 每个场景后两项真实工作必须都能重新占槽。
        await Task.WhenAll(Enumerable.Range(0, 2).Select(_ => SemanticFixture.Runtime().AnalyzeAsync(source, 1, default)));
    }
}
