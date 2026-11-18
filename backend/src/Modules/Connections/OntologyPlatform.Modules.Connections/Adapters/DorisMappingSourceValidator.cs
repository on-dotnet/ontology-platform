using System.Globalization;
using MySqlConnector;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>用 Doris 4.0.8 的实际建表语句核对合成源的物理模型、列和完整键序。</summary>
internal static class DorisMappingSourceValidator
{
    /// <summary>单表实体切片只接受冻结的组织、厂区、实体键及已发布的目录引用。</summary>
    internal static CatalogObject EntityTable(MappingEntityBinding entity, CatalogSnapshotView original,
        CatalogSnapshotView current, MappingDefinition mapping)
    {
        // 同名对象没有固定的 schema、种类和列序时不能重新绑定。
        var dataset = entity.DatasetRef;
        if (dataset.SnapshotId != original.SnapshotId || dataset.Schema != "fixture" || dataset.Name != "dmq_entity"
            || entity.ScopeFields.Organization.Name != "org_id" || entity.ScopeFields.Site.Name != "site_id") throw InvalidShape();
        // 原目录与当前目录可属于不同的正式作业，但本表的完整字段必须一致。
        var table = current.Objects.SingleOrDefault(t => t.Schema == dataset.Schema && t.Name == dataset.Name && t.Kind == "TABLE") ?? throw InvalidShape();
        // 用序号和名称同时核对草稿或已发布定义中所有实际引用。
        var prior = original.Objects.SingleOrDefault(t => t.Schema == dataset.Schema && t.Name == dataset.Name && t.Kind == "TABLE");
        if (prior is null || !prior.Fields.SequenceEqual(table.Fields) ||
            PgMappingSourceValidator.RequiredFields(mapping).Where(f => f.DatasetRef == dataset)
                .Any(f => !table.Fields.Any(c => c.Ordinal == f.Ordinal && c.Name == f.Name))) throw InvalidShape();
        return table;
    }

    /// <summary>固定模板的组织、厂区、业务键与四个业务时间必须对应同一冻结数据集。</summary>
    internal static bool SupportsEntityPlan(MappingEntityBinding entity, MappingIdentitySpec identity, MappingTemporalSpec temporal)
    {
        // 名称和引用的目录身份同时参与比较，防止把另一个同名字段用于固定谓词。
        bool Bound(MappingFieldRef? field, string name) => field is not null && field.DatasetRef == entity.DatasetRef && field.Name == name;
        return Bound(identity.OrganizationFieldRef, "org_id") && Bound(identity.SiteFieldRef, "site_id")
            && identity.ExternalIdFieldRefs is [var key] && Bound(key, "entity_id")
            && Bound(identity.ValidFromFieldRef, "valid_from") && Bound(identity.ValidToFieldRef, "valid_to")
            && Bound(temporal.ValidFromFieldRef, "valid_from") && Bound(temporal.ValidToFieldRef, "valid_to")
            && Bound(temporal.EventTimeFieldRef, "event_at") && Bound(temporal.ObservedAtFieldRef, "observed_at")
            && temporal.TimezonePolicy is { Kind: "REGISTERED_ZONE", ZoneId: "Etc/UTC" } && temporal.Precision == "MICROSECOND";
    }

    /// <summary>当前目录与已冻结的物理模型共同决定允许执行的源语义。</summary>
    internal static async Task<string> CheckCatalogAsync(MySqlConnection connection, DorisConnectionProfile profile, CatalogSnapshotView snapshot)
    {
        // 目录沿用首次发现时的同一真实读取器和原字节算法。
        var catalog = ConnectionApplicationService.CanonicalCatalog(await DorisSourceAdapter.ReadCatalogAsync(connection),
            new DorisConnectionConfig { Profile = profile });
        if (snapshot.Status != "READY" || catalog.Fingerprint != snapshot.SchemaFingerprint
            || ConnectionApplicationService.Encode(catalog.Objects) != ConnectionApplicationService.Encode(snapshot.Objects)
            || !catalog.Objects.Select(t => (t.Schema, t.Name, t.Kind)).SequenceEqual(new[] {
                ("fixture", "dmq_entity", "TABLE"), ("fixture", "dmq_target", "TABLE") })) throw InvalidShape();
        await CheckTableAsync(connection, false);
        await CheckTableAsync(connection, true);
        return MappingValidationService.Digest(new { sourceType = "DORIS", adapterVersion = "doris-mapping-v1",
            catalogFingerprint = catalog.Fingerprint, tables = catalog.Objects.Select(t => new { database = t.Schema, name = t.Name,
                tableModel = "UNIQUE", mergeOnWrite = true, keyColumns = new[] { "org_id", "site_id", t.Name == "dmq_entity" ? "entity_id" : "target_id" } }) });
    }

