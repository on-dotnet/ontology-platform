using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

namespace OntologyPlatform.Modules.SemanticQuery.Migrations;

/// <summary>为已批准的G4 Run引用增加独占表；不改已应用迁移或旧Agents模型。</summary>
[DbContext(typeof(G4QueryDbContext))]
[Migration("20261114010000_G4QueryRunReferences")]
public sealed class G4QueryRunReferences : Migration
{
    /// <summary>服务器运行只保留主体、会话摘要、预算与查询引用。</summary>
    protected override void Up(MigrationBuilder migrationBuilder) => migrationBuilder.Sql("""
        CREATE TABLE semantic_query."QueryRuns" (
            "Id" varchar(128) PRIMARY KEY,
            "OrganizationId" varchar(128) NOT NULL,
            "SubjectId" varchar(256) NOT NULL,
            "SessionReference" varchar(64) NOT NULL,
            "CreatedAtUtc" timestamptz NOT NULL,
            "DeadlineAtUtc" timestamptz NOT NULL,
            "ToolCalls" integer NOT NULL CHECK ("ToolCalls" BETWEEN 1 AND 3),
            "QueryIds" text[] NOT NULL DEFAULT '{}',
            CHECK (cardinality("QueryIds") <= "ToolCalls")
        );
        CREATE INDEX "IX_QueryRuns_CreatedAtUtc" ON semantic_query."QueryRuns" ("CreatedAtUtc");
        """);

    /// <summary>只撤销本迁移拥有的G4引用表。</summary>
    protected override void Down(MigrationBuilder migrationBuilder) => migrationBuilder.DropTable("QueryRuns", "semantic_query");
}
