# G3-M3：术语、标准及Synthetic单位量纲合同

状态：FROZEN。Master公共合同单写；仅M3+E0。规范来源：W3C SKOS Reference 2009 https://www.w3.org/TR/skos-reference/ ，正式RDF/OWL/SHACL；本项目额外治理政策明确区分。无QUDT/UCUM正式资产，不宣称完整QUDT兼容。

## 权威与HTTP

四源SourceBundle/PG修订/CAS/幂等/审计保持唯一权威，不新表/迁移/词汇数据库。旧OntologyDraft/SemanticProjection/SemanticEdit/ReleaseManifest/Run/SSE合同不改。

新增GET /api/v1/ontology-drafts/{id}/vocabulary → VocabularySnapshot（semantic.read/完整scope）；POST /api/v1/ontology-drafts/{id}/vocabulary-edits → OntologyDraft（ontology.edit/CSRF/强If-Match/完整scope）；GET /api/v1/releases/{id}/vocabulary → VocabularySnapshot（semantic.read/完整scope/已Published）。现有普通源码保存仍可保留冲突草稿，assessment阻断发布；批量精确编辑不清洗未知RDF，不以标签改身份。

DTO唯一来源g2-models.json：
- VocabularyEditSource枚举：ontology、vocabulary。未知/数字在JSON400拒绝。
- VocabularyChange：SourceId VocabularyEditSource、Edit SemanticEdit。
- VocabularyEditsRequest：Hashes SourceHashes、Changes VocabularyChange[]、Command CommandContext；全部必需非null，批1..64项；一次命令最多两个源原子更新。Hashes与revision相同已读版本；任何旧对象不存在409 vocabulary_edit_conflict；无批/超64/非法项422 vocabulary_edit_invalid；缺JSON字段/extra400。源码本身仍受既有256KiB/source、1MiB/bundle、三元组和执行预算。
- VocabularySourceTriple：SourceId string（server只输出ontology/shapes/vocabulary/data）、Triple RdfTriple。全部四源实际解析三元组用于引用位置；保留RdfTerm kind/value/datatype/language，不从显示字符串反建RDF。
- VocabularySnapshot：DraftId string?、ReleaseId string?、ManifestHash string?、Revision long、Hashes SourceHashes、ProfileVersion string?、ProfileHash string?、Triples VocabularySourceTriple[]、Diagnostics AssessmentDiagnostic[]。当前草稿DraftId有值/ReleaseId及ManifestHash=null；正式版三者来自固定manifest，Revision/Hashes/profile来自正式manifest，不能用当前草稿替代。历史Manifest V1没有Semantics，ProfileVersion/ProfileHash明确null（UI显示LEGACY_G2/UNKNOWN），禁止填current v3或捏造历史profile；V2必须来自已注册精确profile。

IG3VocabularyService.ReadVocabularyAsync(actor,draftId,ct)、EditVocabularyAsync(actor,draftId,VocabularyEditsRequest,ct)、ReadReleaseVocabularyAsync(actor,releaseId,ct)。实现由OntologyService partial继承，复用Write/SaveCore事务边界，权威scope在任何源/Jena调用前检查；同命令相同payload重放，冲突payload拒绝；无变化保原字节但沿既有保存修订规则。不触碰shapes/data原字节；ontology/vocabulary只对有真实变更源canonicalize完整图，旧修订保留。

IG3VocabularyRuntime.ReadVocabularyAsync(sources,revision,ct)、ApplyVocabularyEditsAsync(sources,changes,ct)。由JenaSemanticRuntime partial实现，真实RIOT解析；投影不是新权威。正式服务先IReleaseCatalog与不可变对象核验，再ISemanticRuntime.ReadVerifiedPublishedAsync对实际Jena同批图和源逐项核验，通过后投影同一已验证四源，不能只有PG/Mock便标正式查询成功。未知/复杂源支持失败不能丢三元组，只锁结构保留源码。

## SKOS标准与治理政策

Concept/ConceptScheme、pref/alt/hiddenLabel、notation/definition、broader/narrower/related、inScheme/topConceptOf/hasTopConcept、exact/close/broad/narrow/relatedMatch按显式事实保留，不执行OWL推理或自动sameAs。允许Concept属于多个Scheme；同标签不同IRI只是搜索歧义，不自动合并。

