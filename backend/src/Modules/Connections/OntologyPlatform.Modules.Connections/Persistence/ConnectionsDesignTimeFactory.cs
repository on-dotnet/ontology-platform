using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Design;

namespace OntologyPlatform.Modules.Connections;

/// <summary>设计期仅构造模型，不访问数据库或注入运行凭据。</summary>
public sealed class ConnectionsDesignTimeFactory : IDesignTimeDbContextFactory<ConnectionsDbContext>
{
    /// <summary>供已锁定EF工具生成独立schema迁移。</summary>
    public ConnectionsDbContext CreateDbContext(string[] args)
    {
        // 此无密码地址仅给模型生成器，运行Host必须显式配置独立平台数据库。
        var options = new DbContextOptionsBuilder<ConnectionsDbContext>().UseNpgsql("Host=localhost;Database=design_only", postgres => postgres.MigrationsHistoryTable("__EFMigrationsHistory", "connections"));
        return new ConnectionsDbContext(options.Options);
    }
}
