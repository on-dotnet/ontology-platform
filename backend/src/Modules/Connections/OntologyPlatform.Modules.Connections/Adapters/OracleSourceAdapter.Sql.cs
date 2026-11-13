using System.Data.Common;
using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using Oracle.ManagedDataAccess.Client;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>固定Oracle字典查询、只读证明与类型表达；不接收用户SQL。</summary>
public sealed partial class OracleSourceAdapter
{
    /// <summary>只投影列结构；不读默认值、统计值或业务行，额外一行用于预算拒绝。</summary>
    private const string CatalogSql = """
        SELECT c.OWNER, c.TABLE_NAME,
               CASE WHEN EXISTS (SELECT 1 FROM ALL_VIEWS v WHERE v.OWNER=c.OWNER AND v.VIEW_NAME=c.TABLE_NAME) THEN 'VIEW' ELSE 'TABLE' END,
               c.COLUMN_NAME, c.DATA_TYPE, c.NULLABLE, c.COLUMN_ID, c.DATA_PRECISION, c.DATA_SCALE,
               c.DATA_LENGTH, c.CHAR_LENGTH, c.CHAR_USED, c.DATA_TYPE_OWNER
        FROM ALL_TAB_COLUMNS c
        WHERE c.OWNER IN ('PRODUCTION','CaseOwner')
          AND (EXISTS (SELECT 1 FROM ALL_TABLES t WHERE t.OWNER=c.OWNER AND t.TABLE_NAME=c.TABLE_NAME)
            OR EXISTS (SELECT 1 FROM ALL_VIEWS v WHERE v.OWNER=c.OWNER AND v.VIEW_NAME=c.TABLE_NAME))
        ORDER BY c.OWNER, c.TABLE_NAME, c.COLUMN_ID
        FETCH FIRST 2001 ROWS ONLY
        """;

    /// <summary>在当前物理会话核对PDB、用户、TCPS及直接/继承权限和控制面证明。</summary>
    /// <param name="connection">本次唯一已打开的物理连接。</param>
    /// <param name="token">与整个操作共用的取消令牌。</param>
    private static async Task VerifyReadOnlyAsync(OracleConnection connection, CancellationToken token)
    {
        // 认证身份、PDB和实际协议来自当前会话，不相信连接串自报。
        using var identity = connection.CreateCommand();
        identity.CommandText = "SELECT SYS_CONTEXT('USERENV','SESSION_USER'), SYS_CONTEXT('USERENV','CON_NAME'), SYS_CONTEXT('USERENV','NETWORK_PROTOCOL') FROM DUAL";
        identity.CommandTimeout = 5;
        await using (var reader = await identity.ExecuteReaderAsync(token))
        {
            if (!await reader.ReadAsync(token) || reader.GetString(0) != "FIXTURE_READER"
                || reader.GetString(1) != "FREEPDB1" || !reader.GetString(2).Equals("tcps", StringComparison.OrdinalIgnoreCase))
                throw new PgSourceException("connection_readonly_unverified");
        }
        // 当前有效系统权限只能有CREATE SESSION，角色/自有对象会产生未审能力。
        using var privileges = connection.CreateCommand();
        privileges.CommandText = """
            SELECT
              (SELECT COUNT(*) FROM SESSION_PRIVS WHERE PRIVILEGE <> 'CREATE SESSION') +
              (SELECT COUNT(*) FROM SESSION_ROLES) +
              (SELECT COUNT(*) FROM USER_ROLE_PRIVS) +
              (SELECT COUNT(*) FROM USER_OBJECTS) +
              (SELECT COUNT(*) FROM USER_COL_PRIVS_RECD) +
              (SELECT COUNT(*) FROM USER_SYS_PRIVS WHERE PRIVILEGE <> 'CREATE SESSION' OR ADMIN_OPTION <> 'NO') +
              (SELECT COUNT(*) FROM USER_TAB_PRIVS_RECD WHERE PRIVILEGE <> 'READ' OR GRANTABLE <> 'NO'
                OR NOT (OWNER IN ('PRODUCTION','CaseOwner') OR (OWNER='G4_CONTROL' AND TABLE_NAME='READONLY_ATTESTATION')))
            FROM DUAL
            """;
        privileges.CommandTimeout = 5;
        if (Convert.ToInt32(await privileges.ExecuteScalarAsync(token), CultureInfo.InvariantCulture) != 0)
            throw new PgSourceException("connection_readonly_unverified");
        // 管理面窄视图检查PUBLIC和无法向reader开放的字典；它只给计数，不授广域字典权。
        using var attestation = connection.CreateCommand();
        attestation.CommandText = "SELECT POLICY_VERSION, BLOCKED_COUNT FROM G4_CONTROL.READONLY_ATTESTATION";
        attestation.CommandTimeout = 5;
        await using var proof = await attestation.ExecuteReaderAsync(token);
        if (!await proof.ReadAsync(token) || proof.GetString(0) != "oracle-readonly-v1"
            || Convert.ToInt32(proof.GetValue(1), CultureInfo.InvariantCulture) != 0 || await proof.ReadAsync(token))
            throw new PgSourceException("connection_readonly_unverified");
    }

