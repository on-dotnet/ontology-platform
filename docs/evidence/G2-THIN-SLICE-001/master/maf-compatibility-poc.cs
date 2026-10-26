using System.Runtime.CompilerServices;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

// 此隔离兼容PoC只驱动真实MAF调用本地数学函数，不是G2业务或真实模型验收。
var calls = 0;
// 函数委托记录真实调用次数，最终断言工具实际执行一次。
var function = AIFunctionFactory.Create((int value) => { Interlocked.Increment(ref calls); return value * 2; }, "g2_compat_probe", "仅供离线兼容测试的本地确定性函数");
// 提供者仅生成SDK标准函数调用消息，并从真实返回值构造最终消息，无外部网络。
using var client = new OfflineClient();
// 使用批准的真实MAF ChatClientAgent和正式工具声明。
var agent = new ChatClientAgent(client, instructions: "只执行离线兼容测试工具", tools: [function]);
// 新会话由真实框架创建，不冒充产品PG持久Run。
var session = await agent.CreateSessionAsync();
// 执行两轮provider/工具协议，检查实际工具结果。
var result = await agent.RunAsync("离线兼容测试", session);
if (calls != 1 || client.Requests != 2 || !result.Text.Contains("42", StringComparison.Ordinal))
{
    throw new InvalidOperationException("真实MAF函数调用兼容断言失败");
}
Console.WriteLine(JsonSerializer.Serialize(new { status = "PASS", mode = "deterministic_compatibility_only", maf = "1.26.0", ai = "10.11.0", mcpAssembly = System.Reflection.Assembly.Load("ModelContextProtocol.AspNetCore").GetName().Version?.ToString(), actualToolCalls = calls, actualProviderRounds = client.Requests, actualResult = result.Text, realModel = "NOT_RUN", g2ProductGateway = "NOT_RUN" }, new JsonSerializerOptions { WriteIndented = true }));

/// <summary>只在隔离PoC中生成标准函数消息，绝不调用真实模型。</summary>
sealed class OfflineClient : IChatClient
{
    /// <summary>用于验证实际框架完成工具调用循环的请求计数。</summary>
    public int Requests { get; private set; }

    /// <summary>首次请求函数调用，第二次读取工具返回的真实值。</summary>
    public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        Requests++;
        // 框架回传工具结果后才生成结果文本，避免仅声称工具被调用。
        var returned = messages.SelectMany(message => message.Contents).OfType<FunctionResultContent>().LastOrDefault();
        if (returned is not null)
        {
            return Task.FromResult(new ChatResponse(new ChatMessage(ChatRole.Assistant, JsonSerializer.Serialize(returned.Result))));
        }
        if (Requests > 2 || options?.Tools?.All(tool => tool.Name != "g2_compat_probe") != false)
        {
            throw new InvalidOperationException("隔离PoC未收到批准工具声明");
        }
        return Task.FromResult(new ChatResponse(new ChatMessage(ChatRole.Assistant, [new FunctionCallContent("compat-call-1", "g2_compat_probe", new Dictionary<string, object?> { ["value"] = 21 })])));
    }

    /// <summary>同一离线响应的流式适配，仅用于满足SDK公共接口。</summary>
    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // 保持函数内容而非丢为纯文本。
        var response = await GetResponseAsync(messages, options, cancellationToken);
        foreach (var update in response.ToChatResponseUpdates())
        {
            yield return update;
        }
    }

    /// <summary>只提供自身类型，不暴露任何配置或模型凭证。</summary>
    public object? GetService(Type serviceType, object? serviceKey = null) => serviceKey is null && serviceType.IsInstanceOfType(this) ? this : null;

    /// <summary>本离线客户端无外部连接需要释放。</summary>
    public void Dispose() { }
}
