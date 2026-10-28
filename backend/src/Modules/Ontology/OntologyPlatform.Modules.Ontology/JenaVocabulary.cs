using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>四源词汇视图与仅目标源精确批次共享真实RIOT解析和执行预算。</summary>
public sealed partial class JenaSemanticRuntime : IG3VocabularyRuntime
{
    /// <summary>完整解析四源后返回事实及来源绑定治理诊断，不重建权威RDF。</summary>
    public Task<VocabularySnapshot> ReadVocabularyAsync(SourceBundle sources, long revision, CancellationToken cancellationToken) =>
        Execute(async (graphs, token) =>
        {
            // 包含Shapes事实的投影用于真实引用位置，仍由原ShapePolicy约束。
            var parsed = await ParseSourcesAsync(sources, graphs, token);
            return Vocabulary(sources, revision, parsed, token);
        }, cancellationToken);

    /// <summary>整批先解析和检查，再仅重写发生真实变化的目标图，失败不暴露部分结果。</summary>
    public Task<SourceBundle> ApplyVocabularyEditsAsync(SourceBundle sources, VocabularyChange[] changes, CancellationToken cancellationToken) =>
        Execute(async (graphs, token) =>
        {
            if (changes is null || changes.Length is < 1 or > 64 || changes.Any(change => change?.Edit is null || !Enum.IsDefined(change.SourceId))) throw new SemanticOperationException(422, "vocabulary_edit_invalid");
            // 所有原始源在修改任何集合前完成真实解析。
            var parsed = await ParseSourcesAsync(sources, graphs, token);
            // 两个目标图分开保留，不按合并图删除其它源的相同三元组。
            var targets = new Dictionary<int, List<RdfTriple>>();
            foreach (var change in changes)
            {
                token.ThrowIfCancellationRequested();
                // 枚举已校验，只有ontology/vocabulary两个固定槽位可编辑。
                var index = change.SourceId == VocabularyEditSource.Ontology ? 0 : 2;
                if (!targets.TryGetValue(index, out var triples))
                {
                    // 含未知或复杂事实的目标图锁结构，原文仍可由普通保存保留。
                    if (Support(parsed[index], structural: true).Length != 0) throw new SemanticOperationException(422, "structural_edit_unsupported");
                    triples = parsed[index].ToList();
                    targets.Add(index, triples);
                }
                // 每项精确匹配服务端投影，禁止按标签或显示字符串猜客体。
                var edit = change.Edit;
                try
                {
                    JenaRdfCodec.Iri(edit.SubjectIri);
                    JenaRdfCodec.Iri(edit.PredicateIri);
                    if (edit.OldObject is null && edit.NewObject is null) throw new SemanticOperationException(422, "rdf_edit_invalid");
                    foreach (var term in new[] { edit.OldObject, edit.NewObject })
                        if (term is not null) JenaRdfCodec.Term(term);
                }
                catch (SemanticOperationException) { throw new SemanticOperationException(422, "vocabulary_edit_invalid"); }
                if (!VocabularyPredicate(edit.PredicateIri, parsed[0].Concat(parsed[2]).ToArray())) throw new SemanticOperationException(422, "vocabulary_edit_invalid");
                // 精确三元组的subject仅使用已校验IRI，不允许blank身份修改。
                var subject = new RdfTerm { Kind = RdfTermKind.Iri, Value = edit.SubjectIri };
                if (edit.OldObject is not null && !triples.Remove(new RdfTriple { Subject = subject, Predicate = edit.PredicateIri, Object = edit.OldObject })) throw new SemanticOperationException(409, "vocabulary_edit_conflict");
                if (edit.NewObject is not null) triples.Add(new RdfTriple { Subject = subject, Predicate = edit.PredicateIri, Object = edit.NewObject });
            }
            // 全批次完成后再检查声明完整性，允许同批先建引用后建声明。
            var combined = (targets.TryGetValue(0, out var ontology) ? ontology : parsed[0].ToList()).Concat(targets.TryGetValue(2, out var vocabulary) ? vocabulary : parsed[2].ToList()).Distinct().ToArray();
            RequireNamedAxiomTypes(combined);
            if (Support(combined, structural: true).Length != 0) throw new SemanticOperationException(422, "structural_edit_unsupported");
            // 输出前仍做语义no-op判定，未变化源保留注释/prefix/CRLF原字节。
            var result = sources;
            foreach (var target in targets)
            {
                // 真实图集合去重后仅比较合法literal等价表示。
                var triples = target.Value.Distinct().ToArray();
                if (triples.Select(EditNoOpTriple).ToHashSet().SetEquals(parsed[target.Key].Select(EditNoOpTriple))) continue;
                result = target.Key == 0 ? result with { OntologyTurtle = JenaRdfCodec.Canonical(triples) + "\n" } : result with { VocabularyTurtle = JenaRdfCodec.Canonical(triples) + "\n" };
            }
            return result;
        }, cancellationToken);

    /// <summary>仅本轮已登记语义谓词和既有基本谓词可结构编辑。</summary>
    private static bool VocabularyPredicate(string predicate, RdfTriple[] triples) => EditablePredicate(predicate, triples) || M3MetadataPredicate(predicate) || predicate.StartsWith(Skos, StringComparison.Ordinal) && SkosPredicates.Contains(predicate[Skos.Length..]) || predicate == Prov + "wasDerivedFrom";

    /// <summary>构造同修订事实快照；每项诊断绑定实际来源，未知行列保持null。</summary>
    private static VocabularySnapshot Vocabulary(SourceBundle sources, long revision, RdfTriple[][] parsed, CancellationToken token)
    {
        // 四个槽位与SourceBundle字段固定对应。
        string[] names = ["ontology", "shapes", "vocabulary", "data"];
        // Profile随投影返回，Release服务会按精确manifest覆盖历史profile。
        var profile = SemanticProfile.Current();
        return new VocabularySnapshot { DraftId = null, ReleaseId = null, ManifestHash = null, Revision = revision, Hashes = JenaRdfCodec.Hashes(sources), ProfileVersion = profile.Version, ProfileHash = profile.Hash, Triples = parsed.SelectMany((triples, index) => triples.Select(triple => new VocabularySourceTriple { SourceId = names[index], Triple = triple })).ToArray(), Diagnostics = VocabularyDiagnostics(parsed, JenaRdfCodec.Hashes(sources), token) };
    }
}
