using System.Globalization;
using Npgsql;
using System.Text;
using System.Text.RegularExpressions;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>查询独立的PG类型边界，保留目录精度，不调用M3全映射评估器执行查询。</summary>
public sealed class PgQueryReader : IG4PgQueryReader
{
    /// <summary>本任务服务器固定CA，调用方不能选择信任根。</summary>
    private readonly string certificate;

    /// <summary>冻结允许Schema，不能由查询载荷扩张。</summary>
    private readonly string[] schemas;

    /// <summary>源预算与上层共用的UTC时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>沿既有合成PG目标准入规则，只增加查询执行能力。</summary>
    public PgQueryReader(PgAdapterOptions options, TimeProvider clock)
    {
        _ = new PgSourceAdapter(options);
        certificate = options.RootCertificatePath;
        schemas = options.AllowedSchemas.ToArray();
        this.clock = clock;
    }

    /// <summary>历史恢复只读取系统目录和当前ACL，不执行SELECT业务表或产生新readReceipt。</summary>
    public async Task VerifyAccessAsync(PgConnectionProfile profile, string secret, G4QueryBindingContext context,
        string entityBindingId, DateTimeOffset deadlineAtUtc, CancellationToken cancellationToken)
    {
        // 与执行分支同样预留平台授权和回传时间，绝不另起五秒源预算。
        var remaining = deadlineAtUtc - clock.GetUtcNow() - TimeSpan.FromMilliseconds(500);
        if (remaining <= TimeSpan.Zero) throw new SemanticOperationException(503, "query_source_budget_exhausted");
        // 当前ACL检查最多一秒且响应宿主取消。
        using var budget = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        budget.CancelAfter(remaining < TimeSpan.FromSeconds(1) ? remaining : TimeSpan.FromSeconds(1));
        if (profile.Host != "pg-source" || profile.Port != 5432 || profile.Database != "fixture" || profile.Username != "fixture_reader"
            || profile.SslMode != "VerifyFull" || !profile.AllowedSchemas.SequenceEqual(schemas) || string.IsNullOrEmpty(secret))
            throw new SemanticOperationException(403, "query_source_forbidden");
        // 原保存字段依赖仍从已验manifest产生，不能用自由字段名试探权限。
        var entity = context.Manifest.Mapping.Entities.SingleOrDefault(item => item.Id == entityBindingId) ?? throw Invalid();
        // 完整范围、身份、时间和属性列都需要当前SELECT权限。
        var references = Fields(context.Manifest.Mapping, entity).Distinct().ToArray();
        // 历史字段类型来自原目录，不要求重新激活历史版本。
        var original = context.OriginalCatalog.Objects.SingleOrDefault(item => item.Schema == entity.DatasetRef.Schema && item.Name == entity.DatasetRef.Name && item.Kind == "TABLE") ?? throw Invalid();
        try
        {
            // 仅使用当前精确账号及固定TLS根，不把秘密写入计划或日志。
            var settings = new NpgsqlConnectionStringBuilder { Host = "pg-source", Port = 5432, Database = "fixture", Username = "fixture_reader", Password = secret,
                SslMode = SslMode.VerifyFull, RootCertificate = certificate, Pooling = false, Timeout = 1, CommandTimeout = 1,
                CancellationTimeout = 250, SearchPath = "pg_catalog", IncludeErrorDetail = false, LogParameters = false, GssEncryptionMode = GssEncryptionMode.Disable };
            await using var connection = new NpgsqlConnection(settings.ConnectionString);
            await connection.OpenAsync(budget.Token);
            await using var transaction = await connection.BeginTransactionAsync(System.Data.IsolationLevel.RepeatableRead, budget.Token);
            await using (var readOnly = new NpgsqlCommand("SET TRANSACTION READ ONLY; SET LOCAL statement_timeout = '1s'; SET LOCAL lock_timeout = '500ms'", connection, transaction))
                await readOnly.ExecuteNonQueryAsync(budget.Token);
            await using (var security = new NpgsqlCommand(ReadOnlySql, connection, transaction))
                if (await security.ExecuteScalarAsync(budget.Token) is not true) throw new SemanticOperationException(403, "query_source_forbidden");
            // 只查系统目录；不以当前业务行重建历史结果。
            var catalog = await ReadCatalogAsync(connection, transaction, schemas, budget.Token);
            // 当前字段仍须是原保存类型与序号，移除或换类型时不能披露旧值。
            var table = catalog.SingleOrDefault(item => item.Schema == original.Schema && item.Name == original.Name && item.Kind == "TABLE") ?? throw Invalid();
            foreach (var reference in references)
            {
                // 原目录已登记的精确列身份，不能只按同名列接受类型替换。
                var field = original.Fields.SingleOrDefault(item => item.Ordinal == reference.Ordinal && item.Name == reference.Name) ?? throw Invalid();
                if (reference.DatasetRef != entity.DatasetRef || table.Fields.SingleOrDefault(item => item.Ordinal == reference.Ordinal && item.Name == reference.Name) != field)
                    throw new SemanticOperationException(503, "query_source_access_unverified");
            }
            // 权限函数逐列检查，支持合法列级SELECT；不通过读取业务行来试探ACL。
            await using var access = new NpgsqlCommand("""
                SELECT c.relkind = 'r' AND NOT c.relrowsecurity AND NOT c.relforcerowsecurity
                    AND NOT c.relhassubclass AND NOT c.relhasrules AND has_schema_privilege(n.oid, 'USAGE')
                    AND NOT EXISTS (SELECT 1 FROM unnest(@columns::text[]) AS requested(name)
                        WHERE NOT has_column_privilege(c.oid, requested.name, 'SELECT'))
                FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = @schema AND c.relname = @name
                """, connection, transaction);
            access.Parameters.AddWithValue("schema", table.Schema);
            access.Parameters.AddWithValue("name", table.Name);
            access.Parameters.AddWithValue("columns", references.Select(item => item.Name).Distinct(StringComparer.Ordinal).ToArray());
            if (await access.ExecuteScalarAsync(budget.Token) is not true) throw new SemanticOperationException(403, "query_source_forbidden");
            await transaction.CommitAsync(budget.Token);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (PostgresException error) when (error.SqlState == "42501") { throw new SemanticOperationException(403, "query_source_forbidden"); }
        catch (Exception error) when (error is OperationCanceledException or NpgsqlException or PgSourceException)
        { throw new SemanticOperationException(503, "query_source_access_unverified"); }
    }

    /// <summary>同一分支的目录、ACL和实际行读取共用独立只读快照，绝不复用失败事务。</summary>
    public async Task<G4SourceQueryRead> ReadAsync(PgConnectionProfile profile, string secret, G4QueryBindingContext context,
        string entityBindingId, G4SemanticQuery query, DateTimeOffset deadlineAtUtc, CancellationToken cancellationToken)
    {
        // 剩余预算扣除平台提交保留区，不把分支超时重置为新五秒。
        var remaining = deadlineAtUtc - clock.GetUtcNow() - TimeSpan.FromMilliseconds(500);
        if (remaining <= TimeSpan.Zero) throw new SemanticOperationException(503, "query_source_budget_exhausted");
        // 每分支最多一秒；上层取消、Run期限与查询绝对期限仍可更早终止。
        using var budget = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        budget.CancelAfter(remaining < TimeSpan.FromSeconds(1) ? remaining : TimeSpan.FromSeconds(1));
        if (profile.Host != "pg-source" || profile.Port != 5432 || profile.Database != "fixture" || profile.Username != "fixture_reader"
            || profile.SslMode != "VerifyFull" || !profile.AllowedSchemas.SequenceEqual(schemas) || string.IsNullOrEmpty(secret))
            throw new SemanticOperationException(403, "query_source_forbidden");
        // 绑定与查询均来自正式守卫，所有字段引用只由不可变manifest解析。
        var entity = context.Manifest.Mapping.Entities.SingleOrDefault(item => item.Id == entityBindingId)
            ?? throw new SemanticOperationException(422, "query_entity_binding_invalid");
        // 只投影该实体的实际语义依赖，不为查询读取整张表全部列。
        var references = Fields(context.Manifest.Mapping, entity).Distinct().ToArray();
        // 原目录保证发布引用不被当前同名字段替换。
        var original = context.OriginalCatalog.Objects.SingleOrDefault(item => item.Schema == entity.DatasetRef.Schema
            && item.Name == entity.DatasetRef.Name && item.Kind == "TABLE") ?? throw Invalid();
        // 当前目录在源事务中逐字核验，之后才用于生成标识符。
        var table = context.CurrentCatalog.Objects.SingleOrDefault(item => item.Schema == entity.DatasetRef.Schema
            && item.Name == entity.DatasetRef.Name && item.Kind == "TABLE") ?? throw Invalid();
        // 精确列序与类型必须仍匹配原发布，不将缺字段补null。
        var fields = references.Select(reference =>
        {
            // 固定引用必须属于原目录中的当前实体数据集。
            var field = table.Fields.SingleOrDefault(item => item.Name == reference.Name && item.Ordinal == reference.Ordinal);
            if (reference.DatasetRef != entity.DatasetRef || entity.DatasetRef.SnapshotId != context.OriginalCatalog.SnapshotId || field is null
                || original.Fields.SingleOrDefault(item => item.Name == reference.Name && item.Ordinal == reference.Ordinal) != field) throw Invalid();
            _ = DeclaredType(field);
            return field;
        }).OrderBy(item => item.Ordinal).ToArray();
        if (fields.Length is < 1 or > 64) throw new SemanticOperationException(422, "query_projection_budget");
        // 真实开始窗口在任何源连接之前记录，不用客户端提供的时刻。
        var started = clock.GetUtcNow();
        try
        {
            // 固定连接身份、TLS与池隔离；秘密不进入计划散列或日志。
            var settings = new NpgsqlConnectionStringBuilder
            {
                Host = "pg-source", Port = 5432, Database = "fixture", Username = "fixture_reader", Password = secret,
                SslMode = SslMode.VerifyFull, RootCertificate = certificate, Pooling = false, Timeout = 1,
                CommandTimeout = 1, CancellationTimeout = 250, SearchPath = "pg_catalog", IncludeErrorDetail = false,
                LogParameters = false, GssEncryptionMode = GssEncryptionMode.Disable
            };
            await using var connection = new NpgsqlConnection(settings.ConnectionString);
            await connection.OpenAsync(budget.Token);
            await using var transaction = await connection.BeginTransactionAsync(System.Data.IsolationLevel.RepeatableRead, budget.Token);
            await using (var readOnly = new NpgsqlCommand("SET TRANSACTION READ ONLY; SET LOCAL statement_timeout = '1s'; SET LOCAL lock_timeout = '500ms'; SET LOCAL timezone = 'UTC'", connection, transaction))
                await readOnly.ExecuteNonQueryAsync(budget.Token);
            await using (var security = new NpgsqlCommand(ReadOnlySql, connection, transaction))
            {
                if (await security.ExecuteScalarAsync(budget.Token) is not true) throw new SemanticOperationException(403, "query_source_readonly_unverified");
            }
            // 目录不以业务SELECT权限过滤，独立表拒绝不会伪装为全目录漂移。
            var catalog = await ReadCatalogAsync(connection, transaction, schemas, budget.Token);
            // 精确沿M1指纹算法比较，M4不重算原制品hash。
            var ordered = catalog.OrderBy(item => item.Schema, StringComparer.Ordinal).ThenBy(item => item.Name, StringComparer.Ordinal)
                .ThenBy(item => item.Kind, StringComparer.Ordinal).Select(item => item with { Fields = item.Fields.OrderBy(field => field.Ordinal).ThenBy(field => field.Name, StringComparer.Ordinal).ToArray() }).ToArray();
            if (ConnectionApplicationService.Hash(ConnectionApplicationService.Encode(new { AdapterVersion = "pg-m1-v1", Objects = ordered })) != context.CurrentCatalog.SchemaFingerprint)
                throw new SemanticOperationException(409, "query_catalog_stale");
            await using (var kind = new NpgsqlCommand("SELECT c.relkind = 'r' AND NOT c.relrowsecurity AND NOT c.relforcerowsecurity AND NOT c.relhassubclass AND NOT c.relhasrules FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = @schema AND c.relname = @name", connection, transaction))
            {
                kind.Parameters.AddWithValue("schema", table.Schema);
                kind.Parameters.AddWithValue("name", table.Name);
                if (await kind.ExecuteScalarAsync(budget.Token) is not true) throw new SemanticOperationException(422, "query_dataset_unsupported");
            }
            // 当前实体身份和范围列是源谓词，不能只依靠返回后过滤。
            var identity = context.Manifest.Mapping.IdentitySpecs.Single(item => item.Id == entity.IdentitySpecId);
            if (identity.ExternalIdFieldRefs.Length != 1) throw new SemanticOperationException(422, "query_identity_unsupported");
            if (fields.Single(item => item.Name == entity.ScopeFields.Organization.Name).NativeType != "text"
                || fields.Single(item => item.Name == entity.ScopeFields.Site.Name).NativeType != "text") throw Invalid();
            using var quoting = new NpgsqlCommandBuilder();
            // 每个字段先在源端检查长度/有限时刻，超限原文不会跨网络物化。
            var bad = fields.Select(field => DeclaredType(field) switch
            {
                "string" => "COALESCE(octet_length(" + quoting.QuoteIdentifier(field.Name) + ") > 4096, false)",
                "date" or "timestampUtc" or "timestampLocal" => "COALESCE(NOT pg_catalog.isfinite(" + quoting.QuoteIdentifier(field.Name) + "), false)",
                _ => "false"
            }).ToArray();
            // 替换null前独立返回哨兵，不能将超限值伪装成源null。
            var columns = fields.Select((field, index) => "CASE WHEN " + bad[index] + " THEN NULL ELSE " + quoting.QuoteIdentifier(field.Name) + " END").ToArray();
            // 时间未知单独标识，不用SQL三值逻辑把未知端点过滤成确定零行。
            var unknownTime = "false";
            // 完整计划只含固定引用和参数化谓词，没有用户SQL或任意函数。
            var predicate = " WHERE " + quoting.QuoteIdentifier(entity.ScopeFields.Organization.Name) + " = @organization AND "
                + quoting.QuoteIdentifier(entity.ScopeFields.Site.Name) + " = ANY(@sites)";
            if (query.Filters.EntityExternalId is not null) predicate += " AND " + quoting.QuoteIdentifier(identity.ExternalIdFieldRefs[0].Name) + "::text = @external";
            if (query.Filters.ValidFrom is not null)
            {
                if (identity.ValidFromFieldRef is null || identity.ValidToFieldRef is null
                    || DeclaredType(fields.Single(item => item.Name == identity.ValidFromFieldRef.Name)) != "timestampUtc"
                    || DeclaredType(fields.Single(item => item.Name == identity.ValidToFieldRef.Name)) != "timestampUtc")
                    throw new SemanticOperationException(422, "query_time_window_unknown");
                unknownTime = "(" + quoting.QuoteIdentifier(identity.ValidFromFieldRef.Name) + " IS NULL OR "
                    + quoting.QuoteIdentifier(identity.ValidToFieldRef.Name) + " IS NULL)";
                predicate += " AND (" + unknownTime + " OR (EXTRACT(EPOCH FROM " + quoting.QuoteIdentifier(identity.ValidFromFieldRef.Name)
                    + ") < @until AND EXTRACT(EPOCH FROM " + quoting.QuoteIdentifier(identity.ValidToFieldRef.Name) + ") > @from))";
            }
            // 未知窗口行保留在有界源结果中，由独立标志使上层不能误报EMPTY。
            var sql = "SELECT (" + string.Join(" OR ", bad) + ")," + unknownTime + "," + string.Join(",", columns)
                + " FROM " + quoting.QuoteIdentifier(table.Schema) + "." + quoting.QuoteIdentifier(table.Name) + predicate
                + " ORDER BY " + string.Join(",", fields.Select(field => quoting.QuoteIdentifier(field.Name) + (DeclaredType(field) == "string" ? " COLLATE \"C\"" : "") + " NULLS FIRST")) + " LIMIT 101";
            await using var command = new NpgsqlCommand(sql, connection, transaction);
            command.Parameters.AddWithValue("organization", context.Scope.OrganizationId);
            command.Parameters.AddWithValue("sites", context.Scope.SiteIds);
            if (query.Filters.EntityExternalId is not null) command.Parameters.AddWithValue("external", query.Filters.EntityExternalId);
            if (query.Filters.ValidFrom is not null)
            {
                command.Parameters.AddWithValue("from", Epoch(query.Filters.ValidFrom));
                command.Parameters.AddWithValue("until", Epoch(query.Filters.ValidTo!));
            }
            // 全分支中间内存有界；上层仍负责跨分支总预算。
            var rows = new List<Dictionary<string, G4QueryValue>>();
            // 实际哨兵决定是否完整，不用预估行数宣称EMPTY。
            var limited = false;
            // 未知时间与预算截断分开，不能虚报limited来隐藏语义不确定。
            var indeterminate = false;
            // 近似上界覆盖UTF8值、列名及每单元格固定元数据。
            var size = 0;
            await using (var reader = await command.ExecuteReaderAsync(budget.Token))
            {
                while (await reader.ReadAsync(budget.Token))
                {
                    if (rows.Count >= query.MaxRows || reader.GetBoolean(0)) { limited = true; break; }
                    if (reader.GetBoolean(1)) { indeterminate = true; continue; }
                    // 当前行在所有字段通过后才加入可信前缀。
                    var row = new Dictionary<string, G4QueryValue>(StringComparer.Ordinal);
                    for (var index = 0; index < fields.Length; index++)
                    {
                        // DATE原生取DateOnly，不将其补午夜。
                        var value = reader.IsDBNull(index + 2) ? DBNull.Value : fields[index].NativeType == "date"
                            ? (object)reader.GetFieldValue<DateOnly>(index + 2) : reader.GetValue(index + 2);
                        // 精确类型转换保持scale和微秒，不经过double。
                        var scalar = Scalar(value, fields[index]);
                        size += Encoding.UTF8.GetByteCount(scalar.Lexical ?? "null") + Encoding.UTF8.GetByteCount(fields[index].Name) + 256;
                        row.Add(fields[index].Name, scalar);
                    }
                    if (size > 4 * 1024 * 1024) { limited = true; break; }
                    if (row[entity.ScopeFields.Organization.Name].Lexical != context.Scope.OrganizationId
                        || !context.Scope.SiteIds.Contains(row[entity.ScopeFields.Site.Name].Lexical, StringComparer.Ordinal)) throw Invalid();
                    rows.Add(row);
                }
            }
            // 只把完全投影的真实主键当记录定位依据，无主键时显式降级。
            var keys = await RecordKeysAsync(connection, transaction, table, fields, budget.Token);
            await using var snapshot = new NpgsqlCommand("SELECT pg_catalog.pg_current_snapshot()::text", connection, transaction);
            // 快照仅作为本次读水位，不充当跨分支全局事务。
            var watermark = (string)(await snapshot.ExecuteScalarAsync(budget.Token))!;
            await transaction.CommitAsync(budget.Token);
            return new G4SourceQueryRead
            {
                EntityBindingId = entity.Id, Rows = rows.ToArray(), StartedAtUtc = started, CompletedAtUtc = clock.GetUtcNow(),
                TransactionSnapshot = watermark, Limited = limited, Indeterminate = indeterminate, RecordKeyFields = keys,
                QueryPlanHash = Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(System.Text.Json.JsonSerializer.SerializeToUtf8Bytes(
                    new { context.Binding, entity.Id, fields, context.Scope, query.Filters, query.MaxRows, AdapterVersion = "pg-query-v1" }, G4QueryJson.Options)))
            };
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested) { throw; }
        catch (PostgresException error) when (error.SqlState == "42501") { throw new SemanticOperationException(403, "query_source_forbidden"); }
        catch (Exception error) when (error is OperationCanceledException || error is PostgresException { SqlState: "57014" })
        { throw new SemanticOperationException(503, "query_source_timeout"); }
        catch (Exception error) when (error is NpgsqlException or PgSourceException or InvalidCastException or OverflowException or System.Text.Json.JsonException)
        { throw new SemanticOperationException(503, "query_source_unavailable"); }
    }

