using System.Diagnostics;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;
using Npgsql;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>仅访问本阶段隔离合成源的真实只读适配器，不执行调用方提供的SQL。</summary>
public sealed partial class PgSourceAdapter : IPgSourceAdapter
{
    /// <summary>服务器指定的信任根路径；构造时复制，避免调用方修改选项扩大目标。</summary>
    private readonly string rootCertificatePath;

    /// <summary>构造时冻结服务器对空public的精确准入，调用方不能异步扩大。</summary>
    private readonly bool allowEmptyPublic;

    /// <summary>固定阶段顺序，失败后续阶段保持未执行。</summary>
    private static readonly string[] StageNames = ["NETWORK", "TLS", "AUTH", "READ_ONLY", "METADATA"];

    /// <summary>校验服务器选项也不能扩大本阶段已经批准的隔离目标。</summary>
    /// <param name="options">仅允许固定合成目标与服务器提供的CA文件。</param>
    public PgSourceAdapter(PgAdapterOptions options)
    {
        if (options.AllowedHost != "pg-source" || options.AllowedPort != 5432 ||
            options.AllowedDatabase != "fixture" || options.AllowedUsername != "fixture_reader")
        {
            throw new PgSourceException("connection_network_forbidden");
        }
        if (string.IsNullOrWhiteSpace(options.RootCertificatePath) || !Path.IsPathFullyQualified(options.RootCertificatePath))
        {
            throw new PgSourceException("connection_tls_untrusted");
        }
        rootCertificatePath = options.RootCertificatePath;
        // 明确区分服务器声明上限与请求集合；默认A不能接受B。
        var serverSchemas = options.AllowedSchemas?.ToArray();
        allowEmptyPublic = serverSchemas switch
        {
            ["production"] => false,
            ["production", "public"] => true,
            _ => throw new PgSourceException("connection_network_forbidden")
        };
    }

    /// <summary>独立实测五阶段，失败只返回固定诊断，绝不将后续未观测阶段标为通过。</summary>
    /// <param name="profile">必须再次符合固定目标的类型化配置。</param>
    /// <param name="secret">调用期间使用的内存凭据。</param>
    /// <param name="cancellationToken">调用方取消信号。</param>
    /// <returns>按固定顺序返回真实阶段结果。</returns>
    public async Task<ConnectionProbeStage[]> ProbeAsync(PgConnectionProfile profile, string secret, CancellationToken cancellationToken)
    {
        // 在任何异步等待前复制数组；后续权限与目录查询只消费已验快照。
        profile = profile with { AllowedSchemas = profile.AllowedSchemas?.ToArray()! };
        ValidateTarget(profile, secret);
        // 每次探测共享十秒总期限，阶段不能各自重复获得十秒。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(10));
        // 所有未开始的阶段显式保留NOT_RUN。
        var stages = StageNames.Select(name => new ConnectionProbeStage { Name = name, Status = "NOT_RUN", DurationMs = 0, DiagnosticCode = null }).ToArray();
        // 单调计时仅衡量当前阶段的真实耗时。
        var clock = Stopwatch.StartNew();
        // 当前阶段用于安全分类，避免TLS失败被误写成认证通过。
        var stage = 0;
        try
        {
            // 独立网络连接也用于真实TLS握手，不发送任何数据库凭据。
            using var client = new TcpClient();
            // 网络建立有三秒子期限且受总期限限制。
            using var networkDeadline = CancellationTokenSource.CreateLinkedTokenSource(deadline.Token);
            networkDeadline.CancelAfter(TimeSpan.FromSeconds(3));
            await client.ConnectAsync("pg-source", 5432, networkDeadline.Token);
            CompleteStage(stages, stage++, clock);
            await VerifyTlsAsync(client, deadline.Token);
            CompleteStage(stages, stage++, clock);
            // Npgsql在自己的认证连接上再次执行VerifyFull，独立TLS探测不替代认证连接校验。
            await using var connection = CreateConnection(secret);
            await connection.OpenAsync(deadline.Token);
            CompleteStage(stages, stage++, clock);
            // 只读事务包围权限核验与全部目录读取，永不执行试写DML。
            await using var transaction = await BeginReadOnlyAsync(connection, deadline.Token);
            await VerifyReadOnlyAsync(connection, transaction, deadline.Token);
            CompleteStage(stages, stage++, clock);
            await ReadCatalogAsync(connection, transaction, profile.AllowedSchemas, deadline.Token);
            CompleteStage(stages, stage, clock);
        }
        catch (Exception exception)
        {
            // 只输出冻结错误码；原异常不被挂为InnerException或写入日志。
            var code = SafeCode(exception, stage, cancellationToken.IsCancellationRequested);
            stages[stage] = stages[stage] with { Status = "FAIL", DurationMs = clock.ElapsedMilliseconds, DiagnosticCode = code };
        }
        return stages;
    }

