using System.Data.Common;
using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using OntologyPlatform.Contracts;

[assembly: System.Runtime.CompilerServices.InternalsVisibleTo("OntologyPlatform.Api")]

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>一次性维护进程验证过的私有输入，不是产品请求，也不能通过 HTTP 或 MCP 构造。</summary>
internal sealed class G4OracleMaintenanceProof
{
    /// <summary>保留准确输入字节解析得到的只读证据对象。</summary>
    private readonly JsonElement proof;

    /// <summary>保留唯一被授权的准确后继，不从数据库刷新目标身份。</summary>
    internal const string QueryId = "query-18b5ee00b53e4e4eafc43cc4717bd293";

    /// <summary>正式 Binding 引用的目标连接。</summary>
    internal const string ConnectionId = "a7913bb552eb4cd1a3f6eaf5b93cd619";

    /// <summary>未获产品时限内物理确认的原 owner。</summary>
    internal const string Owner = "oracle-execution-004f5b3e04084f1998201939aaeec5e6";

    /// <summary>实际源数据库服务的完整引擎身份。</summary>
    internal const string SourceContainer = "00c4f5dabf4a9348adf0f8910f28015f4a84301f56548e4da23642227c223f09";

    /// <summary>实际任务平台库的完整引擎身份。</summary>
    internal const string PlatformContainer = "eb3c386dbfe423d22f71f638d1be1c62d30d181e6e6decc039ead85b3ea2dbe5";

    /// <summary>只由验证准确原字节、独立观察与封闭回执后的入口产生。</summary>
    private G4OracleMaintenanceProof(JsonElement proof) => this.proof = proof;

    /// <summary>取得经封闭字段表核验的字符串值。</summary>
    internal string this[string name] => proof.GetProperty(name).GetString() ?? throw Invalid();

    /// <summary>读取 ISO UTC 原时间，拒绝自动推断本地时区。</summary>
    internal DateTimeOffset Utc(string name)
    {
        // 原件允许显式 UTC 偏移，转为同一 UTC 值后和平台列逐项比较。
        var text = this[name];
        Check((text.EndsWith('Z') || text.EndsWith("+00:00", StringComparison.Ordinal)) &&
            DateTimeOffset.TryParse(text, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind, out _));
        return DateTimeOffset.Parse(text, CultureInfo.InvariantCulture, DateTimeStyles.RoundtripKind);
    }

    /// <summary>在事务锁内外分别核当前证明仍在五分钟有界维护窗口中。</summary>
    internal void DemandFresh(DateTimeOffset now)
    {
        // 新鲜期限只约束此任务级证明，绝不改原产品清理时限。
        var verified = Utc("verifiedUtc");
        // 不能用远期时间延长维护证明。
        var until = Utc("validUntilUtc");
        Check(verified <= now && now < until && until - verified <= TimeSpan.FromMinutes(5));
    }

