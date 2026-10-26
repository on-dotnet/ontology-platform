using Microsoft.EntityFrameworkCore;

namespace OntologyPlatform.Modules.Publishing;

/// <summary>只写publishing schema，跨模块事务使用同一物理连接显式加入。</summary>
public sealed class PublishingDbContext : DbContext
{
    /// <summary>接收模块专属选项，不自行创建其他模块上下文。</summary>
    public PublishingDbContext(DbContextOptions<PublishingDbContext> options) : base(options)
    {
    }

    /// <summary>保存精确提案绑定与单次消费事实。</summary>
    public DbSet<ProposalRecord> Proposals => Set<ProposalRecord>();

    /// <summary>保存准备及正式版本的不可变字节绑定。</summary>
    public DbSet<ReleaseRecord> Releases => Set<ReleaseRecord>();

    /// <summary>资产唯一活动指针及防ABA修订。</summary>
    public DbSet<ActiveReleaseRecord> ActiveReleases => Set<ActiveReleaseRecord>();

    /// <summary>同完整范围及操作绑定的幂等预留和真实回执。</summary>
    public DbSet<PublishingCommandRecord> Commands => Set<PublishingCommandRecord>();

    /// <summary>持久保留每次发布或回滚的完整事实。</summary>
    public DbSet<ActivationRecord> Activations => Set<ActivationRecord>();

    /// <summary>激活事务内写入并由带fence租约的后台工作者调和。</summary>
    public DbSet<OutboxRecord> Outbox => Set<OutboxRecord>();

    /// <summary>事件消费者唯一去重回执，不参与活动指针切换。</summary>
    public DbSet<OutboxReceiptRecord> Receipts => Set<OutboxReceiptRecord>();

    /// <summary>固定唯一约束和CAS列；迁移由Master生成。</summary>
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.HasDefaultSchema("publishing");
        modelBuilder.Entity<ProposalRecord>(entity =>
        {
            entity.ToTable("Proposals");
            entity.HasKey(row => row.ProposalId);
            entity.Property(row => row.Revision).IsConcurrencyToken();
        });
        modelBuilder.Entity<ReleaseRecord>(entity =>
        {
            entity.ToTable("Releases");
            entity.HasKey(row => row.ReleaseId);
            entity.HasIndex(row => row.ProposalId).IsUnique();
            entity.HasOne<ProposalRecord>().WithMany().HasForeignKey(row => row.ProposalId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<ActiveReleaseRecord>(entity =>
        {
            entity.ToTable("ActiveReleases");
            entity.HasKey(row => row.AssetId);
            entity.Property(row => row.Revision).IsConcurrencyToken();
            entity.HasOne<ReleaseRecord>().WithMany().HasForeignKey(row => row.ReleaseId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<PublishingCommandRecord>(entity =>
        {
            entity.ToTable("Commands");
            entity.HasKey(row => row.Key);
        });
        modelBuilder.Entity<ActivationRecord>(entity =>
        {
            entity.ToTable("Activations");
            entity.HasKey(row => row.ActivationId);
            entity.HasIndex(row => new { row.AssetId, row.Revision }).IsUnique();
            entity.HasOne<ReleaseRecord>().WithMany().HasForeignKey(row => row.ReleaseId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<OutboxRecord>(entity =>
        {
            entity.ToTable("Outbox");
            entity.HasKey(row => row.EventId);
            entity.Property(row => row.FencingToken).IsConcurrencyToken();
            entity.HasIndex(row => new { row.DispatchedAtUtc, row.NextAttemptAtUtc });
            entity.HasOne<ReleaseRecord>().WithMany().HasForeignKey(row => row.ReleaseId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<OutboxReceiptRecord>(entity =>
        {
            entity.ToTable("Receipts");
            entity.HasKey(row => row.EventId);
            entity.HasOne<OutboxRecord>().WithMany().HasForeignKey(row => row.EventId).OnDelete(DeleteBehavior.Restrict);
        });
    }
}
