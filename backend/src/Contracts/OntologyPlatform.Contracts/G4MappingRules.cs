using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace OntologyPlatform.Contracts;

/// <summary>映射公开合同的形状守卫，引用存在性与当前授权由应用服务另验。</summary>
public static class G4MappingRules
{
    /// <summary>JSON和canonical制品的独立一MiB上限。</summary>
    public const int MaximumBytes = 1024 * 1024;

    /// <summary>JavaScript可精确表示的最大整数。</summary>
    public const long MaximumRevision = 9007199254740991;

    /// <summary>读取封闭判别请求，拒绝重复键与分支字段混用。</summary>
    /// <param name="json">受请求大小预算约束的JSON。</param>
    /// <returns>发布或回滚的严格模型。</returns>
    public static MappingProposalCreateRequest ReadProposal(string json)
    {
        try
        {
            // 先检测重复键，不能让反序列化器最后值覆盖审批输入。
            using var document = ReadDocument(json);
            // UTC精确格式属于wire合同，不能由DateTimeOffset容错解析掩盖。
            var expiry = document.RootElement.GetProperty("expiresAtUtc").GetString();
            Require(expiry is not null && Regex.IsMatch(expiry, @"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{7}Z$", RegexOptions.CultureInvariant));
            // 类型判别和未映射字段在统一序列化器中严格拒绝。
            var proposal = JsonSerializer.Deserialize<MappingProposalCreateRequest>(json, G4MappingJson.Options);
            Require(proposal is not null);
            Validate(proposal!);
            return proposal!;
        }
        catch (Exception error) when (error is JsonException or KeyNotFoundException or InvalidOperationException or FormatException)
        {
            throw new SemanticOperationException(400, "mapping_payload_invalid");
        }
    }

    /// <summary>读取有界JSON并递归拒绝所有对象中的重复键。</summary>
    /// <param name="json">原始请求或规范化前的内容。</param>
    /// <returns>由调用者释放的解析文档。</returns>
    public static JsonDocument ReadDocument(string json)
    {
        Require(json is not null && Encoding.UTF8.GetByteCount(json) <= MaximumBytes);
        // 有界深度与严格尾随内容避免解析资源放大。
        var document = JsonDocument.Parse(json!, new JsonDocumentOptions { MaxDepth = 48 });
        try
        {
            UniqueKeys(document.RootElement);
            return document;
        }
        catch
        {
            document.Dispose();
            throw;
        }
    }

    /// <summary>验证提案完整版本输入，不替代数据库关联检查。</summary>
    /// <param name="request">已解析的发布或回滚请求。</param>
    public static void Validate(MappingProposalCreateRequest request)
    {
        Require(request.SchemaVersion == "g4.mapping.v1");
        Scope(request.Scope);
        Command(request.Command, true);
        Binding(request.Binding);
        Active(request.ExpectedActive);
        switch (request)
        {
            case MappingPublishProposalRequest publish:
                Identifier(publish.DraftId);
                Revision(publish.DraftRevision);
                break;
            case MappingRollbackProposalRequest rollback:
                Identifier(rollback.TargetReleaseId);
                Hash(rollback.ManifestHash);
                Require(rollback.ExpectedActive.ReleaseId is not null && rollback.ExpectedActive.ReleaseId != rollback.TargetReleaseId);
                break;
            default:
                throw new SemanticOperationException(400, "mapping_payload_invalid");
        }
    }

    /// <summary>所有影响审批的版本均必须明确且来源类型在首切片范围内。</summary>
    /// <param name="binding">不可变版本绑定。</param>
    public static void Binding(MappingVersionBinding binding)
    {
        Require(binding is not null);
        Identifier(binding!.SourceConnectionId);
        Identifier(binding.SourceCatalogSnapshotId);
        Identifier(binding.OntologyReleaseId);
        Identifier(binding.AssessmentId);
        Revision(binding.ConnectionRevision);
        Revision(binding.SecretVersion);
        Revision(binding.AuthorizationEpoch);
        foreach (var hash in new[] { binding.ConfigHash, binding.SourceCatalogFingerprint, binding.OntologyManifestHash, binding.MappingHash, binding.ValidationHash, binding.ImpactHash })
        {
            Hash(hash);
        }
        Require(binding.SourceType == "POSTGRESQL" && binding.AdapterVersion == "pg-mapping-v1"
            && binding.ExecutorVersion == "mapping-validator-v1" && binding.CanonicalVersion == "mapping-c14n-v1");
    }

