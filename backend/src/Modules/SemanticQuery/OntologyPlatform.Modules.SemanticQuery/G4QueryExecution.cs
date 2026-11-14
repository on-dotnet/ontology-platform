using System.Globalization;
using System.Text;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.SemanticQuery;

/// <summary>固定映射到查询判别结果的执行边界，保持源精度且不创建假的RDF图来源。</summary>
public sealed class G4QueryExecution
{
    /// <summary>固定材料只由Connections模块读取。</summary>
    private readonly IG4QueryBindingReader bindings;

    /// <summary>唯一类型化只读源执行端口。</summary>
    private readonly IG4SourceQueryReader source;

    /// <summary>当前服务器会话和完整字段授权。</summary>
    private readonly IG4QueryAuthorizationAuthority authority;

    /// <summary>跨实例持久执行与恢复边界。</summary>
    private readonly G4QueryResultStore store;

    /// <summary>与总预算和租约共用的服务器时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>正式DI组合现有模块参与者，不绕过公共Gateway或Guard。</summary>
    public G4QueryExecution(IG4QueryBindingReader bindings, IG4SourceQueryReader source, IG4QueryAuthorizationAuthority authority,
        G4QueryResultStore store, TimeProvider clock)
    {
        this.bindings = bindings;
        this.source = source;
        this.authority = authority;
        this.store = store;
        this.clock = clock;
    }

