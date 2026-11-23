using System.Data.Common;
using System.Globalization;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>一次性维护进程验证过的私有输入，不是产品请求，也不能通过 HTTP 或 MCP 构造。</summary>
internal sealed class G4OracleAccessMaintenanceProof
{
    /// <summary>保留准确输入字节解析得到的只读证据对象。</summary>
    private readonly JsonElement proof;

    /// <summary>保留唯一被授权的准确后继，不从数据库刷新目标身份。</summary>
    internal const string QueryId = "query-4b9f97e1bbdd45f7a39111c907447f65";

    /// <summary>准确资源代次终止证明只允许本条失败查询。</summary>
    internal const string GenerationQueryId = "query-d368ac610c7745889890e1589653af8f";

    /// <summary>普通正式关系查询仅允许本代已冻结的一条失败行。</summary>
    internal const string NormalQueryId = "query-f1599097a7274c20b82cbf0dfcea4e2b";

    /// <summary>本次有界元数据诊断前唯一允许清租约的历史行。</summary>
    internal const string MetadataQueryId = "query-5d891e89221e4a3f8f6893873b1d7a9d";

    /// <summary>核对行锁内读取的 owner，专用代次模式仅暴露原 owner 的摘要。</summary>
    internal bool MatchesOwner(string? owner) => owner is not null && (this["queryId"] is GenerationQueryId or NormalQueryId or MetadataQueryId
        ? G4QueryCanonical.Hash(System.Text.Encoding.UTF8.GetBytes(owner)) == this["ownerSha256"]
        : owner == Owner);

    /// <summary>正式 Binding 引用的目标连接。</summary>
    internal const string ConnectionId = "a7913bb552eb4cd1a3f6eaf5b93cd619";

    /// <summary>未获产品时限内物理确认的原 owner。</summary>
    internal const string Owner = "oracle-execution-8db5f162e634422abf8b94caf509d2c9";

    /// <summary>实际源数据库服务的完整引擎身份。</summary>
    internal const string SourceContainer = "65bdf442f5679f2f80c2a14f3a1e635f0333a0343679f4123809b314959b77e1";

    /// <summary>实际任务平台库的完整引擎身份。</summary>
    internal const string PlatformContainer = "79b5f2d2af1911ff87d54a3466623f06448c770d52a57c217783cbd643a4b545";

    /// <summary>只由验证准确原字节、独立观察与封闭回执后的入口产生。</summary>
    private G4OracleAccessMaintenanceProof(JsonElement proof) => this.proof = proof;

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
    internal static G4OracleAccessMaintenanceProof Read(byte[] bytes, string expectedSha, string operatorId, string sealSha,
        string terminationSha, bool isolated = false) =>
        ReadBound(bytes, expectedSha, operatorId, sealSha, terminationSha, isolated, "SOURCE_EXECUTION");

    /// <summary>仅由核实原件的维护进程选择专用实例整体终止模式，无逐执行标识。</summary>
    internal static G4OracleAccessMaintenanceProof ReadGeneration(byte[] bytes, string expectedSha, string operatorId, string sealSha,
        string terminationSha, bool isolated = false) =>
        ReadBound(bytes, expectedSha, operatorId, sealSha, terminationSha, isolated, "DEDICATED_GENERATION");

    /// <summary>普通关系查询的专用实例证明需要无子进程的真实父和准确终态。</summary>
    internal static G4OracleAccessMaintenanceProof ReadNormal(byte[] bytes, string expectedSha, string operatorId, string sealSha,
        string terminationSha) => ReadBound(bytes, expectedSha, operatorId, sealSha, terminationSha, false, "NORMAL_GENERATION");

