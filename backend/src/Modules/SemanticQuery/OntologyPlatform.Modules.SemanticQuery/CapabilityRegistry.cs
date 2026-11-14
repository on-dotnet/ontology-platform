using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.Configuration;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>从唯一机器生成DTO组件取得严格输出Schema，并稳定绑定受控执行器版本。</summary>
public sealed class CapabilityRegistry
{
    /// <summary>此实现默认登记三项旧能力，G4宿主另启用三项查询能力已批准的正式只读能力。</summary>
    private readonly SemanticCapability[] capabilities;

    /// <summary>旧能力默认保持原字节；只有真实G4组合开启后才加载其正式生成Schema。</summary>
    public CapabilityRegistry(IConfiguration? configuration = null)
    {
        capabilities = configuration?.GetValue<bool>("G4:QueryEnabled") == true ? [.. Create(), .. CreateG4()] : Create();
    }

    /// <summary>仅暴露三个已冻结G4传输组件，保持生成文档为唯一Schema来源。</summary>
    public JsonElement G4Schema(string name)
    {
        if (!capabilities.Any(item => item.Id == "g4_resolve_entity") || name is not ("G4SemanticQuery" or "G4QueryResultV1" or "G4QueryView"))
            throw new SemanticOperationException(422, "capability_not_supported");
        return ComponentSchema("OntologyPlatform.G4OpenApiSchemas.json", name);
    }

    /// <summary>返回防止调用方修改内部数组的能力副本。</summary>
    public SemanticCapability[] Read() => JsonSerializer.Deserialize<SemanticCapability[]>(JsonSerializer.Serialize(capabilities))!;

    /// <summary>拒绝未登记或错误版本的工具计划。</summary>
    internal SemanticCapability Resolve(SemanticQueryPlan plan) => capabilities.SingleOrDefault(value => value.Id == plan.CapabilityId && value.Version == plan.CapabilityVersion) ?? throw new SemanticOperationException(422, "capability_invalid");

    /// <summary>G4版本与机器Schema和真实分支计划绑定，未登记能力始终拒绝。</summary>
    internal SemanticCapability Resolve(G4SemanticQuery query) => capabilities.SingleOrDefault(value => value.Id == query.CapabilityId && value.Version == query.CapabilityVersion)
        ?? throw new SemanticOperationException(422, "capability_not_supported");

    /// <summary>S1只登记已经贯通的单实体PG计划；S3增加实际执行分支时推进计划身份。</summary>
    private static SemanticCapability[] CreateG4()
    {
        // 输入和输出都来自同一DTO及实际路由生成文档，不能手抄另一套Schema。
        var input = ComponentSchema("OntologyPlatform.G4OpenApiSchemas.json", "G4SemanticQuery");
        // 结果联合必须保留全部判别分支，即使当前能力只产生实体分支。
        var output = ComponentSchema("OntologyPlatform.G4OpenApiSchemas.json", "G4QueryResultV1");
        // 计划身份显式描述必需分支，不以运行时任意选表代替登记。
        return new[] { "g4_resolve_entity", "g4_read_observations", "g4_traverse_relationships" }.Select(id =>
        {
        // 三能力共享唯一根和发布关系分支计划，版本随实际执行语义推进。
        var executor = "g4-query/" + id + "/s3-root-published-relations-pg-v2";
        // 规范hash涵盖完整嵌套输入和输出而非简写能力展示字段。
        var version = G4QueryCanonical.Hash(G4QueryCanonical.Serialize(new { input, output, executor, requiredBranches = new[] { "unique-mapping-root", "published-directed-relations-within-depth" } }));
        return new SemanticCapability
        {
            Id = id, Version = version, ExecutorId = executor, Policy = "data.query.execute",
            Meaning = id == "g4_resolve_entity" ? "定位业务实体" : id == "g4_read_observations" ? "读取精确观测" : "追溯已发布关系",
            InputSchema = new CapabilityInputSchema { SchemaVersion = 1, Type = "object", AdditionalProperties = false,
                Required = ["assetId", "ontologyReleaseId", "mappingReleaseIds", "capabilityId", "capabilityVersion", "relationshipIris", "depth", "maxRows", "timeoutMs", "filters"],
                Properties = [Parameter("assetId", "string", "正式本体资产"), Parameter("ontologyReleaseId", "string", "固定本体发布"),
                    Parameter("mappingReleaseIds", "array", "唯一固定映射发布"), Parameter("capabilityId", "string", "登记能力"),
                    Parameter("capabilityVersion", "string", "完整Schema与执行计划散列"), Parameter("relationshipIris", "array", "正式关系路径"),
                    Parameter("depth", "integer", "深度", 1, 5), Parameter("maxRows", "integer", "返回项数", 2, 100),
                    Parameter("timeoutMs", "integer", "总毫秒预算", 100, 5000), Parameter("filters", "object", "封闭身份与时间过滤")] },
            OutputSchema = output, Budgets = new CapabilityBudget { MaxDepth = 5, MaxRows = 100, TimeoutMs = 5000, MaxToolCalls = 3 }
        };
        }).ToArray();
    }

