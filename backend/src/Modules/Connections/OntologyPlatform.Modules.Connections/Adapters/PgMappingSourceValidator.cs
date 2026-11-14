using System.Globalization;
using System.Text;
using Npgsql;
using System.Text.Json;
using System.Text.RegularExpressions;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>只执行固定PG映射计划的源读取与精确类型边界。</summary>
public sealed class PgMappingSourceValidator : IMappingSourceValidator
{
    /// <summary>服务器信任根只接受已批准固定目标。</summary>
    private readonly string certificate;

    /// <summary>固定源Schema集合由服务器注入，客户端不能扩大。</summary>
    private readonly string[] allowedSchemas;

    /// <summary>复用现有PG目标策略构造检查，但不扩大旧metadata适配器能力。</summary>
    public PgMappingSourceValidator(PgAdapterOptions options)
    {
        _ = new PgSourceAdapter(options);
        certificate = options.RootCertificatePath;
        allowedSchemas = options.AllowedSchemas.ToArray();
    }

    /// <summary>全部受支持变长类型均须在源端施加字节哨兵。</summary>
    private static bool VariableLength(string type) => type is "text" or "jsonb"
        || type.StartsWith("character varying(", StringComparison.Ordinal) || type.StartsWith("character(", StringComparison.Ordinal);

    /// <summary>在同一真实只读可重复读事务内完成全目录与限定完整行读取。</summary>
    public Task<MappingSourceObservation> ReadAsync(PgConnectionProfile profile, string secret, CatalogSnapshotView snapshot,
        MappingDefinition mapping, ResourceScope scope, CancellationToken cancellationToken, CatalogSnapshotView? originSnapshot = null) =>
        ReadCoreAsync(profile, secret, snapshot, mapping, scope, cancellationToken, originSnapshot, readRows: true);

    /// <summary>正文GET只检查真实源目录和精确SELECT权限，不读取业务行。</summary>
    public async Task VerifyAccessAsync(PgConnectionProfile profile, string secret, CatalogSnapshotView snapshot,
        MappingDefinition mapping, ResourceScope scope, CancellationToken cancellationToken, CatalogSnapshotView? originSnapshot = null)
    {
        _ = await ReadCoreAsync(profile, secret, snapshot, mapping, scope, cancellationToken, originSnapshot, readRows: false);
    }

