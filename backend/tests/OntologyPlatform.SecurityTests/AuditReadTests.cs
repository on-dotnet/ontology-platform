using System.Net;
using System.Net.Http.Json;
using System.Security.Claims;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Builder;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Options;
using Microsoft.VisualStudio.TestTools.UnitTesting;
using OntologyPlatform.Api.Contracts;
using OntologyPlatform.Api.Security;
using OntologyPlatform.Modules.Governance;

namespace OntologyPlatform.SecurityTests;

/// <summary>用真实Kestrel、PG票据和审计表验证敏感读取事实、完整范围及写入失败关闭。</summary>
[TestClass]
public sealed class AuditReadTests
{
    /// <summary>每次成功读取恰好提交一个事件，本次结果不含自身，重复及并发也不递归。</summary>
    /// <returns>真实HTTP与PG事实验证任务。</returns>
    [TestMethod]
    public async Task SuccessfulRepeatedAndConcurrentReadsCommitExactlyOnceWithoutSelf()
    {
        // 每个测试独占随机主体及组织，不能读取其他测试数据。
        await using var fixture = await AuditReadFixture.CreateAsync(["site-b", "site-a", "site-b", "", " "]);
        // 第一条返回之前必须已经存在成功审计事实。
        var firstId = await fixture.ReadAndAssertAsync();
        // 查询成功事实必须按Ordinal保留完整可信集合，且多厂兼容字段为空。
        var first = await fixture.Database.AuditRecords.AsNoTracking().SingleAsync(value => value.Id == firstId);
        CollectionAssert.AreEqual(new[] { "site-a", "site-b" }, first.ScopeSiteIds);
        Assert.IsNull(first.SiteId);
        // 下一条可见已提交的上一次查询，不能包含自己的事件。
        var secondId = await fixture.ReadAndAssertAsync(firstId);
        Assert.AreNotEqual(firstId, secondId);
        // 四个并发请求独立持有请求级DbContext；不要求全局串行快照。
        var ids = await Task.WhenAll(Enumerable.Range(0, 4).Select(_ => fixture.ReadAndAssertAsync()));
        Assert.AreEqual(4, ids.Distinct(StringComparer.Ordinal).Count());
        Assert.AreEqual(6, await fixture.Database.AuditRecords.CountAsync(value => value.Actor == fixture.Subject && value.Action == "platform.audit.read"));
        // 登录也必须通过统一Create保留完整范围，而非任意首厂。
        var login = await fixture.Database.AuditRecords.AsNoTracking().SingleAsync(value => value.Actor == fixture.Subject && value.Action == "authentication.login");
        CollectionAssert.AreEqual(new[] { "site-a", "site-b" }, login.ScopeSiteIds);
        Assert.IsNull(login.SiteId);
    }

    /// <summary>不同可信厂区仅能看见完整子集，不能由旧SiteId泄露跨厂及历史未知行。</summary>
    /// <param name="scope">当前单厂或双厂授权。</param>
    /// <param name="expected">允许出现的合成事件标记。</param>
    /// <returns>数据库范围过滤验证任务。</returns>
    [TestMethod]
    [DataRow("site-a", "A")]
    [DataRow("site-b", "B")]
    [DataRow("site-a,site-b", "A,B,AB")]
    public async Task ScopeFilterRequiresNonemptyOrganizationAndCompleteArraySubset(string scope, string expected)
    {
        // 可信claims故意按调用用例定义，期望值由独立合成数据显式给出。
        await using var fixture = await AuditReadFixture.CreateAsync(scope.Split(','));
        fixture.Database.AuditRecords.AddRange(
            fixture.Row("A", ["site-a"]), fixture.Row("B", ["site-b"]), fixture.Row("AB", ["site-a", "site-b"]),
            fixture.Row("other-org", ["site-a"], fixture.Organization + "-other"), fixture.Row("null-org", ["site-a"], null, true),
            fixture.Row("empty-org", ["site-a"], ""), fixture.Row("legacy", null), fixture.Row("empty", []));
        await fixture.Database.SaveChangesAsync();
        // 正式端点必须在SQL层限制范围，不以调用方过滤替代权限。
        using var response = await fixture.Client.GetAsync("/api/v1/platform/audit?limit=100");
        Assert.AreEqual(HttpStatusCode.OK, response.StatusCode);
        // 只筛选测试标记以区分合法登录与读取审计，保留真实API完整结果。
        var rows = (await response.Content.ReadFromJsonAsync<PlatformAuditEntry[]>())!;
        CollectionAssert.AreEquivalent(expected.Split(','), rows.Where(value => value.Action == "synthetic.scope").Select(value => value.Resource).ToArray());
        Assert.IsTrue(rows.All(value => value.ScopeSiteIds is { Length: > 0 }));
    }

