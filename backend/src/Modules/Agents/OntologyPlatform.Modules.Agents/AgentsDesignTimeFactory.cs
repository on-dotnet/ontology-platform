using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace OntologyPlatform.Modules.Agents;

/// <summary>向Master提供真实迁移模型，不自行建表或读取凭证。</summary>
public sealed class AgentsDesignTimeFactory : IDesignTimeDbContextFactory<AgentsDbContext>
{
    /// <summary>构造无需真实连接的模型上下文。</summary>
    public AgentsDbContext CreateDbContext(string[] args)
    {
        // 设计时只生成模型，不访问任何现有数据库。
        var options = new DbContextOptionsBuilder<AgentsDbContext>()
            .UseNpgsql("Host=localhost;Database=agents_design;Username=design", database => database.MigrationsHistoryTable("__EFMigrationsHistory", "agents"))
            .Options;
        return new AgentsDbContext(options);
    }
}
