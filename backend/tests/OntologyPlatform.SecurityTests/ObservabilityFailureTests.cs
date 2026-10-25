using System.Collections.Concurrent;
using System.Diagnostics;
using System.Net;
using System.Text;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Hosting.Server.Features;
using Microsoft.AspNetCore.Http;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using Npgsql;
using OpenTelemetry;

namespace OntologyPlatform.SecurityTests;

/// <summary>通过正式Kestrel入口验证异常分类、失败关闭及完整遥测脱敏。</summary>
[TestClass]
public sealed class ObservabilityFailureTests
{
    /// <summary>标记只存在于合成异常内部，不得进入响应、日志或Span。</summary>
    private const string SensitiveMarker = "synthetic-obs-secret-password-token-marker";

    /// <summary>普通编程故障与非请求取消必须500，只有已知输入及依赖故障映射400或503。</summary>
    /// <param name="kind">测试注册器使用的有限异常种类。</param>
    /// <param name="status">独立于实现给出的HTTP预期。</param>
    /// <param name="category">独立于实现给出的固定诊断类别。</param>
    /// <returns>真实请求及全遥测边界检查任务。</returns>
    [TestMethod]
    [DataRow("invalid_operation", 500, "unexpected_failure")]
    [DataRow("argument", 500, "unexpected_failure")]
    [DataRow("format", 500, "unexpected_failure")]
    [DataRow("access", 500, "unexpected_failure")]
    [DataRow("uncancelled_oce", 500, "unexpected_failure")]
    [DataRow("bad_request", 400, "invalid_request")]
    [DataRow("database_write", 503, "database_write")]
    [DataRow("database_failure", 503, "database_failure")]
    [DataRow("upstream", 503, "upstream_unavailable")]
    [DataRow("real_connection", 503, "database_connection")]
    public async Task FaultsHaveBoundedClassificationAndNoSensitiveTelemetry(string kind, int status, string category)
    {
        // 捕获所有正式过滤后日志，包括框架日志、结构化状态、作用域及异常对象。
        using var capture = new ObservabilityCapture();
        // 临时证书和未运行依赖均由测试独立管理。
        using var fixture = new SecurityHostFixture();
        // 正式构造器不包含任何产品故障路由。
        await using var app = fixture.Create(logs: capture);
        app.MapGet("/api/obs-failure/{kind}", async (HttpContext context) =>
        {
            if (kind == "real_connection")
            {
                // 真正Npgsql连接故障，不伪造连接失败分类所需的异常图。
                await using var connection = new NpgsqlConnection("Host=127.0.0.1;Port=18998;Database=unused;Username=test;Password=" + SensitiveMarker + ";Timeout=1");
                await connection.OpenAsync(context.RequestAborted);
                return;
            }
            throw CreateFailure(kind);
        });
        await app.StartAsync();
        // 客户端只连接正式Kestrel动态回环端口。
        using var client = fixture.CreateClient(app);
        // 将marker也放在query，检测默认开发框架遥测是否泄漏。
        using var response = await client.GetAsync("/api/obs-failure/" + kind + "?access_token=" + SensitiveMarker);
        Assert.AreEqual(status, (int)response.StatusCode);
        // ProblemDetails必须无原异常且Trace与诊断事件一致。
        var body = await response.Content.ReadAsStringAsync();
        Assert.IsFalse(body.Contains(SensitiveMarker, StringComparison.Ordinal), "响应泄漏合成异常。");
        StringAssert.Contains(body, status == 500 ? "internal_error" : status == 400 ? "invalid_request" : "dependency_unavailable");
        // HTTP处理可能已完成而Activity停止通知尚未投递，停止宿主确保导出完成。
        await app.StopAsync();
        capture.AssertFault("/api/obs-failure/{kind}", category, "problem_returned", status, response.Headers.GetValues("X-Trace-Id").Single());
        capture.AssertNoSensitiveData(SensitiveMarker);
    }

