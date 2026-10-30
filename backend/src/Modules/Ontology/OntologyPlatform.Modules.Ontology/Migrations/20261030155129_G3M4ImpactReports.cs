using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace OntologyPlatform.Modules.Ontology.Migrations
{
    /// <inheritdoc />
    public partial class G3M4ImpactReports : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "ImpactReports",
                schema: "ontology",
                columns: table => new
                {
                    ReportId = table.Column<string>(type: "text", nullable: false),
                    InputFingerprint = table.Column<string>(type: "text", nullable: false),
                    AssetId = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    TargetDraftId = table.Column<string>(type: "text", nullable: true),
                    TargetRevision = table.Column<long>(type: "bigint", nullable: true),
                    AssessmentId = table.Column<string>(type: "text", nullable: true),
                    ReportHash = table.Column<string>(type: "text", nullable: false),
                    ReportJson = table.Column<string>(type: "text", nullable: false),
                    GeneratedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    ExpiresAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ImpactReports", x => x.ReportId);
                    table.ForeignKey(
                        name: "FK_ImpactReports_Assessments_AssessmentId",
                        column: x => x.AssessmentId,
                        principalSchema: "ontology",
                        principalTable: "Assessments",
                        principalColumn: "AssessmentId",
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_ImpactReports_Revisions_TargetDraftId_TargetRevision",
                        columns: x => new { x.TargetDraftId, x.TargetRevision },
                        principalSchema: "ontology",
                        principalTable: "Revisions",
                        principalColumns: new[] { "DraftId", "Revision" },
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateIndex(
                name: "IX_ImpactReports_AssessmentId",
                schema: "ontology",
                table: "ImpactReports",
                column: "AssessmentId");

            migrationBuilder.CreateIndex(
                name: "IX_ImpactReports_InputFingerprint",
                schema: "ontology",
                table: "ImpactReports",
                column: "InputFingerprint",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_ImpactReports_OrganizationId_AssetId",
                schema: "ontology",
                table: "ImpactReports",
                columns: new[] { "OrganizationId", "AssetId" });

            migrationBuilder.CreateIndex(
                name: "IX_ImpactReports_TargetDraftId_TargetRevision",
                schema: "ontology",
                table: "ImpactReports",
                columns: new[] { "TargetDraftId", "TargetRevision" });
        }

        /// <summary>语义回滚复用旧Release，禁止数据库降级删除持久影响报告。</summary>
        /// <param name="migrationBuilder">不执行删除操作的迁移构建器。</param>
        /// <exception cref="NotSupportedException">任何降级请求均显式拒绝。</exception>
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            throw new NotSupportedException("影响报告迁移只允许向前升级，禁止降级删除持久报告。");
        }
    }
}
