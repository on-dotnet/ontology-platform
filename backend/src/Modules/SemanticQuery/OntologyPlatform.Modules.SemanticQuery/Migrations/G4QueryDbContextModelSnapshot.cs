using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;

namespace OntologyPlatform.Modules.SemanticQuery.Migrations;

/// <summary>首次查询迁移的冻结模型快照，后续模型变化必须新增迁移。</summary>
[DbContext(typeof(G4QueryDbContext))]
public sealed class G4QueryDbContextModelSnapshot : ModelSnapshot
{
    /// <summary>固定已迁移字段与索引，不借当前DbContext动态生成旧模型。</summary>
    protected override void BuildModel(ModelBuilder modelBuilder)
    {
        modelBuilder.HasDefaultSchema("semantic_query");
        modelBuilder.HasAnnotation("ProductVersion", "10.0.13").HasAnnotation("Relational:MaxIdentifierLength", 63);
        NpgsqlModelBuilderExtensions.UseIdentityByDefaultColumns(modelBuilder);
        modelBuilder.Entity("OntologyPlatform.Modules.SemanticQuery.G4QueryRecord", entity =>
        {
            entity.Property<string>("Id").IsRequired().HasMaxLength(128).HasColumnType("character varying(128)");
            entity.Property<string>("OrganizationId").IsRequired().HasMaxLength(128).HasColumnType("character varying(128)");
            entity.Property<string>("SubjectId").IsRequired().HasMaxLength(256).HasColumnType("character varying(256)");
            entity.Property<string>("SessionReference").IsRequired().HasMaxLength(64).HasColumnType("character varying(64)");
            entity.Property<string>("ConnectionId").IsRequired().HasMaxLength(128).HasColumnType("character varying(128)");
            entity.Property<string>("IdempotencyKey").IsRequired().HasMaxLength(128).HasColumnType("character varying(128)");
            entity.Property<string>("RequestHash").IsRequired().HasMaxLength(64).HasColumnType("character varying(64)");
            entity.Property<byte[]>("RequestBytes").IsRequired().HasColumnType("bytea");
            entity.Property<byte[]>("BindingBytes").IsRequired().HasColumnType("bytea");
            entity.Property<byte[]>("ResultCiphertext").IsRequired().HasColumnType("bytea");
            entity.Property<string?>("ResultHash").HasMaxLength(64).HasColumnType("character varying(64)");
            entity.Property<int>("ResultSize").HasColumnType("integer");
            entity.Property<string>("ExecutionStatus").IsRequired().HasMaxLength(16).HasColumnType("character varying(16)");
            entity.Property<string?>("ErrorCode").HasMaxLength(128).HasColumnType("character varying(128)");
            entity.Property<DateTimeOffset>("CreatedAtUtc").HasColumnType("timestamp with time zone");
            entity.Property<DateTimeOffset>("DeadlineAtUtc").HasColumnType("timestamp with time zone");
            entity.Property<DateTimeOffset>("ExpiresAtUtc").HasColumnType("timestamp with time zone");
            entity.Property<DateTimeOffset?>("CompletedAtUtc").HasColumnType("timestamp with time zone");
            entity.Property<DateTimeOffset?>("LeaseUntilUtc").HasColumnType("timestamp with time zone");
            entity.Property<string?>("LeaseOwner").HasMaxLength(128).HasColumnType("character varying(128)");
            entity.Property<long>("Fence").HasColumnType("bigint");
            entity.Property<bool>("CancelRequested").HasColumnType("boolean");
            entity.HasKey("Id");
            entity.HasIndex("OrganizationId", "SubjectId", "IdempotencyKey").IsUnique();
            entity.HasIndex("ExecutionStatus", "LeaseUntilUtc");
            entity.HasIndex("ExpiresAtUtc");
            entity.ToTable("Queries", "semantic_query");
        });
    }
}