S13：同一subject上的同RDF literal（value+大小写不敏感language+datatype规范）不能同时出现在pref/alt/hidden不同标签关系。S14：每资源每语言最多一个prefLabel（重复相同三元组集合去重不是冲突）；EN/en归一比较但原词法保留。@zh与@en同文本不是冲突。所有使用这些谓词的资源都检查，不限显式Concept。标签必须非空plain/lang literal；合法BCP47语法、支持zh/en及其合法子标签；其它语法合法语言保留并显示language_policy_unknown，不假装非法。无lang标签允许原文保存，治理显示skos_label_language_required并阻断本轮正式术语（平台政策）。

Scheme必须显式登记ConceptScheme；Concept至少一个已登记Scheme（治理）。broader/narrower/related两端必须已登记Concept；broader(A,B)和narrower(B,A)为同方向层次边，有限图检测环（平台治理冲突，不是OWL矛盾）；related不许同节点或与任一方向可达层次重叠。mapping两端已登记Concept且有明确Scheme，只允许至少一对不同Scheme、共享Scheme的exactMatch不自动视sameAs；缺引用/无确定Scheme阻断并准确位置。显式mapping完整性遵循SKOS S41/S43/S46：broadMatch(A,B)/narrowMatch(B,A)也贡献同向层次边，relatedMatch贡献关联边；同一对（含对称方向规范）exactMatch不得与broadMatch/narrowMatch/relatedMatch重叠，broad/narrowMatch不得与related/relatedMatch层次可达重叠，代码skos_mapping_relation_conflict。仅有界检查已登记显式事实及必要可达性，不物化推理图。

notation按共享Scheme+datatype+value唯一，同一Concept多Scheme允许、不同不共享Scheme同notation允许并在搜索显示歧义。缺Scheme无法判唯一时UNKNOWN，不认定无冲突。废弃用owl:deprecated true^^xsd:boolean受控annotation，保留IRI/历史，v3评估对当前四源全部关系/单位引用废弃项报semantic_reference_deprecated（本方法不带前一修订，不声称只检查时间差分）；历史profile不追加该新规则。

诊断代码：skos_label_language_invalid、skos_label_language_required、language_policy_unknown、skos_label_term_invalid、skos_pref_label_conflict、skos_label_relation_conflict、skos_notation_duplicate、skos_scheme_reference_missing、skos_concept_reference_missing、skos_hierarchy_cycle、skos_related_hierarchy_conflict、skos_mapping_scheme_conflict、skos_mapping_relation_conflict、skos_reference_ambiguous、semantic_reference_deprecated。错误severity=error阻断；unknown项severity=warning但GOVERNANCE=INDETERMINATE、不具发布资格。每个诊断带真实sourceId/hash/focus/path，跨源唯一定位不能确定则bundle，line/column无证据null。

## 单位/quantity kind/量纲/标准来源

平台自身词汇命名空间P=`urn:ontology-platform:semantics:`；合成实例`urn:synthetic:m3:*`。仅四种类型P:UnitDefinition、P:QuantityKind、P:Dimension、P:StandardSource，均为明确命名IRI。单位定义IRI本身版本化，P:canonicalUnit指向稳定单位IRI，P:version为非空版本literal，P:quantityKind/P:dimension分别指登记IRI，P:symbol是显示literal，P:standardSource指登记StandardSource，P:precision为明确非空literal或UNKNOWN，P:synthetic true^^xsd:boolean。不能从℃/K/MPa/t符号猜身份或换算。UnitDefinition的canonicalUnit/version/quantityKind/dimension/symbol/standardSource/precision/synthetic每项恰一，缺失按对应reference/version/source/precision错误，任一多值报unit_definition_conflict，禁止选First；StandardSource的version/synthetic/prov:wasDerivedFrom每项恰一、rdfs:label至少一且按语言唯一；QuantityKind的dimension恰一，多值报quantity_kind_reference_missing并说明基数错误。

Dimension必须有七项xsd:integer指数：P:lengthExponent、massExponent、timeExponent、electricCurrentExponent、temperatureExponent、amountExponent、luminousIntensityExponent，每项恰一、整数-32..32；资源IRI也是身份，指数相同只证明本轮声明维度一致，不推断quantitykind相同。QuantityKind恰一P:dimension。StandardSource至少P:version、rdfs:label、P:synthetic true，prov:wasDerivedFrom是来源IRI（Synthetic引用允许urn:synthetic，不联网）。所有本轮fixture明确Synthetic，正式QUDT资产/许可审批不在此实现。

