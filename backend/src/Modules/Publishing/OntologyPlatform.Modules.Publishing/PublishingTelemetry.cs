using System.Diagnostics;
using System.Diagnostics.Metrics;

namespace OntologyPlatform.Modules.Publishing;

/// <summary>发布低基数遥测，只保留固定操作、结果、阶段。</summary>
internal static class PublishingTelemetry
{
    /// <summary>模块固定活动源，与宿主Trace自动关联。</summary>
    internal static readonly ActivitySource Activities = new("OntologyPlatform.Publishing");

    /// <summary>模块固定指标名称空间。</summary>
    private static readonly Meter Meter = new("OntologyPlatform.Publishing");

    /// <summary>实际阶段完成次数，不以身份或scope作标签。</summary>
    private static readonly Counter<long> Operations = Meter.CreateCounter<long>("publishing.operations");

    /// <summary>仅代码内固定有限值调用，不接受请求正文或trace标签。</summary>
    internal static void Record(string operation, string status, string phase) => Operations.Add(1, new KeyValuePair<string, object?>("operation", operation), new KeyValuePair<string, object?>("status", status), new KeyValuePair<string, object?>("phase", phase));
}
