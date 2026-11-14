using System.Globalization;
using Microsoft.EntityFrameworkCore;
using System.Text.Json;
using System.Text.RegularExpressions;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Connections;

/// <summary>映射的注册纯转换和七阶段评估，不生成或发布本体事实。</summary>
public sealed class MappingValidationService
{
    /// <summary>Connections模块独占的短生命周期持久化上下文。</summary>
    private readonly Microsoft.EntityFrameworkCore.IDbContextFactory<ConnectionsDbContext> factory;

    /// <summary>真实只读源执行器，不能用metadata探测代替业务行验证。</summary>
    private readonly IMappingSourceValidator sourceValidator;

    /// <summary>沿G3固定发布、对象和图回验的词汇读取服务。</summary>
    private readonly IG3VocabularyService vocabulary;

    /// <summary>真实正式发布目录，提供完整scope及Manifest身份。</summary>
    private readonly IReleaseCatalog releases;

    /// <summary>当前会话与精确字段授权，每次IO前后重验。</summary>
    private readonly IMappingAuthorizationAuthority authority;

    /// <summary>绑定凭据只在服务端短期解密。</summary>
    private readonly ConnectionSecretCipher cipher;

    /// <summary>全流程统一UTC时钟。</summary>
    private readonly TimeProvider clock;

    /// <summary>组合既有发布读服务和新受控映射源，不写Publishing或Ontology表。</summary>
    public MappingValidationService(Microsoft.EntityFrameworkCore.IDbContextFactory<ConnectionsDbContext> factory,
        IMappingSourceValidator sourceValidator, IG3VocabularyService vocabulary, IReleaseCatalog releases,
        IMappingAuthorizationAuthority authority, ConnectionSecretCipher cipher, TimeProvider clock)
    {
        this.factory = factory;
        this.sourceValidator = sourceValidator;
        this.vocabulary = vocabulary;
        this.releases = releases;
        this.authority = authority;
        this.cipher = cipher;
        this.clock = clock;
    }

    /// <summary>历史正文GET需要当前真实源ACL，不把平台grant当作数据库列SELECT证据。</summary>
    internal async Task VerifyReadAccessAsync(MappingDraftView draft, CancellationToken token)
    {
        try
        {
            // 读取绑定秘密前调用者已核完整平台grant与字段许可。
            var input = await InputsAsync(draft, token);
            await sourceValidator.VerifyAccessAsync(input.Profile, cipher.Decrypt(input.Secret), input.Current, draft.Mapping, draft.Scope, token, input.Original);
        }
        catch (SemanticOperationException error) when (error.Status is 403 or 409 or 422)
        {
            // 正文读取无法证明当前源字段可见即失败关闭；不能以普通编辑冲突保留旧敏感正文。
            throw new SemanticOperationException(403, "mapping_source_access_unverified");
        }
    }

    /// <summary>跨实例非等待准入：主体一份、连接两份；独立非池化会话断开即释放，不持有平台事务或业务行锁。</summary>
    /// <param name="connectionString">服务端平台PG连接，不能来自客户端。</param>
    /// <param name="organizationId">主体所在组织。</param>
    /// <param name="subjectId">已验证的服务器主体。</param>
    /// <param name="connectionId">固定源连接。</param>
    /// <param name="token">整个评估的有界取消令牌。</param>
    /// <returns>覆盖全部源IO的独立会话租约；调用者必须异步释放。</returns>
    public static async Task<IAsyncDisposable> AcquireCapacityAsync(string connectionString, string organizationId,
        string subjectId, string connectionId, CancellationToken token)
    {
        // 禁止池化，进程退出或取消后不会将持锁会话返还连接池。
        var settings = new Npgsql.NpgsqlConnectionStringBuilder(connectionString) { Pooling = false, Timeout = 3, CommandTimeout = 2 };
        // 此连接只持有准入会话锁，不开启事务，不读写业务表。
        var lease = new Npgsql.NpgsqlConnection(settings.ConnectionString);
        try
        {
            await lease.OpenAsync(token);
            // 固定命名域与JSON编码消除主体/连接拼接歧义。
            var subjectKey = "mapping-capacity-subject:" + JsonSerializer.Serialize(new[] { organizationId, subjectId });
            if (!await TryCapacityAsync(lease, subjectKey, token))
            {
                throw new SemanticOperationException(429, "mapping_capacity_exceeded");
            }
            // 两个固定槽位共用所有验证和激活调用，不依赖进程内计数。
            var sourceKey = "mapping-capacity-source:" + JsonSerializer.Serialize(new[] { organizationId, connectionId });
            if (!await TryCapacityAsync(lease, sourceKey + ":0", token) && !await TryCapacityAsync(lease, sourceKey + ":1", token))
            {
                throw new SemanticOperationException(429, "mapping_capacity_exceeded");
            }
            return lease;
        }
        catch
        {
            await lease.DisposeAsync();
            throw;
        }
    }

    /// <summary>只尝试一个固定会话锁，散列冲突最多保守拒绝，不会放大并发。</summary>
    private static async Task<bool> TryCapacityAsync(Npgsql.NpgsqlConnection connection, string key, CancellationToken token)
    {
        // 所有键均作为参数进入固定SQL，无等待、无事务、无源字段内容。
        await using var command = new Npgsql.NpgsqlCommand("SELECT pg_try_advisory_lock(hashtextextended(@key, 0))", connection);
        command.Parameters.AddWithValue("key", key);
        return await command.ExecuteScalarAsync(token) is true;
    }

