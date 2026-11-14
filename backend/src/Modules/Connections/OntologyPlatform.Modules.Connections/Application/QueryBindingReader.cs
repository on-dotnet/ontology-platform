using System.Data;
using System.Data.Common;
using System.Globalization;
using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>只读固定映射及当前平台版本，源ACL和schema由各独立读取分支核验。</summary>
public sealed class QueryBindingReader : IG4QueryBindingReader, IG4SourceQueryReader
{
    /// <summary>只访问Connections模块自己的表。</summary>
    private readonly IDbContextFactory<ConnectionsDbContext> factory;

    /// <summary>秘密仅由本模块解密后交给固定PG适配器。</summary>
    private readonly ConnectionSecretCipher cipher;

    /// <summary>每个源分支的唯一类型化PG执行器。</summary>
    private readonly IG4PgQueryReader sourceReader;

    /// <summary>源读取之前重验真实会话与单条完整字段授权。</summary>
    private readonly IG4QueryAuthorizationAuthority authority;

    /// <summary>与授权及源预算共享的真实UTC时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>使用正式模块工厂，不持有共享长生命周期DbContext。</summary>
    public QueryBindingReader(IDbContextFactory<ConnectionsDbContext> factory, ConnectionSecretCipher cipher, IG4PgQueryReader sourceReader, IG4QueryAuthorizationAuthority authority, TimeProvider clock)
    {
        this.factory = factory;
        this.cipher = cipher;
        this.sourceReader = sourceReader;
        this.authority = authority;
        this.clock = clock;
    }

    /// <summary>每个分支的真实完整投影与PG执行器共享字段枚举，避免授权漏列。</summary>
    public G4QueryProjection DescribeProjection(G4QueryBindingContext context, string entityBindingId)
    {
        // 绑定只能来自已验证的manifest，不根据客户端字符串选择自由表。
        var entity = context.Manifest.Mapping.Entities.SingleOrDefault(item => item.Id == entityBindingId) ?? throw Stale();
        // 字段依赖包括范围、身份和时间，即使不显示给UI也必须有当前许可。
        var fields = PgQueryReader.Fields(context.Manifest.Mapping, entity).Distinct().ToArray();
        return new G4QueryProjection
        {
            ObjectRefs = fields.Select(field => MappingValidationService.ObjectPermission(field.DatasetRef.Schema, field.DatasetRef.Name)).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray(),
            FieldRefs = fields.Select(field => MappingValidationService.ObjectPermission(field.DatasetRef.Schema, field.DatasetRef.Name)
                + "/" + field.Ordinal.ToString(CultureInfo.InvariantCulture) + "/" + Uri.EscapeDataString(field.Name)).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray()
        };
    }