    /// <summary>同一源边界供实际评估和无业务行ACL检查复用。</summary>
    private async Task<MappingSourceObservation> ReadCoreAsync(PgConnectionProfile profile, string secret, CatalogSnapshotView snapshot,
        MappingDefinition mapping, ResourceScope scope, CancellationToken cancellationToken, CatalogSnapshotView? originSnapshot, bool readRows)
    {
        originSnapshot ??= snapshot;
        G4MappingRules.Definition(mapping);
        G4MappingRules.Scope(scope);
        if (profile.Host != "pg-source" || profile.Port != 5432 || profile.Database != "fixture" || profile.Username != "fixture_reader"
            || profile.SslMode != "VerifyFull" || !profile.AllowedSchemas.SequenceEqual(allowedSchemas) || string.IsNullOrEmpty(secret)
            || snapshot.Status != "READY" || snapshot.Scope.OrganizationId != scope.OrganizationId
            || !scope.SiteIds.All(site => snapshot.Scope.SiteIds.Contains(site, StringComparer.Ordinal)))
        {
            throw new SemanticOperationException(422, "mapping_source_forbidden");
        }
        // 冻结可变数组，异步IO期间不消费调用方后来更改的定义。
        mapping = JsonSerializer.Deserialize<MappingDefinition>(MappingCanonical.Serialize(mapping), G4MappingJson.Options)!;
        // 总预算包括目录、真实源行、ACL和提交，不重复为每张表续期。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(30));
        // 观察时间仅属于本次证据，不改变受审版本hash。
        var started = DateTimeOffset.UtcNow;
        try
        {
            // 强类型固定连接控制字段；密码只在本调用内存中使用。
            var builder = new NpgsqlConnectionStringBuilder
            {
                Host = "pg-source",
                Port = 5432,
                Database = "fixture",
                Username = "fixture_reader",
                Password = secret,
                SslMode = SslMode.VerifyFull,
                RootCertificate = certificate,
                Pooling = false,
                Timeout = 3,
                CommandTimeout = 5,
                CancellationTimeout = 250,
                SearchPath = "pg_catalog",
                IncludeErrorDetail = false,
                LogParameters = false,
                GssEncryptionMode = GssEncryptionMode.Disable
            };
            // 不共享源连接池，避免角色与会话状态跨任务残留。
            await using var connection = new NpgsqlConnection(builder.ConnectionString);
            await connection.OpenAsync(deadline.Token);
            // 源目录、ACL、COUNT及业务行必须来自同一可重复读快照。
            await using var transaction = await connection.BeginTransactionAsync(System.Data.IsolationLevel.RepeatableRead, deadline.Token);
            // 第一条源命令先设置只读，所有SQL只能读或设置当前事务参数。
            await using (var readOnly = new NpgsqlCommand("SET TRANSACTION READ ONLY; SET LOCAL statement_timeout = '5s'; SET LOCAL lock_timeout = '2s'; SET LOCAL timezone = 'UTC'", connection, transaction))
            {
                await readOnly.ExecuteNonQueryAsync(deadline.Token);
            }
            // 继承角色、所有权和全部有效写权限再次由源系统目录证明。
            await using (var security = new NpgsqlCommand(ReadOnlySql, connection, transaction))
            {
                if (await security.ExecuteScalarAsync(deadline.Token) is not true)
                {
                    throw new SemanticOperationException(422, "mapping_source_readonly_unverified");
                }
            }
            // 全目录指纹仍使用M1既有原字节算法，不能被新canonical悄然重算。
            var catalog = await ReadCatalogAsync(connection, transaction, allowedSchemas, deadline.Token);
            // 排序与现有ConnectionApplicationService.CanonicalCatalog逐字段一致。
            var ordered = catalog.OrderBy(item => item.Schema, StringComparer.Ordinal).ThenBy(item => item.Name, StringComparer.Ordinal)
                .ThenBy(item => item.Kind, StringComparer.Ordinal).Select(item => item with { Fields = item.Fields.OrderBy(field => field.Ordinal).ThenBy(field => field.Name, StringComparer.Ordinal).ToArray() }).ToArray();
            // 原目录使用G4ConnectionJson，而Mapping内容使用独立版本的canonical。
            var fingerprint = ConnectionApplicationService.Hash(ConnectionApplicationService.Encode(new { AdapterVersion = "pg-m1-v1", Objects = ordered }));
            if (fingerprint != snapshot.SchemaFingerprint || ConnectionApplicationService.Encode(ordered) != ConnectionApplicationService.Encode(snapshot.Objects))
            {
                throw new SemanticOperationException(409, "mapping_catalog_stale");
            }
            // 每张表只读一次，多个实体绑定共享同一完整样本。
            var tables = new List<MappingSourceTable>();
            // 所有表合计行数不超过100，不能分别取100后冒充全局预算。
            var rowCount = 0;
            // 字节预算覆盖原始精确值，不把超限字符串先持久化再截断。
            var byteCount = 0;
            // 数据集去重保持固定引用身份，范围列冲突直接拒绝。
            foreach (var group in mapping.Entities.GroupBy(entity => entity.DatasetRef))
            {
                // 表名来自已经逐字节比较的固定目录，不接受自由SQL片段。
                var dataset = group.Key;
                if (dataset.SnapshotId != originSnapshot.SnapshotId || group.Select(entity => entity.ScopeFields).Distinct().Count() != 1)
                {
                    throw new SemanticOperationException(422, "mapping_dataset_invalid");
                }
                // 同名表必须同时精确匹配schema和TABLE种类。
                var table = ordered.SingleOrDefault(item => item.Schema == dataset.Schema && item.Name == dataset.Name && item.Kind == "TABLE")
                    ?? throw new SemanticOperationException(422, "mapping_dataset_invalid");
                if (table.Fields.Length is < 1 or > 12)
                {
                    throw new SemanticOperationException(422, "mapping_source_budget_exceeded");
                }
                // 回滚可使用当前兼容快照，但原制品引用的表列类型不能悄然重绑。
                var originalTable = originSnapshot.Objects.SingleOrDefault(item => item.Schema == dataset.Schema && item.Name == dataset.Name && item.Kind == "TABLE");
                if (originalTable is null || RequiredFields(mapping).Where(field => field.DatasetRef == dataset).Any(reference =>
                    originalTable.Fields.SingleOrDefault(field => field.Ordinal == reference.Ordinal && field.Name == reference.Name)
                        != table.Fields.SingleOrDefault(field => field.Ordinal == reference.Ordinal && field.Name == reference.Name)))
                {
                    throw new SemanticOperationException(409, "mapping_original_schema_incompatible");
                }
                // 所有业务引用同时核列名与ordinal，不能以同名列替换旧绑定。
                if (RequiredFields(mapping).Where(field => field.DatasetRef == dataset)
                    .Any(reference => !table.Fields.Any(field => field.Name == reference.Name && field.Ordinal == reference.Ordinal)))
                {
                    throw new SemanticOperationException(409, "mapping_field_stale");
                }
                // 未知类型即使全null也拒绝；避免驱动调用用户类型转换。
                foreach (var field in table.Fields)
                {
                    _ = Scalar(DBNull.Value, field);
                }
                // 分区、外部表、视图、RLS和规则可能使完整性不明，首切片只读普通表。
                await using (var kind = new NpgsqlCommand("SELECT c.relkind = 'r' AND NOT c.relrowsecurity AND NOT c.relforcerowsecurity AND NOT c.relhassubclass AND NOT c.relhasrules FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace WHERE n.nspname = @schema AND c.relname = @name", connection, transaction))
                {
                    kind.Parameters.AddWithValue("schema", dataset.Schema);
                    kind.Parameters.AddWithValue("name", dataset.Name);
                    if (await kind.ExecuteScalarAsync(deadline.Token) is not true)
                    {
                        throw new SemanticOperationException(422, "mapping_dataset_unsupported");
                    }
                }
                // 范围字段必须在已授权列集合中且是明确文本类型。
                var fields = group.First().ScopeFields;
                if (!table.Fields.Any(field => field.Name == fields.Organization.Name && field.Ordinal == fields.Organization.Ordinal && field.NativeType == "text")
                    || !table.Fields.Any(field => field.Name == fields.Site.Name && field.Ordinal == fields.Site.Ordinal && field.NativeType == "text"))
                {
                    throw new SemanticOperationException(422, "mapping_scope_fields_invalid");
                }
                // QuoteIdentifier仅用于已批准目录标识，所有业务值始终参数化。
                using var quoting = new NpgsqlCommandBuilder();
                if (!readRows)
                {
                    // LIMIT 0仍由PG验证全部被选列权限，但不会返回任何业务值。
                    await using var access = new NpgsqlCommand("SELECT " + string.Join(",", table.Fields.Select(field => quoting.QuoteIdentifier(field.Name)))
                        + " FROM " + quoting.QuoteIdentifier(table.Schema) + "." + quoting.QuoteIdentifier(table.Name) + " LIMIT 0", connection, transaction);
                    // 仅打开并关闭空结果，任何权限错误按统一安全异常退出。
                    await using var empty = await access.ExecuteReaderAsync(deadline.Token);
                    continue;
                }
                // 源端先屏蔽超大可变长值，避免驱动在本地预算检查前物化无界text/jsonb。
                var oversized = table.Fields.Where(field => VariableLength(field.NativeType))
                    .Select(field => "COALESCE(octet_length(" + quoting.QuoteIdentifier(field.Name) + "::text) > 65536, false)").ToArray();
                // 哨兵独立于替换后的null，超限值绝不伪装成合法数据库null。
                var sentinel = oversized.Length == 0 ? "false" : string.Join(" OR ", oversized);
                // 单列最多64KiB，驱动整行缓冲也受12列上限约束。
                var projections = table.Fields.Select(field => VariableLength(field.NativeType)
                    ? "CASE WHEN octet_length(" + quoting.QuoteIdentifier(field.Name) + "::text) <= 65536 THEN " + quoting.QuoteIdentifier(field.Name) + " ELSE NULL END"
                    : quoting.QuoteIdentifier(field.Name));
                // 先读完整COUNT与字节哨兵，再按目录ordinal读取有界数据列。
                var sql = "SELECT count(*) OVER (), (" + sentinel + "), " + string.Join(",", projections)
                    + " FROM " + quoting.QuoteIdentifier(table.Schema) + "." + quoting.QuoteIdentifier(table.Name)
                    + " WHERE " + quoting.QuoteIdentifier(fields.Organization.Name) + " = @organization AND " + quoting.QuoteIdentifier(fields.Site.Name) + " = ANY(@sites) LIMIT 101";
                // 单表查询使用五秒硬期限和总三十秒取消。
                await using var command = new NpgsqlCommand(sql, connection, transaction);
                command.Parameters.AddWithValue("organization", scope.OrganizationId);
                command.Parameters.AddWithValue("sites", scope.SiteIds);
                // 原始业务行只存内存，后续评估仅持久摘要和散列。
                var rows = new List<Dictionary<string, MappingSourceCell>>();
                // 完整COUNT用于证明LIMIT没有截断，零行仍由评估标INDETERMINATE。
                long expected = 0;
                await using (var reader = await command.ExecuteReaderAsync(deadline.Token))
                {
                    while (await reader.ReadAsync(deadline.Token))
                    {
                        expected = reader.GetInt64(0);
                        if (expected > 100 || ++rowCount > 100 || reader.GetBoolean(1))
                        {
                            throw new SemanticOperationException(422, "mapping_source_budget_exceeded");
                        }
                        // 字段按名称唯一保存，后续执行按固定fieldRef定位。
                        var row = new Dictionary<string, MappingSourceCell>(StringComparer.Ordinal);
                        // 每个值使用真实驱动类型进行无损转换。
                        for (var index = 0; index < table.Fields.Length; index++)
                        {
                            // 日期显式读取DateOnly，禁止驱动缺省DateTime带来午夜时区猜测。
                            var value = reader.IsDBNull(index + 2) ? DBNull.Value : table.Fields[index].NativeType == "date" ? (object)reader.GetFieldValue<DateOnly>(index + 2) : reader.GetValue(index + 2);
                            // 精确值字符串不经过浮点或浏览器数值转换。
                            var scalar = Scalar(value, table.Fields[index]);
                            byteCount += Encoding.UTF8.GetByteCount(scalar ?? "null") + Encoding.UTF8.GetByteCount(table.Fields[index].Name) + 64;
                            if (byteCount > G4MappingRules.MaximumBytes)
                            {
                                throw new SemanticOperationException(422, "mapping_source_budget_exceeded");
                            }
                            row.Add(table.Fields[index].Name, new MappingSourceCell { NativeType = table.Fields[index].NativeType, Value = scalar });
                        }
                        rows.Add(row);
                    }
                }
                if (rows.Count != expected)
                {
                    throw new SemanticOperationException(422, "mapping_source_incomplete");
                }
                tables.Add(new MappingSourceTable { Dataset = dataset, Rows = rows.ToArray() });
            }
            // 事务标识仅绑定本次观察，不纳入可允许业务数值变化的语义不变量。
            await using var snapshotCommand = new NpgsqlCommand("SELECT pg_catalog.pg_current_snapshot()::text", connection, transaction);
            // 获取快照字符串前后仍在同一只读事务。
            var transactionSnapshot = (string)(await snapshotCommand.ExecuteScalarAsync(deadline.Token))!;
            await transaction.CommitAsync(deadline.Token);
            return new MappingSourceObservation
            {
                Tables = tables.ToArray(),
                CatalogFingerprint = fingerprint,
                TransactionSnapshot = transactionSnapshot,
                StartedAtUtc = started,
                FinishedAtUtc = DateTimeOffset.UtcNow,
                SecurityVerified = true
            };
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (Exception error) when (error is NpgsqlException or PgSourceException or OperationCanceledException or InvalidCastException or OverflowException or JsonException)
        {
            // 来源异常可能含标识、SQL或数据值，只返回固定脱敏分类。
            throw new SemanticOperationException(422, "mapping_source_unverified");
        }
    }

    /// <summary>枚举定义实际消费的全部字段，包含scope、单位证据和关系键。</summary>
    public static MappingFieldRef[] RequiredFields(MappingDefinition mapping)
    {
        return mapping.Entities.SelectMany(entity => new[] { entity.ScopeFields.Organization, entity.ScopeFields.Site })
            .Concat(mapping.IdentitySpecs.SelectMany(identity => new MappingFieldRef?[] { identity.OrganizationFieldRef, identity.SiteFieldRef, identity.ValidFromFieldRef, identity.ValidToFieldRef }
                .Concat(identity.ExternalIdFieldRefs).OfType<MappingFieldRef>()))
            .Concat(mapping.TemporalSpecs.SelectMany(time => new[] { time.EventTimeFieldRef, time.ObservedAtFieldRef, time.ValidFromFieldRef, time.ValidToFieldRef }.OfType<MappingFieldRef>()))
            .Concat(mapping.Properties.Select(property => property.FieldRef))
            .Concat(mapping.UnitSpecs.Select(unit => unit.SourceUnitFieldRef))
            .Concat(mapping.Relations.SelectMany(relation => relation.JoinFieldPairs.SelectMany(pair => new[] { pair.From, pair.To })))
            .Distinct().ToArray();
    }

    /// <summary>将受支持驱动标量转换为精确字符串，未知类型失败关闭。</summary>
    public static string? Scalar(object value, CatalogField field)
    {
        // 在null之前检查类型，未知类型的空样本也不能成为支持证据。
        var type = field.NativeType;
        // numeric必须有明确精度且在decimal无损范围内，拒绝无界和负scale。
        var numeric = field.Precision is >= 1 and <= 28 && field.Scale is >= 0 and <= 28
            && field.Scale <= field.Precision && type == $"numeric({field.Precision},{field.Scale})";
        // 字符长度只取系统目录格式，不从用户表达式推断类型。
        var text = type == "text" || Regex.IsMatch(type, @"^(character varying|character)\([1-9][0-9]{0,6}\)$", RegexOptions.CultureInvariant);
        // 固定时间类型同时接受PG系统format_type的显式精度变体。
        var zoned = Regex.IsMatch(type, @"^timestamp(?:\([0-6]\))? with time zone$", RegexOptions.CultureInvariant);
        // 无时区值只保留未指定语义；映射评估必须另验注册时区。
        var unzoned = Regex.IsMatch(type, @"^timestamp(?:\([0-6]\))? without time zone$", RegexOptions.CultureInvariant);
        if (!numeric && !text && !zoned && !unzoned && type is not ("smallint" or "integer" or "bigint" or "boolean" or "date" or "jsonb"))
        {
            throw new SemanticOperationException(422, "mapping_source_type_unsupported");
        }
        if (value is DBNull)
        {
            return null;
        }
        if (numeric && value is decimal number && decimal.Round(number, field.Scale!.Value) == number)
        {
            return number == 0 ? "0" : number.ToString("0.############################", CultureInfo.InvariantCulture);
        }
        if ((type == "smallint" && value is short) || (type == "integer" && value is int) || (type == "bigint" && value is long))
        {
            return ((IFormattable)value).ToString(null, CultureInfo.InvariantCulture);
        }
        if (type == "boolean" && value is bool boolean)
        {
            return boolean ? "true" : "false";
        }
        if (text && value is string content && content.Length <= 65536)
        {
            return content;
        }
        if (type == "date" && value is DateOnly date)
        {
            return date.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
        }
        if ((zoned || unzoned) && value is DateTime time && time.Ticks % 10 == 0
            && time.Kind == (zoned ? DateTimeKind.Utc : DateTimeKind.Unspecified))
        {
            return time.ToString(zoned ? "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'" : "yyyy-MM-dd'T'HH:mm:ss.fffffff", CultureInfo.InvariantCulture);
        }
        if (type == "jsonb" && value is string json && json.Length <= 65536)
        {
            // 只接收顶层对象；具体固定键及scalar类型由注册转换校验。
            using var document = G4MappingRules.ReadDocument(json);
            if (document.RootElement.ValueKind == JsonValueKind.Object)
            {
                return json;
            }
        }
        throw new SemanticOperationException(422, "mapping_source_value_invalid");
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

    /// <summary>源端LIMIT哨兵、逐列SELECT权限和系统format_type保真，不读取业务数据。</summary>
    private const string CatalogSql = """
        WITH visible_objects AS MATERIALIZED (
            SELECT c.oid, n.nspname, c.relname, c.relkind
            FROM pg_catalog.pg_class c
            JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = ANY(@schemas)
                AND pg_catalog.has_schema_privilege(n.oid, 'USAGE')
                AND c.relkind IN ('r','p','v','m','f')
                AND (pg_catalog.has_table_privilege(c.oid, 'SELECT') OR pg_catalog.has_any_column_privilege(c.oid, 'SELECT'))
            ORDER BY n.nspname COLLATE "C", c.relname COLLATE "C"
            LIMIT 101
        )
        SELECT o.nspname, o.relname, CASE WHEN o.relkind IN ('v','m') THEN 'VIEW' ELSE 'TABLE' END,
            a.attname, pg_catalog.format_type(a.atttypid, a.atttypmod), NOT (a.attnotnull OR t.typnotnull), a.attnum,
            CASE WHEN bt.oid = 1700 AND m.typmod >= 4 THEN ((m.typmod - 4) >> 16) & 65535 END,
            CASE WHEN bt.oid = 1700 AND m.typmod >= 4 THEN (((m.typmod - 4) & 2047) # 1024) - 1024 END
        FROM visible_objects o
        LEFT JOIN pg_catalog.pg_attribute a ON a.attrelid = o.oid AND a.attnum > 0 AND NOT a.attisdropped
            AND pg_catalog.has_column_privilege(o.oid, a.attnum, 'SELECT')
        LEFT JOIN pg_catalog.pg_type t ON t.oid = a.atttypid
        LEFT JOIN pg_catalog.pg_type bt ON bt.oid = CASE WHEN t.typtype = 'd' THEN t.typbasetype ELSE t.oid END
        LEFT JOIN LATERAL (SELECT CASE WHEN t.typtype = 'd' THEN t.typtypmod ELSE a.atttypmod END AS typmod) m ON true
        ORDER BY o.nspname COLLATE "C", o.relname COLLATE "C", a.attnum
        LIMIT 2001
        """;
}
