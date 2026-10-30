using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>受控OWL-Time及显式身份治理只处理已声明事实，不合并身份或联网推理。</summary>
public sealed partial class JenaSemanticRuntime
{
    /// <summary>W3C OWL-Time受控模板命名空间。</summary>
    private const string TimeNamespace = "http://www.w3.org/2006/time#";

    /// <summary>当前v4允许的精确谓词，不能按命名空间整体放开。</summary>
    private static bool M4Predicate(string predicate) => predicate is
        PlatformSemantics + "organizationId" or PlatformSemantics + "siteId" or
        PlatformSemantics + "sourceNamespace" or PlatformSemantics + "externalIdentifier" or
        PlatformSemantics + "targetIri" or PlatformSemantics + "declarationSource" or
        PlatformSemantics + "validityInterval" or PlatformSemantics + "observedAtUtc" or
        TimeNamespace + "hasBeginning" or TimeNamespace + "hasEnd" or
        TimeNamespace + "inXSDDateTimeStamp" or TimeNamespace + "hasTime";

    /// <summary>沿用四源真实定位的有限身份与时间诊断器。</summary>
    private sealed partial class VocabularyGovernance
    {
        /// <summary>校验完整声明、模板及同复合编号下的半开有效期关系。</summary>
        internal void CheckIdentityTime()
        {
            // 类型集合仅包含显式命名声明，不从关系端点推断类型。
            var instants = Registered(TimeNamespace + "Instant");
            // 区间类型独立于点，双类型会被明确阻断。
            var intervals = Registered(TimeNamespace + "Interval");
            // 事件业务时间与观察时间独立登记。
            var events = Registered(PlatformSemantics + "Event");
            // 声明主体包括错误缺类型字段，不能靠删除rdf:type逃过治理。
            var claims = IdentityTimePolicy.Claims(triples);
            foreach (var triple in triples)
            {
                token.ThrowIfCancellationRequested();
                if (triple.Predicate.StartsWith(TimeNamespace, StringComparison.Ordinal))
                {
                    // 四个精确谓词按主体模板限制，不支持Allen关系或其它时间表达式。
                    var allowed = triple.Subject.Kind == RdfTermKind.Iri && triple.Predicate switch
                    {
                        TimeNamespace + "inXSDDateTimeStamp" => instants.Contains(triple.Subject),
                        TimeNamespace + "hasBeginning" or TimeNamespace + "hasEnd" => intervals.Contains(triple.Subject),
                        TimeNamespace + "hasTime" => events.Contains(triple.Subject),
                        _ => false
                    };
                    if (!allowed) Add("time_template_unsupported", triple.Subject, triple.Predicate, "只允许显式命名点、区间及事件的受控OWL-Time模板。保留源码，不执行通用时间推理。");
                }
                if (triple.Predicate == PlatformSemantics + "observedAtUtc" && !events.Contains(triple.Subject)) Add("event_time_invalid", triple.Subject, triple.Predicate, "观察时间只能用于显式登记的事件，不替代身份有效期或版本时间。");
                if (triple.Predicate == JenaRdfCodec.Type && triple.Object.Value.StartsWith(TimeNamespace, StringComparison.Ordinal)
                    && (triple.Subject.Kind != RdfTermKind.Iri || triple.Object.Kind != RdfTermKind.Iri || triple.Object.Value is not (TimeNamespace + "Instant" or TimeNamespace + "Interval")))
                    Add("time_template_unsupported", triple.Subject, triple.Predicate, "未支持的OWL-Time类型或空白节点模板不能发布。");
            }
            foreach (var instant in instants)
            {
                token.ThrowIfCancellationRequested();
                if (intervals.Contains(instant)) Add("time_template_unsupported", instant, JenaRdfCodec.Type, "同一资源不能同时声明为受控时间点和区间。");
                // 零值为未知，不自动填机器时间或源版本时间。
                var values = Values(instant, TimeNamespace + "inXSDDateTimeStamp");
                if (values.Length > 1) Add("time_lexical_invalid", instant, TimeNamespace + "inXSDDateTimeStamp", "受控时间点最多一个明确时间戳，不能挑选第一个值。");
                foreach (var value in values) CheckTimestamp(instant, TimeNamespace + "inXSDDateTimeStamp", value);
            }
            foreach (var interval in intervals)
            {
                token.ThrowIfCancellationRequested();
                foreach (var path in new[] { TimeNamespace + "hasBeginning", TimeNamespace + "hasEnd" })
                {
                    // 缺失端点合法地表达未知；有引用则必须唯一且明确登记Instant。
                    var values = Values(interval, path);
                    if (values.Length > 1 || values.Any(value => value.Kind != RdfTermKind.Iri || !instants.Contains(value)))
                        Add("time_reference_missing", interval, path, "区间端点只能引用一个明确登记的命名Instant，缺失谓词表示未知。");
                }
                // 点的非法词法已有准确诊断；仅已知端点参加顺序判断。
                var from = Endpoint(interval, TimeNamespace + "hasBeginning", instants);
                // 终点未知时保持null，不当作确定永久有效。
                var to = Endpoint(interval, TimeNamespace + "hasEnd", instants);
                if (TemporalContractRules.Compare(from, to, from, to) == TemporalRelation.Invalid)
                    Add("time_interval_reversed", interval, TimeNamespace + "hasEnd", "有效区间采用[from,to)，已知起点必须严格早于终点。");
            }
            foreach (var item in events)
            {
                // 事件恰一业务时间，观察时间不替代事件的起止。
                var times = Values(item, TimeNamespace + "hasTime");
                if (times.Length != 1 || times.Any(value => value.Kind != RdfTermKind.Iri || !instants.Contains(value) && !intervals.Contains(value)))
                    Add("event_time_invalid", item, TimeNamespace + "hasTime", "事件必须引用一个明确受控Instant或Interval，不从观察或版本时间推测。");
                // 观察时间允许未知，但多值或非法词法不能假装确定。
                var observed = Values(item, PlatformSemantics + "observedAtUtc");
                if (observed.Length > 1) Add("event_time_invalid", item, PlatformSemantics + "observedAtUtc", "事件观察时间最多一个显式时区时间戳。");
                foreach (var value in observed) CheckTimestamp(item, PlatformSemantics + "observedAtUtc", value);
            }
            foreach (var claim in claims)
            {
                token.ThrowIfCancellationRequested();
                if (claim.Kind != RdfTermKind.Iri || !Values(claim, JenaRdfCodec.Type).Any(value => value.Kind == RdfTermKind.Iri && value.Value == PlatformSemantics + "IdentityClaim"))
                    Add("identity_claim_invalid", claim, JenaRdfCodec.Type, "身份声明必须是显式登记的命名IdentityClaim，不能按编号或标签推断身份。");
                foreach (var name in IdentityTimePolicy.KeyFields)
                {
                    // 编号与范围逐字段检查真实RDF项，不选取多值第一项。
                    var values = Values(claim, PlatformSemantics + name);
                    if (values.Length != 1 || !IdentityTimePolicy.StringTerm(values[0]))
                        Add("identity_claim_invalid", claim, PlatformSemantics + name, "组织、厂区、来源命名空间及外部编号必须各有一个非空字符串。");
                }
                foreach (var name in new[] { "targetIri", "declarationSource", "validityInterval" })
                {
                    // 外部声明来源只作引用保留，不通过网络解析。
                    var values = Values(claim, PlatformSemantics + name);
                    if (values.Length != 1 || values[0].Kind != RdfTermKind.Iri)
                        Add("identity_claim_invalid", claim, PlatformSemantics + name, "目标、声明来源及有效区间必须各有一个明确命名IRI。");
                    else if (name == "validityInterval" && !intervals.Contains(values[0]))
                        Add("time_reference_missing", claim, PlatformSemantics + name, "身份有效期必须引用已登记受控Interval。");
                    else if (name == "targetIri" && !triples.Any(triple => triple.Subject == values[0] && triple.Predicate == JenaRdfCodec.Type && triple.Object.Kind == RdfTermKind.Iri))
                        Add("identity_claim_invalid", claim, PlatformSemantics + name, "目标IRI必须在同一四源包中有显式命名类型声明。");
                }
            }
            // 只比较完整复合键；不同组织、厂区或来源的同号从不自动合并。
            var complete = claims.Where(claim => IdentityTimePolicy.KeyFields.All(name => Values(claim, PlatformSemantics + name) is { Length: 1 } values && IdentityTimePolicy.StringTerm(values[0]))).ToArray();
            foreach (var group in complete.GroupBy(claim => (Values(claim, PlatformSemantics + "organizationId")[0].Value, Values(claim, PlatformSemantics + "siteId")[0].Value, Values(claim, PlatformSemantics + "sourceNamespace")[0].Value, Values(claim, PlatformSemantics + "externalIdentifier")[0].Value)))
            {
                // 同键两两比较前先固定集合，取消预算贯穿每一对。
                var items = group.ToArray();
                for (var left = 0; left < items.Length; left++)
                    for (var right = left + 1; right < items.Length; right++)
                    {
                        token.ThrowIfCancellationRequested();
                        // 必须引用唯一合法区间；缺失/多值已有阻断，不选第一个。
                        var a = Values(items[left], PlatformSemantics + "validityInterval");
                        // 另一声明保留自己的区间和源作用域。
                        var b = Values(items[right], PlatformSemantics + "validityInterval");
                        if (a.Length != 1 || b.Length != 1 || !intervals.Contains(a[0]) || !intervals.Contains(b[0])) continue;
                        // 未知端点不会被默认成无限远；只有证实不相交才能确定安全。
                        var relation = TemporalContractRules.Compare(Endpoint(a[0], TimeNamespace + "hasBeginning", instants), Endpoint(a[0], TimeNamespace + "hasEnd", instants), Endpoint(b[0], TimeNamespace + "hasBeginning", instants), Endpoint(b[0], TimeNamespace + "hasEnd", instants));
                        if (relation is TemporalRelation.Overlap or TemporalRelation.Indeterminate)
                            foreach (var focus in new[] { items[left], items[right] })
                                Add(relation == TemporalRelation.Overlap ? "identity_ambiguous" : "identity_relation_indeterminate", focus, PlatformSemantics + "validityInterval", relation == TemporalRelation.Overlap ? "AMBIGUOUS：同一完整编号键存在重叠有效声明，不选择首个身份。" : "INDETERMINATE：未知端点不足以证明同号历史不相交，不能视为无冲突。", relation == TemporalRelation.Indeterminate);
                    }
            }
        }