    /// <summary>完整输入字段的有限描述保持服务端约束，不接收客户端actor。</summary>
    private static SemanticCapability[] Create()
    {
        // 输出来自嵌入的机器生成组件闭包，保留所有联合与空值约束。
        var output = OutputSchema();
        // 每项受控能力的固定ID与中文含义。
        var definitions = new[] { ("describe_ontology", "读取正式本体类与属性"), ("resolve_entity", "按全局身份或厂区业务号定位实体"), ("traverse_relationships", "沿正式对象属性双向追溯有界关系子图") };
        return definitions.Select(item =>
        {
            // 服务器按工具ID补入能力身份，用户输入仅为以下受控参数。
            var input = new CapabilityInputSchema
            {
                SchemaVersion = 1,
                Type = "object",
                AdditionalProperties = false,
                Required = ["assetId", "depth", "maxRows", "timeoutMs"],
                Properties = [Parameter("assetId", "string", "正式资产标识"), Parameter("releaseId", "string", "可选历史正式发布"), Parameter("entityType", "string", "正式类IRI"), Parameter("entityIri", "string", "实体完整IRI"), Parameter("externalId", "string", "业务外部号"), Parameter("siteId", "string", "授权厂区"), Parameter("relationshipIris", "array", "正式对象属性路径"), Parameter("depth", "integer", "遍历深度", 1, 5), Parameter("maxRows", "integer", "最大返回行数", 1, 100), Parameter("timeoutMs", "integer", "毫秒预算", 100, 5000)]
            };
            // 执行器语义标识纳入散列；代码语义变化必须推进此标识。
            var executor = "semantic-query/" + item.Item1 + "/4";
            // 序列化属性顺序确定，输出组件和定义按序排列，因此同构建跨进程稳定。
            var version = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { input, output, executor }))));
            return new SemanticCapability { Id = item.Item1, Version = version, InputSchema = input, OutputSchema = output, Meaning = item.Item2, Policy = "semantic.read", ExecutorId = executor, Budgets = new CapabilityBudget { MaxDepth = 5, MaxRows = 100, TimeoutMs = 5000, MaxToolCalls = 3 } };
        }).ToArray();
    }

    /// <summary>构造一个实际执行器接受的有限输入参数。</summary>
    private static CapabilityParameter Parameter(string name, string type, string description, int? minimum = null, int? maximum = null) => new() { Name = name, Type = type, Description = description, Minimum = minimum, Maximum = maximum, ItemsType = type == "array" ? "string" : null };

    /// <summary>读取SemanticQueryResult可达组件，未知引用立即失败，不弱化输出Schema。</summary>
    private static JsonElement OutputSchema() => ComponentSchema("OntologyPlatform.G2OpenApiSchemas.json", "SemanticQueryResult");

    /// <summary>从唯一生成物读取完整可达组件闭包，缺失时失败启动而不是登记空壳能力。</summary>
    private static JsonElement ComponentSchema(string resource, string root)
    {
        // 该资源是Master维护的机器生成bootstrap组件，不声称其空paths为运行API导出。
        using var stream = typeof(CapabilityRegistry).Assembly.GetManifestResourceStream(resource) ?? throw new InvalidOperationException("缺少唯一输出Schema资源。");
        // 解析后仅重写组件引用路径，保留原始Schema全部关键字。
        var components = JsonNode.Parse(stream)!["components"]!["schemas"]!.AsObject();
        // 队列与集合保证递归引用只复制一次。
        var pending = new Queue<string>([root]);
        // 定义按名称排序，避免遍历顺序影响hash版本。
        var definitions = new SortedDictionary<string, JsonNode>(StringComparer.Ordinal);
        while (pending.TryDequeue(out var name))
        {
            if (definitions.ContainsKey(name)) continue;
            // 缺失引用不是可以忽略的未知结构。
            var schema = components[name]?.DeepClone() ?? throw new InvalidOperationException("输出Schema引用缺失。");
            definitions.Add(name, schema);
            Rewrite(schema, pending);
        }
        // 标准JSON Schema 2020-12文档根引用同一唯一结果定义。
        var document = new JsonObject { ["$schema"] = "https://json-schema.org/draft/2020-12/schema", ["$ref"] = "#/$defs/" + root, ["$defs"] = new JsonObject(definitions.Select(value => new KeyValuePair<string, JsonNode?>(value.Key, value.Value))) };
        return JsonSerializer.SerializeToElement(document);
    }

    /// <summary>递归保留对象与数组，只将本地OpenAPI组件引用换为标准defs引用。</summary>
    private static void Rewrite(JsonNode node, Queue<string> pending)
    {
        if (node is JsonObject map)
        {
            if (map["$ref"] is JsonValue value)
            {
                // 唯一受信组件前缀，不允许远程Schema地址。
                var reference = value.GetValue<string>();
                if (!reference.StartsWith("#/components/schemas/", StringComparison.Ordinal)) throw new InvalidOperationException("输出Schema存在未知引用。");
                // 保留JSON Pointer编码名称，不能解码为另一组件。
                var name = reference[21..];
                pending.Enqueue(name);
                map["$ref"] = "#/$defs/" + name;
            }
            // 每个对象子Schema继续保留其所有关键字和引用。
            foreach (var child in map.Select(value => value.Value).OfType<JsonNode>()) Rewrite(child, pending);
        }
        else if (node is JsonArray list)
        {
            // 数组中的oneOf/枚举/元组项也必须完整处理。
            foreach (var child in list.OfType<JsonNode>()) Rewrite(child, pending);
        }
    }
}
