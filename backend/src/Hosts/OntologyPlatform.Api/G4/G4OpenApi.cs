using System.Text.Json.Nodes;
using OntologyPlatform.Contracts;
using Microsoft.AspNetCore.OpenApi;
using Microsoft.OpenApi;

namespace OntologyPlatform.Api.G4;

/// <summary>让原生OpenAPI反映G4专用严格数字与必填判别，不改变G2文档或序列化。</summary>
public static class G4OpenApi
{
    /// <summary>仅用于G4文档的产品模型投影规则。</summary>
    public static OpenApiOptions AddG4Contracts(this OpenApiOptions options)
    {
        options.ShouldInclude = description => description.GroupName == "g4";
        options.AddDocumentTransformer((document, _, _) =>
        {
            document.Servers = [new OpenApiServer { Url = "/" }];
            // HttpContext适配器自行严格解析参数，文档从真实路由模板及共用头名补齐传输参数。
            foreach (var path in document.Paths.Where(entry => entry.Key.StartsWith("/api/v1/data/semantic-queries", StringComparison.Ordinal)
                || entry.Key.StartsWith("/api/v1/data/source-evidence/", StringComparison.Ordinal)))
            {
                if (path.Value.Operations is null) continue;
                foreach (var operation in path.Value.Operations.Values)
                {
                    operation.Parameters ??= [];
                    foreach (var segment in path.Key.Split('/').Where(segment => segment.StartsWith('{') && segment.EndsWith('}')))
                        operation.Parameters.Add(new OpenApiParameter { Name = segment[1..^1], In = ParameterLocation.Path,
                            Required = true, Schema = new OpenApiSchema { Type = JsonSchemaType.String } });
                    if (path.Key == "/api/v1/data/semantic-queries")
                    {
                        operation.Parameters.Add(new OpenApiParameter { Name = QueryEndpoints.IdempotencyHeader, In = ParameterLocation.Header,
                            Required = true, Schema = new OpenApiSchema { Type = JsonSchemaType.String } });
                        operation.Parameters.Add(new OpenApiParameter { Name = QueryEndpoints.SelectionHeader, In = ParameterLocation.Header,
                            Required = false, Schema = new OpenApiSchema { Type = JsonSchemaType.String } });
                    }
                }
            }
            // 原生生成器完成所有判别子类遍历及组件命名后，才能收紧为互斥联合。
            foreach (var name in new[] { nameof(G4QueryDatum), nameof(G4QueryValue) })
            {
                if (document.Components?.Schemas?.TryGetValue(name, out var component) == true && component is OpenApiSchema schema
                    && schema.AnyOf is { Count: > 0 })
                {
                    schema.OneOf = schema.AnyOf;
                    schema.AnyOf = null;
                }
            }
            return Task.CompletedTask;
        });
        options.AddSchemaTransformer((schema, context, _) =>
        {
            // G4运行入口禁用Web的数字字符串宽容选项，文档必须一致。
            var type = Nullable.GetUnderlyingType(context.JsonTypeInfo.Type) ?? context.JsonTypeInfo.Type;
            if (type.Name.StartsWith("G4", StringComparison.Ordinal)) ApplyQuerySchema(schema, type);
            if (type == typeof(int) || type == typeof(long))
            {
                schema.Type = JsonSchemaType.Integer | (Nullable.GetUnderlyingType(context.JsonTypeInfo.Type) is null ? 0 : JsonSchemaType.Null);
                schema.Pattern = null;
            }
            if (type.Name.StartsWith("Mapping", StringComparison.Ordinal) && schema.Properties is not null)
            {
                foreach (var field in schema.Properties)
                {
                    if (field.Value is not OpenApiSchema property)
                    {
                        continue;
                    }
                    if (field.Key == "schemaVersion")
                    {
                        property.Enum = [(JsonNode)JsonValue.Create("g4.mapping.v1")!];
                    }
                    if (field.Key.EndsWith("Hash", StringComparison.Ordinal) || field.Key is "sourceCatalogFingerprint")
                    {
                        property.Pattern = "^[0-9a-f]{64}$";
                        property.MinLength = 64;
                        property.MaxLength = 64;
                    }
                    if (field.Key.EndsWith("AtUtc", StringComparison.Ordinal))
                    {
                        property.Pattern = @"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{7}Z$";
                    }
                    // 每个状态机独立枚举，不把Draft与Proposal混用。
                    var values = (type.Name, field.Key) switch
                    {
                        (nameof(MappingDraftView), "status") or (nameof(MappingListItem), "status") => new[] { "DRAFT", "NEEDS_REVIEW", "VALIDATING", "READY_FOR_PROPOSAL", "BLOCKED" },
                        (nameof(MappingJobView), "status") => ["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"],
                        (nameof(MappingAssessmentView), "status") => ["READY_FOR_PROPOSAL", "BLOCKED"],
                        (nameof(MappingStageResult), "status") => ["PASS", "FAIL", "INDETERMINATE", "NOT_RUN"],
                        (nameof(MappingStageResult), "stage") => ["SCHEMA", "IDENTITY", "TIME_UNIT", "SECURITY", "EXECUTABILITY", "RECONCILIATION", "IMPACT"],
                        (_, "status") when typeof(MappingProposalView).IsAssignableFrom(type) => ["PENDING", "APPROVED", "REJECTED", "CANCELLED", "STALE", "EXPIRED"],
                        (nameof(MappingDecisionRequest), "decision") or (nameof(MappingDecision), "decision") => ["APPROVE", "REJECT"],
                        (nameof(MappingSuggestionRequest), "mode") => ["OFF"],
                        (nameof(MappingSuggestionCandidate), "status") => ["CANDIDATE_ONLY"],
                        (nameof(MappingSuggestionCandidate), "evidence") => ["METADATA", "TERM", "USER_ASSERTION", "NO_EVIDENCE"],
                        (nameof(MappingDatasetRef), "kind") => ["TABLE"],
                        (nameof(MappingTimezonePolicy), "kind") => ["UTC", "REGISTERED_ZONE"],
                        (nameof(MappingPropertyBinding), "nullPolicy") => ["KEEP_NULL", "REJECT_NULL"],
                        (nameof(MappingRelationBinding), "cardinality") => ["ONE_TO_MANY", "MANY_TO_MANY"],
                        (nameof(MappingRelationBinding), "temporalJoinPolicy") => ["HALF_OPEN_OVERLAP"],
                        (nameof(MappingTemporalSpec), "precision") => ["SECOND", "MILLISECOND", "MICROSECOND"],
                        (nameof(MappingConversion), "registeredId") => ["identity", "decimal-scale-exact", "celsius-to-kelvin", "json-top-level-scalar"],
                        (nameof(MappingConversion), "version") or (nameof(MappingUnitSpec), "unitRegistryVersion") => ["1"],
                        (nameof(MappingUnitSpec), "sourceUnitCode") => ["Cel", "K"],
                        (nameof(MappingUnitSpec), "evidenceKind") => ["SOURCE_FIELD"],
                        (nameof(MappingVersionBinding), "sourceType") => ["POSTGRESQL"],
                        (nameof(MappingVersionBinding), "adapterVersion") => ["pg-mapping-v1"],
                        (nameof(MappingVersionBinding), "executorVersion") => ["mapping-validator-v1"],
                        (nameof(MappingVersionBinding), "canonicalVersion") => ["mapping-c14n-v1"],
                        (nameof(MappingActivationReceipt), "kind") => ["PUBLISH", "ROLLBACK"],
                        _ => Array.Empty<string>()
                    };
                    if (values.Length > 0)
                    {
                        property.Enum = values.Select(value => (JsonNode)JsonValue.Create(value)!).ToList();
                    }
                }
            }
            if (type == typeof(OracleColumnMetadata) && schema.Properties is not null)
            {
                // 显式枚举与DTO setter保持同一合同，不把未知字符串描述为受支持值。
                var values = new Dictionary<string, string[]>
                {
                    ["charSemantics"] = ["BYTE", "CHAR"],
                    ["timeZoneKind"] = ["NONE", "WITH_TIME_ZONE", "WITH_LOCAL_TIME_ZONE", "UNKNOWN"],
                    ["supportStatus"] = ["SUPPORTED", "METADATA_ONLY", "UNSUPPORTED"]
                };
                foreach (var entry in values)
                {
                    if (schema.Properties.TryGetValue(entry.Key, out var property) && property is OpenApiSchema concrete)
                    {
                        concrete.Enum = entry.Value.Select(value => (JsonNode)JsonValue.Create(value)!).ToList();
                        if (entry.Key == "charSemantics") concrete.Enum.Add(null!);
                    }
                }
            }
            if (schema.Properties?.ContainsKey("kind") == true && type.Name.StartsWith("Mapping", StringComparison.Ordinal))
            {
                schema.Required ??= new HashSet<string>();
                schema.Required.Add("kind");
            }
            if (schema.Properties?.ContainsKey("type") == true)
            {
                schema.Required ??= new HashSet<string>();
                schema.Required.Add("type");
            }
            return Task.CompletedTask;
        });
        return options;
    }

