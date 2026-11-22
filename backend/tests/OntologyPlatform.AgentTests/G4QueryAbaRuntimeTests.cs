using System.Data.Common;
using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.SemanticQuery;

namespace OntologyPlatform.AgentTests;

/// <summary>AC-05真实在途ABA验收，保持正式五秒截止和所有安全参与者。</summary>
public sealed partial class G4QueryMafRuntimeTests
{
    /// <summary>历史 PG 与 Doris 夹具的提案审核身份，只供其既有场景使用。</summary>
    private static async Task<(ActorContext Actor, string Session)> HistoricalMappingReviewerAsync(IServiceProvider services, string proposalId)
    {
        // 精确提案的原证明属于历史夹具，在调用者分支隔离后才读取。
        await using var connections = await services.GetRequiredService<IDbContextFactory<ConnectionsDbContext>>().CreateDbContextAsync();
        // 只投影该提案的证明，避免加载其他提案数据。
        var json = await connections.MappingProposals.AsNoTracking().Where(item => item.Id == proposalId)
            .Select(item => item.DecisionProofJson).SingleAsync();
        // 原正式审核证明只在进程内传递。
        var proof = JsonSerializer.Deserialize<MappingAuthorizationProof>(json!, G4MappingJson.Options)!;
        return (proof.Actor, proof.SessionReference);
    }