    /// <summary>在二十秒有界只读事务中重验当前权限并发现目录，截断和零可见对象均不返回伪完整快照。</summary>
    /// <param name="profile">固定目标和允许Schema。</param>
    /// <param name="secret">当前内存凭据。</param>
    /// <param name="cancellationToken">发现任务持久取消意图传播来的信号。</param>
    /// <returns>最多一百对象、两千字段和二MiB的完整可见元数据。</returns>
    public async Task<CatalogObject[]> DiscoverAsync(PgConnectionProfile profile, string secret, CancellationToken cancellationToken)
    {
        // 在任何异步等待前复制数组；后续权限与目录查询只消费已验快照。
        profile = profile with { AllowedSchemas = profile.AllowedSchemas?.ToArray()! };
        ValidateTarget(profile, secret);
        // 发现总期限覆盖连接、只读核验和全部目录读取。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(20));
        // 阶段仅用于异常安全分类，不对外暴露原始驱动诊断。
        var stage = 2;
        try
        {
            // 禁用连接池，凭据轮换或撤权后不能复用旧认证连接。
            await using var connection = CreateConnection(secret);
            await connection.OpenAsync(deadline.Token);
            stage = 3;
            // 同一连接只读事务中重新验证角色，不依赖历史Probe结论。
            await using var transaction = await BeginReadOnlyAsync(connection, deadline.Token);
            await VerifyReadOnlyAsync(connection, transaction, deadline.Token);
            stage = 4;
            return await ReadCatalogAsync(connection, transaction, profile.AllowedSchemas, deadline.Token);
        }
        catch (Exception exception)
        {
            throw new PgSourceException(SafeCode(exception, stage, cancellationToken.IsCancellationRequested));
        }
    }

    /// <summary>拒绝绕过HTTP规则层的目标、Schema和TLS输入。</summary>
    /// <param name="profile">待验证配置。</param>
    /// <param name="secret">内存凭据，仅检查是否存在及有界。</param>
    private void ValidateTarget(PgConnectionProfile profile, string secret)
    {
        if (profile.Host != "pg-source" || profile.Port != 5432 || profile.Database != "fixture" || profile.Username != "fixture_reader")
        {
            throw new PgSourceException("connection_network_forbidden");
        }
        if (profile.SslMode != "VerifyFull")
        {
            throw new PgSourceException("connection_tls_untrusted");
        }
        if (profile.AllowedSchemas is not ["production"] && !(allowEmptyPublic && profile.AllowedSchemas is ["production", "public"]))
        {
            throw new PgSourceException("catalog_access_forbidden");
        }
        if (string.IsNullOrEmpty(secret) || secret.Length > 16384 || secret.Contains('\0'))
        {
            throw new PgSourceException("connection_auth_failed");
        }
    }

    /// <summary>使用强类型builder固定所有连接控制项，不接收任意连接串或Options。</summary>
    /// <param name="secret">仅当前调用使用的密码。</param>
    /// <returns>未打开且不使用共享连接池的连接。</returns>
    private NpgsqlConnection CreateConnection(string secret)
    {
        // 固定SearchPath防止源Schema中同名函数遮蔽系统元数据函数。
        var builder = new NpgsqlConnectionStringBuilder
        {
            Host = "pg-source",
            Port = 5432,
            Database = "fixture",
            Username = "fixture_reader",
            Password = secret,
            SslMode = SslMode.VerifyFull,
            RootCertificate = rootCertificatePath,
            Pooling = false,
            Timeout = 3,
            CommandTimeout = 3,
            CancellationTimeout = 250,
            SearchPath = "pg_catalog",
            IncludeErrorDetail = false,
            LogParameters = false,
            GssEncryptionMode = GssEncryptionMode.Disable
        };
        return new NpgsqlConnection(builder.ConnectionString);
    }

