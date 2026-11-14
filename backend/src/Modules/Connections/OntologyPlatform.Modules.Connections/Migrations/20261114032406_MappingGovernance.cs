using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace OntologyPlatform.Modules.Connections.Migrations
{
    /// <inheritdoc />
    public partial class MappingGovernance : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "Mappings",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    Revision = table.Column<long>(type: "bigint", nullable: false),
                    DisplayName = table.Column<string>(type: "text", nullable: false),
                    DraftId = table.Column<string>(type: "text", nullable: false),
                    CurrentRevisionId = table.Column<string>(type: "text", nullable: false),
                    SourceConnectionId = table.Column<string>(type: "text", nullable: false),
                    UpdatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Mappings", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "MappingActivationChecks",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    MappingId = table.Column<string>(type: "text", nullable: false),
                    CanonicalBytes = table.Column<byte[]>(type: "bytea", nullable: false),
                    ContentHash = table.Column<string>(type: "text", nullable: false),
                    CreatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    ProposalId = table.Column<string>(type: "text", nullable: false),
                    BindingHash = table.Column<string>(type: "text", nullable: false),
                    ExpiresAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    Status = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MappingActivationChecks", x => x.Id);
                    table.ForeignKey(
                        name: "FK_MappingActivationChecks_Mappings_MappingId",
                        column: x => x.MappingId,
                        principalSchema: "connections",
                        principalTable: "Mappings",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "MappingActivations",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    MappingId = table.Column<string>(type: "text", nullable: false),
                    CanonicalBytes = table.Column<byte[]>(type: "bytea", nullable: false),
                    ContentHash = table.Column<string>(type: "text", nullable: false),
                    CreatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    ProposalId = table.Column<string>(type: "text", nullable: false),
                    ReleaseId = table.Column<string>(type: "text", nullable: false),
                    CheckId = table.Column<string>(type: "text", nullable: false),
                    BindingJson = table.Column<string>(type: "text", nullable: false),
                    ActivationRevision = table.Column<long>(type: "bigint", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MappingActivations", x => x.Id);
                    table.ForeignKey(
                        name: "FK_MappingActivations_Mappings_MappingId",
                        column: x => x.MappingId,
                        principalSchema: "connections",
                        principalTable: "Mappings",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "MappingActives",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    MappingId = table.Column<string>(type: "text", nullable: false),
                    ReleaseId = table.Column<string>(type: "text", nullable: false),
                    ActivationRevision = table.Column<long>(type: "bigint", nullable: false),
                    ActivationId = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MappingActives", x => x.Id);
                    table.ForeignKey(
                        name: "FK_MappingActives_Mappings_MappingId",
                        column: x => x.MappingId,
                        principalSchema: "connections",
                        principalTable: "Mappings",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "MappingAssessments",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    MappingId = table.Column<string>(type: "text", nullable: false),
                    CanonicalBytes = table.Column<byte[]>(type: "bytea", nullable: false),
                    ContentHash = table.Column<string>(type: "text", nullable: false),
                    CreatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    TargetKind = table.Column<string>(type: "text", nullable: false),
                    TargetId = table.Column<string>(type: "text", nullable: false),
                    TargetRevision = table.Column<long>(type: "bigint", nullable: false),
                    BindingJson = table.Column<string>(type: "text", nullable: false),
                    SemanticResultHash = table.Column<string>(type: "text", nullable: false),
                    ImpactHash = table.Column<string>(type: "text", nullable: false),
                    Status = table.Column<string>(type: "text", nullable: false),
                    ExpiresAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MappingAssessments", x => x.Id);
                    table.ForeignKey(
                        name: "FK_MappingAssessments_Mappings_MappingId",
                        column: x => x.MappingId,
                        principalSchema: "connections",
                        principalTable: "Mappings",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "MappingCommands",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    MappingId = table.Column<string>(type: "text", nullable: false),
                    CreatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    SubjectId = table.Column<string>(type: "text", nullable: false),
                    Operation = table.Column<string>(type: "text", nullable: false),
                    CommandId = table.Column<string>(type: "text", nullable: false),
                    IdempotencyKey = table.Column<string>(type: "text", nullable: false),
                    PayloadHash = table.Column<string>(type: "text", nullable: false),
                    ResponseBytes = table.Column<byte[]>(type: "bytea", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MappingCommands", x => x.Id);
                    table.ForeignKey(
                        name: "FK_MappingCommands_Mappings_MappingId",
                        column: x => x.MappingId,
                        principalSchema: "connections",
                        principalTable: "Mappings",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "MappingJobs",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    MappingId = table.Column<string>(type: "text", nullable: false),
                    Revision = table.Column<long>(type: "bigint", nullable: false),
                    CreatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    Kind = table.Column<string>(type: "text", nullable: false),
                    Status = table.Column<string>(type: "text", nullable: false),
                    RequestJson = table.Column<string>(type: "text", nullable: false),
                    AuthorityJson = table.Column<string>(type: "text", nullable: false),
                    SubmittedBy = table.Column<string>(type: "text", nullable: false),
                    Fence = table.Column<long>(type: "bigint", nullable: false),
                    LeaseUntil = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    ResultId = table.Column<string>(type: "text", nullable: true),
                    CompletedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    ErrorCode = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MappingJobs", x => x.Id);
                    table.ForeignKey(
                        name: "FK_MappingJobs_Mappings_MappingId",
                        column: x => x.MappingId,
                        principalSchema: "connections",
                        principalTable: "Mappings",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "MappingNotifications",
                schema: "connections",
                columns: table => new
                {
                    MappingId = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    ActivationRevision = table.Column<long>(type: "bigint", nullable: false),
                    ReleaseId = table.Column<string>(type: "text", nullable: false),
                    ManifestHash = table.Column<string>(type: "text", nullable: false),
                    EventId = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MappingNotifications", x => x.MappingId);
                    table.ForeignKey(
                        name: "FK_MappingNotifications_Mappings_MappingId",
                        column: x => x.MappingId,
                        principalSchema: "connections",
                        principalTable: "Mappings",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "MappingOutboxReceipts",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    MappingId = table.Column<string>(type: "text", nullable: false),
                    ActivationRevision = table.Column<long>(type: "bigint", nullable: false),
                    CreatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MappingOutboxReceipts", x => x.Id);
                    table.ForeignKey(
                        name: "FK_MappingOutboxReceipts_Mappings_MappingId",
                        column: x => x.MappingId,
                        principalSchema: "connections",
                        principalTable: "Mappings",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "MappingOutboxs",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    MappingId = table.Column<string>(type: "text", nullable: false),
                    CreatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    ReleaseId = table.Column<string>(type: "text", nullable: false),
                    ManifestHash = table.Column<string>(type: "text", nullable: false),
                    ActivationRevision = table.Column<long>(type: "bigint", nullable: false),
                    DispatchedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    Attempts = table.Column<long>(type: "bigint", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MappingOutboxs", x => x.Id);
                    table.ForeignKey(
                        name: "FK_MappingOutboxs_Mappings_MappingId",
                        column: x => x.MappingId,
                        principalSchema: "connections",
                        principalTable: "Mappings",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "MappingProposals",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    MappingId = table.Column<string>(type: "text", nullable: false),
                    Revision = table.Column<long>(type: "bigint", nullable: false),
                    CreatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    Kind = table.Column<string>(type: "text", nullable: false),
                    RequestBytes = table.Column<byte[]>(type: "bytea", nullable: false),
                    BindingHash = table.Column<string>(type: "text", nullable: false),
                    Status = table.Column<string>(type: "text", nullable: false),
                    SubmittedBy = table.Column<string>(type: "text", nullable: false),
                    SubmitProofJson = table.Column<string>(type: "text", nullable: false),
                    DecidedBy = table.Column<string>(type: "text", nullable: true),
                    DecisionJson = table.Column<string>(type: "text", nullable: true),
                    DecisionProofJson = table.Column<string>(type: "text", nullable: true),
                    DecidedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    ExpiresAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    ActivationId = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MappingProposals", x => x.Id);
                    table.ForeignKey(
                        name: "FK_MappingProposals_Mappings_MappingId",
                        column: x => x.MappingId,
                        principalSchema: "connections",
                        principalTable: "Mappings",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "MappingReleases",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    MappingId = table.Column<string>(type: "text", nullable: false),
                    CanonicalBytes = table.Column<byte[]>(type: "bytea", nullable: false),
                    ContentHash = table.Column<string>(type: "text", nullable: false),
                    CreatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MappingReleases", x => x.Id);
                    table.ForeignKey(
                        name: "FK_MappingReleases_Mappings_MappingId",
                        column: x => x.MappingId,
                        principalSchema: "connections",
                        principalTable: "Mappings",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateTable(
                name: "MappingRevisions",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    MappingId = table.Column<string>(type: "text", nullable: false),
                    Revision = table.Column<long>(type: "bigint", nullable: false),
                    CanonicalBytes = table.Column<byte[]>(type: "bytea", nullable: false),
                    ContentHash = table.Column<string>(type: "text", nullable: false),
                    CreatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    DraftId = table.Column<string>(type: "text", nullable: false),
                    CreatedBy = table.Column<string>(type: "text", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_MappingRevisions", x => x.Id);
                    table.ForeignKey(
                        name: "FK_MappingRevisions_Mappings_MappingId",
                        column: x => x.MappingId,
                        principalSchema: "connections",
                        principalTable: "Mappings",
                        principalColumn: "Id",
                        onDelete: ReferentialAction.Restrict);
                });

            migrationBuilder.CreateIndex(
                name: "IX_MappingActivationChecks_MappingId",
                schema: "connections",
                table: "MappingActivationChecks",
                column: "MappingId");

            migrationBuilder.CreateIndex(
                name: "IX_MappingActivationChecks_OrganizationId_Id",
                schema: "connections",
                table: "MappingActivationChecks",
                columns: new[] { "OrganizationId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_MappingActivations_MappingId",
                schema: "connections",
                table: "MappingActivations",
                column: "MappingId");

            migrationBuilder.CreateIndex(
                name: "IX_MappingActivations_OrganizationId_Id",
                schema: "connections",
                table: "MappingActivations",
                columns: new[] { "OrganizationId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_MappingActivations_ProposalId",
                schema: "connections",
                table: "MappingActivations",
                column: "ProposalId",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_MappingActives_MappingId",
                schema: "connections",
                table: "MappingActives",
                column: "MappingId",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_MappingActives_OrganizationId_Id",
                schema: "connections",
                table: "MappingActives",
                columns: new[] { "OrganizationId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_MappingAssessments_MappingId",
                schema: "connections",
                table: "MappingAssessments",
                column: "MappingId");

            migrationBuilder.CreateIndex(
                name: "IX_MappingAssessments_OrganizationId_Id",
                schema: "connections",
                table: "MappingAssessments",
                columns: new[] { "OrganizationId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_MappingCommands_MappingId",
                schema: "connections",
                table: "MappingCommands",
                column: "MappingId");

            migrationBuilder.CreateIndex(
                name: "IX_MappingCommands_OrganizationId_CommandId",
                schema: "connections",
                table: "MappingCommands",
                columns: new[] { "OrganizationId", "CommandId" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_MappingCommands_OrganizationId_Id",
                schema: "connections",
                table: "MappingCommands",
                columns: new[] { "OrganizationId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_MappingCommands_OrganizationId_MappingId_Operation_Idempote~",
                schema: "connections",
                table: "MappingCommands",
                columns: new[] { "OrganizationId", "MappingId", "Operation", "IdempotencyKey" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_MappingJobs_MappingId",
                schema: "connections",
                table: "MappingJobs",
                column: "MappingId");

            migrationBuilder.CreateIndex(
                name: "IX_MappingJobs_OrganizationId_Id",
                schema: "connections",
                table: "MappingJobs",
                columns: new[] { "OrganizationId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_MappingJobs_Status_LeaseUntil",
                schema: "connections",
                table: "MappingJobs",
                columns: new[] { "Status", "LeaseUntil" });

            migrationBuilder.CreateIndex(
                name: "IX_MappingOutboxReceipts_MappingId",
                schema: "connections",
                table: "MappingOutboxReceipts",
                column: "MappingId");

            migrationBuilder.CreateIndex(
                name: "IX_MappingOutboxs_MappingId",
                schema: "connections",
                table: "MappingOutboxs",
                column: "MappingId");

            migrationBuilder.CreateIndex(
                name: "IX_MappingOutboxs_OrganizationId_Id",
                schema: "connections",
                table: "MappingOutboxs",
                columns: new[] { "OrganizationId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_MappingProposals_MappingId",
                schema: "connections",
                table: "MappingProposals",
                column: "MappingId");

            migrationBuilder.CreateIndex(
                name: "IX_MappingProposals_OrganizationId_Id",
                schema: "connections",
                table: "MappingProposals",
                columns: new[] { "OrganizationId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_MappingReleases_MappingId",
                schema: "connections",
                table: "MappingReleases",
                column: "MappingId");

            migrationBuilder.CreateIndex(
                name: "IX_MappingReleases_OrganizationId_Id",
                schema: "connections",
                table: "MappingReleases",
                columns: new[] { "OrganizationId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_MappingRevisions_MappingId_Revision",
                schema: "connections",
                table: "MappingRevisions",
                columns: new[] { "MappingId", "Revision" },
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_MappingRevisions_OrganizationId_Id",
                schema: "connections",
                table: "MappingRevisions",
                columns: new[] { "OrganizationId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_Mappings_OrganizationId_Id",
                schema: "connections",
                table: "Mappings",
                columns: new[] { "OrganizationId", "Id" });
            // 历史制品及证明只追加，直接SQL也不能绕过不可变与原字节散列约束。
            migrationBuilder.Sql("""

                CREATE FUNCTION connections.mapping_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN
                    RAISE EXCEPTION 'mapping_immutable' USING ERRCODE = '23514';
                END $$;
                CREATE TRIGGER mapping_immutable BEFORE UPDATE OR DELETE ON connections."MappingReleases"
                    FOR EACH ROW EXECUTE FUNCTION connections.mapping_immutable();
                ALTER TABLE connections."MappingReleases" ADD CONSTRAINT "CK_MappingReleases_bytes"
                    CHECK (octet_length("CanonicalBytes") BETWEEN 1 AND 1048576 AND "ContentHash" = encode(sha256("CanonicalBytes"), 'hex'));
                CREATE TRIGGER mapping_immutable BEFORE UPDATE OR DELETE ON connections."MappingRevisions"
                    FOR EACH ROW EXECUTE FUNCTION connections.mapping_immutable();
                ALTER TABLE connections."MappingRevisions" ADD CONSTRAINT "CK_MappingRevisions_bytes"
                    CHECK (octet_length("CanonicalBytes") BETWEEN 1 AND 1048576 AND "ContentHash" = encode(sha256("CanonicalBytes"), 'hex'));
                CREATE TRIGGER mapping_immutable BEFORE UPDATE OR DELETE ON connections."MappingAssessments"
                    FOR EACH ROW EXECUTE FUNCTION connections.mapping_immutable();
                ALTER TABLE connections."MappingAssessments" ADD CONSTRAINT "CK_MappingAssessments_bytes"
                    CHECK (octet_length("CanonicalBytes") BETWEEN 1 AND 1048576 AND "ContentHash" = encode(sha256("CanonicalBytes"), 'hex'));
                CREATE TRIGGER mapping_immutable BEFORE UPDATE OR DELETE ON connections."MappingActivations"
                    FOR EACH ROW EXECUTE FUNCTION connections.mapping_immutable();
                ALTER TABLE connections."MappingActivations" ADD CONSTRAINT "CK_MappingActivations_bytes"
                    CHECK (octet_length("CanonicalBytes") BETWEEN 1 AND 1048576 AND "ContentHash" = encode(sha256("CanonicalBytes"), 'hex'));
                CREATE TRIGGER mapping_immutable BEFORE UPDATE OR DELETE ON connections."MappingActivationChecks"
                    FOR EACH ROW EXECUTE FUNCTION connections.mapping_immutable();
                ALTER TABLE connections."MappingActivationChecks" ADD CONSTRAINT "CK_MappingActivationChecks_bytes"
                    CHECK (octet_length("CanonicalBytes") BETWEEN 1 AND 1048576 AND "ContentHash" = encode(sha256("CanonicalBytes"), 'hex'));
                """);
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "MappingActivationChecks",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "MappingActivations",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "MappingActives",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "MappingAssessments",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "MappingCommands",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "MappingJobs",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "MappingNotifications",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "MappingOutboxReceipts",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "MappingOutboxs",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "MappingProposals",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "MappingReleases",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "MappingRevisions",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "Mappings",
                schema: "connections");
            // 所有引用触发器随表删除后再移除本模块函数。
            migrationBuilder.Sql("DROP FUNCTION connections.mapping_immutable();");
        }
    }
}
