using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace OntologyPlatform.Modules.Governance.Migrations
{
    /// <inheritdoc />
    public partial class MappingAuthorization : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "MappingAuthorizationEpochs",
                schema: "governance",
                columns: table => new
                {
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    Revision = table.Column<long>(type: "bigint", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MappingAuthorizationEpochs", x => x.OrganizationId);
                });

            migrationBuilder.CreateTable(
                name: "MappingAuthorizationGrants",
                schema: "governance",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    SubjectId = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    Permission = table.Column<string>(type: "text", nullable: false),
                    ConnectionId = table.Column<string>(type: "text", nullable: true),
                    ObjectRefs = table.Column<string[]>(type: "text[]", nullable: false),
                    FieldRefs = table.Column<string[]>(type: "text[]", nullable: false),
                    ExpiresAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    RevokedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MappingAuthorizationGrants", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_MappingAuthorizationGrants_OrganizationId_SubjectId_Permiss~",
                schema: "governance",
                table: "MappingAuthorizationGrants",
                columns: new[] { "OrganizationId", "SubjectId", "Permission" });
            // 授权记录的任何变化都在组织唯一锁域中递增epoch，CLI遗漏也不能静默绕过。
            migrationBuilder.Sql("""
                ALTER TABLE governance."MappingAuthorizationEpochs" ADD CONSTRAINT "CK_mapping_epoch"
                    CHECK ("Revision" BETWEEN 1 AND 9007199254740991);
                CREATE FUNCTION governance.mapping_grant_epoch() RETURNS trigger LANGUAGE plpgsql AS $$
                DECLARE organization text;
                BEGIN
                    IF TG_OP = 'UPDATE' AND NEW."OrganizationId" <> OLD."OrganizationId" THEN
                        RAISE EXCEPTION 'mapping_grant_scope_immutable' USING ERRCODE = '23514';
                    END IF;
                    IF TG_OP = 'DELETE' THEN organization := OLD."OrganizationId";
                    ELSE organization := NEW."OrganizationId"; END IF;
                    INSERT INTO governance."MappingAuthorizationEpochs" ("OrganizationId", "Revision")
                        VALUES (organization, 1) ON CONFLICT ("OrganizationId") DO NOTHING;
                    UPDATE governance."MappingAuthorizationEpochs" SET "Revision" = "Revision" + 1
                        WHERE "OrganizationId" = organization;
                    IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
                END $$;
                CREATE TRIGGER mapping_grant_epoch BEFORE INSERT OR UPDATE OR DELETE ON governance."MappingAuthorizationGrants"
                    FOR EACH ROW EXECUTE FUNCTION governance.mapping_grant_epoch();
                """);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.Sql("DROP TRIGGER mapping_grant_epoch ON governance.\"MappingAuthorizationGrants\"; DROP FUNCTION governance.mapping_grant_epoch();");
            migrationBuilder.DropTable(
                name: "MappingAuthorizationEpochs",
                schema: "governance");

            migrationBuilder.DropTable(
                name: "MappingAuthorizationGrants",
                schema: "governance");
        }
    }
}
