using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>身份时间用例复用四源精确变更及同事务CAS/幂等/审计。</summary>
public sealed partial class OntologyService : IG3IdentityTimeService
{
    /// <summary>先授权完整草稿，再返回同修订身份时间事实及真实来源诊断。</summary>
    public Task<VocabularySnapshot> ReadIdentityTimeAsync(ActorContext actor, string draftId, CancellationToken cancellationToken) =>
        ReadVocabularyAsync(actor, draftId, cancellationToken);

    /// <summary>固定正式读取沿用RustFS原字节和实际Jena图核验，不回读当前草稿。</summary>
    public Task<VocabularySnapshot> ReadReleaseIdentityTimeAsync(ActorContext actor, string releaseId, CancellationToken cancellationToken) =>
        ReadReleaseVocabularyAsync(actor, releaseId, cancellationToken);

    /// <summary>整批受控编辑后校验身份时间，不将部分变更提交到PG。</summary>
    public async Task<OntologyDraft> EditIdentityTimeAsync(ActorContext actor, string draftId, IdentityTimeEditsRequest request, CancellationToken cancellationToken)
    {
        DemandRole(actor, true);
        if (request?.Command is null || request.Hashes is null || request.Changes is null || request.Changes.Length is < 1 or > 64 || request.Changes.Any(change => change?.Edit is null || !Enum.IsDefined(change.SourceId))) throw new SemanticOperationException(422, "identity_time_invalid");
        ValidateCommand(request.Command);
        // 主体范围必须在任何源或Jena访问之前由服务器草稿头确认。
        var row = await FindAsync(draftId, false, cancellationToken);
        DemandScope(actor, Scope(row));
        // 相同完整请求重放无需再次访问Jena，也不会刷新历史事实。
        var replay = await ReplayAsync<OntologyDraft>(actor, Scope(row), "ontology.edit", request.Command, new { draftId, request }, cancellationToken);
        if (replay is not null) return replay;
        if (row.Revision != request.Command.ExpectedRevision) throw new SemanticOperationException(409, "draft_revision_conflict");
        // 当前修订及全四源散列共同限定精确编辑输入。
        var current = await MapAsync(row, cancellationToken);
        if (current.Hashes != request.Hashes) throw new SemanticOperationException(409, "identity_time_conflict");
        if (runtime is not IG3VocabularyRuntime vocabulary) throw new SemanticOperationException(503, "vocabulary_runtime_unavailable");
        // 复用原已冻结的按源精确编辑，不重建源码或另建身份表。
        var sources = await vocabulary.ApplyVocabularyEditsAsync(current.Sources, request.Changes, cancellationToken);
        // 在完整新源上治理，批次可以先建引用后登记目标，但不接受半成品。
        var snapshot = await vocabulary.ReadVocabularyAsync(sources, row.Revision + 1, cancellationToken);
        // 已形成有效声明的历史破坏优先返回409，与普通源码入口保持同一可解释错误。
        var originalIdentity = await IdentityFactsAsync(current.Sources, current.Revision, cancellationToken);
        IdentityTimePolicy.DemandHistory(originalIdentity, snapshot);
        IdentityTimePolicy.DemandScope(snapshot, Scope(row));
        DemandIdentityEdit(snapshot);
        // 正式投影仍由同一真实解析器生成，SaveCore会在CAS锁内重新检查范围/历史。
        var analysis = await runtime.AnalyzeAsync(sources, row.Revision + 1, cancellationToken);
        return await SaveCoreAsync(actor, row, request.Command, sources, analysis, "ontology.edit", request, cancellationToken, fixedBefore: originalIdentity, fixedAfter: snapshot);
    }

    /// <summary>按固定错误类别优先级返回可解释安全code，不从冲突身份中选择一个值。</summary>
    private static void DemandIdentityEdit(VocabularySnapshot snapshot)
    {
        // 业务错误优先级显式固定，多项输入错误不会变成依赖枚举顺序的任意选择。
        string[] priorities = ["identity_ambiguous", "time_interval_reversed", "time_timezone_required", "time_lexical_invalid", "time_reference_missing", "time_template_unsupported", "identity_claim_invalid", "event_time_invalid"];
        foreach (var code in priorities)
            if (snapshot.Diagnostics.Any(item => item.Diagnostic.Code == code && item.Diagnostic.Severity == DiagnosticSeverity.Error)) throw new SemanticOperationException(422, code);
        if (snapshot.Diagnostics.Any(item => IdentityDiagnostic(item.Diagnostic.Code) && item.Diagnostic.Severity == DiagnosticSeverity.Error)) throw new SemanticOperationException(422, "identity_time_invalid");
        if (snapshot.Diagnostics.Any(item => item.Diagnostic.Code == "identity_relation_indeterminate")) throw new SemanticOperationException(422, "identity_relation_indeterminate");
        if (snapshot.Diagnostics.Any(item => IdentityDiagnostic(item.Diagnostic.Code) && item.Diagnostic.Severity == DiagnosticSeverity.Warning)) throw new SemanticOperationException(422, "identity_time_indeterminate");
    }

    /// <summary>识别v4新增诊断，不向历史v3正式词汇追溯追加身份时间政策。</summary>
    private static bool IdentityDiagnostic(string code) => code.StartsWith("identity_", StringComparison.Ordinal) || code.StartsWith("time_", StringComparison.Ordinal) || code == "event_time_invalid";

    /// <summary>在PG短事务外固定同修订的四源投影，锁内只做纯政策与CAS复核。</summary>
    private async Task<VocabularySnapshot> IdentityFactsAsync(SourceBundle sources, long revision, CancellationToken cancellationToken)
    {
        if (runtime is not IG3VocabularyRuntime vocabulary) throw new SemanticOperationException(503, "vocabulary_runtime_unavailable");
        return await vocabulary.ReadVocabularyAsync(sources, revision, cancellationToken);
    }
}
