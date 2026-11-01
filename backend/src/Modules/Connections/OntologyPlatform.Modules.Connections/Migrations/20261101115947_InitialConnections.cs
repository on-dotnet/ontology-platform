using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace OntologyPlatform.Modules.Connections.Migrations
{
    /// <inheritdoc />
    public partial class InitialConnections : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.EnsureSchema(
                name: "connections");

            migrationBuilder.CreateTable(
                name: "CatalogJobs",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    ConnectionId = table.Column<string>(type: "text", nullable: false),
                    Revision = table.Column<long>(type: "bigint", nullable: false),
                    SecretVersion = table.Column<long>(type: "bigint", nullable: false),
                    ConfigHash = table.Column<string>(type: "text", nullable: false),
                    ActorJson = table.Column<string>(type: "text", nullable: false),
                    SessionReference = table.Column<string>(type: "text", nullable: false),
                    Status = table.Column<string>(type: "text", nullable: false),
                    TraceId = table.Column<string>(type: "text", nullable: false),
                    CreatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    CompletedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    LeaseUntil = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    Fence = table.Column<long>(type: "bigint", nullable: false),
                    Attempt = table.Column<int>(type: "integer", nullable: false),
                    CancelRequested = table.Column<bool>(type: "boolean", nullable: false),
                    SnapshotId = table.Column<string>(type: "text", nullable: true),
                    DiagnosticCode = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CatalogJobs", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "CatalogSnapshots",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    ConnectionId = table.Column<string>(type: "text", nullable: false),
                    ConfigHash = table.Column<string>(type: "text", nullable: false),
                    SecretVersion = table.Column<long>(type: "bigint", nullable: false),
                    ViewJson = table.Column<string>(type: "text", nullable: false),
                    CapturedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_CatalogSnapshots", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "ConnectionCommands",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    ErrorCode = table.Column<string>(type: "text", nullable: true),
                    RequestHash = table.Column<string>(type: "text", nullable: false),
                    ScopeJson = table.Column<string>(type: "text", nullable: false),
                    ResultScopeJson = table.Column<string>(type: "text", nullable: false),
                    ReceiptJson = table.Column<string>(type: "text", nullable: false),
                    CreatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    Etag = table.Column<string>(type: "text", nullable: true),
                    StatusCode = table.Column<int>(type: "integer", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ConnectionCommands", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "ConnectionProbes",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    Revision = table.Column<long>(type: "bigint", nullable: false),
                    CommandKey = table.Column<string>(type: "text", nullable: false),
                    ActorJson = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    ConnectionId = table.Column<string>(type: "text", nullable: true),
                    Owner = table.Column<string>(type: "text", nullable: false),
                    ReportJson = table.Column<string>(type: "text", nullable: false),
                    ConfigHash = table.Column<string>(type: "text", nullable: false),
                    SecretVersion = table.Column<long>(type: "bigint", nullable: false),
                    ExpiresAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    Deadline = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ConnectionProbes", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "Connections",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    DisplayName = table.Column<string>(type: "text", nullable: false),
                    ConfigJson = table.Column<string>(type: "text", nullable: false),
                    ConfigHash = table.Column<string>(type: "text", nullable: false),
                    Revision = table.Column<long>(type: "bigint", nullable: false),
                    SecretId = table.Column<string>(type: "text", nullable: false),
                    SecretVersion = table.Column<long>(type: "bigint", nullable: false),
                    State = table.Column<string>(type: "text", nullable: false),
                    LastProbeId = table.Column<string>(type: "text", nullable: true),
                    UpdatedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_Connections", x => x.Id);
                });

            migrationBuilder.CreateTable(
                name: "ConnectionSecrets",
                schema: "connections",
                columns: table => new
                {
                    Id = table.Column<string>(type: "text", nullable: false),
                    OrganizationId = table.Column<string>(type: "text", nullable: false),
                    SiteIds = table.Column<string[]>(type: "text[]", nullable: false),
                    Owner = table.Column<string>(type: "text", nullable: false),
                    Purpose = table.Column<string>(type: "text", nullable: false),
                    Ciphertext = table.Column<string>(type: "text", nullable: false),
                    Nonce = table.Column<string>(type: "text", nullable: false),
                    Tag = table.Column<string>(type: "text", nullable: false),
                    Version = table.Column<long>(type: "bigint", nullable: false),
                    KeyVersion = table.Column<string>(type: "text", nullable: false),
                    ExpiresAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: false),
                    UsedAtUtc = table.Column<DateTimeOffset>(type: "timestamp with time zone", nullable: true),
                    ConnectionId = table.Column<string>(type: "text", nullable: true)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ConnectionSecrets", x => x.Id);
                });

            migrationBuilder.CreateIndex(
                name: "IX_CatalogJobs_OrganizationId_Id",
                schema: "connections",
                table: "CatalogJobs",
                columns: new[] { "OrganizationId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_CatalogJobs_Status_LeaseUntil",
                schema: "connections",
                table: "CatalogJobs",
                columns: new[] { "Status", "LeaseUntil" });

            migrationBuilder.CreateIndex(
                name: "IX_CatalogSnapshots_OrganizationId_Id",
                schema: "connections",
                table: "CatalogSnapshots",
                columns: new[] { "OrganizationId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_ConnectionProbes_OrganizationId_Id",
                schema: "connections",
                table: "ConnectionProbes",
                columns: new[] { "OrganizationId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_Connections_OrganizationId_Id",
                schema: "connections",
                table: "Connections",
                columns: new[] { "OrganizationId", "Id" });

            migrationBuilder.CreateIndex(
                name: "IX_ConnectionSecrets_OrganizationId_Id",
                schema: "connections",
                table: "ConnectionSecrets",
                columns: new[] { "OrganizationId", "Id" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "CatalogJobs",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "CatalogSnapshots",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "ConnectionCommands",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "ConnectionProbes",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "Connections",
                schema: "connections");

            migrationBuilder.DropTable(
                name: "ConnectionSecrets",
                schema: "connections");
        }
    }
}
