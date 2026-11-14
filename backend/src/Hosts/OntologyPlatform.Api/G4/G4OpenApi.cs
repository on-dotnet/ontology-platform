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
            return Task.CompletedTask;
        });
        options.AddSchemaTransformer((schema, context, _) =>
        {
            // G4运行入口禁用Web的数字字符串宽容选项，文档必须一致。
            var type = Nullable.GetUnderlyingType(context.JsonTypeInfo.Type) ?? context.JsonTypeInfo.Type;
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
}