    /// <summary>通过PostgreSQL SSLRequest及标准TLS验证同时证明证书链和主机身份。</summary>
    /// <param name="client">已在三秒内建立的固定目标TCP连接。</param>
    /// <param name="cancellationToken">总期限。</param>
    private async Task VerifyTlsAsync(TcpClient client, CancellationToken cancellationToken)
    {
        // PostgreSQL协议的固定SSLRequest报文不包含SQL或凭据。
        byte[] request = [0, 0, 0, 8, 4, 210, 22, 47];
        // 保持同一个受控网络连接完成TLS探测。
        var stream = client.GetStream();
        await stream.WriteAsync(request, cancellationToken);
        // 服务端必须明确同意TLS，拒绝明文或未知协议响应。
        byte[] response = new byte[1];
        await stream.ReadExactlyAsync(response, cancellationToken);
        if (response[0] != (byte)'S')
        {
            throw new PgSourceException("connection_tls_untrusted");
        }
        // 仅加载服务器挂载的合成CA，不读取用户证书或全局私钥。
        using var certificate = X509Certificate2.CreateFromPem(await File.ReadAllTextAsync(rootCertificatePath, cancellationToken));
        // 自定义根及禁用下载保证验证不访问外网AIA/CRL。
        var chainPolicy = new X509ChainPolicy { TrustMode = X509ChainTrustMode.CustomRootTrust, RevocationMode = X509RevocationMode.NoCheck, DisableCertificateDownloads = true };
        chainPolicy.CustomTrustStore.Add(certificate);
        // 标准SslStream保留默认主机名验证，不使用接受全部证书回调。
        using var tls = new SslStream(stream, leaveInnerStreamOpen: true);
        await tls.AuthenticateAsClientAsync(new SslClientAuthenticationOptions
        {
            TargetHost = "pg-source",
            CertificateChainPolicy = chainPolicy,
            EnabledSslProtocols = SslProtocols.Tls12 | SslProtocols.Tls13
        }, cancellationToken);
    }

    /// <summary>创建只读事务，固定SQL不能被客户端参数替换。</summary>
    /// <param name="connection">已经过VerifyFull认证的连接。</param>
    /// <param name="cancellationToken">总期限与取消。</param>
    /// <returns>调用方负责释放的只读事务。</returns>
    private static async Task<NpgsqlTransaction> BeginReadOnlyAsync(NpgsqlConnection connection, CancellationToken cancellationToken)
    {
        // 事务开始后第一条命令就是只读设置，不在读取后补设。
        var transaction = await connection.BeginTransactionAsync(cancellationToken);
        try
        {
            // 仅设置当前事务，不改变源角色或持久数据库配置。
            await using var command = new NpgsqlCommand("SET TRANSACTION READ ONLY", connection, transaction);
            await command.ExecuteNonQueryAsync(cancellationToken);
            return transaction;
        }
        catch
        {
            await transaction.DisposeAsync();
            throw;
        }
    }

    /// <summary>验证身份、只读会话、继承能力、所有权与有效写ACL；未知或缺权限时关闭访问。</summary>
    /// <param name="connection">受控连接。</param>
    /// <param name="transaction">当前只读事务。</param>
    /// <param name="cancellationToken">总期限与取消。</param>
    private static async Task VerifyReadOnlyAsync(NpgsqlConnection connection, NpgsqlTransaction transaction, CancellationToken cancellationToken)
    {
        // 固定查询只返回安全布尔结论，不把角色名或ACL送出适配器。
        await using var command = new NpgsqlCommand(ReadOnlySql, connection, transaction);
        if (await command.ExecuteScalarAsync(cancellationToken) is not true)
        {
            throw new PgSourceException("connection_readonly_unverified");
        }
    }

