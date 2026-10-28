using System.Diagnostics;
using Aspire.Hosting;
using Aspire.Hosting.ApplicationModel;

namespace OntologyPlatform.AppHost;

/// <summary>通过唯一内容寻址构建入口取得可复用的本地Fuseki镜像。</summary>
internal static class CanonicalFusekiImage
{
    /// <summary>先验证或构建固定上下文镜像，再以普通容器引用同一结果。</summary>
    /// <param name="builder">当前开发宿主构建器。</param>
    /// <returns>复用已校验镜像的Fuseki容器资源。</returns>
    /// <exception cref="InvalidOperationException">唯一构建入口失败或返回非法引用。</exception>
    internal static IResourceBuilder<ContainerResource> Add(IDistributedApplicationBuilder builder)
    {
        // 从AppHost工程位置解析仓库内唯一构建脚本，避免工作目录影响上下文。
        var root = Path.GetFullPath(Path.Combine(builder.AppHostDirectory, "../../.."));
        // Python标准库入口被工程验收和AppHost共同调用，不再让Aspire生成第二镜像标签。
        var start = new ProcessStartInfo(OperatingSystem.IsWindows() ? "python" : "python3")
        {
            WorkingDirectory = root,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        start.ArgumentList.Add(Path.Combine(root, "scripts/maintenance/canonical_fuseki.py"));
        start.ArgumentList.Add("--image-only");
        // 跨宿主调用复用按构建输入和引擎环境绑定的失败提示，每次仍独立短探测。
        start.ArgumentList.Add("--failure-state");
        start.ArgumentList.Add(Path.Combine(root, "artifacts/fuseki-failures"));
        start.ArgumentList.Add("--task-id");
        start.ArgumentList.Add(builder.Configuration["ResourceLifecycle:TaskId"] ?? "DEVELOPMENT");
        start.ArgumentList.Add("--run-id");
        start.ArgumentList.Add(builder.Configuration["ResourceLifecycle:RunId"] ?? $"local-{Guid.NewGuid():N}");
        // 构建调用只传非秘密归属标识，不传开发运行时凭证。
        using var process = Process.Start(start) ?? throw new InvalidOperationException("无法启动唯一Fuseki构建入口。");
        // 并行排空输出管道以避免Docker构建输出造成子进程阻塞。
        var output = process.StandardOutput.ReadToEndAsync();
        // 原始错误可能包含机器路径，仅消费而不输出到宿主日志。
        var error = process.StandardError.ReadToEndAsync();
        process.WaitForExit();
        error.GetAwaiter().GetResult();
        // 只接受固定仓库和完整SHA256上下文标签，禁止外部参数切换镜像来源。
        var image = output.GetAwaiter().GetResult().Trim();
        if (process.ExitCode != 0 || !System.Text.RegularExpressions.Regex.IsMatch(image, "^ontology-platform-fuseki:context-[0-9a-f]{64}$"))
        {
            throw new InvalidOperationException("唯一Fuseki构建入口未通过；请先运行scripts/maintenance/canonical_fuseki.py排查本地Docker前提。");
        }
        return builder.AddContainer("fuseki", "ontology-platform-fuseki", image.Split(':')[1]);
    }
}
