using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace OntologyPlatform.Modules.Agents.Migrations
{
    /// <inheritdoc />
    public partial class InitialAgents : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.EnsureSchema(
                name: "agents");

            migrationBuilder.CreateTable(
                name: "Runs",
                schema: "agents",
                columns: table => new
                {
                    RunId = table.Column<string>(type: "text", nullable: false),
                    OwnerSubjectId = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    SnapshotJson = table.Column<string>(type: "text", nullable: false),
                    ActorJson = table.Column<string>(type: "text", nullable: false),
                    PlanJson = table.Column<string>(type: "text", nullable: false),
                    SourcePrompt = table.Column<string>(type: "text", nullable: false),
                    Status = table.Column<string>(type: "text", nullable: false),
                    ProviderMode = table.Column<string>(type: "text", nullable: false),
                    CreatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    UpdatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    DeadlineUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    LastSeq = table.Column<long>(type: "bigint", nullable: false),
                    CancelRequested = table.Column<bool>(type: "boolean", nullable: false),
                    LeaseOwner = table.Column<string>(type: "text", nullable: true),
                    LeaseUntil = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    FencingToken = table.Column<long>(type: "bigint", nullable: false),
                    ToolCalls = table.Column<int>(type: "integer", nullable: false),
                    TraceId = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Runs", x => x.RunId);
                });

            migrationBuilder.CreateTable(
                name: "Commands",
                schema: "agents",
                columns: table => new
                {
                    Key = table.Column<string>(type: "text", nullable: false),
                    PayloadHash = table.Column<string>(type: "text", nullable: false),
                    RunId = table.Column<string>(type: "text", nullable: false),
                    ReceiptJson = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Commands", x => x.Key);
                    table.ForeignKey(
                        name: "FK_Commands_Runs_RunId",
                        column: x => x.RunId,
                        principalSchema: "agents",
                        principalTable: "Runs",
                        principalColumn: "RunId",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "Events",
                schema: "agents",
                columns: table => new
                {
                    RunId = table.Column<string>(type: "text", nullable: false),
                    Seq = table.Column<long>(type: "bigint", nullable: false),
                    EventId = table.Column<string>(type: "text", nullable: false),
                    EnvelopeJson = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Events", x => new { x.RunId, x.Seq });
                    table.ForeignKey(
                        name: "FK_Events_Runs_RunId",
                        column: x => x.RunId,
                        principalSchema: "agents",
                        principalTable: "Runs",
                        principalColumn: "RunId",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateIndex(
                name: "IX_Commands_RunId",
                schema: "agents",
                table: "Commands",
                column: "RunId");

            migrationBuilder.CreateIndex(
                name: "IX_Events_EventId",
                schema: "agents",
                table: "Events",
                column: "EventId",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Runs_OwnerSubjectId_OrganizationId",
                schema: "agents",
                table: "Runs",
                columns: new[] { "OwnerSubjectId", "OrganizationId" });

            migrationBuilder.CreateIndex(
                name: "IX_Runs_Status_LeaseUntil",
                schema: "agents",
                table: "Runs",
                columns: new[] { "Status", "LeaseUntil" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            // 仅空开发库可回退；立即排他锁保护持久运行、事件和幂等历史。
            migrationBuilder.Sql("LOCK TABLE agents.\"Runs\", agents.\"Events\", agents.\"Commands\" IN ACCESS EXCLUSIVE MODE NOWAIT;");
            migrationBuilder.Sql("DO $$ BEGIN IF EXISTS (SELECT 1 FROM agents.\"Runs\") OR EXISTS (SELECT 1 FROM agents.\"Events\") OR EXISTS (SELECT 1 FROM agents.\"Commands\") THEN RAISE EXCEPTION 'Execution history exists; use forward repair.'; END IF; END $$;");

            migrationBuilder.DropTable(
                name: "Commands",
                schema: "agents");

            migrationBuilder.DropTable(
                name: "Events",
                schema: "agents");

            migrationBuilder.DropTable(
                name: "Runs",
                schema: "agents");
        }
    }
}