    /// <summary>要求完整非空组织厂区集合，不进行授权裁剪。</summary>
    /// <param name="scope">资源scope。</param>
    public static void Scope(ResourceScope scope)
    {
        Require(scope is not null);
        Identifier(scope!.OrganizationId);
        Require(scope.SiteIds is { Length: >= 1 and <= 16 });
        foreach (var site in scope.SiteIds)
        {
            Identifier(site);
        }
        Require(scope.SiteIds.Distinct(StringComparer.Ordinal).Count() == scope.SiteIds.Length);
    }

    /// <summary>CAS必须同时固定ID与修订，首次仅允许null加0。</summary>
    /// <param name="active">预期指针。</param>
    public static void Active(MappingExpectedActive active)
    {
        Require(active is not null && active.ActivationRevision >= 0 && active.ActivationRevision <= MaximumRevision);
        Require((active!.ReleaseId is null) == (active.ActivationRevision == 0));
        if (active.ReleaseId is not null)
        {
            Identifier(active.ReleaseId);
        }
    }

    /// <summary>命令仍沿已有四字段合同，创建与修改修订分离。</summary>
    /// <param name="command">幂等命令上下文。</param>
    /// <param name="create">创建对象时为真。</param>
    public static void Command(CommandContext command, bool create)
    {
        Require(command is not null);
        Identifier(command!.CommandId);
        Identifier(command.IdempotencyKey);
        Require(!string.IsNullOrWhiteSpace(command.Reason) && command.Reason.Length <= 512 && !command.Reason.Any(char.IsControl));
        Require(create ? command.ExpectedRevision == 0 : command.ExpectedRevision is >= 1 and <= MaximumRevision);
    }

