using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>目录持久命令、当前ACL过滤和不可变快照访问。</summary>
public sealed partial class ConnectionApplicationService
{
    /// <summary>公开任务不携会话、秘密、内部故障或租约信息。</summary>
    private static CatalogDiscoveryJobView JobView(CatalogJobRecord job) => new()
    {
        JobId = job.Id,
        ConnectionId = job.ConnectionId,
        ConfigRevision = job.Revision,
        Status = job.Status,
        CreatedAtUtc = job.CreatedAtUtc,
        CompletedAtUtc = job.CompletedAtUtc,
        SnapshotId = job.SnapshotId,
        TraceId = job.TraceId
    };

    /// <summary>发现先持久排队并在同一事务审计，后台才访问真实源。</summary>
    private Task<ConnectionReply> DiscoverAsync(ConnectionInvocation call, CancellationToken token)
        => CommandAsync<CatalogDiscoveryJobView>(call, ((ConnectionMutationCommand)call.Body!).Command, "connection.catalog.start", 202, async (db, ct) =>
        {
            // 先加载已授权连接并检查资源修订。
            var row = await FindAsync(db, call.Actor, call.Id, ct);
            Cas(call, row, ((ConnectionMutationCommand)call.Body!).Command);
            if (row.State != "ACTIVE" || !await FreshAsync(db, row, ct)) throw new SemanticOperationException(409, "connection_probe_stale");
            if (!await authority.IsCurrentAsync(call.SessionReference, call.Actor, ct)) throw new SemanticOperationException(401, "authentication_required");
            if (await db.CatalogJobs.AnyAsync(value => value.ConnectionId == row.Id && (value.Status == "QUEUED" || value.Status == "RUNNING"), ct))
                throw new SemanticOperationException(409, "connection_version_conflict");
            _ = await BoundSecretAsync(db, row, ct);
            // 捕获当前输入版本和受保护会话引用，后台每次重新验证。
            var job = new CatalogJobRecord
            {
                Id = Guid.NewGuid().ToString("N"),
                ConnectionId = row.Id,
                OrganizationId = row.OrganizationId,
                SiteIds = row.SiteIds,
                Revision = row.Revision,
                SecretVersion = row.SecretVersion,
                ConfigHash = row.ConfigHash,
                ActorJson = Encode(call.Actor),
                SessionReference = call.SessionReference,
                TraceId = call.Actor.TraceId,
                CreatedAtUtc = clock.GetUtcNow()
            };
            db.CatalogJobs.Add(job);
            return (JobView(job), Scope(row), Scope(row), Etag(row));
        }, token);

    /// <summary>读取或持久取消指定连接的指定任务。</summary>
    private async Task<ConnectionReply> JobAsync(ConnectionInvocation call, CancellationToken token)
    {
        if (call.Operation == "cancel") return await CommandAsync<CatalogDiscoveryJobView>(call, ((ConnectionMutationCommand)call.Body!).Command,
            "connection.catalog.cancel", 200, async (db, ct) =>
            {
                // 取消仍需当前资源范围及CAS，不能跨连接取消任务。
                var row = await FindAsync(db, call.Actor, call.Id, ct);
                Cas(call, row, ((ConnectionMutationCommand)call.Body!).Command);
                _ = await BoundSecretAsync(db, row, ct);
                // 捕获范围仍需被当前身份覆盖。
                var job = await FindJobAsync(db, call, ct);
                job.CancelRequested = true;
                if (job.Status == "QUEUED") { job.Status = "CANCELLED"; job.CompletedAtUtc = clock.GetUtcNow(); }
                return (JobView(job), Scope(row), Scope(row), Etag(row));
            }, token);
        // 读取路径不依赖进程缓存，可在重启后恢复。
        await using var read = await factory.CreateDbContextAsync(token);
        _ = await FindAsync(read, call.Actor, call.Id, token);
        return new ConnectionReply { Value = JobView(await FindJobAsync(read, call, token)) };
    }

    /// <summary>任务归属及完整范围先于任何字段投影。</summary>
    private static async Task<CatalogJobRecord> FindJobAsync(ConnectionsDbContext db, ConnectionInvocation call, CancellationToken token)
    {
        // 组织、连接及任务ID共同约束查询。
        var job = await db.CatalogJobs.SingleOrDefaultAsync(value => value.Id == call.ChildId && value.ConnectionId == call.Id
            && value.OrganizationId == call.Actor.OrganizationId, token) ?? throw new SemanticOperationException(403, "connection_scope_forbidden");
        DemandScope(call.Actor, new ResourceScope { OrganizationId = job.OrganizationId, SiteIds = job.SiteIds });
        return job;
    }

