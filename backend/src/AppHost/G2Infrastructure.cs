using Aspire.Hosting;
using Aspire.Hosting.ApplicationModel;

namespace OntologyPlatform.AppHost;

/// <summary>在既有唯一AppHost内增量编排G2真实语义与不可变制品开发资源。</summary>
internal static class G2Infrastructure
{
    /// <summary>注册独立新卷的Jena与RustFS，不访问任何历史卷或凭证。</summary>
    /// <param name="builder">当前AppHost。</param>
    /// <param name="prefix">已经校验的本轮独立资源前缀。</param>
    /// <returns>语义资源、对象存储和受保护参数引用。</returns>
    internal static (IResourceBuilder<ContainerResource> Jena, IResourceBuilder<ContainerResource> RustFs,
        IResourceBuilder<ParameterResource> AccessKey, IResourceBuilder<ParameterResource> SecretKey)
        AddG2SemanticResources(this IDistributedApplicationBuilder builder, string prefix)
    {
        // 复用批准发行包和JRE的精确摘要，Java日志关闭原文出口且堆上限512MiB。
        var jena = CanonicalFusekiImage.Add(builder)
            .WithEntrypoint("java")
            .WithArgs("-Xmx512m", "-Dlog4j.configurationFile=/opt/fuseki/g2-log4j2.properties", "-jar", "/opt/fuseki/fuseki-server.jar", "--config=/opt/fuseki/g2-config.ttl")
            .WithHttpEndpoint(port: 13030, targetPort: 3030, name: "http")
            .WithVolume($"{prefix}-fuseki-data", "/fuseki/databases")
            .WithHttpHealthCheck("/$/ping", endpointName: "http")
            .WithContainerRuntimeArgs("--restart", "unless-stopped", "--memory", "768m");
        // 凭证仅由本轮运行器在私有目录生成后作为secret参数引用。
        var access = builder.AddParameter("rustfs-access-key", secret: true);
        // S3签名密钥不进入命令行或普通日志。
        var secret = builder.AddParameter("rustfs-secret-key", secret: true);
        // 复用已经批准的RustFS1.0.3精确镜像；不引入云资源或S3 SDK。
        var rustfs = builder.AddContainer("rustfs", "rustfs/rustfs", "1.0.3")
            .WithImageSHA256("9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b")
            .WithEnvironment("RUSTFS_ACCESS_KEY", access)
            .WithEnvironment("RUSTFS_SECRET_KEY", secret)
            .WithEnvironment("RUSTFS_ADDRESS", ":9000")
            .WithEnvironment("RUSTFS_CONSOLE_ADDRESS", ":9001")
            .WithEnvironment("RUSTFS_CONSOLE_ENABLE", "true")
            .WithEnvironment("RUSTFS_HEALTH_ENDPOINT_ENABLE", "true")
            .WithEnvironment("RUSTFS_CHECK_UPDATE", "false")
            .WithVolume($"{prefix}-rustfs-data", "/data")
            .WithHttpEndpoint(port: 19000, targetPort: 9000, name: "s3")
            .WithHttpEndpoint(port: 19001, targetPort: 9001, name: "console")
            .WithArgs("/data")
            .WithHttpHealthCheck("/health/ready", endpointName: "s3")
            .WithContainerRuntimeArgs("--restart", "unless-stopped");
        return (jena, rustfs, access, secret);
    }
}
