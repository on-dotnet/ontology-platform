using MySqlConnector;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>用 Doris 4.0.8 的实际建表语句核对合成源的物理模型、列和完整键序。</summary>
internal static class DorisMappingSourceValidator
{
    /// <summary>读取本分支表的当前形状，所有命令由外层无池分支统一限时和取消。</summary>
    internal static async Task CheckTableAsync(MySqlConnection connection, bool target)
    {
        // 表名来自封闭的两表集合。
        var table = target ? "dmq_target" : "dmq_entity";
        await using var command = new MySqlCommand("SHOW CREATE TABLE fixture." + table, connection);
        await using var reader = await command.ExecuteReaderAsync();
        if (!await reader.ReadAsync() || reader.GetString(0) != table)
        {
            throw InvalidShape();
        }

        RequireShape(reader.GetString(1), target);
        if (await reader.ReadAsync()) throw InvalidShape();
    }

    /// <summary>核对每列原生类型、宽度、空值、序位以及唯一键全序与显式 MOW，未知表示拒绝。</summary>
    internal static void RequireShape(string ddl, bool target)
    {
        // SHOW CREATE 在本版本把 DATETIMEV2(6) 规范显示为 datetime(6)。
        var table = target ? "dmq_target" : "dmq_entity";
        // 实体和关系目标的第三个键列不同。
        var identity = target ? "target_id" : "entity_id";
        // 每行直接与该版本的建表输出比对，属性中的引号和注释不参与键匹配。
        var lines = ddl.Split('\n', StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
        // 固定源列允许在物化前核对值宽、顺序和类型。
        string[] expected = [
            $"CREATE TABLE `{table}` (", "`org_id` varchar(32) NOT NULL,", "`site_id` varchar(16) NOT NULL,",
            $"`{identity}` varchar(32) NOT NULL,",
            .. target ? new[] { "`join_key` decimal(12,3) NULL," }
                : new[] { "`join_key` decimal(10,2) NULL,", "`amount` decimal(20,2) NULL,", "`unit_code` varchar(8) NOT NULL," },
            "`valid_from` datetime(6) NOT NULL,", "`valid_to` datetime(6) NOT NULL,",
            "`event_at` datetime(6) NOT NULL,", "`observed_at` datetime(6) NOT NULL", ") ENGINE=OLAP",
            $"UNIQUE KEY(`org_id`, `site_id`, `{identity}`)", $"DISTRIBUTED BY HASH(`{identity}`) BUCKETS 1", "PROPERTIES ("
        ];
        if (!lines.Take(expected.Length).SequenceEqual(expected, StringComparer.Ordinal)
            || lines.Count(line => line.TrimEnd(',') == "\"enable_unique_key_merge_on_write\" = \"true\"") != 1)
        {
            throw InvalidShape();
        }
    }

    /// <summary>拒绝时不泄露源端建表正文。</summary>
    private static SemanticOperationException InvalidShape() => new(422, "mapping_source_shape_invalid");
}
