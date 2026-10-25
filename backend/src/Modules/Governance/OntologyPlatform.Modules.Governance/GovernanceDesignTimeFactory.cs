using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace OntologyPlatform.Modules.Governance;

/// <summary>供Master唯一迁移写入者创建模型，连接配置只从环境注入。</summary>
public sealed class GovernanceDesignTimeFactory : IDesignTimeDbContextFactory<GovernanceDbContext>
{
    /// <summary>构造不会自动连接数据库的设计时模块上下文。</summary>
    /// <param name="args">EF工具参数，本模块不解析秘密参数。</param>
    /// <returns>供生成迁移使用的上下文。</returns>
    public GovernanceDbContext CreateDbContext(string[] args)
    {
        // 设计时模型生成不需要真实密码；实际更新数据库必须显式提供隔离连接。
        var connection = Environment.GetEnvironmentVariable("ConnectionStrings__governance")
            ?? "Host=localhost;Database=governance_design;Username=design";
        // 采用与运行时一致的Npgsql模型，迁移历史也归属模块schema。
        var options = new DbContextOptionsBuilder<GovernanceDbContext>()
            .UseNpgsql(connection, database => database.MigrationsHistoryTable("__EFMigrationsHistory", "governance"))
            .Options;
        return new GovernanceDbContext(options);
    }
}
