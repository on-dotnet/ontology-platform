using Microsoft.EntityFrameworkCore;

namespace OntologyPlatform.Modules.Governance;

/// <summary>仅管理Governance拥有的会话、审计和合成开发资源。</summary>
public sealed class GovernanceDbContext : DbContext
{
    /// <summary>以调用方提供的专属数据库配置创建模块上下文。</summary>
    /// <param name="options">只用于Governance的数据库选项。</param>
    public GovernanceDbContext(DbContextOptions<GovernanceDbContext> options) : base(options)
    {
    }

    /// <summary>加密服务器会话及其固定失效、撤销状态。</summary>
    public DbSet<ServerSession> Sessions => Set<ServerSession>();

    /// <summary>已经提交的安全审计事实。</summary>
    public DbSet<AuditRecord> AuditRecords => Set<AuditRecord>();

    /// <summary>显式开发初始化的合成平台资源。</summary>
    public DbSet<SyntheticResource> Resources => Set<SyntheticResource>();

    /// <summary>冻结模块schema、长度及查询索引，不触碰其他模块。</summary>
    /// <param name="modelBuilder">EF模型构建器。</param>
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.HasDefaultSchema("governance");
        modelBuilder.Entity<ServerSession>(entity =>
        {
            entity.ToTable("server_sessions");
            entity.HasKey(value => value.Id);
            entity.Property(value => value.Id).HasMaxLength(64);
            entity.Property(value => value.ProtectedTicket).IsRequired();
            entity.HasIndex(value => value.ExpiresAtUtc);
        });
        modelBuilder.Entity<AuditRecord>(entity =>
        {
            entity.ToTable("audit_records");
            entity.HasKey(value => value.Id);
            entity.Property(value => value.Id).HasMaxLength(32);
            entity.Property(value => value.Actor).HasMaxLength(256);
            entity.Property(value => value.Action).HasMaxLength(64);
            entity.Property(value => value.Resource).HasMaxLength(256);
            entity.Property(value => value.Outcome).HasMaxLength(32);
            entity.Property(value => value.TraceId).HasMaxLength(64);
            entity.Property(value => value.CorrelationId).HasMaxLength(64);
            entity.Property(value => value.OrganizationId).HasMaxLength(128);
            entity.Property(value => value.SiteId).HasMaxLength(128);
            entity.HasIndex(value => new { value.OrganizationId, value.SiteId, value.OccurredAtUtc });
        });
        modelBuilder.Entity<SyntheticResource>(entity =>
        {
            entity.ToTable("synthetic_resources");
            entity.HasKey(value => value.Id);
            entity.Property(value => value.Id).HasMaxLength(128);
            entity.Property(value => value.Name).HasMaxLength(256);
            entity.Property(value => value.OrganizationId).HasMaxLength(128);
            entity.Property(value => value.SiteId).HasMaxLength(128);
            entity.Property(value => value.Status).HasMaxLength(64);
            entity.HasIndex(value => new { value.OrganizationId, value.SiteId });
        });
    }
}