    /// <summary>S1单实体映射的完整执行；正式本体已经由同Gateway按真实源校验。</summary>
    internal async Task<G4QueryDelivery> ExecuteAsync(ActorContext actor, string sessionReference, G4SemanticQuery query,
        string key, string? selectionQueryId, PublishedGraph ontology, DateTimeOffset deadline,
        Func<G4SemanticQuery, CancellationToken, Task> verifyRoot, CancellationToken token)
    {
        if (key.Length is < 1 or > 128 || key.Any(character => character is < '!' or > '~'))
            throw new SemanticOperationException(400, "query_idempotency_invalid");
        // 同键重放先走本人历史恢复，不要求旧MappingRelease仍是当前Active。
        var existing = await store.FindKeyAsync(actor, key, token);
        if (existing is not null)
        {
            if (existing.RequestHash != G4QueryCanonical.Hash(G4QueryCanonical.Serialize(new { query, selectionQueryId })))
                throw new SemanticOperationException(409, "query_idempotency_conflict");
            return await ReadAsync(actor, sessionReference, existing.Id, true, false, deadline, verifyRoot, token);
        }
        // 初始会话只捕获真实epoch，绝不授予任何源字段权限。
        var initialScope = new ResourceScope { OrganizationId = actor.OrganizationId,
            SiteIds = actor.SiteIds.Where(site => query.Filters.SiteId is null || site == query.Filters.SiteId).ToArray() };
        // 正式映射捕获需要当前真实组织版本，不借用M3历史授权epoch。
        var initial = await authority.CaptureSessionAsync(actor, sessionReference, initialScope, token);
        // 全部后续读取和提交固定这一条版本链，不静默换Active。
        var context = await bindings.CaptureAsync(actor, query, initial.AuthorizationEpoch, token);
        // 以实际映射scope交集捕获当前会话，初始范围不成为数据授权。
        var session = await authority.CaptureSessionAsync(actor, sessionReference, context.Scope, token);
        if (session.AuthorizationEpoch != initial.AuthorizationEpoch) throw new SemanticOperationException(403, "query_forbidden");
        if (query.CapabilityId != "g4_resolve_entity" || context.Manifest.Mapping.Entities.Length != 1)
            throw new SemanticOperationException(422, "capability_not_supported");
        // S1仅一个实体分支，后续关系分支必须在同登记器中明确升级执行器版本。
        var entity = context.Manifest.Mapping.Entities[0];
        if (!ontology.Description.ClassIris.Contains(entity.EntityClassIri, StringComparer.Ordinal)
            || context.Manifest.Mapping.Properties.Any(property => !ontology.Description.DatatypePropertyIris.Contains(property.PropertyIri, StringComparer.Ordinal)))
            throw new SemanticOperationException(422, "query_path_invalid");
        if (selectionQueryId is not null)
            await DemandSelectionAsync(actor, sessionReference, query, selectionQueryId, context.Binding, deadline, verifyRoot, token);
        // 源实际完整字段依赖由同一个适配器枚举，不把scope列排除在grant之外。
        var projection = source.DescribeProjection(context, entity.Id);
        // 默认没有grant；可见snapshot的分支拒绝仍需以无数据六态表达。
        MappingAuthorizationProof[] proofs;
        try { proofs = [await CaptureAsync(session, context.Binding.ConnectionId, projection, "data.query.execute", token)]; }
        catch (SemanticOperationException error) when (error.Status == 403) { proofs = []; }
        // 拒绝分支保留计划投影供将来当前授权恢复，不保存原始源行。
        var state = new G4QueryState { Binding = context.Binding, Scope = context.Scope,
            Projections = proofs.Length == 0 ? [] : [projection], RequiredProjections = [projection] };
        // 随机实例租约只属于本次执行，不由调用方传入owner。
        var admission = await store.AdmitAsync(session, proofs, query, state, key, selectionQueryId,
            "execution-" + Guid.NewGuid().ToString("N"), deadline, token);
        if (!admission.Created) return await ReadAsync(actor, sessionReference, admission.Record.Id, true, false, deadline, verifyRoot, token);
        // 业务读取与租约观察共享取消，取消先提交后旧worker不能继续提交。
        using var execution = CancellationTokenSource.CreateLinkedTokenSource(token);
        // 观察器可在进入最终短事务前停止，不能因本实例成功清除租约而误取消回传。
        using var observation = CancellationTokenSource.CreateLinkedTokenSource(execution.Token);
        // 心跳只续本次fence，不能接管或重放另一个实例的业务查询。
        var watching = WatchAsync(admission.Record, execution, observation.Token);
        try
        {
            // 源未读取时没有伪造回执，后续成功读取才构造真实分支材料。
            G4QueryBranchProjection? projected = null;
            // 源读取事实只留在本次有界内存，提交只保存授权投影。
            G4SourceQueryRead? read = null;
            // 当前可见分支的固定状态，不回显异常或SQL。
            var branchStatus = "FORBIDDEN";
            if (proofs.Length != 0)
            {
                try
                {
                    read = await source.ReadAsync(context, proofs[0], entity.Id, query, deadline, execution.Token);
                    projected = ProjectEntities(admission.Record.Id, actor.TraceId, context, read);
                    if (query.Filters.EntityIri is not null)
                    {
                        // IRI已由原候选证明；内存等值筛选是固定类型计划的一部分，不访问IRI地址。
                        var selected = projected.Entities.Where(item => item.EntityIri == query.Filters.EntityIri).ToArray();
                        // 回执覆盖完成本次选择谓词后的授权投影，不把未选候选计入本次结果。
                        var selectedEvidence = projected.Evidence.Where(item => selected.Any(entityValue => entityValue.EvidenceIds.Contains(item.EvidenceId, StringComparer.Ordinal))).ToArray();
                        // 空投影只有完整读取时才是EMPTY，截断或未知仍保留不确定。
                        var selectedReceipt = projected.Receipt.Receipt with { RowCount = selected.Length,
                            Status = selected.Length == 0 && !read.Limited && !read.Indeterminate ? "EMPTY" : "SUCCESS",
                            SourceRecordRef = selectedEvidence.Length == 1 ? selectedEvidence[0].SourceRecordRef : null,
                            ResultHash = G4QueryCanonical.Hash(G4QueryCanonical.Projection(selected.Cast<G4QueryDatum>().ToArray())) };
                        projected = new G4QueryBranchProjection { Entities = selected, Evidence = selectedEvidence,
                            Receipt = new G4QueryStoredReceipt { Receipt = selectedReceipt, ReceiptHash = G4QueryCanonical.Hash(G4QueryCanonical.Serialize(selectedReceipt)) } };
                    }
                    branchStatus = projected.Receipt.Receipt.Status;
                    if (read.Indeterminate || read.Limited && (projected.Entities.Length < 2 || !CandidatePrefixIsIndependent(context, read))
                        || projected.Entities.Length >= 2 && projected.Evidence.Any(item => item.Precision is not ("ROW_KEY" or "RECORD")))
                    {
                        // 未知窗口不支撑任何候选或业务断言，保留真实读取发生的安全回执。
                        var uncertain = projected.Receipt.Receipt with { Status = "INDETERMINATE", RowCount = 0, Precision = "UNKNOWN", SourceRecordRef = null, ResultHash = null };
                        projected = new G4QueryBranchProjection { Entities = [], Evidence = [], Receipt = new G4QueryStoredReceipt
                        { Receipt = uncertain, ReceiptHash = G4QueryCanonical.Hash(G4QueryCanonical.Serialize(uncertain)) } };
                        branchStatus = "INDETERMINATE";
                    }
                }
                catch (SemanticOperationException error) when (error.Status is 403 or 503)
                {
                    branchStatus = error.Status == 403 ? "FORBIDDEN" : error.Code == "query_source_timeout" ? "TIMEOUT" : "UNAVAILABLE";
                }
            }
            // 聚合不把运行状态或空数组误判成EMPTY。
            var result = Aggregate(actor, query, context, projected, read, branchStatus);
            await observation.CancelAsync();
            try { await watching; } catch (OperationCanceledException) when (observation.IsCancellationRequested) { }
            await store.CompleteAsync(admission.Record, session, proofs, query, state, result,
                projected is null ? [] : [projected.Receipt], execution.Token);
            if (result.Status is "UNAUTHORIZED" or "UNAVAILABLE")
            {
                // 无数据结果也重新检查当前会话；本次只披露先前已验证可见的snapshot。
                await authority.CaptureSessionAsync(actor, sessionReference, context.Scope, execution.Token);
                // 不把内存中的RUNNING对象伪装为已完成，读取实际提交状态。
                var completed = await store.FindOwnedAsync(actor, admission.Record.Id, execution.Token);
                return new G4QueryDelivery { View = G4QueryResultStore.View(completed), ResultBytes = G4QueryCanonical.Result(result) };
            }
            // 刚才的真实源读取已经核验当前ACL；回传短事务再次固定同一连接版本。
            var access = new G4QueryConnectionAccess { ConnectionId = context.Binding.ConnectionId,
                Revision = long.Parse(context.Binding.ConnectionRevision, CultureInfo.InvariantCulture), ConfigHash = context.Binding.ConfigHash,
                SecretVersion = long.Parse(context.Binding.SecretVersion, CultureInfo.InvariantCulture), Scope = context.Scope, Projection = projection,
                CheckedAtUtc = read!.CompletedAtUtc };
            // 结果披露许可独立于execute，不能因为创建成功就直接回显缓存字节。
            var currentSession = await authority.CaptureSessionAsync(actor, sessionReference, context.Scope, execution.Token);
            // 当前execute和result.read分别捕获，撤权先提交即禁止披露。
            var currentExecute = await CaptureAsync(currentSession, context.Binding.ConnectionId, projection, "data.query.execute", execution.Token);
            // 查询读取许可仍须覆盖本次实际全部投影字段。
            var currentRead = await CaptureAsync(currentSession, context.Binding.ConnectionId, projection, "data.query.result.read", execution.Token);
            return await store.ReadAuthorizedAsync(admission.Record.Id, currentSession, [currentExecute], [currentRead], [], [access], true, false, execution.Token);
        }
        finally
        {
            await execution.CancelAsync();
            try { await watching; } catch (OperationCanceledException) { }
        }
    }

