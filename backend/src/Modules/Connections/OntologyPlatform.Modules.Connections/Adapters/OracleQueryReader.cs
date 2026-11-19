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
        work.CancelAfter(budget - CleanupLimit);
        // 取消信号与工作线程分别记录第一次进入清理的时间。
        long cleanupStart = 0;
        using var observed = work.Token.Register(() => Interlocked.CompareExchange(ref cleanupStart, Stopwatch.GetTimestamp(), 0));
        // 准确占位在任何物理连接/游标申请之前登记。
        var acquisition = lifetime.BeginSource();
        // 只在真实事务已结束且所有源命令已应答时才允许确认。
        var confirmed = false;
        // 原始行必须在全部后验成功后才能生成业务结果。
        List<OracleMappingRow> raw;
        try
        {
            // 非池化连接只有成功完成 DisposeAsync 才能确认物理释放。
            var connection = await adapter.OpenMappingAsync(secret, Guid.ParseExact(lifetime.ExecutionId, "N"), work.Token);
            try
            {
                // 使用与 M2 发现完全相同的字节口径，再核物理主键与字符语义。
                var shape = await OracleMappingSourceValidator.CheckCatalogAsync(connection, context.CurrentCatalog, work.Token);
                // 已核会话的首条事务内语句是 SET TRANSACTION READ ONLY。
                var tx = await OracleSourceAdapter.BeginMappingAsync(connection, work.Token);
                try
                {
                    try
                    {
                        using (var command = OracleSourceAdapter.CreateMappingCommand(connection, tx, table.Schema == "CaseOwner"))
                        {
                            // Cancel 只指向这条尚存命令；注册先释放并等待回调，随后才可发出其它 SQL。
                            using var cancel = work.Token.Register(() => { try { command.Cancel(); } catch (Exception error) when (error is OracleException or InvalidOperationException) { } });
                            raw = await OracleSourceAdapter.ConsumeMappingAsync(command, work.Token);
                        }
                        await tx.CommitAsync(work.Token);
                    }
                    catch (Exception failure)
                    {
                        // 清理原点取取消和实际异常中最早者；不把无权观察的异常当作源终态。
                        Interlocked.CompareExchange(ref cleanupStart, Stopwatch.GetTimestamp(), 0);
                        // 允许已取消的工作归还源事务，绝不超过原分支、请求和首次取消 250ms。
                        var left = RemainingCleanup(origin, budget, Volatile.Read(ref cleanupStart));
                        if (left <= TimeSpan.Zero) throw;
                        using var cleanup = new CancellationTokenSource(left);
                        await tx.RollbackAsync(cleanup.Token);
                        confirmed = failure is OracleException { Number: 1013 }
                            or OperationCanceledException { InnerException: OracleException { Number: 1013 } };
                        throw;
                    }
                }
                finally
                {
                    try { await tx.DisposeAsync(); }
                    catch { confirmed = false; throw; }
                }
                // 事务已结束，权限/目录后验不会误用冻结快照。
                await OracleSourceAdapter.VerifyMappingAccessAsync(connection, work.Token);
                if (await OracleMappingSourceValidator.CheckCatalogAsync(connection, context.CurrentCatalog, work.Token) != shape) throw Invalid();
                work.Token.ThrowIfCancellationRequested();
                Interlocked.CompareExchange(ref cleanupStart, Stopwatch.GetTimestamp(), 0);
                confirmed = true;
            }
            finally
            {
                try { await connection.DisposeAsync(); }
                catch { confirmed = false; throw; }
            }
        }
        catch (OperationCanceledException) when (token.IsCancellationRequested) { throw; }
        catch (Exception failure) when (failure is OperationCanceledException or OracleException { Number: 1013 })
        { throw Timeout(); }
        catch (OracleException failure) when (failure.Number == 1031) { throw new SemanticOperationException(403, "query_source_forbidden"); }
        catch (Exception failure) when (failure is OracleException or PgSourceException or InvalidCastException or OverflowException)
        { throw new SemanticOperationException(503, "query_source_unavailable"); }
        finally
        {
            if (confirmed && RemainingCleanup(origin, budget, Volatile.Read(ref cleanupStart)) > TimeSpan.Zero)
                lifetime.ConfirmReleased(acquisition);
        }
        if (!lifetime.CleanupConfirmed || work.IsCancellationRequested) throw Timeout();
        // 第 101 行没有全集证明；物理键未进入业务身份，不能暗示完整命中。
        var sentinel = raw.Count > 100;
        // 所有范围和业务约束先核再投影，绝不向调用者返回其它范围的行。
        var projected = new List<Dictionary<string, G4QueryValue>>();
        foreach (var row in raw.Take(100))
        {
            if (row.Organization != context.Scope.OrganizationId || !context.Scope.SiteIds.Contains(row.Site, StringComparer.Ordinal))
                throw new SemanticOperationException(403, "query_source_forbidden");
            // 通用 Query 也使用同一套精确目录解释，不把数值或时间默转字符串。
            var cells = OracleMappingSourceValidator.Cells(row, table);
            // 每个生产分支返回稳定按非空 PK 排序的有界实际投影。
            var values = table.Fields.ToDictionary(f => f.Name, f => Scalar(cells[f.Name], f, temporal), StringComparer.Ordinal);
            if (branch is null && query.Filters.EntityExternalId is string external && !StringComparer.Ordinal.Equals(row.External, external)) continue;
            if (query.Filters.ValidFrom is string from && query.Filters.ValidTo is string to
                && (PgQueryReader.Epoch(values["FROM_TS"].Lexical!) >= PgQueryReader.Epoch(to)
                    || PgQueryReader.Epoch(values["TO_TS"].Lexical!) <= PgQueryReader.Epoch(from))) continue;
            if (branch is not null && !branch.Parents.Rows.Any(parent => Matches(parent, values))) continue;
            projected.Add(values);
        }
        if (branch is not null && branch.Parents.Rows.Any(p => projected.Count(v => Matches(p, v)) > 10))
            throw new SemanticOperationException(503, "query_source_budget_exhausted");
        if (Stopwatch.GetElapsedTime(origin) >= budget || work.IsCancellationRequested) throw Timeout();
        return new G4SourceQueryRead { EntityBindingId = entity.Id, Rows = projected.Take(query.MaxRows).ToArray(), RecordKeyFields = ["ROW_ID"],
            StartedAtUtc = start, CompletedAtUtc = DateTimeOffset.UtcNow, AdapterVersion = "oracle-query-v1", WatermarkKind = "UNKNOWN", Watermark = null,
            Indeterminate = sentinel, Limited = sentinel || projected.Count > query.MaxRows, QueryPlanHash = MappingValidationService.Digest(new
            { adapterVersion = "oracle-query-v1", table.Schema, table.Name, table.Fields, entity.Id, context.Binding, context.Scope, query.Filters,
                query.MaxRows, relation = branch?.RelationId, parentPlan = branch?.Parents.QueryPlanHash, parents = branch?.Parents.Rows }) };
    }

    /// <summary>原分支余量、原请求余量及从首次取消起的绝对清理余量取最小值。</summary>
    private static TimeSpan RemainingCleanup(long origin, TimeSpan budget, long cleanupStart) =>
        new[] { budget - Stopwatch.GetElapsedTime(origin), CleanupLimit - Stopwatch.GetElapsedTime(cleanupStart),
            G4RequestDeadline.Current?.Remaining ?? TimeSpan.Zero, G4OracleSourceLifetime.Current?.CleanupRemaining ?? CleanupLimit }.Min();

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
