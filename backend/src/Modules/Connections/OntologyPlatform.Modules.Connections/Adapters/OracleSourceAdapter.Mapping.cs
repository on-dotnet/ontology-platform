using System.Data;
using Oracle.ManagedDataAccess.Client;

[assembly: System.Runtime.CompilerServices.InternalsVisibleTo("OntologyPlatform.ConnectionsTests")]

namespace OntologyPlatform.Modules.Connections;

/// <summary>Oracle 业务切片使用新物理连接、显式只读事务和固定的有界投影。</summary>
public sealed partial class OracleSourceAdapter
{
    /// <summary>在业务事务外验证信任与当前直接读取范围，交给调用者管理同一物理连接。</summary>
    /// <param name="secret">本任务读者的内存口令。</param>
    /// <param name="executionId">独占的源执行身份。</param>
    /// <param name="token">调用者原期限令牌。</param>
    /// <returns>完成实际 TCPS、当前权限及对象核验的非池化连接。</returns>
    internal async Task<OracleConnection> OpenMappingAsync(string secret, Guid executionId, CancellationToken token)
    {
        await VerifyTlsAsync(token);
        // 连接配置沿用固定端点、可信钱包及零重试。
        var connection = Create(secret);
        try
        {
            await connection.OpenAsync(token);
            connection.ModuleName = "G4-ORACLE-MAPPING-QUERY-001";
            connection.ClientId = executionId.ToString("N");
            await VerifyMappingAccessAsync(connection, token);
            return connection;
        }
        catch
        {
            await connection.DisposeAsync();
            throw;
        }
    }

    /// <summary>在当前独占物理会话复核只读身份与准确三项直接授权。</summary>
    internal static async Task VerifyMappingAccessAsync(OracleConnection connection, CancellationToken token)
    {
        await VerifyReadOnlyAsync(connection, token);
        // 直接授予的可读闭包须准确匹配两表和证明视图。
        using var grants = connection.CreateCommand();
        grants.CommandText = """
            SELECT OWNER, TABLE_NAME FROM USER_TAB_PRIVS_RECD
            WHERE PRIVILEGE='READ' AND GRANTABLE='NO' ORDER BY OWNER,TABLE_NAME
            """;
        // 集合采用 Oracle 目录原始标识符，不折叠大小写。
        var objects = new HashSet<(string, string)>();
        await using var cursor = await grants.ExecuteReaderAsync(token);
        while (await cursor.ReadAsync(token))
            objects.Add((cursor.GetString(0), cursor.GetString(1)));
        if (!objects.SetEquals([("PRODUCTION", "OMQ_ENTITY"), ("CaseOwner", "OmqTarget"), ("G4_CONTROL", "READONLY_ATTESTATION")]))
            throw new PgSourceException("connection_readonly_unverified");
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
        var transaction = (OracleTransaction)await connection.BeginTransactionAsync(IsolationLevel.ReadCommitted, token);
        try
        {
            using var mode = connection.CreateCommand();
            mode.Transaction = transaction;
            mode.CommandText = "SET TRANSACTION READ ONLY";
            await mode.ExecuteNonQueryAsync(token);
            return transaction;
        }
        catch
        {
            await transaction.DisposeAsync();
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
    /// <returns>真实读取的有界行集。</returns>
    internal static async Task<List<OracleMappingRow>> ConsumeMappingAsync(OracleCommand command, CancellationToken token)
    {
        // 原生驱动游标在离开事务之前释放。
        await using var cursor = await command.ExecuteReaderAsync(token);
        // 只保存固定查询实际返回的行；第 101 行留给调用方的超量分类。
        var rows = new List<OracleMappingRow>();
        while (await cursor.ReadAsync(token))
        {
            rows.Add(new(cursor.GetInt64(0), cursor.IsDBNull(1) ? null : cursor.GetDecimal(1),
                cursor.IsDBNull(2) ? null : cursor.GetDecimal(2), cursor.GetString(3), cursor.GetString(4),
                cursor.GetString(5), cursor.IsDBNull(6) ? null : cursor.GetString(6), cursor.GetDateTime(7),
                cursor.GetDateTime(8), cursor.GetDateTime(9), cursor.GetDateTime(10)));
        }
        return rows;
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