    /// <summary>本人历史恢复重验根快照、当前grant与当前源ACL，但从不重放业务ReadAsync。</summary>
    internal async Task<G4QueryDelivery> ReadAsync(ActorContext actor, string sessionReference, string queryId, bool includeResult,
        bool evidenceRead, DateTimeOffset deadline, Func<G4SemanticQuery, CancellationToken, Task> verifyRoot, CancellationToken token)
    {
        // 未知或异主体查询统一404，只有本人记录才进入内部恢复流程。
        var record = await store.FindOwnedAsync(actor, queryId, token);
        if (record.ExpiresAtUtc <= clock.GetUtcNow()) throw new SemanticOperationException(410, "result_expired");
        // 原请求只用于根版本和计划校验，不重新执行其中的业务过滤。
        var query = G4QueryResultStore.ReadRequest(record);
        await verifyRoot(query, token);
        // 保存版本保持原样，授权版本在本次读取重新捕获。
        var state = G4QueryResultStore.ReadState(record);
        // 当前会话、scope、角色在字段授权之前核验。
        var session = await authority.CaptureSessionAsync(actor, sessionReference, state.Scope, token);
        // 历史MappingRelease不要求当前Active回到原值。
        var context = await bindings.ReadHistoricalAsync(actor, state.Binding, state.Scope, token);
        // 无数据拒绝结果仍需从原计划获得当前完整许可后才可恢复。
        var projections = state.Projections.Length == 0 ? state.RequiredProjections : state.Projections;
        // 本次当前授权证明与来源检查逐分支独立，不合并不同grant。
        var executes = new List<MappingAuthorizationProof>();
        // 结果读取权限不能由连接管理或映射管理权限替代。
        var reads = new List<MappingAuthorizationProof>();
        // 证据打开是额外权限，不是普通结果读取的隐式升级。
        var evidences = new List<MappingAuthorizationProof>();
        // 当前源账号检查产物只在本请求短事务中使用。
        var access = new List<G4QueryConnectionAccess>();
        foreach (var projection in projections)
        {
            // 服务端完整投影必须能重新关联到原manifest的明确实体绑定。
            var entity = context.Manifest.Mapping.Entities.FirstOrDefault(item => SameProjection(source.DescribeProjection(context, item.Id), projection)) ?? throw Invalid();
            // 每个许可独立命中完整grant。
            var execute = await CaptureAsync(session, state.Binding.ConnectionId, projection, "data.query.execute", token);
            executes.Add(execute);
            reads.Add(await CaptureAsync(session, state.Binding.ConnectionId, projection, "data.query.result.read", token));
            if (evidenceRead) evidences.Add(await CaptureAsync(session, state.Binding.ConnectionId, projection, "data.query.evidence.read", token));
            access.Add(await source.VerifyAccessAsync(context, execute, entity.Id, deadline, token));
        }
        return await store.ReadAuthorizedAsync(queryId, session, executes.ToArray(), reads.ToArray(), evidences.ToArray(), access.ToArray(), includeResult, evidenceRead, token);
    }

