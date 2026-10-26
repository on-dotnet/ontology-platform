using Microsoft.EntityFrameworkCore;

namespace OntologyPlatform.Modules.Agents;

/// <summary>独占agents持久运行、事件与回执，迁移由Master生成。</summary>
public sealed class AgentsDbContext : DbContext
{
    /// <summary>接收同数据库但独立schema的模块配置。</summary>
    public AgentsDbContext(DbContextOptions<AgentsDbContext> options) : base(options)
    {
    }

    /// <summary>受原子租约保护的运行。</summary>
    public DbSet<RunRecord> Runs => Set<RunRecord>();

    /// <summary>只在提交之后才可发送的有序事件。</summary>
    public DbSet<RunEventRecord> Events => Set<RunEventRecord>();

    /// <summary>完整请求散列绑定的幂等回执。</summary>
    public DbSet<RunCommandRecord> Commands => Set<RunCommandRecord>();

    /// <summary>固定主键、事件唯一性、外键及并发令牌。</summary>
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.HasDefaultSchema("agents");
        modelBuilder.Entity<RunRecord>(entity =>
        {
            entity.ToTable("Runs");
            entity.HasKey(row => row.RunId);
            entity.Property(row => row.FencingToken).IsConcurrencyToken();
            entity.Property(row => row.LastSeq).IsConcurrencyToken();
            entity.HasIndex(row => new { row.Status, row.LeaseUntil });
            entity.HasIndex(row => new { row.OwnerSubjectId, row.OrganizationId });
        });
        modelBuilder.Entity<RunEventRecord>(entity =>
        {
            entity.ToTable("Events");
            entity.HasKey(row => new { row.RunId, row.Seq });
            entity.HasIndex(row => row.EventId).IsUnique();
            entity.HasOne<RunRecord>().WithMany().HasForeignKey(row => row.RunId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<RunCommandRecord>(entity =>
        {
            entity.ToTable("Commands");
            entity.HasKey(row => row.Key);
            entity.HasOne<RunRecord>().WithMany().HasForeignKey(row => row.RunId).OnDelete(DeleteBehavior.Restrict);
        });
    }
}
