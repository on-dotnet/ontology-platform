using Microsoft.EntityFrameworkCore;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>查询结果只写自己的semantic_query schema，不访问其他模块写表。</summary>
public sealed class G4QueryDbContext : DbContext
{
    /// <summary>正式DI工厂传入同一平台PG的模块配置。</summary>
    public G4QueryDbContext(DbContextOptions<G4QueryDbContext> options) : base(options) { }

    /// <summary>当前执行、幂等与结果恢复记录。</summary>
    public DbSet<G4QueryRecord> Queries => Set<G4QueryRecord>();

    /// <summary>模块自己的显式模型映射与并发索引。</summary>
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.HasDefaultSchema("semantic_query");
        modelBuilder.Entity<G4QueryRecord>(entity =>
        {
            entity.ToTable("Queries");
            entity.HasKey(value => value.Id);
            entity.Property(value => value.Id).HasMaxLength(128);
            entity.Property(value => value.OrganizationId).HasMaxLength(128);
            entity.Property(value => value.SubjectId).HasMaxLength(256);
            entity.Property(value => value.SessionReference).HasMaxLength(64);
            entity.Property(value => value.ConnectionId).HasMaxLength(128);
            entity.Property(value => value.IdempotencyKey).HasMaxLength(128);
            entity.Property(value => value.RequestHash).HasMaxLength(64);
            entity.Property(value => value.ResultHash).HasMaxLength(64);
            entity.Property(value => value.ExecutionStatus).HasMaxLength(16);
            entity.Property(value => value.ErrorCode).HasMaxLength(128);
            entity.Property(value => value.LeaseOwner).HasMaxLength(128);
            entity.HasIndex(value => new { value.OrganizationId, value.SubjectId, value.IdempotencyKey }).IsUnique();
            entity.HasIndex(value => new { value.ExecutionStatus, value.LeaseUntilUtc });
            entity.HasIndex(value => value.ExpiresAtUtc);
        });
    }
}