仅含任一P:quantityKind/P:dimension/P:nominalUnit的属性资源触发适配完整性；普通历史/G2无此谓词的datatypeProperty不要求单位。触发的属性需显式owl:DatatypeProperty并有P:quantityKind、P:dimension、P:nominalUnit（一项版本化UnitDefinition IRI）。属性quantityKind/dimension/nominalUnit每项恰一，缺失或多值报property_unit_binding_invalid。核对登记、单位版本/source/precision、属性与quantitykind/单位的dimension IRI和完整指数、quantityKind精确匹配。不同IRI但同指数不自动认定同一量纲，诊断需明确；未知precision/source显示UNKNOWN并阻断，不能默认精度。K/℃共享温度Dimension但两个canonicalUnit及定义IRI，MPa压力、t质量；不存/算换算因子。

诊断：unit_reference_missing、unit_version_reference_missing、unit_definition_conflict、quantity_kind_reference_missing、dimension_reference_missing、dimension_definition_invalid、unit_dimension_mismatch、unit_quantity_kind_mismatch、property_unit_binding_invalid、unit_source_required、unit_precision_unknown。原始标准引用和版本进入RDF及四源hash/正式Release；不建立第二套单位表。

## Profile/评估/历史

SemanticProfile.LegacyM1()字节/hash不变；当前v2函数原封保留为LegacyM2()；Current()注册v3，在原20行后添加21 SKOS和22 Synthetic单位引用能力（Edit BASIC/Preserve EXACT/Publish SUPPORTED/Validation ASSERTED），Reason明确域治理与非换算。hash按原DTO顺序算法。Matches显式v1/v2/v3，任何未知version/hash拒绝。

新assessment仍五阶段PARSE/SUPPORT/SHACL_CORE/GOVERNANCE/OWL_REASONING，SHACL仅原真实报告，M3诊断由ReadVocabularyAsync返回直接追加AssessmentDiagnostic，保留精确code不经过旧ValidationIssue丢码链。GOVERNANCE根据M3诊断error→FAIL、warning/unknown→INDETERMINATE、无问题PASS；资格需前四PASS/预算COMPLETE，OWL_REASONING始终NOT_RUN。旧ValidateAsync wire保留，不能把治理冲突伪装SHACL constraint。

当前草稿与结构编辑采用v3发布支持白名单：增加仅此合同P谓词及owl:deprecated元数据，不放开其他OWL/未知语义。新Release deploy/Verify/ReadVerified按manifest精确profile分派：v1/v2保留旧Support，不回套M3治理；v3要原支持+M3政策，防绕过assessment。V1 Manifest/历史Run/SSE及其字节/hash不改，旧v1/v2正式版当前授权/异人审批/CAS回滚仍可用。旧v2 assessment不能新发布；不能把current=v3破坏M1/M2验收中显式historical profile预期。

## UI/状态与所有权

三栏同draftId/revision/hash/dirty/selection；默认source和E0状态合同固定。加术语/单位工作区模式，目录/搜索/新建编辑/废弃/多语言别名/标准来源/引用位置/历史差异，右侧服务诊断；真实API，不从textarea正则猜RDF。结构编辑使用原始RdfTerm精确batch；有未保存源码时阻断结构编辑。保存清旧assessment、刷新同revision词汇snapshot；回包过期/卸载取消不能覆盖新草稿。正式词汇显示由release接口返回明确固定releaseId/hash，不能把Draft当正式。

Master：本合同、DTO/schema/OpenAPI/生成TS、Host/DI公共组合、g2-client、全部迁移、CI/公共scripts/Tokens、backend/tests/OntologyPlatform.G2ContractTests/G3M3VocabularyContractTests.cs、SecurityTests/G3M3EndpointTests.cs及master证据。SEM：Ontology模块（排除迁移，含profile唯一实现写者和模块内DI）、SemanticTests、新增PublishingTests/G3M3*.cs及samples/g3-m3、SEM证据；只读公共合同/Host/CI/scripts/Web。WEB：apps/web/src/features/ontology/**、WEB证据；不改client/生成TS/Tokens/Shell/公共脚本。公共变更先报Master。两写者独立托管树与分支，总并发3，Reviewer只读，任何一方不回退别人工作。

## 验证与集成

合同先正例/缺多字段/源枚举/原子64预算/语言/RdfTerm/If-Match/权限/scope/hash/revision负例；独立Review后冻结。SEM最早API+PG/Jena子闭环独立Review/同HeadCI后增量main点1；WEB真实UI/API子闭环同样点2。E0全部真实门禁/独立Review通过后才M3正式整栈验收。
