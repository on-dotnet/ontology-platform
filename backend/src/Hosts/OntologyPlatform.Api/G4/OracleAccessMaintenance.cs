using System.Data.Common;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Npgsql;
using OntologyPlatform.Modules.Governance;
using OntologyPlatform.Modules.SemanticQuery;

namespace OntologyPlatform.Api.G4;

/// <summary>已封闭任务栈的单次进程入口。只构造两个模块的数据库工厂，不创建 Web 宿主或后台消费者。</summary>
internal static class OracleAccessMaintenance
{
    /// <summary>从私有运行环境取独立维护执行器生成的身份锚点，缺一即拒绝。</summary>
    private static string Trusted(string name) => Environment.GetEnvironmentVariable("OMQ_S23_MAINTENANCE_" + name)
        ?? throw new InvalidOperationException("oracle_maintenance_environment_missing");

    /// <summary>读取并验证私有 stdin 原件，执行成功后只输出操作身份与提交包络。</summary>
    internal static async Task RunAsync(bool generationClosure = false)
    {
        using var limit = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        try
        {
            // 只读取固定上限加一字节，以便拒绝任意长度或未结束的输入流。
            var bytes = new byte[65537];
            using var input = Console.OpenStandardInput();
            // 真实执行器关闭 stdin 后，最后一个字节也参与指纹。
            var count = await input.ReadAtLeastAsync(bytes, bytes.Length, false, limit.Token);
            // 独立核验器提供同一准确封闭原件与新鲜源证明的散列。
            var proof = generationClosure
                ? G4OracleAccessMaintenanceProof.ReadGeneration(bytes[..count], Trusted("PROOF_SHA256"), Trusted("OPERATOR"), Trusted("SEAL_SHA256"), Trusted("TERMINATION_SHA256"))
                : G4OracleAccessMaintenanceProof.Read(bytes[..count], Trusted("PROOF_SHA256"), Trusted("OPERATOR"), Trusted("SEAL_SHA256"), Trusted("TERMINATION_SHA256"));
            // 凭据只在限权进程内使用。引擎 inspect 及命令行不得含连接口令。
            var path = Trusted("DSN_FILE");
            if (!OperatingSystem.IsLinux()) throw new PlatformNotSupportedException("维护进程仅在准确 Linux 验证器中运行。");
            // 核 Linux 进程的实际及有效 UID；不凭环境字符串合成维护操作者。
            var uid = (await File.ReadAllLinesAsync("/proc/self/status", limit.Token)).Single(line => line.StartsWith("Uid:", StringComparison.Ordinal))
                .Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
            G4OracleAccessMaintenanceProof.Check(uid.Length == 5 && proof["operatorId"] == "os-uid-" + uid[1] && uid[2] == uid[1]);
            G4OracleAccessMaintenanceProof.Check(Path.IsPathFullyQualified(path) && File.Exists(path) && new FileInfo(path).LinkTarget is null
                && (File.GetUnixFileMode(path) & (UnixFileMode.GroupRead | UnixFileMode.GroupWrite | UnixFileMode.GroupExecute
                    | UnixFileMode.OtherRead | UnixFileMode.OtherWrite | UnixFileMode.OtherExecute)) == 0);
            // 验证专属网络端点、TLS 证书、数据库和时限，仅创建必要的连接池外连接。
            var settings = new NpgsqlConnectionStringBuilder((await File.ReadAllTextAsync(path, limit.Token)).Trim())
            { Pooling = false, Timeout = 5, CommandTimeout = 5, IncludeErrorDetail = false };
            G4OracleAccessMaintenanceProof.Check(settings.Host == "platform-pg" && settings.Port == 5432 && settings.Database == "mapping"
                && settings.Username == proof["databaseUser"] && settings.SslMode == SslMode.VerifyFull && !string.IsNullOrWhiteSpace(settings.RootCertificate));
            // 维护宿主不注册业务授权、发布、Oracle 连接器、监听端口或 HostedService。
            var services = new ServiceCollection();
            services.AddDbContextFactory<G4QueryDbContext>(options => options.UseNpgsql(settings.ConnectionString));
            services.AddDbContextFactory<GovernanceDbContext>(options => options.UseNpgsql(settings.ConnectionString));
            await using var provider = services.BuildServiceProvider();
            // 审计写入使用正式治理实现，重读也必须加入同一事务。
            var governance = provider.GetRequiredService<IDbContextFactory<GovernanceDbContext>>();
            await using var database = await provider.GetRequiredService<IDbContextFactory<G4QueryDbContext>>().CreateDbContextAsync(limit.Token);
            // 外侧区间覆盖真正提交；精确命令以及提交后新连接强后验仍由独立工具保存。
            var lower = DateTimeOffset.UtcNow;
            // 只处理该私有证明固定的一行。
            var status = await G4OracleAccessMaintenance.RecoverAsync(database, new TransactionalAuditWriter(governance), proof,
                (connection, transaction, token) => ReadAuditAsync(governance, connection, transaction, token, proof["queryId"]), limit.Token);
            Console.WriteLine(JsonSerializer.Serialize(new { status, operationId = proof["operationId"], lowerUtc = lower, upperUtc = DateTimeOffset.UtcNow }));
        }
        catch
        {
            Console.Error.WriteLine("oracle_access_maintenance_rejected");
            Environment.ExitCode = 1;
        }
    }

    /// <summary>通过治理上下文读取准确 query 的本次失败与恢复的全部审计，含 UTF8 jsonb 原行摘要。</summary>
    internal static async Task<JsonElement> ReadAuditAsync(IDbContextFactory<GovernanceDbContext> factory,
        DbConnection connection, DbTransaction transaction, CancellationToken token, string queryId = G4OracleAccessMaintenanceProof.QueryId)
    {
        await using var governance = await factory.CreateDbContextAsync(token);
        governance.Database.SetDbConnection(connection, contextOwnsConnection: false);
        await governance.Database.UseTransactionAsync(transaction, token);
        // 精确资源限定在 SQL 内，不输出其他主体历史或原始审计内容。
        var json = await governance.Database.SqlQuery<string>($"""
            SELECT COALESCE(json_agg(json_build_object('id',a."Id",'action',a."Action",'outcome',a."Outcome",
                'actor',a."Actor",'trace',a."TraceId",'correlation',a."CorrelationId",'organization',a."OrganizationId",
                'sites',a."ScopeSiteIds",'sha256',encode(sha256(convert_to(to_jsonb(a)::text,'UTF8')),'hex')) ORDER BY a."Id"),'[]')::text AS "Value"
            FROM governance.audit_records a WHERE a."Resource"={queryId}
            """).SingleAsync(token);
        return JsonSerializer.Deserialize<JsonElement>(json);
    }
}
