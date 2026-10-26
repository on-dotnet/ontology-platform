using System.Diagnostics;
using System.Diagnostics.Metrics;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Agents;

/// <summary>真实MAF标准工具循环；PG租约、取消及预算保持权威。</summary>
public sealed class AgentRunExecutor
{
    /// <summary>由宿主统一采样的运行链路源。</summary>
    private static readonly ActivitySource Activities = new("OntologyPlatform.Agents");

    /// <summary>仅低基数结果和能力的指标源。</summary>
    private static readonly Meter Meter = new("OntologyPlatform.Agents");

    /// <summary>不把运行、主体或Prompt写入标签。</summary>
    private static readonly Counter<long> Runs = Meter.CreateCounter<long>("agents.run.count");

    /// <summary>持久运行与事件用例。</summary>
    private readonly ExecutionRunService runs;

    /// <summary>与REST及MCP完全相同的唯一Gateway。</summary>
    private readonly ISemanticGateway gateway;

    /// <summary>与租约使用相同的服务端时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>接收实际模块服务，不提供备用查询实现。</summary>
    public AgentRunExecutor(ExecutionRunService runs, ISemanticGateway gateway, TimeProvider clock)
    {
        this.runs = runs;
        this.gateway = gateway;
        this.clock = clock;
    }

    /// <summary>处理一个PG候选并运行真实MAF；无候选返回false。</summary>
    public async Task<bool> RunOneAsync(string workerId, CancellationToken stoppingToken)
    {
        // 所有worker共同竞争PG，不通过本地队列认定任务归属。
        var claim = await runs.ClaimAsync(workerId, stoppingToken);
        if (claim is null) return false;
        await ExecuteAsync(claim, stoppingToken);
        return true;
    }

    /// <summary>执行claim绑定的版本与工具，旧fence永远不能提交事件。</summary>
    public async Task ExecuteAsync(RunRecord claim, CancellationToken stoppingToken)
    {
        // 后台执行创建实际新span；持久合同只保存traceId，不能伪造不存在的父span。
        using var activity = Activities.StartActivity("execution.run", ActivityKind.Internal);
        activity?.SetTag("execution.creation_trace_id", claim.TraceId);
        // 使用剩余绝对预算，接管不能重新获得三十秒。
        using var cancellation = CancellationTokenSource.CreateLinkedTokenSource(stoppingToken);
        // 首次claim已经设置deadline，失效预算直接进入失败终态。
        var remaining = claim.DeadlineUtc!.Value - clock.GetUtcNow();
        if (remaining > TimeSpan.Zero) cancellation.CancelAfter(remaining); else cancellation.Cancel();
        // 心跳直接检查PG取消与fence并将失效传播到Gateway/Jena。
        var monitor = MonitorAsync(claim, cancellation);
        // 只来自PG保存的服务器身份和固定计划。
        var actor = ExecutionRunService.Decode<ActorContext>(claim.ActorJson);
        // Prompt永远不能改写此计划或扩充工具。
        var plan = ExecutionRunService.Decode<SemanticQueryPlan>(claim.PlanJson);
        // 统计实际调用，不以提供者声称执行代替结果。
        var calls = 0;
        // 最终状态只能取真实Gateway返回。
        SemanticQueryStatus? resultStatus = null;
        try
        {
            if (claim.ProviderMode != "deterministic" || !runs.DeterministicEnabled)
            {
                await AppendAsync(claim, new RunFailedPayload { Status = ExecutionStatus.Failed, Code = "provider_not_configured", TotalToolCalls = claim.ToolCalls }, stoppingToken);
                return;
            }
            if (remaining <= TimeSpan.Zero) throw new OperationCanceledException(cancellation.Token);
            // 标准工具委托闭包仅持有可信计划，工具schema没有actor或可写管理能力。
            var tool = AIFunctionFactory.Create(async (CancellationToken token) =>
            {
                // 本次调用标识在持久tool.started/tool.completed间一致。
                var invocation = Guid.NewGuid().ToString("N");
                await AppendAsync(claim, new ToolStartedPayload { InvocationId = invocation, CapabilityId = plan.CapabilityId, CapabilityVersion = plan.CapabilityVersion, Plan = plan }, token);
                calls++;
                // 测量真实Gateway执行时间，不从模型输出伪造耗时。
                var timer = Stopwatch.StartNew();
                // 唯一执行器重新授权正式snapshot与实体范围。
                var result = await gateway.ExecuteAsync(actor, plan, token);
                resultStatus = result.Status;
                await AppendAsync(claim, new ToolCompletedPayload { InvocationId = invocation, Result = result, DurationMs = timer.Elapsed.TotalMilliseconds }, token);
                // 每条真实证据单独持久化，所有事件保持同一个正式snapshot。
                foreach (var evidence in result.Evidence)
                    await AppendAsync(claim, new EvidenceAddedPayload { Evidence = evidence }, token);
                return ExecutionRunService.Encode(result);
            }, plan.CapabilityId, "只调用运行创建时固定的正式版本与只读语义计划");
            // 真实Microsoft.Agents.AI提供函数调用循环，本客户端无任何模型网络能力。
            using var client = new DeterministicRunClient(plan.CapabilityId);
            // 工具白名单仅一个明确能力，其他Prompt指令无法新增工具。
            var agent = new ChatClientAgent(client, instructions: "只执行显式批准的只读工具；这是离线确定性验收，不是真实模型。", tools: [tool]);
            // MAF会话为本次调用临时上下文，Run与重放权威始终在PG。
            var session = await agent.CreateSessionAsync(cancellation.Token);
            // 真正交框架执行；正文不进入日志或指标。
            var response = await agent.RunAsync(claim.SourcePrompt, session, cancellationToken: cancellation.Token);
            if (calls != 1 || resultStatus is null) throw new InvalidOperationException("MAF未完成真实工具调用。");
            // 按UTF16长度有界分片并保持代理对完整，防止JSON序列化悄然替换非BMP字符。
            foreach (var chunk in ChunkMessageText(response.Text))
                await AppendAsync(claim, new MessageDeltaPayload { Text = chunk }, cancellation.Token);
            await AppendAsync(claim, new RunCompletedPayload { Status = ExecutionStatus.Completed, TotalToolCalls = claim.ToolCalls + calls, LastResultStatus = resultStatus }, cancellation.Token);
            Runs.Add(1, new KeyValuePair<string, object?>("outcome", "completed"), new KeyValuePair<string, object?>("capability", plan.CapabilityId));
        }
        catch (Exception failure) when (failure is not OutOfMemoryException && !stoppingToken.IsCancellationRequested)
        {
            // 只输出固定错误类别；租约失效或取消时append将自然拒绝旧worker。
            var code = failure is OperationCanceledException ? "run_timeout" : "tool_execution_failed";
            await runs.AppendAsync(claim.RunId, claim.LeaseOwner!, claim.FencingToken, new RunFailedPayload { Status = ExecutionStatus.Failed, Code = code, TotalToolCalls = claim.ToolCalls + calls }, stoppingToken);
            Runs.Add(1, new KeyValuePair<string, object?>("outcome", "failed"));
        }
        finally
        {
            await cancellation.CancelAsync();
            await monitor;
        }
    }

