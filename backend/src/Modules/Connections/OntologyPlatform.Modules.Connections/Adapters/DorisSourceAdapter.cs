using System.Data.Common;
using System.Diagnostics;
using System.Security.Authentication;
using System.Text.Json;
using MySqlConnector;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>本机Doris固定元数据适配器；不接受自由SQL、外部Catalog或管理员身份。</summary>
public sealed class DorisSourceAdapter : IDorisSourceAdapter
{
    /// <summary>宿主固定的CA文件，构造时冻结。</summary>
    private readonly string rootCertificatePath;

    /// <summary>冻结探测顺序，未观察阶段不伪造成功。</summary>
    private static readonly string[] StageNames = ["NETWORK", "TLS", "AUTH", "READ_ONLY", "METADATA"];

    /// <summary>冻结信任路径，缺配置时拒绝执行。</summary>
    /// <param name="options">仅从服务端注入的信任配置。</param>
    public DorisSourceAdapter(DorisAdapterOptions options)
    {
        rootCertificatePath = options.RootCertificatePath;
    }

    /// <summary>共享十秒期限，认证成功仅证明同一次连接上的网络、TLS和身份。</summary>
    /// <param name="profile">固定合成目标。</param>
    /// <param name="secret">当前调用内存凭据。</param>
    /// <param name="cancellationToken">调用者取消信号。</param>
    /// <returns>独立阶段快照，不受后台清理影响。</returns>
    public async Task<ConnectionProbeStage[]> ProbeAsync(DorisConnectionProfile profile, string secret, CancellationToken cancellationToken)
    {
        Validate(profile, secret);
        // 全部探测共享一份总期限。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(10));
        // 保留每一个未运行阶段，不能以连接成功代替权限和目录验证。
        var stages = StageNames.Select(name => new ConnectionProbeStage { Name = name, Status = "NOT_RUN", DurationMs = 0, DiagnosticCode = null }).ToArray();
        // 单调时间衡量真实调用。
        var clock = Stopwatch.StartNew();
        // 当前失败点仅用于安全阶段分类。
        var stage = 0;
        try
        {
            // 执行器拥有连接及唯一清理期限，不能在外层隐式追加无界Dispose。
            var connection = Create(secret);
            await ExecuteAsync(connection, secret, async current =>
            {
                await current.OpenAsync(deadline.Token);
                for (; stage < 3; stage++) stages[stage] = stages[stage] with { Status = "PASS", DurationMs = stage == 0 ? clock.ElapsedMilliseconds : 0 };
                await VerifyReadOnlyAsync(current);
                stages[stage] = stages[stage] with { Status = "PASS", DurationMs = clock.ElapsedMilliseconds };
                stage++;
                await ReadCatalogAsync(current);
                stages[stage] = stages[stage] with { Status = "PASS", DurationMs = clock.ElapsedMilliseconds };
                return true;
            }, deadline.Token);
        }
        catch (Exception error)
        {
            // 先脱离后台任务持有的数组，再写失败，防止迟到阶段覆盖失败回执。
            var failed = stages.ToArray();
            // 阶段索引也冻结在本次失败投影中。
            var failedStage = stage;
            failed[failedStage] = failed[failedStage] with { Status = "FAIL", DurationMs = clock.ElapsedMilliseconds, DiagnosticCode = SafeCode(error, cancellationToken.IsCancellationRequested) };
            return failed;
        }
        return stages.ToArray();
    }

    /// <summary>每次发现重验有效权限，连接和全部目录读取共同受十秒限制。</summary>
    /// <param name="profile">固定合成目标。</param>
    /// <param name="secret">当前版本内存凭据。</param>
    /// <param name="cancellationToken">会话撤销和任务取消信号。</param>
    /// <returns>有界完整目录。</returns>
    public async Task<CatalogObject[]> DiscoverAsync(DorisConnectionProfile profile, string secret, CancellationToken cancellationToken)
    {
        Validate(profile, secret);
        // 连接、授权和读取不能分别重新获得十秒。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(10));
        try
        {
            // 一次执行器拥有开启、权限与目录的完整生命周期。
            var connection = Create(secret);
            return await ExecuteAsync(connection, secret, async current =>
            {
                await current.OpenAsync(deadline.Token);
                await VerifyReadOnlyAsync(current);
                return await ReadCatalogAsync(current);
            }, deadline.Token);
        }
        catch (Exception error)
        {
            throw new PgSourceException(SafeCode(error, cancellationToken.IsCancellationRequested));
        }
    }

