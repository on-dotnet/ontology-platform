using Microsoft.EntityFrameworkCore;

namespace OntologyPlatform.Modules.Connections;

/// <summary>仅拥有connections schema，治理写入通过既有事务审计接口。</summary>
public sealed class ConnectionsDbContext : DbContext
{
    /// <summary>接收平台独立测试数据库的模块配置。</summary>
    public ConnectionsDbContext(DbContextOptions<ConnectionsDbContext> options) : base(options) { }

    /// <summary>ConnectionRecord集合，禁止跨模块写入。</summary>
    public DbSet<ConnectionRecord> Connections => Set<ConnectionRecord>();

    /// <summary>ConnectionSecretRecord集合，禁止跨模块写入。</summary>
    public DbSet<ConnectionSecretRecord> ConnectionSecrets => Set<ConnectionSecretRecord>();

    /// <summary>ConnectionProbeRecord集合，禁止跨模块写入。</summary>
    public DbSet<ConnectionProbeRecord> ConnectionProbes => Set<ConnectionProbeRecord>();

    /// <summary>CatalogJobRecord集合，禁止跨模块写入。</summary>
    public DbSet<CatalogJobRecord> CatalogJobs => Set<CatalogJobRecord>();

    /// <summary>CatalogSnapshotRecord集合，禁止跨模块写入。</summary>
    public DbSet<CatalogSnapshotRecord> CatalogSnapshots => Set<CatalogSnapshotRecord>();

    /// <summary>ConnectionCommandRecord集合，禁止跨模块写入。</summary>
    public DbSet<ConnectionCommandRecord> ConnectionCommands => Set<ConnectionCommandRecord>();

    /// <summary>永久映射与当前编辑头，锁定此行保护首次激活。</summary>
    public DbSet<MappingRecord> Mappings => Set<MappingRecord>();

    /// <summary>每次保存产生新修订，不覆盖历史映射定义。</summary>
    public DbSet<MappingRevisionRecord> MappingRevisions => Set<MappingRevisionRecord>();

    /// <summary>不可变七阶段受审报告，激活复核另存。</summary>
    public DbSet<MappingAssessmentRecord> MappingAssessments => Set<MappingAssessmentRecord>();

    /// <summary>提案固定受审目标与三方内部授权，状态通过CAS推进。</summary>
    public DbSet<MappingProposalRecord> MappingProposals => Set<MappingProposalRecord>();

    /// <summary>只追加的正式发布原字节；数据库拒绝UPDATE和DELETE。</summary>
    public DbSet<MappingReleaseRecord> MappingReleases => Set<MappingReleaseRecord>();

    /// <summary>当前正式发布指针，可用性不写入历史Manifest。</summary>
    public DbSet<MappingActiveRecord> MappingActives => Set<MappingActiveRecord>();

    /// <summary>激活或回滚的不可变当前绑定、审计和Outbox收据。</summary>
    public DbSet<MappingActivationRecord> MappingActivations => Set<MappingActivationRecord>();

    /// <summary>每次网络复核的不可变证明，失败和过期记录也保留。</summary>
    public DbSet<MappingActivationCheckRecord> MappingActivationChecks => Set<MappingActivationCheckRecord>();

    /// <summary>持久验证任务、租约及fence，旧工作者不得提交结果。</summary>
    public DbSet<MappingJobRecord> MappingJobs => Set<MappingJobRecord>();

    /// <summary>与Active、审计同事务写入的至少一次通知。</summary>
    public DbSet<MappingOutboxRecord> MappingOutboxs => Set<MappingOutboxRecord>();

    /// <summary>消费者按eventId唯一去重的持久收据。</summary>
    public DbSet<MappingOutboxReceiptRecord> MappingOutboxReceipts => Set<MappingOutboxReceiptRecord>();

    /// <summary>同主体、范围和操作幂等响应恢复，不跨主体泄漏。</summary>
    public DbSet<MappingCommandRecord> MappingCommands => Set<MappingCommandRecord>();

    /// <summary>治理通知消费者的单调版本，不提供M4执行入口。</summary>
    public DbSet<MappingNotificationRecord> MappingNotifications => Set<MappingNotificationRecord>();