    /// <summary>评估与历史 ACL 核验使用相同前后验；只在评估模式读取实体业务行。</summary>
    internal static Task<MappingSourceObservation> ObserveAsync(DorisSourceAdapter adapter, DorisConnectionProfile profile,
        string secret, CatalogSnapshotView original, CatalogSnapshotView current, MappingDefinition mapping, ResourceScope scope,
        bool readRows, DateTimeOffset deadline, CancellationToken token)
    {
        DorisAdapterOptions.Validate(profile, scope);
        G4MappingRules.Definition(mapping);
        if (mapping.Entities is not [var entity] || original.Scope.OrganizationId != scope.OrganizationId
            || current.Scope.OrganizationId != scope.OrganizationId || !scope.SiteIds.All(s => original.Scope.SiteIds.Contains(s) && current.Scope.SiteIds.Contains(s)))
            throw InvalidShape();
        // 评估期间验证的列包含全固定投影，平台调用端必须给出完整字段授权。
        var table = EntityTable(entity, original, current, mapping);
        // 开始时刻覆盖本次连接、目录和权限检查。
        var start = DateTimeOffset.UtcNow;
        return adapter.ReadBranchAsync(profile, secret, deadline, TimeProvider.System, async connection =>
        {
            // 当前目录与真实模型均经该业务分支的绝对期限约束。
            var shape = await CheckCatalogAsync(connection, profile, current);
            // 历史授权核验不重放业务 SELECT。
            var result = new List<Dictionary<string, MappingSourceCell>>();
            if (readRows)
            {
                foreach (var raw in await DorisQueryReader.ReadPlanAsync(connection, scope, null, null))
                {
                    result.Add(table.Fields.ToDictionary(f => f.Name,
                        f => new MappingSourceCell { NativeType = f.NativeType, Value = Lexical(raw[f.Name], f) }, StringComparer.Ordinal));
                }
            }
            if (await CheckCatalogAsync(connection, profile, current) != shape) throw InvalidShape();
            return new MappingSourceObservation { Tables = [new MappingSourceTable { Dataset = entity.DatasetRef, Rows = result.ToArray() }],
                CatalogFingerprint = current.SchemaFingerprint, SourceSemanticsHash = shape, WatermarkKind = "UNKNOWN", Watermark = null,
                StartedAtUtc = start, FinishedAtUtc = DateTimeOffset.UtcNow, SecurityVerified = true };
        }, token);
    }

    /// <summary>按目录声明解释实际驱动标量，保留定点标度及六位无时区时间。</summary>
    internal static string? Lexical(object? value, CatalogField field) => value switch
    {
        null when field.Nullable => null,
        string text when field.NativeType.StartsWith("varchar(", StringComparison.Ordinal) => text,
        decimal number when field.NativeType.StartsWith("decimalv3(", StringComparison.Ordinal) && field.Precision is int p && field.Scale is int s =>
            DorisMappingTypeRules.DecimalValue(number.ToString("F" + s, CultureInfo.InvariantCulture), p, s).Lexical,
        DateTime local when field.NativeType == "datetime(6)" && local.Kind == DateTimeKind.Unspecified && local.Ticks % 10 == 0 =>
            local.ToString("yyyy-MM-dd HH:mm:ss.ffffff", CultureInfo.InvariantCulture),
        long integer when field.NativeType == "bigint" => integer.ToString(CultureInfo.InvariantCulture),
        _ => throw InvalidShape()
    };

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