    /// <summary>读取固定owner交集，两个批准owner都必须有可见对象。</summary>
    /// <param name="connection">当前已验证权限的连接。</param>
    /// <param name="token">调用方和总期限共同控制的取消令牌。</param>
    /// <returns>完整有界目录。</returns>
    private static async Task<CatalogObject[]> ReadCatalogAsync(OracleConnection connection, CancellationToken token)
    {
        // 固定SQL不插入配置中的标识符或其它用户文本。
        using var command = connection.CreateCommand();
        command.CommandText = CatalogSql;
        command.CommandTimeout = 10;
        await using var reader = await command.ExecuteReaderAsync(token);
        // 同一reader按预算消费，不先整表物化再截断。
        var result = await ReadCatalogRowsAsync(reader, token);
        if (!result.Any(value => value.Schema == "PRODUCTION") || !result.Any(value => value.Schema == "CaseOwner"))
            throw new PgSourceException("catalog_permission_limited");
        return result;
    }

    /// <summary>保留字典原名、原生类型和null，未知类型不发布完整可信目录。</summary>
    /// <param name="reader">与固定字典SQL同序的十三列。</param>
    /// <param name="token">读取取消令牌。</param>
    /// <returns>最多100对象、2000列、2MiB的完整目录。</returns>
    private static async Task<CatalogObject[]> ReadCatalogRowsAsync(DbDataReader reader, CancellationToken token)
    {
        // 元组按Ordinal字符串相等比较，不改变quoted标识符大小写。
        var objects = new Dictionary<(string Owner, string Name, string Kind), List<CatalogField>>();
        // 整个结果共享列预算，而非每个表重新计数。
        var columns = 0;
        token.ThrowIfCancellationRequested();
        while (await reader.ReadAsync(token))
        {
            // 元组顺序与SELECT前三列一致。
            var key = (Owner: reader.GetString(0), Name: reader.GetString(1), Kind: reader.GetString(2));
            if (key.Owner is not ("PRODUCTION" or "CaseOwner") || key.Kind is not ("TABLE" or "VIEW"))
                throw new PgSourceException("catalog_access_forbidden");
            if (++columns > 2000) throw new PgSourceException("catalog_budget_exceeded");
            if (!objects.TryGetValue(key, out var fields))
            {
                if (objects.Count == 100) throw new PgSourceException("catalog_budget_exceeded");
                fields = [];
                objects.Add(key, fields);
            }
            // DATA_TYPE包含Oracle的TIMESTAMP精度与时区后缀，不转换成通用datetime。
            var native = reader.GetString(4);
            // 类型分类只针对固定已覆盖集合，未知类型不会默认为字符串。
            var timestamp = Regex.Match(native, @"^TIMESTAMP(?:\((\d)\))?( WITH (?:LOCAL )?TIME ZONE)?$", RegexOptions.CultureInvariant);
            // LOB只描述类型，不读取值；用户定义类型不能当作内置类型。
            var supported = native is "NUMBER" or "FLOAT" or "BINARY_FLOAT" or "BINARY_DOUBLE" or "DATE" or "CHAR" or "NCHAR" or "VARCHAR2" or "NVARCHAR2" or "RAW" || timestamp.Success;
            // LOB保留元数据但不承诺值读取。
            var metadataOnly = native is "CLOB" or "NCLOB" or "BLOB" or "BFILE" or "LONG" or "LONG RAW";
            if ((!supported && !metadataOnly) || !reader.IsDBNull(12)) throw new PgSourceException("catalog_permission_limited");
            // 缺失CHAR_USED不是BYTE；字典B/C精确转换为冻结合同。
            var semantics = reader.IsDBNull(11) ? null : reader.GetString(11) switch { "B" => "BYTE", "C" => "CHAR", _ => throw new PgSourceException("catalog_permission_limited") };
            fields.Add(new CatalogField
            {
                Name = reader.GetString(3), NativeType = native, Nullable = reader.GetString(5) == "Y",
                Ordinal = Number(reader, 6) ?? throw new PgSourceException("catalog_permission_limited"),
                Precision = Number(reader, 7), Scale = Number(reader, 8),
                OracleMetadata = new OracleColumnMetadata
                {
                    DataTypeOwner = null, ByteLength = Number(reader, 9), CharLength = Number(reader, 10), CharSemantics = semantics,
                    FractionalSecondsPrecision = timestamp.Success ? (timestamp.Groups[1].Success ? int.Parse(timestamp.Groups[1].Value, CultureInfo.InvariantCulture) : Number(reader, 8)) : null,
                    TimeZoneKind = native.EndsWith(" WITH LOCAL TIME ZONE", StringComparison.Ordinal) ? "WITH_LOCAL_TIME_ZONE"
                        : native.EndsWith(" WITH TIME ZONE", StringComparison.Ordinal) ? "WITH_TIME_ZONE" : "NONE",
                    SupportStatus = metadataOnly ? "METADATA_ONLY" : "SUPPORTED"
                }
            });
        }
        if (objects.Count == 0) throw new PgSourceException("catalog_permission_limited");
        // 排序和字节预算作用于最终公开DTO，不能忽略新增Oracle元数据开销。
        var result = objects.Select(value => new CatalogObject { Schema = value.Key.Owner, Name = value.Key.Name, Kind = value.Key.Kind, Fields = value.Value.ToArray() }).ToArray();
        if (JsonSerializer.SerializeToUtf8Bytes(result, G4ConnectionJson.Options).Length > 2 * 1024 * 1024)
            throw new PgSourceException("catalog_budget_exceeded");
        return result;
    }

    /// <summary>数据库NUMBER整数投影不假设驱动总返回Int32，NULL保持未知。</summary>
    /// <param name="reader">当前行。</param>
    /// <param name="ordinal">固定列序号。</param>
    /// <returns>有界整数或null。</returns>
    private static int? Number(DbDataReader reader, int ordinal) => reader.IsDBNull(ordinal) ? null : Convert.ToInt32(reader.GetValue(ordinal), CultureInfo.InvariantCulture);
}
