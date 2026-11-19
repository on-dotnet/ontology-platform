using System.Globalization;
using System.Text;
using System.Text.RegularExpressions;
using OntologyPlatform.Contracts;
using Oracle.ManagedDataAccess.Client;

namespace OntologyPlatform.Modules.Connections;

/// <summary>在 Oracle 的原始目录、实际只读会话和固定两张表之间建立受控映射。</summary>
internal static class OracleMappingSourceValidator
{
    /// <summary>固定投影的物理列序来自首次发现前已冻结的两表 DDL。</summary>
    private static readonly string[] Columns = ["ROW_ID", "JOIN_KEY", "VAL", "ORG_ID", "SITE_ID", "EXT_ID", "LABEL", "FROM_TS", "TO_TS", "EVENT_TS", "OBSERVED_TS"];

    /// <summary>用持久索引身份及 Oracle M2 历史算法独立复核每份原始快照。</summary>
    internal static void DemandSnapshot(CatalogSnapshotView view, CatalogSnapshotRecord row, string connection, ResourceScope scope)
    {
        if (view.Status != "READY" || view.SnapshotId != row.Id || row.ConnectionId != connection || view.ConnectionId != connection
            || row.OrganizationId != scope.OrganizationId || view.Scope.OrganizationId != scope.OrganizationId
            || !scope.SiteIds.All(row.SiteIds.Contains) || !scope.SiteIds.All(view.Scope.SiteIds.Contains)
            || view.SecretVersion != row.SecretVersion || view.SchemaFingerprint != ConnectionApplicationService.CanonicalCatalog(view.Objects, "oracle-m2-v1").Fingerprint)
            throw new SemanticOperationException(409, "mapping_catalog_stale");
    }

    /// <summary>核对当前与历史的目录、字段 ordinal、原始 quoted 对象身份及范围列。</summary>
    internal static CatalogObject EntityTable(MappingEntityBinding entity, CatalogSnapshotView original,
        CatalogSnapshotView current, MappingDefinition mapping)
    {
        // 同名字段不能使另一物理对象绑定到本源模板。
        var dataset = entity.DatasetRef;
        if (dataset.SnapshotId != original.SnapshotId || dataset.Kind != "TABLE"
            || (dataset.Schema, dataset.Name) is not (("PRODUCTION", "OMQ_ENTITY") or ("CaseOwner", "OmqTarget"))
            || entity.ScopeFields.Organization.Name != "ORG_ID" || entity.ScopeFields.Site.Name != "SITE_ID"
            || entity.ScopeFields.Organization.DatasetRef != dataset || entity.ScopeFields.Site.DatasetRef != dataset) throw Shape();
        // 原目录仍然是草稿各字段引用的身份。
        var prior = original.Objects.SingleOrDefault(t => t.Schema == dataset.Schema && t.Name == dataset.Name && t.Kind == "TABLE");
        // 当前目录须可以精确解释全部原有字段。
        var table = current.Objects.SingleOrDefault(t => t.Schema == dataset.Schema && t.Name == dataset.Name && t.Kind == "TABLE") ?? throw Shape();
        if (prior is null || !prior.Fields.SequenceEqual(table.Fields)
            || PgMappingSourceValidator.RequiredFields(mapping).Where(f => f.DatasetRef == dataset)
                .Any(f => !table.Fields.Any(c => c.Name == f.Name && c.Ordinal == f.Ordinal))) throw Shape();
        RequireShape(table);
        return table;
    }