    /// <summary>请求取消不写Problem、已开始不追加JSON、错误响应写回再失败均必须受控Abort。</summary>
    /// <param name="kind">需要触发的真实响应生命周期边界。</param>
    /// <param name="outcome">应记录的固定完成结果。</param>
    /// <param name="category">应记录的固定异常类别。</param>
    /// <param name="status">已开始保留200，取消使用499，内部写回失败使用500。</param>
    /// <returns>真实断连及完整日志边界检查任务。</returns>
    [TestMethod]
    [DataRow("cancelled", "request_cancelled", "request_cancelled", 499)]
    [DataRow("started", "response_aborted", "unexpected_failure", 200)]
    [DataRow("started_cancelled", "request_cancelled", "request_cancelled", 200)]
    [DataRow("abort_other", "response_aborted", "unexpected_failure", 500)]
    [DataRow("write_failure", "response_aborted", "unexpected_failure", 500)]
    public async Task UnwritableResponsesAbortWithoutEscapingOriginalFailure(string kind, string outcome, string category, int status)
    {
        // 包括框架默认日志在内的捕获器可以发现原异常逃逸。
        using var capture = new ObservabilityCapture();
        // 仅测试临时资产，不能修改生产路由或真实开发凭据。
        using var fixture = new SecurityHostFixture();
        // 保持Development，覆盖开发异常页自动注入的实际行为。
        await using var app = fixture.Create(logs: capture);
        app.MapGet("/api/obs-boundary/{kind}", async (HttpContext context) =>
        {
            if (kind == "started_cancelled")
            {
                await context.Response.WriteAsync("safe-prefix");
                await context.Response.Body.FlushAsync();
            }
            if (kind is "cancelled" or "started_cancelled")
            {
                context.RequestAborted = new CancellationToken(true);
                throw new OperationCanceledException(SensitiveMarker, context.RequestAborted);
            }
            if (kind == "started")
            {
                await context.Response.WriteAsync("safe-prefix");
                await context.Response.Body.FlushAsync();
            }
            if (kind == "abort_other")
            {
                context.RequestAborted = new CancellationToken(true);
            }
            if (kind == "write_failure")
            {
                context.Response.OnStarting(() => throw new InvalidOperationException(SensitiveMarker));
            }
            throw new InvalidOperationException(SensitiveMarker);
        });
        await app.StartAsync();
        // 真实HTTP读到连接中止可以抛HttpRequestException，不能把客户端断连视为测试错误。
        using var client = fixture.CreateClient(app);
        try
        {
            // 不追加Problem JSON是断连边界的外部可观察合同。
            using var response = await client.GetAsync("/api/obs-boundary/" + kind);
            // 若客户端收到完整响应，仍不能含任何异常细节或Problem正文。
            var body = await response.Content.ReadAsStringAsync();
            Assert.IsFalse(body.Contains(SensitiveMarker, StringComparison.Ordinal));
            Assert.IsFalse(body.Contains("application/problem", StringComparison.Ordinal));
            Assert.IsFalse(body.Contains("internal_error", StringComparison.Ordinal));
        }
        catch (HttpRequestException)
        {
            // 正式Abort导致的真实连接截断符合失败关闭合同。
        }
        await app.StopAsync();
        capture.AssertNoSensitiveData(SensitiveMarker);
        capture.AssertFault("/api/obs-boundary/{kind}", category, outcome, status);
    }

    /// <summary>健康探针与既有OIDC输入错误保持现有状态，成功请求也有明确完成结果。</summary>
    /// <returns>真实正式端点回归检查任务。</returns>
    [TestMethod]
    public async Task ExistingHealthAndOidcStatusesRemainUnchanged()
    {
        // 既有正式端点不需要新增故障注入路由。
        using var capture = new ObservabilityCapture();
        // 探针凭据由临时fixture提供，不输出其值。
        using var fixture = new SecurityHostFixture();
        // 保持原服务、认证和端点配置。
        await using var app = fixture.Create(logs: capture);
        await app.StartAsync();
        // 动态回环客户端不跟随OIDC重定向。
        using var client = fixture.CreateClient(app);
        Assert.AreEqual(HttpStatusCode.Unauthorized, (await client.GetAsync("/health/live")).StatusCode);
        client.DefaultRequestHeaders.Add("X-Health-Key", fixture.HealthKey);
        Assert.AreEqual(HttpStatusCode.OK, (await client.GetAsync("/health/live")).StatusCode);
        Assert.AreEqual(HttpStatusCode.ServiceUnavailable, (await client.GetAsync("/health/ready")).StatusCode);
        Assert.AreEqual(HttpStatusCode.BadRequest, (await client.GetAsync("/signin-oidc?error=invalid_request")).StatusCode);
        await app.StopAsync();
        // 完成事件的outcome用于确认原有正常及受控错误路径已给出明确结果。
        Assert.IsTrue(capture.Logs.Any(log => log.Event.Id == 1001 && log.Fields.TryGetValue("Outcome", out var outcome) && outcome == "completed"));
        capture.AssertNoSensitiveData(SensitiveMarker);
    }

