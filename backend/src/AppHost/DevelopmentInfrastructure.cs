using Aspire.Hosting;
using Aspire.Hosting.ApplicationModel;

namespace OntologyPlatform.AppHost;

/// <summary>
/// 定义有版本、卷、就绪检查和启动依赖的本地开发基础设施。
/// </summary>
internal static class DevelopmentInfrastructure
{
    /// <summary>
    /// 注册 PostgreSQL、Fuseki、RustFS、Keycloak 和非业务健康宿主。
    /// </summary>
    /// <param name="builder">当前 Aspire 应用模型构建器。</param>
    internal static void AddDevelopmentInfrastructure(this IDistributedApplicationBuilder builder)
    {
        // 密码必须从用户秘密存储或进程配置提供，命名卷重建容器时保持同值。
        var postgresPassword = builder.AddParameter("postgres-password", secret: true);
        // S3 访问标识同样按秘密处理，避免仪表盘显示实际凭证。
        var rustfsAccessKey = builder.AddParameter("rustfs-access-key", secret: true);
        // 对象存储签名密钥不设置默认值，避免意外启用公开默认密码。
        var rustfsSecretKey = builder.AddParameter("rustfs-secret-key", secret: true);
        // 只用于本地 Keycloak 引导，不实现任何产品认证流程。
        var keycloakPassword = builder.AddParameter("keycloak-admin-password", secret: true);

        // PostgreSQL18 的数据卷根为 /var/lib/postgresql，数据目录含主版本号。
        var postgres = builder.AddPostgres("postgres", password: postgresPassword, port: 15432)
            .WithImageTag("18.6-trixie")
            .WithEnvironment("PGDATA", "/var/lib/postgresql/18/docker")
            .WithDataVolume("ontology-platform-postgres-data")
            .WithContainerRuntimeArgs("--restart", "unless-stopped");
        // 平台数据库仅预留开发资源，本阶段不定义表、迁移或跨模块数据模型。
        var platformDatabase = postgres.AddDatabase("platform", "ontology_platform");
        // Keycloak 独立数据库避免把开发身份数据放入平台业务库。
        var keycloakDatabase = postgres.AddDatabase("keycloak-database", "keycloak");

        // 自建镜像只使用带固定校验和的 Apache 官方发行包，不冒称官方预构建镜像。
        var fuseki = builder.AddDockerfile("fuseki", "../../../infra/development/fuseki")
            .WithHttpEndpoint(port: 13030, targetPort: 3030, name: "http")
            .WithVolume("ontology-platform-fuseki-data", "/fuseki/databases")
            .WithArgs("--tdb2", "--loc=/fuseki/databases/ontology", "--update", "/ontology")
            .WithHttpHealthCheck("/$/ping", endpointName: "http")
            .WithContainerRuntimeArgs("--restart", "unless-stopped");

        // 单节点对象存储只用于开发，S3 与控制台分别提供独立端点。
        var rustfs = builder.AddContainer("rustfs", "rustfs/rustfs", "1.0.3")
            .WithEnvironment("RUSTFS_ACCESS_KEY", rustfsAccessKey)
            .WithEnvironment("RUSTFS_SECRET_KEY", rustfsSecretKey)
            .WithEnvironment("RUSTFS_ADDRESS", ":9000")
            .WithEnvironment("RUSTFS_CONSOLE_ADDRESS", ":9001")
            .WithEnvironment("RUSTFS_CONSOLE_ENABLE", "true")
            .WithEnvironment("RUSTFS_HEALTH_ENDPOINT_ENABLE", "true")
            .WithEnvironment("RUSTFS_CHECK_UPDATE", "false")
            .WithVolume("ontology-platform-rustfs-data", "/data")
            .WithHttpEndpoint(port: 19000, targetPort: 9000, name: "s3")
            .WithHttpEndpoint(port: 19001, targetPort: 9001, name: "console")
            .WithArgs("/data")
            .WithHttpHealthCheck("/health/ready", endpointName: "s3")
            .WithContainerRuntimeArgs("--restart", "unless-stopped");

        // 管理探针使用独立9000端口，健康检查由宿主执行，不需要镜像内 curl。
        var keycloak = builder.AddContainer("keycloak", "quay.io/keycloak/keycloak", "26.8.1")
            .WithArgs("start-dev")
            .WithEnvironment("KC_BOOTSTRAP_ADMIN_USERNAME", "local-admin")
            .WithEnvironment("KC_BOOTSTRAP_ADMIN_PASSWORD", keycloakPassword)
            .WithEnvironment("KC_HEALTH_ENABLED", "true")
            .WithEnvironment("KC_METRICS_ENABLED", "true")
            .WithEnvironment("KC_DB", "postgres")
            .WithEnvironment("KC_DB_URL_HOST", $"{postgres.GetEndpoint("tcp").Property(EndpointProperty.Host)}")
            .WithEnvironment("KC_DB_URL_PORT", $"{postgres.GetEndpoint("tcp").Property(EndpointProperty.Port)}")
            .WithEnvironment("KC_DB_URL_DATABASE", keycloakDatabase.Resource.DatabaseName)
            .WithEnvironment("KC_DB_USERNAME", "postgres")
            .WithEnvironment("KC_DB_PASSWORD", postgresPassword)
            .WithHttpEndpoint(port: 18080, targetPort: 8080, name: "http")
            .WithHttpEndpoint(port: 19090, targetPort: 9000, name: "management")
            .WithHttpHealthCheck("/health/ready", endpointName: "management")
            .WithContainerRuntimeArgs("--restart", "unless-stopped")
            .WaitFor(keycloakDatabase);

        // 此宿主只证明技术默认值可用，端点就绪不等同依赖或业务功能验收。
        builder.AddProject<Projects.OntologyPlatform_InfrastructureApi>("infrastructure-api")
            .WithEnvironment("ASPNETCORE_ENVIRONMENT", "Development")
            .WithHttpEndpoint(port: 15080, name: "http")
            .WithHttpHealthCheck("/health")
            .WithReference(platformDatabase)
            .WithReference(fuseki.GetEndpoint("http"))
            .WithReference(rustfs.GetEndpoint("s3"))
            .WithReference(keycloak.GetEndpoint("http"))
            .WaitFor(platformDatabase)
            .WaitFor(fuseki)
            .WaitFor(rustfs)
            .WaitFor(keycloak);
    }
}
