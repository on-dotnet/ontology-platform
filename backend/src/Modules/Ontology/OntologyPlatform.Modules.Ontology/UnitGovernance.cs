using System.Globalization;
using OntologyPlatform.Contracts;

namespace OntologyPlatform.Modules.Ontology;

/// <summary>有限Synthetic单位定义与属性引用治理；不会猜测身份或执行换算。</summary>
public sealed partial class JenaSemanticRuntime
{
    /// <summary>同一次四源解析的单位检查，沿用准确来源与共享执行预算。</summary>
    private sealed partial class VocabularyGovernance
    {
        /// <summary>读取恰一个对象；缺失和多值都拒绝，绝不选择First。</summary>
        private RdfTerm? One(RdfTerm subject, string name, string code, bool unknown = false)
        {
            // 谓词来自固定平台有限词表，不能由用户拼接任意查询。
            var values = Values(subject, PlatformSemantics + name);
            if (values.Length == 1) return values[0];
            Add(code, subject, PlatformSemantics + name, $"{name}要求恰一明确值，实际为{values.Length}。", unknown);
            return null;
        }

        /// <summary>非空字符串值才能作为版本、符号或精度声明，UNKNOWN不冒充已知。</summary>
        private static bool KnownLiteral(RdfTerm? term) => term is { Kind: RdfTermKind.Literal } && !string.IsNullOrWhiteSpace(term.Value) && !term.Value.Trim().Equals("UNKNOWN", StringComparison.OrdinalIgnoreCase);

        /// <summary>Synthetic标志仅接受明确xsd:boolean真值。</summary>
        private static bool Synthetic(RdfTerm? term) => term is { Kind: RdfTermKind.Literal, Datatype: Xsd + "boolean", Value: "true" or "1" };

        /// <summary>引用须为明确登记IRI，语法项相似或显示符号相同均不构成身份。</summary>
        private bool Reference(RdfTerm subject, string name, RdfTerm? value, HashSet<RdfTerm> registered, string code)
        {
            if (value is { Kind: RdfTermKind.Iri } && registered.Contains(value)) return true;
            Add(code, subject, PlatformSemantics + name, $"{name}必须引用本轮明确登记的命名IRI。");
            return false;
        }

