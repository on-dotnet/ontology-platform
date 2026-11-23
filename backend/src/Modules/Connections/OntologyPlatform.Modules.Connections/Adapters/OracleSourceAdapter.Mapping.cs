using System.Data;
using System.Data.Common;
using Microsoft.Extensions.Logging;
using OntologyPlatform.Contracts;
using Oracle.ManagedDataAccess.Client;

[assembly: System.Runtime.CompilerServices.InternalsVisibleTo("OntologyPlatform.ConnectionsTests")]

namespace OntologyPlatform.Modules.Connections;

/// <summary>Oracle 业务切片使用新物理连接、显式只读事务和固定的有界投影。</summary>
public sealed partial class OracleSourceAdapter
{
    /// <summary>仅记录当前正式源调用的已知事件及身份，避免记录查询正文、行或异常原文。</summary>
    internal void QueryEvent(string action, G4OracleSourceLifetime lifetime)
    {
        if (action is not ("EXECUTE" or "CANCEL_ENTER" or "CANCEL_RETURN" or "CANCEL_REJECT" or "NATIVE_1013" or "EOF" or "PHYSICAL_RELEASE"))
            throw new ArgumentOutOfRangeException(nameof(action));
        G4OracleQueryTrace.Mark(action, "returned");
        logger?.LogInformation("OracleSourceEvent action={Action} query={QueryId} execution={ExecutionId} utc={Utc:O}",
            action, lifetime.QueryId, lifetime.ExecutionId, DateTimeOffset.UtcNow);
    }

    /// <summary>在准确源申请上记录已到达的驱动生命周期边界；不记录来源数据和凭据。</summary>
    internal void QueryOwnership(string phase, G4OracleSourceLifetime lifetime, Guid acquisition) =>
        logger?.LogInformation("OracleSourceOwnership phase={Phase} query={QueryId} execution={ExecutionId} acquisition={Acquisition:N} utc={Utc:O}",
            phase, lifetime.QueryId, lifetime.ExecutionId, acquisition, DateTimeOffset.UtcNow);

    /// <summary>记录源清理的保守 UTC 截止及单调剩余刻度；原始业务数据不参与观察。</summary>
    internal void QueryCleanup(G4OracleSourceLifetime lifetime, OracleQueryReader.CleanupObservation point) =>
        logger?.LogInformation("OracleSourceCleanup trigger={Trigger} query={QueryId} execution={ExecutionId} acquisition={Acquisition:N} utc={Utc:O} deadlineUtc={DeadlineUtc:O} remainingTicks={RemainingTicks}",
            point.Trigger, lifetime.QueryId, lifetime.ExecutionId, point.Acquisition, point.Utc, point.DeadlineUtc, point.RemainingTicks);

    /// <summary>原生取消必须来自该次业务 Execute 或 Read，不能将普通请求取消扩大为源端因果。</summary>
    internal static bool IsNativeCancel(Exception failure) => failure is OracleException { Number: 1013 }
        or OperationCanceledException { InnerException: OracleException { Number: 1013 } };

    /// <summary>在真实读者会话将统一审计身份、传统审计身份及 SID 绑定到本次 ClientId。</summary>
    internal async Task RecordQuerySessionAsync(OracleConnection connection, G4OracleSourceLifetime lifetime, CancellationToken token)
    {
        // SYS_CONTEXT 只返回本会话，不增加业务账号的字典权限。
        using var identity = connection.CreateCommand();
        identity.CommandText = """
            SELECT SYS_CONTEXT('USERENV','CLIENT_IDENTIFIER'),SYS_CONTEXT('USERENV','INSTANCE'),
                   SYS_CONTEXT('USERENV','SID'),SYS_CONTEXT('USERENV','SESSIONID'),SYS_CONTEXT('USERENV','UNIFIED_AUDIT_SESSIONID'),
                   SYS_CONTEXT('USERENV','CON_ID') FROM DUAL
            """;
        // 原始数字来自自己的物理连接；不同审计体系的编号分别保留。
        await using var row = await identity.ExecuteReaderAsync(token);
        if (!await row.ReadAsync(token) || row.GetString(0) != lifetime.ClientId) throw new PgSourceException("connection_readonly_unverified");
        // 来源标记仅接受无符号数字，不允许其它会话内容写进日志。
        var ids = new ulong[5];
        for (var i = 0; i < ids.Length; i++)
            if (row.IsDBNull(i + 1) || !ulong.TryParse(row.GetString(i + 1), System.Globalization.NumberStyles.None,
                    System.Globalization.CultureInfo.InvariantCulture, out ids[i]) || ids[i] == 0)
                throw new PgSourceException("connection_readonly_unverified");
        G4OracleQueryTrace.Mark("session", "returned", session: ids);
        logger?.LogInformation("OracleSourceSession query={QueryId} execution={ExecutionId} instance={Instance} sid={Sid} audsid={Audsid} unified={Unified} con={Con} utc={Utc:O}",
            lifetime.QueryId, lifetime.ExecutionId, ids[0], ids[1], ids[2], ids[3], ids[4], DateTimeOffset.UtcNow);
    }