    /// <summary>每段不超过4096个UTF16单元；切点落在代理对中间时将整对留给下一段。</summary>
    private static IEnumerable<string> ChunkMessageText(string text)
    {
        // 偏移只按实际已发长度推进，收缩切点不会丢失或重复字符。
        var offset = 0;
        while (offset < text.Length)
        {
            // 合同使用String.Length上限，而非Unicode标量个数。
            var length = Math.Min(4096, text.Length - offset);
            if (offset + length < text.Length && char.IsSurrogatePair(text[offset + length - 1], text[offset + length])) length--;
            yield return text.Substring(offset, length);
            offset += length;
        }
    }

    /// <summary>失效事件提交立即停止后续工具，不能忽略预算失败继续输出成功。</summary>
    private async Task AppendAsync(RunRecord claim, ExecutionPayload payload, CancellationToken token)
    {
        if (!await runs.AppendAsync(claim.RunId, claim.LeaseOwner!, claim.FencingToken, payload, token)) throw new OperationCanceledException("持久租约或运行预算已失效。", token);
    }

    /// <summary>每二百毫秒真实查询PG的撤销/fence并续租；断开SSE不影响此令牌。</summary>
    private async Task MonitorAsync(RunRecord claim, CancellationTokenSource cancellation)
    {
        try
        {
            while (!cancellation.IsCancellationRequested)
            {
                await Task.Delay(TimeSpan.FromMilliseconds(200), cancellation.Token);
                if (!await runs.RenewAsync(claim.RunId, claim.LeaseOwner!, claim.FencingToken, cancellation.Token)) await cancellation.CancelAsync();
            }
        }
        catch (Exception failure) when (failure is not OutOfMemoryException)
        {
            // PG不可用时失败关闭，不在普通日志中输出数据库错误或正文。
            await cancellation.CancelAsync();
        }
    }
}
