using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;

namespace OntologyPlatform.ConnectionsTests;

/// <summary>查询绑定以真实激活身份和单调修订保护读取，不仅比较发布ID。</summary>
[TestClass]
public sealed class G4QuerySourceTests
{
    /// <summary>登记顶层JSON提取保留空串、false、零与null，缺键及精度损失必须拒绝。</summary>
    [TestMethod]
    public void RegisteredJsonScalarDoesNotInventMissingValues()
    {
        // 转换来自固定发布参数，不接受自由JSONPath。
        MappingConversion Conversion(string type) => new() { Id = "extract", RegisteredId = "json-top-level-scalar", Version = "1",
            Parameters = System.Text.Json.JsonSerializer.SerializeToElement(new { key = "value", valueType = type }) };
        Assert.AreEqual("", PgQueryReader.JsonScalar("{\"value\":\"\"}", Conversion("STRING")).Lexical);
        Assert.AreEqual("false", PgQueryReader.JsonScalar("{\"value\":false}", Conversion("BOOLEAN")).Lexical);
        Assert.AreEqual("0", PgQueryReader.JsonScalar("{\"value\":0}", Conversion("DECIMAL")).Lexical);
        Assert.AreEqual("9007199254740993.20", PgQueryReader.JsonScalar("{\"value\":9007199254740993.20}", Conversion("DECIMAL")).Lexical);
        Assert.IsInstanceOfType<G4NullValue>(PgQueryReader.JsonScalar("{\"value\":null}", Conversion("STRING")));
        Assert.Throws<SemanticOperationException>(() => PgQueryReader.JsonScalar("{}", Conversion("STRING")));
        Assert.Throws<SemanticOperationException>(() => PgQueryReader.JsonScalar("{\"value\":{}}", Conversion("STRING")));
        Assert.Throws<SemanticOperationException>(() => PgQueryReader.JsonScalar("{\"value\":0.12345678901234567890123456789}", Conversion("DECIMAL")));
    }

    /// <summary>A切换到B再回到A仍是不同激活；凭据轮换和目录变化同样失效。</summary>
    [TestMethod]
    public void BindingRejectsAbaAndConnectionDrift()
    {
        // 固定原发布目录与当前激活目录，二者不得互相覆盖。
        var captured = new G4QueryBinding
        {
            MappingId = "mapping-1", MappingReleaseId = "release-a", ManifestHash = new string('a', 64),
            OriginalCatalogSnapshotId = "catalog-old", OriginalCatalogFingerprint = new string('b', 64),
            ActivationId = "activation-1", ActivationRevision = "1", CurrentCatalogSnapshotId = "catalog-current",
            CurrentCatalogFingerprint = new string('b', 64), ConnectionId = "connection-1", ConnectionRevision = "3",
            ConfigHash = new string('c', 64), SecretVersion = "2", OntologyReleaseId = "ontology-1",
            AuthorizationEpoch = "4", CapabilityVersion = new string('d', 64)
        };
        QueryBindingReader.DemandSameVersion(captured, captured with { });
        foreach (var changed in new[]
        {
            captured with { ActivationId = "activation-3", ActivationRevision = "3" },
            captured with { SecretVersion = "3" },
            captured with { CurrentCatalogSnapshotId = "catalog-new" },
            captured with { OriginalCatalogSnapshotId = "catalog-current" },
            captured with { ConnectionRevision = "4" }
        })
        {
            // 当前可见版本漂移是409，不能偷偷替换固定绑定继续执行。
            var error = Assert.Throws<SemanticOperationException>(() => QueryBindingReader.DemandSameVersion(captured, changed));
            Assert.AreEqual(409, error.Status);
            Assert.AreEqual("query_binding_stale", error.Code);
        }
    }

