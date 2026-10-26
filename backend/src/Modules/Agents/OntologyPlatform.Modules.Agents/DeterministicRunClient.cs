using System.Runtime.CompilerServices;
using Microsoft.Extensions.AI;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Agents;

/// <summary>显式离线测试提供者：仅产生MAF标准函数调用，并从真实工具返回构造文本。</summary>
internal sealed class DeterministicRunClient : IChatClient
{
    /// <summary>服务器固定的单个已登记只读能力名称。</summary>
    private readonly string capability;

    /// <summary>限制标准函数协议循环，防止提供者意外无界执行。</summary>
    private int requests;

    /// <summary>由可信运行计划确定唯一工具，不解析Prompt获取权限。</summary>
    internal DeterministicRunClient(string capability) => this.capability = capability;

    /// <summary>第一轮请求工具，第二轮读取真实工具结果，绝不预写成功数据。</summary>
    public Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (++requests > 2) throw new InvalidOperationException("离线提供者超过标准调用循环预算。");
        // 框架执行后的函数结果才可以形成展示文本。
        var returned = messages.SelectMany(message => message.Contents).OfType<FunctionResultContent>().LastOrDefault();
        if (returned is not null)
        {
            // 工具返回唯一SemanticQueryResult的JSON字符串，不能以空返回冒充成功。
            var serialized = returned.Result switch
            {
                string value => value,
                System.Text.Json.JsonElement value when value.ValueKind == System.Text.Json.JsonValueKind.String => value.GetString()!,
                _ => throw new InvalidOperationException("离线提供者未得到真实工具结果。")
            };
            // 再次执行唯一DTO的反序列化校验。
            var result = ExecutionRunService.Decode<SemanticQueryResult>(serialized);
            // 所有可展示数量、标签和证据标识均来自实际Gateway返回。
            var text = $"确定性工具结果（非真实模型）：{result.Status}；正式版本 {result.Snapshot.ReleaseId}；返回 {result.Data.Length} 项，候选 {result.Candidates.Length} 项，证据 {result.Evidence.Length} 项。"
                + string.Join("", result.Data.Select(value => value.Kind switch
                {
                    SemanticDatumKind.Entity => $"\n实体：{value.Entity!.Label}（{value.Entity.Iri}）",
                    SemanticDatumKind.Relationship => $"\n关系：{value.Relationship!.SourceIri} → {value.Relationship.PredicateIri} → {value.Relationship.TargetIri}",
                    _ => $"\n本体：{value.Ontology!.ClassIris.Length} 类，{value.Ontology.ObjectPropertyIris.Length} 对象属性。"
                })) + string.Join("", result.Evidence.Select(value => "\n证据：" + value.EvidenceId));
            return Task.FromResult(new ChatResponse(new ChatMessage(ChatRole.Assistant, text)));
        }
        if (options?.Tools?.Any(value => value.Name == capability) != true) throw new InvalidOperationException("离线提供者没有收到批准能力声明。");
        return Task.FromResult(new ChatResponse(new ChatMessage(ChatRole.Assistant,
            [new FunctionCallContent("deterministic-call-1", capability, new Dictionary<string, object?>())])));
    }

    /// <summary>保留完整函数协议内容的标准流适配，不伪造模型token。</summary>
    public async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // 同一协议响应交框架标准适配器拆分。
        var response = await GetResponseAsync(messages, options, cancellationToken);
        foreach (var update in response.ToChatResponseUpdates()) yield return update;
    }

    /// <summary>仅提供自身服务，不读取环境模型配置或凭证。</summary>
    public object? GetService(Type serviceType, object? serviceKey = null) => serviceKey is null && serviceType.IsInstanceOfType(this) ? this : null;

    /// <summary>离线实现没有网络连接或外部模型资源。</summary>
    public void Dispose()
    {
    }
}