    /// <summary>正式ServiceDefaults的原生OTLP出口实际发送安全故障日志与Span，不用内存日志代替导出验收。</summary>
    /// <returns>真实HTTP OTLP接收、导出flush与二次写回负例任务。</returns>
    [TestMethod]
    [DoNotParallelize]
    public async Task NativeOtlpExportContainsControlledFaultAndNoOriginalException()
    {
        // 接收器仅在本轮回环动态端口收取本测试OTLP，不连接外部服务。
        await using var sink = await ObservabilityExportSink.StartAsync();
        // 只临时设置当前测试进程的官方exporter环境选项，退出时恢复原值。
        var names = new[] { "OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_PROTOCOL" };
        // 不输出旧值，避免任何历史运行时配置成为证据内容。
        var previous = names.Select(Environment.GetEnvironmentVariable).ToArray();
        try
        {
            Environment.SetEnvironmentVariable(names[0], sink.Address);
            Environment.SetEnvironmentVariable(names[1], "http/protobuf");
            // 全字段捕获仍检查框架源头，OTLP sink另查实际字节。
            using var capture = new ObservabilityCapture();
            // 测试证书完全临时生成，不接触历史秘密。
            using var fixture = new SecurityHostFixture();
            // 正式配置打开原生ServiceDefaults exporter，宿主释放会flush所有信号。
            await using (var app = fixture.Create(logs: capture, overrides: new Dictionary<string, string?> { ["OTEL_EXPORTER_OTLP_ENDPOINT"] = sink.Address }))
            {
                app.MapGet("/api/obs-export/{kind}", (HttpContext context, string kind) =>
                {
                    if (kind == "write")
                    {
                        context.Response.OnStarting(() => throw new InvalidOperationException(SensitiveMarker));
                    }
                    throw new InvalidOperationException(SensitiveMarker);
                });
                await app.StartAsync();
                // Kestrel请求与OTLP回环出口均为真实网络连接。
                using var client = fixture.CreateClient(app);
                Assert.AreEqual(HttpStatusCode.InternalServerError, (await client.GetAsync("/api/obs-export/normal?access_token=" + SensitiveMarker)).StatusCode);
                try
                {
                    // 二次写回可能直接断连，接收端仍必须得到安全受控故障。
                    using var response = await client.GetAsync("/api/obs-export/write");
                }
                catch (HttpRequestException)
                {
                    // 受控Abort允许真实连接截断。
                }
                await app.StopAsync();
            }
            capture.AssertNoSensitiveData(SensitiveMarker);
            Assert.IsTrue(sink.Payloads.Any(payload => payload.Signal == "logs" && payload.Text.Contains("PlatformRequestFault", StringComparison.Ordinal)), "原生OTLP必须实际发送受控故障事件。");
            // logs.proto字段12的LEN标签0x62与长度20精确定位event_name，不把body中的同名字符串当事件身份。
            Assert.IsTrue(sink.Payloads.Any(payload => payload.Signal == "logs" && payload.Text.Contains("b\u0014PlatformRequestFault", StringComparison.Ordinal)), "实际OTLP顶层event_name必须保留正式LoggerMessage事件名称。");
            Assert.IsTrue(sink.Payloads.Any(payload => payload.Signal == "traces" && payload.Text.Contains("platform.exception.category", StringComparison.Ordinal)), "原生OTLP必须实际发送真实请求Span分类。");
            Assert.IsFalse(sink.Payloads.Any(payload => payload.Text.Contains(SensitiveMarker, StringComparison.Ordinal)), "OTLP原始protobuf出口包含合成秘密。");
        }
        finally
        {
            // 恢复只影响本测试进程，不改机器或项目全局配置。
            for (var index = 0; index < names.Length; index++)
            {
                Environment.SetEnvironmentVariable(names[index], previous[index]);
            }
        }
    }

