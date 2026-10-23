using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Diagnostics.HealthChecks;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Diagnostics.HealthChecks;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Http.Resilience;
using Microsoft.Extensions.Logging;
using OpenTelemetry;
using OpenTelemetry.Logs;
using OpenTelemetry.Metrics;
using OpenTelemetry.Trace;

namespace OntologyPlatform.ServiceDefaults;

/// <summary>
/// 提供宿主健康、遥测、服务发现与 HTTP 弹性默认值，不承载业务合同。
/// </summary>
public static class ServiceDefaultsExtensions
{
    /// <summary>
    /// 汇总开发宿主共用的技术基础配置。
    /// </summary>
    /// <typeparam name="TBuilder">支持服务注册、配置和日志的宿主构建器类型。</typeparam>
    /// <param name="builder">待配置的宿主构建器。</param>
    /// <returns>原构建器，支持继续配置宿主。</returns>
    public static TBuilder AddServiceDefaults<TBuilder>(this TBuilder builder)
        where TBuilder : IHostApplicationBuilder
    {
        builder.ConfigureOpenTelemetry();
        builder.Services.AddHealthChecks()
            .AddCheck("self", () => HealthCheckResult.Healthy(), ["live"]);
        builder.Services.AddServiceDiscovery();
        builder.Services.ConfigureHttpClientDefaults(http =>
        {
            http.AddStandardResilienceHandler(options =>
            {
                // 非幂等请求不默认重试，避免未来调用者产生重复写入。
                options.Retry.DisableForUnsafeHttpMethods();
            });
            http.AddServiceDiscovery();
        });

        return builder;
    }

    /// <summary>
    /// 注册日志、指标和跟踪，并只在显式配置 OTLP 地址时启用导出。
    /// </summary>
    /// <typeparam name="TBuilder">支持宿主环境和配置的构建器类型。</typeparam>
    /// <param name="builder">待配置遥测的宿主构建器。</param>
    /// <returns>原构建器。</returns>
    public static TBuilder ConfigureOpenTelemetry<TBuilder>(this TBuilder builder)
        where TBuilder : IHostApplicationBuilder
    {
        builder.Logging.AddOpenTelemetry(logging =>
        {
            logging.IncludeFormattedMessage = true;
            logging.IncludeScopes = true;
        });
        builder.Services.AddOpenTelemetry()
            .WithMetrics(metrics =>
            {
                metrics.AddAspNetCoreInstrumentation()
                    .AddHttpClientInstrumentation()
                    .AddRuntimeInstrumentation();
            })
            .WithTracing(tracing =>
            {
                tracing.AddSource(builder.Environment.ApplicationName)
                    .AddAspNetCoreInstrumentation(options =>
                    {
                        // 探针是常规运维请求，不占用业务跟踪采样预算。
                        options.Filter = context =>
                            !context.Request.Path.StartsWithSegments("/health")
                            && !context.Request.Path.StartsWithSegments("/alive");
                    })
                    .AddHttpClientInstrumentation();
            });

        if (!string.IsNullOrWhiteSpace(builder.Configuration["OTEL_EXPORTER_OTLP_ENDPOINT"]))
        {
            builder.Services.AddOpenTelemetry().UseOtlpExporter();
        }

        return builder;
    }

    /// <summary>
    /// 仅在开发环境公开就绪和存活端点。
    /// </summary>
    /// <param name="application">已经构建的 Web 宿主。</param>
    /// <returns>原宿主，支持继续映射端点。</returns>
    public static WebApplication MapDefaultEndpoints(this WebApplication application)
    {
        if (application.Environment.IsDevelopment())
        {
            application.MapHealthChecks("/health");
            application.MapHealthChecks("/alive", new HealthCheckOptions
            {
                Predicate = registration => registration.Tags.Contains("live")
            });
        }

        return application;
    }
}