    /// <summary>只接受已由独立维护执行器登记的原字节、准确观察及已封闭业务入口。</summary>
    internal static G4OracleMaintenanceProof Read(byte[] bytes, string expectedSha, string operatorId, string sealSha,
        string terminationSha, bool isolated = false)
    {
        Check(bytes.Length is > 0 and <= 65536 && G4QueryCanonical.Hash(bytes) == expectedSha);
        using var document = JsonDocument.Parse(bytes);
        // 所有字段必须唯一且准确；输入声明不能替代私有进程环境传入的独立证据摘要。
        var fields = "taskId runId attemptId operationId operatorId systemIdentifier database databaseUser organizationId queryId connectionId owner originalFence terminalFence clientId instanceId conId sid serial audsid sqlId sqlExecId platformContainerId sourceContainerId createdUtc deadlineUtc completedUtc leaseUntilUtc requestSha256 bindingSha256 stableRowSha256 cancelAuditId cancelAuditSha256 sealSha256 terminationProofSha256 verifiedUtc validUntilUtc".Split(' ');
        // 按键数和集合双检，避免重复 JSON 属性掩盖错误身份。
        var names = document.RootElement.EnumerateObject().Select(p => p.Name).ToArray();
        Check(names.Length == fields.Length && fields.ToHashSet(StringComparer.Ordinal).SetEquals(names));
        // 对象独立于临时 JsonDocument 的生命周期。
        var value = new G4OracleMaintenanceProof(document.RootElement.Clone());
        Check(value["taskId"] == "G4-ORACLE-MAPPING-QUERY-001" && value["runId"] == "implementation-01"
            && value["organizationId"] == "org-demo" && value["queryId"] == QueryId && value["connectionId"] == ConnectionId
            && value["owner"] == Owner && value["clientId"] == "0e224578b55b4b479d98d3fa4ff1ac46" && value["sqlId"] == "dum3m3c96vc07"
            && value["platformContainerId"] == PlatformContainer && value["sourceContainerId"] == SourceContainer);
        foreach (var (key, number) in new[] { ("originalFence", 1), ("terminalFence", 2), ("instanceId", 1), ("conId", 3),
            ("sid", 60), ("serial", 51748), ("audsid", 50045), ("sqlExecId", 16777219) })
            Check(value.proof.GetProperty(key).GetInt32() == number);
        foreach (var key in new[] { "requestSha256", "bindingSha256", "stableRowSha256", "cancelAuditSha256", "sealSha256", "terminationProofSha256" })
            Check(Regex.IsMatch(value[key], @"\A[0-9a-f]{64}\z"));
        foreach (var key in new[] { "attemptId", "operationId", "cancelAuditId" })
            Check(Regex.IsMatch(value[key], @"\A[0-9a-f]{32}\z"));
        Check(value["operatorId"] == operatorId && Regex.IsMatch(operatorId, @"\Aos-uid-[0-9]{1,10}\z")
            && sealSha == value["sealSha256"] && terminationSha == value["terminationProofSha256"] && sealSha != terminationSha
            && Regex.IsMatch(value["systemIdentifier"], @"\A[0-9]{1,20}\z")
            && Regex.IsMatch(value["databaseUser"], @"\A[a-z_][a-z0-9_]{0,62}\z") && (isolated
                ? Regex.IsMatch(value["database"], @"\Aomq_query_test_[a-z0-9_]+\z") : value["database"] == "mapping"));
        if (!isolated)
        {
            // 首次真实只读快照冻结的物理集群及不可变原件。后续独立观察只能更新其新鲜证明。
            Check(value["systemIdentifier"] == "7709907053089669168" && value["databaseUser"] == "postgres" && operatorId == "os-uid-501"
                && value["requestSha256"] == "6f9417572fbba281c8e530bee3bd5145722fc78cb9011e562aa63f2ca9178a98"
                && value["bindingSha256"] == "1ce4785488a1421b3216be2bc8b2855577643e70a19b2aca4cf2e364fe0d2999"
                && value["stableRowSha256"] == "3f49e5938439ddc765b6e5ad9d2a3ea0b37d1132d2d769870d9b8c179ed1066f"
                && value["cancelAuditSha256"] == "d39c7404dfc2a222e52feccd74125a574b8456d68d593a3735fd61fdcc1414ad"
                && value["cancelAuditId"] == "5f1275a6948b4ea5a33f0dc671ae93a4");
        }
        value.DemandFresh(DateTimeOffset.UtcNow);
        return value;
    }

    /// <summary>全部拒绝使用固定诊断，私有输入不会出现在公开错误信息中。</summary>
    internal static void Check(bool valid)
    {
        if (!valid) throw Invalid();
    }

    /// <summary>创建固定拒绝异常。</summary>
    private static InvalidOperationException Invalid() => new("oracle_maintenance_precondition_failed");
}

