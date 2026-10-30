using System.Data;
using System.Data.Common;
using Microsoft.EntityFrameworkCore;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Governance;

/// <summary>由治理模块自己写审计，支持共享物理事务及独立提交的安全事实。</summary>
public sealed class TransactionalAuditWriter : ITransactionalAuditWriter, IAuditTrail
{
    /// <summary>创建仅拥有Governance表的独立上下文，不复用其他模块的跟踪实体。</summary>
    private readonly IDbContextFactory<GovernanceDbContext> factory;

    /// <summary>本轮批准的固定审计事件，禁止把来源、Prompt或异常当作事件。</summary>
    private static readonly HashSet<string> Actions = new(StringComparer.Ordinal)
    {
        "ontology.create", "ontology.save", "ontology.edit", "ontology.validate", "ontology.assess", "ontology.impact.generate", "ontology.read", "ontology.list", "ontology.diff",
        "release.proposal.create", "release.approval.decide", "release.activate", "release.rollback",
        "semantic.query", "semantic.evidence.read", "execution.run.create", "execution.run.start", "execution.run.tool",
        "execution.run.complete", "execution.run.fail", "execution.run.cancel", "execution.events.read", "authorization.denied", "csrf.denied"
    };

    /// <summary>以宿主配置的模块工厂构造事务审计写入器。</summary>
    /// <param name="factory">Governance专属上下文工厂。</param>
    public TransactionalAuditWriter(IDbContextFactory<GovernanceDbContext> factory)
    {
        this.factory = factory;
    }

    /// <summary>显式加入同一个物理事务，失败时回滚整笔业务，成功时由外层决定提交。</summary>
    /// <param name="actor">服务器验证主体。</param>
    /// <param name="command">固定事件与完整资源范围。</param>
    /// <param name="connection">调用者拥有的已打开物理连接。</param>
    /// <param name="transaction">此连接正在执行的事务。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>尚未提交的审计标识，外层提交之前不得公开。</returns>
    public async Task<string> WriteAsync(ActorContext actor, AuditCommand command, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken)
    {
        try
        {
            // 连接前置失败也必须使调用方事务失效，不能留下可单独提交的业务写入。
            if (connection.State != ConnectionState.Open || !ReferenceEquals(transaction.Connection, connection))
            {
                throw new InvalidOperationException("审计必须加入调用方同一已打开物理连接与事务。");
            }
            // 工厂保留治理模型配置；替换连接后不取得调用方连接所有权。
            await using var database = await factory.CreateDbContextAsync(cancellationToken);
            database.Database.SetDbConnection(connection, contextOwnsConnection: false);
            await database.Database.UseTransactionAsync(transaction, cancellationToken);
            // 范围与固定元数据先验证，再由治理上下文自己写入治理表。
            var record = CreateRecord(actor, command);
            database.AuditRecords.Add(record);
            await database.SaveChangesAsync(cancellationToken);
            return record.Id;
        }
        catch
        {
            // EF可能仅回滚Savepoint；显式整笔回滚防止调用者捕获审计失败后提交业务。
            await transaction.RollbackAsync(CancellationToken.None);
            throw;
        }
    }

    /// <summary>独立审计拥有自己的短事务，提交成功后才返回标识。</summary>
    /// <param name="actor">当前可信主体。</param>
    /// <param name="command">固定安全事件及完整资源范围。</param>
    /// <param name="cancellationToken">请求取消信号。</param>
    /// <returns>已经提交的审计标识。</returns>
    public async Task<string> WriteAsync(ActorContext actor, AuditCommand command, CancellationToken cancellationToken)
    {
        // 不涉及业务变更的安全拒绝与读取事实由治理自己拥有事务生命周期。
        await using var database = await factory.CreateDbContextAsync(cancellationToken);
        // 外层事务明确控制业务与审计的共同提交或回滚。
        await using var transaction = await database.Database.BeginTransactionAsync(cancellationToken);
        // 创建及保存共用相同元数据验证，不造第二种审计格式。
        var record = CreateRecord(actor, command);
        database.AuditRecords.Add(record);
        await database.SaveChangesAsync(cancellationToken);
        await transaction.CommitAsync(cancellationToken);
        return record.Id;
    }

    /// <summary>只接受固定操作结果与服务器受控标识，并保留真实完整范围。</summary>
    /// <param name="actor">可信身份及安全关联标识。</param>
    /// <param name="command">调用模块已经授权的范围与固定资源标识。</param>
    /// <returns>治理模块拥有的待保存实体。</returns>
    private static AuditRecord CreateRecord(ActorContext actor, AuditCommand command)
    {
        ArgumentNullException.ThrowIfNull(actor);
        ArgumentNullException.ThrowIfNull(command);
        if (!Actions.Contains(command.Action) || command.Outcome is not ("allowed" or "denied" or "failure")
            || !IsIdentifier(command.Resource, 256) || !IsIdentifier(actor.SubjectId, 256)
            || !IsIdentifier(actor.TraceId, 64) || !IsIdentifier(actor.CorrelationId, 64)
            || command.Scope is null || !IsIdentifier(command.Scope.OrganizationId, 128)
            || command.Scope.SiteIds is null || command.Scope.SiteIds.Any(site => !IsIdentifier(site, 128)))
        {
            throw new InvalidOperationException("审计元数据未满足固定事件和完整范围合同。");
        }
        // 范围是集合且按确定顺序保存；不能只取第一厂伪造单厂语义。
        var sites = command.Scope.SiteIds.Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray();
        return new AuditRecord
        {
            Actor = actor.SubjectId,
            Action = command.Action,
            Resource = command.Resource,
            Outcome = command.Outcome,
            OrganizationId = command.Scope.OrganizationId,
            ScopeSiteIds = sites,
            SiteId = sites.Length == 1 ? sites[0] : null,
            TraceId = actor.TraceId,
            CorrelationId = actor.CorrelationId
        };
    }

    /// <summary>限制标识存储格式；调用方仍必须提供服务器受控标识，字符合法不等于已授权。</summary>
    /// <param name="value">受控标识。</param>
    /// <param name="maximum">对应治理字段的最大长度。</param>
    /// <returns>非空有限安全字符标识时为真。</returns>
    private static bool IsIdentifier(string? value, int maximum)
    {
        return !string.IsNullOrWhiteSpace(value) && value.Length <= maximum
            && value.All(character => char.IsAsciiLetterOrDigit(character) || character is '.' or '_' or '-' or ':' or '/' or '@');
    }
}
