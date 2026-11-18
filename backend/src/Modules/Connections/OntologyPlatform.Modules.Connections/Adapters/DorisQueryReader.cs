using System.Diagnostics;
using System.Globalization;
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

    /// <summary>单表正式分支核完整目录、当前形状和实体过滤条件，按映射的显式时区解释时间。</summary>
    internal static async Task<G4SourceQueryRead> ReadEntityAsync(DorisSourceAdapter adapter, DorisConnectionProfile profile,
        string secret, G4QueryBindingContext context, string entityId, G4SemanticQuery query, G4QueryBranchFilter? branch,
        DateTimeOffset deadline, CancellationToken token)
    {
        DorisAdapterOptions.Validate(profile, context.Scope);
        // S1 的唯一实体必须对应固定表与已经获准的列。
        var mapping = context.Manifest.Mapping;
        if (mapping.Entities is not [var entity] || entity.Id != entityId || branch is not null) throw Invalid();
        // 类型、序位和范围列均来自本次正式快照。
        var table = DorisMappingSourceValidator.EntityTable(entity, context.OriginalCatalog, context.CurrentCatalog, mapping);
        // 外部身份参数只可过滤已批准的实体标识列。
        var identity = mapping.IdentitySpecs.Single(i => i.Id == entity.IdentitySpecId);
        // 显式时区与当前会话偏移独立；输出业务瞬间需要该版本的登记策略。
        var temporal = mapping.TemporalSpecs.Single(t => t.Id == entity.TemporalSpecId);
        if (!DorisMappingSourceValidator.SupportsEntityPlan(entity, identity, temporal) || query.Filters.EntityExternalId is { Length: > 32 })
            throw Invalid();
        // 包住源权限前验及两端目录检查的实际起点。
        var started = DateTimeOffset.UtcNow;
        // 结果一直保留在受限内存内，完成后验和释放后才返回上层。
        var result = await adapter.ReadBranchAsync(profile, secret, deadline, TimeProvider.System, async connection =>
        {
            var shape = await DorisMappingSourceValidator.CheckCatalogAsync(connection, profile, context.CurrentCatalog);
            // 在源端使用固定查询，下游额外使用 Ordinal 验证字符串身份。
            var source = await ReadPlanAsync(connection, context.Scope, query.Filters.EntityExternalId, null);
            // 通过完整组装的行才可构成可信前缀。
            var rows = new List<Dictionary<string, G4QueryValue>>();
            foreach (var item in source)
            {
                if (query.Filters.EntityExternalId is string external && !string.Equals((string?)item["entity_id"], external, StringComparison.Ordinal)) continue;
                // 实体业务行不向公共结果暴露未映射原值。
                var row = table.Fields.ToDictionary(f => f.Name, f => Scalar(item[f.Name], f, temporal), StringComparer.Ordinal);
                if (query.Filters.ValidFrom is string from && query.Filters.ValidTo is string until)
                {
                    if (identity.ValidFromFieldRef is not { Name: "valid_from" } || identity.ValidToFieldRef is not { Name: "valid_to" }) throw Invalid();
                    if (PgQueryReader.Epoch(row["valid_from"].Lexical!) >= PgQueryReader.Epoch(until)
                        || PgQueryReader.Epoch(row["valid_to"].Lexical!) <= PgQueryReader.Epoch(from)) continue;
                }
                rows.Add(row);
            }
            if (await DorisMappingSourceValidator.CheckCatalogAsync(connection, profile, context.CurrentCatalog) != shape) throw Invalid();
            return rows;
        }, token);
        return new G4SourceQueryRead { EntityBindingId = entityId, Rows = result.Take(query.MaxRows).ToArray(), Limited = result.Count > query.MaxRows,
            RecordKeyFields = ["org_id", "site_id", "entity_id"], Indeterminate = false, StartedAtUtc = started, CompletedAtUtc = DateTimeOffset.UtcNow,
            AdapterVersion = "doris-query-v1", WatermarkKind = "UNKNOWN", Watermark = null,
            QueryPlanHash = G4QueryCanonicalHash(context, entityId, query) };
    }

    /// <summary>登记查询计划的来源与固定参数身份，摘要不包含秘密。</summary>
    private static string G4QueryCanonicalHash(G4QueryBindingContext context, string entityId, G4SemanticQuery query) =>
        MappingValidationService.Digest(new { context.Binding, entityId, context.Scope, query.Filters, query.MaxRows,
            template = EntitySql, adapterVersion = "doris-query-v1" });

    /// <summary>按精确源类型生成封闭的 G4 标量；空值保留非空类型。</summary>
    private static G4QueryValue Scalar(object? raw, CatalogField field, MappingTemporalSpec temporal)
    {
        // 同一原生词法供评估和查询使用，避免第二套数值或时间解释。
        var text = DorisMappingSourceValidator.Lexical(raw, field);
        return raw switch
        {
            null when field.NativeType.StartsWith("decimalv3(", StringComparison.Ordinal) => new G4NullValue { DeclaredType = "decimal", Lexical = null },
            string => new G4StringValue { Lexical = text },
            long => new G4Int64Value { Lexical = text },
            decimal => DorisMappingTypeRules.DecimalValue(text!, field.Precision!.Value, field.Scale!.Value),
            DateTime => new G4UtcValue { Lexical = DorisMappingTypeRules.Instant(text!, temporal).ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'", CultureInfo.InvariantCulture) },
            _ => throw Invalid()
        };
    }

    /// <summary>只泄露固定拒绝码，避免返回源结构正文。</summary>
    private static SemanticOperationException Invalid() => new(422, "query_source_plan_invalid");

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
            // 只有两次同形状观测之间的固定行才有资格返回。
            var rows = await ReadPlanAsync(connection, scope, externalId, parent);
            await DorisMappingSourceValidator.CheckTableAsync(connection, parent.HasValue);
            return rows;
        }, cancellationToken);
    }

    /// <summary>在上层已核准的同一物理连接上执行唯一的参数化数据命令。</summary>
    internal static async Task<List<Dictionary<string, object?>>> ReadPlanAsync(MySqlConnection connection,
        ResourceScope scope, string? externalId, (decimal Key, DateTime Start, DateTime End)? parent)
    {
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
        return result;
    }
}