    /// <summary>真实源读取后经正式批准和激活执行A到B再到A，核验提交失败和审计原子性。</summary>
    private static async Task MappingAbaAfterRealReadAsync(IServiceProvider services, ActorContext actor,
        G4QueryRecord original, G4QueryDbContext database, string proposalId,
        (ActorContext Actor, string Session)? editing = null, (ActorContext Actor, string Session)? activating = null, string? reviewerId = null,
        (ActorContext Actor, string Session)? currentReviewer = null, object? seedReceipt = null, OracleRuntimeSourceEvents? sourceEvents = null)
    {
        // 当前夹具的编辑者负责草稿、评估与提案；历史 PG 夹具沿用它的原始参与者。
        var editor = editing ?? (actor, original.SessionReference);
        // 仅激活者执行两次正式激活，权限仍由各正式应用服务检查。
        var activator = activating ?? (actor, original.SessionReference);
        // 所有映射变更均进入HTTP端点使用的正式应用服务。
        var mappings = services.GetRequiredService<MappingApplicationService>();
        // 激活仍执行真实七阶段复核、当前授权、CAS和事务审计。
        var activations = services.GetRequiredService<MappingActivationService>();
        // 查询前已批准B，避免把审批等待计入不可延长的查询五秒预算。
        var approvedB = await mappings.ReadProposalAsync(editor.Actor, editor.Session, proposalId, CancellationToken.None);
        Assert.AreEqual("APPROVED", approvedB.Status);
        // Oracle 只接受本轮正式验证的审核会话；旧源继续沿自身夹具合同取参与者。
        var oracle = Environment.GetEnvironmentVariable("G4_QUERY_RUNTIME_TEST") == "G4-ORACLE-MAPPING-QUERY-001:product-resume-01";
        Assert.IsTrue(!oracle || currentReviewer.HasValue, "Oracle 回滚必须提供当前验证的审核者。");
        // 原 B 提案仍须由约定的异人审核，当前回滚另行取得其正式决定。
        if (reviewerId is not null) Assert.AreEqual(reviewerId, approvedB.Decision?.DecidedBy);
        // 准确审核参与者只在当前操作进程中使用。
        var auditor = currentReviewer ?? await HistoricalMappingReviewerAsync(services, proposalId);
        Assert.AreNotEqual(actor.SubjectId, auditor.Actor.SubjectId);
        if (reviewerId is not null) Assert.AreEqual(reviewerId, auditor.Actor.SubjectId);
        // 当前草稿仅用于正式回滚调度CAS，不替换历史A的定义。
        var draft = await mappings.ReadDraftAsync(editor.Actor, editor.Session, approvedB.MappingId, null, CancellationToken.None);
        // 新命令始终产生新的准入记录，不复用历史结果。
        var key = Guid.NewGuid().ToString();
        // 原查询能力和筛选来自已完成真实查询。
        using var request = JsonDocument.Parse(original.RequestBytes);
        // 正式固定查询合同没有自造版本或身份字段。
        var query = request.RootElement.GetProperty("query").Deserialize<G4SemanticQuery>(G4QueryJson.Options)!;
        // 仅接受已批准驱动的精确任务和Run，原件不得沿用其它任务标签。
        var runtimeIdentity = Environment.GetEnvironmentVariable("G4_QUERY_RUNTIME_TEST");
        Assert.IsTrue(runtimeIdentity is "G4-M4-QUERY-001:query-impl-01" or "G4-M5-INTEGRATION-001:integration-01" or "G4-DORIS-MAPPING-QUERY-001:implementation-01" or "G4-ORACLE-MAPPING-QUERY-001:product-resume-01");
        // 公开记录仅包括合成标识、时间、计数及状态，绝不包含会话证明。
        var evidence = new Dictionary<string, object?> { ["taskId"] = runtimeIdentity!.Split(':')[0], ["case"] = "AC-05_INFLIGHT_ABA", ["status"] = "FAIL", ["resourceRun"] = runtimeIdentity!.Split(':')[1] };
        if (oracle) evidence["runtimeSeed"] = seedReceipt;
        // 完整两次激活完成后才能把409归因于查询提交。
        var abaCompleted = false;
        // 真实墙钟预算从正式Gateway调用之前开始。
        var elapsed = new Stopwatch();
        sourceEvents?.Bind(elapsed);
        // 事件序列由唯一查询进程产生，UTC关联数据库，单调时钟证明原五秒内顺序。
        var events = new List<object>();
        // 分段与固定合格事件使用同一单调表，仅在响应后的 finally 序列化。
        var phases = new List<Dictionary<string, object?>>(32);
        // 映射命令只登记本回调实际创建的公开 ID，供响应后按精确行回读。
        var commands = new List<string>(5);
        // 有界内存达到容量时显式报告丢失，不能据此声称观测完整。
        var dropped = 0;
        // 使用操作自身的命令，不额外发送请求。
        CommandContext ActualCommand(long revision)
        {
            // 每次正式操作生成且消费一次的同一对象。
            var command = Command(revision);
            if (oracle)
            {
                commands.Add(command.CommandId);
                if (phases.Count > 0 && dropped == 0) phases[^1]["commandId"] = command.CommandId;
            }
            return command;
        }
        // 只记录公开资源 ID 与异常代码，保留真实异常继续传播。
        void Point(string phase, string edge, CancellationToken token, string? resourceId, Exception? error = null)
        {
            if (!oracle) return;
            if (phases.Count >= 128) { dropped++; return; }
            phases.Add(new Dictionary<string, object?>
            {
                ["phase"] = phase, ["edge"] = edge, ["utc"] = DateTimeOffset.UtcNow,
                ["monotonicMs"] = elapsed.Elapsed.TotalMilliseconds, ["cancelled"] = token.IsCancellationRequested,
                ["resourceId"] = resourceId, ["errorCode"] = error is SemanticOperationException semantic
                    ? semantic.Code : error is OperationCanceledException ? "cancelled" : error is null ? null : "operation_error"
            });
        }
        // 在原调用两侧以同一 token 取样；工作者持有的活动标识只来自真实领取提交。
        async Task<T> Observe<T>(string phase, string? inputId, CancellationToken token, Func<Task<T>> call, Func<T, string?> outputId)
        {
            if (!oracle) return await call();
            Point(phase, "ENTER", token, inputId);
            // 实际领取标记只归属于本次 RunNext 调用。
            using var claim = phase == "WORKER_RUN" ? new Activity("mapping.worker.run").Start() : null;
            try
            {
                // 返回值保持原类型；诊断只投影其中的公开 ID。
                var reply = await call();
                Point(phase, "RETURN", token, claim is null ? outputId(reply) : claim.GetTagItem("mapping.worker.claimed_job_id") as string);
                return reply;
            }
            catch (Exception error)
            {
                Point(phase, "ERROR", token, claim is null ? inputId : claim.GetTagItem("mapping.worker.claimed_job_id") as string, error);
                throw;
            }
        }
        // 捕获后每个阶段都绑定同一query和mapping，不借其他请求的成功回执。
        void RecordEvent(string phase)
        {
            events.Add(new
            {
                phase,
                sequence = events.Count + 1,
                monotonicMs = elapsed.Elapsed.TotalMilliseconds,
                utc = DateTimeOffset.UtcNow,
                queryId = evidence.GetValueOrDefault("queryId"),
                mappingId = evidence.GetValueOrDefault("mappingId"),
                connectionId = evidence.GetValueOrDefault("connectionId")
            });
        }
        // 唯一注入点在真实源读取之后，不替换版本读取器、结果存储或审计参与者。
        async Task SwitchCore(CancellationToken token)
        {
            // 精确命令已准入且尚未提交，防止入口拒绝冒充在途保护。
            var running = await database.Queries.AsNoTracking().SingleAsync(item => item.IdempotencyKey == key, token);
            Assert.AreEqual("RUNNING", running.ExecutionStatus);
            Assert.IsTrue((running.DeadlineAtUtc - running.CreatedAtUtc).TotalMilliseconds <= 5000);
            // 固定A取自实际准入原件，后续不以当前Active替换它。
            var captured = G4QueryResultStore.ReadState(running).Binding;
            evidence["queryId"] = running.Id;
            evidence["mappingId"] = captured.MappingId;
            evidence["connectionId"] = captured.ConnectionId;
            evidence["subjectId"] = running.SubjectId;
            evidence["leaseOwnerHash"] = G4QueryCanonical.Hash(System.Text.Encoding.UTF8.GetBytes(running.LeaseOwner!));
            evidence["fence"] = running.Fence;
            Assert.AreEqual(original.ConnectionId, captured.ConnectionId);
            Assert.AreEqual(actor.SubjectId, running.SubjectId);
            Assert.IsFalse(string.IsNullOrWhiteSpace(running.LeaseOwner));
            Assert.IsTrue(running.Fence > 0);
            evidence["capturedA"] = new { captured.MappingId, captured.MappingReleaseId, captured.ActivationId, captured.ActivationRevision, captured.ConnectionId };
            evidence["admittedAtUtc"] = running.CreatedAtUtc;
            evidence["deadlineAtUtc"] = running.DeadlineAtUtc;
            evidence["afterRealReadAtUtc"] = DateTimeOffset.UtcNow;
            RecordEvent("SOURCE_READ_COMPLETED");
            // B提交使用当前operator及先前真实异人批准的提案。
            var b = await Observe("B_ACTIVATE", proposalId, token, () => activations.ActivateAsync(activator.Actor, activator.Session, proposalId,
                new MappingActivationRequest { BindingHash = approvedB.BindingHash, ExpectedActive = approvedB.ExpectedActive,
                    Command = ActualCommand(approvedB.ProposalRevision) }, $"\"proposal:{approvedB.ProposalRevision}\"", token), receipt => receipt.ActivationId);
            evidence["activatedB"] = b;
            RecordEvent("B_ACTIVATED");
            Assert.AreNotEqual(captured.MappingReleaseId, b.MappingReleaseId);
            Assert.IsTrue(b.ActivationRevision > long.Parse(captured.ActivationRevision, CultureInfo.InvariantCulture));
            // 回滚目标是原查询捕获的真实历史A原字节散列。
            var target = new MappingRollbackTarget { TargetReleaseId = captured.MappingReleaseId, ManifestHash = captured.ManifestHash };
            // 正式入队并由实际消费者运行，不写伪造assessment或activation行。
            var job = await Observe("ROLLBACK_VALIDATE_ENQUEUE", captured.MappingId, token, () => mappings.ValidateAsync(editor.Actor, editor.Session, captured.MappingId,
                new MappingValidateRequest { Target = target, Command = ActualCommand(draft.Revision) }, $"\"mapping:{draft.Revision}\"", token), receipt => receipt.JobId);
            // 显式调用已注册真实worker省掉后台轮询等待，不启动宿主其他服务。
            var worker = services.GetServices<IHostedService>().OfType<MappingJobWorker>().Single();
            while (job.Status is "QUEUED" or "RUNNING")
            {
                await Observe("WORKER_RUN", job.JobId, token, () => worker.RunNextAsync(token), _ => null);
                job = await Observe("ROLLBACK_JOB_READ", job.JobId, token, () => mappings.ReadJobAsync(editor.Actor, editor.Session, job.JobId, token), receipt => receipt.AssessmentId);
                if (job.Status is "QUEUED" or "RUNNING") await Task.Delay(10, token);
            }
            Assert.AreEqual("SUCCEEDED", job.Status);
            if (oracle) evidence["rollbackValidatedAtUtc"] = DateTimeOffset.UtcNow;
            // 七阶段结果由真实源、语义和当前授权验证产生。
            var assessment = await Observe("ROLLBACK_ASSESSMENT_READ", job.AssessmentId, token,
                () => mappings.ReadAssessmentAsync(editor.Actor, editor.Session, job.AssessmentId!, token), receipt => receipt.AssessmentId);
            Assert.AreEqual("READY_FOR_PROPOSAL", assessment.Status);
            Assert.AreEqual(7, assessment.Stages.Length);
            Assert.IsTrue(assessment.Stages.All(stage => stage.Status == "PASS"));
            // 回滚提案绑定B当前激活基线，不预造不可成立的CAS。
            var proposedA = await Observe("ROLLBACK_PROPOSE", assessment.AssessmentId, token, () => mappings.ProposeAsync(editor.Actor, editor.Session, captured.MappingId,
                new MappingRollbackProposalRequest { SchemaVersion = "g4.mapping.v1", Scope = draft.Scope, Binding = assessment.Binding,
                    ExpectedActive = assessment.ExpectedActive, ExpiresAtUtc = assessment.ExpiresAtUtc, Command = ActualCommand(0),
                    TargetReleaseId = target.TargetReleaseId, ManifestHash = target.ManifestHash }, token), receipt => receipt.ProposalId);
            // 使用已获正式服务器验证的不同审核主体，当前授权仍由正式服务重核。
            var approvedA = await Observe("ROLLBACK_DECIDE", proposedA.ProposalId, token, () => mappings.DecideAsync(auditor.Actor, auditor.Session, proposedA.ProposalId,
                new MappingDecisionRequest { Decision = "APPROVE", BindingHash = proposedA.BindingHash, Command = ActualCommand(proposedA.ProposalRevision) },
                $"\"proposal:{proposedA.ProposalRevision}\"", token), receipt => receipt.ProposalId);
            if (oracle)
            {
                Assert.AreEqual(proposedA.ProposalId, approvedA.ProposalId);
                Assert.AreEqual("APPROVED", approvedA.Status);
                Assert.IsNotNull(approvedA.Decision);
                Assert.AreEqual(auditor.Actor.SubjectId, approvedA.Decision.DecidedBy);
                Assert.AreEqual(proposedA.BindingHash, approvedA.Decision.BindingHash);
                evidence["rollbackDecision"] = new { path = "MappingApplicationService.DecideAsync", proposedA.ProposalId,
                    proposedA.BindingHash, proposedA.SubmittedBy, approvedA.Decision.DecidedBy,
                    sessionHash = G4QueryCanonical.Hash(System.Text.Encoding.UTF8.GetBytes(auditor.Session)) };
            }
            // 第二次真实激活回到同一release，但生成新的activation身份和单调修订。
            var a = await Observe("A_ACTIVATE", approvedA.ProposalId, token, () => activations.ActivateAsync(activator.Actor, activator.Session, approvedA.ProposalId,
                new MappingActivationRequest { BindingHash = approvedA.BindingHash, ExpectedActive = approvedA.ExpectedActive,
                    Command = ActualCommand(approvedA.ProposalRevision) }, $"\"proposal:{approvedA.ProposalRevision}\"", token), receipt => receipt.ActivationId);
            evidence["activatedA"] = a;
            RecordEvent("A_ACTIVATED");
            Assert.AreEqual(captured.MappingReleaseId, a.MappingReleaseId);
            Assert.AreNotEqual(captured.ActivationId, a.ActivationId);
            Assert.IsTrue(a.ActivationRevision > b.ActivationRevision);
            Assert.IsTrue(DateTimeOffset.UtcNow < running.DeadlineAtUtc);
            abaCompleted = true;
        }
        // 调度原回调，观察其退出或异常，不额外执行映射或查询动作。
        async Task SwitchTwice(CancellationToken token)
        {
            Point("CALLBACK", "ENTER", token, proposalId);
            try
            {
                await SwitchCore(token);
                Point("CALLBACK", "RETURN", token, evidence.GetValueOrDefault("queryId") as string);
            }
            catch (Exception error)
            {
                Point("CALLBACK", "ERROR", token, evidence.GetValueOrDefault("queryId") as string, error);
                throw;
            }
        }
        // 只在已完成回调后记录正式事务绑定检查，排除准入的同名方法。
        void BindingPoint(string edge, CancellationToken token, Exception? error)
        {
            if (abaCompleted) Point("FINAL_BINDING_CHECK", edge, token, evidence.GetValueOrDefault("queryId") as string, error);
        }
        // Doris 和 Oracle 的切换在源观察器退出后、最终事务取得第一把授权锁前进行，切换不占用源 I/O 预算。
        var execution = editing is null
            ? new G4QueryExecution(services.GetRequiredService<IG4QueryBindingReader>(),
                new AfterReadSource(services.GetRequiredService<IG4SourceQueryReader>(), SwitchTwice),
                services.GetRequiredService<IG4QueryAuthorizationAuthority>(), services.GetRequiredService<G4QueryResultStore>(), TimeProvider.System)
            : BeforeCommitExecution(services, SwitchTwice, oracle ? BindingPoint : null,
                sourceEvents is null ? null : services.GetRequiredService<ILogger<G4QueryExecution>>());
        // 与UI/MCP相同的SemanticGateway生成实际五秒截止，不能用测试时钟延长。
        var gateway = new SemanticGateway(services.GetRequiredService<IReleaseCatalog>(), services.GetRequiredService<ISemanticRuntime>(),
            services.GetRequiredService<CapabilityRegistry>(), services.GetRequiredService<IAuditTrail>(), TimeProvider.System,
            services.GetRequiredService<VerifiedReleaseSources>(), execution);
        // 只有原业务断言全部通过才允许在 finally 核对资格，异常路径只读回原件。
        var eligible = false;
        try
        {
            elapsed.Start();
            // 必须是两次激活完成之后的确切绑定拒绝，不能接受超时或映射命令失败。
            var error = await Assert.ThrowsAsync<SemanticOperationException>(() => gateway.ExecuteG4Async(actor, original.SessionReference, query, key, null, CancellationToken.None));
            RecordEvent("COMMIT_REJECTED");
            elapsed.Stop();
            evidence["errorStatus"] = error.Status;
            evidence["errorCode"] = error.Code;
            Assert.IsTrue(abaCompleted);
            Assert.AreEqual(409, error.Status);
            Assert.AreEqual("query_binding_stale", error.Code);
            Assert.IsTrue(elapsed.ElapsedMilliseconds < 5000);
            if (oracle)
            {
                eligible = true;
                return;
            }
            // 新上下文按精确ID检查数据库实际终态，避免跟踪缓存假阳性。
            await using var fresh = await services.GetRequiredService<IDbContextFactory<G4QueryDbContext>>().CreateDbContextAsync();
            // 不扫描或清理其他查询，只核验本次随机命令。
            var rejected = await fresh.Queries.SingleAsync(item => item.IdempotencyKey == key);
            Assert.AreNotEqual("COMPLETED", rejected.ExecutionStatus);
            Assert.AreEqual(0, rejected.ResultCiphertext.Length);
            Assert.IsNull(rejected.ResultHash);
            Assert.AreEqual(0, rejected.ResultSize);
            Assert.AreEqual(0, G4QueryResultStore.ReadState(rejected).Receipts.Length);
            // 正式治理库只读核验同一queryId，没有提交成功审计。
            await using var governance = await services.GetRequiredService<IDbContextFactory<GovernanceDbContext>>().CreateDbContextAsync();
            // 成功审计与结果必须同时为空，不以应用异常代替持久层检查。
            var successes = await governance.AuditRecords.CountAsync(item => item.Resource == rejected.Id && item.Action == "data.query.execute" && item.Outcome == "allowed");
            Assert.AreEqual(0, successes);
            evidence["executionStatus"] = rejected.ExecutionStatus;
            evidence["ciphertextBytes"] = rejected.ResultCiphertext.Length;
            evidence["resultHash"] = rejected.ResultHash;
            evidence["resultSize"] = rejected.ResultSize;
            evidence["committedReadReceipts"] = G4QueryResultStore.ReadState(rejected).Receipts.Length;
            evidence["successfulQueryAudits"] = successes;
            evidence["status"] = "PASS";
        }
        finally
        {
            elapsed.Stop();
            evidence["elapsedMs"] = elapsed.Elapsed.TotalMilliseconds;
            evidence["events"] = events;
            sourceEvents?.Export(evidence);
            evidence["abaCompleted"] = abaCompleted;
            // 后态查询在 Gateway 计时之外，失败保留原异常；资格检查在写出原件后进行。
            if (oracle)
            {
                // 记录实际响应后采样区间，与五秒内的阶段区间分开。
                var postStarted = DateTimeOffset.UtcNow;
                // 独立单调表只计取证开销。
                var postClock = Stopwatch.StartNew();
                evidence["postStateStartedAtUtc"] = postStarted;
                try
                {
                    // 只重开回调中有实际激活尝试的提案，失败时也能关联已落库的检查与命令。
                    var attempted = phases.Where(row => row["phase"] is "B_ACTIVATE" or "A_ACTIVATE" && row["edge"] is "ENTER")
                        .Select(row => (string)row["resourceId"]!).Distinct(StringComparer.Ordinal).ToArray();
                    await ReadOracleAbaPostState(services, key, actor, approvedB.MappingId, commands, attempted, evidence);
                    evidence["postStateStatus"] = "READ";
                }
                catch (Exception error) when (error is not OutOfMemoryException)
                {
                    evidence["postStateStatus"] = "READ_FAILED";
                    evidence["postStateError"] = error.GetType().Name;
                }
                evidence["postStateElapsedMs"] = postClock.Elapsed.TotalMilliseconds;
                evidence["postStateFinishedAtUtc"] = DateTimeOffset.UtcNow;
                foreach (var phase in phases) // 回填之前未知的真实持久截止；不新开计时窗口。
                {
                    // 若准入行不可见，则期限仍未知，不能补成零。
                    var deadline = evidence.GetValueOrDefault("deadlineAtUtc") as DateTimeOffset?;
                    phase["deadlineAtUtc"] = deadline;
                    phase["remainingMs"] = (deadline - (DateTimeOffset)phase["utc"]!)?.TotalMilliseconds;
                    phase["queryId"] = evidence.GetValueOrDefault("queryId");
                }
                evidence["diagnosticPhases"] = phases;
                evidence["diagnosticPhasesDropped"] = dropped;
                if (eligible && Equals(evidence.GetValueOrDefault("postStateStatus"), "READ")
                    && evidence.GetValueOrDefault("executionStatus") is "RUNNING" or "FAILED" or "CANCELLED"
                    && Equals(evidence.GetValueOrDefault("ciphertextBytes"), 0)
                    && evidence["resultHash"] is null && Convert.ToInt64(evidence["resultSize"], CultureInfo.InvariantCulture) == 0
                    && Equals(evidence.GetValueOrDefault("successfulQueryAudits"), 0)
                    && Equals(evidence.GetValueOrDefault("committedReadReceipts"), 0))
                    evidence["status"] = "PASS";
            }
            // 临时容器退出前由执行器回收公开原件；失败原件也保留。
            // Doris 宿主只写本任务既有原件目录，其他驱动保留原固定文件入口。
            var resultFile = runtimeIdentity == "G4-DORIS-MAPPING-QUERY-001:implementation-01"
                ? Path.Combine(DorisRuntimeRoot(), "artifacts/workflow/G4-DORIS-MAPPING-QUERY-001/implementation-01", $"aba-inflight-{key}.json")
                : runtimeIdentity == "G4-ORACLE-MAPPING-QUERY-001:product-resume-01"
                    ? Environment.GetEnvironmentVariable("OMQ_RUNTIME_REPORT")! : "/tmp/aba-inflight.json";
            if (runtimeIdentity == "G4-ORACLE-MAPPING-QUERY-001:product-resume-01")
                Assert.IsTrue(System.Text.RegularExpressions.Regex.IsMatch(resultFile, "^/tmp/omq-s23-[a-f0-9]{32}/aba-inflight[.]json$"));
            await File.WriteAllTextAsync(resultFile, JsonSerializer.Serialize(evidence, new JsonSerializerOptions(JsonSerializerDefaults.Web)) + "\n");
            if (eligible) Assert.AreEqual("PASS", evidence["status"]);
        }
    }