    /// <summary>对两张物理表核对批准的最大声明、长度、标度、字符语义、空值与顺序。</summary>
    internal static void RequireShape(CatalogObject table)
    {
        // 标识大小写决定关系侧和键标度。
        var target = (table.Schema, table.Name) == ("CaseOwner", "OmqTarget");
        if ((!target && (table.Schema, table.Name) != ("PRODUCTION", "OMQ_ENTITY")) || table.Kind != "TABLE"
            || !table.Fields.Select(f => f.Name).SequenceEqual(Columns, StringComparer.Ordinal)) throw Shape();
        foreach (var field in table.Fields)
        {
            // 字典中的列序为一基；每一个引用都要对应本表的已审投影。
            var index = Array.IndexOf(Columns, field.Name);
            if (field.Ordinal != index + 1 || field.Nullable != (index is 1 or 2 or 6)
                || field.OracleMetadata is not { SupportStatus: "SUPPORTED", DataTypeOwner: null, TimeZoneKind: "NONE" } meta) throw Shape();
            // 只接受该表精确的 NUMBER 声明、AL32UTF8 字符列或有界精度的无时区时间。
            var accepted = index switch
            {
                0 => field.NativeType == "NUMBER" && field.Precision == 18 && field.Scale == 0,
                1 => field.NativeType == "NUMBER" && field.Precision == (target ? 13 : 12) && field.Scale == (target ? 2 : 1),
                2 => field.NativeType == "NUMBER" && field.Precision == 28 && field.Scale == 6,
                >= 3 and <= 6 => field.NativeType == "VARCHAR2" && meta.CharSemantics == "CHAR" && meta.CharLength == (index == 6 ? 48 : 32)
                    && meta.ByteLength == meta.CharLength * 4,
                _ => field.NativeType == "TIMESTAMP(6)" && meta.FractionalSecondsPrecision == 6
            };
            if (!accepted) throw Shape();
        }
    }

    /// <summary>身份、组织、厂区与四个业务时间必须来自同一已发布模板。</summary>
    internal static bool SupportsEntityPlan(MappingEntityBinding entity, MappingIdentitySpec identity, MappingTemporalSpec temporal)
    {
        // 不能由另一表的同名列提供业务身份或时间。
        bool Bound(MappingFieldRef? field, string name) => field is not null && field.DatasetRef == entity.DatasetRef && field.Name == name;
        return Bound(identity.OrganizationFieldRef, "ORG_ID") && Bound(identity.SiteFieldRef, "SITE_ID")
            && identity.ExternalIdFieldRefs is [var key] && Bound(key, "EXT_ID")
            && Bound(identity.ValidFromFieldRef, "FROM_TS") && Bound(identity.ValidToFieldRef, "TO_TS")
            && Bound(temporal.ValidFromFieldRef, "FROM_TS") && Bound(temporal.ValidToFieldRef, "TO_TS")
            && Bound(temporal.EventTimeFieldRef, "EVENT_TS") && Bound(temporal.ObservedAtFieldRef, "OBSERVED_TS")
            && temporal.TimezonePolicy is { Kind: "REGISTERED_ZONE", ZoneId: "Etc/UTC" } && temporal.Precision == "MICROSECOND";
    }

    /// <summary>只允许准确两个源对象之间的异标度 NUMBER 等值及半开区间关系。</summary>
    internal static bool SupportsRelation(MappingDefinition mapping, MappingRelationBinding relation)
    {
        // 两侧字段绑定分别由已发布实体确定。
        var from = mapping.Entities.SingleOrDefault(e => e.Id == relation.FromBindingId)?.DatasetRef;
        // 目标标识区分大小写。
        var to = mapping.Entities.SingleOrDefault(e => e.Id == relation.ToBindingId)?.DatasetRef;
        return from is { Schema: "PRODUCTION", Name: "OMQ_ENTITY" } && to is { Schema: "CaseOwner", Name: "OmqTarget" }
            && relation.Cardinality == "ONE_TO_MANY" && relation.TemporalJoinPolicy == "HALF_OPEN_OVERLAP"
            && relation.JoinFieldPairs is [{ From.Name: "JOIN_KEY", To.Name: "JOIN_KEY" } pair] && pair.From.DatasetRef == from && pair.To.DatasetRef == to;
    }

