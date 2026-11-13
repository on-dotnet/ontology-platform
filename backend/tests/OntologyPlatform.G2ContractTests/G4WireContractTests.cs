using System.Text.Json;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.G2ContractTests;

/// <summary>用真实序列化器验证M1公共合同，不代替PG或HTTP验收。</summary>
[TestClass]
public sealed class G4WireContractTests
{
    /// <summary>四个已批准用途仅扩展精确字符串值域，未知用途仍拒绝。</summary>
    [TestMethod]
    public void SecretIntakeAcceptsOnlyApprovedTypedPurposes()
    {
        // 其它字段保持合法且无真实凭据，隔离Purpose校验边界。
        var request = new ConnectionSecretIntakeRequest
        {
            SecretValue = "synthetic-key", Purpose = "WEB_API_KEY",
            ScopeSelection = new ResourceScope { OrganizationId = "org-demo", SiteIds = ["site-a"] },
            Command = new CommandContext { CommandId = "cmd", IdempotencyKey = "key", ExpectedRevision = 0, Reason = "合成用途校验" }
        };
        G4ConnectionRules.Validate(request);
        G4ConnectionRules.Validate(request with { Purpose = "POSTGRESQL_READONLY" });
        G4ConnectionRules.Validate(request with { Purpose = "DORIS_READONLY" });
        G4ConnectionRules.Validate(request with { Purpose = "ORACLE_READONLY" });
        Assert.Throws<SemanticOperationException>(() => G4ConnectionRules.Validate(request with { Purpose = "OTHER" }));
    }

    /// <summary>Oracle公开配置也必须拒绝明文，不能等到网络调用才发现降级。</summary>
    [TestMethod]
    public void OraclePlaintextIsRejectedBeforeCredentialConsumption()
    {
        // 固定其它合法字段，只改变TLS以证明请求边界拒绝明文。
        var profile = new OracleConnectionProfile { Host = "oracle-source", Port = 2484, ServiceName = "FREEPDB1", Username = "FIXTURE_READER", Tls = true, AllowedOwners = ["PRODUCTION", "CaseOwner"] };
        G4ConnectionRules.Config(new OracleConnectionConfig { Profile = profile });
        Assert.Throws<SemanticOperationException>(() => G4ConnectionRules.Config(new OracleConnectionConfig { Profile = profile with { Tls = false } }));
    }