    /// <summary>没有匹配行或没有有效组织厂区仍提交敏感读取事实，空范围不可产生全局可见性。</summary>
    /// <param name="organizationMode">正常、缺失或空白组织。</param>
    /// <param name="hasSites">是否签发有效厂区。</param>
    /// <returns>空结果与空范围事实验证任务。</returns>
    [TestMethod]
    [DataRow("valid", true)]
    [DataRow("valid", false)]
    [DataRow("missing", true)]
    [DataRow("empty", true)]
    [DataRow("blank", true)]
    public async Task EmptyResultsAndMissingScopesStillCommitReadFact(string organizationMode, bool hasSites)
    {
        // 隔离身份的组织缺失必须与合法组织明确区分。
        await using var fixture = await AuditReadFixture.CreateAsync(hasSites ? ["site-a"] : [], organizationMode: organizationMode);
        await fixture.Database.AuditRecords.Where(value => value.Actor == fixture.Subject).ExecuteDeleteAsync();
        // 插入未知或空范围行，确保空结果不是因为表天然无数据。
        fixture.Database.AuditRecords.Add(fixture.Row("hidden-empty", []));
        if (organizationMode != "valid")
        {
            fixture.Database.AuditRecords.Add(fixture.Row("hidden-org", ["site-a"]));
        }
        await fixture.Database.SaveChangesAsync();
        // 空列表也必须先持久化事件才返回200。
        using var response = await fixture.Client.GetAsync("/api/v1/platform/audit");
        Assert.AreEqual(HttpStatusCode.OK, response.StatusCode);
        Assert.AreEqual(0, (await response.Content.ReadFromJsonAsync<PlatformAuditEntry[]>())!.Length);
        Assert.IsTrue(response.Headers.Contains("X-Audit-Id"));
        // 审计事实保留实际可信范围；没有厂区时写[]而非历史未知null。
        var row = await fixture.Database.AuditRecords.AsNoTracking().SingleAsync(value => value.Actor == fixture.Subject && value.Action == "platform.audit.read");
        CollectionAssert.AreEqual(hasSites ? new[] { "site-a" } : Array.Empty<string>(), row.ScopeSiteIds);
        Assert.AreEqual(hasSites ? "site-a" : null, row.SiteId);
    }

    /// <summary>权限拒绝保存denied事实，PG会话过期则401且不生成成功读取事件。</summary>
    /// <returns>真实身份负例验证任务。</returns>
    [TestMethod]
    public async Task DeniedRoleAndExpiredSessionNeverProduceSuccessfulRead()
    {
        // 无审计员角色但拥有厂区的可信身份必须被拒绝。
        await using var fixture = await AuditReadFixture.CreateAsync(["site-a"], auditor: false);
        // 第一次请求验证403并持久化拒绝事实。
        using var denied = await fixture.Client.GetAsync("/api/v1/platform/audit");
        Assert.AreEqual(HttpStatusCode.Forbidden, denied.StatusCode);
        Assert.AreEqual(1, await fixture.Database.AuditRecords.CountAsync(value => value.Actor == fixture.Subject && value.Action == "authorization.denied" && value.Outcome == "denied"));
        await fixture.Database.Sessions.Where(value => value.Id == fixture.SessionKey)
            .ExecuteUpdateAsync(update => update.SetProperty(value => value.ExpiresAtUtc, DateTimeOffset.UtcNow.AddMinutes(-1)));
        // 相同Cookie仍可解密，但真实PG行过期使认证失败。
        using var expired = await fixture.Client.GetAsync("/api/v1/platform/audit");
        Assert.AreEqual(HttpStatusCode.Unauthorized, expired.StatusCode);
        Assert.IsFalse(expired.Headers.Contains("X-Audit-Id"));
        Assert.AreEqual(0, await fixture.Database.AuditRecords.CountAsync(value => value.Actor == fixture.Subject && value.Action == "platform.audit.read"));
    }

