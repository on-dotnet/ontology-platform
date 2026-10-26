using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace OntologyPlatform.Modules.Publishing.Migrations;

/// <inheritdoc />
public partial class InitialPublishing : Migration
{
    /// <inheritdoc />
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.EnsureSchema(
            name: "publishing");

        migrationBuilder.CreateTable(
            name: "Commands",
            schema: "publishing",
            columns: table => new
            {
                Key = table.Column<string>(type: "text", nullable: false),
                PayloadHash = table.Column<string>(type: "text", nullable: false),
                SubjectId = table.Column<string>(type: "text", nullable: false),
                ReleaseId = table.Column<string>(type: "text", nullable: true),
                ResultJson = table.Column<string>(type: "text", nullable: true)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_Commands", x => x.Key);
            });

        migrationBuilder.CreateTable(
            name: "Proposals",
            schema: "publishing",
            columns: table => new
            {
                ProposalId = table.Column<string>(type: "text", nullable: false),
                AssetId = table.Column<string>(type: "text", nullable: false),
                OrganizationId = table.Column<string>(type: "text", nullable: false),
                SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                ProposalJson = table.Column<string>(type: "text", nullable: false),
                Revision = table.Column<long>(type: "bigint", nullable: false),
                Activated = table.Column<bool>(type: "boolean", nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_Proposals", x => x.ProposalId);
            });

        migrationBuilder.CreateTable(
            name: "Releases",
            schema: "publishing",
            columns: table => new
            {
                ReleaseId = table.Column<string>(type: "text", nullable: false),
                ProposalId = table.Column<string>(type: "text", nullable: false),
                AssetId = table.Column<string>(type: "text", nullable: false),
                OrganizationId = table.Column<string>(type: "text", nullable: false),
                SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                ManifestJson = table.Column<string>(type: "text", nullable: false),
                ManifestHash = table.Column<string>(type: "text", nullable: false),
                ManifestObjectJson = table.Column<string>(type: "text", nullable: false),
                SourcesJson = table.Column<string>(type: "text", nullable: false),
                State = table.Column<string>(type: "text", nullable: false),
                Published = table.Column<bool>(type: "boolean", nullable: false),
                TraceId = table.Column<string>(type: "text", nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_Releases", x => x.ReleaseId);
                table.ForeignKey(
                    name: "FK_Releases_Proposals_ProposalId",
                    column: x => x.ProposalId,
                    principalSchema: "publishing",
                    principalTable: "Proposals",
                    principalColumn: "ProposalId",
                    onDelete: ReferentialAction.Restrict);
            });

        migrationBuilder.CreateTable(
            name: "Activations",
            schema: "publishing",
            columns: table => new
            {
                ActivationId = table.Column<string>(type: "text", nullable: false),
                AssetId = table.Column<string>(type: "text", nullable: false),
                Revision = table.Column<long>(type: "bigint", nullable: false),
                ReleaseId = table.Column<string>(type: "text", nullable: false),
                ResultJson = table.Column<string>(type: "text", nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_Activations", x => x.ActivationId);
                table.ForeignKey(
                    name: "FK_Activations_Releases_ReleaseId",
                    column: x => x.ReleaseId,
                    principalSchema: "publishing",
                    principalTable: "Releases",
                    principalColumn: "ReleaseId",
                    onDelete: ReferentialAction.Restrict);
            });

        migrationBuilder.CreateTable(
            name: "ActiveReleases",
            schema: "publishing",
            columns: table => new
            {
                AssetId = table.Column<string>(type: "text", nullable: false),
                OrganizationId = table.Column<string>(type: "text", nullable: false),
                SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                ReleaseId = table.Column<string>(type: "text", nullable: false),
                Revision = table.Column<long>(type: "bigint", nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_ActiveReleases", x => x.AssetId);
                table.ForeignKey(
                    name: "FK_ActiveReleases_Releases_ReleaseId",
                    column: x => x.ReleaseId,
                    principalSchema: "publishing",
                    principalTable: "Releases",
                    principalColumn: "ReleaseId",
                    onDelete: ReferentialAction.Restrict);
            });

        migrationBuilder.CreateTable(
            name: "Outbox",
            schema: "publishing",
            columns: table => new
            {
                EventId = table.Column<string>(type: "text", nullable: false),
                ReleaseId = table.Column<string>(type: "text", nullable: false),
                ActivationRevision = table.Column<long>(type: "bigint", nullable: false),
                EventType = table.Column<string>(type: "text", nullable: false),
                PayloadHash = table.Column<string>(type: "text", nullable: false),
                CreatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                Attempts = table.Column<int>(type: "integer", nullable: false),
                NextAttemptAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                DispatchedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                LeaseOwner = table.Column<string>(type: "text", nullable: true),
                LeaseUntilUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                FencingToken = table.Column<long>(type: "bigint", nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_Outbox", x => x.EventId);
                table.ForeignKey(
                    name: "FK_Outbox_Releases_ReleaseId",
                    column: x => x.ReleaseId,
                    principalSchema: "publishing",
                    principalTable: "Releases",
                    principalColumn: "ReleaseId",
                    onDelete: ReferentialAction.Restrict);
            });

        migrationBuilder.CreateTable(
            name: "Receipts",
            schema: "publishing",
            columns: table => new
            {
                EventId = table.Column<string>(type: "text", nullable: false),
                ReleaseId = table.Column<string>(type: "text", nullable: false),
                ManifestHash = table.Column<string>(type: "text", nullable: false),
                VerifiedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_Receipts", x => x.EventId);
                table.ForeignKey(
                    name: "FK_Receipts_Outbox_EventId",
                    column: x => x.EventId,
                    principalSchema: "publishing",
                    principalTable: "Outbox",
                    principalColumn: "EventId",
                    onDelete: ReferentialAction.Restrict);
            });

        migrationBuilder.CreateIndex(
            name: "IX_Activations_AssetId_Revision",
            schema: "publishing",
            table: "Activations",
            columns: new[] { "AssetId", "Revision" },
            unique: true);

        migrationBuilder.CreateIndex(
            name: "IX_Activations_ReleaseId",
            schema: "publishing",
            table: "Activations",
            column: "ReleaseId");

        migrationBuilder.CreateIndex(
            name: "IX_ActiveReleases_ReleaseId",
            schema: "publishing",
            table: "ActiveReleases",
            column: "ReleaseId");

        migrationBuilder.CreateIndex(
            name: "IX_Outbox_DispatchedAtUtc_NextAttemptAtUtc",
            schema: "publishing",
            table: "Outbox",
            columns: new[] { "DispatchedAtUtc", "NextAttemptAtUtc" });

        migrationBuilder.CreateIndex(
            name: "IX_Outbox_ReleaseId",
            schema: "publishing",
            table: "Outbox",
            column: "ReleaseId");

        migrationBuilder.CreateIndex(
            name: "IX_Releases_ProposalId",
            schema: "publishing",
            table: "Releases",
            column: "ProposalId",
            unique: true);
    }

    /// <inheritdoc />
    protected override void Down(MigrationBuilder migrationBuilder)
    {
        // 仅空开发库可回退；立即排他锁拒绝并发写入，保留发布、审批和投递历史。
        migrationBuilder.Sql("LOCK TABLE publishing.\"Commands\", publishing.\"Proposals\", publishing.\"Releases\", publishing.\"Activations\", publishing.\"ActiveReleases\", publishing.\"Outbox\", publishing.\"Receipts\" IN ACCESS EXCLUSIVE MODE NOWAIT;");
        migrationBuilder.Sql("DO $$ BEGIN IF EXISTS (SELECT 1 FROM publishing.\"Commands\") OR EXISTS (SELECT 1 FROM publishing.\"Proposals\") OR EXISTS (SELECT 1 FROM publishing.\"Releases\") OR EXISTS (SELECT 1 FROM publishing.\"Activations\") OR EXISTS (SELECT 1 FROM publishing.\"ActiveReleases\") OR EXISTS (SELECT 1 FROM publishing.\"Outbox\") OR EXISTS (SELECT 1 FROM publishing.\"Receipts\") THEN RAISE EXCEPTION 'Publishing history exists; use forward repair.'; END IF; END $$;");

        migrationBuilder.DropTable(
            name: "Activations",
            schema: "publishing");

        migrationBuilder.DropTable(
            name: "ActiveReleases",
            schema: "publishing");

        migrationBuilder.DropTable(
            name: "Commands",
            schema: "publishing");

        migrationBuilder.DropTable(
            name: "Receipts",
            schema: "publishing");

        migrationBuilder.DropTable(
            name: "Outbox",
            schema: "publishing");

        migrationBuilder.DropTable(
            name: "Releases",
            schema: "publishing");

        migrationBuilder.DropTable(
            name: "Proposals",
            schema: "publishing");
    }
}