    /// <summary>真实字段授权与当前凭据均在源IO之前核验，平台连接不持长事务。</summary>
    public async Task<G4SourceQueryRead> ReadAsync(G4QueryBindingContext context, MappingAuthorizationProof proof,
        string entityBindingId, G4SemanticQuery query, DateTimeOffset deadlineAtUtc, CancellationToken cancellationToken)
    {
        // 执行前严格比较实际投影，不接受少字段或其他来源的授权证明。
        var projection = DescribeProjection(context, entityBindingId);
        if (proof.ExpiresAtUtc <= clock.GetUtcNow() || proof.Permission != "data.query.execute" || proof.ConnectionId != context.Binding.ConnectionId
            || proof.Scope.OrganizationId != context.Scope.OrganizationId
            || !proof.Scope.SiteIds.Order(StringComparer.Ordinal).SequenceEqual(context.Scope.SiteIds.Order(StringComparer.Ordinal))
            || !projection.ObjectRefs.SequenceEqual(proof.ObjectRefs.Order(StringComparer.Ordinal))
            || !projection.FieldRefs.SequenceEqual(proof.FieldRefs.Order(StringComparer.Ordinal))) throw Forbidden();
        // 捕获是当前真实数据库复核；epoch必须仍等于固定绑定，不能静默升级授权。
        var currentProof = await authority.CaptureAsync(proof, cancellationToken);
        if (currentProof.AuthorizationEpoch.ToString(CultureInfo.InvariantCulture) != context.Binding.AuthorizationEpoch
            || proof.AuthorizationEpoch != currentProof.AuthorizationEpoch) throw Forbidden();
        // 独立平台上下文只读当前连接和密文，不把源读取放进平台事务。
        await using var database = await factory.CreateDbContextAsync(cancellationToken);
        // 组织条件进入SQL，其他组织秘密永不进入当前进程。
        var connection = await database.Connections.AsNoTracking().SingleOrDefaultAsync(row => row.Id == context.Binding.ConnectionId
            && row.OrganizationId == context.Scope.OrganizationId, cancellationToken) ?? throw Forbidden();
        if (connection.State != "ACTIVE" || connection.Revision.ToString(CultureInfo.InvariantCulture) != context.Binding.ConnectionRevision
            || connection.ConfigHash != context.Binding.ConfigHash || connection.SecretVersion.ToString(CultureInfo.InvariantCulture) != context.Binding.SecretVersion
            || !context.Scope.SiteIds.All(connection.SiteIds.Contains)) throw Stale();
        // 强类型配置不能替换为其他连接器或自由URL。
        var config = ConnectionApplicationService.Decode<ConnectionConfig>(connection.ConfigJson) as PgConnectionConfig ?? throw Stale();
        // 只解密当前准确版本的已绑定秘密，不回读旧密钥执行历史查询。
        var secret = await database.ConnectionSecrets.AsNoTracking().SingleOrDefaultAsync(row => row.Id == connection.SecretId, cancellationToken);
        if (secret is null || secret.ConnectionId != connection.Id || secret.UsedAtUtc is null || secret.Version != connection.SecretVersion
            || secret.OrganizationId != connection.OrganizationId || secret.Purpose != "POSTGRESQL_READONLY" || string.IsNullOrEmpty(secret.Owner)
            || !secret.SiteIds.Order(StringComparer.Ordinal).SequenceEqual(connection.SiteIds.Order(StringComparer.Ordinal))) throw Stale();
        return await sourceReader.ReadAsync(config.Profile, cipher.Decrypt(secret), context, entityBindingId, query, deadlineAtUtc, cancellationToken);
    }

    /// <summary>发布ID相同不足以证明一致，完整绑定同时包含激活修订和当前连接身份。</summary>
    public static void DemandSameVersion(G4QueryBinding captured, G4QueryBinding current)
    {
        if (captured != current) throw Stale();
    }

    /// <summary>捕获不可变原件和当前绑定，不执行源网络IO；epoch零仅供授权投影解析，执行前必须固定非零真实证明。</summary>
    public async Task<G4QueryBindingContext> CaptureAsync(ActorContext actor, G4SemanticQuery query, long authorizationEpoch, CancellationToken cancellationToken)
    {
        // 正式工厂提供独立短生命周期上下文，随后提交前仍需事务复核。
        await using var database = await factory.CreateDbContextAsync(cancellationToken);
        return await CaptureCoreAsync(database, actor, query, authorizationEpoch, cancellationToken);
    }

    /// <summary>组织授权锁由调用方先取得，再依次锁连接、映射并验证全部固定身份。</summary>
    public async Task VerifyInTransactionAsync(ActorContext actor, G4SemanticQuery query, G4QueryBinding expected,
        DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken)
    {
        try
        {
            if (connection.State != ConnectionState.Open || !ReferenceEquals(connection, transaction.Connection))
                throw new InvalidOperationException("查询绑定复核必须加入同物理事务。");
            // 本模块不拥有传入连接，也不提交调用方事务。
            await using var database = await factory.CreateDbContextAsync(cancellationToken);
            database.Database.SetDbConnection(connection, contextOwnsConnection: false);
            await database.Database.UseTransactionAsync(transaction, cancellationToken);
            await ConnectionApplicationService.LockAsync(database, "connection:" + expected.ConnectionId, cancellationToken);
            await ConnectionApplicationService.LockAsync(database, "mapping:" + expected.MappingId, cancellationToken);
            // 授权epoch由Governance先核，不能从Mapping历史授权版本冒充当前值。
            var epoch = long.Parse(expected.AuthorizationEpoch, NumberStyles.None, CultureInfo.InvariantCulture);
            if (epoch < 1) throw Stale();
            // 新上下文强制从数据库读取，不复用捕获时的跟踪状态。
            var current = await CaptureCoreAsync(database, actor, query, epoch, cancellationToken);
            DemandSameVersion(expected, current.Binding);
        }
        catch
        {
            await transaction.RollbackAsync(CancellationToken.None);
            throw;
        }
    }