    /// <summary>限制条数在权限过滤之后应用，非法limit不产生成功读取。</summary>
    /// <returns>实际SQL排序及输入验证任务。</returns>
    [TestMethod]
    public async Task LimitAppliesAfterScopeFilterAndInvalidLimitDoesNotAuditSuccess()
    {
        // 当前主体只有A厂，最新的B厂记录不能占据允许结果条数。
        await using var fixture = await AuditReadFixture.CreateAsync(["site-a"]);
        // 未来合成时间仅用于稳定排序，未修改系统时钟。
        var allowed = fixture.Row("older-A", ["site-a"]);
        allowed.OccurredAtUtc = DateTimeOffset.UtcNow.AddMinutes(1);
        // 更新但无权限的AB不能通过兼容SiteId泄漏或提前Take。
        var hidden = fixture.Row("newer-AB", ["site-a", "site-b"]);
        hidden.OccurredAtUtc = DateTimeOffset.UtcNow.AddMinutes(2);
        fixture.Database.AuditRecords.AddRange(allowed, hidden);
        await fixture.Database.SaveChangesAsync();
        // Take(1)必须发生在授权过滤之后。
        using var response = await fixture.Client.GetAsync("/api/v1/platform/audit?limit=1");
        Assert.AreEqual(HttpStatusCode.OK, response.StatusCode);
        // 显式比较独立种子ID，避免复制生产过滤算法作期望值。
        var rows = (await response.Content.ReadFromJsonAsync<PlatformAuditEntry[]>())!;
        Assert.AreEqual(1, rows.Length);
        Assert.AreEqual(allowed.Id, rows[0].Id);
        // 分别覆盖零、超过上限、负数及非数字输入。
        foreach (var limit in new[] { "0", "101", "-1", "invalid" })
        {
            // 每个非法值都走正式校验分支且不额外写入成功事实。
            using var invalid = await fixture.Client.GetAsync("/api/v1/platform/audit?limit=" + limit);
            Assert.AreEqual(HttpStatusCode.BadRequest, invalid.StatusCode);
        }
        Assert.AreEqual(1, await fixture.Database.AuditRecords.CountAsync(value => value.Actor == fixture.Subject && value.Action == "platform.audit.read"));
    }

    /// <summary>仅审计INSERT被PG触发器拒绝时读取失败关闭，撤销故障后恢复正常。</summary>
    /// <returns>真实PG写入故障及恢复验证任务。</returns>
    [TestMethod]
    public async Task InsertOnlyFailureNeverReturnsSuccessOrAuditIdAndRecovers()
    {
        // 独立主体、连接和函数名避免影响并行测试或真实开发数据。
        await using var fixture = await AuditReadFixture.CreateAsync(["site-a"]);
        // 先验证正常认证和查询提交，失败不能由无效会话或SELECT中断冒充。
        await fixture.ReadAndAssertAsync();
        // 名称只由GUID十六进制生成，不含任何请求输入或凭证。
        var trigger = "audit_fail_" + Guid.NewGuid().ToString("N");
        // DDL标识符不能参数化，仅允许本测试固定前缀和随机十六进制；主体同样受严格白名单约束。
        StringAssert.Matches(trigger, new System.Text.RegularExpressions.Regex("^audit_fail_[0-9a-f]{32}$"));
        StringAssert.Matches(fixture.Subject, new System.Text.RegularExpressions.Regex("^audit-[0-9a-f]{32}$"));
#pragma warning disable EF1002 // 上面已验证所有插值，DDL不接受请求输入或凭证。
        await fixture.Database.Database.ExecuteSqlRawAsync($"CREATE FUNCTION governance.{trigger}() RETURNS trigger LANGUAGE plpgsql AS $f$ BEGIN IF NEW.\"Actor\" = '{fixture.Subject}' AND NEW.\"Action\" = 'platform.audit.read' THEN RAISE EXCEPTION 'synthetic-insert-rejection'; END IF; RETURN NEW; END $f$; CREATE TRIGGER {trigger} BEFORE INSERT ON governance.audit_records FOR EACH ROW EXECUTE FUNCTION governance.{trigger}();");
#pragma warning restore EF1002
        try
        {
            // 故障期间SELECT正常，真实Cookie仍能读取服务端票据。
            Assert.IsTrue(await fixture.Database.AuditRecords.AnyAsync(value => value.Actor == fixture.Subject));
            // 正式me端点确认故障仅作用于审计INSERT而非认证票据读取。
            using var identity = await fixture.Client.GetAsync("/api/v1/platform/me");
            Assert.AreEqual(HttpStatusCode.OK, identity.StatusCode);
            // INSERT异常不能返回200或先行暴露成功ID。
            using var failed = await fixture.Client.GetAsync("/api/v1/platform/audit");
            Assert.AreEqual(HttpStatusCode.ServiceUnavailable, failed.StatusCode);
            Assert.IsFalse(failed.Headers.Contains("X-Audit-Id"));
            Assert.IsFalse((await failed.Content.ReadAsStringAsync()).Contains("synthetic-insert-rejection", StringComparison.Ordinal));
            Assert.AreEqual(1, await fixture.Database.AuditRecords.CountAsync(value => value.Actor == fixture.Subject && value.Action == "platform.audit.read"));
        }
        finally
        {
#pragma warning disable EF1002 // 沿用已验证且仅本测试生成的DDL标识符。
            await fixture.Database.Database.ExecuteSqlRawAsync($"DROP TRIGGER IF EXISTS {trigger} ON governance.audit_records; DROP FUNCTION IF EXISTS governance.{trigger}();");
#pragma warning restore EF1002
        }
        await fixture.ReadAndAssertAsync();
        Assert.AreEqual(2, await fixture.Database.AuditRecords.CountAsync(value => value.Actor == fixture.Subject && value.Action == "platform.audit.read"));
    }