    /// <summary>PG原生值在投影前精确编码，不经浮点或隐式时区转换。</summary>
    [TestMethod]
    public void NativeScalarPreservesScaleAndRejectsPrecisionLoss()
    {
        // numeric目录精度是已发布字段的一部分，不能从样本猜scale。
        var numeric = new CatalogField { Name = "mass", NativeType = "numeric(20,2)", Nullable = true, Ordinal = 1, Precision = 20, Scale = 2 };
        Assert.AreEqual("9007199254740993.20", PgQueryReader.Scalar(9007199254740993.20m, numeric).Lexical);
        Assert.IsInstanceOfType<G4NullValue>(PgQueryReader.Scalar(DBNull.Value, numeric));
        Assert.Throws<SemanticOperationException>(() => PgQueryReader.Scalar(DBNull.Value, numeric with { Nullable = false }));
        Assert.Throws<SemanticOperationException>(() => PgQueryReader.Scalar(1.001m, numeric));
        // PG最多微秒，非零第七位禁止截断。
        var timestamp = numeric with { NativeType = "timestamp with time zone", Precision = null, Scale = null };
        // 固定UTC及微秒是类型事实，不受宿主时区影响。
        var utc = new DateTime(2026, 11, 14, 1, 2, 3, DateTimeKind.Utc).AddTicks(1234560);
        Assert.AreEqual("2026-11-14T01:02:03.123456Z", PgQueryReader.Scalar(utc, timestamp).Lexical);
        Assert.Throws<SemanticOperationException>(() => PgQueryReader.Scalar(utc.AddTicks(1), timestamp));
        Assert.Throws<SemanticOperationException>(() => PgQueryReader.Scalar(DateTime.SpecifyKind(utc, DateTimeKind.Unspecified), timestamp));
        Assert.Throws<SemanticOperationException>(() => PgQueryReader.Scalar(DBNull.Value, numeric with { NativeType = "double precision" }));
    }

    /// <summary>读分支预算耗尽时不能打开源连接，也不能重置五秒总期限。</summary>
    [TestMethod]
    public async Task ExhaustedDeadlineDoesNotStartSourceIo()
    {
        // 只有500毫秒提交保留区时禁止发出新源读取。
        var reader = new PgQueryReader(new PgAdapterOptions { RootCertificatePath = "/not-used", AllowedSchemas = ["production"] }, TimeProvider.System);
        // 预算检查必须先于使用任何源对象，因此空材料也不应产生网络IO。
        var error = await Assert.ThrowsAsync<SemanticOperationException>(() => reader.ReadAsync(null!, "", null!, "entity-1", null!, DateTimeOffset.UtcNow, CancellationToken.None));
        Assert.AreEqual("query_source_budget_exhausted", error.Code);
    }
}