    /// <summary>在事务外采集新鲜 M2 目录、实际主键、对象标识和 NLS/字符排序。</summary>
    internal static async Task<string> CheckCatalogAsync(OracleConnection connection, CatalogSnapshotView snapshot, CancellationToken token)
    {
        // 对业务读者实际可见的原 M2 全量目录重算，而非对预设合成列散列。
        var catalog = ConnectionApplicationService.CanonicalCatalog(await OracleSourceAdapter.ReadCatalogAsync(connection, token), "oracle-m2-v1");
        if (catalog.Fingerprint != snapshot.SchemaFingerprint || catalog.Objects.Length != 2
            || ConnectionApplicationService.Encode(catalog.Objects) != ConnectionApplicationService.Encode(snapshot.Objects)) throw Shape();
        foreach (var table in catalog.Objects) RequireShape(table);
        // 每行要求完整启用、已验证、非延迟的单列 PK；非二进制文本/会话语义不能发布。
        using var physical = connection.CreateCommand();
        physical.CommandText = """
            SELECT o.OWNER,o.OBJECT_NAME,o.OBJECT_ID,o.DATA_OBJECT_ID
            FROM ALL_OBJECTS o JOIN ALL_CONSTRAINTS k ON k.OWNER=o.OWNER AND k.TABLE_NAME=o.OBJECT_NAME
            JOIN ALL_CONS_COLUMNS c ON c.OWNER=k.OWNER AND c.CONSTRAINT_NAME=k.CONSTRAINT_NAME
            WHERE (o.OWNER,o.OBJECT_NAME) IN (('PRODUCTION','OMQ_ENTITY'),('CaseOwner','OmqTarget'))
              AND o.OBJECT_TYPE='TABLE' AND o.STATUS='VALID' AND k.CONSTRAINT_TYPE='P'
              AND k.STATUS='ENABLED' AND k.VALIDATED='VALIDATED' AND k.DEFERRABLE='NOT DEFERRABLE'
              AND c.POSITION=1 AND c.COLUMN_NAME='ROW_ID'
              AND NOT EXISTS (SELECT 1 FROM ALL_CONS_COLUMNS x WHERE x.OWNER=c.OWNER AND x.CONSTRAINT_NAME=c.CONSTRAINT_NAME AND x.POSITION<>1)
              AND NOT EXISTS (SELECT 1 FROM ALL_TAB_COLUMNS x WHERE x.OWNER=o.OWNER AND x.TABLE_NAME=o.OBJECT_NAME
                AND x.DATA_TYPE='VARCHAR2' AND (x.COLLATION IS NULL OR x.COLLATION NOT IN ('BINARY','USING_NLS_COMP')))
              AND (SELECT VALUE FROM NLS_DATABASE_PARAMETERS WHERE PARAMETER='NLS_CHARACTERSET')='AL32UTF8'
              AND (SELECT COUNT(*) FROM NLS_SESSION_PARAMETERS WHERE PARAMETER IN ('NLS_COMP','NLS_SORT') AND VALUE='BINARY')=2
            ORDER BY o.OWNER,o.OBJECT_NAME
            """;
        // 将物理对象身份绑定到本次观察；同名重建不能伪造相同模型。
        var keys = new List<object>();
        await using var cursor = await physical.ExecuteReaderAsync(token);
        while (await cursor.ReadAsync(token))
        {
            if (keys.Count >= 2 || cursor.IsDBNull(2) || cursor.IsDBNull(3)) throw Shape();
            keys.Add(new { owner = cursor.GetString(0), table = cursor.GetString(1), objectId = cursor.GetInt64(2), dataObjectId = cursor.GetInt64(3) });
        }
        if (keys.Count != 2) throw Shape();
        return MappingValidationService.Digest(new { adapterVersion = "oracle-mapping-v1", catalog.Fingerprint, keys });
    }

