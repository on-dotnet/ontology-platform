using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Modules.Agents;

namespace OntologyPlatform.AgentTests;

/// <summary>真实迁移是持久Run验收前提，不能用EnsureCreated代替。</summary>
[TestClass]
public sealed class PersistenceTests
{
    /// <summary>没有Master提交的真实迁移时明确失败。</summary>
    [TestMethod]
    public void AgentsHaveRealMigration()
    {
        // 工厂只构建模型，不连接真实数据库。
        using var database = new AgentsDesignTimeFactory().CreateDbContext([]);
        Assert.IsTrue(database.Database.GetMigrations().Any(), "Agents真实迁移缺失");
    }
}
