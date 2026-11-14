using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

namespace OntologyPlatform.Modules.SemanticQuery.Migrations;

/// <summary>查询独占持久表，显式迁移不修改G2 Run或其他模块表。</summary>
[DbContext(typeof(G4QueryDbContext))]
[Migration("20261114000000_G4QueryPersistence")]
public sealed partial class G4QueryPersistence : Migration
{
    /// <summary>建立查询记录、主体幂等及租约回收索引。</summary>
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.EnsureSchema("semantic_query");
        migrationBuilder.Sql("""
            CREATE TABLE semantic_query."Queries" (
                "Id" character varying(128) NOT NULL PRIMARY KEY,
                "OrganizationId" character varying(128) NOT NULL,
                "SubjectId" character varying(256) NOT NULL,
                "SessionReference" character varying(64) NOT NULL,
                "ConnectionId" character varying(128) NOT NULL,
                "IdempotencyKey" character varying(128) NOT NULL,
                "RequestHash" character varying(64) NOT NULL,
                "RequestBytes" bytea NOT NULL,
                "BindingBytes" bytea NOT NULL,
                "ResultCiphertext" bytea NOT NULL,
                "ResultHash" character varying(64) NULL,
                "ResultSize" integer NOT NULL,
                "ExecutionStatus" character varying(16) NOT NULL,
                "ErrorCode" character varying(128) NULL,
                "CreatedAtUtc" timestamp with time zone NOT NULL,
                "DeadlineAtUtc" timestamp with time zone NOT NULL,
                "ExpiresAtUtc" timestamp with time zone NOT NULL,
                "CompletedAtUtc" timestamp with time zone NULL,
                "LeaseUntilUtc" timestamp with time zone NULL,
                "LeaseOwner" character varying(128) NULL,
                "Fence" bigint NOT NULL,
                "CancelRequested" boolean NOT NULL
            );
            CREATE UNIQUE INDEX "IX_Queries_OrganizationId_SubjectId_IdempotencyKey"
                ON semantic_query."Queries" ("OrganizationId", "SubjectId", "IdempotencyKey");
            CREATE INDEX "IX_Queries_ExecutionStatus_LeaseUntilUtc"
                ON semantic_query."Queries" ("ExecutionStatus", "LeaseUntilUtc");
            CREATE INDEX "IX_Queries_ExpiresAtUtc" ON semantic_query."Queries" ("ExpiresAtUtc");
            """);
    }

    /// <summary>仅撤销本模块新表，不删除共享数据库或其他schema。</summary>
    protected override void Down(MigrationBuilder migrationBuilder) => migrationBuilder.DropTable("Queries", "semantic_query");
}
