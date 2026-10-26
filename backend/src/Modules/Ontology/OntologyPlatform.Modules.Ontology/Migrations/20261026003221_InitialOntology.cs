using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace OntologyPlatform.Modules.Ontology.Migrations;

/// <inheritdoc />
public partial class InitialOntology : Migration
{
    /// <inheritdoc />
    protected override void Up(MigrationBuilder migrationBuilder)
    {
        migrationBuilder.EnsureSchema(
            name: "ontology");

        migrationBuilder.CreateTable(
            name: "Commands",
            schema: "ontology",
            columns: table => new
            {
                Key = table.Column<string>(type: "text", nullable: false),
                PayloadHash = table.Column<string>(type: "text", nullable: false),
                SubjectId = table.Column<string>(type: "text", nullable: false),
                ResultJson = table.Column<string>(type: "text", nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_Commands", x => x.Key);
            });

        migrationBuilder.CreateTable(
            name: "Drafts",
            schema: "ontology",
            columns: table => new
            {
                DraftId = table.Column<string>(type: "text", nullable: false),
                AssetId = table.Column<string>(type: "text", nullable: false),
                OrganizationId = table.Column<string>(type: "text", nullable: false),
                SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                BaseReleaseId = table.Column<string>(type: "text", nullable: true),
                Revision = table.Column<long>(type: "bigint", nullable: false),
                Name = table.Column<string>(type: "text", nullable: false),
                OwnerSubjectId = table.Column<string>(type: "text", nullable: false),
                UpdatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_Drafts", x => x.DraftId);
            });

        migrationBuilder.CreateTable(
            name: "Revisions",
            schema: "ontology",
            columns: table => new
            {
                DraftId = table.Column<string>(type: "text", nullable: false),
                Revision = table.Column<long>(type: "bigint", nullable: false),
                SourcesJson = table.Column<string>(type: "text", nullable: false),
                HashesJson = table.Column<string>(type: "text", nullable: false),
                ProjectionJson = table.Column<string>(type: "text", nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_Revisions", x => new { x.DraftId, x.Revision });
                table.ForeignKey(
                    name: "FK_Revisions_Drafts_DraftId",
                    column: x => x.DraftId,
                    principalSchema: "ontology",
                    principalTable: "Drafts",
                    principalColumn: "DraftId",
                    onDelete: ReferentialAction.Restrict);
            });

        migrationBuilder.CreateTable(
            name: "Validations",
            schema: "ontology",
            columns: table => new
            {
                ReportId = table.Column<string>(type: "text", nullable: false),
                DraftId = table.Column<string>(type: "text", nullable: false),
                Revision = table.Column<long>(type: "bigint", nullable: false),
                BundleHash = table.Column<string>(type: "text", nullable: false),
                Conforms = table.Column<bool>(type: "boolean", nullable: false),
                ReportJson = table.Column<string>(type: "text", nullable: false)
            },
            constraints: table =>
            {
                table.PrimaryKey("PK_Validations", x => x.ReportId);
                table.ForeignKey(
                    name: "FK_Validations_Revisions_DraftId_Revision",
                    columns: x => new { x.DraftId, x.Revision },
                    principalSchema: "ontology",
                    principalTable: "Revisions",
                    principalColumns: new[] { "DraftId", "Revision" },
                    onDelete: ReferentialAction.Restrict);
            });

        migrationBuilder.CreateIndex(
            name: "IX_Drafts_OrganizationId_AssetId",
            schema: "ontology",
            table: "Drafts",
            columns: new[] { "OrganizationId", "AssetId" });

        migrationBuilder.CreateIndex(
            name: "IX_Validations_DraftId_Revision",
            schema: "ontology",
            table: "Validations",
            columns: new[] { "DraftId", "Revision" });
    }

    /// <inheritdoc />
    protected override void Down(MigrationBuilder migrationBuilder)
    {
        // 只允许空开发库回退；NOWAIT避免与活跃业务形成等待环，拒绝并发或既有事实丢失。
        migrationBuilder.Sql("LOCK TABLE ontology.\"Drafts\", ontology.\"Revisions\", ontology.\"Validations\", ontology.\"Commands\" IN ACCESS EXCLUSIVE MODE NOWAIT;");
        migrationBuilder.Sql("DO $$ BEGIN IF EXISTS (SELECT 1 FROM ontology.\"Drafts\") OR EXISTS (SELECT 1 FROM ontology.\"Revisions\") OR EXISTS (SELECT 1 FROM ontology.\"Validations\") OR EXISTS (SELECT 1 FROM ontology.\"Commands\") THEN RAISE EXCEPTION 'Ontology source history exists; use forward repair.'; END IF; END $$;");

        migrationBuilder.DropTable(
            name: "Commands",
            schema: "ontology");

        migrationBuilder.DropTable(
            name: "Validations",
            schema: "ontology");

        migrationBuilder.DropTable(
            name: "Revisions",
            schema: "ontology");

        migrationBuilder.DropTable(
            name: "Drafts",
            schema: "ontology");
    }
}