    /// <summary>构造仅用于测试的有界已知异常，原始marker不得越过宿主边界。</summary>
    /// <param name="kind">固定测试种类。</param>
    /// <returns>带无效合成marker的异常。</returns>
    private static Exception CreateFailure(string kind) => kind switch
    {
        "invalid_operation" => new InvalidOperationException(SensitiveMarker),
        "argument" => new ArgumentException(SensitiveMarker),
        "format" => new FormatException(SensitiveMarker),
        "access" => new UnauthorizedAccessException(SensitiveMarker),
        "uncancelled_oce" => new OperationCanceledException(SensitiveMarker),
        "bad_request" => new BadHttpRequestException(SensitiveMarker),
        "database_write" => new DbUpdateException(SensitiveMarker),
        "database_failure" => new NpgsqlException(SensitiveMarker),
        "upstream" => new HttpRequestException(SensitiveMarker),
        _ => throw new AssertFailedException("未知测试种类。")
    };
}

/// <summary>检查ILogger所有可导出字段及真实Activity，而不只检查新日志格式化正文。</summary>
internal sealed class ObservabilityCapture : ILoggerProvider, ISupportExternalScope
{
    /// <summary>真实框架与应用日志的完整安全快照。</summary>
    public ConcurrentBag<ObservabilityLog> Logs { get; } = [];

    /// <summary>真实停止Activity的标记、事件及状态描述快照。</summary>
    private readonly ConcurrentBag<string> spans = [];

    /// <summary>标准外部作用域提供器包含活动Trace作用域。</summary>
    private IExternalScopeProvider scopes = new LoggerExternalScopeProvider();

    /// <summary>直接监听ASP.NET Core与平台的真实活动生命周期。</summary>
    private readonly ActivityListener listener;

    /// <summary>监听正式服务端Activity，样本由实际请求产生。</summary>
    public ObservabilityCapture()
    {
        listener = new ActivityListener
        {
            ShouldListenTo = source => source.Name is "Microsoft.AspNetCore" or "OntologyPlatform.Api",
            Sample = (ref ActivityCreationOptions<ActivityContext> _) => ActivitySamplingResult.AllDataAndRecorded,
            ActivityStopped = activity => spans.Add(string.Join("|", activity.TagObjects.Select(tag => tag.Key + "=" + tag.Value))
                + "|" + activity.StatusDescription + "|" + string.Join("|", activity.Events.Select(item => item.Name + ":" + string.Join(";", item.Tags.Select(tag => tag.Key + "=" + tag.Value)))))
        };
        ActivitySource.AddActivityListener(listener);
    }

    /// <summary>让标准LoggerFactory注入真实外部作用域。</summary>
    /// <param name="scopeProvider">框架使用的作用域提供器。</param>
    public void SetScopeProvider(IExternalScopeProvider scopeProvider) => scopes = scopeProvider;

    /// <summary>保留日志类别，便于发现框架异常绕过。</summary>
    /// <param name="categoryName">真实日志类别。</param>
    /// <returns>专属日志快照写入器。</returns>
    public ILogger CreateLogger(string categoryName) => new Observer(this, categoryName);

    /// <summary>核对Event1003合同，字段必须精确且无异常对象。</summary>
    /// <param name="route">固定路由模板。</param>
    /// <param name="category">固定异常类别。</param>
    /// <param name="outcome">固定完成结果。</param>
    /// <param name="status">准确HTTP状态或受控取消状态。</param>
    /// <param name="traceId">可选的实际响应TraceId。</param>
    public void AssertFault(string route, string category, string outcome, int status, string? traceId = null)
    {
        // 每请求只能产生一个固定故障事件，不能在二次写失败时重复记录。
        var fault = Logs.Single(log => log.Event.Id == 1003);
        Assert.AreEqual("PlatformRequestFault", fault.Event.Name);
        CollectionAssert.AreEquivalent(new[] { "Route", "ExceptionCategory", "Outcome", "Status", "TraceId", "{OriginalFormat}" }, fault.Fields.Keys.ToArray());
        Assert.AreEqual(route, fault.Fields["Route"]);
        Assert.AreEqual(category, fault.Fields["ExceptionCategory"]);
        Assert.AreEqual(outcome, fault.Fields["Outcome"]);
        Assert.AreEqual(status.ToString(System.Globalization.CultureInfo.InvariantCulture), fault.Fields["Status"]);
        Assert.AreEqual(32, fault.Fields["TraceId"].Length);
        if (traceId is not null)
        {
            Assert.AreEqual(traceId, fault.Fields["TraceId"]);
        }
        Assert.IsNull(fault.Exception);
        // 同请求完成事件的completed值必须与故障结果一致。
        Assert.IsTrue(Logs.Any(log => log.Event.Id == 1001 && log.Fields.TryGetValue("Outcome", out var completed) && completed == outcome));
        Assert.IsTrue(spans.Any(span => span.Contains("platform.exception.category=" + category, StringComparison.Ordinal)), "必须检查真实请求Activity，不能只有日志。");
    }