    /// <summary>验证定义的封闭引用和注册转换。</summary>
    /// <param name="mapping">完整定义。</param>
    public static void Definition(MappingDefinition mapping)
    {
        Require(mapping is not null && mapping.Entities is { Length: >= 1 and <= 12 }
            && mapping.Properties is { Length: <= 24 } && mapping.Relations is { Length: <= 12 }
            && mapping.IdentitySpecs is { Length: <= 12 } && mapping.TemporalSpecs is { Length: <= 12 }
            && mapping.Conversions is { Length: <= 24 } && mapping.UnitSpecs is { Length: <= 24 });
        // 每个引用空间独立且无重复，不允许后写覆盖前写。
        var entities = Index(mapping!.Entities, item => item.Id);
        // 身份、时间和转换均按固定ID解析。
        var identities = Index(mapping.IdentitySpecs, item => item.Id);
        // 时间定义不能回退到宿主本地时区。
        var temporal = Index(mapping.TemporalSpecs, item => item.Id);
        // 转换登记与实例标识分离。
        var conversions = Index(mapping.Conversions, item => item.Id);
        // 单位证据实例必须真实引用字段。
        var units = Index(mapping.UnitSpecs, item => item.Id);
        Index(mapping.Properties, item => item.Id);
        Index(mapping.Relations, item => item.Id);
        Require(mapping.Entities.Select(item => item.DatasetRef).Distinct().Count() <= 2);
        // 每个实体必须在自己的数据集内闭合scope、身份和时间字段。
        foreach (var entity in mapping.Entities)
        {
            Dataset(entity.DatasetRef);
            Iri(entity.EntityClassIri);
            Identifier(entity.IdentitySpecId);
            Identifier(entity.TemporalSpecId);
            Require(identities.ContainsKey(entity.IdentitySpecId) && temporal.ContainsKey(entity.TemporalSpecId));
            Require(entity.ScopeFields is not null);
            Field(entity.ScopeFields!.Organization, entity.DatasetRef);
            Field(entity.ScopeFields.Site, entity.DatasetRef);
            // 身份所用scope必须与实体完全一致。
            var identity = identities[entity.IdentitySpecId];
            Require(identity.OrganizationFieldRef == entity.ScopeFields.Organization && identity.SiteFieldRef == entity.ScopeFields.Site);
            Identifier(identity.SourceNamespace);
            Require(identity.ExternalIdFieldRefs is { Length: >= 1 and <= 12 });
            Require(identity.ExternalIdFieldRefs.Distinct().Count() == identity.ExternalIdFieldRefs.Length);
            // 复合键保留原顺序，仅检查逐字段归属。
            foreach (var field in identity.ExternalIdFieldRefs)
            {
                Field(field, entity.DatasetRef);
            }
            OptionalField(identity.ValidFromFieldRef, entity.DatasetRef);
            OptionalField(identity.ValidToFieldRef, entity.DatasetRef);
            // 时间字段允许未知，但未知须在真实评估中阻断，不能补成无穷。
            var time = temporal[entity.TemporalSpecId];
            OptionalField(time.EventTimeFieldRef, entity.DatasetRef);
            OptionalField(time.ObservedAtFieldRef, entity.DatasetRef);
            OptionalField(time.ValidFromFieldRef, entity.DatasetRef);
            OptionalField(time.ValidToFieldRef, entity.DatasetRef);
            Require(time.TimezonePolicy is not null && time.Precision is "DAY" or "SECOND" or "MILLISECOND" or "MICROSECOND");
            Require(time.TimezonePolicy!.Kind == "UTC" ? time.TimezonePolicy.ZoneId is null
                : time.TimezonePolicy.Kind == "REGISTERED_ZONE" && time.TimezonePolicy.ZoneId is "Asia/Shanghai" or "Etc/UTC");
        }
        // 属性只能使用所属实体数据集，不能以字段名混入另一张表。
        foreach (var property in mapping.Properties)
        {
            Identifier(property.EntityBindingId);
            Require(entities.ContainsKey(property.EntityBindingId));
            Iri(property.PropertyIri);
            Field(property.FieldRef, entities[property.EntityBindingId].DatasetRef);
            Require(property.NullPolicy is "KEEP_NULL" or "REJECT_NULL");
            Require(property.ConversionId is null || conversions.ContainsKey(property.ConversionId));
            Require(property.UnitSpecId is null || units.ContainsKey(property.UnitSpecId));
            if (property.UnitSpecId is not null)
            {
                Field(units[property.UnitSpecId].SourceUnitFieldRef, property.FieldRef.DatasetRef);
            }
        }
        // 关系只支持显式有序键和半开时间交集。
        foreach (var relation in mapping.Relations)
        {
            Identifier(relation.FromBindingId);
            Identifier(relation.ToBindingId);
            Require(entities.ContainsKey(relation.FromBindingId) && entities.ContainsKey(relation.ToBindingId));
            Iri(relation.PredicateIri);
            Require(relation.Cardinality is "ONE_TO_MANY" or "MANY_TO_MANY");
            Require(relation.TemporalJoinPolicy == "HALF_OPEN_OVERLAP" && relation.JoinFieldPairs is { Length: >= 1 and <= 12 });
            // 键对逐侧检查，不接受跨源或原始表达式。
            foreach (var pair in relation.JoinFieldPairs)
            {
                Require(pair is not null);
                Field(pair!.From, entities[relation.FromBindingId].DatasetRef);
                Field(pair.To, entities[relation.ToBindingId].DatasetRef);
            }
        }
        // 未被引用的转换也必须合法，不能隐藏动态表达式。
        foreach (var conversion in mapping.Conversions)
        {
            Require(conversion.Version == "1" && conversion.Parameters.ValueKind == JsonValueKind.Object);
            UniqueKeys(conversion.Parameters);
            // 参数名称集合决定注册纯函数，不进行自由求值。
            var keys = conversion.Parameters.EnumerateObject().Select(item => item.Name).Order(StringComparer.Ordinal).ToArray();
            switch (conversion.RegisteredId)
            {
                case "identity":
                case "celsius-to-kelvin":
                    Require(keys.Length == 0);
                    break;
                case "decimal-scale-exact":
                    Require(keys.SequenceEqual(new[] { "scale" }));
                    Require(conversion.Parameters.GetProperty("scale").ValueKind == JsonValueKind.Number
                        && conversion.Parameters.GetProperty("scale").TryGetInt32(out var scale) && scale is >= 0 and <= 28);
                    break;
                case "json-top-level-scalar":
                    Require(keys.SequenceEqual(new[] { "key", "valueType" }));
                    Require(conversion.Parameters.GetProperty("key").ValueKind == JsonValueKind.String);
                    Identifier(conversion.Parameters.GetProperty("key").GetString()!);
                    Require(conversion.Parameters.GetProperty("valueType").ValueKind == JsonValueKind.String
                        && conversion.Parameters.GetProperty("valueType").GetString() is "STRING" or "DECIMAL" or "BOOLEAN");
                    break;
                default:
                    Require(false);
                    break;
            }
        }
        // 物理量单位不可只凭转换函数推测，必须声明精确证据列。
        foreach (var unit in mapping.UnitSpecs)
        {
            Iri(unit.SourceUnitIri);
            Iri(unit.TargetUnitIri);
            Require(unit.SourceUnitFieldRef is not null);
            Field(unit.SourceUnitFieldRef!, unit.SourceUnitFieldRef!.DatasetRef);
            Require(unit.EvidenceKind == "SOURCE_FIELD" && unit.UnitRegistryVersion == "1");
            Require(unit.SourceUnitCode is "Cel" or "K");
        }
    }