    /// <summary>在 Gateway 返回后，以三个独立上下文读取本 Q、审计、当前激活及本回调发出的命令。</summary>
    private static async Task ReadOracleAbaPostState(IServiceProvider services, string key, ActorContext actor, string mappingId,
        List<string> commands, string[] attempted, Dictionary<string, object?> evidence)
    {
        // 记录各独立投影的未知项；单个读回失败时还会尝试其余已知身份。
        var missing = new List<string>();
        // 总预算属于响应后外层，仅用于只读投影。
        using var cutoff = new CancellationTokenSource(TimeSpan.FromSeconds(3));
        async Task Sample(string name, Func<Task> read)
        {
            try
            {
                await read();
            }
            catch (Exception failure) when (failure is not OutOfMemoryException)
            {
                missing.Add(name + "/" + failure.GetType().Name);
            }
        }
        await Sample("query", async () =>
        {
            // 只用本调用的随机键与真实参与者查找，失败也不尝试另一行。
            await using var fresh = await services.GetRequiredService<IDbContextFactory<G4QueryDbContext>>().CreateDbContextAsync(cutoff.Token);
            // 只读本组织、本主体和准确幂等键对应的查询，从未准入时保留未知。
            var rejected = await fresh.Queries.AsNoTracking().SingleAsync(row => row.OrganizationId == actor.OrganizationId
                && row.SubjectId == actor.SubjectId && row.IdempotencyKey == key, cutoff.Token);
            if (evidence.TryGetValue("queryId", out var captured) && !Equals(captured, rejected.Id))
                throw new InvalidOperationException("原查询与后态查询标识不一致。");
            evidence["queryId"] = rejected.Id;
            evidence["deadlineAtUtc"] = rejected.DeadlineAtUtc;
            evidence["executionStatus"] = rejected.ExecutionStatus;
            evidence["resultHash"] = rejected.ResultHash;
            evidence["resultSize"] = rejected.ResultSize;
            evidence["ciphertextBytes"] = rejected.ResultCiphertext.Length;
            evidence["committedReadReceipts"] = G4QueryResultStore.ReadState(rejected).Receipts.Length;
            evidence["postLeaseOwnerHash"] = rejected.LeaseOwner is null ? null : G4QueryCanonical.Hash(System.Text.Encoding.UTF8.GetBytes(rejected.LeaseOwner));
            evidence["postFence"] = rejected.Fence;
            evidence["postLeaseUntilUtc"] = rejected.LeaseUntilUtc;
            evidence["postErrorCode"] = rejected.ErrorCode;
        });
        await Sample("audits", async () =>
        {
            // 查询读回失败时，仍可用回调里原有的精确 ID 核审计。
            if (evidence.GetValueOrDefault("queryId") is not string queryId)
                throw new InvalidOperationException("缺少原查询标识。");
            // 从治理库只回读同一 Q 的执行审计，不输出主体或会话原文。
            await using var governance = await services.GetRequiredService<IDbContextFactory<GovernanceDbContext>>().CreateDbContextAsync(cutoff.Token);
            // 逐行保存固定审计身份与结果，限定同一组织与 Q。
            var audits = await governance.AuditRecords.AsNoTracking().Where(row => row.OrganizationId == actor.OrganizationId
                && row.Resource == queryId && row.Action == "data.query.execute").OrderBy(row => row.Id)
                .Select(row => new { row.Id, row.Outcome, row.OccurredAtUtc }).ToArrayAsync(cutoff.Token);
            evidence["queryAudits"] = audits;
            evidence["successfulQueryAudits"] = audits.Count(row => row.Outcome == "allowed");
            evidence["failedQueryAudits"] = audits.Count(row => row.Outcome == "failure");
        });
        await Sample("mapping", async () =>
        {
            // 只定位刚进入过的正式映射操作，既不重发也不修改其中任何行。
            await using var mappings = await services.GetRequiredService<IDbContextFactory<ConnectionsDbContext>>().CreateDbContextAsync(cutoff.Token);
            evidence["postActive"] = await mappings.MappingActives.AsNoTracking().Where(row => row.OrganizationId == actor.OrganizationId
                && row.MappingId == mappingId).Select(row => new { row.MappingId, row.ActivationId, row.ReleaseId, row.ActivationRevision }).SingleAsync(cutoff.Token);
            evidence["postActivations"] = await mappings.MappingActivations.AsNoTracking().Where(row => row.OrganizationId == actor.OrganizationId
                && row.MappingId == mappingId && attempted.Contains(row.ProposalId)).OrderBy(row => row.ActivationRevision)
                .Select(row => new { row.Id, row.ProposalId, row.CheckId, row.ReleaseId, row.ActivationRevision }).ToArrayAsync(cutoff.Token);
            evidence["postChecks"] = await mappings.MappingActivationChecks.AsNoTracking().Where(row => row.OrganizationId == actor.OrganizationId
                && row.MappingId == mappingId && attempted.Contains(row.ProposalId)).OrderBy(row => row.CreatedAtUtc)
                .Select(row => new { row.Id, row.ProposalId, row.Status, row.CreatedAtUtc }).ToArrayAsync(cutoff.Token);
            evidence["postCommands"] = await mappings.MappingCommands.AsNoTracking().Where(row => row.OrganizationId == actor.OrganizationId
                && row.MappingId == mappingId && commands.Contains(row.CommandId)).OrderBy(row => row.CommandId)
                .Select(row => new { row.Id, row.CommandId, row.Operation, row.CreatedAtUtc }).ToArrayAsync(cutoff.Token);
        });
        evidence["postStateMissing"] = missing;
        if (missing.Count > 0) throw new InvalidOperationException("后态部分读回失败。");
    }

