using Microsoft.AspNetCore.Antiforgery;
using Microsoft.AspNetCore.Http;
using Microsoft.Extensions.DependencyInjection;
using OntologyPlatform.Api.G2;

namespace OntologyPlatform.SecurityTests;

/// <summary>原生MCP/SSE传输复用安全边界时必须保持授权、防伪与原始响应媒体类型。</summary>
[TestClass]
public sealed class G2TransportTests
{
    /// <summary>传输没有业务Command也不能绕过身份、策略、来源及原生防伪。</summary>
    /// <param name="role">由服务器测试宿主固定的角色。</param>
    /// <param name="policy">共同具名策略。</param>
    /// <param name="csrf">是否验证POST防伪。</param>
    /// <param name="origin">明确的请求来源。</param>
    /// <param name="expected">应有原生状态。</param>
    /// <returns>真实原生结果执行验证任务。</returns>
    [TestMethod]
    [DataRow(null, "semantic.read", false, null, 401)]
    [DataRow("platform.viewer", "ontology.edit", false, null, 403)]
    [DataRow("platform.viewer", "semantic.read", false, null, 202)]
    [DataRow("platform.viewer", "semantic.read", true, "http://platform.test", 403)]
    [DataRow("platform.viewer", "semantic.read", true, "http://untrusted.invalid", 403)]
    [DataRow("platform.viewer", "semantic.read", true, "http://platform.test", 202)]
    public async Task NativeTransportPreservesBoundaryAndResult(string? role, string policy, bool csrf, string? origin, int expected)
    {
        // 复用原生Antiforgery与授权服务，身份仅由宿主夹具指定，非客户端头。
        await using var fixture = await G2HttpFixture.StartAsync(role);
        // 直接执行原生结果以避免传输编码或JSON包装掩盖状态。
        var context = new DefaultHttpContext { RequestServices = fixture.App.Services, User = G2HttpFixture.Principal(role) };
        context.Response.Body = new MemoryStream();
        context.Request.Scheme = "http";
        context.Request.Host = new HostString("platform.test");
        context.Request.Method = csrf ? "POST" : "GET";
        if (origin is not null)
        {
            context.Request.Headers.Origin = origin;
        }
        if (csrf && expected == 202)
        {
            // 在独立请求上下文生成真实cookie/token，再由被测请求原生验证。
            var issuance = new DefaultHttpContext { RequestServices = fixture.App.Services, User = G2HttpFixture.Principal(role) };
            issuance.Request.Scheme = "http";
            issuance.Request.Host = new HostString("platform.test");
            // 原生令牌只存在当前夹具内存，不写报告或浏览器状态文件。
            var tokens = fixture.App.Services.GetRequiredService<IAntiforgery>().GetAndStoreTokens(issuance);
            context.Request.Headers.Cookie = string.Join("; ", issuance.Response.Headers.SetCookie.Select(value => value!.Split(';', 2)[0]));
            context.Request.Headers["X-CSRF-TOKEN"] = tokens.RequestToken;
        }
        // 可观察计数保证拒绝时没有执行原生业务传输。
        var calls = 0;
        // 202与非JSON媒体类型能揭示错误的Results.Ok二次包装。
        var result = await G2EndpointGuard.TransportAsync(context, policy, (_, _) =>
        {
            calls++;
            return Task.FromResult<IResult>(Results.Text("Synthetic transport", "text/event-stream", statusCode: 202));
        }, csrf);
        await result.ExecuteAsync(context);
        Assert.AreEqual(expected, context.Response.StatusCode);
        Assert.AreEqual(expected == 202 ? 1 : 0, calls);
        if (expected == 202)
        {
            StringAssert.StartsWith(context.Response.ContentType!, "text/event-stream");
        }
    }
}
