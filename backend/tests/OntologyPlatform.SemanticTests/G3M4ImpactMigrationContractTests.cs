using Microsoft.EntityFrameworkCore.Migrations.Operations;
using OntologyPlatform.Modules.Ontology.Migrations;

namespace OntologyPlatform.SemanticTests;

/// <summary>Master公共持久化合同只增加自身表和唯一输入，数据库降级不能删历史报告。</summary>
[TestClass]
public sealed class G3M4ImpactMigrationContractTests
{
    /// <summary>只检查真实迁移操作，不将模型存在当数据库应用成功。</summary>
    [TestMethod]
    public void ImpactMigrationCreatesOwnedTableAndRefusesDestructiveDown()
    {
        // 实际生成迁移的操作树无需连接数据库即可核对准确schema与唯一性。
        var migration = new G3M4ImpactReports();
        // 正向只创建本模块自身影响报告表。
        var table = migration.UpOperations.OfType<CreateTableOperation>().Single();
        Assert.AreEqual("ontology", table.Schema);
        Assert.AreEqual("ImpactReports", table.Name);
        Assert.IsTrue(migration.UpOperations.OfType<CreateIndexOperation>().Any(index => index.Name == "IX_ImpactReports_InputFingerprint" && index.IsUnique));
        Assert.Throws<NotSupportedException>(() => _ = migration.DownOperations);
    }
}