/// <summary>独占合成PG上的适配器实测，不代替正式发布、HTTP和持久恢复闭环。</summary>
[TestClass]
public sealed class G4QuerySourceIntegrationTests
{
    /// <summary>真实TLS目录与只读源行验证厂区隔离、准确列值、零行和参数化身份。</summary>
    [TestMethod]
    public async Task ReadsScopedRowsAndProvesEmptyInIndependentTransactions()
    {
        // 当前任务驱动仅挂载本任务新生成的只读秘密文件。
        var passwordFile = Environment.GetEnvironmentVariable("G4_QUERY_SOURCE_PASSWORD_FILE");
        Assert.IsFalse(string.IsNullOrWhiteSpace(passwordFile), "真实合成源尚未准入。");
        // 秘密只停留在当前进程内，不记录到断言或日志。
        var secret = await File.ReadAllTextAsync(passwordFile!);
        // 源端固定服务身份，CA来自本任务独占证书。
        var options = new PgAdapterOptions { RootCertificatePath = Environment.GetEnvironmentVariable("G4_QUERY_SOURCE_CA")!, AllowedSchemas = ["production", "public"] };
        // 使用正式适配器解析真实系统目录，不用预填目录冒充源验证。
        var discovery = new PgSourceAdapter(options);
        // 固定允许目标，不接受任意宿主URL。
        var profile = new PgConnectionProfile { Host = "pg-source", Port = 5432, Database = "fixture", Username = "fixture_reader", SslMode = "VerifyFull", AllowedSchemas = ["production", "public"] };
        // 元数据观察独立于一秒查询分支，不重跑M3验证任务。
        var objects = (await discovery.DiscoverAsync(profile, secret, CancellationToken.None))
            .OrderBy(item => item.Schema, StringComparer.Ordinal).ThenBy(item => item.Name, StringComparer.Ordinal).ThenBy(item => item.Kind, StringComparer.Ordinal)
            .Select(item => item with { Fields = item.Fields.OrderBy(field => field.Ordinal).ThenBy(field => field.Name, StringComparer.Ordinal).ToArray() }).ToArray();
        // 身份材料明确是适配器fixture，不是伪造正式MappingRelease成功证据。
        var context = Fixture(objects);
        // 正式PG查询适配器与上层使用同一个UTC时钟边界。
        var reader = new PgQueryReader(options, TimeProvider.System);
        // 外部号只作为SQL参数，源范围仍限制为site-a。
        var query = new G4SemanticQuery
        {
            AssetId = "fixture-asset", OntologyReleaseId = "fixture-ontology", MappingReleaseIds = ["fixture-release"],
            CapabilityId = "g4_resolve_entity", CapabilityVersion = new string('a', 64), RelationshipIris = [], Depth = 1,
            MaxRows = 100, TimeoutMs = 5000, Filters = new G4QueryFilters { EntityExternalId = "asset-1" }
        };
        // 第一条真实业务读取必须产生完整行和真实事务水位。
        var found = await reader.ReadAsync(profile, secret, context, "asset", query, DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None);
        Assert.HasCount(1, found.Rows);
        Assert.AreEqual("site-a", found.Rows[0]["site_id"].Lexical);
        Assert.AreEqual("合成设备A", found.Rows[0]["label"].Lexical);
        Assert.AreEqual("2026-01-01T00:00:00.000000Z", found.Rows[0]["valid_from"].Lexical);
        Assert.IsFalse(found.Limited);
        Assert.HasCount(4, found.RecordKeyFields);
        Assert.IsFalse(string.IsNullOrWhiteSpace(found.TransactionSnapshot));
        // 历史恢复权限只检查系统目录和ACL，不调用业务ReadAsync来制造新回执。
        await reader.VerifyAccessAsync(profile, secret, context, "asset", DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None);
        // SQL样式输入只是不存在的外部号，不能突破范围或改写语句。
        var empty = await reader.ReadAsync(profile, secret, context, "asset", query with { Filters = new G4QueryFilters { EntityExternalId = "' OR true --" } }, DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None);
        Assert.HasCount(0, empty.Rows);
        Assert.IsFalse(empty.Limited);
        Assert.IsTrue(empty.CompletedAtUtc >= empty.StartedAtUtc);
        // 独立合成表保留null结束；目录真实声明可空，不能被窗口WHERE静默丢掉。
        var unknownContext = Fixture(objects, "query_assets_unknown");
        // 纳秒窗口通过numeric精确比较，null端点必须保留不确定性。
        var unknown = await reader.ReadAsync(profile, secret, unknownContext, "asset", query with
        {
            Filters = new G4QueryFilters { EntityExternalId = "asset-1", ValidFrom = "2026-11-14T00:00:00.000000001Z", ValidTo = "2026-11-15T00:00:00.000000001Z" }
        }, DateTimeOffset.UtcNow.AddSeconds(5), CancellationToken.None);
        Assert.HasCount(0, unknown.Rows);
        Assert.IsFalse(unknown.Limited);
        Assert.IsTrue(unknown.Indeterminate, "未知时间不是完整零行，禁止解释为EMPTY。");
    }