    /// <summary>证据额外通过当前evidence.read许可；客户端只给ID，不能提供可被信任的回执。</summary>
    internal async Task<G4SourceEvidenceView> ReadEvidenceAsync(ActorContext actor, string sessionReference, string evidenceId,
        DateTimeOffset deadline, Func<G4SemanticQuery, CancellationToken, Task> verifyRoot, CancellationToken token)
    {
        // ID包含服务器生成query前缀，不尝试访问任意URL或反解客户端源定位符。
        var separator = evidenceId.IndexOf(":e-", StringComparison.Ordinal);
        if (separator <= 0 || evidenceId.Length > 128) throw new SemanticOperationException(404, "query_not_found");
        // 所有权、当前根、完整三项许可与源ACL先经同一个恢复边界核验。
        var queryId = evidenceId[..separator];
        // 只有已完成且未到期原规范结果才可能打开真实证据。
        var delivery = await ReadAsync(actor, sessionReference, queryId, true, true, deadline, verifyRoot, token);
        if (delivery.ResultBytes is null) throw new SemanticOperationException(404, "query_not_found");
        // 不能用相似ID或另一个query中的证据替代原结果引用。
        var evidence = G4QueryRules.ReadResult(delivery.ResultBytes).Evidence.SingleOrDefault(item => item.EvidenceId == evidenceId)
            ?? throw new SemanticOperationException(404, "query_not_found");
        // 已提交结果与回执不可变，当前读取事务已经重验二者闭合。
        var record = await store.FindOwnedAsync(actor, queryId, token);
        // 只显式投影已冻结公共字段，不序列化内部完整Binding。
        var receipt = G4QueryResultStore.ReadState(record).Receipts.SingleOrDefault(item => item.Receipt.ReceiptId == evidence.SourceReadReceiptId)?.Receipt
            ?? throw Invalid();
        return new G4SourceEvidenceView { SchemaVersion = "g4.source-evidence.v1", Evidence = evidence, Receipt = new G4SourceReceiptView
        {
            ReceiptId = receipt.ReceiptId, QueryId = receipt.QueryId, MappingReleaseId = receipt.Binding.MappingReleaseId,
            ManifestHash = receipt.Binding.ManifestHash, OriginalCatalogSnapshotId = receipt.Binding.OriginalCatalogSnapshotId,
            CurrentCatalogSnapshotId = receipt.Binding.CurrentCatalogSnapshotId, ConnectionId = receipt.Binding.ConnectionId,
            ConnectionRevision = receipt.Binding.ConnectionRevision, ActivationId = receipt.Binding.ActivationId,
            ActivationRevision = receipt.Binding.ActivationRevision, QueryPlanHash = receipt.QueryPlanHash, AdapterVersion = receipt.AdapterVersion,
            Status = receipt.Status, RowCount = receipt.RowCount, Limited = receipt.Limited, WatermarkKind = receipt.WatermarkKind,
            Watermark = receipt.Watermark, ReadStartedAtUtc = receipt.ReadStartedAtUtc, ReadCompletedAtUtc = receipt.ReadCompletedAtUtc,
            ResultHash = receipt.ResultHash, TraceId = receipt.TraceId
        } };
    }

    /// <summary>取消只提交本人执行状态，不读取业务结果或重新执行外源查询。</summary>
    internal async Task<G4QueryView> CancelAsync(ActorContext actor, string sessionReference, string queryId,
        Func<G4SemanticQuery, CancellationToken, Task> verifyRoot, CancellationToken token)
    {
        // 所有权优先，未知与异主体统一404。
        var record = await store.FindOwnedAsync(actor, queryId, token);
        if (record.ExpiresAtUtc <= clock.GetUtcNow()) throw new SemanticOperationException(410, "result_expired");
        await verifyRoot(G4QueryResultStore.ReadRequest(record), token);
        // 使用原执行实际投影，当前Active变更不妨碍取消。
        var state = G4QueryResultStore.ReadState(record);
        // 当前服务器会话及epoch在取消事务中再次复核。
        var session = await authority.CaptureSessionAsync(actor, sessionReference, state.Scope, token);
        // 原执行无授权分支没有数据投影，取消不升级任何源读取权限。
        var proofs = new List<MappingAuthorizationProof>();
        foreach (var projection in state.Projections)
            proofs.Add(await CaptureAsync(session, state.Binding.ConnectionId, projection, "data.query.execute", token));
        return G4QueryResultStore.View(await store.CancelAsync(queryId, session, proofs.ToArray(), token));
    }

    /// <summary>只接受原本人AMBIGUOUS结果中的精确候选和完整版本，禁止客户端自带IRI绕过。</summary>
    private async Task DemandSelectionAsync(ActorContext actor, string sessionReference, G4SemanticQuery query, string selectionId,
        G4QueryBinding binding, DateTimeOffset deadline, Func<G4SemanticQuery, CancellationToken, Task> verifyRoot, CancellationToken token)
    {
        // 原消歧结果按同一当前恢复边界重新鉴权与校验证据。
        var original = await ReadAsync(actor, sessionReference, selectionId, true, false, deadline, verifyRoot, token);
        if (original.ResultBytes is null) throw new SemanticOperationException(422, "selection_invalid");
        // 此结果已解密、验hash及当前授权，不能用UI传回的候选对象替代。
        var result = G4QueryRules.ReadResult(original.ResultBytes);
        // 重新读取固定元数据，完整Binding含activationId/revision可识别ABA。
        var record = await store.FindOwnedAsync(actor, selectionId, token);
        if (G4QueryResultStore.ReadState(record).Binding != binding) throw new SemanticOperationException(409, "query_binding_stale");
        // 原请求用于证明除了site与选择IRI以外没有改变任何语义参数。
        var prior = G4QueryResultStore.ReadRequest(record);
        // 仅恢复两个被合同允许改变的字段，其他参数必须规范字节完全相同。
        var normalized = query with { Filters = query.Filters with { EntityIri = prior.Filters.EntityIri, SiteId = prior.Filters.SiteId } };
        if (result.Status != "AMBIGUOUS" || !G4QueryCanonical.Serialize(normalized).AsSpan().SequenceEqual(G4QueryCanonical.Serialize(prior))
            || !result.Candidates.Any(candidate => candidate.EntityIri == query.Filters.EntityIri && candidate.SiteId == query.Filters.SiteId))
            throw new SemanticOperationException(422, "selection_invalid");
    }