    /// <summary>历史保存在存储中；返回字段前实时重验源ACL并与当前可见元数据求交。</summary>
    private async Task<ConnectionReply> CatalogAsync(ConnectionInvocation call, CancellationToken token)
    {
        // 读取快照前核验当前连接范围。
        await using var db = await factory.CreateDbContextAsync(token);
        // 独立快照路由先解析已授权快照的所属连接，绝不信任客户端补充连接ID。
        if (call.Operation == "catalog")
        {
            // 未授权快照与不存在快照统一拒绝。
            var snapshot = await db.CatalogSnapshots.AsNoTracking().SingleOrDefaultAsync(value => value.Id == call.ChildId
                && value.OrganizationId == call.Actor.OrganizationId, token) ?? throw new SemanticOperationException(403, "catalog_access_forbidden");
            DemandScope(call.Actor, new ResourceScope { OrganizationId = snapshot.OrganizationId, SiteIds = snapshot.SiteIds });
            call = call with { Id = snapshot.ConnectionId };
        }
        // 禁用连接不能触发任何源IO或暴露旧源权限的目录。
        var row = await FindAsync(db, call.Actor, call.Id, token);
        if (row.State == "DISABLED") throw new SemanticOperationException(403, "catalog_access_forbidden");
        // 当前源ACL必须真实可用，不能单信历史Probe。
        var credential = await BoundSecretAsync(db, row, token);
        // Adapter不读取业务行，发生撤权或故障时失败关闭。
        CatalogObject[] visible;
        try { visible = await WithCurrentSourceAsync(call, row, ct => adapter.DiscoverAsync(Decode<ConnectionConfig>(row.ConfigJson), Scope(row), cipher.Decrypt(credential), ct), token); }
        catch (PgSourceException) { throw new SemanticOperationException(403, "catalog_access_forbidden"); }
        catch (OperationCanceledException) { throw new SemanticOperationException(403, "catalog_access_forbidden"); }
        if (!await authority.IsCurrentAsync(call.SessionReference, call.Actor, token)) throw new SemanticOperationException(401, "authentication_required");
        // 源调用后刷新资源，编辑或撤权不能让旧输入通过。
        await db.Entry(row).ReloadAsync(token);
        DemandScope(call.Actor, Scope(row));
        if (row.State == "DISABLED" || row.SecretId != credential.Id) throw new SemanticOperationException(403, "catalog_access_forbidden");
        // 捕获范围在数据库内先过滤，避免历史跨范围泄漏。
        var query = db.CatalogSnapshots.AsNoTracking().Where(value => value.ConnectionId == row.Id && value.OrganizationId == call.Actor.OrganizationId
            && value.SiteIds.All(site => call.Actor.SiteIds.Contains(site)));
        if (call.Operation == "catalog") query = query.Where(value => value.Id == call.ChildId);
        // 固定ID游标和有界页面，不允许任意偏移扫描。
        var after = Cursor(call.Cursor);
        if (after.Length > 0) query = query.Where(value => string.Compare(value.Id, after) > 0);
        // 本页最多返回50项，源目录总大小在Adapter受限。
        var records = await query.OrderBy(value => value.Id).Take(call.Operation == "catalog" ? 1 : 51).ToArrayAsync(token);
        // 完整当前目录指纹同时识别新增对象、字段和属性变化，不仅识别旧字段消失。
        var currentFingerprint = CanonicalCatalog(visible, Decode<ConnectionConfig>(row.ConfigJson)).Fingerprint;
        // 任何当前不可见字段都不能由历史快照恢复。
        var views = records.Take(50).Select(value =>
        {
            // 每一快照的状态投影不修改持久原文。
            var snapshot = Decode<CatalogSnapshotView>(value.ViewJson);
            // 比较对象和字段的精确身份，不将旧字段套给新对象。
            var objects = snapshot.Objects.Select(item => item with
            {
                Fields = item.Fields.Where(field => visible.Any(now => now.Schema == item.Schema
                && now.Name == item.Name && now.Kind == item.Kind && now.Fields.Any(column => column.Name == field.Name && column.NativeType == field.NativeType))).ToArray()
            })
                .Where(item => item.Fields.Length > 0).ToArray();
            return snapshot with
            {
                Objects = objects,
                Status = value.ConfigHash == row.ConfigHash && value.SecretVersion == row.SecretVersion
                && snapshot.SchemaFingerprint == currentFingerprint && Encode(objects) == Encode(snapshot.Objects) ? snapshot.Status : "STALE"
            };
        }).ToArray();
        if (call.Operation == "catalog") return new ConnectionReply { Value = views.SingleOrDefault() ?? throw new SemanticOperationException(403, "catalog_access_forbidden") };
        return new ConnectionReply
        {
            Value = new CatalogSnapshotListPage
            {
                Items = views,
                NextCursor = records.Length > 50 ? Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(records[49].Id)) : null
            }
        };
    }

    /// <summary>以冻结的适配器版本与排序规则生成目录及指纹，供快照写入和当前状态读取共用。</summary>
    /// <param name="objects">当前授权范围内由真实适配器返回的有界目录。</param>
    /// <param name="config">当前配置用于区分适配器版本，PG原指纹规则保持。</param>
    /// <returns>排序后的目录与保持历史字节规则的内容指纹。</returns>
    private static (CatalogObject[] Objects, string Fingerprint) CanonicalCatalog(CatalogObject[] objects, ConnectionConfig config)
    {
        // 排序只规范化已有目录，不添加字段或改变旧快照内容。
        var canonical = objects.OrderBy(value => value.Schema, StringComparer.Ordinal).ThenBy(value => value.Name, StringComparer.Ordinal)
            .ThenBy(value => value.Kind, StringComparer.Ordinal).Select(value => value with { Fields = value.Fields.OrderBy(field => field.Ordinal).ThenBy(field => field.Name, StringComparer.Ordinal).ToArray() }).ToArray();
        return (canonical, Hash(Encode(new { AdapterVersion = config is OracleConnectionConfig ? "oracle-m2-v1" : config is WebApiConnectionConfig ? "web-m2-v1" : "pg-m1-v1", Objects = canonical })));
    }

}