    /// <summary>以进程选择的封闭判别值校验两种证明各自的准确字段与物理身份。</summary>
    private static G4OracleAccessMaintenanceProof ReadBound(byte[] bytes, string expectedSha, string operatorId, string sealSha,
        string terminationSha, bool isolated, string mode)
    {
        // 只有专用模式接受原件锚定的整代关闭及生产者封闭。
        var generation = mode is "DEDICATED_GENERATION" or "NORMAL_GENERATION";
        Check(bytes.Length is > 0 and <= 65536 && G4QueryCanonical.Hash(bytes) == expectedSha);
        using var document = JsonDocument.Parse(bytes);
        // 所有字段必须唯一且准确；输入声明不能替代私有进程环境传入的独立证据摘要。
        var fields = "taskId runId attemptId operationId operatorId systemIdentifier database databaseUser organizationId queryId connectionId owner originalFence terminalFence sourceExecutionId parentCommandId platformContainerId sourceContainerId createdUtc deadlineUtc completedUtc leaseUntilUtc requestSha256 bindingSha256 stableRowSha256 failureAuditId failureAuditSha256 sealSha256 terminationProofSha256 verifiedUtc validUntilUtc".Split(' ');
        if (generation)
        {
            fields = fields.Except(["sourceExecutionId", "owner"]).Concat(["proofKind", "ownerSha256", "childCommandId",
                "closeSha256", "sourceStartedAt", "sourceFinishedAt"]).ToArray();
        }
        // 按键数和集合双检，避免重复 JSON 属性掩盖错误身份。
        var names = document.RootElement.EnumerateObject().Select(p => p.Name).ToArray();
        Check(names.Length == fields.Length && fields.ToHashSet(StringComparer.Ordinal).SetEquals(names));
        // 对象独立于临时 JsonDocument 的生命周期。
        var value = new G4OracleAccessMaintenanceProof(document.RootElement.Clone());
        Check(value["taskId"] == "G4-ORACLE-MAPPING-QUERY-001" && value["runId"] == "product-resume-01"
            && value["organizationId"] == "org-demo" && value["connectionId"] == ConnectionId
            && value["platformContainerId"] == PlatformContainer && value["sourceContainerId"] == SourceContainer);
        if (mode == "NORMAL_GENERATION" && value["queryId"] == MetadataQueryId)
        {
            Check(value["queryId"] == MetadataQueryId && value["proofKind"] == mode
                && value["parentCommandId"] == "e1c70fc2faf344f39c98ac6731a061aa"
                && value.proof.GetProperty("childCommandId").ValueKind == JsonValueKind.Null
                && value["sourceStartedAt"] == "2026-11-22T15:03:56.505162467Z"
                && value["sourceFinishedAt"] == "2026-11-22T15:06:22.192480006Z"
                && value["closeSha256"] == "64bdc66845958810935eb00e9b633108b6c5dc7ebf56ea19d030c396a5db5040");
        }
        else if (mode == "NORMAL_GENERATION")
        {
            Check(value["queryId"] == NormalQueryId && value["proofKind"] == mode
                && value["parentCommandId"] == "4032c1d770b240989966ba3275d86999"
                && value.proof.GetProperty("childCommandId").ValueKind == JsonValueKind.Null
                && value["sourceStartedAt"] == "2026-11-22T12:48:17.47353763Z"
                && value["sourceFinishedAt"] == "2026-11-22T12:51:07.888426792Z"
                && value["closeSha256"] == "a3839fe8ebb6e418e42e2280d1d6044acd7a1a4f3f65babdc8f13b8c7d055348");
        }
        else if (generation)
        {
            Check(value["queryId"] == GenerationQueryId && value["proofKind"] == mode
                && value["parentCommandId"] == "c02e89f8d8f2481f90058606ccf71b29" && value["childCommandId"] == "5b90bb8f66fb4ddd9bfeddbe5015133a"
                && value["sourceStartedAt"] == "2026-11-21T13:49:57.33078955Z" && value["sourceFinishedAt"] == "2026-11-21T13:52:47.119332336Z"
                && value["closeSha256"] == "21d6d0cff882452f4e810c28e59e82418fbb31a30ea9c40d74849f29dc48776e"
                && Regex.IsMatch(value["ownerSha256"], @"\A[0-9a-f]{64}\z"));
        }
        else
        {
            Check(value["queryId"] == QueryId && value["owner"] == Owner && value["sourceExecutionId"] == "b4b07ea50d304927975cd5d052ff58e4"
                && value["parentCommandId"] == "04f23ea8cfe34868a8500b80164d86fb");
        }
        foreach (var (key, number) in new[] { ("originalFence", 1), ("terminalFence", 2) })
            Check(value.proof.GetProperty(key).GetInt32() == number);
        foreach (var key in new[] { "requestSha256", "bindingSha256", "stableRowSha256", "failureAuditSha256", "sealSha256", "terminationProofSha256" })
            Check(Regex.IsMatch(value[key], @"\A[0-9a-f]{64}\z"));
        foreach (var key in new[] { "attemptId", "operationId", "failureAuditId" })
            Check(Regex.IsMatch(value[key], @"\A[0-9a-f]{32}\z"));
        Check(value["operatorId"] == operatorId && Regex.IsMatch(operatorId, @"\Aos-uid-[0-9]{1,10}\z")
            && sealSha == value["sealSha256"] && terminationSha == value["terminationProofSha256"] && sealSha != terminationSha
            && Regex.IsMatch(value["systemIdentifier"], @"\A[0-9]{1,20}\z")
            && Regex.IsMatch(value["databaseUser"], @"\A[a-z_][a-z0-9_]{0,62}\z") && (isolated
                ? Regex.IsMatch(value["database"], @"\Aomq_query_test_[a-z0-9_]+\z") : value["database"] == "mapping"));
        if (mode == "NORMAL_GENERATION" && value["queryId"] == MetadataQueryId)
        {
            Check(value["systemIdentifier"] == "7709907053089669168" && value["databaseUser"] == "postgres" && operatorId == "os-uid-501"
                && sealSha == "2120d6d36a993bdc5234e8febce44d42d83d3315fd0ad405f6bbfc3e9ef2588b"
                && terminationSha == "3004a217e2551b91d104092fd3faad8cc8d8fa56ee4eac0119e5f37d7327a858"
                && value["ownerSha256"] == "f155210a2019304736db8f52cc879be44f88045bd28ddcbae06878159f09e08b"
                && value["requestSha256"] == "e65bb0daa424428e3b4f54f5931973ec7a34edc7b5a11230365cab8524503fbd"
                && value["bindingSha256"] == "8c5267a7cf1e34090f41b876fcdcf176898669dd4e240cf85082916ce88973dc"
                && value["stableRowSha256"] == "aa8ed5eaf5a90a5073d404707a023b560fa6a2298144c90e1c18613a55bc2a03"
                && value["failureAuditId"] == "3e1ca8e4e1af42efa3ac8d0007c8debf"
                && value["failureAuditSha256"] == "8625e5892d8c7360efd0a5eaaaf5da78e808c6fb859c4f15c529b36244c88de3"
                && value["leaseUntilUtc"] == "2026-11-22T15:05:57.808477+00:00"
                && value["deadlineUtc"] == value["leaseUntilUtc"] && value["createdUtc"] == "2026-11-22T15:05:53.724627+00:00"
                && value["completedUtc"] == "2026-11-22T15:05:54.520735+00:00");
        }
        else if (mode == "NORMAL_GENERATION")
        {
            Check(value["systemIdentifier"] == "7709907053089669168" && value["databaseUser"] == "postgres" && operatorId == "os-uid-501"
                && sealSha == "34fd7fda857fc5ca2f2456ad5cb76885b8473fafe00b588366d187286e0fd9c5"
                && terminationSha == "d3bd83e5b832d68295dd3abeeb84a558bf290b51ce882b5df7a9995c4aefce6b"
                && value["ownerSha256"] == "08d6b6d8633b72b6ad4a980128d3e6a1b68c83b5c388cecd3a3296d84accf4cb"
                && value["requestSha256"] == "e65bb0daa424428e3b4f54f5931973ec7a34edc7b5a11230365cab8524503fbd"
                && value["bindingSha256"] == "8c5267a7cf1e34090f41b876fcdcf176898669dd4e240cf85082916ce88973dc"
                && value["stableRowSha256"] == "8bbdb6cb314c00994015ef3eef5c36c5f9ec60d41f005875256129f2b7d91a57"
                && value["failureAuditId"] == "38ebcc6e08504994b36a322edc4ffd86"
                && value["failureAuditSha256"] == "91713b546c40b9d6925079220bfa0420e6bbfc3d8dbd18c1a9c335cc2e0d422c"
                && value["leaseUntilUtc"] == "2026-11-22T12:50:41.308879+00:00"
                && value["deadlineUtc"] == value["leaseUntilUtc"] && value["createdUtc"] == "2026-11-22T12:50:37.198569+00:00"
                && value["completedUtc"] == "2026-11-22T12:50:37.974659+00:00");
        }
        else if (!isolated && generation)
        {
            Check(value["systemIdentifier"] == "7709907053089669168" && value["databaseUser"] == "postgres" && operatorId == "os-uid-501"
                && sealSha == "1d39291bc79d057dc310bdad98049442305aff73b236e4a004b4829d3890edb2"
                && terminationSha == "a617d1e838631e9f16b5e9bc65aa97842c3a85cfc7c9991137262a537881c3d0"
                && value["ownerSha256"] == "8fdc75f71c16c2972b1ab468d7a7ee79726888b2b45adc5970255183e569f013"
                && value["requestSha256"] == "e65bb0daa424428e3b4f54f5931973ec7a34edc7b5a11230365cab8524503fbd"
                && value["bindingSha256"] == "f9791b46957e72f0240a2bb8861d7cf7d58856136905e151c0c7c6be377b4a0a"
                && value["stableRowSha256"] == "c7e08ef5d06001addd262eb403a8d86cca760efffc172f675d5c4ff9956e3bf6"
                && value["failureAuditId"] == "83330a307d7a4583aa44e7c2a6db4fa4"
                && value["failureAuditSha256"] == "ccad5f400813da2d9e641b2a2ba59af8dba87b41a5320e5bd095e40ee975d3c4"
                && value["leaseUntilUtc"] == "2026-11-21T13:52:21.635112+00:00"
                && value["deadlineUtc"] == value["leaseUntilUtc"] && value["createdUtc"] == "2026-11-21T13:52:17.360623+00:00"
                && value["completedUtc"] == "2026-11-21T13:52:21.897952+00:00");
        }
        else if (!isolated)
        {
            // 首次真实只读快照冻结的物理集群及不可变原件。后续独立观察只能更新其新鲜证明。
            Check(value["systemIdentifier"] == "7709907053089669168" && value["databaseUser"] == "postgres" && operatorId == "os-uid-501"
                && value["requestSha256"] == "e04b175fec4de4f9f6437e3841c14fd312f304dfa6849b3c6d98a2a491655a1c"
                && value["bindingSha256"] == "3365a0ef157ed7b265d94f2ff0fd648bbfc3d79c64c8d875d144af7ef00ef5fd"
                && value["stableRowSha256"] == "25e9289fe30b97d2e03ed49723134713966a9949faf53fdc1c199af74ac56f5a"
                && value["failureAuditSha256"] == "5dda9b7f61a129ea975162da32706ae41433efad261039e09804ee8fe00c6c3f"
                && value["failureAuditId"] == "eb5cfd622f3049238006b828e1a4ff52");
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
    private static InvalidOperationException Invalid() => new("oracle_access_maintenance_precondition_failed");
}

/// <summary>仅处理本次源ACL失败的唯一准确行的任务级恢复，与原产品清理 CAS 分离。</summary>
internal static class G4OracleAccessMaintenance
{
    /// <summary>在持锁同一事务中复核治理事实、准确行与原始字节，再更新两列并记录一次维护审计。</summary>
    internal static async Task<string> RecoverAsync(G4QueryDbContext db, ITransactionalAuditWriter audit,
        G4OracleAccessMaintenanceProof proof, Func<DbConnection, DbTransaction, CancellationToken, Task<JsonElement>> auditFacts,
        CancellationToken token)
    {
        // UTC 显式固定 PG 的原始 jsonb 文本摘要，即使数据库缺省时区以后发生变化。
        await using var transaction = await db.Database.BeginTransactionAsync(token);
        await db.Database.ExecuteSqlRawAsync("SET LOCAL TIME ZONE 'UTC'", token);
        await G4QueryResultStore.LockCapacityAsync(db, token);
        // 准确行锁沿产品既有顺序在容量锁之后取得。
        var row = await G4QueryResultStore.LockedAsync(db, proof["queryId"], token);
        // 证明绑定物理 PostgreSQL 集群、数据库、当前用户和其余全部查询字段。
        var databaseFacts = await db.Database.SqlQuery<string>($"""
            SELECT json_build_array((pg_control_system()).system_identifier::text, current_database(), current_user,
                encode(sha256(convert_to((to_jsonb(q)-'LeaseOwner'-'LeaseUntilUtc')::text,'UTF8')),'hex'))::text AS "Value"
            FROM semantic_query."Queries" q WHERE q."Id" = {row.Id}
            """).SingleAsync(token);
        // JSON 只含平台身份与摘要。
        var values = JsonSerializer.Deserialize<string[]>(databaseFacts)!;
        G4OracleAccessMaintenanceProof.Check(values.SequenceEqual(new[] { proof["systemIdentifier"], proof["database"], proof["databaseUser"], proof["stableRowSha256"] }));
        // 现行语义合同必须能重新打开原请求与稳定的 binding，不能仅凭投影列更新。
        var state = G4QueryResultStore.ReadState(row);
        _ = G4QueryResultStore.ReadRequest(row);
        G4OracleAccessMaintenanceProof.Check(row.OrganizationId == proof["organizationId"] && row.ConnectionId == proof["connectionId"]
            && state.Binding.ConnectionId == row.ConnectionId && state.Scope.OrganizationId == row.OrganizationId
            && state.Scope.SiteIds.SequenceEqual(["site-a"]) && state.Receipts.Length == 0 && row.ExecutionStatus == "FAILED"
            && !row.CancelRequested && row.Fence == 2 && row.ResultHash is null && row.ResultSize == 0 && row.ResultCiphertext.Length == 0
            && row.CreatedAtUtc == proof.Utc("createdUtc") && row.DeadlineAtUtc == proof.Utc("deadlineUtc")
            && row.CompletedAtUtc == proof.Utc("completedUtc") && row.RequestHash == proof["requestSha256"]
            && G4QueryCanonical.Hash(row.RequestBytes) == row.RequestHash && G4QueryCanonical.Hash(row.BindingBytes) == proof["bindingSha256"]);
        // 治理模块通过调用者同一物理事务提供准确失败行的全部审计投影。
        var facts = await auditFacts(db.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
        // 原失败审计必须保持唯一且与私有原快照逐字节关联。
        G4OracleAccessMaintenanceProof.Check(facts.EnumerateArray().All(a => a.GetProperty("action").GetString() is "data.query.execute" or "data.query.cleanup.recover"));
        var failures = facts.EnumerateArray().Where(a => a.GetProperty("action").GetString() == "data.query.execute").ToArray();
        G4OracleAccessMaintenanceProof.Check(failures.Length == 1 && failures[0].GetProperty("outcome").GetString() == "failure"
            && failures[0].GetProperty("id").GetString() == proof["failureAuditId"] && failures[0].GetProperty("sha256").GetString() == proof["failureAuditSha256"]
            && !facts.EnumerateArray().Any(a => a.GetProperty("action").GetString() == "data.query.execute" && a.GetProperty("outcome").GetString() == "allowed"));
        // 只认可同一实际维护身份、操作和尝试，未知清空不能按幂等成功返回。
        var recovered = facts.EnumerateArray().Where(a => a.GetProperty("action").GetString() == "data.query.cleanup.recover").ToArray();
        proof.DemandFresh(DateTimeOffset.UtcNow);
        if (row.LeaseOwner is null && row.LeaseUntilUtc is null)
        {
            G4OracleAccessMaintenanceProof.Check(recovered.Length == 1 && recovered[0].GetProperty("actor").GetString() == proof["operatorId"]
                && recovered[0].GetProperty("trace").GetString() == proof["operationId"] && recovered[0].GetProperty("correlation").GetString() == proof["attemptId"]
                && recovered[0].GetProperty("outcome").GetString() == "allowed" && recovered[0].GetProperty("organization").GetString() == row.OrganizationId
                && recovered[0].GetProperty("sites").Deserialize<string[]>()!.SequenceEqual(state.Scope.SiteIds));
            await transaction.CommitAsync(token);
            return "ALREADY_RECOVERED";
        }
        G4OracleAccessMaintenanceProof.Check(recovered.Length == 0 && proof.MatchesOwner(row.LeaseOwner)
            && row.LeaseUntilUtc == proof.Utc("leaseUntilUtc") && row.CompletedAtUtc <= DateTimeOffset.UtcNow
            && row.LeaseUntilUtc <= DateTimeOffset.UtcNow && row.DeadlineAtUtc <= DateTimeOffset.UtcNow);
        // CAS 的更新集合只有两列；其余稳定字节均已在行锁内重核。
        var count = await db.Queries.Where(q => q.Id == row.Id && q.LeaseOwner == row.LeaseOwner && q.LeaseUntilUtc == row.LeaseUntilUtc
            && q.Fence == 2 && q.ExecutionStatus == "FAILED" && !q.CancelRequested).ExecuteUpdateAsync(update =>
                update.SetProperty(q => q.LeaseOwner, (string?)null).SetProperty(q => q.LeaseUntilUtc, (DateTimeOffset?)null), token);
        G4OracleAccessMaintenanceProof.Check(count == 1);
        // 受信身份来自维护进程的实际 OS 操作者；绝不借用原业务主体。
        var actor = new ActorContext
        {
            SubjectId = proof["operatorId"],
            OrganizationId = row.OrganizationId,
            SiteIds = state.Scope.SiteIds,
            Roles = [],
            TraceId = proof["operationId"],
            CorrelationId = proof["attemptId"]
        };
        await audit.WriteAsync(actor, new AuditCommand { Action = "data.query.cleanup.recover", Resource = row.Id, Outcome = "allowed", Scope = state.Scope },
            db.Database.GetDbConnection(), transaction.GetDbTransaction(), token);
        proof.DemandFresh(DateTimeOffset.UtcNow);
        await transaction.CommitAsync(token);
        return "TASK_LEVEL_RECOVERY";
    }
}