    /// <summary>UTC窗口转精确numeric秒，避免PG微秒参数舍入纳秒边界。</summary>
    private static decimal Epoch(string value)
    {
        // 请求已由正式守卫验证公历与0至9位小数，这里不猜测偏移。
        var whole = DateTimeOffset.ParseExact(value[..19] + "Z", "yyyy-MM-dd'T'HH:mm:ss'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal).ToUnixTimeSeconds();
        return whole + (value.Length == 20 ? 0m : decimal.Parse("0" + value[19..^1], CultureInfo.InvariantCulture));
    }

    /// <summary>实体实际消费列包含范围、身份、业务时间、属性及单位证据。</summary>
    internal static IEnumerable<MappingFieldRef> Fields(MappingDefinition mapping, MappingEntityBinding entity)
    {
        // 固定身份定义来自manifest，不接收任意列名列表。
        var identity = mapping.IdentitySpecs.Single(item => item.Id == entity.IdentitySpecId);
        // 时间规则与身份有效区间可能共享列，调用方按精确引用去重。
        var temporal = mapping.TemporalSpecs.Single(item => item.Id == entity.TemporalSpecId);
        foreach (var field in new[] { entity.ScopeFields.Organization, entity.ScopeFields.Site, identity.OrganizationFieldRef,
            identity.SiteFieldRef, identity.ValidFromFieldRef, identity.ValidToFieldRef, temporal.EventTimeFieldRef,
            temporal.ObservedAtFieldRef, temporal.ValidFromFieldRef, temporal.ValidToFieldRef }.OfType<MappingFieldRef>()) yield return field;
        foreach (var field in identity.ExternalIdFieldRefs) yield return field;
        foreach (var property in mapping.Properties.Where(item => item.EntityBindingId == entity.Id))
        {
            yield return property.FieldRef;
            if (property.UnitSpecId is not null) yield return mapping.UnitSpecs.Single(item => item.Id == property.UnitSpecId).SourceUnitFieldRef;
        }
    }

    /// <summary>系统目录证明真实主键，不以行号或当前返回顺序伪造记录身份。</summary>
    private static async Task<string[]> RecordKeysAsync(NpgsqlConnection connection, NpgsqlTransaction transaction, CatalogObject table,
        CatalogField[] fields, CancellationToken token)
    {
        await using var command = new NpgsqlCommand("""
            SELECT a.attname FROM pg_catalog.pg_index i
            JOIN pg_catalog.pg_class c ON c.oid = i.indrelid
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            CROSS JOIN LATERAL unnest(i.indkey) WITH ORDINALITY AS k(attnum, position)
            JOIN pg_catalog.pg_attribute a ON a.attrelid = c.oid AND a.attnum = k.attnum
            WHERE n.nspname = @schema AND c.relname = @name AND i.indisprimary AND i.indisvalid
            ORDER BY k.position LIMIT 65
            """, connection, transaction);
        command.Parameters.AddWithValue("schema", table.Schema);
        command.Parameters.AddWithValue("name", table.Name);
        // 只保留真实名称，输出证据使用有界哈希或明确记录引用。
        var names = new List<string>();
        await using var reader = await command.ExecuteReaderAsync(token);
        while (await reader.ReadAsync(token)) names.Add(reader.GetString(0));
        return names.Count is > 0 and <= 64 && names.All(name => fields.Any(field => field.Name == name)) ? names.ToArray() : [];
    }

    /// <summary>按批准目录类型生成精确wire标量；未知类型即使为null也拒绝。</summary>
    public static G4QueryValue Scalar(object value, CatalogField field)
    {
        // 类型来自已固定目录，必须先校验再处理数据库null。
        var type = DeclaredType(field);
        if (value is DBNull)
        {
            if (!field.Nullable) throw Invalid();
            return new G4NullValue { Lexical = null, DeclaredType = type };
        }
        // 各分支校验原生CLR类型，绝不通过Convert.ChangeType进行损失性转换。
        G4QueryValue result;
        switch (type)
        {
            case "decimal" when value is decimal number:
                if (decimal.Round(number, field.Scale!.Value) != number) throw Invalid();
                result = new G4DecimalValue
                {
                    Lexical = (number == 0 ? 0m : number).ToString("F" + field.Scale.Value.ToString(CultureInfo.InvariantCulture), CultureInfo.InvariantCulture),
                    Precision = field.Precision!.Value, Scale = field.Scale.Value
                };
                break;
            case "int64" when field.NativeType == "smallint" && value is short
                || field.NativeType == "integer" && value is int || field.NativeType == "bigint" && value is long:
                result = new G4Int64Value { Lexical = ((IFormattable)value).ToString(null, CultureInfo.InvariantCulture) };
                break;
            case "boolean" when value is bool boolean:
                result = new G4BooleanValue { Lexical = boolean ? "true" : "false" };
                break;
            case "string" when value is string text:
                if (new UTF8Encoding(false, true).GetByteCount(text) > 4096) throw Invalid();
                result = new G4StringValue { Lexical = text };
                break;
            case "date" when value is DateOnly date:
                result = new G4DateValue { Lexical = date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture) };
                break;
            case "timestampUtc" when value is DateTime utc && utc.Kind == DateTimeKind.Utc && utc.Ticks % 10 == 0:
                result = new G4UtcValue { Lexical = utc.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'", CultureInfo.InvariantCulture) };
                break;
            case "timestampLocal" when value is DateTime local && local.Kind == DateTimeKind.Unspecified && local.Ticks % 10 == 0:
                result = new G4LocalValue { Lexical = local.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff", CultureInfo.InvariantCulture) };
                break;
            default:
                throw Invalid();
        }
        G4QueryRules.Value(result);
        return result;
    }

    /// <summary>仅允许已冻结标量类型，numeric须有准确precision/scale且不大于28位。</summary>
    private static string DeclaredType(CatalogField field)
    {
        if (field.Precision is >= 1 and <= 28 && field.Scale >= 0 && field.Scale <= field.Precision
            && field.NativeType == $"numeric({field.Precision},{field.Scale})") return "decimal";
        if (field.NativeType is "smallint" or "integer" or "bigint") return "int64";
        if (field.NativeType == "boolean") return "boolean";
        if (field.NativeType == "date") return "date";
        if (field.NativeType == "text" || Regex.IsMatch(field.NativeType, @"\A(character varying|character)\([1-9][0-9]{0,6}\)\z", RegexOptions.CultureInvariant)) return "string";
        if (Regex.IsMatch(field.NativeType, @"\Atimestamp(?:\([0-6]\))? with time zone\z", RegexOptions.CultureInvariant)) return "timestampUtc";
        if (Regex.IsMatch(field.NativeType, @"\Atimestamp(?:\([0-6]\))? without time zone\z", RegexOptions.CultureInvariant)) return "timestampLocal";
        throw Invalid();
    }

    /// <summary>固定脱敏码，不回传原生值、SQL或源异常。</summary>
    private static SemanticOperationException Invalid() => new(409, "query_source_value_invalid");
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
                bytes += System.Text.Json.JsonSerializer.SerializeToUtf8Bytes(current, G4ConnectionJson.Options).Length + 1;
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
            bytes += System.Text.Json.JsonSerializer.SerializeToUtf8Bytes(field, G4ConnectionJson.Options).Length + 1;
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

    /// <summary>保守检查全部直接及间接成员角色，包括可SET ROLE但未自动继承的写入能力。</summary>
    private const string ReadOnlySql = """
        WITH reachable AS (
            SELECT r.* FROM pg_catalog.pg_roles r
            WHERE r.rolname = current_user OR pg_catalog.pg_has_role(current_user, r.oid, 'MEMBER')
        )
        SELECT current_user = 'fixture_reader' AND session_user = 'fixture_reader'
            AND current_database() = 'fixture'
            AND current_setting('transaction_read_only') = 'on'
            AND NOT EXISTS (
                SELECT 1 FROM reachable r
                WHERE r.rolsuper OR r.rolcreatedb OR r.rolcreaterole OR r.rolbypassrls OR r.rolreplication
                    OR r.rolname IN ('pg_write_all_data', 'pg_write_server_files', 'pg_execute_server_program',
                        'pg_signal_backend', 'pg_checkpoint', 'pg_maintain', 'pg_database_owner')
                    OR pg_catalog.has_database_privilege(r.oid, current_database(), 'CREATE,TEMP')
                    OR EXISTS (SELECT 1 FROM pg_catalog.pg_shdepend d WHERE d.refclassid = 'pg_catalog.pg_authid'::regclass
                        AND d.refobjid = r.oid AND d.deptype = 'o')
                    OR EXISTS (SELECT 1 FROM pg_catalog.pg_namespace n
                        WHERE n.nspowner = r.oid OR pg_catalog.has_schema_privilege(r.oid, n.oid, 'CREATE'))
                    OR EXISTS (SELECT 1 FROM pg_catalog.pg_class c WHERE c.relowner = r.oid)
                    OR EXISTS (SELECT 1 FROM pg_catalog.pg_proc p WHERE p.proowner = r.oid)
                    OR EXISTS (SELECT 1 FROM pg_catalog.pg_type t WHERE t.typowner = r.oid)
                    OR EXISTS (SELECT 1 FROM pg_catalog.pg_class c
                        WHERE c.relkind IN ('r','p','v','m','f') AND (
                            pg_catalog.has_table_privilege(r.oid, c.oid, 'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER,MAINTAIN')
                            OR pg_catalog.has_any_column_privilege(r.oid, c.oid, 'INSERT,UPDATE,REFERENCES')))
                    OR EXISTS (SELECT 1 FROM pg_catalog.pg_class c
                        WHERE CASE WHEN c.relkind = 'S' THEN pg_catalog.has_sequence_privilege(r.oid, c.oid, 'USAGE,UPDATE') ELSE false END)
            )
        """;

    /// <summary>源端LIMIT哨兵与系统format_type保真，SELECT许可由真实分支语句验证，不读取业务数据。</summary>
    private const string CatalogSql = """
        WITH visible_objects AS MATERIALIZED (
            SELECT c.oid, n.nspname, c.relname, c.relkind
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = ANY(@schemas)
                AND pg_catalog.has_schema_privilege(n.oid, 'USAGE')
                AND c.relkind IN ('r','p','v','m','f')

            ORDER BY n.nspname COLLATE "C", c.relname COLLATE "C"
            LIMIT 101
        )
        SELECT o.nspname, o.relname, CASE WHEN o.relkind IN ('v','m') THEN 'VIEW' ELSE 'TABLE' END,
            a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod), NOT (a.attnotnull OR t.typnotnull), a.attnum,
            CASE WHEN bt.oid = 1700 AND m.typmod >= 4 THEN ((m.typmod - 4) >> 16) & 65535 END,
            CASE WHEN bt.oid = 1700 AND m.typmod >= 4 THEN (((m.typmod - 4) & 2047) # 1024) - 1024 END
        FROM visible_objects o
        LEFT JOIN pg_catalog.pg_attribute a ON a.attrelid = o.oid AND a.attnum > 0 AND NOT a.attisdropped

        LEFT JOIN pg_catalog.pg_type t ON t.oid = a.atttypid
        LEFT JOIN pg_catalog.pg_type bt ON bt.oid = CASE WHEN t.typtype = 'd' THEN t.typbasetype ELSE t.oid END
        LEFT JOIN LATERAL (SELECT CASE WHEN t.typtype = 'd' THEN t.typtypmod ELSE a.atttypmod END AS typmod) m ON true
        ORDER BY o.nspname COLLATE "C", o.relname COLLATE "C", a.attnum
        LIMIT 2001
        """;
}
