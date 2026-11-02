using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>创建、凭据绑定和版本化编辑用例。</summary>
public sealed partial class ConnectionApplicationService
{
    /// <summary>只允许同actor、同精确scope、用途正确、未使用且未过期的引用。</summary>
    private async Task<ConnectionSecretRecord> UnboundSecretAsync(ConnectionsDbContext db, ActorContext actor, string id, ResourceScope scope, CancellationToken token)
    {
        // 在同事务内串行化引用绑定，两个连接不能消费同一Ref。
        if (db.Database.CurrentTransaction is not null) await LockAsync(db, "secret:" + id, token);
        // 先组织与owner过滤，绝不解密不属于调用者的秘密。
        var row = await db.ConnectionSecrets.SingleOrDefaultAsync(value => value.Id == id && value.OrganizationId == actor.OrganizationId && value.Owner == actor.SubjectId, token);
        if (row is null || row.UsedAtUtc is not null || row.ExpiresAtUtc <= clock.GetUtcNow() || row.Purpose != "POSTGRESQL_READONLY"
            || Encode(Normalize(new ResourceScope { OrganizationId = row.OrganizationId, SiteIds = row.SiteIds })) != Encode(Normalize(scope)))
            throw new SemanticOperationException(422, "connection_secret_expired");
        DemandScope(actor, scope);
        return row;
    }

    /// <summary>签发合成密钥引用与审计同事务，秘密原文不进入幂等回执。</summary>
    private Task<ConnectionReply> IntakeAsync(ConnectionInvocation call, CancellationToken token)
    {
        // HTTP已严格解析，应用再次复用同一规则而不重新读取请求流。
        var request = (ConnectionSecretIntakeRequest)call.Body!;
        return CommandAsync<SecretIntakeReceipt>(call, request.Command, "connection.secret.intake", 201, (db, _) =>
        {
            DemandScope(call.Actor, request.ScopeSelection);
            // 创建随机不透明ID，不把actor、host或密码编码到引用。
            var row = new ConnectionSecretRecord
            {
                Id = Guid.NewGuid().ToString("N"),
                Owner = call.Actor.SubjectId,
                OrganizationId = request.ScopeSelection.OrganizationId,
                SiteIds = Normalize(request.ScopeSelection).SiteIds,
                Purpose = request.Purpose,
                ExpiresAtUtc = clock.GetUtcNow().AddMinutes(10)
            };
            cipher.Encrypt(row, request.SecretValue);
            db.ConnectionSecrets.Add(row);
            // 此回执仅从专用HTTPS/可信本地Intake返回。
            var receipt = new SecretIntakeReceipt { SecretRef = row.Id, CredentialVersion = row.Version, ExpiresAtUtc = row.ExpiresAtUtc, UsageLimit = 1 };
            return Task.FromResult((receipt, Normalize(request.ScopeSelection), Normalize(request.ScopeSelection), (string?)null));
        }, token);
    }

    /// <summary>绑定一次性秘密并始终创建DRAFT，绝不继承未保存Probe。</summary>
    private Task<ConnectionReply> CreateAsync(ConnectionInvocation call, CancellationToken token)
    {
        // 非PG在任何写入或秘密消费前拒绝。
        var request = (ConnectionCreateRequest)call.Body!;
        _ = Pg(request.Config);
        DemandScope(call.Actor, request.ScopeSelection);
        return CommandAsync<ConnectionView>(call, request.Command, "connection.create", 201, async (db, ct) =>
        {
            // 先验证引用owner/用途/TTL，再创建绑定对象。
            var secret = await UnboundSecretAsync(db, call.Actor, request.SecretRef!, request.ScopeSelection, ct);
            // 创建仅使用当前可信scope，不把草稿Probe当已保存成功事实。
            var row = new ConnectionRecord
            {
                Id = Guid.NewGuid().ToString("N"),
                DisplayName = request.DisplayName,
                OrganizationId = request.ScopeSelection.OrganizationId,
                SiteIds = Normalize(request.ScopeSelection).SiteIds,
                ConfigJson = Encode(request.Config),
                SecretId = secret.Id,
                UpdatedAtUtc = clock.GetUtcNow()
            };
            secret.UsedAtUtc = clock.GetUtcNow();
            secret.ConnectionId = row.Id;
            Rehash(row);
            db.Connections.Add(row);
            return (await ViewAsync(db, call.Actor, row, ct), Scope(row), Scope(row), (string?)Etag(row));
        }, token);
    }