    /// <summary>在业务事务外验证信任并打开物理连接；Mapping先核直接读取范围，Query取得所有权后核验。</summary>
    /// <param name="secret">本任务读者的内存口令。</param>
    /// <param name="executionId">独占的源执行身份。</param>
    /// <param name="token">调用者原期限令牌。</param>
    /// <param name="verifyAccess">Mapping默认在返回前核权；Query在取得所有权后单独核验同一连接。</param>
    /// <returns>完成实际 TCPS的非池化连接；默认还包含当前权限及对象核验。</returns>
    internal async Task<OracleConnection> OpenMappingAsync(string secret, Guid executionId, CancellationToken token, bool verifyAccess = true)
    {
        await G4OracleQueryTrace.ObserveAsync("permitCheck", () => G4OracleSourceOpen.BeforePhysicalOpenAsync(token));
        await G4OracleQueryTrace.ObserveAsync("tls", () => VerifyTlsAsync(token));
        // 连接配置沿用固定端点、可信钱包及零重试。
        var connection = Create(secret);
        try
        {
            await G4OracleQueryTrace.ObserveAsync("openCheck", () => G4OracleSourceOpen.BeforeSessionOpenAsync(token));
            await G4OracleQueryTrace.ObserveAsync("open", () => connection.OpenAsync(token));
            await G4OracleQueryTrace.ObserveAsync("permitReturn", () => G4OracleSourceOpen.AfterPhysicalOpenAsync().AsTask());
            await G4OracleQueryTrace.ObserveAsync("sessionTag", () =>
            {
                connection.ModuleName = "G4-ORACLE-MAPPING-QUERY-001";
                connection.ClientId = executionId.ToString("N");
                return Task.CompletedTask;
            });
            if (verifyAccess) await VerifyMappingAccessAsync(connection, token);
            return connection;
        }
        catch
        {
            await G4OracleQueryTrace.ObserveAsync("disposeConnection", () => connection.DisposeAsync().AsTask());
            throw;
        }
    }

    /// <summary>在当前独占物理会话复核只读身份与准确三项直接授权。</summary>
    internal static async Task VerifyMappingAccessAsync(OracleConnection connection, CancellationToken token, bool post = false)
    {
        if (!await MappingAccessMatchesAsync(connection, token, post))
            throw new PgSourceException("connection_readonly_unverified");
    }

    /// <summary>完整读取并释放权限元数据后才返回匹配结论；取消或资源异常不能伪装成明确拒绝。</summary>
    internal static async Task<bool> MappingAccessMatchesAsync(OracleConnection connection, CancellationToken token, bool post = false)
    {
        token.ThrowIfCancellationRequested();
        if (!await ReadOnlyPolicyMatchesAsync(connection, token, post)) return false;
        // 直接授予的可读闭包须准确匹配两表和证明视图。
        return await OracleMetadataCommand.RunAsync(connection, "directRead", post, async grantsCost =>
        {
            // 保留生产命令的原 SQL 及超时。
            var grants = grantsCost.Command;
            grants.CommandText = """
                SELECT OWNER, TABLE_NAME FROM USER_TAB_PRIVS_RECD
                WHERE PRIVILEGE='READ' AND GRANTABLE='NO' ORDER BY OWNER,TABLE_NAME
                """;
            // 集合采用 Oracle 目录原始标识符，不折叠大小写。
            var objects = new HashSet<(string, string)>();
            token.ThrowIfCancellationRequested();
            return await grantsCost.WithReaderAsync(token, async cursor =>
            {
                while (await OracleMetadataCommand.ReadAsync(cursor, token))
                    objects.Add((cursor.GetString(0), cursor.GetString(1)));
                return objects.SetEquals([("PRODUCTION", "OMQ_ENTITY"), ("CaseOwner", "OmqTarget"), ("G4_CONTROL", "READONLY_ATTESTATION")]);
            });
        });
    }

    /// <summary>所有前置核验已结束，在该连接显式建立本地事务并立即发出只读声明。</summary>
    /// <param name="connection">本分支专属的已核非池化物理连接。</param>
    /// <param name="token">贯穿全部业务游标和清理的上游令牌。</param>
    /// <returns>调用者须在消费全部游标后完成的真实事务。</returns>
    internal static async Task<OracleTransaction> BeginMappingAsync(OracleConnection connection, CancellationToken token)
    {
        // 仅在当前会话的事务外关闭自动提交。
        connection.AutoCommit = false;
        // 明确让驱动创建本地事务，再发出第一行业务 SQL。
        var transaction = (OracleTransaction)await G4OracleQueryTrace.ObserveAsync("transaction", () => connection.BeginTransactionAsync(IsolationLevel.ReadCommitted, token).AsTask());
        try
        {
            using var mode = connection.CreateCommand();
            mode.Transaction = transaction;
            mode.CommandText = "SET TRANSACTION READ ONLY";
            await G4OracleQueryTrace.ObserveAsync("declareReadOnly", () => mode.ExecuteNonQueryAsync(token));
            return transaction;
        }
        catch
        {
            await G4OracleQueryTrace.ObserveAsync("disposeTransaction", () => transaction.DisposeAsync().AsTask());
            throw;
        }
    }

