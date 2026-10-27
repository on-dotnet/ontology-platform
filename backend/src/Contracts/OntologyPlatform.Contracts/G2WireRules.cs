using System.Collections.Concurrent;
using System.Globalization;
using System.Reflection;
using System.Text.Json;

namespace OntologyPlatform.Contracts;

/// <summary>只约束G2唯一DTO的线协议，不改变既有G1全局JSON行为。</summary>
internal static class G2WireRules
{
    /// <summary>有限合同类型的非空引用成员缓存，不接受客户端类型名。</summary>
    private static readonly ConcurrentDictionary<Type, PropertyInfo[]> RequiredMembers = new();

    /// <summary>在输入、持久化与输出采用完全相同的判别和非空规则。</summary>
    /// <param name="value">生成DTO主动传入的当前合同实例。</param>
    internal static void Validate(object value)
    {
        // 只对本合同程序集生成类型的显式非空引用进行检查。
        var members = RequiredMembers.GetOrAdd(value.GetType(), static type =>
        {
            // 每个类型独享反射上下文，不跨线程共享可变解析状态。
            var nullability = new NullabilityInfoContext();
            return type.GetProperties(BindingFlags.Public | BindingFlags.Instance)
                .Where(property => !property.PropertyType.IsValueType && nullability.Create(property).ReadState == NullabilityState.NotNull)
                .ToArray();
        });
        foreach (var property in members)
        {
            // 属性名来自固定代码元数据，值不拼接到错误消息。
            var member = property.GetValue(value);
            if (member is null)
            {
                throw new JsonException("G2必需字段不允许null。");
            }
            if (member is Array items && items.Cast<object?>().Any(item => item is null))
            {
                throw new JsonException("G2必需数组项不允许null。");
            }
        }
        switch (value)
        {
            case ReleaseManifest manifest:
                ReleaseManifestCompatibility.Validate(manifest);
                break;
            case PublicationSemantics binding:
                ReleaseManifestCompatibility.ValidateBinding(binding);
                break;
            case VersionRef reference when string.IsNullOrWhiteSpace(reference.Id)
                || (reference.Kind == VersionRefKind.Draft ? reference.Revision is null or < 1 : reference.Revision is not null):
                throw new JsonException("版本定位与修订判别不一致。");
            case SemanticDatum datum:
                // 恰好一个分支非空且与kind一致，禁止全空、混合和错配。
                var validDatum = datum.Kind switch
                {
                    SemanticDatumKind.Ontology => datum.Ontology is not null && datum.Entity is null && datum.Relationship is null,
                    SemanticDatumKind.Entity => datum.Entity is not null && datum.Ontology is null && datum.Relationship is null,
                    SemanticDatumKind.Relationship => datum.Relationship is not null && datum.Ontology is null && datum.Entity is null,
                    _ => false
                };
                if (!validDatum)
                {
                    throw new JsonException("G2语义数据分支与判别不一致。");
                }
                break;
            case ExecutionEvent envelope:
                // 从真实载荷CLR类型映射固定事件名称，不信任另一独立字符串。
                var expected = envelope.Payload switch
                {
                    RunStartedPayload => "run.started",
                    ToolStartedPayload => "tool.started",
                    ToolCompletedPayload => "tool.completed",
                    EvidenceAddedPayload => "evidence.added",
                    MessageDeltaPayload => "message.delta",
                    ApprovalRequiredPayload => "approval.required",
                    RunCompletedPayload => "run.completed",
                    RunFailedPayload => "run.failed",
                    RunCancelledPayload => "run.cancelled",
                    _ => string.Empty
                };
                if (envelope.SchemaVersion != 1 || envelope.EventType != expected || envelope.Seq < 1
                    || string.IsNullOrWhiteSpace(envelope.RunId)
                    || envelope.EventId != envelope.RunId + ":" + envelope.Seq.ToString(CultureInfo.InvariantCulture))
                {
                    throw new JsonException("G2执行事件的版本、游标或载荷判别不一致。");
                }
                break;
            case RunCompletedPayload completed when completed.Status != ExecutionStatus.Completed:
            case RunFailedPayload failed when failed.Status != ExecutionStatus.Failed:
            case RunCancelledPayload cancelled when cancelled.Status != ExecutionStatus.Cancelled || cancelled.Code != "cancelled":
                throw new JsonException("G2终态载荷与固定状态不一致。");
        }
    }
}