    /// <summary>捕获单一许可对完整投影的当前grant，不构造客户端可伪造proof。</summary>
    private Task<MappingAuthorizationProof> CaptureAsync(MappingAuthorizationProof session, string connectionId, G4QueryProjection projection, string permission, CancellationToken token) =>
        authority.CaptureAsync(session with { ConnectionId = connectionId, Permission = permission, ObjectRefs = projection.ObjectRefs, FieldRefs = projection.FieldRefs }, token);

    /// <summary>仅对完整相同投影复用源ACL检查，不把另一张表的检查当作当前字段许可。</summary>
    private static bool SameProjection(G4QueryProjection left, G4QueryProjection right) => left.ObjectRefs.Order(StringComparer.Ordinal).SequenceEqual(right.ObjectRefs.Order(StringComparer.Ordinal))
        && left.FieldRefs.Order(StringComparer.Ordinal).SequenceEqual(right.FieldRefs.Order(StringComparer.Ordinal));

    /// <summary>两秒心跳观察跨实例取消或失联，源预算仍由原绝对deadline决定。</summary>
    private async Task WatchAsync(G4QueryRecord lease, CancellationTokenSource execution, CancellationToken observation)
    {
        while (!observation.IsCancellationRequested)
        {
            await Task.Delay(TimeSpan.FromSeconds(2), clock, observation);
            try
            {
                if (!await store.HeartbeatAsync(lease, observation) && !observation.IsCancellationRequested) await execution.CancelAsync();
            }
            catch (OperationCanceledException) when (observation.IsCancellationRequested) { throw; }
            catch
            {
                await execution.CancelAsync();
                throw;
            }
        }
    }

    /// <summary>截断候选必须由已投影主键证明未读行不会产生同一完整身份，不能只凭已见两条。</summary>
    private static bool CandidatePrefixIsIndependent(G4QueryBindingContext context, G4SourceQueryRead read)
    {
        // 主键必须是业务身份组成字段的子集，未读行才不能改变已展示候选的唯一性。
        var entity = context.Manifest.Mapping.Entities.Single(item => item.Id == read.EntityBindingId);
        // 完整身份包含源scope、复合键和有效时间端点。
        var identity = context.Manifest.Mapping.IdentitySpecs.Single(item => item.Id == entity.IdentitySpecId);
        // 字段名只在同一个固定数据集内比较，不跨表混用同名列。
        var fields = identity.ExternalIdFieldRefs.Concat(new[] { identity.OrganizationFieldRef, identity.SiteFieldRef,
            identity.ValidFromFieldRef, identity.ValidToFieldRef }.OfType<MappingFieldRef>()).Select(item => item.Name).ToHashSet(StringComparer.Ordinal);
        return read.RecordKeyFields.Length > 0 && read.RecordKeyFields.All(fields.Contains);
    }

