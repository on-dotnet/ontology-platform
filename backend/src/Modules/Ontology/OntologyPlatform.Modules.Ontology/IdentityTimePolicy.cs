using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>草稿权威范围与历史身份保护的纯检查，不依赖客户端显示或机器时间。</summary>
internal static class IdentityTimePolicy
{
    /// <summary>平台显式身份词汇命名空间。</summary>
    internal const string P = "urn:ontology-platform:semantics:";

    /// <summary>受控时间命名空间。</summary>
    internal const string T = "http://www.w3.org/2006/time#";

    /// <summary>身份复合键各字段，比较使用有边界的元组编码。</summary>
    internal static readonly string[] KeyFields = ["organizationId", "siteId", "sourceNamespace", "externalIdentifier"];

    /// <summary>收集显式类型及身份字段主体，不能靠移除类型绕过保护。</summary>
    internal static RdfTerm[] Claims(RdfTriple[] triples) => triples.Where(triple => triple.Predicate == JenaRdfCodec.Type && triple.Object.Kind == RdfTermKind.Iri && triple.Object.Value == P + "IdentityClaim" || KeyFields.Concat(new[] { "targetIri", "declarationSource", "validityInterval" }).Any(name => triple.Predicate == P + name)).Select(triple => triple.Subject).Distinct().ToArray();

    /// <summary>范围与编号只允许无语言的非空字符串，不按标签合并。</summary>
    internal static bool StringTerm(RdfTerm value) => value.Kind == RdfTermKind.Literal && value.Language is null && value.Datatype is null or "http://www.w3.org/2001/XMLSchema#string" && !string.IsNullOrWhiteSpace(value.Value);

    /// <summary>声明范围必须属于草稿完整scope，不能用操作者更大范围扩大资产。</summary>
    internal static bool ScopeValid(RdfTriple[] triples, ResourceScope scope) => Claims(triples).All(claim =>
        Values(triples, claim, P + "organizationId").All(value => StringTerm(value) && value.Value == scope.OrganizationId)
        && Values(triples, claim, P + "siteId").All(value => StringTerm(value) && scope.SiteIds.Contains(value.Value, StringComparer.Ordinal)));

    /// <summary>纯范围判定在真实CAS锁内重新执行，未授权声明不提交任何副作用。</summary>
    internal static void DemandScope(VocabularySnapshot snapshot, ResourceScope scope)
    {
        if (!ScopeValid(snapshot.Triples.Select(item => item.Triple).ToArray(), scope))
            throw new SemanticOperationException(403, "identity_scope_forbidden");
    }

    /// <summary>逐个保护此前完整有效的声明，无关错误或重叠诊断不能解锁旧历史。</summary>
    internal static void DemandHistory(VocabularySnapshot before, VocabularySnapshot after)
    {
        // 两个快照都由相同真实解析器产生，原始修订仍在PG不可变保存。
        var original = before.Triples.Select(item => item.Triple).Distinct().ToArray();
        // 新源全部完成解析后才进入锁内纯检查，不在事务持锁时访问Jena。
        var changed = after.Triples.Select(item => item.Triple).Distinct().ToArray();
        foreach (var claim in Claims(original).Where(claim => LocallyValid(original, claim)))
        {
            if (!LocallyValid(changed, claim)) throw new SemanticOperationException(409, "identity_history_immutable");
            foreach (var name in KeyFields.Concat(new[] { "targetIri", "declarationSource", "validityInterval" }))
                if (!Values(original, claim, P + name).ToHashSet().SetEquals(Values(changed, claim, P + name)))
                    throw new SemanticOperationException(409, "identity_history_immutable");
            // 本地有效声明恰一有效区间，因此此处取值不会掩盖歧义。
            var interval = Values(original, claim, P + "validityInterval")[0];
            if (!Values(original, interval, T + "hasBeginning").ToHashSet().SetEquals(Values(changed, interval, T + "hasBeginning")))
                throw new SemanticOperationException(409, "identity_history_immutable");
            // 原起点与未知性不可移动；共享点也受到每个可达旧claim的保护。
            var beginning = Values(original, interval, T + "hasBeginning");
            if (beginning.Length == 1 && !Values(original, beginning[0], T + "inXSDDateTimeStamp").ToHashSet().SetEquals(Values(changed, beginning[0], T + "inXSDDateTimeStamp")))
                throw new SemanticOperationException(409, "identity_history_immutable");
            // 只有补已知终点或收窄终点可变；已知终点不能变为未知或扩张。
            var oldEnd = Endpoint(original, interval, T + "hasEnd");
            // 新声明已经过局部完整性检查，非法词法不能被当作空终点放行。
            var newEnd = Endpoint(changed, interval, T + "hasEnd");
            if (oldEnd is not null && (newEnd is null || newEnd > oldEnd)
                || oldEnd is null && newEnd is null && !SameEndpoint(original, changed, interval, T + "hasEnd"))
                throw new SemanticOperationException(409, "identity_history_immutable");
        }
    }

