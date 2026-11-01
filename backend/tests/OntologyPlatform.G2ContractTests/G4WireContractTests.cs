using System.Text.Json;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.G2ContractTests;

/// <summary>用真实序列化器验证M1公共合同，不代替PG或HTTP验收。</summary>
[TestClass]
public sealed class G4WireContractTests
{
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
