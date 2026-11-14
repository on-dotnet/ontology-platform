using System.Diagnostics.CodeAnalysis;
using System.Globalization;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace OntologyPlatform.Contracts;

/// <summary>查询wire输入和结果形状守卫，不替代当前授权与真实来源校验。</summary>
public static class G4QueryRules
{
    /// <summary>完整结果的UTF8字节预算。</summary>
    public const int MaximumResultBytes = 1024 * 1024;

    /// <summary>严格读取单个判别载荷，拒绝重复键后才构造类型。</summary>
    /// <param name="json">有界原始JSON。</param>
    /// <returns>已通过形状和精度校验的载荷。</returns>
    public static G4QueryDatum ReadDatum(string json)
    {
        try
        {
            // 严格UTF8编码拒绝孤立代理项，不静默替换后继续读取。
            var bytes = new UTF8Encoding(false, true).GetBytes(json);
            Require(bytes.Length <= MaximumResultBytes);
            // 元数据排序不影响判别，但任何重复键均必须在解码前失败。
            using var document = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 16 });
            Unique(document.RootElement);
            // 不使用JsonElement字典逃避正式判别字段。
            var result = JsonSerializer.Deserialize<G4QueryDatum>(bytes, G4QueryJson.Options);
            Require(result is not null);
            Validate(result!);
            return result!;
        }
        catch (Exception failure) when (failure is JsonException or InvalidOperationException or FormatException or ArgumentException or OverflowException)
        {
            throw new SemanticOperationException(400, "query_payload_invalid");
        }
    }

    /// <summary>按原始UTF8读取十字段请求，选择上下文不藏入请求body。</summary>
    /// <param name="bytes">不超过64KiB的完整请求字节。</param>
    /// <param name="selectionQueryId">传输适配器提取的原消歧查询ID。</param>
    /// <returns>通过形状与预算验证的请求；版本及授权由应用边界另验。</returns>
    public static G4SemanticQuery ReadQuery(byte[] bytes, string? selectionQueryId)
    {
        try
        {
            Require(bytes is { Length: > 0 and <= 65536 });
            _ = new UTF8Encoding(false, true).GetString(bytes);
            // 重复键和非法代理项必须在正式反序列化之前检查。
            using var document = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 16 });
            Unique(document.RootElement);
            // 显式entityIri:null与可选filter缺席语义不同。
            if (document.RootElement.TryGetProperty("filters", out var filters) && filters.ValueKind == JsonValueKind.Object
                && filters.TryGetProperty("entityIri", out var selected)) Require(selected.ValueKind == JsonValueKind.String);
            // 全层封闭与必填字段由正式DTO定义，不接受宽松字典。
            var request = JsonSerializer.Deserialize<G4SemanticQuery>(bytes, G4QueryJson.Options);
            Require(request is not null);
            ValidateQuery(request!, selectionQueryId);
            return request!;
        }
        catch (Exception failure) when (failure is JsonException or InvalidOperationException or FormatException or ArgumentException or OverflowException)
        {
            throw Invalid();
        }
    }

    /// <summary>请求只能缩小当前范围，不接受隐式分页、无界遍历或无来源选择。</summary>
    public static void ValidateQuery(G4SemanticQuery query, string? selectionQueryId)
    {
        Require(query is not null);
        Identifier(query!.AssetId);
        Identifier(query.OntologyReleaseId);
        Require(query.MappingReleaseIds is { Length: 1 });
        Identifier(query.MappingReleaseIds![0]);
        Identifier(query.CapabilityId);
        Require(query.CapabilityVersion is not null && Regex.IsMatch(query.CapabilityVersion, @"\A[0-9a-f]{64}\z"));
        Iris(query.RelationshipIris, 0, 5);
        Require(query.Depth is >= 1 and <= 5 && query.MaxRows is >= 2 and <= 100 && query.TimeoutMs is >= 100 and <= 5000);
        Require(query.Filters is not null);
        if (query.Filters!.SiteId is not null) Identifier(query.Filters.SiteId);
        if (query.Filters.EntityExternalId is not null) Text(query.Filters.EntityExternalId, 256, true);
        Require((query.Filters.ValidFrom is null) == (query.Filters.ValidTo is null));
        if (query.Filters.ValidFrom is not null)
        {
            UtcLexical(query.Filters.ValidFrom);
            UtcLexical(query.Filters.ValidTo!);
            // 固定补齐小数位后用十进制秒比较，纳秒不经DateTime舍入。
            var from = UtcSeconds(query.Filters.ValidFrom);
            // 同一UTC基准支持31天上限的精确差值。
            var to = UtcSeconds(query.Filters.ValidTo!);
            Require(to > from && to - from <= 31m * 86400m);
        }
        if (query.Filters.EntityIri is not null)
        {
            Iri(query.Filters.EntityIri);
            Identifier(query.Filters.SiteId);
            if (selectionQueryId is null) throw new SemanticOperationException(422, "selection_context_required");
            Identifier(selectionQueryId);
        }
        else Require(selectionQueryId is null);
    }

    /// <summary>校验UTC词法的实际小数位，不将本地时间猜测为UTC。</summary>
    private static void UtcLexical(string value)
    {
        Require(value is not null);
        // 小数点只允许处于秒之后；TemporalLexical负责全部字符和公历校验。
        var digits = value.Length > 19 && value[19] == '.' ? value.Length - 21 : 0;
        Require(TemporalLexical(value, "UTC", digits));
    }

    /// <summary>已验证的UTC时刻转精确十进制秒，保留最多九位小数。</summary>
    private static decimal UtcSeconds(string value)
    {
        // 整秒使用UTC日期算术，小数独立解析避免纳秒截断。
        var whole = DateTime.ParseExact(value[..19], "yyyy-MM-dd'T'HH:mm:ss", CultureInfo.InvariantCulture, DateTimeStyles.None).Ticks / TimeSpan.TicksPerSecond;
        return whole + (value.Length == 20 ? 0m : decimal.Parse("0" + value[19..^1], CultureInfo.InvariantCulture));
    }

    /// <summary>原始结果先验封闭JSON再验六态与证据闭合，不能靠反序列化成功就披露。</summary>
    public static G4QueryResultV1 ReadResult(byte[] bytes)
    {
        try
        {
            Require(bytes is { Length: > 0 and <= MaximumResultBytes });
            _ = new UTF8Encoding(false, true).GetString(bytes);
            // 对持久恢复同样检测重复键和非法文本，不信任存储字节的结构。
            using var document = JsonDocument.Parse(bytes, new JsonDocumentOptions { MaxDepth = 16 });
            Unique(document.RootElement);
            // 正式十二字段类型是唯一wire解码器。
            var result = JsonSerializer.Deserialize<G4QueryResultV1>(bytes, G4QueryJson.Options);
            Require(result is not null);
            ValidateResult(result!);
            return result!;
        }
        catch (Exception failure) when (failure is JsonException or InvalidOperationException or FormatException or ArgumentException or OverflowException)
        {
            throw Invalid();
        }
    }

    /// <summary>校验业务态、版本身份与所有断言的证据闭包；真实授权仍由服务事务负责。</summary>
    public static void ValidateResult(G4QueryResultV1 result)
    {
        Require(result is not null && result.SchemaVersion == "g4.query-result.v1");
        Require(result!.Data is { Length: <= 100 } && result.Candidates is { Length: <= 100 }
            && result.Evidence is { Length: <= 256 } && result.SubSources is { Length: >= 1 and <= 256 }
            && result.Diagnostics is { Length: <= 256 } && result.Snapshot is not null);
        Identifier(result.TraceId);
        UtcLexical(result.ObservedAtUtc);
        UtcInterval(result.ValidTime);
        Identifier(result.Snapshot!.OntologyReleaseId);
        Ids(result.Snapshot.MappingReleaseIds);
        Ids(result.Snapshot.SourceCatalogSnapshotIds);
        Identifier(result.Snapshot.CapabilityId);
        Require(result.Snapshot.CapabilityVersion is not null && Regex.IsMatch(result.Snapshot.CapabilityVersion, @"\A[0-9a-f]{64}\z"));
        // 每分支回执唯一，失败无回执只保留每连接一个摘要。
        var branchIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (var branch in result.SubSources!)
        {
            Require(branch is not null);
            Identifier(branch!.ConnectionId);
            UtcLexical(branch.ObservedAtUtc);
            Require(branch.Status is "SUCCESS" or "EMPTY" or "TIMEOUT" or "FORBIDDEN" or "UNAVAILABLE" or "INDETERMINATE");
            Require(branch.WatermarkKind is "TRANSACTION_SNAPSHOT" or "EVENT_TIME" or "OBSERVED_AT" or "OPAQUE" or "UNKNOWN");
            if (branch.SourceReadReceiptId is not null) Identifier(branch.SourceReadReceiptId);
            Require(branchIds.Add(branch.SourceReadReceiptId ?? "failure:" + branch.ConnectionId));
            if (branch.Status is "SUCCESS" or "EMPTY") Require(branch.SourceReadReceiptId is not null);
            if (branch.Status == "EMPTY") Require(!branch.Limited);
        }
        // 证据ID在一个结果中唯一，所有业务引用都从该集合解析。
        var evidence = new Dictionary<string, G4SourceEvidenceRef>(StringComparer.Ordinal);
        foreach (var item in result.Evidence!)
        {
            Require(item is not null);
            Identifier(item!.EvidenceId);
            Require(evidence.TryAdd(item.EvidenceId, item));
            Identifier(item.ConnectionId);
            Identifier(item.MappingReleaseId);
            Identifier(item.SourceCatalogSnapshotId);
            Identifier(item.SourceDatasetRef);
            Identifier(item.SourceReadReceiptId);
            Require(result.Snapshot.MappingReleaseIds.Contains(item.MappingReleaseId, StringComparer.Ordinal));
            Require(item.Scope is not null);
            Identifier(item.Scope!.OrganizationId);
            Ids(item.Scope.SiteIds);
            UtcLexical(item.ObservedAtUtc);
            UtcInterval(item.ValidTime);
            Require(item.Precision is "RECORD" or "ROW_KEY" or "DATASET" or "TIME_WINDOW" or "UNKNOWN");
            if (item.Precision is "RECORD" or "ROW_KEY") Text(item.SourceRecordRef, 4096, true);
            else Require(item.SourceRecordRef is null);
            if (item.Precision == "TIME_WINDOW") Require(item.ValidTime is not null);
            Require(result.SubSources.Any(branch => branch.ConnectionId == item.ConnectionId && branch.SourceReadReceiptId == item.SourceReadReceiptId));
        }
        foreach (var datum in result.Data!)
        {
            Validate(datum);
            Require(datum is not G4OntologyDatum);
            // 递归检查属性及单位的证据引用，不只检查顶层EvidenceIds。
            var references = References(JsonSerializer.SerializeToElement<G4QueryDatum>(datum, G4QueryJson.Options)).Distinct(StringComparer.Ordinal).ToArray();
            DemandReferences(references, evidence, result.SubSources);
            switch (datum)
            {
                case G4EntityDatum entity:
                    DemandIdentity(entity.Identity, references, evidence);
                    break;
                case G4ObservationDatum observation:
                    DemandIdentity(observation.Identity, references, evidence);
                    break;
                case G4RelationshipDatum relationship:
                    DemandIdentity(relationship.Source.Identity, references, evidence);
                    DemandIdentity(relationship.Target.Identity, references, evidence);
                    break;
            }
        }
        // 候选必须由实际证据支撑，不允许重复IRI制造歧义数量。
        var candidateIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (var candidate in result.Candidates!)
        {
            Require(candidate is not null);
            Iri(candidate!.EntityIri);
            Require(candidateIds.Add(candidate.EntityIri));
            Iris(candidate.EntityTypeIris, 1, 16);
            Identifier(candidate.OrganizationId);
            Identifier(candidate.SiteId);
            Text(candidate.ExternalId, 256, true);
            Text(candidate.Label, 256, true);
            Ids(candidate.EvidenceIds);
            DemandReferences(candidate.EvidenceIds, evidence, result.SubSources);
            Require(candidate.EvidenceIds.Any(id => evidence[id].Scope.OrganizationId == candidate.OrganizationId
                && evidence[id].Scope.SiteIds.Contains(candidate.SiteId, StringComparer.Ordinal)));
            Require(candidate.EvidenceIds.All(id => evidence[id].Precision is "RECORD" or "ROW_KEY"));
        }
        foreach (var diagnostic in result.Diagnostics!)
        {
            Require(diagnostic is not null);
            Identifier(diagnostic!.Code);
            Require(diagnostic.Severity is "info" or "warning" or "error");
            Text(diagnostic.Message, 4096, true);
            if (diagnostic.FocusNode is not null) Iri(diagnostic.FocusNode);
            if (diagnostic.Path is not null) Iri(diagnostic.Path);
        }
        // 完整状态由全部必需分支判定，不能用零行掩盖超时或拒绝。
        var complete = result.SubSources.All(branch => branch.Status is "SUCCESS" or "EMPTY" && !branch.Limited);
        // 数据集和时间窗证据只支持降级结果，不能冒充记录定位。
        var degraded = result.Evidence.Any(item => item.Precision is "DATASET" or "TIME_WINDOW" or "UNKNOWN");
        Require(!result.SubSources.Any(branch => branch.Limited) || result.Limited);
        Require(result.Status switch
        {
            "FOUND" => result.Data.Length > 0 && result.Candidates.Length == 0 && complete && !result.Limited && !degraded,
            "EMPTY" => result.Data.Length == 0 && result.Candidates.Length == 0 && !result.Limited && result.SubSources.All(branch => branch.Status == "EMPTY"),
            "PARTIAL" => result.Data.Length > 0 && result.Candidates.Length == 0 && (!complete || result.Limited || degraded),
            "AMBIGUOUS" => result.Data.Length == 0 && result.Candidates.Length >= 2 && result.SubSources.All(branch => branch.Status is "SUCCESS" or "EMPTY") && !degraded,
            "UNAUTHORIZED" => result.Data.Length == 0 && result.Candidates.Length == 0 && result.Evidence.Length == 0 && result.SubSources.All(branch => branch.Status == "FORBIDDEN"),
            "UNAVAILABLE" => result.Data.Length == 0 && result.Candidates.Length == 0 && (!complete || result.Limited || result.Evidence.Any(item => item.Precision == "UNKNOWN")) && !result.SubSources.All(branch => branch.Status == "FORBIDDEN"),
            _ => false
        });
    }

    /// <summary>递归提取正式载荷的所有证据数组，不接受客户端自定义键。</summary>
    private static IEnumerable<string> References(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            foreach (var property in value.EnumerateObject())
            {
                if (property.Name == "evidenceIds")
                {
                    foreach (var id in property.Value.EnumerateArray()) yield return id.GetString()!;
                }
                else foreach (var id in References(property.Value)) yield return id;
            }
        }
        else if (value.ValueKind == JsonValueKind.Array)
        {
            foreach (var child in value.EnumerateArray()) foreach (var id in References(child)) yield return id;
        }
    }

    /// <summary>只有真实成功分支且精度非UNKNOWN的引用才能支撑业务值。</summary>
    private static void DemandReferences(string[] ids, Dictionary<string, G4SourceEvidenceRef> evidence, G4QuerySubSource[] branches)
    {
        Require(ids.Length > 0);
        foreach (var id in ids)
        {
            Require(evidence.TryGetValue(id, out var item));
            Require(item!.Precision != "UNKNOWN" && branches.Any(branch => branch.Status == "SUCCESS"
                && branch.ConnectionId == item.ConnectionId && branch.SourceReadReceiptId == item.SourceReadReceiptId));
        }
    }

    /// <summary>完整实体身份必须至少有同组织同厂区证据，不能凭其他厂区行构造。</summary>
    private static void DemandIdentity(G4QueryIdentity identity, string[] ids, Dictionary<string, G4SourceEvidenceRef> evidence) =>
        Require(ids.Any(id => evidence[id].Scope.OrganizationId == identity.OrganizationId
            && evidence[id].Scope.SiteIds.Contains(identity.SiteId, StringComparer.Ordinal)));

    /// <summary>顶层原合同UTC半开区间，不用观察时间补业务时间。</summary>
    private static void UtcInterval(G4QueryUtcInterval? value)
    {
        if (value is null) return;
        UtcLexical(value.FromUtc);
        if (value.ToUtc is null) return;
        UtcLexical(value.ToUtc);
        Require(UtcSeconds(value.ToUtc) > UtcSeconds(value.FromUtc));
    }

    /// <summary>递归检测转义解码后的重复属性及非法字符串。</summary>
    /// <param name="value">待验证的当前节点。</param>
    public static void Unique(JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            // 按解码后的准确键名比较，k\u0069nd与kind视为同一个键。
            var names = new HashSet<string>(StringComparer.Ordinal);
            foreach (var property in value.EnumerateObject())
            {
                Require(names.Add(property.Name));
                _ = new UTF8Encoding(false, true).GetBytes(property.Name);
                Unique(property.Value);
            }
        }
        else if (value.ValueKind == JsonValueKind.Array)
        {
            foreach (var item in value.EnumerateArray())
            {
                Unique(item);
            }
        }
        else if (value.ValueKind == JsonValueKind.String)
        {
            _ = new UTF8Encoding(false, true).GetBytes(value.GetString()!);
        }
    }

    /// <summary>逐分支核验字段、不变量与精确值，不允许未支持分支混入。</summary>
    /// <param name="datum">已经反序列化的判别数据。</param>
    public static void Validate(G4QueryDatum datum)
    {
        Require(datum is not null);
        Ids(datum!.EvidenceIds);
        if (datum is G4OntologyDatum ontology)
        {
            Require(datum.EntityIri is null);
            Identifier(ontology.OntologyReleaseId);
            Require(ontology.Classes is not null && ontology.Properties is not null && ontology.Classes.Length + ontology.Properties.Length <= 100);
            foreach (var item in ontology.Classes!)
            {
                Require(item is not null);
                Iri(item!.Iri);
                if (item.Label is not null) Text(item.Label, 256, false);
                Ids(item.EvidenceIds);
            }
            foreach (var item in ontology.Properties!)
            {
                Require(item is not null && item.Kind is "OBJECT" or "DATATYPE");
                Iri(item!.Iri);
                Iris(item.DomainIris, 0, 16);
                Iris(item.RangeIris, 0, 16);
                Ids(item.EvidenceIds);
            }
            return;
        }
        Iri(datum.EntityIri);
        switch (datum)
        {
            case G4EntityDatum entity:
                Identity(entity.Identity);
                Iris(entity.TypeIris, 1, 16);
                if (entity.Label is not null) Text(entity.Label, 256, false);
                Require(entity.Properties is { Length: <= 32 });
                Interval(entity.ValidTime);
                foreach (var property in entity.Properties!)
                {
                    Require(property is not null);
                    Iri(property!.PropertyIri);
                    Value(property.Value);
                    Unit(property.Unit);
                    if (property.EventTime is not null) Time(property.EventTime);
                    Ids(property.EvidenceIds);
                }
                break;
            case G4RelationshipDatum relationship:
                Iri(relationship.RelationshipIri);
                Endpoint(relationship.Source);
                Endpoint(relationship.Target);
                Require(relationship.EntityIri == relationship.Source.EntityIri);
                Require(relationship.Cardinality is "ONE_TO_ONE" or "ONE_TO_MANY" or "MANY_TO_ONE" or "MANY_TO_MANY");
                Interval(relationship.ValidTime);
                break;
            case G4ObservationDatum observation:
                Identity(observation.Identity);
                Iri(observation.PropertyIri);
                Value(observation.Value);
                Unit(observation.Unit);
                if (observation.EventTime is not null) Time(observation.EventTime);
                Require(TemporalLexical(observation.ObservedAtUtc, "UTC", 6));
                Interval(observation.ValidTime);
                break;
            default:
                throw Invalid();
        }
    }

    /// <summary>检查精确标量的词法和范围，不使用double解析。</summary>
    /// <param name="value">严格类型化标量。</param>
    public static void Value(G4QueryValue value)
    {
        Require(value is not null);
        if (value is G4NullValue missing)
        {
            Require(missing.Lexical is null && missing.DeclaredType is "string" or "boolean" or "int64" or "decimal" or "date" or "timestampUtc" or "timestampLocal");
            return;
        }
        Text(value!.Lexical, 4096, false);
        switch (value)
        {
            case G4StringValue:
                break;
            case G4BooleanValue:
                Require(value.Lexical is "true" or "false");
                break;
            case G4Int64Value:
                Require(Regex.IsMatch(value.Lexical!, @"\A(0|-?[1-9][0-9]*)\z", RegexOptions.CultureInvariant)
                    && long.TryParse(value.Lexical, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out _));
                break;
            case G4DecimalValue number:
                Require(number.Precision is >= 1 and <= 28 && number.Scale >= 0 && number.Scale <= number.Precision);
                // scale决定精确小数位数，不能用TryParse的宽松格式替代词法校验。
                var pattern = @"\A-?(0|[1-9][0-9]*)" + (number.Scale == 0 ? "" : @"\.[0-9]{" + number.Scale.ToString(CultureInfo.InvariantCulture) + "}") + @"\z";
                Require(Regex.IsMatch(number.Lexical!, pattern, RegexOptions.CultureInvariant));
                // decimal在批准的28位精度范围内可无损解析；禁止负零。
                var parsed = decimal.Parse(number.Lexical!, NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture);
                Require(parsed != 0 || !number.Lexical!.StartsWith('-'));
                // numeric(p,s)的整数位容量独立于实际小数末尾零。
                var whole = number.Lexical!.TrimStart('-').Split('.')[0].TrimStart('0');
                Require(whole.Length <= number.Precision - number.Scale);
                break;
            case G4DateValue:
                Require(TemporalLexical(value.Lexical!, "DATE", 0));
                break;
            case G4UtcValue:
                Require(TemporalLexical(value.Lexical!, "UTC", 6));
                break;
            case G4LocalValue:
                Require(TemporalLexical(value.Lexical!, "LOCAL", 6));
                break;
            default:
                throw Invalid();
        }
    }

    /// <summary>检查时间词法，日期合法性与声明的分辨率一致。</summary>
    /// <param name="value">不自动转换时区的时间。</param>
    public static void Time(G4QueryTime value)
    {
        Require(value is not null && TemporalLexical(value.Lexical, value.Kind, value.FractionalDigits));
    }

    /// <summary>支持完整0至9位时间合同，PG源能力另限制为真实微秒。</summary>
    private static bool TemporalLexical(string? lexical, string kind, int digits)
    {
        if (lexical is null || digits is < 0 or > 9 || kind is not ("DATE" or "LOCAL" or "UTC")) return false;
        if (kind == "DATE") return digits == 0 && Regex.IsMatch(lexical, @"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\z")
            && DateOnly.TryParseExact(lexical, "yyyy-MM-dd", CultureInfo.InvariantCulture, DateTimeStyles.None, out _);
        // 公历和整秒单独校验，纳秒小数不交给只能承载七位的DateTime截断。
        var pattern = @"\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}" + (digits == 0 ? "" : @"\.[0-9]{" + digits + "}") + (kind == "UTC" ? "Z" : "") + @"\z";
        return Regex.IsMatch(lexical, pattern, RegexOptions.CultureInvariant)
            && DateTime.TryParseExact(lexical[..19], "yyyy-MM-dd'T'HH:mm:ss", CultureInfo.InvariantCulture, DateTimeStyles.None, out _);
    }

    /// <summary>有效区间同种类同分辨率且严格半开。</summary>
    private static void Interval(G4QueryInterval? value)
    {
        if (value is null) return;
        Time(value.From);
        if (value.To is null) return;
        Time(value.To);
        Require(value.From.Kind == value.To.Kind && value.From.FractionalDigits == value.To.FractionalDigits
            && string.CompareOrdinal(value.From.Lexical, value.To.Lexical) < 0);
    }

    /// <summary>完整来源身份必须有组织、厂区、命名空间和外部号。</summary>
    private static void Identity(G4QueryIdentity value)
    {
        Require(value is not null);
        Identifier(value!.OrganizationId);
        Identifier(value.SiteId);
        Text(value.SourceNamespace, 256, true);
        Text(value.ExternalId, 256, true);
        Interval(value.EffectiveTime);
    }

    /// <summary>关系两端的静态身份完整性，授权由执行器重验。</summary>
    private static void Endpoint(G4QueryEndpoint value)
    {
        Require(value is not null);
        Iri(value!.EntityIri);
        Identity(value.Identity);
        Iris(value.TypeIris, 1, 16);
    }

    /// <summary>来源种类决定是否必须提供真实字段引用。</summary>
    private static void Unit(G4QueryUnit? value)
    {
        if (value is null) return;
        Identifier(value.UnitSpecId);
        Iri(value.UnitIri);
        Ids(value.EvidenceIds);
        Require(value.Source is "MAPPING_RELEASE" or "SOURCE_FIELD");
        if (value.Source == "MAPPING_RELEASE") Require(value.SourceFieldRef is null);
        else Identifier(value.SourceFieldRef);
    }

    /// <summary>传输标识必须为已登记ASCII字符且有界。</summary>
    public static void Identifier(string? value) => Require(value is not null && Regex.IsMatch(value, @"\A[A-Za-z0-9][A-Za-z0-9._:-]{0,127}\z", RegexOptions.CultureInvariant));

    /// <summary>IRI只是标识，必须符合已批准ASCII传输规则。</summary>
    public static void Iri(string? value)
    {
        Require(value is { Length: > 0 and <= 2048 } && value!.All(character => character is > ' ' and < (char)127 && !"<>\"{}|^`\\".Contains(character)));
        Require(Uri.TryCreate(value, UriKind.Absolute, out var parsed));
        Require(parsed!.Scheme is "http" or "https" ? parsed.Host.Length > 0
            : parsed.Scheme == "urn" && Regex.IsMatch(value!, @"\Aurn:[A-Za-z0-9][A-Za-z0-9-]{0,31}:.+\z", RegexOptions.CultureInvariant));
    }

    /// <summary>IRI集合非重复，保留空集合与必需集合的差别。</summary>
    private static void Iris(string[] values, int minimum, int maximum)
    {
        Require(values is not null && values.Length >= minimum && values.Length <= maximum);
        Require(values!.Distinct(StringComparer.Ordinal).Count() == values!.Length);
        foreach (var value in values) Iri(value);
    }

    /// <summary>证据标识非空去重，交叉引用由结果层另验。</summary>
    private static void Ids(string[] values)
    {
        Require(values is { Length: >= 1 and <= 256 } && values.Distinct(StringComparer.Ordinal).Count() == values!.Length);
        foreach (var value in values!) Identifier(value);
    }

    /// <summary>字符串按UTF8字节限制，不能因UTF16长度误放大。</summary>
    private static void Text(string? value, int maximum, bool nonempty)
    {
        Require(value is not null && (!nonempty || value.Length > 0) && new UTF8Encoding(false, true).GetByteCount(value) <= maximum);
    }

    /// <summary>统一固定错误，不向调用者反射输入或源异常。</summary>
    private static SemanticOperationException Invalid() => new(400, "query_payload_invalid");

    /// <summary>任何形状不变量失败都拒绝载荷。</summary>
    private static void Require([DoesNotReturnIf(false)] bool valid)
    {
        if (!valid) throw Invalid();
    }
}