    /// <summary>正文、结构化值、作用域、异常对象、Span标签及事件都不能含原异常marker。</summary>
    /// <param name="marker">固定无效合成秘密标记。</param>
    public void AssertNoSensitiveData(string marker)
    {
        Assert.IsTrue(spans.Count > 0, "必须观察到真实服务端Activity。");
        Assert.IsFalse(spans.Any(span => span.Contains(marker, StringComparison.Ordinal)), "真实Activity含敏感值。");
        Assert.IsFalse(Logs.Any(log => log.Text.Contains(marker, StringComparison.Ordinal)
            || log.Fields.Any(field => field.Value.Contains(marker, StringComparison.Ordinal))
            || log.Scopes.Contains(marker, StringComparison.Ordinal)
            || (log.Exception?.ToString().Contains(marker, StringComparison.Ordinal) ?? false)), "框架或应用日志的正文/state/scopes/exception泄漏敏感值。 " + string.Join(";", Logs.Where(log => log.Text.Contains(marker, StringComparison.Ordinal) || (log.Exception?.ToString().Contains(marker, StringComparison.Ordinal) ?? false)).Select(log => log.Text.Split('|')[0] + ":" + log.Event.Id)));
    }

    /// <summary>停止只读观察，不持久化原始日志或异常。</summary>
    public void Dispose() => listener.Dispose();

    /// <summary>每个类别使用真实过滤后的结构化日志快照。</summary>
    /// <param name="owner">拥有作用域与内存证据的捕获器。</param>
    /// <param name="category">框架实际请求的日志类别。</param>
    private sealed class Observer(ObservabilityCapture owner, string category) : ILogger
    {
        /// <summary>由框架统一管理日志作用域。</summary>
        /// <typeparam name="TState">作用域状态类型。</typeparam>
        /// <param name="state">真实作用域状态。</param>
        /// <returns>标准作用域生命周期。</returns>
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => owner.scopes.Push(state);

        /// <summary>捕获所有正式过滤后日志级别。</summary>
        /// <param name="logLevel">待捕获级别。</param>
        /// <returns>始终捕获。</returns>
        public bool IsEnabled(LogLevel logLevel) => true;

        /// <summary>快照全部导出字段，不依赖单一格式化正文。</summary>
        /// <typeparam name="TState">结构化状态类型。</typeparam>
        /// <param name="logLevel">日志级别。</param>
        /// <param name="eventId">稳定事件身份。</param>
        /// <param name="state">真实结构化字段。</param>
        /// <param name="exception">真实异常对象，正常边界应为空。</param>
        /// <param name="formatter">正式日志格式化器。</param>
        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state, Exception? exception, Func<TState, Exception?, string> formatter)
        {
            // 标准字段保留原大小写，避免漏查源生成器的受控数据。
            var fields = state is IEnumerable<KeyValuePair<string, object?>> values
                ? values.ToDictionary(value => value.Key, value => value.Value?.ToString() ?? "") : new Dictionary<string, string>();
            // 当前作用域只在内存检查，不写入测试输出。
            var activeScopes = new List<string>();
            owner.scopes.ForEachScope((scope, target) => target.Add(scope is IEnumerable<KeyValuePair<string, object?>> scopeFields
                ? string.Join(";", scopeFields.Select(value => value.Key + "=" + value.Value)) : scope?.ToString() ?? ""), activeScopes);
            owner.Logs.Add(new ObservabilityLog(eventId, category + "|" + formatter(state, exception), fields, string.Join("|", activeScopes), exception));
        }
    }
}