    /// <summary>同一真实只读事务内读取所有映射表，目录与 ACL 在事务外复核。</summary>
    internal static async Task<MappingSourceObservation> ObserveAsync(OracleSourceAdapter adapter, OracleConnectionProfile profile,
        string secret, CatalogSnapshotView original, CatalogSnapshotView current, MappingDefinition mapping, ResourceScope scope,
        bool readRows, DateTimeOffset deadline, CancellationToken token)
    {
        OracleAdapterOptions.Validate(profile, scope);
        G4MappingRules.Definition(mapping);
        // 单表切片和双表关系切片共用全部授权及证明。
        var tables = mapping.Entities.Select(e => (Entity: e, Table: EntityTable(e, original, current, mapping))).ToArray();
        if (tables.Select(t => t.Table.Name).Order(StringComparer.Ordinal).ToArray() is not (["OMQ_ENTITY"] or ["OMQ_ENTITY", "OmqTarget"])) throw Shape();
        // 工作时间覆盖身份、真实源事务及读取后的复核。
        var start = DateTimeOffset.UtcNow;
        using var work = CancellationTokenSource.CreateLinkedTokenSource(token);
        work.CancelAfter(deadline > start ? deadline - start : TimeSpan.Zero);
        await using var connection = await adapter.OpenMappingAsync(secret, Guid.NewGuid(), work.Token);
        // 前后检查的物理标识和字段散列必须相同。
        var shape = await CheckCatalogAsync(connection, current, work.Token);
        // ACL 恢复路径没有业务 SELECT，仍须证明本次读取权限和新鲜目录。
        var samples = new List<MappingSourceTable>();
        if (readRows)
        {
            await using var transaction = await OracleSourceAdapter.BeginMappingAsync(connection, work.Token);
            foreach (var (entity, table) in tables)
            {
                // 有序真实投影不可丢弃哨兵后声称完整。
                var rows = await OracleSourceAdapter.ReadMappingAsync(connection, transaction, table.Schema == "CaseOwner", work.Token);
                if (rows.Count > 100) throw new SemanticOperationException(422, "mapping_source_budget_exceeded");
                samples.Add(new MappingSourceTable { Dataset = entity.DatasetRef, Rows = rows.Select(row => Cells(row, table)).ToArray() });
            }
            await transaction.CommitAsync(work.Token);
        }
        await OracleSourceAdapter.VerifyMappingAccessAsync(connection, work.Token);
        if (await CheckCatalogAsync(connection, current, work.Token) != shape) throw Shape();
        return new MappingSourceObservation { IsOracle = true, Tables = samples.ToArray(), CatalogFingerprint = current.SchemaFingerprint,
            SourceSemanticsHash = shape, WatermarkKind = "UNKNOWN", Watermark = null, SecurityVerified = true,
            StartedAtUtc = start, FinishedAtUtc = DateTimeOffset.UtcNow };
    }

    /// <summary>使用驱动原生十进制、时间和原串生成一行准确映射输入，禁止舍入。</summary>
    internal static Dictionary<string, MappingSourceCell> Cells(OracleMappingRow row, CatalogObject table)
    {
        // 原值严格对应固定 SELECT 顺序，不按忽略大小写的名字扩展投影。
        object?[] values = [row.Id, row.JoinKey, row.Value, row.Organization, row.Site, row.External, row.Label, row.From, row.To, row.Event, row.Observed];
        if (!Regex.IsMatch(row.External, @"\A[A-Za-z0-9._:-]{1,32}\z", RegexOptions.CultureInvariant)
            || row.From >= row.To) throw Shape();
        // 词法由已核目录生成，同一套解释用于 Mapping 和 Query。
        return table.Fields.ToDictionary(f => f.Name, f => new MappingSourceCell
        {
            NativeType = f.Name == "ROW_ID" ? "NUMBER(18,0)" : f.NativeType,
            Value = values[f.Ordinal - 1] switch
            {
                null when f.Nullable => null,
                long n when n is >= -999999999999999999L and <= 999999999999999999L => n.ToString(CultureInfo.InvariantCulture),
                decimal n when f.Scale is int scale && decimal.Round(n, scale) == n => DorisMappingTypeRules.DecimalValue(
                    n.ToString("F" + scale, CultureInfo.InvariantCulture), f.Precision!.Value, scale).Lexical,
                string s when s.Length > 0 && s.EnumerateRunes().Count() <= f.OracleMetadata!.CharLength
                    && Encoding.UTF8.GetByteCount(s) <= f.OracleMetadata.ByteLength => s,
                DateTime t when t.Kind == DateTimeKind.Unspecified && t.Ticks % 10 == 0 => t.ToString("yyyy-MM-dd HH:mm:ss.ffffff", CultureInfo.InvariantCulture),
                _ => throw Shape()
            }
        }, StringComparer.Ordinal);
    }

    /// <summary>固定脱敏失败，不输出源内容。</summary>
    private static SemanticOperationException Shape() => new(422, "mapping_source_shape_invalid");
}
