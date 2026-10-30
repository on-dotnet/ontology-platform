using System.Security.Cryptography;
using System.Text;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>复用草稿权威修订、CAS、幂等及审计事务的M3用例。</summary>
public sealed partial class OntologyService : IG3VocabularyService
{
    /// <summary>先完成角色和全部范围授权，再调用真实四源词汇投影。</summary>
    public async Task<VocabularySnapshot> ReadVocabularyAsync(ActorContext actor, string draftId, CancellationToken cancellationToken)
    {
        // ReadAsync在取源及外部调用前完成当前草稿范围检查。
        var draft = await ReadAsync(actor, draftId, cancellationToken);
        if (runtime is not IG3VocabularyRuntime vocabulary) throw new SemanticOperationException(503, "vocabulary_runtime_unavailable");
        return (await vocabulary.ReadVocabularyAsync(draft.Sources, draft.Revision, cancellationToken)) with { DraftId = draftId };
    }

    /// <summary>完整源散列及修订共同绑定一次原子批次，已提交重放不再次访问Jena。</summary>
    public async Task<OntologyDraft> EditVocabularyAsync(ActorContext actor, string draftId, VocabularyEditsRequest request, CancellationToken cancellationToken)
    {
        DemandRole(actor, true);
        if (request?.Command is null || request.Hashes is null || request.Changes is null || request.Changes.Length is < 1 or > 64 || request.Changes.Any(change => change?.Edit is null || !Enum.IsDefined(change.SourceId))) throw new SemanticOperationException(422, "vocabulary_edit_invalid");
        ValidateCommand(request.Command);
        // 首先仅取草稿头判定范围，任何源读取和Jena之前都已重新授权。
        var row = await FindAsync(draftId, false, cancellationToken);
        DemandScope(actor, Scope(row));
        // 同一个完整payload同时用于预检查和SaveCore事务回执，避免重放hash漂移。
        var replay = await ReplayAsync<OntologyDraft>(actor, Scope(row), "ontology.edit", request.Command, new { draftId, request }, cancellationToken);
        if (replay is not null) return replay;
        if (row.Revision != request.Command.ExpectedRevision) throw new SemanticOperationException(409, "draft_revision_conflict");
        // 数据库不可变修订保留全四源，不接受只对部分hash的编辑。
        var current = await MapAsync(row, cancellationToken);
        if (current.Hashes != request.Hashes) throw new SemanticOperationException(409, "vocabulary_edit_conflict");
        if (runtime is not IG3VocabularyRuntime vocabulary) throw new SemanticOperationException(503, "vocabulary_runtime_unavailable");
        // 批次在数据库短事务之前全量成功，任一失败没有持久副作用。
        var sources = await vocabulary.ApplyVocabularyEditsAsync(current.Sources, request.Changes, cancellationToken);
        // 投影从新权威字节重新解析，SaveCore内重新做修订CAS。
        var analysis = await runtime.AnalyzeAsync(sources, row.Revision + 1, cancellationToken);
        return await SaveCoreAsync(actor, row, request.Command, sources, analysis, "ontology.edit", request, cancellationToken);
    }

    /// <summary>固定正式版本必须经过目录授权、原始对象及同批Jena核验才返回。</summary>
    public async Task<VocabularySnapshot> ReadReleaseVocabularyAsync(ActorContext actor, string releaseId, CancellationToken cancellationToken)
    {
        DemandRole(actor, false);
        if (releases is null || artifacts is null) throw new SemanticOperationException(503, "release_catalog_unavailable");
        // 目录先授权整个scope，不能先读源或正式图探测其它厂区。
        var release = await releases.ReadAsync(actor, releaseId, cancellationToken);
        if (release.Status is not (ReleaseStatus.Active or ReleaseStatus.Superseded) || release.Manifest.ReleaseId != releaseId) throw new SemanticOperationException(409, "release_not_formal");
        // 目录绑定的不可变清单是本次所有下游读取的唯一版本。
        var manifest = release.Manifest;
        DemandScope(actor, manifest.Scope);
        // 固定顺序和源对象键阻止替换槽位；null词汇不等于空词汇。
        string[] hashes = manifest.Hashes.VocabularyHash is { } vocabularyHash ? [manifest.Hashes.OntologyHash, manifest.Hashes.ShapesHash, vocabularyHash, manifest.Hashes.DataHash] : [manifest.Hashes.OntologyHash, manifest.Hashes.ShapesHash, manifest.Hashes.DataHash];
        if (manifest.ArtifactObjects.Length != hashes.Length) throw new SemanticOperationException(503, "published_source_binding_invalid");
        // 仅严格UTF8解码，不替换损坏的源字节。
        var encoding = new UTF8Encoding(false, true);
        // 每个实际对象只能填入经过hash及位置核验的源槽位。
        var texts = new string[hashes.Length];
        for (var index = 0; index < hashes.Length; index++)
        {
            // key、media、size、hash均与固定manifest绑定。
            var item = manifest.ArtifactObjects[index];
            if (item.Hash != hashes[index] || item.ContentType != "text/turtle" || item.SizeBytes is < 0 or > 256 * 1024 || item.ObjectKey != $"releases/{releaseId}/source-{index}-{hashes[index]}.ttl") throw new SemanticOperationException(503, "published_source_binding_invalid");
            // 适配器之外再核验实际返回对象字节，防止替换或错误缓存。
            var bytes = await artifacts.ReadVerifiedAsync(item, cancellationToken);
            if (bytes.LongLength != item.SizeBytes || Convert.ToHexStringLower(SHA256.HashData(bytes)) != hashes[index]) throw new SemanticOperationException(503, "published_source_binding_invalid");
            try { texts[index] = encoding.GetString(bytes); }
            catch (DecoderFallbackException) { throw new SemanticOperationException(503, "published_source_encoding_invalid"); }
        }
        // 同一四源同时交给正式Jena核验及后续投影，不回读当前草稿。
        var sources = new SourceBundle { OntologyTurtle = texts[0], ShapesTurtle = texts[1], VocabularyTurtle = texts.Length == 4 ? texts[2] : null, DataTurtle = texts[^1] };
        await runtime.ReadVerifiedPublishedAsync(manifest, sources, cancellationToken);
        if (runtime is not IG3VocabularyRuntime vocabulary) throw new SemanticOperationException(503, "vocabulary_runtime_unavailable");
        // 历史profile没有M3治理；事实仍保留，不能向旧正式版本追溯追加新错误。
        var snapshot = await vocabulary.ReadVocabularyAsync(sources, manifest.Revision, cancellationToken);
        return snapshot with { DraftId = manifest.DraftId, ReleaseId = releaseId, ManifestHash = release.ManifestHash, ProfileVersion = manifest.Semantics?.ProfileVersion, ProfileHash = manifest.Semantics?.ProfileHash, Diagnostics = manifest.Semantics?.ProfileVersion == "4" ? snapshot.Diagnostics : manifest.Semantics?.ProfileVersion == "3" ? snapshot.Diagnostics.Where(item => !IdentityDiagnostic(item.Diagnostic.Code)).ToArray() : [] };
    }
}
