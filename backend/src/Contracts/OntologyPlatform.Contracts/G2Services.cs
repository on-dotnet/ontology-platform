using System.Data.Common;

namespace OntologyPlatform.Contracts;

/// <summary>由Governance自己执行并加入调用方物理PG事务的唯一审计边界。</summary>
public interface ITransactionalAuditWriter
{
    /// <summary>只写本模块审计且不提交外层事务，成功ID在外层commit后才能公开。</summary>
    /// <param name="actor">服务器验证的主体。</param>
    /// <param name="command">固定操作及已授权范围。</param>
    /// <param name="connection">外层已打开的同一物理PG连接。</param>
    /// <param name="transaction">同一物理PG事务。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>尚待外层提交的审计标识。</returns>
    Task<string> WriteAsync(ActorContext actor, AuditCommand command, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken);
}

/// <summary>草稿持久应用用例，HTTP与业务逻辑保持分离。</summary>
public interface IOntologyService
{
    /// <summary>只列出完整范围获准的持久草稿。</summary>
    /// <param name="actor">可信主体。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>真实草稿集合。</returns>
    Task<OntologyDraft[]> ListAsync(ActorContext actor, CancellationToken cancellationToken);

    /// <summary>创建经真实解析的草稿及原子审计。</summary>
    /// <param name="actor">可信主体。</param>
    /// <param name="request">创建与幂等命令。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>已提交草稿。</returns>
    Task<OntologyDraft> CreateAsync(ActorContext actor, CreateDraftRequest request, CancellationToken cancellationToken);

    /// <summary>读取完整授权范围内的真实草稿。</summary>
    /// <param name="actor">可信主体。</param>
    /// <param name="draftId">草稿ID。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>真实源码、修订与投影。</returns>
    Task<OntologyDraft> ReadAsync(ActorContext actor, string draftId, CancellationToken cancellationToken);

    /// <summary>按期望修订CAS保存完整源码并保留旧修订。</summary>
    /// <param name="actor">可信主体。</param>
    /// <param name="draftId">草稿ID。</param>
    /// <param name="request">完整源和修订命令。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>新持久修订。</returns>
    Task<OntologyDraft> SaveAsync(ActorContext actor, string draftId, SaveDraftRequest request, CancellationToken cancellationToken);

    /// <summary>只按批准子集对标准RDF做精确编辑。</summary>
    /// <param name="actor">可信主体。</param>
    /// <param name="draftId">草稿ID。</param>
    /// <param name="request">显式语义变更和修订。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>真实新源码与同修订投影。</returns>
    Task<OntologyDraft> EditAsync(ActorContext actor, string draftId, EditDraftRequest request, CancellationToken cancellationToken);

    /// <summary>比较指定基础修订与当前修订的真实源和语义。</summary>
    /// <param name="actor">可信主体。</param>
    /// <param name="draftId">草稿ID。</param>
    /// <param name="fromRevision">基础修订。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>标准差异与未支持边界。</returns>
    Task<DraftDiff> DiffAsync(ActorContext actor, string draftId, long fromRevision, CancellationToken cancellationToken);

    /// <summary>对精确修订执行并持久保存真实校验。</summary>
    /// <param name="actor">可信主体。</param>
    /// <param name="draftId">草稿ID。</param>
    /// <param name="request">精确源散列与修订。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>真实报告。</returns>
    Task<SemanticValidationReport> ValidateAsync(ActorContext actor, string draftId, ValidateDraftRequest request, CancellationToken cancellationToken);
}

/// <summary>由Ontology拥有的发布源只读锁定边界，禁止其他模块直写草稿表。</summary>
public interface IDraftPublicationReader
{
    /// <summary>在调用方事务内锁定当前草稿并核实成功报告与全部修订散列。</summary>
    /// <param name="actor">可信主体。</param>
    /// <param name="draftId">草稿ID。</param>
    /// <param name="revision">已批准修订。</param>
    /// <param name="hashes">已批准全部源散列。</param>
    /// <param name="reportId">真实成功校验标识。</param>
    /// <param name="connection">共同物理连接。</param>
    /// <param name="transaction">共同事务。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>不可变发布源快照。</returns>
    Task<DraftPublicationSnapshot> LockForPublicationAsync(ActorContext actor, string draftId, long revision, SourceHashes hashes, string reportId, DbConnection connection, DbTransaction transaction, CancellationToken cancellationToken);
}

/// <summary>只提供受控RDF操作的内部Jena适配，不暴露任意查询或管理地址。</summary>
public interface ISemanticRuntime
{
    /// <summary>由RIOT解析真实源码并生成有界完整投影。</summary>
    /// <param name="sources">权威源码。</param>
    /// <param name="revision">对应修订。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>实际散列与投影。</returns>
    Task<SemanticAnalysis> AnalyzeAsync(SourceBundle sources, long revision, CancellationToken cancellationToken);