    /// <summary>资源读取沿用统一审计构造器，完整claims与已授权显式厂区分别保留正确范围。</summary>
    /// <returns>资源读取及跨厂拒绝回归任务。</returns>
    [TestMethod]
    public async Task ResourceReadAuditsTrustedFullScopeOrAuthorizedExplicitSite()
    {
        // 同时拥有资源viewer及审计员，使用乱序重复claims验证归一化。
        await using var fixture = await AuditReadFixture.CreateAsync(["site-b", "site-a", "site-a"]);
        // 不指定厂区时即使结果为空也必须记录完整可信查询范围。
        using var all = await fixture.Client.GetAsync("/api/v1/platform/resources");
        Assert.AreEqual(HttpStatusCode.OK, all.StatusCode);
        // 无显式筛选时记录全部授权范围而非首厂。
        var allRow = await fixture.Database.AuditRecords.AsNoTracking().SingleAsync(value => value.Id == all.Headers.GetValues("X-Audit-Id").Single());
        CollectionAssert.AreEqual(new[] { "site-a", "site-b" }, allRow.ScopeSiteIds);
        Assert.IsNull(allRow.SiteId);
        // 已授权显式厂区仅记录该次实际选择范围。
        using var selected = await fixture.Client.GetAsync("/api/v1/platform/resources?siteId=site-b");
        Assert.AreEqual(HttpStatusCode.OK, selected.StatusCode);
        // 读取持久事实而非仅信任HTTP头中的ID。
        var selectedRow = await fixture.Database.AuditRecords.AsNoTracking().SingleAsync(value => value.Id == selected.Headers.GetValues("X-Audit-Id").Single());
        CollectionAssert.AreEqual(new[] { "site-b" }, selectedRow.ScopeSiteIds);
        Assert.AreEqual("site-b", selectedRow.SiteId);
        // 未获授权厂区仍由原行级检查拒绝。
        using var denied = await fixture.Client.GetAsync("/api/v1/platform/resources?siteId=site-c");
        Assert.AreEqual(HttpStatusCode.Forbidden, denied.StatusCode);
    }
}

/// <summary>审计测试专用真实宿主与随机PG主体，生命周期清理仅限本测试拥有的数据。</summary>
internal sealed class AuditReadFixture : IAsyncDisposable
{
    /// <summary>当前测试的证书与keyring所有者。</summary>
    private readonly SecurityHostFixture host = new();

    /// <summary>当前测试真实Kestrel宿主。</summary>
    private WebApplication app = null!;

