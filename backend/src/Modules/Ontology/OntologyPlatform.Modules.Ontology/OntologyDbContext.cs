using Microsoft.EntityFrameworkCore;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>只拥有ontology表及明确事务的模块上下文。</summary>
public sealed class OntologyDbContext : DbContext
{
    /// <summary>接收宿主或发布事务提供的显式连接选项。</summary>
    /// <param name="options">本模块数据库选项。</param>
    public OntologyDbContext(DbContextOptions<OntologyDbContext> options) : base(options)
    {
    }

    /// <summary>当前草稿CAS头。</summary>
    public DbSet<DraftRecord> Drafts => Set<DraftRecord>();

    /// <summary>不可变源码修订历史。</summary>
    public DbSet<DraftRevisionRecord> Revisions => Set<DraftRevisionRecord>();

    /// <summary>绑定修订的真实校验事实。</summary>
    public DbSet<ValidationRecord> Validations => Set<ValidationRecord>();

    /// <summary>与报告同事务产生的不可变评估。</summary>
    public DbSet<AssessmentRecord> Assessments => Set<AssessmentRecord>();

    /// <summary>与业务和审计同时提交的幂等回执。</summary>
    public DbSet<CommandRecord> Commands => Set<CommandRecord>();

    /// <summary>声明专属schema、唯一键、外键与CAS列。</summary>
    /// <param name="modelBuilder">EF模型构建器。</param>
    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.HasDefaultSchema("ontology");
        modelBuilder.Entity<DraftRecord>(entity =>
        {
            entity.ToTable("Drafts");
            entity.HasKey(row => row.DraftId);
            entity.Property(row => row.Revision).IsConcurrencyToken();
            entity.HasIndex(row => new { row.OrganizationId, row.AssetId });
        });
        modelBuilder.Entity<DraftRevisionRecord>(entity =>
        {
            entity.ToTable("Revisions");
            entity.HasKey(row => new { row.DraftId, row.Revision });
            entity.HasOne<DraftRecord>().WithMany().HasForeignKey(row => row.DraftId).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<ValidationRecord>(entity =>
        {
            entity.ToTable("Validations");
            entity.HasKey(row => row.ReportId);
            entity.HasOne<DraftRevisionRecord>().WithMany().HasForeignKey(row => new { row.DraftId, row.Revision }).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<AssessmentRecord>(entity =>
        {
            entity.ToTable("Assessments");
            entity.HasKey(row => row.AssessmentId);
            entity.HasIndex(row => row.ValidationReportId).IsUnique();
            entity.HasOne<ValidationRecord>().WithOne().HasForeignKey<AssessmentRecord>(row => row.ValidationReportId).OnDelete(DeleteBehavior.Restrict);
            entity.HasOne<DraftRevisionRecord>().WithMany().HasForeignKey(row => new { row.DraftId, row.Revision }).OnDelete(DeleteBehavior.Restrict);
        });
        modelBuilder.Entity<CommandRecord>(entity =>
        {
            entity.ToTable("Commands");
            entity.HasKey(row => row.Key);
        });
    }
}