    /// <summary>业务事务内只读两张已冻结表之一，按主键取至多 101 行。</summary>
    /// <param name="connection">本次唯一物理连接。</param>
    /// <param name="transaction">覆盖整条分支的真实只读事务。</param>
    /// <param name="target">选择固定目标表或固定实体表。</param>
    /// <param name="token">调用方的原有期限。</param>
    /// <returns>原生 decimal 和微秒时间精度的有界投影。</returns>
    internal static async Task<List<OracleMappingRow>> ReadMappingAsync(OracleConnection connection,
        OracleTransaction transaction, bool target, CancellationToken token)
    {
        // 命令与所有取行由同一个调用者拥有并顺序释放。
        using var command = CreateMappingCommand(connection, transaction, target);
        return await ConsumeMappingAsync(command, token);
    }

    /// <summary>由业务分支持有准确命令，取消定向到同一连接的同一次在途调用。</summary>
    /// <param name="connection">已核物理连接。</param>
    /// <param name="transaction">固定业务事务。</param>
    /// <param name="target">选择冻结的物理表。</param>
    /// <returns>尚未发送的固定命令。</returns>
    internal static OracleCommand CreateMappingCommand(OracleConnection connection, OracleTransaction transaction, bool target)
    {
        // 投影、对象、排序和行数均取自固定合同，不接收调用者文本。
        var command = connection.CreateCommand();
        command.Transaction = transaction;
        const string projection = "SELECT ROW_ID,JOIN_KEY,VAL,ORG_ID,SITE_ID,EXT_ID,LABEL,FROM_TS,TO_TS,EVENT_TS,OBSERVED_TS FROM ";
        command.CommandText = projection + (target ? "\"CaseOwner\".\"OmqTarget\"" : "\"PRODUCTION\".\"OMQ_ENTITY\"")
            + " ORDER BY ROW_ID FETCH FIRST 101 ROWS ONLY";
        return command;
    }

    /// <summary>执行准确命令并消费及释放该次游标，保留 Oracle 原生数据类型。</summary>
    /// <param name="command">本次分支独占的固定业务命令。</param>
    /// <param name="token">分支原始预算。</param>
    /// <param name="completed">仅在驱动游标实际读到末尾后发送的无业务值通知。</param>
    /// <param name="native">仅标记业务执行或取行中收到的准确原生 1013；游标释放异常不在此范围。</param>
    /// <returns>真实读取并已释放游标的有界行集。</returns>
    internal static async Task<List<OracleMappingRow>> ConsumeMappingAsync(OracleCommand command, CancellationToken token,
        Action? completed = null, Action<Exception>? native = null)
    {
        // 外层按异常实例区分原生取行取消与游标 Dispose 后来报告的错误。
        DbDataReader? cursor = null;
        // 只保存真实返回的行，第 101 行供上层判定超量。
        var rows = new List<OracleMappingRow>();
        try
        {
            try
            {
                token.ThrowIfCancellationRequested();
                cursor = await command.ExecuteReaderAsync(token);
                while (await cursor.ReadAsync(token))
                {
                    rows.Add(new(cursor.GetInt64(0), cursor.IsDBNull(1) ? null : cursor.GetDecimal(1),
                        cursor.IsDBNull(2) ? null : cursor.GetDecimal(2), cursor.GetString(3), cursor.GetString(4),
                        cursor.GetString(5), cursor.IsDBNull(6) ? null : cursor.GetString(6), cursor.GetDateTime(7),
                        cursor.GetDateTime(8), cursor.GetDateTime(9), cursor.GetDateTime(10)));
                }
            }
            catch (Exception error) when (IsNativeCancel(error))
            {
                native?.Invoke(error);
                throw;
            }
            completed?.Invoke();
            return rows;
        }
        finally
        {
            if (cursor is not null) await cursor.DisposeAsync();
        }
    }
}

/// <summary>两个明确物理对象所用的内部读取投影，供已核类型的固定查询使用。</summary>
/// <param name="Id">稳定主键。</param>
/// <param name="JoinKey">可空等值关系键。</param>
/// <param name="Value">最多二十八位的源十进制数。</param>
/// <param name="Organization">组织身份。</param>
/// <param name="Site">厂区身份。</param>
/// <param name="External">合成外部键。</param>
/// <param name="Label">合成显示值。</param>
/// <param name="From">有效期左端。</param>
/// <param name="To">有效期右端。</param>
/// <param name="Event">源事件时间。</param>
/// <param name="Observed">源观察时间。</param>
internal sealed record OracleMappingRow(long Id, decimal? JoinKey, decimal? Value, string Organization, string Site,
    string External, string? Label, DateTime From, DateTime To, DateTime Event, DateTime Observed);
