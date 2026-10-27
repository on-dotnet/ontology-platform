using System.Text.RegularExpressions;
using Aspire.Hosting;
using Aspire.Hosting.ApplicationModel;

namespace OntologyPlatform.AppHost;

/// <summary>把非秘密任务归属绑定到全部开发容器，供准确资源清单识别。</summary>
internal static class ResourceLifecycle
{
    /// <summary>在资源构建之前冻结一次任务和运行标识，兼容直接启动宿主。</summary>
    /// <param name="builder">当前开发宿主构建器。</param>
    internal static void Prepare(IDistributedApplicationBuilder builder)
    {
        // 同一次宿主内唯一镜像构建和普通容器共用同一非秘密归属。
        var task = builder.Configuration["ResourceLifecycle:TaskId"] ?? "DEVELOPMENT";
        // 直接启动也获得稳定到本次宿主生命周期的运行标识。
        var run = builder.Configuration["ResourceLifecycle:RunId"] ?? $"local-{Guid.NewGuid():N}";
        if (!Regex.IsMatch(task, "\\A[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\\z") || !Regex.IsMatch(run, "\\A[A-Za-z0-9][A-Za-z0-9_.-]{0,99}\\z"))
        {
            throw new ArgumentException("资源任务和运行标识不符合安全格式。");
        }
        builder.Configuration["ResourceLifecycle:TaskId"] = task;
        builder.Configuration["ResourceLifecycle:RunId"] = run;
    }

    /// <summary>为所有已注册容器添加精确任务、运行和服务标签，不复制任何秘密配置。</summary>
    /// <param name="builder">已完成资源注册的宿主构建器。</param>
    internal static void Apply(IDistributedApplicationBuilder builder)
    {
        // 只消费Prepare冻结后的非秘密标识，不查看环境或连接字符串。
        var task = builder.Configuration["ResourceLifecycle:TaskId"]!;
        // 同任务不同运行由独立标识区分，不能只凭显示名认领容器。
        var run = builder.Configuration["ResourceLifecycle:RunId"]!;
        // 遍历全部容器而非仅带卷资源，覆盖Keycloak等无专属卷服务。
        foreach (var resource in builder.Resources.OfType<ContainerResource>())
        {
            // Docker标签在创建容器时生效，后验清单以双标签和完整ID验证归属。
            resource.Annotations.Add(new ContainerRuntimeArgsCallbackAnnotation(arguments =>
            {
                arguments.Add("--label");
                arguments.Add($"io.ontology-platform.task-id={task}");
                arguments.Add("--label");
                arguments.Add($"io.ontology-platform.run-id={run}");
                arguments.Add("--label");
                arguments.Add($"io.ontology-platform.service={resource.Name}");
            }));
        }
    }
}