    /// <summary>适配器自身再次验证精确目标和凭据边界，不依赖分发器曾经验证。</summary>
    private void Validate(DorisConnectionProfile profile, string secret)
    {
        DorisAdapterOptions.Validate(profile, new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a"] });
        if (!Path.IsPathFullyQualified(rootCertificatePath)) throw new PgSourceException("connection_tls_untrusted");
        if (string.IsNullOrEmpty(secret) || secret.Length > 16384 || secret.Contains('\0')) throw new PgSourceException("connection_auth_failed");
    }

    /// <summary>固定目标、强制TLS及严格实际握手验证、无连接池并禁止本地文件加载。</summary>
    private MySqlConnection Create(string secret)
    {
        // Builder防止密码被解释为额外连接选项；负取消超时使驱动超时直接关闭连接。
        var builder = new MySqlConnectionStringBuilder
        {
            Server = "localhost",
            Port = 19030,
            UserID = "fixture_reader",
            Password = secret,
            SslMode = MySqlSslMode.Required,
            Pooling = false,
            ConnectionTimeout = 3,
            DefaultCommandTimeout = 0,
            CancellationTimeout = -1,
            AllowLoadLocalInfile = false,
            AllowUserVariables = false
        };
        // Required仅启用驱动公开回调；实际叶证书链、名称和有效期由统一严格策略校验。
        return new MySqlConnection(builder.ConnectionString)
        {
            RemoteCertificateValidationCallback = (_, certificate, chain, errors) => DorisCertificatePolicy.Validate(certificate, chain, errors, rootCertificatePath)
        };
    }

    /// <summary>避免驱动软取消的Doris兼容问题；取消后关闭自己的源连接，禁止其继续被复用。</summary>
    private async Task<T> ExecuteAsync<T>(MySqlConnection connection, string secret, Func<MySqlConnection, Task<T>> operation, CancellationToken token)
    {
        // 执行器唯一拥有连接，工作结束后只创建一次四秒释放窗口。
        Task<T>? pending = null;
        try
        {
            token.ThrowIfCancellationRequested();
            pending = operation(connection);
            return await pending.WaitAsync(token);
        }
        finally
        {
            // 清理独立于工作令牌，成功、异常和取消都使用同一个释放期限。
            using var cleanup = new CancellationTokenSource(TimeSpan.FromSeconds(4));
            // 任何清理失败覆盖成功/取消结论，保持源状态未验证。
            Exception? cleanupFailure = null;
            // 辅助连接手动释放，防止隐式Dispose越过剩余期限。
            MySqlConnection? auxiliary = null;
            try
            {
                if (token.IsCancellationRequested && connection.State == System.Data.ConnectionState.Open)
                {
                    // 数字握手ID只能来自本次源连接；此执行器结束后不会再复用该连接。
                    var sourceId = connection.ServerThread;
                    auxiliary = Create(secret);
                    await auxiliary.OpenAsync(cleanup.Token);
                    // 无驱动软取消；辅助命令两秒硬超时也受整体清理期限约束。
                    using var kill = new MySqlCommand("KILL CONNECTION " + sourceId.ToString(System.Globalization.CultureInfo.InvariantCulture), auxiliary) { CommandTimeout = 2 };
                    // 超时后仍观察辅助命令异常，不能把WaitAsync当成任务终止。
                    var killing = kill.ExecuteNonQueryAsync(CancellationToken.None);
                    try { await killing.WaitAsync(cleanup.Token); }
                    catch
                    {
                        if (!killing.IsCompleted)
                            _ = killing.ContinueWith(task => _ = task.Exception, CancellationToken.None, TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
                        throw;
                    }
                }
            }
            catch (Exception error) { cleanupFailure = error; }
            // 无论辅助连接是否成功，仍尝试关闭本机源连接，但不把关闭当作源端终止证据。
            try { await ReleaseAsync(connection, cleanup.Token); }
            catch (Exception error) { cleanupFailure ??= error; }
            if (auxiliary is not null)
            {
                try { await ReleaseAsync(auxiliary, cleanup.Token); }
                catch (Exception error) { cleanupFailure ??= error; }
            }
            if (pending is not null)
            {
                try { await pending.WaitAsync(cleanup.Token); }
                catch (Exception error)
                {
                    // 工作失败已由上层传播；这里只确认任务终止。清理超时不能丢失后台异常。
                    if (!pending.IsCompleted)
                    {
                        cleanupFailure ??= error;
                        _ = pending.ContinueWith(task => _ = task.Exception, CancellationToken.None, TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
                    }
                }
            }
            if (cleanupFailure is not null) throw new PgSourceException("connection_source_unavailable");
        }
    }

    /// <summary>释放受同一剩余期限约束，超时任务仍观察异常，不声称WaitAsync能终止驱动。</summary>
    private static async Task ReleaseAsync(MySqlConnection connection, CancellationToken token)
    {
        // 只创建一次真实释放任务，超时不重复释放同一连接。
        var release = connection.DisposeAsync().AsTask();
        try { await release.WaitAsync(token); }
        catch
        {
            if (!release.IsCompleted)
                _ = release.ContinueWith(task => _ = task.Exception, CancellationToken.None, TaskContinuationOptions.OnlyOnFaulted | TaskContinuationOptions.ExecuteSynchronously, TaskScheduler.Default);
            throw;
        }
    }

    /// <summary>拒绝角色继承、全局权限和任何写授权；只接受固定三项数据库SELECT及默认工作负载使用权。</summary>
    private static async Task<bool> VerifyReadOnlyAsync(MySqlConnection connection)
    {
        // SHOW GRANTS查询当前认证身份，不带用户输入。
        await using var command = new MySqlCommand("SHOW GRANTS", connection);
        // 结果流由当前工作任务拥有，其终止受执行器总期限控制。
        await using var reader = await command.ExecuteReaderAsync();
        if (!await reader.ReadAsync()) throw new PgSourceException("connection_readonly_unverified");
        ValidateGrantRow(reader);
        if (await reader.ReadAsync()) throw new PgSourceException("connection_readonly_unverified");
        return true;
    }

    /// <summary>验证当前权限行的全部列和值，便于直接覆盖未知格式和管理员权限负例。</summary>
    /// <param name="reader">已经定位到当前行的实际结果读取器。</param>
    private static void ValidateGrantRow(DbDataReader reader)
    {
        // 白名单覆盖实际版本全部列，未知权限列也不能默认为安全。
        var expected = new Dictionary<string, string>(StringComparer.Ordinal)
        {
            ["UserIdentity"] = "'fixture_reader'@'%'",
            ["Password"] = "Yes",
            ["Comment"] = "",
            ["RequireSan"] = "",
            ["Roles"] = "",
            ["GlobalPrivs"] = "",
            ["CatalogPrivs"] = "",
            ["DatabasePrivs"] = "internal.fixture: Select_priv; internal.information_schema: Select_priv; internal.mysql: Select_priv",
            ["TablePrivs"] = "",
            ["ColPrivs"] = "",
            ["ResourcePrivs"] = "",
            ["CloudClusterPrivs"] = "",
            ["CloudStagePrivs"] = "",
            ["StorageVaultPrivs"] = "",
            ["WorkloadGroupPrivs"] = "normal: Usage_priv",
            ["ComputeGroupPrivs"] = ""
        };
        if (reader.FieldCount != expected.Count) throw new PgSourceException("connection_readonly_unverified");
        // 逐列核对完整权限形态，未知列不能静默忽略。
        for (var index = 0; index < reader.FieldCount; index++)
        {
            if (!expected.TryGetValue(reader.GetName(index), out var value) || Convert.ToString(reader.GetValue(index)) != value)
                throw new PgSourceException("connection_readonly_unverified");
        }
    }

    /// <summary>固定internal信息表交集，最大一百对象、两千字段、二MiB；不读取业务行。</summary>
    private static async Task<CatalogObject[]> ReadCatalogAsync(MySqlConnection connection)
    {
        // 固定schema且不切换catalog；连接默认internal，不访问外部连接器。
        const string sql = "SELECT c.TABLE_NAME,t.TABLE_TYPE,c.COLUMN_NAME,c.COLUMN_TYPE,c.IS_NULLABLE,c.ORDINAL_POSITION,c.NUMERIC_PRECISION,c.NUMERIC_SCALE FROM information_schema.COLUMNS c JOIN information_schema.TABLES t ON c.TABLE_SCHEMA=t.TABLE_SCHEMA AND c.TABLE_NAME=t.TABLE_NAME WHERE c.TABLE_SCHEMA='fixture' ORDER BY c.TABLE_NAME,c.ORDINAL_POSITION LIMIT 2001";
        // 只执行上面的固定元数据SQL。
        await using var command = new MySqlCommand(sql, connection);
        // 结果流由当前工作任务拥有，其终止受执行器总期限控制。
        await using var reader = await command.ExecuteReaderAsync();
        return await ReadCatalogRowsAsync(reader);
    }

    /// <summary>实际流式目录解析及总预算检查，超限只抛异常而不返回部分结果。</summary>
    /// <param name="reader">固定元数据SQL的结果流。</param>
    /// <returns>预算内的完整目录。</returns>
    private static async Task<CatalogObject[]> ReadCatalogRowsAsync(DbDataReader reader)
    {
        // 有界暂存仅用于完整快照，超过预算绝不返回截断目录。
        var objects = new Dictionary<string, (string Kind, List<CatalogField> Fields)>(StringComparer.Ordinal);
        // 字段总数防止单表绕过对象限额。
        var count = 0;
        // 逐字段累加序列化字节，在全量物化前提前止损。
        var bytes = 0;
        while (await reader.ReadAsync())
        {
            if (++count > 2000) throw new PgSourceException("catalog_budget_exceeded");
            // 源名称只作为返回元数据，不参与拼接SQL。
            var name = reader.GetString(0);
            // Doris表与视图类型必须明确，未知类型不伪装成表。
            var kind = reader.GetString(1) switch { "BASE TABLE" => "TABLE", "VIEW" => "VIEW", _ => throw new PgSourceException("catalog_permission_limited") };
            if (!objects.TryGetValue(name, out var entry))
            {
                if (objects.Count >= 100) throw new PgSourceException("catalog_budget_exceeded");
                entry = (kind, []);
                objects.Add(name, entry);
            }
            // 保留原生类型及精度，不推断业务含义。
            var field = new CatalogField { Name = reader.GetString(2), NativeType = reader.GetString(3), Nullable = reader.GetString(4) == "YES", Ordinal = Convert.ToInt32(reader.GetValue(5)), Precision = reader.IsDBNull(6) ? null : Convert.ToInt32(reader.GetValue(6)), Scale = reader.IsDBNull(7) ? null : Convert.ToInt32(reader.GetValue(7)) };
            bytes += JsonSerializer.SerializeToUtf8Bytes(field).Length;
            if (bytes > 2 * 1024 * 1024) throw new PgSourceException("catalog_budget_exceeded");
            entry.Fields.Add(field);
        }
        if (objects.Count == 0) throw new PgSourceException("catalog_permission_limited");
        // 最终包括对象名称与结构开销，再次精确检查响应预算。
        var result = objects.Select(pair => new CatalogObject { Schema = "fixture", Name = pair.Key, Kind = pair.Value.Kind, Fields = pair.Value.Fields.ToArray() }).ToArray();
        if (JsonSerializer.SerializeToUtf8Bytes(result).Length > 2 * 1024 * 1024) throw new PgSourceException("catalog_budget_exceeded");
        return result;
    }

    /// <summary>复用现有安全异常合同，任何原始SQL、地址和驱动异常都不跨边界。</summary>
    private static string SafeCode(Exception error, bool cancelled)
    {
        if (error is PgSourceException known) return known.Code;
        if (cancelled && error is OperationCanceledException) return "connection_cancelled";
        // 只识别标准TLS异常类型，不返回证书或网络诊断正文。
        for (var current = error; current is not null; current = current.InnerException)
            if (current is AuthenticationException) return "connection_tls_untrusted";
        if (error is MySqlException { ErrorCode: MySqlErrorCode.AccessDenied }) return "connection_auth_failed";
        return "connection_source_unavailable";
    }
}
