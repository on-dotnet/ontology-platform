using System.Diagnostics;
using System.Net;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text.RegularExpressions;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>本任务唯一隔离HTTPS GET实现；每次新连接绑定完整核验DNS集合，禁止代理、重定向及Cookie。</summary>
public sealed class WebSourceAdapter : IWebSourceAdapter
{
    /// <summary>服务器冻结的运行身份。</summary>
    private readonly string runId;

    /// <summary>任务独立信任根路径，缺配置时拒绝Web调用而不影响PG。</summary>
    private readonly string rootCertificatePath;

    /// <summary>固定操作及授权范围注册。</summary>
    private readonly WebOperationPolicy policy;

    /// <summary>唯一允许的合成隔离地址，不是通用私网白名单。</summary>
    private static readonly IPAddress FixtureAddress = IPAddress.Parse("172.30.240.10");

    /// <summary>保持既有五阶段wire集合；READ_ONLY对Web表示实际固定GET操作。</summary>
    private static readonly string[] StageNames = ["NETWORK", "TLS", "AUTH", "READ_ONLY", "METADATA"];

    /// <summary>复制可信选项；未准入环境保持关闭，不读取任何密钥。</summary>
    public WebSourceAdapter(WebAdapterOptions options, WebOperationPolicy policy)
    {
        runId = options.TaskId == "G4-M2-WEB-01" ? options.RunId : string.Empty;
        rootCertificatePath = options.RootCertificatePath;
        this.policy = policy;
    }

    /// <summary>拒绝空集合、mapped IPv6、混合解析及任何非准确fixture地址。</summary>
    public static void ValidateAddresses(IPAddress[] addresses)
    {
        if (addresses.Length is < 1 or > 16 || addresses.Any(address => address.AddressFamily != AddressFamily.InterNetwork || !address.Equals(FixtureAddress)))
            throw new PgSourceException("connection_network_forbidden");
    }