    /// <summary>透传正式绑定服务，仅在事务校验的实际边界记录开始、返回与原异常。</summary>
    private sealed class ObservedBindingReader(IG4QueryBindingReader actual, Action<string, CancellationToken, Exception?> record) : IG4QueryBindingReader
    {
        /// <summary>捕获当前绑定时保持实际实现与查询截止。</summary>
        public Task<G4QueryBindingContext> CaptureAsync(ActorContext actor, G4SemanticQuery query, long epoch, CancellationToken token)
            => actual.CaptureAsync(actor, query, epoch, token);

        /// <summary>记录正式事务验证边界，不拦截或翻译真实错误。</summary>
        public async Task VerifyInTransactionAsync(ActorContext actor, G4SemanticQuery query, G4QueryBinding expected,
            DbConnection connection, DbTransaction transaction, CancellationToken token)
        {
            record("ENTER", token, null);
            try
            {
                await actual.VerifyInTransactionAsync(actor, query, expected, connection, transaction, token);
                record("RETURN", token, null);
            }
            catch (Exception error)
            {
                record("ERROR", token, error);
                throw;
            }
        }

        /// <summary>历史回读透传相同的范围与取消条件。</summary>
        public Task<G4QueryBindingContext> ReadHistoricalAsync(ActorContext actor, G4QueryBinding binding, ResourceScope scope, CancellationToken token)
            => actual.ReadHistoricalAsync(actor, binding, scope, token);

        /// <summary>历史访问仍由同一连接、同一事务内的正式参与者验证。</summary>
        public Task VerifyHistoricalAccessInTransactionAsync(ActorContext actor, G4QueryConnectionAccess access,
            DbConnection connection, DbTransaction transaction, CancellationToken token)
            => actual.VerifyHistoricalAccessInTransactionAsync(actor, access, connection, transaction, token);
    }
}