    /// <summary>原manifest与当前activation绑定分离，任何漂移均不得静默切换版本。</summary>
    private static async Task<G4QueryBindingContext> CaptureCoreAsync(ConnectionsDbContext database, ActorContext actor,
        G4SemanticQuery query, long authorizationEpoch, CancellationToken token)
    {
        if (!actor.Roles.Any(role => role is "platform.viewer" or "platform.operator" or "platform.auditor")
            || query.MappingReleaseIds.Length != 1 || authorizationEpoch < 0) throw Forbidden();
        // 先以可信组织过滤，未知或异组织snapshot统一403，不能泄露其存在性。
        var release = await database.MappingReleases.AsNoTracking().SingleOrDefaultAsync(row => row.Id == query.MappingReleaseIds[0]
            && row.OrganizationId == actor.OrganizationId, token) ?? throw Forbidden();
        // 只执行当前主体与请求的厂区交集，不要求获得映射其他厂区的源字段。
        var sites = release.SiteIds.Intersect(actor.SiteIds, StringComparer.Ordinal)
            .Where(site => query.Filters.SiteId is null || query.Filters.SiteId == site).Order(StringComparer.Ordinal).ToArray();
        if (sites.Length == 0) throw Forbidden();
        // 原字节hash先验证，再解码定义；不重算历史manifest身份。
        var manifest = MappingApplicationService.Original<MappingReleaseManifest>(release.CanonicalBytes, release.ContentHash);
        if (manifest.MappingReleaseId != release.Id || manifest.MappingId != release.MappingId
            || manifest.Scope.OrganizationId != actor.OrganizationId || !sites.All(manifest.Scope.SiteIds.Contains)) throw Stale();
        if (manifest.Binding.OntologyReleaseId != query.OntologyReleaseId) throw Stale();
        // 当前指针必须仍指向指定发布，A到B再到A由激活身份及修订识别。
        var active = await database.MappingActives.AsNoTracking().SingleOrDefaultAsync(row => row.MappingId == release.MappingId
            && row.OrganizationId == actor.OrganizationId, token) ?? throw Stale();
        if (active.ReleaseId != release.Id) throw Stale();
        // 激活收据为不可变原件，BindingJson只作为本次激活版本材料。
        var activation = await database.MappingActivations.AsNoTracking().SingleOrDefaultAsync(row => row.Id == active.ActivationId
            && row.OrganizationId == actor.OrganizationId && row.MappingId == release.MappingId, token) ?? throw Stale();
        // 原激活收据hash必须与索引身份一致，拒绝不一致的数据库投影。
        var receipt = MappingApplicationService.Original<MappingActivationReceipt>(activation.CanonicalBytes, activation.ContentHash);
        if (activation.ReleaseId != release.Id || activation.ActivationRevision != active.ActivationRevision
            || receipt.ActivationId != active.ActivationId || receipt.ActivationRevision != active.ActivationRevision
            || receipt.MappingReleaseId != release.Id || receipt.ManifestHash != release.ContentHash) throw Stale();
        // 当前源身份来自激活绑定，原目录仍来自原发布绑定。
        var current = MappingApplicationService.Decode<MappingVersionBinding>(activation.BindingJson);
        if (current.SourceConnectionId != manifest.Binding.SourceConnectionId || current.SourceType != "POSTGRESQL"
            || current.OntologyReleaseId != query.OntologyReleaseId || current.MappingHash != manifest.Binding.MappingHash) throw Stale();
        // 本模块拥有连接表，其他模块只得到不可变版本身份。
        var source = await database.Connections.AsNoTracking().SingleOrDefaultAsync(row => row.Id == current.SourceConnectionId
            && row.OrganizationId == actor.OrganizationId, token) ?? throw Forbidden();
        if (!sites.All(source.SiteIds.Contains)) throw Forbidden();
        if (source.State != "ACTIVE" || source.Revision != current.ConnectionRevision || source.ConfigHash != current.ConfigHash
            || source.SecretVersion != current.SecretVersion) throw Stale();
        // 目录更新不得在一次固定查询中静默换成新ID。
        var newest = await database.CatalogSnapshots.AsNoTracking().Where(row => row.ConnectionId == source.Id
            && row.OrganizationId == actor.OrganizationId && row.ConfigHash == source.ConfigHash && row.SecretVersion == source.SecretVersion)
            .OrderByDescending(row => row.CapturedAtUtc).ThenByDescending(row => row.Id).FirstOrDefaultAsync(token) ?? throw Stale();
        if (newest.Id != current.SourceCatalogSnapshotId) throw Stale();
        // 原目录是历史证据链的一环，即使当前目录重扫也不能覆盖。
        var origin = await database.CatalogSnapshots.AsNoTracking().SingleOrDefaultAsync(row => row.Id == manifest.Binding.SourceCatalogSnapshotId
            && row.OrganizationId == actor.OrganizationId && row.ConnectionId == source.Id, token) ?? throw Stale();
        // 两份目录分别校验自己原有身份，不将M4规范编码套用于M1指纹。
        var originalCatalog = ConnectionApplicationService.Decode<CatalogSnapshotView>(origin.ViewJson);
        // 当前目录提供执行时登记对象列，源事务随后逐分支核实。
        var currentCatalog = ConnectionApplicationService.Decode<CatalogSnapshotView>(newest.ViewJson);
        if (currentCatalog.Status != "READY" || currentCatalog.SnapshotId != newest.Id || currentCatalog.ConnectionId != source.Id
            || currentCatalog.SchemaFingerprint != current.SourceCatalogFingerprint || originalCatalog.SnapshotId != origin.Id
            || originalCatalog.SchemaFingerprint != manifest.Binding.SourceCatalogFingerprint) throw Stale();
        return new G4QueryBindingContext
        {
            Binding = new G4QueryBinding
            {
                MappingId = release.MappingId, MappingReleaseId = release.Id, ManifestHash = release.ContentHash,
                OriginalCatalogSnapshotId = origin.Id, OriginalCatalogFingerprint = originalCatalog.SchemaFingerprint,
                ActivationId = active.ActivationId, ActivationRevision = active.ActivationRevision.ToString(CultureInfo.InvariantCulture),
                CurrentCatalogSnapshotId = newest.Id, CurrentCatalogFingerprint = currentCatalog.SchemaFingerprint,
                ConnectionId = source.Id, ConnectionRevision = source.Revision.ToString(CultureInfo.InvariantCulture),
                ConfigHash = source.ConfigHash, SecretVersion = source.SecretVersion.ToString(CultureInfo.InvariantCulture),
                OntologyReleaseId = query.OntologyReleaseId, AuthorizationEpoch = authorizationEpoch.ToString(CultureInfo.InvariantCulture),
                CapabilityVersion = query.CapabilityVersion
            },
            Manifest = manifest, Scope = new ResourceScope { OrganizationId = actor.OrganizationId, SiteIds = sites },
            OriginalCatalog = originalCatalog, CurrentCatalog = currentCatalog
        };
    }

    /// <summary>根范围不可见时只有固定拒绝，不返回映射、目录或连接身份。</summary>
    private static SemanticOperationException Forbidden() => new(403, "query_forbidden");

    /// <summary>已可见但执行身份漂移时要求显式发起新查询。</summary>
    private static SemanticOperationException Stale() => new(409, "query_binding_stale");
}
