using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace OntologyPlatform.Modules.Agents;

/// <summary>向Master提供真实迁移模型，不自行建表或读取凭证。</summary>
public sealed class AgentsDesignTimeFactory : IDesignTimeDbContextFactory<AgentsDbContext>
{
    /// <summary>构造无需真实连接的模型上下文。</summary>
    public AgentsDbContext CreateDbContext(string[] args)
    {
        // 生成模型可使用无凭证占位；更新数据库只接受调用者显式注入的隔离配置。
        var connection = Environment.GetEnvironmentVariable("ConnectionStrings__governance")
            ?? "Host=localhost;Database=agents_design;Username=design";
        // 真实迁移与运行时保持同一独立schema。
        var options = new DbContextOptionsBuilder<AgentsDbContext>()
            .UseNpgsql(connection, database => database.MigrationsHistoryTable("__EFMigrationsHistory", "agents"))
            .Options;
        return new AgentsDbContext(options);
    }
}
