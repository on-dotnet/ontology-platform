using System.Text.Json;
using Aspire.Hosting;
using Aspire.Hosting.ApplicationModel;
using Microsoft.Extensions.Configuration;

namespace OntologyPlatform.AppHost;

/// <summary>用独立卷和回环端点编排本轮正式BFF与本地观测资源。</summary>
internal static class Wave2Infrastructure
{
    /// <summary>注册专用数据库、身份服务及可选的完整纵向验收栈。</summary>
    /// <param name="builder">当前开发编排模型。</param>
    internal static void AddWave2Infrastructure(this IDistributedApplicationBuilder builder)
    {
        // 每轮验收显式指定新卷前缀，禁止误用历史开发数据。
        var prefix = Required(builder, "DevelopmentInfrastructure:VolumePrefix");
        if (!System.Text.RegularExpressions.Regex.IsMatch(prefix, "\\A(?:wave2|g2|g3-m1|g3-m2|g3-m3)-[a-z0-9-]{1,40}\\z"))
        {
            throw new ArgumentException("纵向验收必须使用独立wave2-、g2-、g3-m1-、g3-m2-或g3-m3-卷前缀。");
        }
        // 参数标记secret，Aspire仪表盘与环境模型不显示密码明文。
        var postgresPassword = builder.AddParameter("postgres-password", secret: true);
        // 新卷的Keycloak引导身份不访问已有Realm或凭证。
        var keycloakPassword = builder.AddParameter("keycloak-admin-password", secret: true);
        // PostgreSQL镜像与M0已验收精确摘要一致。
        var postgres = builder.AddPostgres("postgres", password: postgresPassword, port: 15432)
            .WithImageTag("18.6-trixie")
            .WithImageSHA256("edb0c08dc33befd0262ab3b5cf1c4f3f8cfd8b09e88c05b45adee29d6761ddb6")
            .WithEnvironment("PGDATA", "/var/lib/postgresql/18/docker")
            .WithDataVolume($"{prefix}-postgres-data")
            .WithContainerRuntimeArgs("--restart", "unless-stopped");
        // 模块数据和身份服务使用不同数据库，不跨模块写表。
        var governance = postgres.AddDatabase("governance", "governance");
        // Keycloak仅使用本轮独立身份数据库。
        var identityDatabase = postgres.AddDatabase("keycloak-database", "keycloak");
        // 复用批准的Keycloak固定版本，公开端口由Aspire回环代理提供。
        var keycloak = builder.AddContainer("keycloak", "quay.io/keycloak/keycloak", "26.8.1")
            .WithImageSHA256("a78d6b79572168cb25886b80a8b5b8d4ed4390743e3eecb810538683e209dd6b")
            .WithArgs("start-dev")
            .WithEnvironment("KC_BOOTSTRAP_ADMIN_USERNAME", "wave2-bootstrap")
            .WithEnvironment("KC_BOOTSTRAP_ADMIN_PASSWORD", keycloakPassword)
            .WithEnvironment("KC_HEALTH_ENABLED", "true")
            .WithEnvironment("KC_METRICS_ENABLED", "true")
            .WithEnvironment("KC_DB", "postgres")
            .WithEnvironment("KC_DB_URL_HOST", $"{postgres.GetEndpoint("tcp").Property(EndpointProperty.Host)}")
            .WithEnvironment("KC_DB_URL_PORT", $"{postgres.GetEndpoint("tcp").Property(EndpointProperty.Port)}")
            .WithEnvironment("KC_DB_URL_DATABASE", identityDatabase.Resource.DatabaseName)
            .WithEnvironment("KC_DB_USERNAME", "postgres")
            .WithEnvironment("KC_DB_PASSWORD", postgresPassword)
            .WithHttpEndpoint(port: 18080, targetPort: 8080, name: "http")
            .WithHttpEndpoint(port: 19090, targetPort: 9000, name: "management")
            .WithHttpHealthCheck("/health/ready", endpointName: "management")
            .WithContainerRuntimeArgs("--restart", "unless-stopped")
            .WaitFor(identityDatabase);
        if (builder.Configuration.GetValue<bool>("Wave2:CoreOnly"))
        {
            return;
        }
        // 只在完整阶段读取已审OBS清单，首次身份引导不启动产品服务。
        var observation = AddObservation(builder, prefix);
        // 只有本次G2显式开启才增加真实语义和制品资源，历史Wave2模型不变。
        var g2Enabled = builder.Configuration.GetValue<bool>("G2:Enabled");
        // 未启用时不创建任何额外容器或读取参数。
        var semantics = g2Enabled ? builder.AddG2SemanticResources(prefix) : default;
        // Next使用精确项目工具路径，无全局pnpm与浏览器令牌。
        var web = builder.AddExecutable("web", Required(builder, "Wave2:NodePath"), "../../../apps/web",
                "node_modules/next/dist/bin/next", "start", "--hostname", "127.0.0.1", "--port", "15300")
            .WithEnvironment("NODE_ENV", "production")
            .WithEnvironment("PLATFORM_API_ORIGIN", "http://localhost:15100")
            .WithHttpEndpoint(port: 15300, targetPort: 15300, name: "http", isProxied: false);
        // 两实例共享持久化证书和加密keyring，客户端秘密始终作为secret参数。
        var clientSecret = builder.AddParameter("bff-client-secret", secret: true);
        // 证书密码不进入源码或进程命令行。
        var certificatePassword = builder.AddParameter("keyring-certificate-password", secret: true);
        // 编排器探针共享的随机密钥不向浏览器暴露。
        var healthKey = builder.AddParameter("api-health-key", secret: true);
        foreach (var instance in new[] { 1, 2 })
        {
            // 第二实例在同一主机不同端口，模拟同一公共源后的两个服务节点。
            var port = instance == 1 ? 15100 : 15101;
            // 固定两个实例维度，避免累计指标被聚合成同一写入流。
            // 历史G1验收保留阶段名，仅G2开关启用后使用本轮版本。
            var version = g2Enabled ? "G2-THIN-SLICE-001" : "G1-WAVE2";
            // 每实例保持独立指标流。
            var resourceAttributes = $"service.version={version},deployment.environment.name=development,service.instance.id=platform-api-{instance}";
            var api = builder.AddProject<Projects.OntologyPlatform_Api>($"platform-api-{instance}", launchProfileName: null)
                .WithEnvironment("ASPNETCORE_ENVIRONMENT", "Development")
                .WithEnvironment("AllowedHosts", "localhost")
                .WithEnvironment("Security__Authority", Required(builder, "Wave2:Authority"))
                .WithEnvironment("Security__ClientId", Required(builder, "Wave2:ClientId"))
                .WithEnvironment("Security__ClientSecret", clientSecret)
                .WithEnvironment("Security__PublicOrigin", "http://localhost:15100")
                .WithEnvironment("Security__KeyRingPath", Required(builder, "Wave2:KeyRingPath"))
                .WithEnvironment("Security__CertificatePath", Required(builder, "Wave2:CertificatePath"))
                .WithEnvironment("Security__CertificatePassword", certificatePassword)
                .WithEnvironment("Security__HealthKey", healthKey)
                .WithEnvironment("Web__Origin", "http://127.0.0.1:15300")
                .WithEnvironment("Governance__ApplyMigrations", instance == 1 ? "true" : "false")
                .WithEnvironment("Governance__SeedDevelopmentResources", instance == 1 ? "true" : "false")
                .WithEnvironment("OTEL_SERVICE_NAME", "ontology-platform-api")
                .WithEnvironment("OTEL_RESOURCE_ATTRIBUTES", resourceAttributes)
                .WithEnvironment("OTEL_EXPORTER_OTLP_ENDPOINT", observation.GetEndpoint("otlp-http"))
                .WithEnvironment("OTEL_EXPORTER_OTLP_PROTOCOL", "http/protobuf")
                .WithEnvironment("OTEL_METRIC_EXPORT_INTERVAL", "5000")
                .WithHttpEndpoint(port: port, targetPort: port, name: "http", isProxied: false)
                .WithReference(governance)
                .WaitFor(governance)
                .WaitFor(keycloak)
                .WaitFor(web)
                .WaitFor(observation);
            if (g2Enabled)
            {
                api.WithEnvironment("G2__Enabled", "true")
                    .WithEnvironment("G2__ApplyMigrations", instance == 1 ? "true" : "false")
                    .WithEnvironment("Agents__EnableDeterministicHarness", "true")
                    .WithEnvironment("Semantics__ValidationOrigin", ReferenceExpression.Create($"{semantics.Jena.GetEndpoint("http")}/validation"))
                    .WithEnvironment("Semantics__PublishedOrigin", ReferenceExpression.Create($"{semantics.Jena.GetEndpoint("http")}/ontology"))
                    .WithEnvironment("Publishing__S3Endpoint", ReferenceExpression.Create($"http://127.0.0.1:{semantics.RustFs.GetEndpoint("s3").Property(EndpointProperty.Port)}"))
                    .WithEnvironment("Publishing__AccessKey", semantics.AccessKey)
                    .WithEnvironment("Publishing__SecretKey", semantics.SecretKey)
                    .WithEnvironment("Publishing__Bucket", "ontology-releases")
                    .WaitFor(semantics.Jena).WaitFor(semantics.RustFs);
            }
        }
    }

