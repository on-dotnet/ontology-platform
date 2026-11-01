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

    /// <summary>固定每类记录的表、主键、并发令牌与恢复索引。</summary>
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.HasDefaultSchema("connections");
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
