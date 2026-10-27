using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace OntologyPlatform.Modules.Ontology.Migrations
{
    /// <inheritdoc />
    public partial class G3Assessments : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "Assessments",
                schema: "ontology",
                columns: table => new
                {
                    AssessmentId = table.Column<string>(type: "text", nullable: false),
                    ValidationReportId = table.Column<string>(type: "text", nullable: false),
                    DraftId = table.Column<string>(type: "text", nullable: false),
                    Revision = table.Column<long>(type: "bigint", nullable: false),
                    AssessmentJson = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Assessments", x => x.AssessmentId);
                    table.ForeignKey(
                        name: "FK_Assessments_Revisions_DraftId_Revision",
                        columns: x => new { x.DraftId, x.Revision },
                        principalSchema: "ontology",
                        principalTable: "Revisions",
                        principalColumns: new[] { "DraftId", "Revision" },
                        onDelete: ReferentialAction.Restrict);
                    table.ForeignKey(
                        name: "FK_Assessments_Validations_ValidationReportId",
                        column: x => x.ValidationReportId,
                        principalSchema: "ontology",
                        principalTable: "Validations",
                        principalColumn: "ReportId",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateIndex(
                name: "IX_Assessments_DraftId_Revision",
                schema: "ontology",
                table: "Assessments",
                columns: new[] { "DraftId", "Revision" });

            migrationBuilder.CreateIndex(
                name: "IX_Assessments_ValidationReportId",
                schema: "ontology",
                table: "Assessments",
                column: "ValidationReportId",
                unique: true);
        }

        /// <summary>本迁移仅向前兼容；应用回退保留评估事实，禁止降级删除已持久数据。</summary>
        /// <param name="migrationBuilder">不执行删除操作的迁移构建器。</param>
        /// <exception cref="NotSupportedException">任何降级请求都必须显式拒绝。</exception>
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            throw new NotSupportedException("G3评估迁移只允许向前升级，禁止降级删除评估事实。");
        }
    }
}