    /// <summary>只检查一个声明的结构、词法和引用；其它claim错误不能改变此结论。</summary>
    private static bool LocallyValid(RdfTriple[] triples, RdfTerm claim)
    {
        if (claim.Kind != RdfTermKind.Iri || !Typed(triples, claim, P + "IdentityClaim")) return false;
        if (!KeyFields.All(name => Values(triples, claim, P + name) is { Length: 1 } values && StringTerm(values[0]))) return false;
        if (!new[] { "targetIri", "declarationSource", "validityInterval" }.All(name => Values(triples, claim, P + name) is { Length: 1 } values && values[0].Kind == RdfTermKind.Iri)) return false;
        // 完整本地目标必须有命名类型声明，不能从标签猜身份。
        var target = Values(triples, claim, P + "targetIri")[0];
        if (!triples.Any(triple => triple.Subject == target && triple.Predicate == JenaRdfCodec.Type && triple.Object.Kind == RdfTermKind.Iri)) return false;
        // 单一合法Interval类型不允许被Instant双类型混淆。
        var interval = Values(triples, claim, P + "validityInterval")[0];
        if (!Typed(triples, interval, T + "Interval") || Typed(triples, interval, T + "Instant")) return false;
        if (triples.Any(triple => triple.Subject == interval && triple.Predicate.StartsWith(T, StringComparison.Ordinal) && triple.Predicate is not (T + "hasBeginning" or T + "hasEnd"))) return false;
        foreach (var path in new[] { T + "hasBeginning", T + "hasEnd" })
        {
            // 缺失端点是合法未知，两个引用或未注册点不是有效历史。
            var links = Values(triples, interval, path);
            if (links.Length > 1 || links.Any(point => point.Kind != RdfTermKind.Iri || !Typed(triples, point, T + "Instant") || Typed(triples, point, T + "Interval"))) return false;
            if (links.Length == 0) continue;
            if (triples.Any(triple => triple.Subject == links[0] && triple.Predicate.StartsWith(T, StringComparison.Ordinal) && triple.Predicate != T + "inXSDDateTimeStamp")) return false;
            // 非法词法不能被未知端点默认值隐藏。
            var stamps = Values(triples, links[0], T + "inXSDDateTimeStamp");
            if (stamps.Length > 1 || stamps.Any(stamp => stamp.Kind != RdfTermKind.Literal || stamp.Language is not null || stamp.Datatype != "http://www.w3.org/2001/XMLSchema#dateTimeStamp" || !TemporalContractRules.TryInstant(stamp.Value, out _))) return false;
        }
        // 已知顺序错误尚未形成有效身份历史，错误草稿可被修复且原修订保留。
        var from = Endpoint(triples, interval, T + "hasBeginning");
        // 业务终点未知独立保留，不替换为无限大。
        var to = Endpoint(triples, interval, T + "hasEnd");
        return from is null || to is null || from < to;
    }

    /// <summary>端点引用及其时间词法都一致时才视为同一个未知端点。</summary>
    private static bool SameEndpoint(RdfTriple[] before, RdfTriple[] after, RdfTerm interval, string path)
    {
        // 不把不同空点静默替换成同一未知历史。
        var links = Values(before, interval, path);
        return links.ToHashSet().SetEquals(Values(after, interval, path)) && links.All(point => Values(before, point, T + "inXSDDateTimeStamp").ToHashSet().SetEquals(Values(after, point, T + "inXSDDateTimeStamp")));
    }

    /// <summary>在局部结构已验证后读取明确端点；没有事实就保持null。</summary>
    private static DateTimeOffset? Endpoint(RdfTriple[] triples, RdfTerm interval, string path)
    {
        // 最多一个端点的前提由LocallyValid保障，方法本身仍不挑选多值。
        var links = Values(triples, interval, path);
        if (links.Length != 1) return null;
        // 词法只来自该点的精确datatype声明。
        var stamps = Values(triples, links[0], T + "inXSDDateTimeStamp");
        return stamps.Length == 1 && TemporalContractRules.TryInstant(stamps[0].Value, out var point) ? point : null;
    }

    /// <summary>仅显式命名类型声明参与局部有效性，不进行类型推理。</summary>
    private static bool Typed(RdfTriple[] triples, RdfTerm subject, string type) => Values(triples, subject, JenaRdfCodec.Type).Any(value => value.Kind == RdfTermKind.Iri && value.Value == type);

    /// <summary>读取指定主体的全部精确值，调用方必须自行判定基数。</summary>
    internal static RdfTerm[] Values(RdfTriple[] triples, RdfTerm subject, string predicate) => triples.Where(triple => triple.Subject == subject && triple.Predicate == predicate).Select(triple => triple.Object).Distinct().ToArray();
}