    /// <summary>当前测试唯一合成主体。</summary>
    public string Subject { get; } = "audit-" + Guid.NewGuid().ToString("N");

    /// <summary>本测试可信组织，缺失或空白用于权限负例。</summary>
    public string? Organization { get; private set; }

    /// <summary>本测试唯一服务器票据引用，仅内存使用。</summary>
    public string SessionKey { get; private set; } = string.Empty;

    /// <summary>本测试真实模块上下文。</summary>
    public GovernanceDbContext Database { get; private set; } = null!;

    /// <summary>持有受保护引用Cookie的真实HTTP客户端。</summary>
    public HttpClient Client { get; private set; } = null!;

    /// <summary>创建真实PG票据和HTTP客户端，不使用认证替身或开发栈私有配置。</summary>
    /// <param name="sites">本用例的可信厂区声明。</param>
    /// <param name="auditor">是否具备审计员角色。</param>
    /// <param name="organizationMode">组织正常或缺失的负例模式。</param>
    /// <returns>调用方必须异步释放的隔离夹具。</returns>
    public static async Task<AuditReadFixture> CreateAsync(string[] sites, bool auditor = true, string organizationMode = "valid")
    {
        // 本轮专用PG由受控脚本注入，缺前提明确NOT_RUN。
        var connection = Environment.GetEnvironmentVariable("G1_SEC_PG_CONNECTION");
        if (string.IsNullOrWhiteSpace(connection))
        {
            Assert.Inconclusive("NOT_RUN: 未注入本轮隔离PG连接。");
        }
        // 所有资源归本夹具，初始化失败也应释放。
        var fixture = new AuditReadFixture();
        try
        {
            fixture.Organization = organizationMode switch { "missing" => null, "empty" => "", "blank" => " ", _ => "org-" + Guid.NewGuid().ToString("N") };
            fixture.app = fixture.host.Create(connection: connection);
            await fixture.app.StartAsync();
            fixture.Database = await fixture.app.Services.GetRequiredService<IDbContextFactory<GovernanceDbContext>>().CreateDbContextAsync();
            // 最小合成可信票据只隔离权限测试，不冒充真实OIDC登录验收。
            var claims = new List<Claim> { new("sub", fixture.Subject), new(ClaimTypes.Role, "platform.viewer") };
            if (fixture.Organization is not null)
            {
                claims.Add(new Claim("organization_id", fixture.Organization));
            }
            claims.AddRange(sites.Select(site => new Claim("site_ids", site)));
            if (auditor)
            {
                claims.Add(new Claim(ClaimTypes.Role, "platform.auditor"));
            }
            // 使用真实加密PG存储器创建会话及原子登录事件。
            var properties = new AuthenticationProperties { ExpiresUtc = DateTimeOffset.UtcNow.AddMinutes(10) };
            properties.StoreTokens([new AuthenticationToken { Name = "id_token", Value = "synthetic-audit-secret-marker" }]);
            fixture.SessionKey = await fixture.app.Services.GetRequiredService<PostgresTicketStore>().StoreAsync(new AuthenticationTicket(
                new ClaimsPrincipal(new ClaimsIdentity(claims, "synthetic-audit-test")), properties, CookieAuthenticationDefaults.AuthenticationScheme));
            // Cookie仅保存框架标准的受保护服务器引用。
            var options = fixture.app.Services.GetRequiredService<IOptionsMonitor<CookieAuthenticationOptions>>().Get(CookieAuthenticationDefaults.AuthenticationScheme);
            // 标准会话引用声明由框架Cookie处理器解析，不携带真实身份内容。
            var reference = new ClaimsPrincipal(new ClaimsIdentity([new Claim("Microsoft.AspNetCore.Authentication.Cookies-SessionId", fixture.SessionKey)], CookieAuthenticationDefaults.AuthenticationScheme));
            // 加密结果仅留在进程内，任何断言或证据都不输出Cookie。
            var cookie = options.TicketDataFormat.Protect(new AuthenticationTicket(reference, properties, CookieAuthenticationDefaults.AuthenticationScheme));
            fixture.Client = fixture.host.CreateClient(fixture.app);
            fixture.Client.DefaultRequestHeaders.Add("Cookie", options.Cookie.Name + "=" + cookie);
            return fixture;
        }
        catch
        {
            await fixture.DisposeAsync();
            throw;
        }
    }