    /// <summary>建立有界唯一引用索引，重复和空元素一律拒绝。</summary>
    private static Dictionary<string, T> Index<T>(T[] items, Func<T, string> id) where T : class
    {
        // 每个集合有自己的命名空间，不进行隐式覆盖。
        var result = new Dictionary<string, T>(StringComparer.Ordinal);
        // 各元素标识在构造字典前校验。
        foreach (var item in items)
        {
            Require(item is not null);
            Identifier(id(item!));
            Require(result.TryAdd(id(item!), item!));
        }
        return result;
    }

    /// <summary>只接受固定目录的表身份；实际存在性由当前目录证明。</summary>
    private static void Dataset(MappingDatasetRef dataset)
    {
        Require(dataset is not null);
        Identifier(dataset!.SnapshotId);
        Require(dataset.Kind == "TABLE");
        Require(!string.IsNullOrWhiteSpace(dataset.Schema) && dataset.Schema.Length <= 63 && !dataset.Schema.Any(char.IsControl));
        Require(!string.IsNullOrWhiteSpace(dataset.Name) && dataset.Name.Length <= 63 && !dataset.Name.Any(char.IsControl));
    }

    /// <summary>字段必须在实体数据集内且拥有真实目录序号。</summary>
    private static void Field(MappingFieldRef field, MappingDatasetRef dataset)
    {
        Require(field is not null && field.DatasetRef == dataset && field.Ordinal is >= 1 and <= 1600);
        Dataset(dataset);
        Require(!string.IsNullOrWhiteSpace(field!.Name) && field.Name.Length <= 63 && !field.Name.Any(char.IsControl));
    }

    /// <summary>可空字段保持未知，不转成无穷或宿主时间。</summary>
    private static void OptionalField(MappingFieldRef? field, MappingDatasetRef dataset)
    {
        if (field is not null)
        {
            Field(field, dataset);
        }
    }

    /// <summary>IRI仅作安全ASCII形状验证，发布目录另外证明存在性。</summary>
    private static void Iri(string value)
    {
        Require(!string.IsNullOrWhiteSpace(value) && value.Length <= 2048 && value.All(character => character is > ' ' and < '\u007f')
            && Uri.TryCreate(value, UriKind.Absolute, out _));
    }

    /// <summary>固定hash必须为64位小写hex，不接受synthetic占位。</summary>
    /// <param name="value">被引用原字节的散列。</param>
    public static void Hash(string value) => Require(value is not null && Regex.IsMatch(value, "^[a-f0-9]{64}$", RegexOptions.CultureInvariant));

    /// <summary>资源标识采用有界安全ASCII，标识本身不代表有权。</summary>
    /// <param name="value">资源或命令标识。</param>
    public static void Identifier(string value) => Require(value is not null && Regex.IsMatch(value, "^[A-Za-z0-9][A-Za-z0-9._:/-]{0,127}$", RegexOptions.CultureInvariant));

    /// <summary>正修订上限须能在前端精确往返。</summary>
    /// <param name="value">版本整数。</param>
    public static void Revision(long value) => Require(value is >= 1 and <= MaximumRevision);

    /// <summary>递归确认不存在重复键，包括未使用的嵌套参数。</summary>
    /// <param name="element">当前JSON节点。</param>
    private static void UniqueKeys(JsonElement element)
    {
        if (element.ValueKind == JsonValueKind.Object)
        {
            // 每个对象拥有自己的键集合，不能把不同对象的同名键误判。
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in element.EnumerateObject())
            {
                Require(names.Add(property.Name));
                UniqueKeys(property.Value);
            }
        }
        else if (element.ValueKind == JsonValueKind.Array)
        {
            foreach (var child in element.EnumerateArray())
            {
                UniqueKeys(child);
            }
        }
    }

    /// <summary>固定安全错误不携不可信JSON或值。</summary>
    /// <param name="condition">必须满足的形状条件。</param>
    private static void Require(bool condition)
    {
        if (!condition)
        {
            throw new SemanticOperationException(400, "mapping_payload_invalid");
        }
    }
}
