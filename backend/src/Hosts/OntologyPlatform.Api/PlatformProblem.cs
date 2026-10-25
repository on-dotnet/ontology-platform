using System.Diagnostics;

namespace OntologyPlatform.Api;

/// <summary>输出统一、无秘密的标准ProblemDetails。</summary>
public static class PlatformProblem
{
    /// <summary>为当前请求创建具有关联标识的通用错误。</summary>
    /// <param name="context">当前请求。</param>
    /// <param name="status">准确的HTTP状态。</param>
    /// <param name="code">平台固定错误代码。</param>
    /// <returns>标准application/problem+json响应。</returns>
    public static IResult Create(HttpContext context, int status, string code)
    {
        return Results.Problem(statusCode: status, title: status switch
        {
            401 => "需要有效登录",
            403 => "当前请求无权执行",
            404 => "资源不存在",
            500 => "平台内部故障",
            503 => "依赖暂不可用",
            _ => "请求无效"
        }, type: "about:blank", detail: "请求无法完成，请使用关联标识联系运维。",
        extensions: new Dictionary<string, object?>
        {
            ["code"] = code,
            ["traceId"] = Activity.Current?.TraceId.ToString() ?? context.TraceIdentifier,
            ["correlationId"] = context.Items["CorrelationId"]
        });
    }
}
