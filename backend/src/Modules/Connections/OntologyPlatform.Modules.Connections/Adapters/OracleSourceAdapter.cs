using System.Diagnostics;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using Oracle.ManagedDataAccess.Client;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>Oracle固定TCPS目标的真实只读元数据适配器，无池、无自动重试或用户SQL。</summary>
public sealed partial class OracleSourceAdapter : IOracleSourceAdapter
{
    /// <summary>只由组合根注入的信任配置。</summary>
    private readonly OracleAdapterOptions options;

    /// <summary>每次调用都新建阶段数组，未观察阶段不能写PASS。</summary>
    private static readonly string[] StageNames = ["NETWORK", "TLS", "AUTH", "READ_ONLY", "METADATA"];

    /// <summary>固定宿主配置，不在构造期间访问网络或读取凭据。</summary>
    /// <param name="options">独立的CA和仅信任用途wallet路径。</param>
    public OracleSourceAdapter(OracleAdapterOptions options)
    {
        this.options = options;
    }

    /// <summary>每次重新核验当前信任原件，供持久配置绑定和进行中失效检查。</summary>
    public string TrustFingerprint
    {
        get
        {
            // 两份信任原件均有大小和路径边界，不将材料输出到诊断。
            var certificate = ReadTrustFile(options.RootCertificatePath);
            // 客户端wallet仅含CA，不包含认证或服务器私钥。
            var wallet = ReadTrustFile(Path.Combine(options.WalletDirectory, "cwallet.sso"));
            return Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(
                "oracle-tcps-v1|oracle-source:2484/FREEPDB1|" + Convert.ToHexString(SHA256.HashData(certificate)) + "|" + Convert.ToHexString(SHA256.HashData(wallet)))));
        }
    }

    /// <summary>共享十秒总期限，真实探测TLS、认证、只读权限与目录。</summary>
    /// <param name="profile">固定目标配置。</param>
    /// <param name="secret">本次调用内存中的密码。</param>
    /// <param name="cancellationToken">调用方取消。</param>
    /// <returns>五阶段真实快照。</returns>
    public async Task<ConnectionProbeStage[]> ProbeAsync(OracleConnectionProfile profile, string secret, CancellationToken cancellationToken)
    {
        Validate(profile, secret);
        // 一份总期限贯穿网络和所有命令，不在每阶段重新计时。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(10));
        // 当前步骤决定安全错误投影，绝不回显Oracle异常消息。
        var stage = 0;
        // 全部阶段先置为未运行。
        var stages = StageNames.Select(name => new ConnectionProbeStage { Name = name, Status = "NOT_RUN", DurationMs = 0, DiagnosticCode = null }).ToArray();
        // 真实单调计时供观测而非推断。
        var clock = Stopwatch.StartNew();
        try
        {
            await VerifyTlsAsync(deadline.Token);
            stages[0] = stages[0] with { Status = "PASS", DurationMs = clock.ElapsedMilliseconds };
            stage = 1;
            await ExecuteAsync(secret, async connection =>
            {
                // 只有实际ODP连接成功，才同时确认其TLS和认证；预握手本身不足。
                stages[1] = stages[1] with { Status = "PASS", DurationMs = clock.ElapsedMilliseconds };
                stage = 2;
                stages[stage] = stages[stage] with { Status = "PASS", DurationMs = clock.ElapsedMilliseconds };
                stage = 3;
                await VerifyReadOnlyAsync(connection, deadline.Token);
                stages[stage] = stages[stage] with { Status = "PASS", DurationMs = clock.ElapsedMilliseconds };
                stage = 4;
                await ReadCatalogAsync(connection, deadline.Token);
                await VerifyReadOnlyAsync(connection, deadline.Token);
                stages[stage] = stages[stage] with { Status = "PASS", DurationMs = clock.ElapsedMilliseconds };
                return true;
            }, deadline.Token);
        }
        catch (Exception error)
        {
            // TLS握手错误归入TLS阶段；未经成功握手不宣称网络/TLS共同通过。
            if (SafeCode(error, cancellationToken.IsCancellationRequested) == "connection_tls_untrusted") stage = 1;
            if (error is OracleException { Number: 1017 or 28000 or 28001 })
            {
                // 真实服务器在TCPS通道返回认证拒绝，才能确认TLS已完成。
                stages[1] = stages[1] with { Status = "PASS", DurationMs = clock.ElapsedMilliseconds };
                stage = 2;
            }
            stages[stage] = stages[stage] with { Status = "FAIL", DurationMs = clock.ElapsedMilliseconds, DiagnosticCode = SafeCode(error, cancellationToken.IsCancellationRequested) };
        }
        return stages;
    }

    /// <summary>二十秒内重新验证当前信任、权限和目录，真实令牌传入驱动读取。</summary>
    /// <param name="profile">固定合成目标。</param>
    /// <param name="secret">当前版本密码。</param>
    /// <param name="cancellationToken">来自会话/任务的取消信号。</param>
    /// <returns>完整有界元数据；失败不返回部分目录。</returns>
    public async Task<CatalogObject[]> DiscoverAsync(OracleConnectionProfile profile, string secret, CancellationToken cancellationToken)
    {
        Validate(profile, secret);
        // 取消关闭pipelining后可由驱动向源端发送真实取消。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(20));
        try
        {
            await VerifyTlsAsync(deadline.Token);
            return await ExecuteAsync(secret, async connection =>
            {
                await VerifyReadOnlyAsync(connection, deadline.Token);
                // 目录读取后再次检查实际权限，撤权期间不得发布旧成功。
                var objects = await ReadCatalogAsync(connection, deadline.Token);
                await VerifyReadOnlyAsync(connection, deadline.Token);
                return objects;
            }, deadline.Token);
        }
        catch (Exception error)
        {
            throw new PgSourceException(SafeCode(error, cancellationToken.IsCancellationRequested));
        }
    }

    /// <summary>适配器自身防御性核对目标与秘密，不能只信分发器曾校验。</summary>
    /// <param name="profile">公开配置。</param>
    /// <param name="secret">仅用于长度检查的内存密码。</param>
    private static void Validate(OracleConnectionProfile profile, string secret)
    {
        OracleAdapterOptions.Validate(profile, new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a"] });
        if (string.IsNullOrEmpty(secret) || secret.Length > 4096 || secret.Contains('\0'))
            throw new PgSourceException("connection_auth_failed");
    }

    /// <summary>官方builder隔离密码；描述符/钱包/重试策略全部由服务端固定。</summary>
    /// <param name="secret">不拼入描述符的内存密码。</param>
    /// <returns>尚未打开且没有连接池的物理连接。</returns>
    private OracleConnection Create(string secret)
    {
        // 固定单地址、单PDB和零重试，不使用TNS别名、LDAP或调用方连接串。
        var builder = new OracleConnectionStringBuilder
        {
            UserID = "FIXTURE_READER", Password = secret, Pooling = false, ConnectionTimeout = 5,
            DataSource = "(DESCRIPTION=(CONNECT_TIMEOUT=5)(TRANSPORT_CONNECT_TIMEOUT=5)(RETRY_COUNT=0)(ADDRESS=(PROTOCOL=TCPS)(HOST=oracle-source)(PORT=2484))(CONNECT_DATA=(SERVICE_NAME=FREEPDB1))(SECURITY=(SSL_SERVER_DN_MATCH=YES)))"
        };
        return new OracleConnection(builder.ConnectionString) { WalletLocation = options.WalletDirectory, SSLServerDNMatch = true, Pipelining = false };
    }

    /// <summary>唯一连接覆盖打开、操作及有界清理；不以Task.Run伪装异步或取消。</summary>
    /// <typeparam name="T">元数据操作返回类型。</typeparam>
    /// <param name="secret">内存密码。</param>
    /// <param name="action">串行源命令。</param>
    /// <param name="token">贯通Open及命令的取消令牌。</param>
    /// <returns>操作完整结果。</returns>
    private async Task<T> ExecuteAsync<T>(string secret, Func<OracleConnection, Task<T>> action, CancellationToken token)
    {
        // 捕获信任内容，不允许进行中替换wallet后沿用原探测依据。
        var trust = TrustFingerprint;
        // 从不复用物理连接，轮换/撤权不会命中旧连接池。
        var connection = Create(secret);
        try
        {
            await connection.OpenAsync(token);
            // 每个新会话主动设置内核只读，封住管理员切换用户模式期间的已连接会话竞态。
            using var readOnly = connection.CreateCommand();
            readOnly.CommandText = "ALTER SESSION SET READ_ONLY=TRUE";
            readOnly.CommandTimeout = 5;
            await readOnly.ExecuteNonQueryAsync(token);
            connection.ClientId = "G4-ORACLE-" + Guid.NewGuid().ToString("N");
            // 独立源端见证仅按此固定模块和reader筛选，不把密码用于标记。
            connection.ModuleName = "G4-M2-ORACLE-01";
            // 结果提交前再次检查信任材料字节。
            var result = await action(connection);
            if (TrustFingerprint != trust) throw new PgSourceException("connection_tls_untrusted");
            return result;
        }
        finally
        {
            await connection.DisposeAsync().AsTask().WaitAsync(TimeSpan.FromSeconds(5));
        }
    }

    /// <summary>单独确认链、有效期、ServerAuth与主机名；不改全局信任库。</summary>
    /// <param name="token">总期限的真实令牌。</param>
    private async Task VerifyTlsAsync(CancellationToken token)
    {
        _ = TrustFingerprint;
        // CA原件在当前任务路径内独立加载。
        using var root = X509Certificate2.CreateFromPem(Encoding.UTF8.GetString(ReadTrustFile(options.RootCertificatePath)));
        // 网络与握手均响应同一取消令牌。
        using var socket = new TcpClient();
        await socket.ConnectAsync("oracle-source", 2484, token);
        using var ssl = new SslStream(socket.GetStream(), false, (_, certificate, _, errors) =>
        {
            if (certificate is null || (errors & SslPolicyErrors.RemoteCertificateNameMismatch) != 0) return false;
            // 自定义根只用于本次握手，不能接受操作系统其它根替代固定任务CA。
            using var chain = new X509Chain();
            chain.ChainPolicy.TrustMode = X509ChainTrustMode.CustomRootTrust;
            chain.ChainPolicy.CustomTrustStore.Add(root);
            chain.ChainPolicy.RevocationMode = X509RevocationMode.NoCheck;
            chain.ChainPolicy.ApplicationPolicy.Add(new Oid("1.3.6.1.5.5.7.3.1"));
            // 回调证书不由本作用域拥有，复制后独立释放。
            using var leaf = X509CertificateLoader.LoadCertificate(certificate.GetRawCertData());
            return chain.Build(leaf);
        });
        await ssl.AuthenticateAsClientAsync(new SslClientAuthenticationOptions
        {
            TargetHost = "oracle-source", EnabledSslProtocols = SslProtocols.Tls12 | SslProtocols.Tls13,
            CertificateRevocationCheckMode = X509RevocationMode.NoCheck
        }, token);
    }

    /// <summary>只读取有界普通信任文件，拒绝URL、链接和缺失路径。</summary>
    /// <param name="path">宿主固定路径。</param>
    /// <returns>仅用于散列与解析的原始字节。</returns>
    private static byte[] ReadTrustFile(string path)
    {
        try
        {
            if (!Path.IsPathFullyQualified(path) || !File.Exists(path)) throw new PgSourceException("connection_tls_untrusted");
            // 上级目录同样不能经符号链接转移到其它信任来源。
            var file = new FileInfo(path);
            if (file.LinkTarget is not null || file.Length is <= 0 or > 1024 * 1024) throw new PgSourceException("connection_tls_untrusted");
            for (var parent = file.Directory; parent is not null; parent = parent.Parent)
                if (parent.LinkTarget is not null) throw new PgSourceException("connection_tls_untrusted");
            // 打开后仍限制实际读取字节，文件增长不能绕过元数据上限。
            using var stream = File.OpenRead(path);
            return ReadTrustBytes(stream);
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException)
        {
            throw new PgSourceException("connection_tls_untrusted");
        }
    }

    /// <summary>信任正文最多读取上限加一字节，所有预期读取故障统一失败关闭。</summary>
    private static byte[] ReadTrustBytes(Stream stream)
    {
        try
        {
            // 多一个字节仅用于判断超限，不读取其余内容。
            var buffer = new byte[1024 * 1024 + 1];
            // 同步短文件读取不涉及网络，实际长度独立于FileInfo。
            var length = stream.ReadAtLeast(buffer, buffer.Length, throwOnEndOfStream: false);
            if (length is <= 0 or > 1024 * 1024) throw new PgSourceException("connection_tls_untrusted");
            return buffer[..length];
        }
        catch (Exception error) when (error is IOException or UnauthorizedAccessException or ObjectDisposedException)
        {
            throw new PgSourceException("connection_tls_untrusted");
        }
    }

    /// <summary>异常仅映射白名单，不返回Oracle错误消息、SQL或目标。</summary>
    /// <param name="error">真实底层异常。</param>
    /// <param name="cancelled">调用方是否明确取消。</param>
    /// <returns>安全错误码。</returns>
    private static string SafeCode(Exception error, bool cancelled)
    {
        // ODP把TLS认证异常包在50201及两层网络异常内；只识别类型，不解析可能含敏感信息的正文。
        Exception? cause = error;
        for (var depth = 0; cause is not null && depth < 8; depth++, cause = cause.InnerException)
            if (cause is AuthenticationException) return "connection_tls_untrusted";
        return error switch
        {
        PgSourceException safe => safe.Code,
        OperationCanceledException when cancelled => "connection_cancelled",
        OracleException { Number: 1013 } when cancelled => "connection_cancelled",
        OracleException { Number: 1017 or 28000 or 28001 } => "connection_auth_failed",
        OracleException { Number: 1031 or 942 } => "connection_readonly_unverified",
        OracleException { Number: 29024 or 28759 or 28860 } => "connection_tls_untrusted",
        AuthenticationException => "connection_tls_untrusted",
            _ => "connection_source_unavailable"
        };
    }
}