        /// <summary>检查单位、来源、七维指数和启用单位元数据的属性，不强加旧普通属性。</summary>
        internal void CheckUnits()
        {
            // 以下集合只登记四源显式声明，既不联网也不推理生成新类型。
            var units = Registered(PlatformSemantics + "UnitDefinition");
            // 量种身份与量纲身份分离，同指数不能推断同量种。
            var kinds = Registered(PlatformSemantics + "QuantityKind");
            // 维度IRI是权威身份，七指数只检验声明的一致性。
            var dimensions = Registered(PlatformSemantics + "Dimension");
            // 来源必须明确版本化且保持Synthetic出处。
            var standards = Registered(PlatformSemantics + "StandardSource");
            foreach (var declaration in triples.Where(item => item.Predicate == JenaRdfCodec.Type && item.Object.Kind == RdfTermKind.Iri && item.Object.Value is PlatformSemantics + "UnitDefinition" or PlatformSemantics + "QuantityKind" or PlatformSemantics + "Dimension" or PlatformSemantics + "StandardSource" && item.Subject.Kind != RdfTermKind.Iri))
                Add(declaration.Object.Value == PlatformSemantics + "Dimension" ? "dimension_definition_invalid" : declaration.Object.Value == PlatformSemantics + "QuantityKind" ? "quantity_kind_reference_missing" : declaration.Object.Value == PlatformSemantics + "StandardSource" ? "unit_source_required" : "unit_reference_missing", declaration.Subject, JenaRdfCodec.Type, "单位治理实体必须使用明确命名IRI，blank身份不能正式发布。");
            foreach (var dimension in dimensions)
            {
                token.ThrowIfCancellationRequested();
                foreach (var exponent in Exponents)
                {
                    // 精确datatype和词法整数同时核对，不从普通字符串推测指数。
                    var value = One(dimension, exponent, "dimension_definition_invalid");
                    if (value is not { Kind: RdfTermKind.Literal, Datatype: Xsd + "integer" } || !int.TryParse(value.Value, NumberStyles.AllowLeadingSign, CultureInfo.InvariantCulture, out var number) || number is < -32 or > 32)
                        Add("dimension_definition_invalid", dimension, PlatformSemantics + exponent, "七个基本量指数须各恰一xsd:integer，范围-32..32。");
                }
            }
            foreach (var kind in kinds)
                Reference(kind, "dimension", One(kind, "dimension", "quantity_kind_reference_missing"), dimensions, "dimension_reference_missing");
            foreach (var standard in standards)
            {
                // 每个来源版本、合成标识、出处都必须恰一；标签可多语但每语言唯一。
                var version = One(standard, "version", "unit_source_required");
                // 当前批准只允许Synthetic，false或UNKNOWN均不能混入正式来源资产。
                var synthetic = One(standard, "synthetic", "unit_source_required");
                // PROV来源也要求明确IRI；允许合成urn，不进行外网请求。
                var derived = Values(standard, Prov + "wasDerivedFrom");
                // 标签身份按BCP47大小写归一核对，但不改原字节。
                var labels = Values(standard, "http://www.w3.org/2000/01/rdf-schema#label");
                if (!KnownLiteral(version)) Add("unit_source_required", standard, PlatformSemantics + "version", "来源须有恰一明确非空版本，不能以UNKNOWN代替。");
                if (!Synthetic(synthetic)) Add("unit_source_required", standard, PlatformSemantics + "synthetic", "本轮来源须明确标注Synthetic真值。");
                if (derived.Length != 1 || derived[0].Kind != RdfTermKind.Iri) Add("unit_source_required", standard, Prov + "wasDerivedFrom", "来源须有恰一明确prov:wasDerivedFrom来源IRI。");
                if (labels.Length == 0 || labels.Any(label => !KnownLiteral(label) || label.Datatype is not (null or Xsd + "string" or "http://www.w3.org/1999/02/22-rdf-syntax-ns#langString") || label.Language is not null && !LanguageSyntax(label.Language)) || labels.GroupBy(label => label.Language?.ToLowerInvariant() ?? "").Any(group => group.Count() != 1))
                    Add("unit_source_required", standard, "http://www.w3.org/2000/01/rdf-schema#label", "来源须有非空标签，各语言最多一个，不能任意选择冲突标签。");
            }
            foreach (var unit in units)
            {
                token.ThrowIfCancellationRequested();
                foreach (var field in new[] { "canonicalUnit", "version", "quantityKind", "dimension", "symbol", "standardSource", "precision", "synthetic" })
                    if (Values(unit, PlatformSemantics + field).Length > 1) Add("unit_definition_conflict", unit, PlatformSemantics + field, "单位定义字段恰一；多值冲突不能选取首项。");
                // canonicalUnit是稳定身份，只要求IRI，不把它误认为版本化定义。
                var canonical = One(unit, "canonicalUnit", "unit_reference_missing");
                if (canonical is not { Kind: RdfTermKind.Iri }) Add("unit_reference_missing", unit, PlatformSemantics + "canonicalUnit", "canonicalUnit须是稳定命名单位IRI。");
                // 单位版本严格独立于来源版本。
                var version = One(unit, "version", "unit_version_reference_missing");
                if (!KnownLiteral(version)) Add("unit_version_reference_missing", unit, PlatformSemantics + "version", "单位定义须明确非空版本，不能用UNKNOWN代替。");
                // 符号仅为显示，不参与任何身份推断。
                var symbol = One(unit, "symbol", "unit_reference_missing");
                if (!KnownLiteral(symbol)) Add("unit_reference_missing", unit, PlatformSemantics + "symbol", "单位显示符号须为明确非空literal。");
                // 精度未确定时保留原文并返回warning，由GOVERNANCE阻断发布。
                var precision = One(unit, "precision", "unit_precision_unknown", true);
                if (!KnownLiteral(precision)) Add("unit_precision_unknown", unit, PlatformSemantics + "precision", "精度未明确，显示UNKNOWN；不能推断默认精度。", true);
                if (!Synthetic(One(unit, "synthetic", "unit_source_required"))) Add("unit_source_required", unit, PlatformSemantics + "synthetic", "本轮单位必须明确标注Synthetic真值。");
                Reference(unit, "standardSource", One(unit, "standardSource", "unit_source_required"), standards, "unit_source_required");
                // 单位定义内部量种与维度也必须对齐，不等属性引用才检查。
                var kind = One(unit, "quantityKind", "quantity_kind_reference_missing");
                // 即使量种缺失，维度引用本身仍应给出准确独立诊断。
                var dimension = One(unit, "dimension", "dimension_reference_missing");
                Reference(unit, "quantityKind", kind, kinds, "quantity_kind_reference_missing");
                Reference(unit, "dimension", dimension, dimensions, "dimension_reference_missing");
                if (kind is not null && kinds.Contains(kind) && Values(kind, PlatformSemantics + "dimension") is [var kindDimension] && dimension is not null && kindDimension != dimension)
                    Add("unit_dimension_mismatch", unit, PlatformSemantics + "dimension", "单位与quantityKind的维度IRI不一致；即使七指数相同也不能自动认定同一量纲。");
            }
            // 仅出现三个绑定谓词之一的主体进入治理；旧普通属性仍按历史行为。
            var properties = triples.Where(item => item.Predicate is PlatformSemantics + "quantityKind" or PlatformSemantics + "dimension" or PlatformSemantics + "nominalUnit").Select(item => item.Subject).Distinct().Where(subject => !units.Contains(subject) && !kinds.Contains(subject)).ToArray();
            foreach (var property in properties)
            {
                token.ThrowIfCancellationRequested();
                if (!triples.Any(item => item.Subject == property && item.Predicate == JenaRdfCodec.Type && item.Object.Kind == RdfTermKind.Iri && item.Object.Value == JenaRdfCodec.Owl + "DatatypeProperty")) Add("property_unit_binding_invalid", property, JenaRdfCodec.Type, "单位属性必须显式声明owl:DatatypeProperty。");
                // 缺失或多值一律失败，不从旧属性、domain/range或显示符号补齐。
                var kind = One(property, "quantityKind", "property_unit_binding_invalid");
                // 属性声明量纲保留独立IRI身份。
                var dimension = One(property, "dimension", "property_unit_binding_invalid");
                // nominalUnit指向具体版本化UnitDefinition，而不是canonicalUnit。
                var unit = One(property, "nominalUnit", "property_unit_binding_invalid");
                Reference(property, "quantityKind", kind, kinds, "quantity_kind_reference_missing");
                Reference(property, "dimension", dimension, dimensions, "dimension_reference_missing");
                if (!Reference(property, "nominalUnit", unit, units, "unit_reference_missing")) continue;
                if (Values(unit!, PlatformSemantics + "dimension") is [var unitDimension] && dimension is not null && unitDimension != dimension || kind is not null && Values(kind, PlatformSemantics + "dimension") is [var kindDimension] && dimension is not null && kindDimension != dimension)
                    Add("unit_dimension_mismatch", property, PlatformSemantics + "dimension", "属性、quantityKind及单位的维度IRI须完全一致；相同指数不替代身份。");
                if (Values(unit!, PlatformSemantics + "quantityKind") is [var unitKind] && kind is not null && unitKind != kind)
                    Add("unit_quantity_kind_mismatch", property, PlatformSemantics + "quantityKind", "属性与版本化单位的quantityKind必须精确一致，不能按相同维度推断量种。");
            }
        }
    }
}