        /// <summary>严格词法和datatype校验先于解析，绝不补本机时区。</summary>
        private void CheckTimestamp(RdfTerm subject, string path, RdfTerm value)
        {
            if (value.Kind != RdfTermKind.Literal || value.Language is not null || value.Datatype != Xsd + "dateTimeStamp")
                Add("time_lexical_invalid", subject, path, "受控时间戳必须是xsd:dateTimeStamp literal，不接受语言标签或其它datatype。");
            else if (!TemporalContractRules.TryInstant(value.Value, out _))
                Add(value.Value.Length >= 19 && value.Value[19..].IndexOfAny(['Z', '+', '-']) < 0 ? "time_timezone_required" : "time_lexical_invalid", subject, path, "时间戳须含明确Z或时区偏移，符合受控日期、秒及最多七位小数；不猜本机时区。");
        }

        /// <summary>只从唯一已登记点读取合法时间，未知和已诊断错误均不伪造端点。</summary>
        private string? Endpoint(RdfTerm interval, string path, HashSet<RdfTerm> instants)
        {
            // 端点缺失是未知，多值不挑选第一项。
            var links = Values(interval, path);
            if (links.Length != 1 || !instants.Contains(links[0])) return null;
            // 同一时间点仅接受一个合法精确typed literal。
            var values = Values(links[0], TimeNamespace + "inXSDDateTimeStamp");
            return values.Length == 1 && values[0].Kind == RdfTermKind.Literal && values[0].Datatype == Xsd + "dateTimeStamp" && values[0].Language is null && TemporalContractRules.TryInstant(values[0].Value, out _) ? values[0].Value : null;
        }
    }
}
