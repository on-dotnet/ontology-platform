using System.Data.Common;
using System.Diagnostics;
using System.Globalization;
using OntologyPlatform.Contracts;
using Oracle.ManagedDataAccess.Client;

namespace OntologyPlatform.Modules.Connections;

/// <summary>由已发布 Oracle 映射生成有界实体和关系投影，共享原始请求与源分支期限。</summary>
internal static class OracleQueryReader
{
    /// <summary>工作与清理共用一秒，其中最后 250 毫秒只供确认清理。</summary>
    private static readonly TimeSpan CleanupLimit = TimeSpan.FromMilliseconds(250);

    /// <summary>绑定正式平台 QueryId 和 Oracle 执行身份，直到物理释放确认才交回分支容量。</summary>
    internal static async Task<G4SourceQueryRead> ReadEntityAsync(OracleSourceAdapter adapter, OracleConnectionProfile profile,
        string secret, G4QueryBindingContext context, string entityId, G4SemanticQuery query, G4QueryBranchFilter? branch,
        DateTimeOffset deadline, CancellationToken token)
    {
        // 精确投影、范围及冻结时间策略在申请物理资源前验证。
        OracleAdapterOptions.Validate(profile, context.Scope);
        // 只允许本次 manifest 给出的实体、时间、身份与关系。
        var mapping = context.Manifest.Mapping;
        // 字段标识与 original/current 两份目录都必须吻合。
        var entity = mapping.Entities.SingleOrDefault(e => e.Id == entityId) ?? throw Invalid();
        // 大小写敏感的目标身份决定使用两个固定语句中的哪一个。
        var table = OracleMappingSourceValidator.EntityTable(entity, context.OriginalCatalog, context.CurrentCatalog, mapping);
        // 源时间不得从会话或宿主默认时区解释。
        var temporal = mapping.TemporalSpecs.Single(t => t.Id == entity.TemporalSpecId);
        if (!OracleMappingSourceValidator.SupportsEntityPlan(entity, mapping.IdentitySpecs.Single(i => i.Id == entity.IdentitySpecId), temporal)
            || (table.Schema == "CaseOwner") != (branch is not null)) throw Invalid();
        if (branch is not null)
        {
            // 发布时确认的方向、精确键与半开窗口在读目标表前再核。
            var relation = mapping.Relations.SingleOrDefault(r => r.Id == branch.RelationId) ?? throw Invalid();
            if (!OracleMappingSourceValidator.SupportsRelation(mapping, relation) || relation.ToBindingId != entity.Id
                || branch.Parents.EntityBindingId != relation.FromBindingId || branch.Parents.AdapterVersion != "oracle-query-v1"
                || branch.Parents.Indeterminate || branch.Parents.Limited || branch.Parents.Rows.Length is < 1 or > 100) throw Invalid();
        }
        // 身份及绝对期限由查询宿主在正式分支调度前建立。
        var lifetime = G4OracleSourceLifetime.Current ?? throw Invalid();
        // 暴露给证据的起点与单调预算同时采集。
        var start = DateTimeOffset.UtcNow;
        // 原绝对期限和当前入口余量取更紧者，禁止执行器另开五秒窗口。
        var remaining = new[] { deadline - start, G4RequestDeadline.Current?.Remaining ?? TimeSpan.Zero }.Min();
        // 总期限内保留后续平台事务的 500ms，不能由源工作消费。
        var budget = new[] { TimeSpan.FromSeconds(1), remaining - TimeSpan.FromMilliseconds(500) }.Min();
        if (budget <= CleanupLimit) throw Timeout();
        // 无论上游或观察器先取消，工作都在原分支中预留同一段清理时间。
        using var work = CancellationTokenSource.CreateLinkedTokenSource(token, G4RequestDeadline.Current!.Token);
        // 单调预算同时约束回滚和物理释放后验。
        var origin = Stopwatch.GetTimestamp();
        using var readerCutoff = new CancellationTokenSource(TimeSpan.FromTicks(Math.Max(0, (budget - CleanupLimit - Stopwatch.GetElapsedTime(origin)).Ticks)));
        using var readerSignal = readerCutoff.Token.Register(() =>
        {
            G4OracleQueryTrace.Mark("readerCutoff", "signal");
            work.Cancel();
        });
        // 目录前态与后验绑定同一非池化连接和同次真实核验。
        string? shape = null;
        // 已发布固定语句的行在所有后验结束前不会用于业务交付。
        List<OracleMappingRow> raw;
        try
        {
            raw = await ReadOwnedAsync(lifetime,
                () => adapter.OpenMappingAsync(secret, Guid.ParseExact(lifetime.ExecutionId, "N"), work.Token, verifyAccess: false),
                async connection =>
                {
                    // 权限元数据及其游标全部返回后，明确拒绝在已持有连接上进入物理清理。
                    if (!await G4OracleQueryTrace.ObserveAsync("readOnly", () => OracleSourceAdapter.MappingAccessMatchesAsync(connection, work.Token)))
                    {
                        G4OracleQueryTrace.Mark("readOnly", "failed");
                        throw new AccessRejectedException();
                    }
                    shape = await G4OracleQueryTrace.ObserveAsync("catalog", () => OracleMappingSourceValidator.CheckCatalogAsync(connection, context.CurrentCatalog, work.Token));
                    await G4OracleQueryTrace.ObserveAsync("session", () => adapter.RecordQuerySessionAsync(connection, lifetime, work.Token));
                    return await OracleSourceAdapter.BeginMappingAsync(connection, work.Token);
                },
                (connection, tx, native, cancelling) => ReadCommandAsync(adapter, connection, tx, table.Schema == "CaseOwner",
                    lifetime, work.Token, native, cancelling),
                async connection =>
                {
                    await OracleSourceAdapter.VerifyMappingAccessAsync(connection, work.Token);
                    work.Token.ThrowIfCancellationRequested();
                    if (await OracleMappingSourceValidator.CheckCatalogAsync(connection, context.CurrentCatalog, work.Token) != shape)
                        throw Invalid();
                },
                () => adapter.QueryEvent("PHYSICAL_RELEASE", lifetime), work.Token, origin, budget,
                (phase, acquisition) => adapter.QueryOwnership(phase, lifetime, acquisition),
                point => adapter.QueryCleanup(lifetime, point));
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { throw; }
        catch (Exception failure) when (failure is OperationCanceledException or OracleException { Number: 1013 })
        { throw Timeout(); }
        catch (AccessRejectedException) { throw new SemanticOperationException(503, "query_source_unavailable"); }
        catch (OracleException failure) when (failure.Number == 1031) { throw new SemanticOperationException(403, "query_source_forbidden"); }
        catch (Exception failure) when (failure is OracleException or PgSourceException or InvalidCastException or OverflowException)
        { throw new SemanticOperationException(503, "query_source_unavailable"); }
        if (!lifetime.CleanupConfirmed || work.IsCancellationRequested) throw Timeout();
        // 第 101 行没有全集证明；物理键未进入业务身份，不能暗示完整命中。
        var sentinel = raw.Count > 100;
        // 完整行集先核类型、范围与业务身份，再按请求筛选，防止筛掉另一父项后掩盖基数冲突。
        var complete = new List<Dictionary<string, G4QueryValue>>();
        foreach (var row in raw.Take(100))
        {
            if (row.Organization != context.Scope.OrganizationId || !context.Scope.SiteIds.Contains(row.Site, StringComparer.Ordinal))
                throw new SemanticOperationException(403, "query_source_forbidden");
            // 正式 Mapping 和 Query 使用相同精确类型转换；所有列均在完整 grant 内。
            var cells = OracleMappingSourceValidator.Cells(row, table);
            complete.Add(table.Fields.ToDictionary(f => f.Name, f => Scalar(cells[f.Name], f, temporal), StringComparer.Ordinal));
        }
        DemandCompleteIdentity(complete);
        // 完整性集合和对外有界投影共用一份行对象，不复制原始业务标量。
        var projected = complete.Where(values =>
            (branch is not null || query.Filters.EntityExternalId is not string external || StringComparer.Ordinal.Equals(values["EXT_ID"].Lexical, external))
            && (query.Filters.ValidFrom is not string from || query.Filters.ValidTo is not string to
                || PgQueryReader.Epoch(values["FROM_TS"].Lexical!) < PgQueryReader.Epoch(to)
                && PgQueryReader.Epoch(values["TO_TS"].Lexical!) > PgQueryReader.Epoch(from))
            && (branch is null || branch.Parents.Rows.Any(parent => Matches(parent, values)))).ToList();
        if (branch is not null)
        {
            // 同次完整根行集由内部载体携带；不可回读另一事务或只使用已筛选的父行猜测唯一性。
            var parents = branch.Parents.OracleIntegrityRows ?? throw Invalid();
            DemandCompleteIdentity(parents);
            if (parents.Length > 100 || branch.Parents.Rows.Any(selected => !parents.Any(parent =>
                MappingCanonical.Serialize(parent).AsSpan().SequenceEqual(MappingCanonical.Serialize(selected))))) throw Invalid();
            DemandRelationIntegrity(parents, complete);
        }
        // 两个固定表的完整性行均受同一四MiB工作集上限，且未进入公开规范字节。
        if (MappingCanonical.Serialize(complete).Length + (branch is null ? 0 : MappingCanonical.Serialize(branch.Parents.OracleIntegrityRows).Length) > 4 * 1024 * 1024)
            throw new SemanticOperationException(503, "query_source_budget_exhausted");
        if (Stopwatch.GetElapsedTime(origin) >= budget || work.IsCancellationRequested) throw Timeout();
        return new G4SourceQueryRead { EntityBindingId = entity.Id, Rows = projected.Take(query.MaxRows).ToArray(), OracleIntegrityRows = branch is null && !sentinel ? complete.ToArray() : null, RecordKeyFields = ["ROW_ID"],
            StartedAtUtc = start, CompletedAtUtc = DateTimeOffset.UtcNow, AdapterVersion = "oracle-query-v1", WatermarkKind = "UNKNOWN", Watermark = null,
            Indeterminate = sentinel, Limited = sentinel || projected.Count > query.MaxRows, QueryPlanHash = MappingValidationService.Digest(new
            { adapterVersion = "oracle-query-v1", table.Schema, table.Name, table.Fields, entity.Id, context.Binding, context.Scope, query.Filters,
                query.MaxRows, relation = branch?.RelationId, parentPlan = branch?.Parents.QueryPlanHash, parents = branch?.Parents.Rows, parentIntegrity = branch?.Parents.OracleIntegrityRows, integrity = complete }) };
    }

    /// <summary>完整有界集合中同一业务身份的交叠区间不能被请求过滤隐藏；不相交历史版本仍可用于消歧。</summary>
    internal static void DemandCompleteIdentity(IReadOnlyList<Dictionary<string, G4QueryValue>> rows)
    {
        if (rows.Count > 100) throw Invalid();
        for (var left = 0; left < rows.Count; left++) // 左侧真实行的序号。
        {
            for (var right = left + 1; right < rows.Count; right++) // 仅比较未检查过的另一真实行。
            {
                if (new[] { "ORG_ID", "SITE_ID", "EXT_ID" }.All(name => StringComparer.Ordinal.Equals(rows[left][name].Lexical, rows[right][name].Lexical))
                    && Overlaps(rows[left], rows[right])) throw new SemanticOperationException(503, "query_source_indeterminate");
            }
        }
    }

    /// <summary>目标不能属于两个时间交叠的父项；十条正常扇出允许，十一条不得输出多余边。</summary>
    internal static void DemandRelationIntegrity(IReadOnlyList<Dictionary<string, G4QueryValue>> parents, IReadOnlyList<Dictionary<string, G4QueryValue>> targets)
    {
        if (parents.Count is < 1 or > 100 || targets.Count > 100) throw Invalid();
        if (parents.Count * targets.Count > 1000) throw new SemanticOperationException(503, "query_source_budget_exhausted");
        DemandCompleteIdentity(targets);
        foreach (var target in targets) // 同次有界读取的完整目标集合中的当前行。
        {
            // 完整根集中的候选父项包括被外部号过滤排除的行。
            var matches = parents.Where(parent => Matches(parent, target)).ToArray();
            for (var left = 0; left < matches.Length; left++) // 首个候选父项的序号。
            {
                for (var right = left + 1; right < matches.Length; right++) // 另一候选父项的序号。
                {
                    if (Overlaps(matches[left], matches[right])) throw new SemanticOperationException(503, "query_source_indeterminate");
                }
            }
        }
        if (parents.Any(parent => targets.Count(target => Matches(parent, target)) > 10))
            throw new SemanticOperationException(503, "query_source_budget_exhausted");
    }

    /// <summary>业务时间按整数纳秒比较半开交叠，不能把接壤误作冲突。</summary>
    private static bool Overlaps(Dictionary<string, G4QueryValue> left, Dictionary<string, G4QueryValue> right) =>
        PgQueryReader.Epoch(left["FROM_TS"].Lexical!) < PgQueryReader.Epoch(right["TO_TS"].Lexical!)
        && PgQueryReader.Epoch(right["FROM_TS"].Lexical!) < PgQueryReader.Epoch(left["TO_TS"].Lexical!);

    /// <summary>仅表示前置权限元数据及其资源已完整返回后的明确拒绝，不代表连接已释放。</summary>
    internal sealed class AccessRejectedException : Exception
    {
    }

    /// <summary>正式 Oracle reader 独占连接、业务事务和后续核验，确认发生在物理释放返回后。</summary>
    internal static async Task<List<OracleMappingRow>> ReadOwnedAsync<TConnection, TTransaction>(
        G4OracleSourceLifetime lifetime, Func<Task<TConnection>> open, Func<TConnection, Task<TTransaction>> begin,
        Func<TConnection, TTransaction, Action<Exception>, Action, Task<List<OracleMappingRow>>> read, Func<TConnection, Task> verifyAfter,
        Action released, CancellationToken work, long origin, TimeSpan budget, Action<string, Guid>? report = null,
        Action<CleanupObservation>? reportCleanup = null)
        where TConnection : IAsyncDisposable where TTransaction : DbTransaction
    {
        // 已取消的工作不能新开源；申请号随下列每个物理观察一同记录。
        work.ThrowIfCancellationRequested();
        var acquisition = lifetime.BeginSource();
        G4OracleQueryTrace.Mark("acquisition", "returned", acquisition);
        // 捕获正式请求，其他线程上的定向取消也复用该原期限。
        var request = G4RequestDeadline.Current;
        // 取消信号和工作线程共用最早清理起点，不能从回滚另起预算。
        long cleanupStart = 0;
        // 跨线程的 UTC 证据只能向前收紧；真正放行使用原单调时基。
        long earliestUtc = DateTimeOffset.MaxValue.UtcTicks;
        TimeSpan Left() => new[] { budget - Stopwatch.GetElapsedTime(origin),
            CleanupLimit - Stopwatch.GetElapsedTime(Volatile.Read(ref cleanupStart)),
            request?.Remaining ?? TimeSpan.Zero, lifetime.CleanupRemaining ?? CleanupLimit }.Min();
        void Record(string trigger)
        {
            if (reportCleanup is null) return;
            // 先读 UTC，再扣实际单调耗时，由此计算跨进程比较可用的保守截止。
            var utc = DateTimeOffset.UtcNow;
            var candidate = utc.Add(Left()).UtcTicks;
            long prior;
            do
            {
                prior = Volatile.Read(ref earliestUtc);
                candidate = Math.Min(candidate, prior);
            } while (Interlocked.CompareExchange(ref earliestUtc, candidate, prior) != prior);
            reportCleanup(new CleanupObservation(trigger, acquisition, utc, new DateTimeOffset(candidate, TimeSpan.Zero), candidate - utc.UtcTicks));
        }
        void StartCleanup(string trigger)
        {
            // 先登记本线程看到的单调戳，若另一线程更早进入则沿用其已消耗的时间。
            var stamp = Stopwatch.GetTimestamp();
            var previous = Interlocked.CompareExchange(ref cleanupStart, stamp, 0);
            lifetime.TightenCleanup(CleanupLimit - Stopwatch.GetElapsedTime(previous == 0 ? stamp : previous));
            G4OracleQueryTrace.Mark("cleanupStart", acquisition: acquisition, originTick: previous == 0 ? stamp : previous);
            Record(trigger);
        }
        report?.Invoke("ACQUIRED", acquisition);
        using var observed = work.Register(() => StartCleanup("WORK_CANCELLED"));
        // 只有业务命令终止、事务结算且无未经确认的后验工作时，才有资格进一步验证物理释放。
        var confirmed = false;
        try
        {
            // 打开成功后由本方法持有到物理 Dispose 返回。
            var connection = await open();
            try
            {
                // 业务读取与事务清理由一个顺序执行者负责。
                TTransaction tx;
                try { tx = await begin(connection); }
                catch (AccessRejectedException)
                {
                    // 只有完整前置拒绝且未取消的工作能进入已知终态；尚未建立任何业务事务。
                    work.ThrowIfCancellationRequested();
                    confirmed = true;
                    throw;
                }
                // 在事务与后验都返回后才可交付这些行。
                List<OracleMappingRow> rows;
                // 只有读取任务返回（含游标和命令 Dispose）才能记录自然结束。
                var readReturned = false;
                // 记录准确业务调用报告的原异常，防止把其他命令或 Dispose 的 1013 误作其终态。
                Exception? nativeTermination = null;
                try
                {
                    try
                    {
                        rows = await G4OracleQueryTrace.ObserveAsync("execute", () => read(connection, tx, error => nativeTermination = error, () => StartCleanup("DIRECTED_CANCEL")));
                        readReturned = true;
                        report?.Invoke("READ_RETURNED", acquisition);
                        work.ThrowIfCancellationRequested();
                        await G4OracleQueryTrace.ObserveAsync("commit", () => tx.CommitAsync(work));
                        report?.Invoke("COMMITTED", acquisition);
                    }
                    catch (Exception failure)
                    {
                        StartCleanup("WORK_FAILURE");
                        // 回滚使用原分支、请求和首次取消窗口中剩余的最小值。
                        var left = Left();
                        if (left <= TimeSpan.Zero) throw;
                        using var cleanup = new CancellationTokenSource(left);
                        await G4OracleQueryTrace.ObserveAsync("rollback", () => tx.RollbackAsync(cleanup.Token));
                        report?.Invoke("ROLLED_BACK", acquisition);
                        confirmed = readReturned || (ReferenceEquals(failure, nativeTermination) && OracleSourceAdapter.IsNativeCancel(failure));
                        throw;
                    }
                }
                finally
                {
                    try
                    {
                        await G4OracleQueryTrace.ObserveAsync("disposeTransaction", () => tx.DisposeAsync().AsTask());
                        report?.Invoke("TX_DISPOSED", acquisition);
                    }
                    catch { confirmed = false; throw; }
                }
                // 已提交并释放事务，若取消已经生效就直接归还连接，不再发后验源读。
                confirmed = true;
                work.ThrowIfCancellationRequested();
                // 后验一旦开始便需独立等它返回；任意中断、读取或游标异常都保留未知。
                confirmed = false;
                report?.Invoke("POST_STARTED", acquisition);
                await G4OracleQueryTrace.ObserveAsync("postcheck", () => verifyAfter(connection));
                report?.Invoke("POST_RETURNED", acquisition);
                confirmed = true;
                // 健康读取仍只在本地度量物理释放。若释放本身失败，则向持有人传递这个已用起点。
                Interlocked.CompareExchange(ref cleanupStart, Stopwatch.GetTimestamp(), 0);
                G4OracleQueryTrace.Mark("cleanupStart", acquisition: acquisition, originTick: Volatile.Read(ref cleanupStart));
                work.ThrowIfCancellationRequested();
                return rows;
            }
            catch
            {
                // 包括后验和事务释放异常，物理连接 Dispose 消耗的时间不能从持有人窗口漏掉。
                StartCleanup("RESOURCE_FAILURE");
                throw;
            }
            finally
            {
                try
                {
                    try { Record("PHYSICAL_DISPOSE"); }
                    finally { await G4OracleQueryTrace.ObserveAsync("disposeConnection", () => connection.DisposeAsync().AsTask()); }
                    released();
                    report?.Invoke("PHYSICAL_DISPOSED", acquisition);
                }
                catch
                {
                    StartCleanup("RESOURCE_FAILURE");
                    confirmed = false;
                    throw;
                }
            }
        }
        finally
        {
            // 最终采样在所有源资源返回后；日志输出本身的耗时仍计入正式确认。
            if (confirmed) Record("FINAL");
            if (confirmed && Left() > TimeSpan.Zero)
            {
                lifetime.ConfirmReleased(acquisition);
                report?.Invoke("CONFIRMED", acquisition);
            }
        }
    }

    /// <summary>在该次固定命令上注册定向取消并等待游标及命令退出，之后才允许事务结算。</summary>
    private static async Task<List<OracleMappingRow>> ReadCommandAsync(OracleSourceAdapter adapter, OracleConnection connection,
        OracleTransaction tx, bool target, G4OracleSourceLifetime lifetime, CancellationToken token, Action<Exception> nativeReturned, Action cancelling)
    {
        // 只有业务执行或取行本身报告的异常能在游标和命令都释放后用于原生确认。
        Exception? native = null;
        try
        {
            // 注册先释放并等待回调，随后才销毁本次命令或发出其它 SQL。
            using var command = OracleSourceAdapter.CreateMappingCommand(connection, tx, target);
            using var cancel = token.Register(() =>
            {
                // 同步驱动 Cancel 也消耗最早 250ms，不能等它返回后才开始计时。
                cancelling();
                adapter.QueryEvent("CANCEL_ENTER", lifetime);
                try
                {
                    command.Cancel();
                    adapter.QueryEvent("CANCEL_RETURN", lifetime);
                }
                catch (Exception error) when (error is OracleException or InvalidOperationException)
                {
                    adapter.QueryEvent("CANCEL_REJECT", lifetime);
                }
            });
            adapter.QueryEvent("EXECUTE", lifetime);
            return await OracleSourceAdapter.ConsumeMappingAsync(command, token, () => adapter.QueryEvent("EOF", lifetime),
                error => native = error);
        }
        catch (Exception error) when (ReferenceEquals(error, native))
        {
            adapter.QueryEvent("NATIVE_1013", lifetime);
            nativeReturned(error);
            throw;
        }
    }

    /// <summary>仅用于关联准确申请的已扣单调耗时；允许零和负余量来说明无法确认。</summary>
    /// <param name="Trigger">本次采样所属的封闭清理阶段。</param>
    /// <param name="Acquisition">当前准确申请身份。</param>
    /// <param name="Utc">读取单调余量之前的 UTC 下界。</param>
    /// <param name="DeadlineUtc">同申请所有已知期限的最早保守 UTC 上界。</param>
    /// <param name="RemainingTicks">上界减该次 UTC 值，以一百纳秒刻度记录。</param>
    internal readonly record struct CleanupObservation(string Trigger, Guid Acquisition, DateTimeOffset Utc,
        DateTimeOffset DeadlineUtc, long RemainingTicks);

    /// <summary>同组织与厂区的精确 NUMBER 等值及半开区间；数据库 NULL 永不组成边。</summary>
    internal static bool Matches(Dictionary<string, G4QueryValue> parent, Dictionary<string, G4QueryValue> target)
    {
        if (parent["JOIN_KEY"] is G4NullValue || target["JOIN_KEY"] is G4NullValue) return false;
        if (parent["JOIN_KEY"] is not G4DecimalValue { Precision: 12, Scale: 1 } a || target["JOIN_KEY"] is not G4DecimalValue { Precision: 13, Scale: 2 } b)
            throw Invalid();
        return parent["ORG_ID"].Lexical == target["ORG_ID"].Lexical && parent["SITE_ID"].Lexical == target["SITE_ID"].Lexical
            && decimal.Parse(a.Lexical!, CultureInfo.InvariantCulture) == decimal.Parse(b.Lexical!, CultureInfo.InvariantCulture)
            && PgQueryReader.Epoch(parent["FROM_TS"].Lexical!) < PgQueryReader.Epoch(target["TO_TS"].Lexical!)
            && PgQueryReader.Epoch(target["FROM_TS"].Lexical!) < PgQueryReader.Epoch(parent["TO_TS"].Lexical!);
    }

    /// <summary>按原始元数据产出已有 wire 的标量，将缺值与空字符串、数值零分开。</summary>
    private static G4QueryValue Scalar(MappingSourceCell cell, CatalogField field, MappingTemporalSpec temporal) => cell.Value switch
    {
        null when field.Nullable => new G4NullValue { DeclaredType = field.NativeType == "VARCHAR2" ? "string" : "decimal", Lexical = null },
        string s when cell.NativeType == "NUMBER(18,0)" => new G4Int64Value { Lexical = s },
        string s when field.NativeType == "NUMBER" => DorisMappingTypeRules.DecimalValue(s, field.Precision!.Value, field.Scale!.Value),
        string s when field.NativeType == "VARCHAR2" => new G4StringValue { Lexical = s },
        string s when field.NativeType == "TIMESTAMP(6)" => new G4UtcValue
        { Lexical = DorisMappingTypeRules.Instant(s, temporal).ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'", CultureInfo.InvariantCulture) },
        _ => throw Invalid()
    };

    /// <summary>冻结映射与请求不匹配。</summary>
    private static SemanticOperationException Invalid() => new(422, "query_source_plan_invalid");

    /// <summary>在既有时限内无法保证完整源结果。</summary>
    private static SemanticOperationException Timeout() => new(503, "query_source_timeout");
}
