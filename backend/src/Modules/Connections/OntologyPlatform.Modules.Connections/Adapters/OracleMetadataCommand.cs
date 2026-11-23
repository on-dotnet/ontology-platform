using System.Data.Common;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using OntologyPlatform.Contracts;
using Oracle.ManagedDataAccess.Client;

namespace OntologyPlatform.Modules.Connections;

/// <summary>在原命令与游标的释放作用域内计量固定元数据操作，不改变驱动调用或追加读取。</summary>
internal sealed class OracleMetadataCommand
{
    /// <summary>按实际游标绑定聚合器，解析器和离线 DataTable 可以共用原读法。</summary>
    private static readonly ConditionalWeakTable<DbDataReader, G4OracleMetadataSpan> Readers = new();

    /// <summary>关闭诊断时不分配持久观察记录。</summary>
    private readonly G4OracleMetadataSpan? span;

    /// <summary>按固定生产方法的调用点建命令，实际 SQL 仍由原方法设置。</summary>
    private OracleMetadataCommand(OracleConnection connection, string statement, bool post)
    {
        Command = connection.CreateCommand();
        span = G4OracleQueryTrace.BeginMetadata(statement, post);
    }

    /// <summary>保留调用体的原始异常，同时等待并单列随后真实发生的释放。</summary>
    internal static async Task<T> RunAsync<T>(OracleConnection connection, string statement, bool post,
        Func<OracleMetadataCommand, Task<T>> action)
    {
        // 固定语句独占一个命令及其释放责任。
        var cost = new OracleMetadataCommand(connection, statement, post);
        // 业务判定或读取已抛出时，后续释放异常仅记入自己的字段。
        var failed = false;
        try { return await action(cost); }
        catch (Exception error)
        {
            failed = true;
            if (cost.span is { CursorError: null } active) active.OperationError ??= Error(error);
            throw;
        }
        finally { cost.Dispose(failed); }
    }

    /// <summary>原生 Oracle 命令及其生产超时保持在原调用方。</summary>
    internal OracleCommand Command { get; }

    /// <summary>事件只公开驱动号、取消或普通异常分类。</summary>
    private static int Error(Exception error) => error switch
    {
        OracleException native => native.Number,
        OperationCanceledException => -1,
        _ => -2
    };

    /// <summary>标量和游标执行共用同一时基，数值和行内容都不进入记录。</summary>
    private async Task<T> ExecuteAsync<T>(Func<Task<T>> execute)
    {
        if (span is null) return await execute();
        span.ExecuteBegin = Stopwatch.GetTimestamp();
        try { return await execute(); }
        catch (Exception error) { span.OperationError = Error(error); throw; }
        finally { span.ExecuteEnd = Stopwatch.GetTimestamp(); }
    }

    /// <summary>权限汇总保持一次原生标量调用。</summary>
    internal Task<object?> ScalarAsync(CancellationToken token) =>
        ExecuteAsync(async () => (object?)await Command.ExecuteScalarAsync(token));

    /// <summary>取得原生游标并将本次实际异步释放与它绑定。</summary>
    internal async Task<T> WithReaderAsync<T>(CancellationToken token, Func<DbDataReader, Task<T>> consume)
    {
        // 取得游标后，操作与关闭的异常分别保存。
        var reader = await ExecuteAsync(() => Command.ExecuteReaderAsync(token));
        if (span is not null) Readers.Add(reader, span);
        var failed = false; // 是否已存在需要原样传播的解析或驱动异常。
        try { return await consume(reader); }
        catch (Exception error)
        {
            failed = true;
            if (span is not null) span.OperationError ??= Error(error);
            throw;
        }
        finally
        {
            if (span is not null) span.CursorDisposeBegin = Stopwatch.GetTimestamp();
            try { await reader.DisposeAsync(); }
            catch (Exception error)
            {
                if (span is not null) span.CursorError = Error(error);
                if (!failed) throw;
            }
            finally
            {
                if (span is not null) { span.CursorDisposeEnd = Stopwatch.GetTimestamp(); Readers.Remove(reader); }
            }
        }
    }

    /// <summary>只计实际调用，短路、标量及取消都不会合成 EOF。</summary>
    internal static async Task<bool> ReadAsync(DbDataReader reader, CancellationToken token)
    {
        if (!Readers.TryGetValue(reader, out var span)) return await reader.ReadAsync(token);
        // 读取累计只覆盖驱动调用，与列解析及命令存活时间分列。
        var start = Stopwatch.GetTimestamp();
        span.ReadCalls++;
        try
        {
            // false 只由实际驱动返回。
            var present = await reader.ReadAsync(token);
            if (present) { span.Rows++; span.FirstRow ??= Stopwatch.GetTimestamp(); }
            else span.Eof = Stopwatch.GetTimestamp();
            return present;
        }
        catch (Exception error) { span.OperationError ??= Error(error); throw; }
        finally { span.ReadTicks += Stopwatch.GetTimestamp() - start; }
    }

    /// <summary>从已读取的身份行提取数值标识；未知值保留为空，不改变原 ACL 判定。</summary>
    internal void CaptureSession(DbDataReader reader)
    {
        if (span is null) return;
        // 投影仅接受本数据库会话给出的正整数，不收集账号或业务值。
        var ids = new ulong[5];
        for (var i = 0; i < ids.Length; i++)
            if (reader.IsDBNull(i + 3) || !ulong.TryParse(reader.GetString(i + 3),
                System.Globalization.NumberStyles.None, System.Globalization.CultureInfo.InvariantCulture, out ids[i]) || ids[i] == 0) return;
        span.Session = ids;
    }

    /// <summary>沿原 using 的实际退出时点计量同步命令释放。</summary>
    private void Dispose(bool failed)
    {
        if (span is not null) span.CommandDisposeBegin = Stopwatch.GetTimestamp();
        try { Command.Dispose(); }
        catch (Exception error)
        {
            if (span is not null) span.CommandError = Error(error);
            if (!failed) throw;
        }
        finally { if (span is not null) span.End = Stopwatch.GetTimestamp(); }
    }
}