    /// <summary>S1聚合明确区分空、失败、未知定位、候选及来源降级。</summary>
    private G4QueryResultV1 Aggregate(ActorContext actor, G4SemanticQuery query, G4QueryBindingContext context,
        G4QueryBranchProjection? projected, G4SourceQueryRead? read, string branchStatus)
    {
        // 选择只缩小已验证候选，不根据IRI访问外部地址。
        var entities = projected?.Entities.Where(item => query.Filters.EntityIri is null || item.EntityIri == query.Filters.EntityIri).ToArray() ?? [];
        // 只有实际输出断言或候选引用的证据才进入响应。
        G4QueryDatum[] data = [];
        // 候选与业务断言互斥，不能擅自选择第一条。
        G4QueryCandidate[] candidates = [];
        // 未知或失败默认不可用，完整条件才提升为其他业务态。
        var status = branchStatus == "FORBIDDEN" ? "UNAUTHORIZED" : "UNAVAILABLE";
        if (branchStatus is "SUCCESS" or "EMPTY" && read is not null && !read.Indeterminate)
        {
            if (entities.Length >= 2 && projected!.Evidence.All(item => item.Precision is "ROW_KEY" or "RECORD"))
            {
                status = "AMBIGUOUS";
                candidates = entities.Select(item => new G4QueryCandidate { EntityIri = item.EntityIri!, EntityTypeIris = item.TypeIris,
                    ExternalId = item.Identity.ExternalId, OrganizationId = item.Identity.OrganizationId, SiteId = item.Identity.SiteId,
                    Label = item.Label ?? item.Identity.ExternalId, EvidenceIds = item.EvidenceIds }).ToArray();
            }
            else if (!read.Limited && entities.Length == 1)
            {
                data = [entities[0]];
                status = projected!.Evidence.Any(item => item.Precision is "DATASET" or "TIME_WINDOW" or "UNKNOWN") ? "PARTIAL" : "FOUND";
            }
            else if (!read.Limited && entities.Length == 0) status = "EMPTY";
        }
        // 聚合后的来源只闭合当前实际可见业务投影。
        var ids = data.SelectMany(item => item.EvidenceIds).Concat(candidates.SelectMany(item => item.EvidenceIds)).ToHashSet(StringComparer.Ordinal);
        return new G4QueryResultV1 { SchemaVersion = "g4.query-result.v1", Status = status, Data = data, Candidates = candidates,
            Evidence = projected?.Evidence.Where(item => ids.Contains(item.EvidenceId)).ToArray() ?? [],
            Snapshot = new G4QuerySnapshot { OntologyReleaseId = query.OntologyReleaseId, MappingReleaseIds = query.MappingReleaseIds,
                SourceCatalogSnapshotIds = [context.Binding.CurrentCatalogSnapshotId], CapabilityId = query.CapabilityId, CapabilityVersion = query.CapabilityVersion },
            SubSources = [new G4QuerySubSource { ConnectionId = context.Binding.ConnectionId, Status = branchStatus,
                ObservedAtUtc = projected?.Receipt.Receipt.ReadCompletedAtUtc ?? Utc(clock.GetUtcNow()),
                WatermarkKind = projected?.Receipt.Receipt.WatermarkKind ?? "UNKNOWN", SourceReadReceiptId = projected?.Receipt.Receipt.ReceiptId, Limited = read?.Limited ?? false }],
            ValidTime = null, ObservedAtUtc = Utc(clock.GetUtcNow()), TraceId = actor.TraceId, Limited = read?.Limited ?? false,
            Diagnostics = status is "UNAVAILABLE" or "PARTIAL" or "UNAUTHORIZED"
                ? [new G4QueryDiagnostic { Code = status == "PARTIAL" ? "query_evidence_degraded" : status == "UNAUTHORIZED" ? "query_source_forbidden" : "query_source_indeterminate",
                    Severity = "warning", Message = "结果受当前授权或可验证来源限制。", FocusNode = null, Path = null }] : [] };
    }