    /// <summary>固定每类记录的表、主键、并发令牌与恢复索引。</summary>
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.HasDefaultSchema("connections");
        modelBuilder.Entity<MappingRecord>(entity =>
        {
            entity.ToTable("Mappings");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
            entity.Property(row => row.Revision).IsConcurrencyToken();
        });
        modelBuilder.Entity<MappingRevisionRecord>(entity =>
        {
            entity.ToTable("MappingRevisions");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
            entity.Property(row => row.Revision).IsConcurrencyToken();
            entity.Property(row => row.CanonicalBytes).HasColumnType("bytea");
            entity.HasIndex(row => new { row.MappingId, row.Revision }).IsUnique();
            entity.HasOne<MappingRecord>().WithMany().HasForeignKey(row => row.MappingId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<MappingAssessmentRecord>(entity =>
        {
            entity.ToTable("MappingAssessments");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
            entity.Property(row => row.CanonicalBytes).HasColumnType("bytea");
            entity.HasOne<MappingRecord>().WithMany().HasForeignKey(row => row.MappingId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<MappingProposalRecord>(entity =>
        {
            entity.ToTable("MappingProposals");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
            entity.Property(row => row.Revision).IsConcurrencyToken();
            entity.HasOne<MappingRecord>().WithMany().HasForeignKey(row => row.MappingId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<MappingReleaseRecord>(entity =>
        {
            entity.ToTable("MappingReleases");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
            entity.Property(row => row.CanonicalBytes).HasColumnType("bytea");
            entity.HasOne<MappingRecord>().WithMany().HasForeignKey(row => row.MappingId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<MappingActiveRecord>(entity =>
        {
            entity.ToTable("MappingActives");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
            entity.Property(row => row.ActivationRevision).IsConcurrencyToken();
            entity.HasIndex(row => row.MappingId).IsUnique();
            entity.HasOne<MappingRecord>().WithMany().HasForeignKey(row => row.MappingId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<MappingActivationRecord>(entity =>
        {
            entity.ToTable("MappingActivations");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
            entity.Property(row => row.CanonicalBytes).HasColumnType("bytea");
            entity.HasIndex(row => row.ProposalId).IsUnique();
            entity.HasOne<MappingRecord>().WithMany().HasForeignKey(row => row.MappingId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<MappingActivationCheckRecord>(entity =>
        {
            entity.ToTable("MappingActivationChecks");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
            entity.Property(row => row.CanonicalBytes).HasColumnType("bytea");
            entity.HasOne<MappingRecord>().WithMany().HasForeignKey(row => row.MappingId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<MappingJobRecord>(entity =>
        {
            entity.ToTable("MappingJobs");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
            entity.Property(row => row.Revision).IsConcurrencyToken();
            entity.Property(row => row.Fence).IsConcurrencyToken();
            entity.HasIndex(row => new { row.Status, row.LeaseUntil });
            entity.HasOne<MappingRecord>().WithMany().HasForeignKey(row => row.MappingId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<MappingOutboxRecord>(entity =>
        {
            entity.ToTable("MappingOutboxs");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
            entity.HasOne<MappingRecord>().WithMany().HasForeignKey(row => row.MappingId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<MappingOutboxReceiptRecord>(entity =>
        {
            entity.ToTable("MappingOutboxReceipts");
            entity.HasKey(row => row.Id);
            entity.HasOne<MappingRecord>().WithMany().HasForeignKey(row => row.MappingId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<MappingNotificationRecord>(entity =>
        {
            entity.ToTable("MappingNotifications");
            entity.HasKey(row => row.MappingId);
            entity.Property(row => row.ActivationRevision).IsConcurrencyToken();
            entity.HasOne<MappingRecord>().WithMany().HasForeignKey(row => row.MappingId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<MappingCommandRecord>(entity =>
        {
            entity.ToTable("MappingCommands");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
            entity.HasIndex(row => new { row.OrganizationId, row.MappingId, row.Operation, row.IdempotencyKey }).IsUnique();
            entity.HasIndex(row => new { row.OrganizationId, row.CommandId }).IsUnique();
            entity.HasOne<MappingRecord>().WithMany().HasForeignKey(row => row.MappingId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<ConnectionRecord>(entity =>
        {
            entity.ToTable("Connections");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
            entity.Property(row => row.Revision).IsConcurrencyToken();
        });
        modelBuilder.Entity<ConnectionSecretRecord>(entity =>
        {
            entity.ToTable("ConnectionSecrets");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
            entity.Property(row => row.UsedAtUtc).IsConcurrencyToken();
        });
        modelBuilder.Entity<ConnectionProbeRecord>(entity =>
        {
            entity.ToTable("ConnectionProbes");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
        });
        modelBuilder.Entity<CatalogJobRecord>(entity =>
        {
            entity.ToTable("CatalogJobs");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
            entity.Property(row => row.Fence).IsConcurrencyToken();
            entity.HasIndex(row => new { row.Status, row.LeaseUntil });
        });
        modelBuilder.Entity<CatalogSnapshotRecord>(entity =>
        {
            entity.ToTable("CatalogSnapshots");
            entity.HasKey(row => row.Id);
            entity.HasIndex(row => new { row.OrganizationId, row.Id });
        });
        modelBuilder.Entity<ConnectionCommandRecord>(entity =>
        {
            entity.ToTable("ConnectionCommands");
            entity.HasKey(row => row.Id);
        });
    }
}