    /// <summary>Oracle元数据保留显式未知值、负scale和旧合同的省略语义。</summary>
    [TestMethod]
    public void OracleMetadataRoundtripsWithoutInventingKnownValues()
    {
        // 旧列的黄金JSON不包含新增字段，旧指纹输入必须逐字保持。
        const string legacy = "{\"name\":\"N\",\"nativeType\":\"NUMBER\",\"nullable\":true,\"ordinal\":1,\"precision\":null,\"scale\":-2}";
        // 新元数据明确表示未知owner/长度和时区，不以CLR默认值填充。
        const string metadata = "{\"dataTypeOwner\":null,\"byteLength\":null,\"charLength\":null,\"charSemantics\":null,\"fractionalSecondsPrecision\":null,\"timeZoneKind\":\"UNKNOWN\",\"supportStatus\":\"METADATA_ONLY\"}";
        // 真实序列化器必须保留所有显式null和负scale。
        var raw = legacy[..^1] + ",\"oracleMetadata\":" + metadata + "}";
        // 新字段存在时应完整往返。
        var parsed = JsonSerializer.Deserialize<CatalogField>(raw, G4ConnectionJson.Options)!;
        Assert.AreEqual(raw, JsonSerializer.Serialize(parsed, G4ConnectionJson.Options));
        Assert.AreEqual(legacy, JsonSerializer.Serialize(JsonSerializer.Deserialize<CatalogField>(legacy, G4ConnectionJson.Options), G4ConnectionJson.Options));
        // 两个合法字符单位都应保留大小写并完整往返。
        foreach (var semantics in new[] { "BYTE", "CHAR" })
        {
            // 只替换字符单位，其余显式未知值保持原样。
            var known = raw.Replace("\"charSemantics\":null", "\"charSemantics\":\"" + semantics + "\"");
            Assert.AreEqual(known, JsonSerializer.Serialize(JsonSerializer.Deserialize<CatalogField>(known, G4ConnectionJson.Options), G4ConnectionJson.Options));
        }
        foreach (var invalid in new[]
        {
            raw.Replace("\"timeZoneKind\":\"UNKNOWN\",", ""),
            raw.Replace("\"supportStatus\":\"METADATA_ONLY\"", "\"supportStatus\":\"OTHER\""),
            raw.Replace("\"timeZoneKind\":\"UNKNOWN\"", "\"timeZoneKind\":null"),
            raw.Replace("\"charSemantics\":null", "\"charSemantics\":\"OTHER\""),
            raw.Replace("\"charSemantics\":null", "\"charSemantics\":\"byte\"")
        })
        {
            Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<CatalogField>(invalid, G4ConnectionJson.Options));
        }
    }

    /// <summary>Doris明文配置在请求验证阶段拒绝，不能消费凭据后才降级。</summary>
    [TestMethod]
    public void DorisPlaintextIsRejectedBeforeCredentialConsumption()
    {
        // 固定合法配置，仅切换TLS以隔离降级输入。
        var profile = new DorisConnectionProfile { FeHost = "doris-fe", QueryPort = 9030, Catalog = "internal", Database = "fixture", Username = "fixture_reader", Tls = true };
        G4ConnectionRules.Config(new DorisConnectionConfig { Profile = profile });
        Assert.Throws<SemanticOperationException>(() => G4ConnectionRules.Config(new DorisConnectionConfig { Profile = profile with { Tls = false } }));
    }

    /// <summary>配置判别与字段一致且可真实往返。</summary>
    [TestMethod]
    [DataRow("POSTGRESQL", "{\"host\":\"pg-source\",\"port\":5432,\"database\":\"fixture\",\"username\":\"fixture_reader\",\"sslMode\":\"VerifyFull\",\"allowedSchemas\":[\"production\"]}")]
    [DataRow("ORACLE", "{\"host\":\"oracle\",\"port\":1521,\"serviceName\":\"svc\",\"username\":\"reader\",\"tls\":true,\"allowedOwners\":[\"OWNER\"]}")]
    [DataRow("DORIS", "{\"feHost\":\"doris\",\"queryPort\":9030,\"catalog\":\"internal\",\"database\":\"fixture\",\"username\":\"reader\",\"tls\":true}")]
    [DataRow("TDENGINE", "{\"wsUrl\":\"wss://td.invalid\",\"database\":\"fixture\",\"timePrecision\":\"UNKNOWN\",\"timeZone\":null}")]
    [DataRow("WEB_API", "{\"baseOrigin\":\"https://api.invalid\",\"operationId\":\"read\",\"method\":\"GET\",\"approvedPath\":\"/items\",\"authentication\":\"NONE\",\"pagination\":\"NONE\",\"hostPolicyRef\":\"synthetic\"}")]
    public void FiveProfilesRoundtripAndRejectInjectedField(string kind, string profile)
    {
        // 宿主使用相同Web命名与非空检查，未知字段不能静默吞掉。
        var options = G4ConnectionJson.Options;
        // 正例仅含唯一判别与对应参数，不使用设计包装。
        var raw = "{\"type\":\"" + kind + "\",\"profile\":" + profile + "}";
        // 实际反序列化得到对应强类型分支。
        var model = JsonSerializer.Deserialize<ConnectionConfig>(raw, options)!;
        G4ConnectionRules.Config(model);
        StringAssert.Contains(JsonSerializer.Serialize(model, options), kind);
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<ConnectionConfig>(raw[..^1] + ",\"actor\":\"forged\"}", options));
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<ConnectionConfig>(raw.Replace("\"profile\":{", "\"profile\":{\"credentialRef\":\"forged\","), options));
    }

    /// <summary>修订必须是JSON整数，不能把布尔或文本当零。</summary>
    [TestMethod]
    [DataRow("null")]
    [DataRow("true")]
    [DataRow("\"0\"")]
    [DataRow("1.5")]
    public void CommandRevisionRejectsNonInteger(string revision)
    {
        // 正常四字段命令只改变修订类型以隔离失败原因。
        var raw = "{\"commandId\":\"cmd\",\"idempotencyKey\":\"key\",\"expectedRevision\":" + revision + ",\"reason\":\"合成验证\"}";
        Assert.Throws<JsonException>(() => JsonSerializer.Deserialize<CommandContext>(raw, G4ConnectionJson.Options));
    }
    /// <summary>结构合法仍必须经过唯一语义规则拒绝错误参数。</summary>
    [TestMethod]
    [DataRow("port")]
    [DataRow("database")]
    [DataRow("tls")]
    [DataRow("schema-null")]
    [DataRow("schema-sql")]
    public void InvalidPgValuesCannotReachAdapter(string mutation)
    {
        // 从有效配置只改变一个字段，确保拒绝来自对应字段规则。
        var profile = new PgConnectionProfile { Host = "pg-source", Port = 5432, Database = "fixture", Username = "fixture_reader", SslMode = "VerifyFull", AllowedSchemas = ["production"] };
        // 各输入均能表示为JSON，必须在服务器规则层明确拒绝。
        profile = mutation switch
        {
            "port" => profile with { Port = 0 },
            "database" => profile with { Database = "" },
            "tls" => profile with { SslMode = "Disable" },
            "schema-null" => profile with { AllowedSchemas = [null!] },
            _ => profile with { AllowedSchemas = ["production;drop table x"] }
        };
        Assert.Throws<SemanticOperationException>(() => G4ConnectionRules.Config(new PgConnectionConfig { Profile = profile }));
    }

    /// <summary>只有命令没有编辑值时不能制造修订与成功审计。</summary>
    [TestMethod]
    public void EmptyPatchFailsSemanticValidation()
    {
        // JSON结构满足必填command，仍不是有效编辑命令。
        var request = new ConnectionPatchRequest { Command = new CommandContext { CommandId = "cmd", IdempotencyKey = "key", ExpectedRevision = 1, Reason = "合成" } };
        Assert.Throws<SemanticOperationException>(() => G4ConnectionRules.Validate(request));
    }
}
