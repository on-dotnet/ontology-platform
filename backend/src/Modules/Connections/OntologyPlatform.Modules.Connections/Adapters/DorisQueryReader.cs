using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using MySqlConnector;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>两表合成切片的业务读取。表、列、顺序及谓词固定，调用方仅传入标量。</summary>
internal static class DorisQueryReader
{
    /// <summary>实体定位和实体列表共用一个有序投影；唯一键消除同一事件时间的并列。</summary>
    private const string EntitySql = """
        SELECT /*+ SET_VAR(enable_sql_cache=false) */ org_id,site_id,entity_id,join_key,amount,unit_code,valid_from,valid_to,event_at,observed_at
        FROM fixture.dmq_entity
        WHERE org_id=@org AND site_id=@site AND (@external IS NULL OR entity_id=@external)
        ORDER BY event_at,entity_id,org_id,site_id LIMIT 101
        """;

    /// <summary>关系目标按源定点数等值及半开有效期匹配；空键由 SQL 三值逻辑排除。</summary>
    private const string TargetSql = """
        SELECT /*+ SET_VAR(enable_sql_cache=false) */ org_id,site_id,target_id,join_key,valid_from,valid_to,event_at,observed_at
        FROM fixture.dmq_target
        WHERE org_id=@org AND site_id=@site AND join_key=@key AND valid_from<@end AND valid_to>@start
        ORDER BY event_at,target_id,org_id,site_id LIMIT 101
        """;

    /// <summary>按调用方已经核准的范围读取实体行，或读取一个已知父实体的关系候选。</summary>
    internal static Task<List<Dictionary<string, object?>>> ReadAsync(DorisSourceAdapter adapter, DorisConnectionProfile profile,
        string secret, ResourceScope scope, string? externalId, (decimal Key, DateTime Start, DateTime End)? parent,
        DateTimeOffset deadline, CancellationToken cancellationToken)
    {
        DorisAdapterOptions.Validate(profile, scope);
        if (externalId is { Length: > 32 } || (parent.HasValue && externalId is not null) ||
            (parent is { } interval && (interval.Start >= interval.End || interval.Start.Kind != DateTimeKind.Unspecified ||
            interval.End.Kind != DateTimeKind.Unspecified)))
            throw new SemanticOperationException(422, "query_source_plan_invalid");

        return adapter.ReadBranchAsync(profile, secret, deadline, TimeProvider.System, async connection =>
        {
            await DorisMappingSourceValidator.CheckTableAsync(connection, parent.HasValue);
            // 模板只由本次读取实体或目标的固定分支选择。
            var template = parent.HasValue ? TargetSql : EntitySql;
            await using var command = new MySqlCommand(template, connection);
            command.Parameters.Add("@org", MySqlDbType.VarChar).Value = scope.OrganizationId;
            command.Parameters.Add("@site", MySqlDbType.VarChar).Value = scope.SiteIds.Single();
            if (parent is { } relation)
            {
                command.Parameters.Add("@key", MySqlDbType.Decimal).Value = relation.Key;
                command.Parameters.Add("@start", MySqlDbType.DateTime).Value = relation.Start;
                command.Parameters.Add("@end", MySqlDbType.DateTime).Value = relation.End;
            }
            else command.Parameters.Add("@external", MySqlDbType.VarChar).Value = (object?)externalId ?? DBNull.Value;
            Activity.Current?.AddEvent(new ActivityEvent("doris.plan.submitted", tags: new ActivityTagsCollection
            {
                { "thread", connection.ServerThread },
                { "template.sha256", Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(template))) }
            }));
            // 两种模板的字段宽度均受批准的固定目录约束，LIMIT 101 保留超限哨兵。
            var result = new List<Dictionary<string, object?>>();
            await using (var rows = await command.ExecuteReaderAsync(CancellationToken.None))
            {
                while (await rows.ReadAsync(CancellationToken.None))
                {
                    if (result.Count >= 100) throw new SemanticOperationException(422, "query_source_row_budget");
                    if (rows.GetString(0) != scope.OrganizationId || rows.GetString(1) != scope.SiteIds[0])
                        throw new SemanticOperationException(403, "query_source_forbidden");
                    // 保留驱动实际的 decimal、无时区时间及空值，业务映射另行解释。
                    var record = new Dictionary<string, object?>(rows.FieldCount, StringComparer.Ordinal);
                    for (int column = 0; column < rows.FieldCount; column++)
                        record.Add(rows.GetName(column), rows.IsDBNull(column) ? null : rows.GetValue(column));
                    result.Add(record);
                }
            }
            Activity.Current?.AddEvent(new ActivityEvent("doris.plan.rows_finished"));
            await DorisMappingSourceValidator.CheckTableAsync(connection, parent.HasValue);
            return result;
        }, cancellationToken);
    }
}