    /// <summary>以参数化Schema交集读取原生类型，不访问业务表行或用户函数。</summary>
    /// <param name="connection">受控连接。</param>
    /// <param name="transaction">只读事务。</param>
    /// <param name="schemas">同步冻结并已通过精确策略校验的Schema集合。</param>
    /// <param name="cancellationToken">总期限与取消。</param>
    /// <returns>完整有界的可见对象集合。</returns>
    private static async Task<CatalogObject[]> ReadCatalogAsync(NpgsqlConnection connection, NpgsqlTransaction transaction, string[] schemas, CancellationToken cancellationToken)
    {
        if (schemas.Length == 2)
        {
            // 系统目录验证public真实无对象，不能用无SELECT权限或空投影代替。
            await using var emptyPublic = new NpgsqlCommand("""
                SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_namespace WHERE nspname = 'public')
                    AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = 'public')
                    AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid = p.pronamespace WHERE n.nspname = 'public')
                    AND NOT EXISTS (SELECT 1 FROM pg_catalog.pg_type t JOIN pg_catalog.pg_namespace n ON n.oid = t.typnamespace WHERE n.nspname = 'public')
                """, connection, transaction);
            if (await emptyPublic.ExecuteScalarAsync(cancellationToken) is not true)
            {
                throw new PgSourceException("catalog_access_forbidden");
            }
        }
        // Schema访问必须明确成立，不能用空目录推断源不存在。
        await using var access = new NpgsqlCommand("SELECT count(*) = cardinality(@schemas) FROM pg_catalog.pg_namespace WHERE nspname = ANY(@schemas) AND pg_catalog.has_schema_privilege(oid, 'USAGE')", connection, transaction);
        access.Parameters.AddWithValue("schemas", schemas);
        if (await access.ExecuteScalarAsync(cancellationToken) is not true)
        {
            throw new PgSourceException("catalog_permission_limited");
        }
        // SQL在源头最多返回两千零一列和一百零一个对象哨兵，不先拉全库再截断。
        await using var command = new NpgsqlCommand(CatalogSql, connection, transaction);
        command.Parameters.AddWithValue("schemas", schemas);
        // 按Schema/对象/原始列序稳定排序，输出可用于确定性fingerprint。
        var objects = new List<CatalogObject>();
        // 当前对象字段缓存仅限总预算内的列。
        var fields = new List<CatalogField>();
        // 全局列计数用于拒绝超额目录，不返回半截数组。
        var fieldCount = 0;
        // 序列化字节计数与最终真实wire格式一致，包括分隔符和对象外壳。
        var bytes = 2;
        // 当前对象只在名称边界完成，避免重复生成大数组。
        CatalogObject? current = null;
        // 驱动读取受总取消信号控制。
        await using var reader = await command.ExecuteReaderAsync(cancellationToken);
        while (await reader.ReadAsync(cancellationToken))
        {
            // 名称仅来自允许Schema与源ACL交集，不用于动态SQL。
            var schema = reader.GetString(0);
            // 同名不同Schema按复合身份分开。
            var name = reader.GetString(1);
            if (current is null || current.Schema != schema || current.Name != name)
            {
                if (current is not null)
                {
                    objects.Add(current with { Fields = fields.ToArray() });
                    fields.Clear();
                }
                if (objects.Count >= 100)
                {
                    throw new PgSourceException("catalog_budget_exceeded");
                }
                current = new CatalogObject { Schema = schema, Name = name, Kind = reader.GetString(2), Fields = [] };
                bytes += JsonSerializer.SerializeToUtf8Bytes(current, G4ConnectionJson.Options).Length + 1;
            }
            // 无可见字段不能把对象包装为完整结构。
            if (reader.IsDBNull(3))
            {
                throw new PgSourceException("catalog_permission_limited");
            }
            if (++fieldCount > 2000)
            {
                throw new PgSourceException("catalog_budget_exceeded");
            }
            // format_type保留numeric修饰、时区、数组和domain原生名称。
            var field = new CatalogField
            {
                Name = reader.GetString(3),
                NativeType = reader.GetString(4),
                Nullable = reader.GetBoolean(5),
                Ordinal = reader.GetInt16(6),
                Precision = reader.IsDBNull(7) ? null : reader.GetInt32(7),
                Scale = reader.IsDBNull(8) ? null : reader.GetInt32(8)
            };
            bytes += JsonSerializer.SerializeToUtf8Bytes(field, G4ConnectionJson.Options).Length + 1;
            if (bytes > 2 * 1024 * 1024)
            {
                throw new PgSourceException("catalog_budget_exceeded");
            }
            fields.Add(field);
        }
        if (current is null)
        {
            throw new PgSourceException("catalog_permission_limited");
        }
        objects.Add(current with { Fields = fields.ToArray() });
        return objects.ToArray();
    }

    /// <summary>仅在当前阶段全部真实操作完成后标记通过并重置阶段时钟。</summary>
    /// <param name="stages">阶段结果数组。</param>
    /// <param name="index">已完成阶段索引。</param>
    /// <param name="clock">单调阶段计时器。</param>
    private static void CompleteStage(ConnectionProbeStage[] stages, int index, Stopwatch clock)
    {
        stages[index] = stages[index] with { Status = "PASS", DurationMs = clock.ElapsedMilliseconds };
        clock.Restart();
    }

    /// <summary>将驱动、TLS和取消异常映射为冻结的机器码，不返回原始消息。</summary>
    /// <param name="exception">仅在当前内存检查的异常。</param>
    /// <param name="stage">实际失败阶段。</param>
    /// <param name="cancelled">是否为调用方明确取消。</param>
    /// <returns>安全白名单错误码。</returns>
    private static string SafeCode(Exception exception, int stage, bool cancelled)
    {
        if (cancelled)
        {
            return "connection_cancelled";
        }
        if (exception is PgSourceException safe)
        {
            return safe.Code;
        }
        if (exception is PostgresException { SqlState: "28P01" or "28000" })
        {
            return "connection_auth_failed";
        }
        if (exception is OperationCanceledException || exception is TimeoutException || exception is NpgsqlException { IsTransient: true })
        {
            return "connection_source_unavailable";
        }
        if (exception is AuthenticationException || exception.InnerException is AuthenticationException || stage == 1)
        {
            return "connection_tls_untrusted";
        }
        if (stage == 4 && exception is PostgresException { SqlState: "42501" })
        {
            return "catalog_permission_limited";
        }
        return stage == 3 ? "connection_readonly_unverified" : "connection_source_unavailable";
    }
}