    /// <summary>从真实类型化分支读取构造完整实体与证据；任何未知身份都不能成为确定候选。</summary>
    public static G4QueryBranchProjection ProjectEntities(string queryId, string traceId, G4QueryBindingContext context, G4SourceQueryRead read)
    {
        // 只能使用固定manifest的实体定义，不能从外部字符串推断任意表。
        var mapping = context.Manifest.Mapping;
        // 源适配器返回的绑定身份必须在本次固定映射中唯一存在。
        var entity = mapping.Entities.SingleOrDefault(item => item.Id == read.EntityBindingId) ?? throw Invalid();
        // 组织厂区、命名空间与有效时间构成业务身份。
        var identity = mapping.IdentitySpecs.Single(item => item.Id == entity.IdentitySpecId);
        // 事件时间与有效时间保持明确类型，不用观察时间填补缺失业务时间。
        var temporal = mapping.TemporalSpecs.Single(item => item.Id == entity.TemporalSpecId);
        // 数据集身份从原发布固定引用产生，不使用当前目录覆盖历史目录。
        var dataset = "dataset-" + G4QueryCanonical.Hash(G4QueryCanonical.Serialize(entity.DatasetRef));
        // 每个实际读取都有独立随机回执，不能按连接名合并两个表。
        var receiptId = "read-" + Guid.NewGuid().ToString("N");
        // 对外观察时间是实际源事务完成时刻，统一微秒词法。
        var observed = Utc(read.CompletedAtUtc);
        // 不保存原始行，只保留经过映射的有界业务断言。
        var entities = new List<G4EntityDatum>();
        // 每行一个来源身份，供实体、属性和单位共同引用。
        var evidence = new List<G4SourceEvidenceRef>();
        if (read.Rows.Length > 100 || read.CompletedAtUtc < read.StartedAtUtc) throw Invalid();
        foreach (var row in read.Rows)
        {
            // 身份只能由真实源列构造，不能用请求scope覆盖错误源值。
            var organization = RequiredIdentity(row, identity.OrganizationFieldRef);
            // 厂区同时与适配器scope列及当前已授权范围逐行核验。
            var site = RequiredIdentity(row, identity.SiteFieldRef);
            if (organization != context.Scope.OrganizationId || !context.Scope.SiteIds.Contains(site, StringComparer.Ordinal)
                || RequiredIdentity(row, entity.ScopeFields.Organization) != organization || RequiredIdentity(row, entity.ScopeFields.Site) != site)
                throw Invalid();
            // 单键保留原词法；复合键使用有序规范JSON，禁止以分隔符拼接制造歧义。
            var components = identity.ExternalIdFieldRefs.Select(field => RequiredIdentity(row, field)).ToArray();
            // 身份外部号的wire仍是明确字符串，不经过浮点或区域格式转换。
            var external = components.Length == 1 ? components[0] : Encoding.UTF8.GetString(G4QueryCanonical.Serialize(components));
            // 有效区间未知保持null，不解释为永久有效。
            var effective = Interval(row, identity.ValidFromFieldRef, identity.ValidToFieldRef);
            // 完整身份用于稳定IRI，不使用外部号本身作为跨厂区主键。
            var semanticIdentity = new G4QueryIdentity { OrganizationId = organization, SiteId = site,
                SourceNamespace = identity.SourceNamespace, ExternalId = external, EffectiveTime = effective };
            // URI仅作为内部标识使用，永不请求这个地址。
            var iri = "urn:ontology-platform:entity:" + G4QueryCanonical.Hash(G4QueryCanonical.Serialize(semanticIdentity));
            // 同一身份出现不同源行不能静默取第一条；查询执行器需报告定位不完整。
            if (entities.Any(item => item.EntityIri == iri)) throw Invalid();
            // 真实登记且完整读取的主键才能形成可定位记录引用。
            var key = RecordReference(row, read.RecordKeyFields);
            // 数据集级来源明确降级，不能把哈希伪装成不存在的唯一主键。
            var precision = key is null ? "DATASET" : "ROW_KEY";
            // 证据身份含查询随机前缀，方便服务端按本人查询进行恢复定位。
            var evidenceId = queryId + ":e-" + Guid.NewGuid().ToString("N");
            // 每行有效时间沿用已发布时间规则，不能根据返回时间猜测。
            var valid = Interval(row, temporal.ValidFromFieldRef, temporal.ValidToFieldRef);
            // 顶层旧UTC区间不接受LOCAL或DATE的隐式时区转换。
            var utcValid = valid?.From.Kind == "UTC" && (valid.To is null || valid.To.Kind == "UTC")
                ? new G4QueryUtcInterval { FromUtc = valid.From.Lexical, ToUtc = valid.To?.Lexical } : null;
            evidence.Add(new G4SourceEvidenceRef { EvidenceId = evidenceId, ConnectionId = context.Binding.ConnectionId,
                MappingReleaseId = context.Binding.MappingReleaseId, SourceCatalogSnapshotId = context.Binding.OriginalCatalogSnapshotId,
                SourceDatasetRef = dataset, SourceReadReceiptId = receiptId, Scope = new ResourceScope { OrganizationId = organization, SiteIds = [site] },
                Precision = precision, SourceRecordRef = key, ValidTime = utcValid, ObservedAtUtc = observed });
            // 属性集合只从发布定义读取，原始字典或未授权列不进入wire。
            var properties = mapping.Properties.Where(item => item.EntityBindingId == entity.Id).Select(property =>
            {
                // 映射引用精确源字段，缺列不能以null补齐。
                var value = Cell(row, property.FieldRef);
                if (value is G4NullValue && property.NullPolicy == "REJECT_NULL") throw Invalid();
                // S1无转换属性保持原精度；已登记转换由下方封闭实现处理。
                value = ConvertValue(value, property.ConversionId is null ? null : mapping.Conversions.Single(item => item.Id == property.ConversionId));
                // 单位必须逐行证实源代码，不能根据属性名推断。
                var unit = property.UnitSpecId is null ? null : mapping.UnitSpecs.Single(item => item.Id == property.UnitSpecId);
                if (unit is not null && RequiredIdentity(row, unit.SourceUnitFieldRef) != unit.SourceUnitCode) throw Invalid();
                return new G4QueryProperty { PropertyIri = property.PropertyIri, Value = value,
                    EventTime = Time(row, temporal.EventTimeFieldRef), EvidenceIds = [evidenceId],
                    Unit = unit is null ? null : new G4QueryUnit { UnitSpecId = unit.Id, UnitIri = unit.TargetUnitIri,
                        Source = "SOURCE_FIELD", SourceFieldRef = "field-" + G4QueryCanonical.Hash(G4QueryCanonical.Serialize(unit.SourceUnitFieldRef)), EvidenceIds = [evidenceId] } };
            }).ToArray();
            // label没有单独可信绑定时为null，不按相似列名猜测显示字段。
            var datum = new G4EntityDatum { EntityIri = iri, Identity = semanticIdentity, TypeIris = [entity.EntityClassIri], Label = null,
                Properties = properties, EvidenceIds = [evidenceId], ValidTime = valid };
            G4QueryRules.Validate(datum);
            entities.Add(datum);
        }
        // 分支投影hash只覆盖这些已授权断言，不包含回执或总结果本身。
        var projection = G4QueryCanonical.Projection(entities.Cast<G4QueryDatum>().ToArray());
        // 不确定窗口即使零行也不能记成真实EMPTY。
        var status = entities.Count == 0 && !read.Limited && !read.Indeterminate ? "EMPTY" : "SUCCESS";
        // 多行回执不虚构一个总记录定位；逐行位置只出现在各自evidence中。
        var receipt = new G4SourceReadReceipt { SchemaVersion = "g4.read-receipt.v1", ReceiptId = receiptId, QueryId = queryId,
            Binding = context.Binding, SourceDatasetRef = dataset, QueryPlanHash = read.QueryPlanHash, AdapterVersion = "pg-query-v1",
            Scope = context.Scope, Status = status, RowCount = entities.Count, Limited = read.Limited, WatermarkKind = "TRANSACTION_SNAPSHOT",
            Watermark = read.TransactionSnapshot, SourceRecordRef = evidence.Count == 1 ? evidence[0].SourceRecordRef : null,
            Precision = read.RecordKeyFields.Length == 0 ? "DATASET" : "ROW_KEY", ValidTime = null,
            ReadStartedAtUtc = Utc(read.StartedAtUtc), ReadCompletedAtUtc = observed, ResultHash = G4QueryCanonical.Hash(projection), TraceId = traceId };
        return new G4QueryBranchProjection { Entities = entities.ToArray(), Evidence = evidence.ToArray(),
            Receipt = new G4QueryStoredReceipt { Receipt = receipt, ReceiptHash = G4QueryCanonical.Hash(G4QueryCanonical.Serialize(receipt)) } };
    }

