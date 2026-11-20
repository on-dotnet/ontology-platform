using System.Diagnostics;
using System.Globalization;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using OntologyPlatform.Contracts;
using OntologyPlatform.Modules.Connections;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.SemanticQuery;

namespace OntologyPlatform.AgentTests;

/// <summary>AC-05真实在途ABA验收，保持正式五秒截止和所有安全参与者。</summary>
public sealed partial class G4QueryMafRuntimeTests
{
    /// <summary>真实源读取后经正式批准和激活执行A到B再到A，核验提交失败和审计原子性。</summary>
    private static async Task MappingAbaAfterRealReadAsync(IServiceProvider services, ActorContext actor,
        G4QueryRecord original, G4QueryDbContext database, string proposalId,
        (ActorContext Actor, string Session)? editing = null, (ActorContext Actor, string Session)? activating = null, string? reviewerId = null)
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
        // 只在进程内读取准确提案保存的真实审核会话，不构造角色或导出证明。
        await using var connections = await services.GetRequiredService<IDbContextFactory<ConnectionsDbContext>>().CreateDbContextAsync();
        // 精确提案记录由真实OIDC异人审核创建。
        var proposal = await connections.MappingProposals.AsNoTracking().SingleAsync(item => item.Id == proposalId);
        // 后续Decide会重新检查此真实服务器会话及当前授权。
        var auditor = JsonSerializer.Deserialize<MappingAuthorizationProof>(proposal.DecisionProofJson!, G4MappingJson.Options)!;
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
        // 完整两次激活完成后才能把409归因于查询提交。
        var abaCompleted = false;
        // 真实墙钟预算从正式Gateway调用之前开始。
        var elapsed = new Stopwatch();
        // 事件序列由唯一查询进程产生，UTC关联数据库，单调时钟证明原五秒内顺序。
        var events = new List<object>();
        // 捕获后每个阶段都绑定同一query和mapping，不借其他请求的成功回执。
        void RecordEvent(string phase)
        {
            events.Add(new
            {
                phase,
                sequence = events.Count + 1,
                monotonicMs = elapsed.Elapsed.TotalMilliseconds,
                utc = DateTimeOffset.UtcNow,
                queryId = evidence["queryId"],
                mappingId = evidence["mappingId"],
                connectionId = evidence.GetValueOrDefault("connectionId")
            });
        }
        // 唯一注入点在真实源读取之后，不替换版本读取器、结果存储或审计参与者。
        async Task SwitchTwice(CancellationToken token)
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
            var b = await activations.ActivateAsync(activator.Actor, activator.Session, proposalId,
                new MappingActivationRequest { BindingHash = approvedB.BindingHash, ExpectedActive = approvedB.ExpectedActive,
                    Command = Command(approvedB.ProposalRevision) }, $"\"proposal:{approvedB.ProposalRevision}\"", token);
            evidence["activatedB"] = b;
            RecordEvent("B_ACTIVATED");
            Assert.AreNotEqual(captured.MappingReleaseId, b.MappingReleaseId);
            Assert.IsTrue(b.ActivationRevision > long.Parse(captured.ActivationRevision, CultureInfo.InvariantCulture));
            // 回滚目标是原查询捕获的真实历史A原字节散列。
            var target = new MappingRollbackTarget { TargetReleaseId = captured.MappingReleaseId, ManifestHash = captured.ManifestHash };
            // 正式入队并由实际消费者运行，不写伪造assessment或activation行。
            var job = await mappings.ValidateAsync(editor.Actor, editor.Session, captured.MappingId,
                new MappingValidateRequest { Target = target, Command = Command(draft.Revision) }, $"\"mapping:{draft.Revision}\"", token);
            // 显式调用已注册真实worker省掉后台轮询等待，不启动宿主其他服务。
            var worker = services.GetServices<IHostedService>().OfType<MappingJobWorker>().Single();
            while (job.Status is "QUEUED" or "RUNNING")
            {
                await worker.RunNextAsync(token);
                job = await mappings.ReadJobAsync(editor.Actor, editor.Session, job.JobId, token);
                if (job.Status is "QUEUED" or "RUNNING") await Task.Delay(10, token);
            }
            Assert.AreEqual("SUCCEEDED", job.Status);
            // 七阶段结果由真实源、语义和当前授权验证产生。
            var assessment = await mappings.ReadAssessmentAsync(editor.Actor, editor.Session, job.AssessmentId!, token);
            Assert.AreEqual("READY_FOR_PROPOSAL", assessment.Status);
            Assert.AreEqual(7, assessment.Stages.Length);
            Assert.IsTrue(assessment.Stages.All(stage => stage.Status == "PASS"));
            // 回滚提案绑定B当前激活基线，不预造不可成立的CAS。
            var proposedA = await mappings.ProposeAsync(editor.Actor, editor.Session, captured.MappingId,
                new MappingRollbackProposalRequest { SchemaVersion = "g4.mapping.v1", Scope = draft.Scope, Binding = assessment.Binding,
                    ExpectedActive = assessment.ExpectedActive, ExpiresAtUtc = assessment.ExpiresAtUtc, Command = Command(0),
                    TargetReleaseId = target.TargetReleaseId, ManifestHash = target.ManifestHash }, token);
            // 使用已获正式服务器验证的不同审核主体，当前授权仍由正式服务重核。
            var approvedA = await mappings.DecideAsync(auditor.Actor, auditor.SessionReference, proposedA.ProposalId,
                new MappingDecisionRequest { Decision = "APPROVE", BindingHash = proposedA.BindingHash, Command = Command(proposedA.ProposalRevision) },
                $"\"proposal:{proposedA.ProposalRevision}\"", token);
            // 第二次真实激活回到同一release，但生成新的activation身份和单调修订。
            var a = await activations.ActivateAsync(activator.Actor, activator.Session, approvedA.ProposalId,
                new MappingActivationRequest { BindingHash = approvedA.BindingHash, ExpectedActive = approvedA.ExpectedActive,
                    Command = Command(approvedA.ProposalRevision) }, $"\"proposal:{approvedA.ProposalRevision}\"", token);
            evidence["activatedA"] = a;
            RecordEvent("A_ACTIVATED");
            Assert.AreEqual(captured.MappingReleaseId, a.MappingReleaseId);
            Assert.AreNotEqual(captured.ActivationId, a.ActivationId);
            Assert.IsTrue(a.ActivationRevision > b.ActivationRevision);
            Assert.IsTrue(DateTimeOffset.UtcNow < running.DeadlineAtUtc);
            abaCompleted = true;
        }
        // Doris 和 Oracle 的切换在源观察器退出后、最终事务取得第一把授权锁前进行，切换不占用源 I/O 预算。
        var execution = editing is null
            ? new G4QueryExecution(services.GetRequiredService<IG4QueryBindingReader>(),
                new AfterReadSource(services.GetRequiredService<IG4SourceQueryReader>(), SwitchTwice),
                services.GetRequiredService<IG4QueryAuthorizationAuthority>(), services.GetRequiredService<G4QueryResultStore>(), TimeProvider.System)
            : BeforeCommitExecution(services, SwitchTwice);
        // 与UI/MCP相同的SemanticGateway生成实际五秒截止，不能用测试时钟延长。
        var gateway = new SemanticGateway(services.GetRequiredService<IReleaseCatalog>(), services.GetRequiredService<ISemanticRuntime>(),
            services.GetRequiredService<CapabilityRegistry>(), services.GetRequiredService<IAuditTrail>(), TimeProvider.System,
            services.GetRequiredService<VerifiedReleaseSources>(), execution);
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
            evidence["elapsedMs"] = elapsed.Elapsed.TotalMilliseconds;
            evidence["events"] = events;
            evidence["abaCompleted"] = abaCompleted;
            // 临时容器退出前由执行器回收公开原件；失败原件也保留。
            // Doris 宿主只写本任务既有原件目录，其他驱动保留原固定文件入口。
            var resultFile = runtimeIdentity == "G4-DORIS-MAPPING-QUERY-001:implementation-01"
                ? Path.Combine(DorisRuntimeRoot(), "artifacts/workflow/G4-DORIS-MAPPING-QUERY-001/implementation-01", $"aba-inflight-{key}.json")
                : runtimeIdentity == "G4-ORACLE-MAPPING-QUERY-001:product-resume-01"
                    ? Environment.GetEnvironmentVariable("OMQ_RUNTIME_REPORT")! : "/tmp/aba-inflight.json";
            if (runtimeIdentity == "G4-ORACLE-MAPPING-QUERY-001:product-resume-01")
                Assert.IsTrue(System.Text.RegularExpressions.Regex.IsMatch(resultFile, "^/tmp/omq-s23-[a-f0-9]{32}/aba-inflight[.]json$"));
            await File.WriteAllTextAsync(resultFile, JsonSerializer.Serialize(evidence, new JsonSerializerOptions(JsonSerializerDefaults.Web)) + "\n");
        }
    }
}
