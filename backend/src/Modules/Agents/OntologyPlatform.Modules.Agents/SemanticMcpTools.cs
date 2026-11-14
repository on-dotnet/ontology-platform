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
    public SemanticMcpTools(ISemanticGateway gateway, IG4QueryRunStore? runs = null)
    {
        this.gateway = gateway;
        this.runs = runs;
    }

    /// <summary>G4运行引用由查询模块持久化；未配置时拒绝G4而不影响旧工具。</summary>
    private readonly IG4QueryRunStore? runs;

    /// <summary>只公开显式白名单，身份从服务器传入，不进入工具Schema。</summary>
    public Tool[] List() => gateway.GetCapabilities().Where(value => Allowed(value.Id)).Select(value => new Tool
    {
        Name = value.Id,
        Description = value.Meaning,
        InputSchema = InputSchema(value.InputSchema),
        OutputSchema = value.OutputSchema,
        Annotations = new ToolAnnotations { ReadOnlyHint = true, DestructiveHint = false, IdempotentHint = true, OpenWorldHint = false }
    }).Concat(G4Tools()).ToArray();

    /// <summary>严格校验全部已登记字段，再调用同一个Gateway并返回唯一结果。</summary>
    public async Task<CallToolResult> CallAsync(ActorContext actor, string name, IDictionary<string, JsonElement>? arguments, CancellationToken token, string? sessionReference = null, G4QueryRunReference? run = null)
    {
        try
        {
            if (name.StartsWith("g4_", StringComparison.Ordinal))
            {
                if (runs is null || string.IsNullOrWhiteSpace(sessionReference)) throw new SemanticOperationException(503, "query_run_unavailable");
                // 单次MCP请求也是一个服务器运行；MAF循环显式共用同一引用。
                var reference = run ?? new G4QueryRunReference(DateTimeOffset.UtcNow);
                // 每次进入都先计数，参数拒绝与恢复调用不能绕过工具预算。
                var delivery = await ExecutionRunService.ExecuteG4ToolAsync(runs, actor, sessionReference, reference,
                    budget => CallG4Async(actor, sessionReference, name, arguments, budget), token);
                // 文本与结构化内容只解码同一组规范字节。
                var text = delivery.ResultBytes is not null ? System.Text.Encoding.UTF8.GetString(delivery.ResultBytes) : JsonSerializer.Serialize(delivery.View, G4QueryJson.Options);
                return new CallToolResult { StructuredContent = JsonSerializer.Deserialize<JsonElement>(text), Content = [new TextContentBlock { Text = text }] };
            }
            // 能力名与版本只来自服务器白名单，调用方不能注入发布或任意查询工具。
            var capability = gateway.GetCapabilities().SingleOrDefault(value => value.Id == name && Allowed(value.Id))
                ?? throw new SemanticOperationException(422, "capability_invalid");
            // 缺省只表示空对象，仍必须满足全部required字段。
            var values = arguments ?? new Dictionary<string, JsonElement>();
            if (values.Keys.Any(key => !capability.InputSchema.Properties.Any(value => value.Name == key))
                || capability.InputSchema.Required.Any(key => !values.ContainsKey(key))) throw new SemanticOperationException(422, "tool_arguments_invalid");
            // 逐项执行唯一登记字段的类型及数值预算。
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
                CapabilityId = capability.Id,
                CapabilityVersion = capability.Version,
                AssetId = values["assetId"].GetString()!,
                ReleaseId = String(values, "releaseId"),
                EntityType = String(values, "entityType"),
                EntityIri = String(values, "entityIri"),
                ExternalId = String(values, "externalId"),
                SiteId = String(values, "siteId"),
                RelationshipIris = values.TryGetValue("relationshipIris", out var relationships) ? relationships.EnumerateArray().Select(value => value.GetString()!).ToArray() : [],
                Depth = values["depth"].GetInt32(),
                MaxRows = values["maxRows"].GetInt32(),
                TimeoutMs = values["timeoutMs"].GetInt32()
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

    /// <summary>SDK把对象转成字典前检查原始JSON重复键及64KiB预算；宿主仅对G4工具应用结果。</summary>
    public static bool RawG4PayloadRejected(ReadOnlyMemory<byte> bytes)
    {
        if (bytes.Length > 65536) return true;
        try
        {
            // 只做原件完整性校验，不在这里手抄MCP协议或工具Schema。
            using var document = JsonDocument.Parse(bytes);
            G4QueryRules.Unique(document.RootElement);
            return false;
        }
        catch (Exception error) when (error is JsonException or SemanticOperationException) { return true; }
    }

    /// <summary>三个执行工具及一个恢复工具直接复用生成的输入和联合输出组件。</summary>
    private IEnumerable<Tool> G4Tools()
    {
        if (!gateway.GetCapabilities().Any(item => item.Id == "g4_resolve_entity")) yield break;
        // 生成组件闭包只在当前真实能力已注册时读取。
        var query = JsonNode.Parse(gateway.GetG4Schema("G4SemanticQuery").GetRawText())!.AsObject();
        // 所有引用在工具顶层定义，避免嵌套Schema的根引用失效。
        var definitions = query["$defs"]!.DeepClone();
        query.Remove("$defs");
        // QueryView与最终结果用不同必需判别字段，成功响应没有第三种形状。
        var result = JsonNode.Parse(gateway.GetG4Schema("G4QueryResultV1").GetRawText())!.AsObject();
        // 视图组件与结果组件共用一个可解析闭包。
        var view = JsonNode.Parse(gateway.GetG4Schema("G4QueryView").GetRawText())!.AsObject();
        // 输出定义合并只来自同一生成文档。
        var outputDefinitions = result["$defs"]!.AsObject();
        foreach (var item in view["$defs"]!.AsObject()) if (!outputDefinitions.ContainsKey(item.Key)) outputDefinitions[item.Key] = item.Value!.DeepClone();
        // 引用节点不能同时挂到两个父节点。
        var output = new JsonObject { ["oneOf"] = new JsonArray(new JsonObject { ["$ref"] = "#/$defs/G4QueryView" }, new JsonObject { ["$ref"] = "#/$defs/G4QueryResultV1" }), ["$defs"] = outputDefinitions.DeepClone() };
        foreach (var name in new[] { "g4_resolve_entity", "g4_read_observations", "g4_traverse_relationships", "g4_query_result" })
        {
            // 恢复只接收不透明queryId，执行包装固定三个必填字段。
            var properties = name == "g4_query_result" ? new JsonObject { ["queryId"] = new JsonObject { ["type"] = "string", ["minLength"] = 1, ["maxLength"] = 128 } }
                : new JsonObject { ["query"] = query.DeepClone(), ["idempotencyKey"] = new JsonObject { ["type"] = "string", ["minLength"] = 1, ["maxLength"] = 128 }, ["selectionQueryId"] = new JsonObject { ["type"] = new JsonArray("string", "null"), ["maxLength"] = 128 } };
            // required与additionalProperties明确封闭包装对象。
            var input = new JsonObject { ["type"] = "object", ["additionalProperties"] = false,
                ["properties"] = properties, ["required"] = JsonSerializer.SerializeToNode(properties.Select(item => item.Key).ToArray()), ["$defs"] = definitions.DeepClone() };
            yield return new Tool { Name = name, Description = name == "g4_query_result" ? "按当前授权恢复本人查询原结果" : "通过唯一语义网关执行正式映射查询",
                InputSchema = JsonSerializer.SerializeToElement(input), OutputSchema = JsonSerializer.SerializeToElement(output),
                Annotations = new ToolAnnotations { ReadOnlyHint = true, DestructiveHint = false, IdempotentHint = true, OpenWorldHint = false } };
        }
    }

    /// <summary>G4输入不转换成旧G2计划，当前会话只能来自宿主上下文。</summary>
    private async Task<G4QueryDelivery> CallG4Async(ActorContext actor, string? sessionReference, string name, IDictionary<string, JsonElement>? arguments, CancellationToken token)
    {
        if (string.IsNullOrWhiteSpace(sessionReference) || arguments is null) throw new SemanticOperationException(403, "query_forbidden");
        // 包装与内部查询共享64KiB请求预算。
        var bytes = JsonSerializer.SerializeToUtf8Bytes(arguments);
        if (bytes.Length > 65536) throw new SemanticOperationException(400, "query_payload_invalid");
        // 工具成功结果直接使用Gateway提供的规范字节，文本和StructuredContent完全相同。
        G4QueryDelivery delivery;
        if (name == "g4_query_result")
        {
            if (arguments.Count != 1 || !arguments.TryGetValue("queryId", out var id) || id.ValueKind != JsonValueKind.String) throw new SemanticOperationException(400, "query_payload_invalid");
            G4QueryRules.Identifier(id.GetString());
            delivery = await gateway.ReadG4Async(actor, sessionReference, id.GetString()!, true, token);
        }
        else
        {
            if (arguments.Count != 3 || !arguments.TryGetValue("query", out var queryValue) || !arguments.TryGetValue("idempotencyKey", out var key)
                || !arguments.TryGetValue("selectionQueryId", out var selection) || key.ValueKind != JsonValueKind.String || selection.ValueKind is not (JsonValueKind.String or JsonValueKind.Null))
                throw new SemanticOperationException(400, "query_payload_invalid");
            // 使用正式严格查询解析器，不信任模型传来的能力名或版本。
            var selectionId = selection.ValueKind == JsonValueKind.Null ? null : selection.GetString();
            // 未登记能力或name/query不一致立即拒绝，不静默替换请求字段。
            var query = G4QueryRules.ReadQuery(System.Text.Encoding.UTF8.GetBytes(queryValue.GetRawText()), selectionId);
            if (name != query.CapabilityId || !gateway.GetCapabilities().Any(item => item.Id == name && item.Version == query.CapabilityVersion)) throw new SemanticOperationException(422, "capability_not_supported");
            delivery = await gateway.ExecuteG4Async(actor, sessionReference, query, key.GetString()!, selectionId, token);
        }
        return delivery;
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