    /// <summary>只有登记的精确转换能运行，不执行表达式或模型生成代码。</summary>
    private static G4QueryValue ConvertValue(G4QueryValue value, MappingConversion? conversion)
    {
        if (conversion is null) return value;
        if (conversion.Version != "1") throw Invalid();
        if (conversion.RegisteredId == "identity") return value;
        if (value is G4NullValue) return value;
        if (value is not (G4DecimalValue or G4Int64Value)) throw Invalid();
        // decimal保留十进制语义，任何溢出或需要舍入都拒绝。
        var number = decimal.Parse(value.Lexical!, NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture);
        // 输出scale来自固定转换或源精度，不由字符串显示位数猜测。
        var scale = value is G4DecimalValue source ? source.Scale : 0;
        switch (conversion.RegisteredId)
        {
            case "decimal-scale-exact":
                scale = conversion.Parameters.GetProperty("scale").GetInt32();
                if (scale is < 0 or > 28 || decimal.Round(number, scale) != number) throw Invalid();
                break;
            case "celsius-to-kelvin":
                // 冻结单位偏移采用精确decimal，并验证逆运算不丢位。
                var original = number;
                number = checked(number + 273.15m);
                if (number - 273.15m != original) throw Invalid();
                scale = Math.Max(scale, 2);
                break;
            default:
                throw Invalid();
        }
        return new G4DecimalValue { Lexical = number.ToString("F" + scale, CultureInfo.InvariantCulture), Precision = 28, Scale = scale };
    }

    /// <summary>主键引用保留完整有序列和值，只对确实登记且非空的键承诺行定位。</summary>
    private static string? RecordReference(Dictionary<string, G4QueryValue> row, string[] fields)
    {
        if (fields.Length == 0 || fields.Any(field => !row.TryGetValue(field, out var value) || value is G4NullValue)) return null;
        // Base64仅用于可逆键编码，不是加密；此字段受与业务结果相同的当前授权保护。
        var encoded = "key:" + Convert.ToBase64String(G4QueryCanonical.Serialize(fields.Select(field => new { field, value = row[field] }).ToArray()));
        return Encoding.UTF8.GetByteCount(encoded) <= 4096 ? encoded : null;
    }

    /// <summary>源字段缺失不是业务null，必须拒绝不完整投影。</summary>
    private static G4QueryValue Cell(Dictionary<string, G4QueryValue> row, MappingFieldRef field) => row.TryGetValue(field.Name, out var value) ? value : throw Invalid();

    /// <summary>外部身份只能来自非空精确标量，不能用null或JSON对象构造实体身份。</summary>
    private static string RequiredIdentity(Dictionary<string, G4QueryValue> row, MappingFieldRef field)
    {
        // 身份词法不转浮点、不裁剪，也不混入客户端补值。
        var value = Cell(row, field);
        return value is G4StringValue or G4Int64Value && !string.IsNullOrWhiteSpace(value.Lexical) ? value.Lexical! : throw Invalid();
    }

    /// <summary>显式类型转换为时间wire，不把LOCAL当UTC或把DATE补午夜。</summary>
    private static G4QueryTime? Time(Dictionary<string, G4QueryValue> row, MappingFieldRef? field)
    {
        if (field is null) return null;
        return Cell(row, field) switch
        {
            G4NullValue => null,
            G4UtcValue value => new G4QueryTime { Kind = "UTC", Lexical = value.Lexical!, FractionalDigits = 6 },
            G4LocalValue value => new G4QueryTime { Kind = "LOCAL", Lexical = value.Lexical!, FractionalDigits = 6 },
            G4DateValue value => new G4QueryTime { Kind = "DATE", Lexical = value.Lexical!, FractionalDigits = 0 },
            _ => throw Invalid()
        };
    }

    /// <summary>端点只沿发布绑定解释，未知起点不构造假的区间。</summary>
    private static G4QueryInterval? Interval(Dictionary<string, G4QueryValue> row, MappingFieldRef? from, MappingFieldRef? to)
    {
        // 真实起点未知时整段有效时间未知，绝不填当前时间。
        var start = Time(row, from);
        return start is null ? null : new G4QueryInterval { From = start, To = Time(row, to) };
    }

    /// <summary>实际UTC观察时刻固定微秒输出，避免数据库回读改变规范字节。</summary>
    internal static string Utc(DateTimeOffset value) => value.UtcDateTime.ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'", CultureInfo.InvariantCulture);

    /// <summary>映射或投影不完整时只返回固定失败，不把内部源值写进异常。</summary>
    private static SemanticOperationException Invalid() => new(503, "query_projection_invalid");
}
