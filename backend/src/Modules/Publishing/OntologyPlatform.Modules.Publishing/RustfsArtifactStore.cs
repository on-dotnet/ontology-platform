using System.Globalization;
using System.Net;
using System.Security.Cryptography;
using System.Text;
using Microsoft.Extensions.Configuration;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Publishing;

/// <summary>只实现本轮回环RustFS需要的SigV4条件写和有界回读，不依赖AWS SDK。</summary>
public sealed class RustfsArtifactStore : IReleaseArtifactStore
{
    /// <summary>禁止代理及重定向的受控工厂。</summary>
    private readonly IHttpClientFactory clients;

    /// <summary>仅可信启动配置中的固定回环根地址。</summary>
    private readonly Uri endpoint;

    /// <summary>仅在进程内用于签名，永不日志输出。</summary>
    private readonly string accessKey;

    /// <summary>仅在进程内用于HMAC，永不持久化。</summary>
    private readonly string signingSecret;

    /// <summary>隔离固定桶名，不能由请求传入。</summary>
    private readonly string bucket;

    /// <summary>可测试的签名UTC时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>读取可信进程配置并限制网络目的地为数字回环IP。</summary>
    public RustfsArtifactStore(IHttpClientFactory clients, IConfiguration configuration, TimeProvider clock)
    {
        this.clients = clients;
        this.clock = clock;
        endpoint = new Uri(configuration["Publishing:S3Endpoint"] ?? throw new InvalidOperationException("缺少发布对象存储配置。"));
        // 解析出的数字地址用于拒绝DNS重绑定和非回环网络目的地。
        if (endpoint.Scheme != "http" || !IPAddress.TryParse(endpoint.Host, out var address) || !IPAddress.IsLoopback(address) || endpoint.AbsolutePath != "/" || endpoint.Query.Length != 0 || endpoint.Fragment.Length != 0 || endpoint.UserInfo.Length != 0) throw new InvalidOperationException("对象存储仅允许固定数字回环地址。");
        accessKey = configuration["Publishing:AccessKey"] ?? throw new InvalidOperationException("缺少对象存储签名配置。");
        signingSecret = configuration["Publishing:SecretKey"] ?? throw new InvalidOperationException("缺少对象存储签名配置。");
        bucket = configuration["Publishing:Bucket"] ?? throw new InvalidOperationException("缺少隔离桶配置。");
        if (bucket.Length is < 3 or > 63 || bucket.Any(value => !char.IsAsciiLetterLower(value) && !char.IsAsciiDigit(value) && value != '-')) throw new InvalidOperationException("桶名称不符合受控格式。");
    }

    /// <summary>条件PUT原子拒绝覆盖，412或409后仍必须GET核对精确字节。</summary>
    public Task<ArtifactObject> PutImmutableAsync(string objectKey, ReadOnlyMemory<byte> content, string contentType, CancellationToken cancellationToken) =>
        WithBudgetAsync(token => PutCoreAsync(objectKey, content, contentType, token), cancellationToken);

    /// <summary>在一次总预算内执行条件写及回验，读取响应体同样受限。</summary>
    private async Task<ArtifactObject> PutCoreAsync(string objectKey, ReadOnlyMemory<byte> content, string contentType, CancellationToken cancellationToken)
    {
        ValidateKey(objectKey);
        if (content.Length > 1024 * 1024) throw new SemanticOperationException(413, "artifact_too_large");
        // 生成当前字节引用，而非信任ETag或调用方散列。
        var artifact = new ArtifactObject { ObjectKey = objectKey, Hash = PublishingRules.Hash(content.Span), SizeBytes = content.Length, ContentType = contentType };
        // S3创建桶操作幂等；既有桶仍由当前签名身份接受后续条件写。
        using var bucketResponse = await SendAsync(HttpMethod.Put, "", ReadOnlyMemory<byte>.Empty, null, false, cancellationToken);
        if (!bucketResponse.IsSuccessStatusCode && bucketResponse.StatusCode != HttpStatusCode.Conflict) throw new SemanticOperationException(503, "artifact_store_unavailable");
        // 条件头也纳入签名，不能被中间层去掉而变成覆盖写。
        using var response = await SendAsync(HttpMethod.Put, objectKey, content, contentType, true, cancellationToken);
        if (!response.IsSuccessStatusCode && response.StatusCode is not HttpStatusCode.PreconditionFailed and not HttpStatusCode.Conflict) throw new SemanticOperationException(503, "artifact_write_failed");
        await ReadCoreAsync(artifact, cancellationToken);
        return artifact;
    }

    /// <summary>流式读取最多一MiB，长度及SHA256都匹配才返回。</summary>
    public Task<byte[]> ReadVerifiedAsync(ArtifactObject artifact, CancellationToken cancellationToken) =>
        WithBudgetAsync(token => ReadCoreAsync(artifact, token), cancellationToken);