    /// <summary>为固定修订或历史Release形成新报告；不覆盖原受审Assessment。</summary>
    public async Task<MappingAssessmentView> AssessAsync(ActorContext actor, string sessionReference, MappingDraftView draft,
        MappingValidationTarget target, string permission, CancellationToken cancellationToken)
    {
        // 此方法只允许服务器固定的验证与激活阶段调用。
        if (permission is not ("mapping.validate" or "mapping.activate"))
        {
            throw new SemanticOperationException(403, "mapping_forbidden");
        }
        // 总评估截止覆盖权限、G3回验、源读取和最终复核，不只限制SQL。
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(30));
        cancellationToken = deadline.Token;
        // 评估固定开始时刻，长源IO不占平台PG行锁。
        var started = clock.GetUtcNow();
        // 当前主体必须拥有完整资源范围与动作grant。
        var proof = await CaptureAsync(actor, sessionReference, draft.Scope, permission, cancellationToken);
        // 准入覆盖发布验证与激活复核；等待源响应期间不占业务事务。
        await using var capacityContext = await factory.CreateDbContextAsync(cancellationToken);
        // 服务端连接串来自模块配置，只有独立非池化租约使用它。
        await using var capacity = await AcquireCapacityAsync(capacityContext.Database.GetConnectionString()!, actor.OrganizationId,
            actor.SubjectId, draft.SourceConnectionId, cancellationToken);
        // 读取原历史目录与当前连接/凭据/可兼容目录，不把新草稿替代回滚目标。
        var input = await InputsAsync(draft, cancellationToken);
        // 源会读取整张表已授权列，明确要求全部实际读取列而非只要求显示列。
        var sourceProof = await CaptureSourceAsync(actor, sessionReference, draft.Scope, input.Connection.Id, draft.Mapping, input.Current, cancellationToken);
        if (sourceProof.AuthorizationEpoch != proof.AuthorizationEpoch)
        {
            throw new SemanticOperationException(409, "mapping_authorization_stale");
        }
        // G3目录先验证正式身份、全部scope、RustFS原字节和真实Jena图。
        var release = await releases.ReadAsync(actor, draft.OntologyReleaseId, cancellationToken);
        if (release.ManifestHash != draft.OntologyManifestHash || release.Manifest.ReleaseId != draft.OntologyReleaseId
            || release.Manifest.Scope.OrganizationId != draft.Scope.OrganizationId
            || !draft.Scope.SiteIds.All(site => release.Manifest.Scope.SiteIds.Contains(site, StringComparer.Ordinal)))
        {
            throw new SemanticOperationException(409, "mapping_ontology_stale");
        }
        // 只读取固定正式版词汇，绝不调用草稿编辑或发布写入。
        var ontology = await vocabulary.ReadReleaseVocabularyAsync(actor, draft.OntologyReleaseId, cancellationToken);
        if (ontology.ManifestHash != draft.OntologyManifestHash || ontology.ReleaseId != draft.OntologyReleaseId)
        {
            throw new SemanticOperationException(409, "mapping_ontology_stale");
        }
        // 解密前已完成精确绑定及权限检查，明文不进入报告或异常。
        var password = cipher.Decrypt(input.Secret);
        // 当前源目录与所有原绑定字段类型必须真实兼容。
        var observation = await sourceValidator.ReadAsync(input.Profile, password, input.Current, draft.Mapping, draft.Scope, cancellationToken, input.Original);
        // 影响分析只涵盖本产品全部登记映射依赖；M4没有开放消费入口。
        var impact = await ImpactAsync(draft, cancellationToken);
        // 网络返回后重新验证实际权限epoch及会话，避免旧证明跨撤权继续生效。
        var finalProof = await CaptureAsync(actor, sessionReference, draft.Scope, permission, cancellationToken);
        // 所有源字段许可也须同一个最终组织epoch。
        var finalSource = await CaptureSourceAsync(actor, sessionReference, draft.Scope, input.Connection.Id, draft.Mapping, input.Current, cancellationToken);
        if (finalProof.AuthorizationEpoch != proof.AuthorizationEpoch || finalSource.AuthorizationEpoch != proof.AuthorizationEpoch)
        {
            throw new SemanticOperationException(409, "mapping_authorization_stale");
        }
        // 重读本模块当前版本，不将源观察期间的连接轮换静默接受。
        var finalInput = await InputsAsync(draft, cancellationToken);
        if (finalInput.Connection.Revision != input.Connection.Revision || finalInput.Connection.ConfigHash != input.Connection.ConfigHash
            || finalInput.Connection.SecretVersion != input.Connection.SecretVersion || finalInput.Current.SnapshotId != input.Current.SnapshotId)
        {
            throw new SemanticOperationException(409, "mapping_source_stale");
        }
        // 七阶段只有真实输入已齐全时才计算；不能靠异常路径补默认PASS。
        var evaluated = Evaluate(draft.Mapping, observation, ontology, draft.Scope, currentAuthority: true, currentImpact: true, impact.Hash);
        cancellationToken.ThrowIfCancellationRequested();
        if (clock.GetUtcNow() - started > TimeSpan.FromSeconds(30))
        {
            throw new SemanticOperationException(422, "mapping_assessment_budget_exceeded");
        }
        // 报告标识先固定，散列不包含自身validationHash，避免循环定义。
        var assessmentId = "ma-" + Guid.NewGuid().ToString("N");
        // 所有当前连接/目录/秘密/权限和固定G3身份逐项绑定。
        var binding = new MappingVersionBinding
        {
            SourceConnectionId = input.Connection.Id,
            ConnectionRevision = input.Connection.Revision,
            ConfigHash = input.Connection.ConfigHash,
            SourceType = "POSTGRESQL",
            SourceCatalogSnapshotId = input.Current.SnapshotId,
            SourceCatalogFingerprint = input.Current.SchemaFingerprint,
            OntologyReleaseId = draft.OntologyReleaseId,
            OntologyManifestHash = draft.OntologyManifestHash,
            MappingHash = Digest(draft.Mapping),
            ValidationHash = new string('0', 64),
            ImpactHash = impact.Hash,
            AssessmentId = assessmentId,
            AdapterVersion = "pg-mapping-v1",
            ExecutorVersion = "mapping-validator-v1",
            CanonicalVersion = "mapping-c14n-v1",
            SecretVersion = input.Connection.SecretVersion,
            AuthorizationEpoch = proof.AuthorizationEpoch
        };
        // 此报告的截止不超过两类授权或源业务校验的本轮十五分钟窗口。
        var finished = clock.GetUtcNow();
        // 不让报告比任何必需主体授权租约活得更久。
        var expiry = new[] { finished.AddMinutes(15), proof.ExpiresAtUtc, sourceProof.ExpiresAtUtc }.Min();
        // 原始报告散列独立固定真实时间、阶段证据及完整预算。
        var validationHash = Digest(new
        {
            schemaVersion = "g4.mapping.v1",
            target,
            inputIdentity = InputIdentity(binding),
            stages = evaluated.Stages,
            evaluated.Issues,
            evaluated.SemanticResultHash,
            evaluated.EvidenceHash,
            status = evaluated.Passed ? "READY_FOR_PROPOSAL" : "BLOCKED",
            expectedActive = impact.Active,
            startedAtUtc = started,
            finishedAtUtc = finished,
            expiresAtUtc = expiry,
            budget = new { tables = 2, fieldsPerTable = 12, rows = 100, outputItems = 100, bytes = 1048576, fanout = 10, sourceSeconds = 30, statementSeconds = 5 }
        });
        return new MappingAssessmentView
        {
            SchemaVersion = "g4.mapping.v1",
            AssessmentId = assessmentId,
            MappingId = draft.MappingId,
            Target = target,
            Binding = binding with { ValidationHash = validationHash },
            ExpectedActive = impact.Active,
            Stages = evaluated.Stages,
            Issues = evaluated.Issues,
            Status = evaluated.Passed ? "READY_FOR_PROPOSAL" : "BLOCKED",
            SemanticResultHash = evaluated.SemanticResultHash,
            EvidenceHash = evaluated.EvidenceHash,
            StartedAtUtc = started,
            FinishedAtUtc = finished,
            ExpiresAtUtc = expiry
        };
    }

    /// <summary>从完整保存报告重算受审散列，不信任自报validationHash。</summary>
    public static string AssessmentHash(MappingAssessmentView report) => Digest(new
    {
        schemaVersion = report.SchemaVersion,
        target = report.Target,
        inputIdentity = InputIdentity(report.Binding),
        stages = report.Stages,
        report.Issues,
        report.SemanticResultHash,
        report.EvidenceHash,
        status = report.Status,
        expectedActive = report.ExpectedActive,
        startedAtUtc = report.StartedAtUtc,
        finishedAtUtc = report.FinishedAtUtc,
        expiresAtUtc = report.ExpiresAtUtc,
        budget = new { tables = 2, fieldsPerTable = 12, rows = 100, outputItems = 100, bytes = 1048576, fanout = 10, sourceSeconds = 30, statementSeconds = 5 }
    });

    /// <summary>捕获内部动作证明，不允许调用者自填当前epoch或租约。</summary>
    internal Task<MappingAuthorizationProof> CaptureAsync(ActorContext actor, string sessionReference, ResourceScope scope, string permission, CancellationToken token) =>
        authority.CaptureAsync(new MappingAuthorizationProof
        {
            Actor = actor,
            SessionReference = sessionReference,
            Scope = scope,
            Permission = permission,
            ConnectionId = null,
            ObjectRefs = [],
            FieldRefs = [],
            AuthorizationEpoch = 0,
            ExpiresAtUtc = clock.GetUtcNow()
        }, token);

    /// <summary>当前读取授权要求单条grant完整覆盖实际读取的全部表与列。</summary>
    internal Task<MappingAuthorizationProof> CaptureSourceAsync(ActorContext actor, string sessionReference, ResourceScope scope, string connectionId,
        MappingDefinition mapping, CatalogSnapshotView snapshot, CancellationToken token)
    {
        // 实际SELECT读取所选表全部有界字段，因此grant不能只覆盖UI使用的部分字段。
        var objects = mapping.Entities.Select(entity => entity.DatasetRef).Distinct().Select(dataset => snapshot.Objects.SingleOrDefault(item =>
            item.Schema == dataset.Schema && item.Name == dataset.Name && item.Kind == "TABLE") ?? throw new SemanticOperationException(409, "mapping_catalog_stale")).ToArray();
        return authority.CaptureAsync(new MappingAuthorizationProof
        {
            Actor = actor,
            SessionReference = sessionReference,
            Scope = scope,
            Permission = "mapping.source.validate",
            ConnectionId = connectionId,
            ObjectRefs = objects.Select(item => ObjectPermission(item.Schema, item.Name)).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray(),
            FieldRefs = objects.SelectMany(item => item.Fields.Select(field => ObjectPermission(item.Schema, item.Name) + "/" + field.Ordinal.ToString(CultureInfo.InvariantCulture) + "/" + Uri.EscapeDataString(field.Name))).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray(),
            AuthorizationEpoch = 0,
            ExpiresAtUtc = clock.GetUtcNow()
        }, token);
    }

    /// <summary>源对象权限身份使用转义分段，避免名字中的斜线造成碰撞。</summary>
    internal static string ObjectPermission(string schema, string name) => Uri.EscapeDataString(schema) + "/" + Uri.EscapeDataString(name);

    /// <summary>完整当前连接和目录读取，历史目录仅用于原字段兼容性证明。</summary>
    internal async Task<MappingValidationInput> InputsAsync(MappingDraftView draft, CancellationToken token)
    {
        // 独立上下文只读本模块表，不接触治理/本体写表。
        await using var db = await factory.CreateDbContextAsync(token);
        // 连接必须当前启用且覆盖完整映射范围。
        var connection = await db.Connections.AsNoTracking().SingleOrDefaultAsync(row => row.Id == draft.SourceConnectionId && row.OrganizationId == draft.Scope.OrganizationId, token);
        if (connection is null || connection.State != "ACTIVE" || !draft.Scope.SiteIds.All(site => connection.SiteIds.Contains(site, StringComparer.Ordinal)))
        {
            throw new SemanticOperationException(409, "mapping_connection_unusable");
        }
        // 仅POSTGRESQL进入本任务，其他连接器不自动视为等价。
        var config = ConnectionApplicationService.Decode<ConnectionConfig>(connection.ConfigJson) as PgConnectionConfig
            ?? throw new SemanticOperationException(422, "mapping_source_unsupported");
        // 凭据必须已绑定当前连接及准确版本，完整AAD范围不可裁剪。
        var secret = await db.ConnectionSecrets.AsNoTracking().SingleOrDefaultAsync(row => row.Id == connection.SecretId, token);
        if (secret is null || secret.ConnectionId != connection.Id || secret.UsedAtUtc is null || secret.Version != connection.SecretVersion
            || secret.OrganizationId != connection.OrganizationId || secret.Purpose != "POSTGRESQL_READONLY" || string.IsNullOrEmpty(secret.Owner)
            || !secret.SiteIds.Order(StringComparer.Ordinal).SequenceEqual(connection.SiteIds.Order(StringComparer.Ordinal)))
        {
            throw new SemanticOperationException(409, "mapping_secret_stale");
        }
        // 历史Definition仍引用原快照；不为兼容轮换改写mappingHash。
        var originalRow = await db.CatalogSnapshots.AsNoTracking().SingleOrDefaultAsync(row => row.Id == draft.SourceCatalogSnapshotId
            && row.ConnectionId == connection.Id && row.OrganizationId == draft.Scope.OrganizationId, token)
            ?? throw new SemanticOperationException(409, "mapping_catalog_stale");
        // 当前兼容评估使用新配置/秘密版本的真实CatalogJob快照。
        var currentRow = await db.CatalogSnapshots.AsNoTracking().Where(row => row.ConnectionId == connection.Id && row.OrganizationId == draft.Scope.OrganizationId
            && row.ConfigHash == connection.ConfigHash && row.SecretVersion == connection.SecretVersion).OrderByDescending(row => row.CapturedAtUtc).ThenByDescending(row => row.Id).FirstOrDefaultAsync(token)
            ?? throw new SemanticOperationException(409, "mapping_catalog_stale");
        // 旧快照与新快照均按原Connection合同解析，不能替换算法。
        var original = ConnectionApplicationService.Decode<CatalogSnapshotView>(originalRow.ViewJson);
        // 当前快照必须是原完整READY，不可拿PARTIAL填当前Binding。
        var current = ConnectionApplicationService.Decode<CatalogSnapshotView>(currentRow.ViewJson);
        if (current.Status != "READY" || current.ConfigRevision != connection.Revision || current.SecretVersion != connection.SecretVersion
            || !draft.Scope.SiteIds.All(site => original.Scope.SiteIds.Contains(site, StringComparer.Ordinal) && current.Scope.SiteIds.Contains(site, StringComparer.Ordinal)))
        {
            throw new SemanticOperationException(409, "mapping_catalog_stale");
        }
        return new MappingValidationInput { Connection = connection, Secret = secret, Profile = config.Profile, Original = original, Current = current };
    }

    /// <summary>固定正式词汇与目录的确定性候选；只读元数据，不读取样本或调用模型。</summary>
    internal async Task<MappingSuggestionView> SuggestAsync(ActorContext actor, MappingDraftView draft, CancellationToken token)
    {
        // 当前目录与旧定义引用分别保留，不能把新目录ID写进旧草稿。
        var input = await InputsAsync(draft, token);
        try
        {
            // ACL核验必须使用同一input.Current；不能二次取C2成功后仍返回C1字段。
            await sourceValidator.VerifyAccessAsync(input.Profile, cipher.Decrypt(input.Secret), input.Current, draft.Mapping, draft.Scope, token, input.Original);
        }
        catch (SemanticOperationException error) when (error.Status is 403 or 409 or 422)
        {
            throw new SemanticOperationException(403, "mapping_source_access_unverified");
        }
        // G3服务自行回验正式制品；额外绑定此草稿准确原件散列。
        var ontology = await vocabulary.ReadReleaseVocabularyAsync(actor, draft.OntologyReleaseId, token);
        if (ontology.ReleaseId != draft.OntologyReleaseId || ontology.ManifestHash != draft.OntologyManifestHash)
        {
            throw new SemanticOperationException(409, "mapping_ontology_stale");
        }
        return Suggest(draft.Mapping, input.Original, input.Current, ontology, draft.Revision);
    }

    /// <summary>原命令回执不能绕过当前候选字段可见性；拒绝整个正文而不裁剪原回执。</summary>
    public static void DemandVisibleCandidates(MappingSuggestionView receipt, MappingSuggestionView current)
    {
        if (receipt.Candidates.Any(candidate => !current.Candidates.Any(visible => Digest(visible) == Digest(candidate))))
        {
            throw new SemanticOperationException(403, "mapping_source_access_unverified");
        }
    }

    /// <summary>名称精确匹配或SKOS标签仅生成候选；单位、类型、歧义和词义匹配须逐项人工处理。</summary>
    public static MappingSuggestionView Suggest(MappingDefinition mapping, CatalogSnapshotView catalog, CatalogSnapshotView currentCatalog, VocabularySnapshot ontology, long revision)
    {
        G4MappingRules.Definition(mapping);
        // 注释和任意来源文字不参与执行，词义仅限固定正式词汇的prefLabel/altLabel。
        var triples = ontology.Triples.Where(item => item.SourceId is "ontology" or "vocabulary").Select(item => item.Triple).ToArray();
        // 输出固定排序且最多两表各十二列；每字段最多保留四个候选，过多表示歧义。
        var candidates = new List<MappingSuggestionCandidate>();
        foreach (var entity in mapping.Entities.OrderBy(item => item.Id, StringComparer.Ordinal))
        {
            if (mapping.Entities.Count(item => Digest(item.DatasetRef) == Digest(entity.DatasetRef)) != 1)
            {
                continue;
            }
            // 仅已绑定表中的固定字段，不能扩展到未授权表。
            var table = catalog.Objects.Single(item => item.Schema == entity.DatasetRef.Schema && item.Name == entity.DatasetRef.Name && item.Kind == entity.DatasetRef.Kind);
            // 当前字段已由调用者完整授权；历史未使用列撤权后不得从原快照重新披露。
            var current = currentCatalog.Objects.SingleOrDefault(item => item.Schema == table.Schema && item.Name == table.Name && item.Kind == table.Kind);
            foreach (var field in table.Fields.Where(field => current is not null && current.Fields.Any(visible => visible.Name == field.Name
                && visible.Ordinal == field.Ordinal && visible.NativeType == field.NativeType)).OrderBy(item => item.Ordinal))
            {
                // 已有显式属性绑定不重建议或覆盖人工决定。
                var reference = new MappingFieldRef { DatasetRef = entity.DatasetRef, Name = field.Name, Ordinal = field.Ordinal };
                if (mapping.Properties.Any(item => item.EntityBindingId == entity.Id && Digest(item.FieldRef) == Digest(reference)))
                {
                    continue;
                }
                // 只选正式声明且域精确等于实体类的DatatypeProperty。
                var targets = triples.Where(item => item.Predicate == RdfType && item.Object.Kind == RdfTermKind.Iri && item.Object.Value == Owl + "DatatypeProperty"
                    && item.Subject.Kind == RdfTermKind.Iri).Select(item => item.Subject.Value).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal)
                    .Where(iri => Objects(triples, iri, Rdfs + "domain") is [{ Kind: RdfTermKind.Iri } domain] && domain.Value == entity.EntityClassIri)
                    .Where(iri => iri[(Math.Max(iri.LastIndexOf('#'), Math.Max(iri.LastIndexOf('/'), iri.LastIndexOf(':'))) + 1)..].Equals(field.Name, StringComparison.OrdinalIgnoreCase)
                        || new[] { "prefLabel", "altLabel" }.Any(label => Objects(triples, iri, "http://www.w3.org/2004/02/skos/core#" + label)
                            .Any(term => term.Kind == RdfTermKind.Literal && term.Value.Equals(field.Name, StringComparison.OrdinalIgnoreCase))))
                    .Take(5).ToArray();
                foreach (var target in targets.Take(4))
                {
                    // 只有唯一同名、直接非物理标量、无单位转换者可进入低风险显式批采纳。
                    var exact = target[(Math.Max(target.LastIndexOf('#'), Math.Max(target.LastIndexOf('/'), target.LastIndexOf(':'))) + 1)..].Equals(field.Name, StringComparison.OrdinalIgnoreCase);
                    // 时间/数字/单位仍须逐项明确，不以名称相等猜测转换。
                    var safe = targets.Length == 1 && exact && Objects(triples, target, Semantics + "nominalUnit").Length == 0
                        && Objects(triples, target, Rdfs + "range") is [{ Kind: RdfTermKind.Iri } range]
                        && range.Value is Xsd + "string" or Xsd + "boolean"
                        && MatchesDatatype(new MappingSourceCell { NativeType = field.NativeType, Value = null }, null, null, range.Value);
                    candidates.Add(new MappingSuggestionCandidate { FieldRef = reference, TargetIri = target, Evidence = safe ? "METADATA" : "TERM", Status = "CANDIDATE_ONLY" });
                }
            }
        }
        return new MappingSuggestionView
        {
            Revision = revision,
            Candidates = candidates.ToArray(),
            IssueCodes = ["mapping_candidate_rules_v1", "mapping_no_sample_evidence", candidates.Count == 0 ? "mapping_no_candidate" : "mapping_manual_adoption_required"]
        };
    }

    /// <summary>从本产品全部Mapping依赖索引和当前Active构造稳定影响基线。</summary>
    internal async Task<MappingImpactObservation> ImpactAsync(MappingDraftView draft, CancellationToken token)
    {
        // 此查询覆盖本产品当前映射依赖集合，不声明外部生产消费者已经盘点。
        await using var db = await factory.CreateDbContextAsync(token);
        // 同组织全部已登记映射的源引用形成完整依赖版本，不仅查当前页面可见项。
        var dependencies = await db.Mappings.AsNoTracking().Where(row => row.OrganizationId == draft.Scope.OrganizationId)
            .OrderBy(row => row.Id).Select(row => new { row.Id, row.SourceConnectionId }).ToArrayAsync(token);
        // 每个已激活指针纳入依赖版本，其他Mapping变更也保守使影响报告失效。
        var activeRows = await db.MappingActives.AsNoTracking().Where(row => row.OrganizationId == draft.Scope.OrganizationId)
            .OrderBy(row => row.MappingId).Select(row => new { row.MappingId, row.ReleaseId, row.ActivationRevision }).ToArrayAsync(token);
        // 固定本目标当前指针，首次不存在明确null+0。
        var active = activeRows.SingleOrDefault(row => row.MappingId == draft.MappingId);
        // M3当前只登记治理通知消费者；没有对外Mapping执行或M4读取入口。
        var hash = Digest(new
        {
            registryVersion = "mapping-dependencies-v1",
            scope = draft.Scope,
            dependencies,
            activeRows,
            notificationConsumers = new[] { "mapping-governance-notification-v1" },
            executionConsumers = Array.Empty<string>(),
            boundary = "M3_GOVERNANCE_ONLY"
        });
        return new MappingImpactObservation { Active = new MappingExpectedActive { ReleaseId = active?.ReleaseId, ActivationRevision = active?.ActivationRevision ?? 0 }, Hash = hash };
    }

    /// <summary>验证hash的输入身份明确排除自身validationHash，避免自引用。</summary>
    private static object InputIdentity(MappingVersionBinding binding) => new
    {
        binding.SourceConnectionId,
        binding.ConnectionRevision,
        binding.ConfigHash,
        binding.SourceType,
        binding.SourceCatalogSnapshotId,
        binding.SourceCatalogFingerprint,
        binding.OntologyReleaseId,
        binding.OntologyManifestHash,
        binding.MappingHash,
        binding.ImpactHash,
        binding.AssessmentId,
        binding.AdapterVersion,
        binding.ExecutorVersion,
        binding.CanonicalVersion,
        binding.SecretVersion,
        binding.AuthorizationEpoch
    };

    /// <summary>评估固定定义、实际源观察和已核验正式词汇，不写任何本体事实。</summary>
    public static MappingEvaluation Evaluate(MappingDefinition mapping, MappingSourceObservation source, VocabularySnapshot ontology,
        ResourceScope scope, bool currentAuthority, bool currentImpact, string impactHash)
    {
        G4MappingRules.Definition(mapping);
        G4MappingRules.Scope(scope);
        G4MappingRules.Hash(impactHash);
        // 每项问题属于明确阶段，不以另一个阶段的成功替代其证据。
        var problems = StageNames.ToDictionary(stage => stage, _ => new List<MappingIssue>(), StringComparer.Ordinal);
        // 只消费正式词汇中的本体和词汇声明，不从data行编造类或单位定义。
        var triples = ontology.Triples.Where(item => item.SourceId is "ontology" or "vocabulary").Select(item => item.Triple).ToArray();
        if (ontology.ReleaseId is null || ontology.ManifestHash is null || ontology.ProfileVersion != "4")
        {
            Issue(problems, "SCHEMA", "mapping_formal_semantics_unknown");
        }
        if (!currentImpact)
        {
            Issue(problems, "IMPACT", "mapping_dependencies_unknown");
        }
        if (!source.SecurityVerified || !currentAuthority)
        {
            Issue(problems, "SECURITY", "mapping_current_authority_unverified");
        }
        if (source.FinishedAtUtc < source.StartedAtUtc || source.FinishedAtUtc - source.StartedAtUtc > TimeSpan.FromSeconds(30))
        {
            Issue(problems, "EXECUTABILITY", "mapping_source_budget_exceeded");
        }
        // 执行结果只在内存保存带时间限定的身份和属性值，报告不返回这些值。
        var entities = new List<EvaluatedEntity>();
        // 属性输出用于独立反向对账，不写回G3图或业务表。
        var values = new List<string>();
        // 独立累计真实输出字节上界，不能用散列长度冒充原值大小。
        var outputBytes = 0;
        // 固定每个实体绑定的输出数量，作为激活复核语义不变量。
        var entityCounts = new SortedDictionary<string, int>(StringComparer.Ordinal);
        // 空完整样本仍不能证明身份、单位和可执行性。
        foreach (var entity in mapping.Entities)
        {
            if (!HasType(triples, entity.EntityClassIri, Owl + "Class"))
            {
                Issue(problems, "SCHEMA", "mapping_class_missing", entity.Id);
            }
            // 固定数据集只能对应一个实际完整集合。
            var table = source.Tables.SingleOrDefault(item => item.Dataset == entity.DatasetRef);
            if (table is null || table.Rows.Length == 0)
            {
                Issue(problems, "SCHEMA", "mapping_samples_unknown", entity.Id);
                Issue(problems, "IDENTITY", "mapping_samples_unknown", entity.Id);
                Issue(problems, "TIME_UNIT", "mapping_samples_unknown", entity.Id);
                Issue(problems, "EXECUTABILITY", "mapping_samples_unknown", entity.Id);
                entityCounts[entity.Id] = 0;
                continue;
            }
            // 形状守卫已证明引用存在且唯一，后续只查固定规则。
            var identity = mapping.IdentitySpecs.Single(item => item.Id == entity.IdentitySpecId);
            // 业务时间和观察时间明确分列。
            var time = mapping.TemporalSpecs.Single(item => item.Id == entity.TemporalSpecId);
            // 成功输出数不能由原始行数直接代填。
            var before = entities.Count;
            // 完整限定集合逐行检查；任一行未知即阻断，而非跳过后继续判PASS。
            foreach (var row in table.Rows)
            {
                try
                {
                    if (Cell(row, identity.OrganizationFieldRef).Value != scope.OrganizationId
                        || !scope.SiteIds.Contains(Cell(row, identity.SiteFieldRef).Value, StringComparer.Ordinal))
                    {
                        throw new SemanticOperationException(422, "mapping_scope_value_invalid");
                    }
                    // 复合外部键顺序保持原定义，不以拼接分隔符制造歧义。
                    var external = identity.ExternalIdFieldRefs.Select(field => Cell(row, field).Value).ToArray();
                    if (external.Any(value => string.IsNullOrWhiteSpace(value)))
                    {
                        throw new SemanticOperationException(422, "mapping_identity_unknown");
                    }
                    // 业务身份明确绑定org/site/namespace，不跨厂同号合并。
                    var key = Digest(new { organization = scope.OrganizationId, site = Cell(row, identity.SiteFieldRef).Value, identity.SourceNamespace, external });
                    // 所有半开端点必须已知，null不解释成正负无穷。
                    var from = Instant(row, identity.ValidFromFieldRef, time);
                    // 终点不能自动取当前时间或最大时间。
                    var to = Instant(row, identity.ValidToFieldRef, time);
                    if (from >= to || from != Instant(row, time.ValidFromFieldRef, time) || to != Instant(row, time.ValidToFieldRef, time))
                    {
                        throw new SemanticOperationException(422, "mapping_interval_invalid");
                    }
                    // 业务事件时间与观察时间各自验证，不互相补齐。
                    _ = Instant(row, time.EventTimeFieldRef, time);
                    _ = Instant(row, time.ObservedAtFieldRef, time);
                    if (entities.Any(item => item.BindingId == entity.Id && item.Key == key && item.From < to && from < item.To))
                    {
                        throw new SemanticOperationException(422, "mapping_identity_overlap");
                    }
                    entities.Add(new EvaluatedEntity
                    {
                        BindingId = entity.Id,
                        Key = key,
                        From = from,
                        To = to,
                        Row = row,
                        Organization = scope.OrganizationId,
                        Site = Cell(row, identity.SiteFieldRef).Value!
                    });
                    outputBytes += 512;
                }
                catch (SemanticOperationException error)
                {
                    if (error.Code.Contains("time", StringComparison.Ordinal) || error.Code.Contains("interval", StringComparison.Ordinal))
                    {
                        Issue(problems, "IDENTITY", "mapping_identity_time_unknown", entity.Id);
                    }
                    Issue(problems, error.Code.Contains("time", StringComparison.Ordinal) || error.Code.Contains("interval", StringComparison.Ordinal) ? "TIME_UNIT" : "IDENTITY", error.Code, entity.Id);
                }
            }
            entityCounts[entity.Id] = entities.Count - before;
            if (entityCounts[entity.Id] != table.Rows.Length)
            {
                Issue(problems, "RECONCILIATION", "mapping_entity_count_mismatch", entity.Id);
            }
        }
        // 固定每个属性绑定的有效输出数，null策略独立验证。
        var propertyCounts = new SortedDictionary<string, int>(StringComparer.Ordinal);
        foreach (var property in mapping.Properties)
        {
            if (!HasType(triples, property.PropertyIri, Owl + "DatatypeProperty"))
            {
                Issue(problems, "SCHEMA", "mapping_property_missing", property.Id, property.FieldRef);
            }
            // 域必须明确匹配绑定类；首切片不猜测复杂OWL继承与交集。
            var entityClass = mapping.Entities.Single(item => item.Id == property.EntityBindingId).EntityClassIri;
            if (Objects(triples, property.PropertyIri, Rdfs + "domain") is not [{ Kind: RdfTermKind.Iri } domain] || domain.Value != entityClass)
            {
                Issue(problems, "SCHEMA", "mapping_property_domain_unknown", property.Id, property.FieldRef);
            }
            // 目标类型需要唯一明确登记，不能在多个range中挑选一个通过。
            var ranges = Objects(triples, property.PropertyIri, Rdfs + "range");
            if (ranges is not [{ Kind: RdfTermKind.Iri }])
            {
                Issue(problems, "SCHEMA", "mapping_target_datatype_unknown", property.Id, property.FieldRef);
            }
            // 未声明单位的属性仅接受明确非物理量的已发布range，不凭缺省猜测。
            var nominal = Objects(triples, property.PropertyIri, Semantics + "nominalUnit");
            if (property.UnitSpecId is null && (nominal.Length != 0 || !Objects(triples, property.PropertyIri, Rdfs + "range")
                .Any(term => term.Kind == RdfTermKind.Iri && term.Value is Xsd + "string" or Xsd + "boolean" or Xsd + "date" or Xsd + "dateTime")))
            {
                Issue(problems, "TIME_UNIT", "mapping_unit_unknown", property.Id, property.FieldRef);
            }
            // 转换只取已登记版本，定义中的null保持无转换。
            var conversion = property.ConversionId is null ? null : mapping.Conversions.Single(item => item.Id == property.ConversionId);
            // 单位实例必须证明每条源行的实际单位代码。
            var unit = property.UnitSpecId is null ? null : mapping.UnitSpecs.Single(item => item.Id == property.UnitSpecId);
            // 独立计数起点防止其他属性的输出混入此属性证据。
            var count = 0;
            foreach (var entity in entities.Where(item => item.BindingId == property.EntityBindingId))
            {
                try
                {
                    if (unit is not null)
                    {
                        CheckUnit(triples, property.PropertyIri, unit, conversion, entity.Row);
                    }
                    // 原始值只留此局部调用内存，未知字段不能当null。
                    var original = Cell(entity.Row, property.FieldRef);
                    // 实际执行注册转换，不能凭schema可编译声称成功。
                    var converted = ConvertValue(original, conversion);
                    if (converted is null && property.NullPolicy == "REJECT_NULL")
                    {
                        throw new SemanticOperationException(422, "mapping_null_rejected");
                    }
                    if (ranges is not [{ Kind: RdfTermKind.Iri } range] || !MatchesDatatype(original, converted, conversion, range.Value))
                    {
                        Issue(problems, "SCHEMA", "mapping_target_datatype_mismatch", property.Id, property.FieldRef);
                        throw new SemanticOperationException(422, "mapping_target_datatype_mismatch");
                    }
                    // 独立反向参考计算校验实际值，不只比较输出数量。
                    if (!Reconciles(original, converted, conversion))
                    {
                        throw new SemanticOperationException(422, "mapping_value_reconciliation_failed");
                    }
                    outputBytes += System.Text.Encoding.UTF8.GetByteCount(converted ?? "null") + 512;
                    values.Add(Digest(new { entity.Key, property.Id, value = converted }));
                    count++;
                }
                catch (SemanticOperationException error)
                {
                    Issue(problems, error.Code.Contains("reconciliation", StringComparison.Ordinal) ? "RECONCILIATION" : "TIME_UNIT", error.Code, property.Id, property.FieldRef);
                    Issue(problems, "EXECUTABILITY", "mapping_transform_failed", property.Id, property.FieldRef);
                }
            }
            propertyCounts[property.Id] = count;
            if (count != entityCounts[property.EntityBindingId])
            {
                Issue(problems, "RECONCILIATION", "mapping_property_count_mismatch", property.Id, property.FieldRef);
            }
        }
        // 关系实测数量用于受审和激活新检查比较，不能只写关系存在。
        var relationCounts = new SortedDictionary<string, int>(StringComparer.Ordinal);
        foreach (var relation in mapping.Relations)
        {
            if (!HasType(triples, relation.PredicateIri, Owl + "ObjectProperty"))
            {
                Issue(problems, "SCHEMA", "mapping_relation_missing", relation.Id);
            }
            // 正式关系的域和值域必须各有唯一明确IRI；不猜测OWL复杂继承或多值交集。
            var fromClass = mapping.Entities.Single(item => item.Id == relation.FromBindingId).EntityClassIri;
            // 目标类独立核验，不能用源端点类代替。
            var toClass = mapping.Entities.Single(item => item.Id == relation.ToBindingId).EntityClassIri;
            if (Objects(triples, relation.PredicateIri, Rdfs + "domain") is not [{ Kind: RdfTermKind.Iri } domain] || domain.Value != fromClass)
            {
                Issue(problems, "SCHEMA", "mapping_relation_domain_unknown", relation.Id);
            }
            if (Objects(triples, relation.PredicateIri, Rdfs + "range") is not [{ Kind: RdfTermKind.Iri } range] || range.Value != toClass)
            {
                Issue(problems, "SCHEMA", "mapping_relation_range_unknown", relation.Id);
            }
            // 双侧都来自已验证同scope的实际实体，而非当前数据库任意表。
            var from = entities.Where(item => item.BindingId == relation.FromBindingId).ToArray();
            // 原始目标集合用于完整关系端点与基数判断。
            var to = entities.Where(item => item.BindingId == relation.ToBindingId).ToArray();
            if (from.Any(item => relation.JoinFieldPairs.Any(pair => !item.Row.TryGetValue(pair.From.Name, out var cell) || string.IsNullOrWhiteSpace(cell.Value)))
                || to.Any(item => relation.JoinFieldPairs.Any(pair => !item.Row.TryGetValue(pair.To.Name, out var cell) || string.IsNullOrWhiteSpace(cell.Value))))
            {
                Issue(problems, "IDENTITY", "mapping_relation_endpoint_unknown", relation.Id);
                Issue(problems, "RECONCILIATION", "mapping_relation_endpoint_unknown", relation.Id);
                relationCounts[relation.Id] = 0;
                continue;
            }
            // 实际计划逐起点连接，计算半开重叠而非闭区间。
            var pairs = new List<(EvaluatedEntity From, EvaluatedEntity To)>();
            foreach (var start in from)
            {
                // fanout最多十个，超过立即阻断整个评估，不截断返回。
                var matches = to.Where(end => JoinMatches(start, end, relation)).ToArray();
                if (matches.Length > 10)
                {
                    Issue(problems, "EXECUTABILITY", "mapping_fanout_exceeded", relation.Id);
                }
                pairs.AddRange(matches.Select(end => (start, end)));
            }
            // ONE_TO_MANY要求同一目标在重叠有效期内不能有多个起点。
            if (relation.Cardinality == "ONE_TO_MANY" && pairs.GroupBy(pair => pair.To).Any(group => group.Any(left => group.Any(right =>
                !ReferenceEquals(left.From, right.From) && left.From.From < right.From.To && right.From.From < left.From.To))))
            {
                Issue(problems, "IDENTITY", "mapping_cardinality_conflict", relation.Id);
            }
            // 独立参考从目标侧反查；不使用实际pairs作为参考输入。
            var referenceCount = to.Sum(end => from.Count(start => start.Organization == end.Organization && start.Site == end.Site
                && start.From < end.To && end.From < start.To && relation.JoinFieldPairs.All(pair =>
                    Cell(start.Row, pair.From).Value is { } value && value == Cell(end.Row, pair.To).Value)));
            if (referenceCount != pairs.Count)
            {
                Issue(problems, "RECONCILIATION", "mapping_relation_count_mismatch", relation.Id);
            }
            relationCounts[relation.Id] = pairs.Count;
            outputBytes += pairs.Count * 512;
        }
        if (entities.Count + values.Count + relationCounts.Values.Sum() > 100 || outputBytes > G4MappingRules.MaximumBytes || MappingCanonical.Serialize(new { entityCounts, propertyCounts, relationCounts, values }).Length > G4MappingRules.MaximumBytes)
        {
            Issue(problems, "EXECUTABILITY", "mapping_output_budget_exceeded");
        }
        // 真实源快照、观察时刻和输出hash只进入本次证据，不强迫人工审核30秒内完成。
        var evidence = Digest(new
        {
            source.CatalogFingerprint,
            source.TransactionSnapshot,
            source.StartedAtUtc,
            source.FinishedAtUtc,
            ontology.ReleaseId,
            ontology.ManifestHash,
            entityCounts,
            propertyCounts,
            relationCounts,
            values,
            impactHash
        });
        // 每阶段的独立问题集与实际输入证据固定排序，缺证据归INDETERMINATE。
        var stages = StageNames.Select(stage => new MappingStageResult
        {
            Stage = stage,
            Status = problems[stage].Count == 0 ? "PASS" : problems[stage].Any(issue => issue.Code.EndsWith("_unknown", StringComparison.Ordinal) || issue.Code.EndsWith("_unverified", StringComparison.Ordinal)) ? "INDETERMINATE" : "FAIL",
            IssueCodes = problems[stage].Select(issue => issue.Code).Distinct(StringComparer.Ordinal).Order(StringComparer.Ordinal).ToArray(),
            EvidenceHash = Digest(new { stage, evidence, problems = problems[stage] })
        }).ToArray();
        // 语义不变量允许具体值和观察时间变化，但数量、单位、scope、问题状态和影响基线不能变化。
        var semantic = Digest(new
        {
            executorVersion = "mapping-validator-v1",
            entityCounts,
            propertyCounts,
            relationCounts,
            scope,
            mapping.UnitSpecs,
            mapping.TemporalSpecs,
            stageResults = stages.Select(stage => new { stage.Stage, stage.Status, stage.IssueCodes }).ToArray(),
            impactHash
        });
        return new MappingEvaluation { Stages = stages, Issues = problems.Values.SelectMany(items => items).Distinct().ToArray(), SemanticResultHash = semantic, EvidenceHash = evidence };
    }

    /// <summary>正式RDF类和属性声明的标准类型谓词。</summary>
    private const string RdfType = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type";

    /// <summary>冻结OWL命名空间。</summary>
    private const string Owl = "http://www.w3.org/2002/07/owl#";

    /// <summary>冻结RDFS命名空间。</summary>
    private const string Rdfs = "http://www.w3.org/2000/01/rdf-schema#";

    /// <summary>冻结XSD标量命名空间。</summary>
    private const string Xsd = "http://www.w3.org/2001/XMLSchema#";

    /// <summary>沿G3的显式单位与身份词表。</summary>
    private const string Semantics = "urn:ontology-platform:semantics:";

    /// <summary>固定七项顺序，状态不能由客户端填入。</summary>
    private static readonly string[] StageNames = ["SCHEMA", "IDENTITY", "TIME_UNIT", "SECURITY", "EXECUTABILITY", "RECONCILIATION", "IMPACT"];

    /// <summary>安全问题只保存代码、绑定ID与明确字段引用。</summary>
    private static void Issue(Dictionary<string, List<MappingIssue>> problems, string stage, string code, string? binding = null, MappingFieldRef? field = null)
    {
        problems[stage].Add(new MappingIssue { Code = code, BindingId = binding, FieldRef = field });
    }

    /// <summary>规范内容的独立散列，不存原始业务值。</summary>
    internal static string Digest<T>(T value) => Convert.ToHexStringLower(System.Security.Cryptography.SHA256.HashData(MappingCanonical.Serialize(value)));

    /// <summary>只有明确命名IRI声明才证明目标存在。</summary>
    private static bool HasType(RdfTriple[] triples, string subject, string type) => Objects(triples, subject, RdfType).Any(term => term.Kind == RdfTermKind.Iri && term.Value == type);

    /// <summary>读取显式RDF值集合，多值不取First伪造确定性。</summary>
    private static RdfTerm[] Objects(RdfTriple[] triples, string subject, string predicate) => triples.Where(triple => triple.Subject.Kind == RdfTermKind.Iri && triple.Subject.Value == subject && triple.Predicate == predicate).Select(triple => triple.Object).Distinct().ToArray();

    /// <summary>缺字段与数据库null分开，缺字段代表固定目录漂移。</summary>
    private static MappingSourceCell Cell(Dictionary<string, MappingSourceCell> row, MappingFieldRef field) => row.TryGetValue(field.Name, out var value)
        ? value : throw new SemanticOperationException(409, "mapping_field_stale");

    /// <summary>读取明确时区和精度的时间，不把未知当无穷。</summary>
    private static DateTimeOffset Instant(Dictionary<string, MappingSourceCell> row, MappingFieldRef? field, MappingTemporalSpec spec)
    {
        if (field is null || Cell(row, field).Value is not { } value)
        {
            throw new SemanticOperationException(422, "mapping_time_unknown");
        }
        // 有时区源值必须已经由PG驱动证明UTC身份和微秒精度。
        var cell = Cell(row, field);
        // 明确解析结果承载最终UTC瞬间，不能采用系统本地时区。
        DateTimeOffset instant;
        if (cell.NativeType.EndsWith(" with time zone", StringComparison.Ordinal)
            && DateTimeOffset.TryParseExact(value, "yyyy-MM-dd'T'HH:mm:ss.fffffff'Z'", CultureInfo.InvariantCulture, DateTimeStyles.AssumeUniversal, out instant))
        {
            instant = instant.ToUniversalTime();
        }
        else
        {
            // 无时区timestamp只接受已登记区域；日期在明确UTC策略下可表示每日起点。
            var format = cell.NativeType == "date" ? "yyyy-MM-dd" : "yyyy-MM-dd'T'HH:mm:ss.fffffff";
            if ((!cell.NativeType.EndsWith(" without time zone", StringComparison.Ordinal) && cell.NativeType != "date")
                || (cell.NativeType != "date" && spec.TimezonePolicy.Kind != "REGISTERED_ZONE")
                || !DateTime.TryParseExact(value, format, CultureInfo.InvariantCulture, DateTimeStyles.None, out var local))
            {
                throw new SemanticOperationException(422, "mapping_time_unknown");
            }
            // 固定安全登记区域不会由用户地址或机器设置扩展。
            var zone = spec.TimezonePolicy.Kind == "UTC" ? TimeZoneInfo.Utc : TimeZoneInfo.FindSystemTimeZoneById(spec.TimezonePolicy.ZoneId!);
            if (zone.IsAmbiguousTime(local) || zone.IsInvalidTime(local))
            {
                throw new SemanticOperationException(422, "mapping_time_ambiguous");
            }
            instant = new DateTimeOffset(TimeZoneInfo.ConvertTimeToUtc(local, zone));
        }
        // 声明精度必须无损覆盖实际源小数，禁止截断。
        var quantum = spec.Precision switch { "DAY" => TimeSpan.TicksPerDay, "SECOND" => TimeSpan.TicksPerSecond, "MILLISECOND" => TimeSpan.TicksPerMillisecond, "MICROSECOND" => 10L, _ => 0L };
        if (quantum == 0 || instant.UtcTicks % quantum != 0)
        {
            throw new SemanticOperationException(422, "mapping_time_precision_loss");
        }
        return instant;
    }

    /// <summary>登记的目标标量类型与源或纯转换输出类型一致，禁止文本强制转换。</summary>
    private static bool MatchesDatatype(MappingSourceCell source, string? value, MappingConversion? conversion, string target)
    {
        // 输出类型由源目录与注册转换确定，不能从恰好能解析的样本猜测。
        var native = conversion?.RegisteredId switch
        {
            "celsius-to-kelvin" or "decimal-scale-exact" => "decimal",
            "json-top-level-scalar" => conversion.Parameters.GetProperty("valueType").GetString() switch
            {
                "STRING" => "string",
                "BOOLEAN" => "boolean",
                "DECIMAL" => "decimal",
                _ => "unknown"
            },
            _ => source.NativeType switch
            {
                "text" => "string",
                _ when Regex.IsMatch(source.NativeType, @"^(character varying|character)\([1-9][0-9]{0,6}\)$", RegexOptions.CultureInvariant) => "string",
                _ when Regex.IsMatch(source.NativeType, @"^timestamp(?:\([0-6]\))? with time zone$", RegexOptions.CultureInvariant) => "dateTime",
                "boolean" => "boolean",
                "smallint" or "integer" or "bigint" => "integer",
                "date" => "date",
                "timestamp with time zone" or "timestamp without time zone" => "dateTime",
                _ when source.NativeType.StartsWith("numeric(", StringComparison.Ordinal) => "decimal",
                _ => "unknown"
            }
        };
        return target switch
        {
            Xsd + "string" => native == "string",
            Xsd + "boolean" => native == "boolean" && (value is null or "true" or "false"),
            Xsd + "decimal" => native is "decimal" or "integer",
            Xsd + "integer" => native == "integer",
            Xsd + "date" => native == "date",
            // 无时区源值未经明确时区纯转换，不能直接充当正式dateTime输出。
            Xsd + "dateTime" => native == "dateTime" && Regex.IsMatch(source.NativeType, @"^timestamp(?:\([0-6]\))? with time zone$", RegexOptions.CultureInvariant),
            _ => false
        };
    }

    /// <summary>注册单位代码必须映射到固定G3定义且逐行源证据一致。</summary>
    private static void CheckUnit(RdfTriple[] triples, string property, MappingUnitSpec unit, MappingConversion? conversion, Dictionary<string, MappingSourceCell> row)
    {
        // 首切片注册只覆盖已冻结Synthetic温度单位；不会把其它单位或连接器视为等价。
        var registered = unit.SourceUnitCode switch { "Cel" => "urn:synthetic:m3:C-v1", "K" => "urn:synthetic:m3:K-v1", _ => string.Empty };
        if (unit.UnitRegistryVersion != "1" || unit.SourceUnitIri != registered || Cell(row, unit.SourceUnitFieldRef).Value != unit.SourceUnitCode
            || !HasType(triples, unit.SourceUnitIri, Semantics + "UnitDefinition") || !HasType(triples, unit.TargetUnitIri, Semantics + "UnitDefinition")
            || Objects(triples, property, Semantics + "nominalUnit") is not [{ Kind: RdfTermKind.Iri } target] || target.Value != unit.TargetUnitIri)
        {
            throw new SemanticOperationException(422, "mapping_unit_evidence_invalid");
        }
        // 单位和量种/量纲必须按IRI相等，不按显示符号或维度指数猜测。
        foreach (var predicate in new[] { "quantityKind", "dimension" })
        {
            // 一源一目标各恰一个明确IRI，不能选取多值中的第一项。
            var sourceValues = Objects(triples, unit.SourceUnitIri, Semantics + predicate);
            // 目标定义须与属性和源定义身份完全一致。
            var targetValues = Objects(triples, unit.TargetUnitIri, Semantics + predicate);
            if (sourceValues is not [{ Kind: RdfTermKind.Iri }] || targetValues is not [{ Kind: RdfTermKind.Iri }]
                || sourceValues[0] != targetValues[0] || !Objects(triples, property, Semantics + predicate).SequenceEqual(targetValues))
            {
                throw new SemanticOperationException(422, "mapping_unit_dimension_mismatch");
            }
        }
        if (conversion?.RegisteredId == "celsius-to-kelvin")
        {
            if (unit.SourceUnitCode != "Cel" || unit.TargetUnitIri != "urn:synthetic:m3:K-v1")
            {
                throw new SemanticOperationException(422, "mapping_unit_conversion_invalid");
            }
        }
        else if (unit.SourceUnitIri != unit.TargetUnitIri || conversion?.RegisteredId is not (null or "identity" or "decimal-scale-exact"))
        {
            throw new SemanticOperationException(422, "mapping_unit_conversion_invalid");
        }
    }

    /// <summary>独立参考以逆变换或源JSON语义验证值，不调用实际转换函数。</summary>
    private static bool Reconciles(MappingSourceCell source, string? result, MappingConversion? conversion)
    {
        if (source.Value is null)
        {
            return result is null;
        }
        return conversion?.RegisteredId switch
        {
            null or "identity" => source.Value == result,
            "decimal-scale-exact" => result is not null && Number(result) == Number(source.Value),
            "celsius-to-kelvin" => result is not null && Number(result) - 273.15m == Number(source.Value),
            "json-top-level-scalar" => JsonReference(source.Value, result, conversion),
            _ => false
        };
    }

    /// <summary>参考JSON解析独立读取固定键，不复用计划输出。</summary>
    private static bool JsonReference(string source, string? result, MappingConversion conversion)
    {
        // 原始JSON已由源和转换两层严格验证，此处独立检查实际标量结果。
        using var document = JsonDocument.Parse(source);
        // 参考键仍来自冻结转换参数，不解释表达式。
        var value = document.RootElement.GetProperty(conversion.Parameters.GetProperty("key").GetString()!);
        return value.ValueKind switch
        {
            JsonValueKind.Null => result is null,
            JsonValueKind.String => value.GetString() == result,
            JsonValueKind.True => result == "true",
            JsonValueKind.False => result == "false",
            JsonValueKind.Number => result is not null && value.TryGetDecimal(out var number) && number == Number(result),
            _ => false
        };
    }

    /// <summary>关系键、完整scope与半开有效区间必须同时匹配。</summary>
    private static bool JoinMatches(EvaluatedEntity from, EvaluatedEntity to, MappingRelationBinding relation) => from.Organization == to.Organization && from.Site == to.Site
        && from.From < to.To && to.From < from.To && relation.JoinFieldPairs.All(pair => Cell(from.Row, pair.From).Value is { } value && value == Cell(to.Row, pair.To).Value);

    /// <summary>已验证实体仅在当前评估内存存活，不发送到页面或日志。</summary>
    private sealed record EvaluatedEntity
    {
        /// <summary>实体绑定。</summary>
        public required string BindingId { get; init; }

        /// <summary>全限定业务身份散列。</summary>
        public required string Key { get; init; }

        /// <summary>明确半开起点。</summary>
        public required DateTimeOffset From { get; init; }

        /// <summary>明确半开终点。</summary>
        public required DateTimeOffset To { get; init; }

        /// <summary>完整源行只留内存。</summary>
        public required Dictionary<string, MappingSourceCell> Row { get; init; }

        /// <summary>已验组织。</summary>
        public required string Organization { get; init; }

        /// <summary>已验厂区。</summary>
        public required string Site { get; init; }
    }

    /// <summary>执行固定版本纯转换，拒绝精度损失和未知动态表达式。</summary>
    public static string? ConvertValue(MappingSourceCell cell, MappingConversion? conversion)
    {
        if (conversion is null)
        {
            if (cell.NativeType == "jsonb")
            {
                throw new SemanticOperationException(422, "mapping_conversion_required");
            }
            return cell.Value;
        }
        if (conversion.Version != "1" || conversion.Parameters.ValueKind != JsonValueKind.Object)
        {
            throw new SemanticOperationException(422, "mapping_conversion_invalid");
        }
        // 封闭参数集合不能被额外expression字段或重复键扩大。
        var keys = conversion.Parameters.EnumerateObject().Select(item => item.Name).Order(StringComparer.Ordinal).ToArray();
        switch (conversion.RegisteredId)
        {
            case "identity":
                if (keys.Length != 0 || cell.NativeType == "jsonb")
                {
                    throw new SemanticOperationException(422, "mapping_conversion_invalid");
                }
                return cell.Value;
            case "decimal-scale-exact":
                if ((!cell.NativeType.StartsWith("numeric(", StringComparison.Ordinal) && cell.NativeType is not ("smallint" or "integer" or "bigint"))
                    || !keys.SequenceEqual(new[] { "scale" }) || !conversion.Parameters.GetProperty("scale").TryGetInt32(out var scale) || scale is < 0 or > 28)
                {
                    throw new SemanticOperationException(422, "mapping_conversion_invalid");
                }
                if (cell.Value is null)
                {
                    return null;
                }
                // 精度转换仅验证无损，不以四舍五入掩盖信息损失。
                var exact = Number(cell.Value);
                if (decimal.Round(exact, scale) != exact)
                {
                    throw new SemanticOperationException(422, "mapping_precision_loss");
                }
                return DecimalText(exact);
            case "celsius-to-kelvin":
                if (keys.Length != 0 || !cell.NativeType.StartsWith("numeric(", StringComparison.Ordinal))
                {
                    throw new SemanticOperationException(422, "mapping_conversion_invalid");
                }
                if (cell.Value is null)
                {
                    return null;
                }
                try
                {
                    // decimal偏移精确执行且反向核验，防止容量极限下发生隐式舍入。
                    var celsius = Number(cell.Value);
                    // 偏移是冻结物理单位定义，不是G5业务指标计算。
                    var kelvin = checked(celsius + 273.15m);
                    if (kelvin - 273.15m != celsius)
                    {
                        throw new SemanticOperationException(422, "mapping_precision_loss");
                    }
                    return DecimalText(kelvin);
                }
                catch (OverflowException)
                {
                    throw new SemanticOperationException(422, "mapping_precision_loss");
                }
            case "json-top-level-scalar":
                if (!keys.SequenceEqual(new[] { "key", "valueType" }) || cell.NativeType != "jsonb"
                    || conversion.Parameters.GetProperty("key").ValueKind != JsonValueKind.String
                    || conversion.Parameters.GetProperty("valueType").ValueKind != JsonValueKind.String)
                {
                    throw new SemanticOperationException(422, "mapping_conversion_invalid");
                }
                if (cell.Value is null)
                {
                    return null;
                }
                // 只读取顶层明确键，拒绝路径解释、嵌套对象与数组。
                using (var document = G4MappingRules.ReadDocument(cell.Value))
                {
                    // 固定键在定义阶段校验，不执行动态JSONPath。
                    var key = conversion.Parameters.GetProperty("key").GetString()!;
                    // 预期类型由注册参数固定，不能用运行时样本猜测。
                    var type = conversion.Parameters.GetProperty("valueType").GetString();
                    if (document.RootElement.ValueKind != JsonValueKind.Object || !document.RootElement.TryGetProperty(key, out var value))
                    {
                        throw new SemanticOperationException(422, "mapping_json_key_missing");
                    }
                    return (type, value.ValueKind) switch
                    {
                        ("STRING", JsonValueKind.String) => value.GetString(),
                        ("BOOLEAN", JsonValueKind.True) => "true",
                        ("BOOLEAN", JsonValueKind.False) => "false",
                        ("DECIMAL", JsonValueKind.Number) => DecimalText(Number(value.GetRawText())),
                        ("STRING" or "BOOLEAN" or "DECIMAL", JsonValueKind.Null) => null,
                        _ => throw new SemanticOperationException(422, "mapping_json_type_invalid")
                    };
                }
            default:
                throw new SemanticOperationException(422, "mapping_conversion_unregistered");
        }
    }

    /// <summary>读取无指数的精确十进制，拒绝decimal解析中的静默舍入。</summary>
    private static decimal Number(string text)
    {
        if (!Regex.IsMatch(text, @"^-?(0|[1-9][0-9]*)(\.[0-9]+)?$", RegexOptions.CultureInvariant)
            || !decimal.TryParse(text, NumberStyles.AllowLeadingSign | NumberStyles.AllowDecimalPoint, CultureInfo.InvariantCulture, out var value))
        {
            throw new SemanticOperationException(422, "mapping_decimal_invalid");
        }
        // JSON源可含尾随小数零，归一化后必须与decimal精确往返一致。
        var normalized = text.Contains('.', StringComparison.Ordinal) ? text.TrimEnd('0').TrimEnd('.') : text;
        if (normalized is "-0")
        {
            normalized = "0";
        }
        if (DecimalText(value) != normalized)
        {
            throw new SemanticOperationException(422, "mapping_precision_loss");
        }
        return value;
    }

    /// <summary>精确十进制输出无指数、无多余小数零和负零。</summary>
    private static string DecimalText(decimal value) => value == 0 ? "0" : value.ToString("0.############################", CultureInfo.InvariantCulture);
}