    /// <summary>验证来源注册与任务准入，密钥仅接受无控制字符的有界HTTP字段值。</summary>
    private void Validate(WebApiConnectionProfile profile, string secret)
    {
        policy.Validate(profile, new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a"] });
        if (!Regex.IsMatch(runId, "^m2-[a-f0-9]{12}$", RegexOptions.CultureInvariant)
            || !Path.IsPathFullyQualified(rootCertificatePath)) throw new PgSourceException("connection_network_forbidden");
        if (secret.Length is < 8 or > 4096 || secret.Any(value => value < 33 || value > 126)) throw new PgSourceException("connection_auth_failed");
    }

    /// <summary>阶段进度仅由本次真实连接与响应推进，不将失败之后阶段标为通过。</summary>
    public async Task<ConnectionProbeStage[]> ProbeAsync(WebApiConnectionProfile profile, string secret, CancellationToken cancellationToken)
    {
        Validate(profile, secret);
        // 总期限覆盖DNS、TCP、TLS、认证及完整JSON正文。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(10));
        // 初始化为未运行，连接回调与响应处理才推进阶段。
        var stages = StageNames.Select(name => new ConnectionProbeStage { Name = name, Status = "NOT_RUN", DurationMs = 0, DiagnosticCode = null }).ToArray();
        // 当前阶段单调耗时用于真实报告。
        var watch = Stopwatch.StartNew();
        // 回调与HTTP响应按顺序推进同一调用的阶段。
        var stage = 0;
        void Complete()
        {
            stages[stage] = stages[stage] with { Status = "PASS", DurationMs = watch.ElapsedMilliseconds };
            stage++;
            watch.Restart();
        }
        try { _ = await ExecuteAsync(secret, Complete, deadline.Token); }
        catch (Exception error) when (error is HttpRequestException or IOException or SocketException or OperationCanceledException or PgSourceException or System.Security.Cryptography.CryptographicException)
        {
            // 异常正文与InnerException绝不跨Adapter边界；只映射固定已有诊断码。
            var code = SafeCode(error, cancellationToken.IsCancellationRequested);
            stages[Math.Min(stage, stages.Length - 1)] = stages[Math.Min(stage, stages.Length - 1)] with { Status = "FAIL", DiagnosticCode = code, DurationMs = watch.ElapsedMilliseconds };
        }
        return stages;
    }

    /// <summary>20秒预算内重新验证完整HTTPS响应；仅返回声明合同元数据。</summary>
    public async Task<CatalogObject[]> DiscoverAsync(WebApiConnectionProfile profile, string secret, CancellationToken cancellationToken)
    {
        Validate(profile, secret);
        // 禁用、用户取消及宿主终止均传播至socket和HTTP正文读取。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(20));
        try { return await ExecuteAsync(secret, () => { }, deadline.Token); }
        catch (Exception error) when (error is HttpRequestException or IOException or SocketException or OperationCanceledException or PgSourceException or System.Security.Cryptography.CryptographicException)
        {
            throw new PgSourceException(SafeCode(error, cancellationToken.IsCancellationRequested));
        }
    }

    /// <summary>逐次建立新连接；正常TLS链/SAN/SNI验证完成后HttpClient才发送密钥头。</summary>
    private async Task<CatalogObject[]> ExecuteAsync(string secret, Action complete, CancellationToken token)
    {
        token.ThrowIfCancellationRequested();
        // 仅加载本任务CA；不修改系统信任库，不下载中间证书。
        using var certificate = X509CertificateLoader.LoadCertificateFromFile(rootCertificatePath);
        // 使用平台TLS主机名验证，无放宽证书错误的回调。
        using var handler = new SocketsHttpHandler
        {
            AllowAutoRedirect = false, UseProxy = false, UseCookies = false, Credentials = null,
            AutomaticDecompression = DecompressionMethods.None, ConnectTimeout = TimeSpan.FromSeconds(3),
            PooledConnectionLifetime = TimeSpan.Zero, PooledConnectionIdleTimeout = TimeSpan.Zero,
            MaxConnectionsPerServer = 1, MaxResponseHeadersLength = 16,
            SslOptions = new SslClientAuthenticationOptions
            {
                AllowTlsResume = false,
                CertificateChainPolicy = new X509ChainPolicy
                {
                    TrustMode = X509ChainTrustMode.CustomRootTrust, RevocationMode = X509RevocationMode.NoCheck,
                    DisableCertificateDownloads = true
                }
            }
        };
        handler.SslOptions.CertificateChainPolicy!.CustomTrustStore.Add(certificate);
        handler.SslOptions.CertificateChainPolicy.ApplicationPolicy.Add(new Oid("1.3.6.1.5.5.7.3.1"));
        // 单次请求仅允许一个物理连接尝试；透明重试不能重新发送密钥或重复推进阶段。
        var connections = 0;
        handler.ConnectCallback = async (context, cancellation) =>
        {
            if (Interlocked.Increment(ref connections) != 1) throw new PgSourceException("connection_source_unavailable");
            if (context.DnsEndPoint.Host != "web-source" || context.DnsEndPoint.Port != 8443) throw new PgSourceException("connection_network_forbidden");
            // 三秒网络子预算同时覆盖DNS与TCP，不为重连重新放宽总预算。
            using var network = CancellationTokenSource.CreateLinkedTokenSource(cancellation, token);
            network.CancelAfter(TimeSpan.FromSeconds(3));
            // 检查所有解析地址后仅连接已验证的准确IP，绝不交回hostname再次解析。
            var addresses = await Dns.GetHostAddressesAsync(context.DnsEndPoint.Host, network.Token);
            ValidateAddresses(addresses);
            // 网络流拥有socket；失败和取消均精确释放本次连接。
            var socket = new Socket(AddressFamily.InterNetwork, SocketType.Stream, ProtocolType.Tcp);
            try
            {
                await socket.ConnectAsync(new IPEndPoint(FixtureAddress, 8443), network.Token);
                if (socket.RemoteEndPoint is not IPEndPoint peer || !peer.Address.Equals(FixtureAddress)) throw new PgSourceException("connection_network_forbidden");
                complete();
                return new NetworkStream(socket, ownsSocket: true);
            }
            catch { socket.Dispose(); throw; }
        };
        // 独立handler杜绝旧池连接和跨origin密钥复用；仅本次请求拥有客户端。
        using var client = new HttpClient(handler) { Timeout = Timeout.InfiniteTimeSpan };
        // 固定HTTP/1.1避免Alt-Svc/HTTP3另辟连接路径；不接收客户端Header或自由query。
        using var request = new HttpRequestMessage(HttpMethod.Get, WebOperationPolicy.Origin + WebOperationPolicy.Path)
        {
            Version = HttpVersion.Version11, VersionPolicy = HttpVersionPolicy.RequestVersionExact
        };
        request.Headers.Add(WebOperationPolicy.KeyHeader, secret);
        request.Headers.ConnectionClose = true;
        request.Headers.Accept.ParseAdd("application/json");
        // ResponseHeadersRead保留正文预算与取消，收到HTTP头意味着正常TLS握手已完成。
        using var response = await client.SendAsync(request, HttpCompletionOption.ResponseHeadersRead, token);
        complete();
        if ((int)response.StatusCode is >= 300 and <= 399) throw new PgSourceException("connection_network_forbidden");
        if (response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden) throw new PgSourceException("connection_auth_failed");
        if (response.StatusCode != HttpStatusCode.OK) throw new PgSourceException("connection_source_unavailable");
        complete();
        // READ_ONLY来自服务器预登记固定GET和本次真实请求，不声称已验证数据库角色。
        complete();
        if (response.Content.Headers.ContentType?.MediaType != "application/json" || response.Content.Headers.ContentEncoding.Count != 0)
            throw new PgSourceException("catalog_permission_limited");
        if (response.Content.Headers.ContentLength > WebJsonCatalog.MaximumBytes) throw new PgSourceException("catalog_budget_exceeded");
        // 正文逐块读取并在超预算第一块拒绝，不把截断结果当成功。
        await using var stream = await response.Content.ReadAsStreamAsync(token);
        // 内存上限由每次写入前的累积检查决定。
        using var body = new MemoryStream();
        // 固定缓冲区避免从不可信Content-Length预分配大内存。
        var buffer = new byte[8192];
        while (true)
        {
            // 同一取消令牌直接进入真实HTTP body read。
            var count = await stream.ReadAsync(buffer, token);
            if (count == 0) break;
            if (body.Length + count > WebJsonCatalog.MaximumBytes) throw new PgSourceException("catalog_budget_exceeded");
            body.Write(buffer, 0, count);
        }
        // 只投影已声明合同，不保存正文值或精度推断。
        var catalog = WebJsonCatalog.Parse(body.ToArray(), token);
        complete();
        return catalog;
    }

    /// <summary>保留固定安全分类，原始异常、地址及密钥不进入外部诊断。</summary>
    private static string SafeCode(Exception error, bool callerCancelled) => error switch
    {
        PgSourceException safe => safe.Code,
        HttpRequestException wrapped when wrapped.GetBaseException() is PgSourceException safe => safe.Code,
        OperationCanceledException => callerCancelled ? "connection_cancelled" : "connection_source_unavailable",
        HttpRequestException { HttpRequestError: HttpRequestError.SecureConnectionError } => "connection_tls_untrusted",
        System.Security.Cryptography.CryptographicException => "connection_tls_untrusted",
        _ => "connection_source_unavailable"
    };
}
