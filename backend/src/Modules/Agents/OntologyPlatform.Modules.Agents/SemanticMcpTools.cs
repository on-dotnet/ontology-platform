using System.Text.Json;
using System.Text.Json.Nodes;
using ModelContextProtocol.Protocol;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Agents;

/// <summary>显式三个只读MCP工具，Schema直接映射唯一Gateway登记。</summary>
public sealed class SemanticMcpTools
{
    /// <summary>唯一正式查询网关，不包含第二份查询引擎。</summary>
    private readonly ISemanticGateway gateway;

    /// <summary>接收当前请求的同一个应用Gateway。</summary>
    public SemanticMcpTools(ISemanticGateway gateway) => this.gateway = gateway;

    /// <summary>只公开显式白名单，身份从服务器传入，不进入工具Schema。</summary>
    public Tool[] List() => gateway.GetCapabilities().Where(value => Allowed(value.Id)).Select(value => new Tool
    {
        Name = value.Id, Description = value.Meaning, InputSchema = InputSchema(value.InputSchema), OutputSchema = value.OutputSchema,
        Annotations = new ToolAnnotations { ReadOnlyHint = true, DestructiveHint = false, IdempotentHint = true, OpenWorldHint = false }
    }).ToArray();

    /// <summary>严格校验全部已登记字段，再调用同一个Gateway并返回唯一结果。</summary>
    public async Task<CallToolResult> CallAsync(ActorContext actor, string name, IDictionary<string, JsonElement>? arguments, CancellationToken token)
    {
        try
        {
            // 能力名与版本只来自服务器白名单，调用方不能注入发布或任意查询工具。
            var capability = gateway.GetCapabilities().SingleOrDefault(value => value.Id == name && Allowed(value.Id))
                ?? throw new SemanticOperationException(422, "capability_invalid");
            // 缺省只表示空对象，仍必须满足全部required字段。
            var values = arguments ?? new Dictionary<string, JsonElement>();
            if (values.Keys.Any(key => !capability.InputSchema.Properties.Any(value => value.Name == key))
                || capability.InputSchema.Required.Any(key => !values.ContainsKey(key))) throw new SemanticOperationException(422, "tool_arguments_invalid");
            foreach (var parameter in capability.InputSchema.Properties)
            {
                if (!values.TryGetValue(parameter.Name, out var value)) continue;
                if (parameter.Type == "string" && value.ValueKind != JsonValueKind.String
                    || parameter.Type == "array" && (value.ValueKind != JsonValueKind.Array || value.EnumerateArray().Any(item => item.ValueKind != JsonValueKind.String))
                    || parameter.Type == "integer" && (!value.TryGetInt32(out var number) || number < parameter.Minimum || number > parameter.Maximum))
                    throw new SemanticOperationException(422, "tool_arguments_invalid");
            }
            // 由受控字段显式构造唯一计划，其他未提供可选字段保持null/空数组。
            var plan = new SemanticQueryPlan
            {
                CapabilityId = capability.Id, CapabilityVersion = capability.Version, AssetId = values["assetId"].GetString()!,
                ReleaseId = String(values, "releaseId"), EntityType = String(values, "entityType"), EntityIri = String(values, "entityIri"),
                ExternalId = String(values, "externalId"), SiteId = String(values, "siteId"),
                RelationshipIris = values.TryGetValue("relationshipIris", out var relationships) ? relationships.EnumerateArray().Select(value => value.GetString()!).ToArray() : [],
                Depth = values["depth"].GetInt32(), MaxRows = values["maxRows"].GetInt32(), TimeoutMs = values["timeoutMs"].GetInt32()
            };
            if (plan.TimeoutMs < 100) throw new SemanticOperationException(422, "tool_arguments_invalid");
            // 请求级独立绝对预算，同时传播真实传输取消。
            using var timeout = CancellationTokenSource.CreateLinkedTokenSource(token);
            timeout.CancelAfter(TimeSpan.FromSeconds(30));
            // 唯一结果在序列化时执行全部合同回调。
            var result = await gateway.ExecuteAsync(actor, plan, timeout.Token);
            // 结构化和文本兼容内容引用同一个真实JSON结果。
            var json = ExecutionRunService.Encode(result);
            return new CallToolResult { StructuredContent = JsonSerializer.Deserialize<JsonElement>(json), Content = [new TextContentBlock { Text = json }] };
        }
        catch (Exception failure) when (failure is SemanticOperationException or JsonException or InvalidOperationException or OperationCanceledException)
        {
            // MCP工具失败遵循SDK协议，不回显用户参数、异常或源查询。
            return new CallToolResult { IsError = true, Content = [new TextContentBlock { Text = "semantic_tool_rejected" }] };
        }
    }

    /// <summary>工具集合只允许当前正式授权三项。</summary>
    private static bool Allowed(string name) => name is "describe_ontology" or "resolve_entity" or "traverse_relationships";

    /// <summary>读取已验证可选字符串，不把任意JSON转成查询文本。</summary>
    private static string? String(IDictionary<string, JsonElement> values, string name) => values.TryGetValue(name, out var value) ? value.GetString() : null;

    /// <summary>有限登记模型转标准JSON Schema；保留预算、required及禁止额外字段。</summary>
    private static JsonElement InputSchema(CapabilityInputSchema source)
    {
        // 有序参数对象保证输出稳定，不引入身份参数。
        var properties = new JsonObject();
        foreach (var parameter in source.Properties)
        {
            // 每项Schema来自唯一Capability，而非另写第二套业务模型。
            var property = new JsonObject { ["type"] = parameter.Type, ["description"] = parameter.Description };
            if (parameter.Minimum is { } minimum) property["minimum"] = parameter.Name == "timeoutMs" ? Math.Max(100, minimum) : minimum;
            if (parameter.Maximum is { } maximum) property["maximum"] = maximum;
            if (parameter.ItemsType is { } items) property["items"] = new JsonObject { ["type"] = items };
            if (parameter.EnumValues.Length > 0) property["enum"] = JsonSerializer.SerializeToNode(parameter.EnumValues);
            properties[parameter.Name] = property;
        }
        return JsonSerializer.SerializeToElement(new JsonObject { ["type"] = source.Type, ["properties"] = properties, ["required"] = JsonSerializer.SerializeToNode(source.Required), ["additionalProperties"] = false });
    }
}