/// <summary>一次真实源和固定发布解析后的内存评估结果，不含原始业务值。</summary>
public sealed record MappingEvaluation
{
    /// <summary>按固定顺序返回七项实证。</summary>
    public required MappingStageResult[] Stages { get; init; }

    /// <summary>可定位的脱敏问题。</summary>
    public required MappingIssue[] Issues { get; init; }

    /// <summary>允许数值变化之外的固定语义不变量。</summary>
    public required string SemanticResultHash { get; init; }

    /// <summary>本次实际观察证据散列。</summary>
    public required string EvidenceHash { get; init; }

    /// <summary>必须七项全部PASS才可进入提案。</summary>
    public bool Passed => Stages.Length == 7 && Stages.All(stage => stage.Status == "PASS");
}

/// <summary>仅验证服务内部使用的当前版本读取，不能直接序列化成公开响应。</summary>
internal sealed record MappingValidationInput
{
    /// <summary>当前连接完整版本。</summary>
    public required ConnectionRecord Connection { get; init; }

    /// <summary>当前绑定密文，仅密码保险箱可解密。</summary>
    public required ConnectionSecretRecord Secret { get; init; }

    /// <summary>受控PG目标配置。</summary>
    public required PgConnectionProfile Profile { get; init; }

    /// <summary>原定义引用的不可变目录。</summary>
    public required CatalogSnapshotView Original { get; init; }

    /// <summary>当前配置和秘密版本的兼容目录。</summary>
    public required CatalogSnapshotView Current { get; init; }
}

/// <summary>本次数据库查询得到的完整依赖影响基线。</summary>
internal sealed record MappingImpactObservation
{
    /// <summary>目标当前Active身份与单调修订。</summary>
    public required MappingExpectedActive Active { get; init; }

    /// <summary>全部已登记依赖版本和指针集合散列。</summary>
    public required string Hash { get; init; }
}