    /// <summary>由正式查询DTO细化封闭判别、标量精度与预算，不手工维护第二套结构定义。</summary>
    private static void ApplyQuerySchema(OpenApiSchema schema, Type type)
    {
        if (schema.Properties is null) return;
        if (schema.Properties.ContainsKey("kind"))
        {
            schema.Required ??= new HashSet<string>();
            schema.Required.Add("kind");
        }
        foreach (var field in schema.Properties)
        {
            if (field.Value is not OpenApiSchema property) continue;
            // 仅具体值分支改变词法空值性，不能把null与缺失或空字符串混为一谈。
            if (field.Key == "lexical" && typeof(G4QueryValue).IsAssignableFrom(type) && type != typeof(G4QueryValue))
            {
                property.Type = type == typeof(G4NullValue) ? JsonSchemaType.Null : JsonSchemaType.String;
                property.MaxLength = type == typeof(G4StringValue) ? 4096 : 128;
                property.Pattern = type.Name switch
                {
                    nameof(G4BooleanValue) => "^(true|false)$",
                    nameof(G4Int64Value) => "^-?(0|[1-9][0-9]{0,18})$",
                    nameof(G4DecimalValue) => "^-?(0|[1-9][0-9]{0,27})(\\.[0-9]{1,28})?$",
                    nameof(G4DateValue) => "^[0-9]{4}-[0-9]{2}-[0-9]{2}$",
                    nameof(G4UtcValue) => "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,9})?Z$",
                    nameof(G4LocalValue) => "^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(\\.[0-9]{1,9})?$",
                    _ => null
                };
            }
            if (field.Key == "entityIri" && typeof(G4QueryDatum).IsAssignableFrom(type) && type != typeof(G4QueryDatum))
                property.Type = type == typeof(G4OntologyDatum) ? JsonSchemaType.Null : JsonSchemaType.String;
            // 固定字符串枚举来自批准的公共合同，不依赖UI翻译猜测状态。
            var values = (type.Name, field.Key) switch
            {
                (nameof(G4QueryResultV1), "schemaVersion") => new[] { "g4.query-result.v1" },
                (nameof(G4SourceEvidenceView), "schemaVersion") => ["g4.source-evidence.v1"],
                (nameof(G4QueryResultV1), "status") => ["FOUND", "AMBIGUOUS", "EMPTY", "UNAUTHORIZED", "UNAVAILABLE", "PARTIAL"],
                (nameof(G4QueryView), "executionStatus") => ["RUNNING", "COMPLETED", "CANCELLED", "FAILED"],
                (nameof(G4QuerySubSource), "status") or (nameof(G4SourceReceiptView), "status") => ["SUCCESS", "EMPTY", "TIMEOUT", "FORBIDDEN", "UNAVAILABLE", "INDETERMINATE"],
                (nameof(G4QuerySubSource), "watermarkKind") or (nameof(G4SourceReceiptView), "watermarkKind") => ["TRANSACTION_SNAPSHOT", "EVENT_TIME", "OBSERVED_AT", "OPAQUE", "UNKNOWN"],
                (nameof(G4SourceEvidenceRef), "precision") => ["RECORD", "ROW_KEY", "DATASET", "TIME_WINDOW", "UNKNOWN"],
                (nameof(G4QueryTime), "kind") => ["UTC", "LOCAL", "DATE"],
                (nameof(G4QueryUnit), "source") => ["MAPPING_RELEASE", "SOURCE_FIELD"],
                (nameof(G4RelationshipDatum), "cardinality") => ["ONE_TO_ONE", "ONE_TO_MANY", "MANY_TO_ONE", "MANY_TO_MANY"],
                (nameof(G4QueryDiagnostic), "severity") => ["info", "warning", "error"],
                (nameof(G4NullValue), "declaredType") => ["string", "boolean", "int64", "decimal", "date", "timestampUtc", "timestampLocal"],
                _ => Array.Empty<string>()
            };
            if (values.Length != 0) property.Enum = values.Select(value => (JsonNode)JsonValue.Create(value)!).ToList();
            // 结构数值与精确业务数值分离，业务值始终为字符串。
            var range = (type.Name, field.Key) switch
            {
                (nameof(G4SemanticQuery), "depth") => (1, 5),
                (nameof(G4SemanticQuery), "maxRows") => (2, 100),
                (nameof(G4SemanticQuery), "timeoutMs") => (100, 5000),
                (nameof(G4DecimalValue), "precision") => (1, 28),
                (nameof(G4DecimalValue), "scale") => (0, 28),
                (nameof(G4QueryTime), "fractionalDigits") => (0, 9),
                (nameof(G4SourceReceiptView), "rowCount") => (0, 100),
                _ => (-1, -1)
            };
            if (range.Item1 >= 0)
            {
                property.Minimum = range.Item1.ToString(System.Globalization.CultureInfo.InvariantCulture);
                property.Maximum = range.Item2.ToString(System.Globalization.CultureInfo.InvariantCulture);
            }
            if (field.Key.EndsWith("Hash", StringComparison.Ordinal) || field.Key == "capabilityVersion")
            {
                property.Pattern = "^[0-9a-f]{64}$";
                property.MinLength = 64;
                property.MaxLength = 64;
            }
            if (type == typeof(G4SemanticQuery) && field.Key == "mappingReleaseIds") { property.MinItems = 1; property.MaxItems = 1; }
            if (type == typeof(G4SemanticQuery) && field.Key == "relationshipIris") { property.MaxItems = 5; property.UniqueItems = true; }
            if (type == typeof(G4QueryResultV1) && field.Key is "data" or "candidates" or "subSources") property.MaxItems = 100;
            if (field.Key is "evidenceIds" or "typeIris" or "entityTypeIris") { property.MinItems = 1; property.UniqueItems = true; }
        }
    }
}