    /// <summary>执行真实SHACL并返回标准定位报告，调用者绑定草稿身份。</summary>
    /// <param name="sources">固定源码。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>实际验证报告。</returns>
    Task<SemanticValidationReport> ValidateAsync(SourceBundle sources, CancellationToken cancellationToken);

    /// <summary>在完整标准图上执行白名单精确编辑，未知结构必须阻断。</summary>
    /// <param name="sources">原始完整源码。</param>
    /// <param name="edit">精确三元组变更。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>完整新源码，不从图形JSON重建。</returns>
    Task<SourceBundle> ApplyEditAsync(SourceBundle sources, SemanticEdit edit, CancellationToken cancellationToken);

    /// <summary>将已准备源加载为此发布独占的正式版本图。</summary>
    /// <param name="manifest">服务器生成的固定图清单。</param>
    /// <param name="sources">散列匹配的完整源。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>部署完成任务。</returns>
    Task DeployAsync(ReleaseManifest manifest, SourceBundle sources, CancellationToken cancellationToken);

    /// <summary>真实回读验证正式图、标准约束与受控查询，不修改活动指针。</summary>
    /// <param name="manifest">固定版本清单。</param>
    /// <param name="sources">用于精确对账的权威源。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>仅全部实际回验符合时为真。</returns>
    Task<bool> VerifyAsync(ReleaseManifest manifest, SourceBundle sources, CancellationToken cancellationToken);

    /// <summary>只读取服务器确认的正式图，不接受用户SPARQL。</summary>
    /// <param name="snapshot">来自正式发布Catalog的完整快照。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>有界真实三元组。</returns>
    Task<PublishedRdfData> ReadPublishedAsync(AssetVersionSnapshot snapshot, CancellationToken cancellationToken);
}

/// <summary>以完整范围再次授权正式版本，供网关与运行固定快照。</summary>
public interface IReleaseCatalog
{
    /// <summary>一次解析当前活动或显式历史正式版本，禁止半准备版本。</summary>
    /// <param name="actor">可信主体。</param>
    /// <param name="assetId">永久唯一范围资产。</param>
    /// <param name="releaseId">可选历史发布，空时解析当前活动。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>已授权的正式清单与实际状态。</returns>
    Task<ReleaseSummary> ResolveAsync(ActorContext actor, string assetId, string? releaseId, CancellationToken cancellationToken);
}

/// <summary>只提供受控不可变发布对象的适配边界。</summary>
public interface IReleaseArtifactStore
{
    /// <summary>对象不存在时写入，相同字节可重试，不同字节绝不覆盖。</summary>
    /// <param name="objectKey">服务器受控对象键。</param>
    /// <param name="content">精确对象字节。</param>
    /// <param name="contentType">固定媒体类型。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>经真实回读核验的引用。</returns>
    Task<ArtifactObject> PutImmutableAsync(string objectKey, ReadOnlyMemory<byte> content, string contentType, CancellationToken cancellationToken);

    /// <summary>读取固定对象且核对期望SHA256，缺失错版必须失败。</summary>
    /// <param name="artifact">可信清单中的对象引用。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>实际完整字节。</returns>
    Task<byte[]> ReadVerifiedAsync(ArtifactObject artifact, CancellationToken cancellationToken);
}

/// <summary>REST、MCP和MAF共同调用的唯一受控语义网关。</summary>
public interface ISemanticGateway
{
    /// <summary>按可信身份、固定发布、真实关系及预算执行登记能力。</summary>
    /// <param name="actor">可信服务器身份。</param>
    /// <param name="plan">有限语义计划。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>唯一六态真实结果与证据。</returns>
    Task<SemanticQueryResult> ExecuteAsync(ActorContext actor, SemanticQueryPlan plan, CancellationToken cancellationToken);

    /// <summary>读取由同一输入输出Schema生成的实际能力登记。</summary>
    /// <returns>登记的受控能力。</returns>
    SemanticCapability[] GetCapabilities();
}

/// <summary>证据打开时重新授权并回验真实来源，禁止信任答案携带的任意对象。</summary>
public interface IEvidenceService
{
    /// <summary>由服务端定位可信证据并再次核查完整范围与对象hash。</summary>
    /// <param name="actor">当前可信身份。</param>
    /// <param name="evidenceId">服务器生成证据ID。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>重新核验的唯一证据。</returns>
    Task<EvidenceRef> ReadAsync(ActorContext actor, string evidenceId, CancellationToken cancellationToken);
}

/// <summary>仅治理模块拥有的独立查询或安全拒绝审计边界。</summary>
public interface IAuditTrail
{
    /// <summary>持久提交不涉及其他业务修改的审计事实，失败关闭。</summary>
    /// <param name="actor">当前可信主体。</param>
    /// <param name="command">固定事件与完整授权范围。</param>
    /// <param name="cancellationToken">取消信号。</param>
    /// <returns>已提交审计标识。</returns>
    Task<string> WriteAsync(ActorContext actor, AuditCommand command, CancellationToken cancellationToken);
}