    /// <summary>构造仅本测试拥有的审计行，故意保留旧首厂模拟历史误归。</summary>
    /// <param name="resource">独立可断言的合成标记。</param>
    /// <param name="sites">真实结构化范围，null表示旧未知行。</param>
    /// <param name="organization">可选组织覆盖。</param>
    /// <param name="nullOrganization">强制组织缺失的负例。</param>
    /// <returns>未提交的本测试审计行。</returns>
    public AuditRecord Row(string resource, string[]? sites, string? organization = null, bool nullOrganization = false)
    {
        return new AuditRecord
        {
            Actor = Subject,
            OrganizationId = nullOrganization ? null : organization ?? Organization,
            ScopeSiteIds = sites,
            SiteId = "site-a",
            Action = "synthetic.scope",
            Resource = resource,
            Outcome = "allowed",
            TraceId = Guid.NewGuid().ToString("N"),
            CorrelationId = Guid.NewGuid().ToString("N")
        };
    }

    /// <summary>验证一次真实读取的已提交唯一事实、Trace、安全正文和时序。</summary>
    /// <param name="previousId">应在后续请求可见的上一事件。</param>
    /// <returns>当前已经提交的事件ID。</returns>
    public async Task<string> ReadAndAssertAsync(string? previousId = null)
    {
        // 每个调用独立响应，允许同一客户端并发访问。
        using var response = await Client.GetAsync("/api/v1/platform/audit?limit=100");
        Assert.AreEqual(HttpStatusCode.OK, response.StatusCode);
        Assert.IsTrue(response.Headers.Contains("X-Audit-Id"), "成功查询必须先提交审计并返回关联ID。");
        // 已提交ID只能由服务端产生，正文不能包含本次刚写事件。
        var id = response.Headers.GetValues("X-Audit-Id").Single();
        // 正文只用于敏感标记负例，禁止把服务器票据复制进响应。
        var body = await response.Content.ReadAsStringAsync();
        Assert.IsFalse(body.Contains("synthetic-audit-secret-marker", StringComparison.Ordinal));
        // 物化的公开事件列表用于验证本次不含自身与后续可见性。
        var rows = (await response.Content.ReadFromJsonAsync<PlatformAuditEntry[]>())!;
        Assert.IsFalse(rows.Any(value => value.Id == id));
        if (previousId is not null)
        {
            Assert.IsTrue(rows.Any(value => value.Id == previousId));
        }
        // 每次使用独立DbContext，不能让测试本身并发共享追踪上下文。
        await using var database = await app.Services.GetRequiredService<IDbContextFactory<GovernanceDbContext>>().CreateDbContextAsync();
        // 响应返回时必须已经能从独立PG上下文查询到唯一事实。
        var row = await database.AuditRecords.AsNoTracking().SingleAsync(value => value.Id == id);
        Assert.AreEqual(Subject, row.Actor);
        Assert.AreEqual("platform.audit.read", row.Action);
        Assert.AreEqual("platform.audit", row.Resource);
        Assert.AreEqual("allowed", row.Outcome);
        Assert.AreEqual(Organization, row.OrganizationId);
        StringAssert.Matches(row.TraceId, new System.Text.RegularExpressions.Regex("^[0-9a-f]{32}$"));
        Assert.AreEqual(response.Headers.GetValues("X-Trace-Id").Single(), row.TraceId);
        Assert.AreEqual(response.Headers.GetValues("X-Correlation-Id").Single(), row.CorrelationId);
        Assert.IsTrue(row.OccurredAtUtc <= DateTimeOffset.UtcNow);
        return id;
    }

    /// <summary>删除本测试的随机主体事实及票据，停止宿主并释放临时证书。</summary>
    /// <returns>受限清理完成任务。</returns>
    public async ValueTask DisposeAsync()
    {
        Client?.Dispose();
        if (Database is not null)
        {
            await Database.Sessions.Where(value => value.Id == SessionKey).ExecuteDeleteAsync();
            await Database.AuditRecords.Where(value => value.Actor == Subject).ExecuteDeleteAsync();
            await Database.DisposeAsync();
        }
        if (app is not null)
        {
            await app.DisposeAsync();
        }
        host.Dispose();
    }
}
