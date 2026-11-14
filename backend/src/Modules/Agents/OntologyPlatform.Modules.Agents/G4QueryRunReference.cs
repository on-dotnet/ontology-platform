using OntologyPlatform.Contracts;
using Microsoft.Extensions.AI;
using System.Runtime.CompilerServices;

namespace OntologyPlatform.Modules.Agents;

/// <summary>仅在服务器工具循环内流转的G4运行引用，不作为客户端DTO或旧Run结果。</summary>
public sealed class G4QueryRunReference
{
    /// <summary>运行内原子计数，跨请求持久约束仍由查询模块执行。</summary>
    private int calls;

    /// <summary>服务器随机标识，调用方不能指定另一个运行。</summary>
    public string RunId { get; } = Guid.NewGuid().ToString("N");

    /// <summary>第一次受控执行固定的绝对期限，后续工具不延期。</summary>
    public DateTimeOffset Deadline { get; }

    /// <summary>服务器在开始工具循环时建立三十秒预算。</summary>
    public G4QueryRunReference(DateTimeOffset started) => Deadline = started.AddSeconds(30);

    /// <summary>每个执行或恢复尝试都计数，超限尝试不进入查询网关。</summary>
    public int Reserve(DateTimeOffset now)
    {
        if (now >= Deadline) throw new SemanticOperationException(429, "query_run_budget");
        // 先原子占用次数，失败不会返还预算供无限重试。
        var count = Interlocked.Increment(ref calls);
        if (count > 3) throw new SemanticOperationException(429, "query_run_budget");
        return count;
    }
}


/// <summary>仅生成固定函数调用的离线MAF客户端，没有模型凭证或网络能力。</summary>
internal sealed class G4QueryRunClient(string toolName, int attempts) : IChatClient
{
    /// <summary>实际提供者轮次，只控制已批准负例次数。</summary>
    private int requests;

    /// <summary>每轮由MAF执行真实工具；结束文本不伪造任何业务结果。</summary>
    public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (++requests > attempts + 1) throw new InvalidOperationException("G4离线提供者循环超限。");
        if (requests > attempts) return Task.FromResult(new ChatResponse(new ChatMessage(ChatRole.Assistant, "受控工具循环完成。")));
        if (options?.Tools?.Any(tool => tool.Name == toolName) != true) throw new InvalidOperationException("缺少固定G4工具。");
        return Task.FromResult(new ChatResponse(new ChatMessage(ChatRole.Assistant,
            [new FunctionCallContent("g4-call-" + requests, toolName, new Dictionary<string, object?>())])));
    }

    /// <summary>使用标准协议流适配，保留函数调用而不合成模型token。</summary>
    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // 所有函数内容来自相同受控响应。
        var response = await GetResponseAsync(messages, options, cancellationToken);
        foreach (var update in response.ToChatResponseUpdates()) yield return update;
    }

    /// <summary>不解析外部模型配置或服务，只返回当前离线实例。</summary>
    public object? GetService(Type serviceType, object? serviceKey = null) => serviceKey is null && serviceType.IsInstanceOfType(this) ? this : null;

    /// <summary>无网络资源，生命周期与当前MAF运行一致。</summary>
    public void Dispose() { }
}