    /// <summary>编辑、轮换和禁用原子失效旧Probe，并持久取消已排队的发现。</summary>
    private Task<ConnectionReply> EditAsync(ConnectionInvocation call, CancellationToken token)
    {
        // 命令来自三个固定DTO之一，不接受客户端动态操作名。
        var command = call.Body switch { ConnectionPatchRequest patch => patch.Command, ConnectionRotateSecretRequest rotate => rotate.Command, ConnectionMutationCommand mutation => mutation.Command, _ => throw new SemanticOperationException(422, "connection_profile_invalid") };
        // action来自固定操作集合，治理仍有严格白名单。
        var action = call.Operation switch { "patch" => "connection.update", "rotate" => "connection.secret.rotate", _ => "connection.disable" };
        return CommandAsync<ConnectionView>(call, command, action, 200, async (db, ct) =>
        {
            // 在连接事务锁内读取最新配置，确保CAS不被并发编辑绕过。
            var row = await FindAsync(db, call.Actor, call.Id, ct);
            Cas(call, row, command);
            // 原范围保存在回执，scope编辑后重放也必须保持原范围权限。
            var before = Scope(row);
            if (row.State == "DISABLED") throw new SemanticOperationException(409, "connection_disabled");
            if (call.Body is ConnectionPatchRequest patch)
            {
                if (patch.Config is not null) { _ = Pg(patch.Config); row.ConfigJson = Encode(patch.Config); }
                if (patch.DisplayName is not null) row.DisplayName = patch.DisplayName;
                if (patch.ScopeSelection is not null)
                {
                    DemandScope(call.Actor, patch.ScopeSelection);
                    // 凭据AAD必须随完整授权范围原子重新绑定，而不是丢失AEAD保护。
                    var secret = await db.ConnectionSecrets.SingleAsync(value => value.Id == row.SecretId, ct);
                    // 明文仅内存用于同事务重新加密，不返回调用者。
                    var value = cipher.Decrypt(secret);
                    row.SiteIds = Normalize(patch.ScopeSelection).SiteIds;
                    secret.SiteIds = row.SiteIds;
                    cipher.Encrypt(secret, value);
                }
                row.State = "DRAFT";
                Rehash(row);
            }
            else if (call.Body is ConnectionRotateSecretRequest rotate)
            {
                // 新秘密签发操作者及完整范围必须与本次命令一致。
                var next = await UnboundSecretAsync(db, call.Actor, rotate.SecretRef, Scope(row), ct);
                // 更新AEAD版本时先解密原版本，再以新绑定版本重加密。
                var value = cipher.Decrypt(next);
                next.Version = row.SecretVersion + 1;
                cipher.Encrypt(next, value);
                next.UsedAtUtc = clock.GetUtcNow();
                next.ConnectionId = row.Id;
                // 撤销旧版本密文，历史审计仍保留版本引用。
                var previous = await db.ConnectionSecrets.SingleAsync(secret => secret.Id == row.SecretId, ct);
                previous.Ciphertext = string.Empty;
                previous.Tag = string.Empty;
                previous.Nonce = string.Empty;
                row.SecretId = next.Id;
                row.SecretVersion = next.Version;
                row.State = "DRAFT";
            }
            else row.State = "DISABLED";
            row.Revision++;
            row.UpdatedAtUtc = clock.GetUtcNow();
            row.LastProbeId = null;
            // 任何旧版本任务都持久收到取消；运行者提交前还会检查fence和版本。
            var jobs = await db.CatalogJobs.Where(job => job.ConnectionId == row.Id && (job.Status == "QUEUED" || job.Status == "RUNNING")).ToArrayAsync(ct);
            foreach (var job in jobs)
            {
                job.CancelRequested = true;
                if (job.Status == "QUEUED") { job.Status = "CANCELLED"; job.CompletedAtUtc = clock.GetUtcNow(); }
            }
            return (await ViewAsync(db, call.Actor, row, ct), before, Scope(row), (string?)Etag(row));
        }, token);
    }
}