/// <summary>仅内存保存完整日志边界，不将潜在原异常持久化。</summary>
/// <param name="Event">原始稳定事件编号及名称。</param>
/// <param name="Text">真实类别及格式化正文。</param>
/// <param name="Fields">结构化状态全部字段。</param>
/// <param name="Scopes">标准作用域完整快照。</param>
/// <param name="Exception">框架可能携带的原始异常。</param>
internal sealed record ObservabilityLog(EventId Event, string Text, Dictionary<string, string> Fields, string Scopes, Exception? Exception);

/// <summary>仅测试注册的真实OTLP HTTP接收器，内存字节仅用于检查不落磁盘。</summary>
internal sealed class ObservabilityExportSink : IAsyncDisposable
{
    /// <summary>本测试独占的回环HTTP接收宿主。</summary>
    private readonly WebApplication app;

    /// <summary>实际收到的日志、Span及指标protobuf字节的UTF8字符串检索视图。</summary>
    public ConcurrentBag<(string Signal, string Text)> Payloads { get; } = [];

    /// <summary>仅本测试进程使用的OTLP动态回环地址。</summary>
    public string Address => app.Services.GetRequiredService<IServer>().Features.Get<IServerAddressesFeature>()!.Addresses.Single();

    /// <summary>将接收宿主与字节快照绑定，不创建外部资源。</summary>
    /// <param name="application">未启动的接收宿主。</param>
    private ObservabilityExportSink(WebApplication application) => app = application;

    /// <summary>在真实Kestrel动态回环端口接收官方OTLP protobuf请求。</summary>
    /// <returns>已经启动的内存接收器。</returns>
    public static async Task<ObservabilityExportSink> StartAsync()
    {
        // 此接收器没有业务路由、证书、身份或外部依赖。
        var builder = WebApplication.CreateBuilder();
        builder.Logging.ClearProviders();
        // 官方exporter按标准路径发送每个信号。
        var sink = new ObservabilityExportSink(builder.Build());
        sink.app.Urls.Add("http://127.0.0.1:0");
        // 可选中继仅供独立Alloy边界fixture使用，限定本机回环，不访问完整栈或外部服务。
        var relay = Environment.GetEnvironmentVariable("G1_OBS_NATIVE_LOG_RELAY");
        if (relay is not null && (!Uri.TryCreate(relay, UriKind.Absolute, out var address) || !address.IsLoopback || address.Scheme != "http"))
        {
            throw new InvalidOperationException("测试中继必须是独立回环HTTP接收器。");
        }
        sink.app.MapPost("/v1/{signal}", async (HttpContext context, string signal) =>
        {
            // 完整保留本测试合成protobuf，仅在内存检测秘密，绝不输出原始字节。
            using var bytes = new MemoryStream();
            await context.Request.Body.CopyToAsync(bytes);
            sink.Payloads.Add((signal, Encoding.UTF8.GetString(bytes.ToArray())));
            if (signal == "logs" && relay is not null)
            {
                // 中继HTTP不能产生递归遥测；原始字节只在测试内存经独立Alloy处理。
                using var suppression = SuppressInstrumentationScope.Begin();
                // 每次fixture使用独立短生命周期连接，不复用产品客户端或凭据。
                using var client = new HttpClient();
                // 保持官方exporter实际protobuf字节，不重建或补造事件字段。
                using var content = new ByteArrayContent(bytes.ToArray());
                content.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue("application/x-protobuf");
                // Python回环中继将相同字节送入随机端口Alloy，并只保存安全字段摘要。
                using var response = await client.PostAsync(relay + "/v1/logs", content);
                response.EnsureSuccessStatusCode();
            }
            context.Response.ContentType = "application/x-protobuf";
            context.Response.StatusCode = 200;
        });
        await sink.app.StartAsync();
        return sink;
    }

    /// <summary>关闭接收器并释放回环端口。</summary>
    /// <returns>宿主停止及释放任务。</returns>
    public async ValueTask DisposeAsync()
    {
        await app.StopAsync();
        await app.DisposeAsync();
    }
}