    /// <summary>只构造适配器测试材料；正式发布生命周期由S1 HTTP验收另证。</summary>
    private static G4QueryBindingContext Fixture(CatalogObject[] objects, string tableName = "assets")
    {
        // 同M1算法计算真实目录的当前内容身份，绝不调用M4结果规范器重算历史目录。
        var fingerprint = Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(System.Text.Json.JsonSerializer.SerializeToUtf8Bytes(
            new { AdapterVersion = "pg-m1-v1", Objects = objects }, G4ConnectionJson.Options)));
        // 真实已发现对象的精确名称与序号作为字段引用来源。
        var table = objects.Single(item => item.Schema == "production" && item.Name == tableName);
        // fixture目录身份仅限当前适配器测试。
        var dataset = new MappingDatasetRef { SnapshotId = "fixture-catalog", Schema = "production", Name = tableName, Kind = "TABLE" };
        // 从真实目录取得精确列引用，不从用户字符串拼接序号。
        MappingFieldRef Field(string name) => new() { DatasetRef = dataset, Name = name, Ordinal = table.Fields.Single(item => item.Name == name).Ordinal };
        // 源范围由服务器上下文固定，不能由外部号参数扩张。
        var scope = new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a"] };
        // 真实目录视图保存内容指纹和身份，不包含数据行。
        var catalog = new CatalogSnapshotView { SnapshotId = dataset.SnapshotId, ConnectionId = "fixture-connection", ConfigRevision = 1,
            SecretVersion = 1, Scope = scope, SchemaFingerprint = fingerprint, CapturedAtUtc = DateTimeOffset.UtcNow, Status = "READY", Objects = objects };
        // 类型化映射fixture只消费资产表标签和身份，不声明正式本体发布通过。
        var mapping = new MappingDefinition
        {
            Entities = [new MappingEntityBinding { Id = "asset", EntityClassIri = "urn:synthetic:mapping:Asset", DatasetRef = dataset,
                IdentitySpecId = "identity", TemporalSpecId = "time", ScopeFields = new MappingScopeFields { Organization = Field("organization_id"), Site = Field("site_id") } }],
            IdentitySpecs = [new MappingIdentitySpec { Id = "identity", OrganizationFieldRef = Field("organization_id"), SiteFieldRef = Field("site_id"),
                SourceNamespace = "fixture", ExternalIdFieldRefs = [Field("asset_id")], ValidFromFieldRef = Field("valid_from"), ValidToFieldRef = Field("valid_to") }],
            TemporalSpecs = [new MappingTemporalSpec { Id = "time", EventTimeFieldRef = Field("valid_from"), ObservedAtFieldRef = Field("valid_from"),
                ValidFromFieldRef = Field("valid_from"), ValidToFieldRef = Field("valid_to"), TimezonePolicy = new MappingTimezonePolicy { Kind = "UTC", ZoneId = null }, Precision = "MICROSECOND" }],
            Properties = [new MappingPropertyBinding { Id = "label", EntityBindingId = "asset", PropertyIri = "urn:synthetic:mapping:label",
                FieldRef = Field("label"), ConversionId = null, UnitSpecId = null, NullPolicy = "REJECT_NULL" }], Relations = [], Conversions = [], UnitSpecs = []
        };
        // 仅供适配器读取；未进入正式发布表或宣称此hash是正式manifest原件。
        var binding = new MappingVersionBinding { SourceConnectionId = catalog.ConnectionId, ConnectionRevision = 1, ConfigHash = new string('a',64),
            SourceType = "POSTGRESQL", SourceCatalogSnapshotId = catalog.SnapshotId, SourceCatalogFingerprint = fingerprint,
            OntologyReleaseId = "fixture-ontology", OntologyManifestHash = new string('b',64), MappingHash = new string('c',64), ValidationHash = new string('d',64),
            ImpactHash = new string('e',64), AssessmentId = "fixture-assessment", AdapterVersion = "pg-mapping-v1", ExecutorVersion = "mapping-validator-v1",
            CanonicalVersion = "mapping-c14n-v1", SecretVersion = 1, AuthorizationEpoch = 1 };
        return new G4QueryBindingContext
        {
            Binding = new G4QueryBinding { MappingId = "fixture-mapping", MappingReleaseId = "fixture-release", ManifestHash = new string('f',64),
                OriginalCatalogSnapshotId = catalog.SnapshotId, OriginalCatalogFingerprint = fingerprint, CurrentCatalogSnapshotId = catalog.SnapshotId,
                CurrentCatalogFingerprint = fingerprint, ActivationId = "fixture-activation", ActivationRevision = "1", ConnectionId = catalog.ConnectionId,
                ConnectionRevision = "1", ConfigHash = binding.ConfigHash, SecretVersion = "1", OntologyReleaseId = binding.OntologyReleaseId,
                AuthorizationEpoch = "1", CapabilityVersion = new string('a',64) },
            Scope = scope, OriginalCatalog = catalog, CurrentCatalog = catalog,
            Manifest = new MappingReleaseManifest { SchemaVersion = "g4.mapping.v1", MappingReleaseId = "fixture-release", MappingId = "fixture-mapping",
                Scope = scope, OriginDraftId = "fixture-draft", OriginDraftRevision = 1, Binding = binding, Mapping = mapping, CreatedAtUtc = DateTimeOffset.UtcNow,
                ReviewReceipt = new MappingReviewReceipt { ProposalId = "fixture-proposal", BindingHash = new string('a',64), SubmittedBy = "fixture-author",
                    DecidedBy = "fixture-reviewer", DecidedAtUtc = DateTimeOffset.UtcNow } }
        };
    }
}