    /// <summary>从固定的配置即代码清单注册五个本地观测容器。</summary>
    /// <param name="builder">当前编排模型。</param>
    /// <param name="prefix">已经校验的独立卷前缀。</param>
    /// <returns>供主机API发送OTLP的Alloy资源。</returns>
    private static IResourceBuilder<ContainerResource> AddObservation(IDistributedApplicationBuilder builder, string prefix)
    {
        // 清单和只读配置均从AppHost工程的仓库路径解析。
        var root = Path.GetFullPath(Path.Combine(builder.AppHostDirectory, "../../.."));
        // 只消费已提交资源合同，不创建第二套Compose生命周期。
        using var manifest = JsonDocument.Parse(File.ReadAllText(Path.Combine(root, "infra/observability/resources.json")));
        // 先注册所有资源，再连接依赖，避免清单顺序影响模型。
        var resources = new Dictionary<string, IResourceBuilder<ContainerResource>>(StringComparer.Ordinal);
        foreach (var item in manifest.RootElement.GetProperty("resources").EnumerateArray())
        {
            // 资源名和镜像摘要在独立OBS审查中固定。
            var name = item.GetProperty("name").GetString()!;
            // 容器只暴露声明的回环代理端口，网络别名仅在本轮网络内使用。
            var resource = builder.AddContainer(name, item.GetProperty("image").GetString()!, item.GetProperty("tag").GetString()!)
                .WithImageSHA256(item.GetProperty("indexDigest").GetString()!["sha256:".Length..])
                .WithContainerNetworkAlias(name)
                .WithArgs(item.GetProperty("args").EnumerateArray().Select(value => value.GetString()!).ToArray())
                .WithContainerRuntimeArgs("--restart", "unless-stopped");
            foreach (var endpoint in item.GetProperty("ports").EnumerateArray())
            {
                resource.WithHttpEndpoint(port: endpoint.GetProperty("host").GetInt32(), targetPort: endpoint.GetProperty("target").GetInt32(),
                    name: endpoint.GetProperty("name").GetString()!);
            }
            foreach (var environment in item.GetProperty("environment").EnumerateObject())
            {
                resource.WithEnvironment(environment.Name, environment.Value.GetString()!);
            }
            foreach (var mount in item.GetProperty("mounts").EnumerateArray())
            {
                resource.WithBindMount(Path.Combine(root, mount.GetProperty("sourceRelativeTo").GetString()!, mount.GetProperty("source").GetString()!),
                    mount.GetProperty("target").GetString()!, isReadOnly: true);
            }
            // 每组件独立命名卷持久化，绝不复用用户历史卷。
            var volume = item.GetProperty("volume");
            resource.WithVolume(volume.GetProperty("name").GetString()!.Replace("${VolumePrefix}", prefix, StringComparison.Ordinal), volume.GetProperty("target").GetString()!);
            // 健康请求只读进程状态，不输出运维或身份数据。
            var health = item.GetProperty("health");
            resource.WithHttpHealthCheck(health.GetProperty("path").GetString()!, endpointName: health.GetProperty("endpoint").GetString()!);
            resources.Add(name, resource);
        }
        // Grafana密码仅存在外部秘密参数；不用源码默认账号密码组合。
        var grafanaPassword = builder.AddParameter("grafana-admin-password", secret: true);
        resources["grafana"].WithEnvironment("GF_SECURITY_ADMIN_PASSWORD", grafanaPassword);
        foreach (var item in manifest.RootElement.GetProperty("resources").EnumerateArray())
        {
            foreach (var dependency in item.GetProperty("dependsOn").EnumerateArray())
            {
                resources[item.GetProperty("name").GetString()!].WaitFor(resources[dependency.GetString()!]);
            }
        }
        return resources["alloy"];
    }

    /// <summary>读取必需配置并用固定错误拒绝缺失值，避免秘密进入异常。</summary>
    /// <param name="builder">当前编排模型。</param>
    /// <param name="key">配置键名。</param>
    /// <returns>已验证存在的配置值。</returns>
    private static string Required(IDistributedApplicationBuilder builder, string key)
        => !string.IsNullOrWhiteSpace(builder.Configuration[key]) ? builder.Configuration[key]! : throw new InvalidOperationException($"缺少Wave2配置：{key}");
}
