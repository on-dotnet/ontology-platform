using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace OntologyPlatform.Modules.Publishing;

/// <summary>只供Master生成迁移的设计时工厂，不隐式执行数据库更新。</summary>
public sealed class PublishingDesignTimeFactory : IDesignTimeDbContextFactory<PublishingDbContext>
{
    /// <summary>生成与实际运行同schema的模型，未配置时使用无凭证设计占位。</summary>
    public PublishingDbContext CreateDbContext(string[] args)
    {
        // 模型生成无需数据库认证材料；真实执行由测试隔离环境显式注入。
        var connection = Environment.GetEnvironmentVariable("ConnectionStrings__governance")
            ?? "Host=localhost;Database=publishing_design;Username=design";
        // 固定模块迁移历史表，避免与Ontology或Governance共用历史。
        var options = new DbContextOptionsBuilder<PublishingDbContext>()
            .UseNpgsql(connection, database => database.MigrationsHistoryTable("__EFMigrationsHistory", "publishing")).Options;
        return new PublishingDbContext(options);
    }
}
