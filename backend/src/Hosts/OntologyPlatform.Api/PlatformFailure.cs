using System.IO;
using System.Net.Sockets;
using Microsoft.EntityFrameworkCore;
using Npgsql;

namespace OntologyPlatform.Api;

/// <summary>将已知宿主故障转换为固定诊断合同，不保留原始异常或用户输入。</summary>
/// <param name="Category">固定白名单异常类别。</param>
/// <param name="Status">适用的HTTP状态，取消使用仅供诊断的499。</param>
/// <param name="Code">面向客户端的固定错误码，取消不输出正文。</param>
internal readonly record struct PlatformFailure(string Category, int Status, string Code)
{
    /// <summary>只按明确异常类型判定输入、数据库和上游故障，其余均视为内部错误。</summary>
    /// <param name="exception">仅在本次调用栈内观察的故障，不进入遥测。</param>
    /// <param name="requestAborted">真实请求取消信号。</param>
    /// <returns>不含异常详情的安全分类。</returns>
    public static PlatformFailure Classify(Exception exception, CancellationToken requestAborted)
    {
        return exception switch
        {
            OperationCanceledException when requestAborted.IsCancellationRequested => new("request_cancelled", 499, ""),
            InvalidOperationException { InnerException: NpgsqlException database } => Classify(database, requestAborted),
            BadHttpRequestException => new("invalid_request", 400, "invalid_request"),
            DbUpdateException => new("database_write", 503, "dependency_unavailable"),
            NpgsqlException database when IsConnectionFailure(database) => new("database_connection", 503, "dependency_unavailable"),
            NpgsqlException => new("database_failure", 503, "dependency_unavailable"),
            HttpRequestException => new("upstream_unavailable", 503, "dependency_unavailable"),
            _ => new("unexpected_failure", 500, "internal_error")
        };
    }

    /// <summary>只遍历Npgsql已知包装链的有限层数，识别真实网络或连接超时故障。</summary>
    /// <param name="exception">已确认来自数据库驱动的异常。</param>
    /// <returns>存在已知连接故障类型时为真；服务端SQL故障不归此类。</returns>
    private static bool IsConnectionFailure(NpgsqlException exception)
    {
        // PostgreSQL服务端错误已建立连接，不能错误归类为连接不可用。
        if (exception is PostgresException)
        {
            return false;
        }
        // 有界遍历只接受驱动或明确系统包装，不猜测Message或类型名称字符串。
        Exception? current = exception;
        // depth限制异常包装层数，避免任意深度遍历或按原文猜测故障。
        for (var depth = 0; depth < 8 && current is not null; depth++)
        {
            if (current is SocketException or IOException or TimeoutException)
            {
                return true;
            }
            if (current is not NpgsqlException)
            {
                return false;
            }
            current = current.InnerException;
        }
        return false;
    }
}