/// <summary>仅处理已批准旧行的任务级恢复，与原产品清理 CAS 分离。</summary>
internal static class G4OracleMaintenance
{
    /// <summary>在持锁同一事务中复核治理事实、准确行与原始字节，再更新两列并记录一次维护审计。</summary>
    internal static async Task<string> RecoverAsync(G4QueryDbContext db, ITransactionalAuditWriter audit,
        G4OracleMaintenanceProof proof, Func<DbConnection, DbTransaction, CancellationToken, Task<JsonElement>> auditFacts,
        CancellationToken token)
    {
        // UTC 显式固定 PG 的原始 jsonb 文本摘要，即使数据库缺省时区以后发生变化。
        await using var transaction = await db.Database.BeginTransactionAsync(token);
        await db.Database.ExecuteSqlRawAsync("SET LOCAL TIME ZONE 'UTC'", token);
        await G4QueryResultStore.LockCapacityAsync(db, token);
        // 准确行锁沿产品既有顺序在容量锁之后取得。
        var row = await G4QueryResultStore.LockedAsync(db, G4OracleMaintenanceProof.QueryId, token);
        // 证明绑定物理 PostgreSQL 集群、数据库、当前用户和其余全部查询字段。
        var databaseFacts = await db.Database.SqlQuery<string>($"""
            SELECT json_build_array((pg_control_system()).system_identifier::text, current_database(), current_user,
                encode(sha256(convert_to((to_jsonb(q)-'LeaseOwner'-'LeaseUntilUtc')::text,'UTF8')),'hex'))::text AS "Value"
            FROM semantic_query."Queries" q WHERE q."Id" = {row.Id}
            """).SingleAsync(token);
        // JSON 只含平台身份与摘要。
        var values = JsonSerializer.Deserialize<string[]>(databaseFacts)!;
        G4OracleMaintenanceProof.Check(values.SequenceEqual(new[] { proof["systemIdentifier"], proof["database"], proof["databaseUser"], proof["stableRowSha256"] }));
        // 现行语义合同必须能重新打开原请求与稳定的 binding，不能仅凭投影列更新。
        var state = G4QueryResultStore.ReadState(row);
        _ = G4QueryResultStore.ReadRequest(row);
        G4OracleMaintenanceProof.Check(row.OrganizationId == proof["organizationId"] && row.ConnectionId == proof["connectionId"]
            && state.Binding.ConnectionId == row.ConnectionId && state.Scope.OrganizationId == row.OrganizationId
            && state.Scope.SiteIds.SequenceEqual(["site-a"]) && state.Receipts.Length == 0 && row.ExecutionStatus == "CANCELLED"
            && row.CancelRequested && row.Fence == 2 && row.ResultHash is null && row.ResultSize == 0 && row.ResultCiphertext.Length == 0
            && row.CreatedAtUtc == proof.Utc("createdUtc") && row.DeadlineAtUtc == proof.Utc("deadlineUtc")
            && row.CompletedAtUtc == proof.Utc("completedUtc") && row.RequestHash == proof["requestSha256"]
            && G4QueryCanonical.Hash(row.RequestBytes) == row.RequestHash && G4QueryCanonical.Hash(row.BindingBytes) == proof["bindingSha256"]);
        // 治理模块通过调用者同一物理事务提供准确行的审计投影。
        var facts = await auditFacts(db.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
        // 原取消审计必须保持唯一且与私有原快照逐字节关联。
        var cancels = facts.EnumerateArray().Where(a => a.GetProperty("action").GetString() == "data.query.cancel").ToArray();
        G4OracleMaintenanceProof.Check(cancels.Length == 1 && cancels[0].GetProperty("outcome").GetString() == "allowed"
            && cancels[0].GetProperty("id").GetString() == proof["cancelAuditId"] && cancels[0].GetProperty("sha256").GetString() == proof["cancelAuditSha256"]
            && !facts.EnumerateArray().Any(a => a.GetProperty("action").GetString() == "data.query.execute" && a.GetProperty("outcome").GetString() == "allowed"));
        // 只认可同一实际维护身份、操作和尝试，未知清空不能按幂等成功返回。
        var recovered = facts.EnumerateArray().Where(a => a.GetProperty("action").GetString() == "data.query.cleanup.recover").ToArray();
        proof.DemandFresh(DateTimeOffset.UtcNow);
        if (row.LeaseOwner is null && row.LeaseUntilUtc is null)
        {
            G4OracleMaintenanceProof.Check(recovered.Length == 1 && recovered[0].GetProperty("actor").GetString() == proof["operatorId"]
                && recovered[0].GetProperty("trace").GetString() == proof["operationId"] && recovered[0].GetProperty("correlation").GetString() == proof["attemptId"]
                && recovered[0].GetProperty("outcome").GetString() == "allowed" && recovered[0].GetProperty("organization").GetString() == row.OrganizationId
                && recovered[0].GetProperty("sites").Deserialize<string[]>()!.SequenceEqual(state.Scope.SiteIds));
            await transaction.CommitAsync(token);
            return "ALREADY_RECOVERED";
        }
        G4OracleMaintenanceProof.Check(recovered.Length == 0 && row.LeaseOwner == G4OracleMaintenanceProof.Owner
            && row.LeaseUntilUtc == proof.Utc("leaseUntilUtc") && row.CompletedAtUtc <= DateTimeOffset.UtcNow
            && row.LeaseUntilUtc <= DateTimeOffset.UtcNow && row.DeadlineAtUtc <= DateTimeOffset.UtcNow);
        // CAS 的更新集合只有两列；其余稳定字节均已在行锁内重核。
        var count = await db.Queries.Where(q => q.Id == row.Id && q.LeaseOwner == row.LeaseOwner && q.LeaseUntilUtc == row.LeaseUntilUtc
            && q.Fence == 2 && q.ExecutionStatus == "CANCELLED" && q.CancelRequested).ExecuteUpdateAsync(update =>
                update.SetProperty(q => q.LeaseOwner, (string?)null).SetProperty(q => q.LeaseUntilUtc, (DateTimeOffset?)null), token);
        G4OracleMaintenanceProof.Check(count == 1);
        // 受信身份来自维护进程的实际 OS 操作者；绝不借用原业务主体。
        var actor = new ActorContext { SubjectId = proof["operatorId"], OrganizationId = row.OrganizationId, SiteIds = state.Scope.SiteIds,
            Roles = [], TraceId = proof["operationId"], CorrelationId = proof["attemptId"] };
        await audit.WriteAsync(actor, new AuditCommand { Action = "data.query.cleanup.recover", Resource = row.Id, Outcome = "allowed", Scope = state.Scope },
            db.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
        proof.DemandFresh(DateTimeOffset.UtcNow);
        await transaction.CommitAsync(token);
        return "TASK_LEVEL_RECOVERY";
    }
}