    /// <summary>在调用方同一个总预算中完成精确有界流式读取。</summary>
    private async Task<byte[]> ReadCoreAsync(ArtifactObject artifact, CancellationToken cancellationToken)
    {
        ValidateKey(artifact.ObjectKey);
        // 固定GET只读该清单对象；不跟随服务重定向。
        using var response = await SendAsync(HttpMethod.Get, artifact.ObjectKey, ReadOnlyMemory<byte>.Empty, null, false, cancellationToken);
        if (!response.IsSuccessStatusCode) throw new SemanticOperationException(503, "artifact_unavailable");
        // 响应头不能成为唯一预算边界，分块传输也逐块计数。
        await using var input = await response.Content.ReadAsStreamAsync(cancellationToken);
        // 内存缓冲受明确上限约束，源正文不进入日志。
        using var output = new MemoryStream();
        // 每块只用于有界复制。
        var buffer = new byte[8192];
        // 读取计数用于阻止服务端无限流。
        int count;
        while ((count = await input.ReadAsync(buffer, cancellationToken)) != 0)
        {
            if (output.Length + count > 1024 * 1024) throw new SemanticOperationException(503, "artifact_too_large");
            output.Write(buffer, 0, count);
        }
        // 完整字节hash与长度是权威判据，ETag不代表SHA256。
        var bytes = output.ToArray();
        if (bytes.LongLength != artifact.SizeBytes || PublishingRules.Hash(bytes) != artifact.Hash) throw new SemanticOperationException(503, "artifact_hash_mismatch");
        return bytes;
    }

    /// <summary>实现固定us-east-1/s3的SigV4最小协议，响应正文错误不外泄。</summary>
    private async Task<HttpResponseMessage> SendAsync(HttpMethod method, string key, ReadOnlyMemory<byte> content, string? contentType, bool conditional, CancellationToken token)
    {
        // 固定受控段不包含路径穿越或编码歧义。
        var path = "/" + bucket + (key.Length == 0 ? "" : "/" + key);
        // 采用注入时钟生成标准签名时间和日期范围。
        var now = clock.GetUtcNow();
        // AWS规范使用UTC紧凑格式，不能使用当前文化。
        var stamp = now.ToString("yyyyMMdd'T'HHmmss'Z'", CultureInfo.InvariantCulture);
        // 日期范围参与派生密钥。
        var date = now.ToString("yyyyMMdd", CultureInfo.InvariantCulture);
        // payload是原始UTF8字节，不使用不透明unsigned payload。
        var hash = PublishingRules.Hash(content.Span);
        // 规范头按ASCII名称排序。
        var headers = "host:" + endpoint.Authority + "\n" + (conditional ? "if-none-match:*\n" : "") + "x-amz-content-sha256:" + hash + "\nx-amz-date:" + stamp + "\n";
        // 签名包含条件写头，保证不可变前置条件不会被降级。
        var signedHeaders = "host;" + (conditional ? "if-none-match;" : "") + "x-amz-content-sha256;x-amz-date";
        // S3对象路径不重复编码，固定键仅允许安全ASCII。
        var canonical = method.Method + "\n" + path + "\n\n" + headers + "\n" + signedHeaders + "\n" + hash;
        // 固定区域和服务严格对应隔离RustFS配置。
        var scope = date + "/us-east-1/s3/aws4_request";
        // 逐层HMAC派生本次签名密钥，不对外暴露任何中间值。
        var keyBytes = Mac(Mac(Mac(Mac(Encoding.UTF8.GetBytes("AWS4" + signingSecret), date), "us-east-1"), "s3"), "aws4_request");
        // 仅请求头携带签名，审计/异常均不包含该值。
        var signature = Convert.ToHexStringLower(Mac(keyBytes, "AWS4-HMAC-SHA256\n" + stamp + "\n" + scope + "\n" + PublishingRules.Hash(canonical)));
        // 原生请求在响应头到达后返回，随后受控读取内容。
        using var request = new HttpRequestMessage(method, new Uri(endpoint, path));
        request.Headers.TryAddWithoutValidation("x-amz-date", stamp);
        request.Headers.TryAddWithoutValidation("x-amz-content-sha256", hash);
        request.Headers.TryAddWithoutValidation("Authorization", "AWS4-HMAC-SHA256 Credential=" + accessKey + "/" + scope + ", SignedHeaders=" + signedHeaders + ", Signature=" + signature);
        if (conditional) request.Headers.TryAddWithoutValidation("If-None-Match", "*");
        if (method == HttpMethod.Put)
        {
            request.Content = new ByteArrayContent(content.ToArray());
            if (contentType is not null) request.Content.Headers.ContentType = new System.Net.Http.Headers.MediaTypeHeaderValue(contentType);
        }
        try
        {
            return await clients.CreateClient("publishing-s3").SendAsync(request, HttpCompletionOption.ResponseHeadersRead, token);
        }
        catch (HttpRequestException)
        {
            throw new SemanticOperationException(503, "artifact_store_unavailable");
        }
    }

    /// <summary>完整S3操作和响应体共享五秒预算，调用者取消与依赖超时明确区分。</summary>
    private static async Task<T> WithBudgetAsync<T>(Func<CancellationToken, Task<T>> operation, CancellationToken cancellationToken)
    {
        // ResponseHeadersRead不自动覆盖后续body流，显式预算必须传递到每次Read。
        using var budget = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        budget.CancelAfter(TimeSpan.FromSeconds(5));
        try
        {
            return await operation(budget.Token);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
        {
            throw new SemanticOperationException(503, "artifact_store_timeout");
        }
    }

    /// <summary>HMAC中间值只在内存存活，不进入异常或遥测。</summary>
    private static byte[] Mac(byte[] key, string value) => HMACSHA256.HashData(key, Encoding.UTF8.GetBytes(value));

    /// <summary>限制键在发布命名空间且无编码、路径穿越或请求头字符。</summary>
    private static void ValidateKey(string key)
    {
        if (!key.StartsWith("releases/", StringComparison.Ordinal) || key.Length > 240 || key.Any(value => !char.IsAsciiLetterOrDigit(value) && value is not '/' and not '-' and not '.') || key.Split('/').Any(part => part is "" or "." or "..")) throw new SemanticOperationException(422, "artifact_key_invalid");
    }
}
