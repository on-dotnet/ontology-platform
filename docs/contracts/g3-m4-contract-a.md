# G3-M4-CONTRACT-A 身份与时间公共合同

状态：FROZEN；公共Owner Master。只Slice A，B合同尚未冻结。基础来源：[OWL-Time 2017 Recommendation](https://www.w3.org/TR/2017/REC-owl-time-20171019/)；本轮是有界模板及平台治理，不是通用时间推理。

## 权威与协议

复用四源SourceBundle、VocabularySnapshot（完整Triples/Diagnostics及revision/hashes/profile/正式上下文）、VocabularyChange/SemanticEdit。新增IdentityTimeEditsRequest={Hashes SourceHashes, Changes VocabularyChange[], Command CommandContext}；全部required/非null/拒绝未知字段，batch 1..64，source仅ontology/vocabulary。快照用原VocabularySnapshot，不另造实体权威表。精确RdfTerm保留language/datatype，复杂未知RDF不能被投影丢弃。

GET /api/v1/ontology-drafts/{id}/identity-time→VocabularySnapshot（semantic.read）；POST /api/v1/ontology-drafts/{id}/identity-time-edits→OntologyDraft（ontology.edit/CSRF/强If-Match=command.expectedRevision）；GET /api/v1/releases/{id}/identity-time→VocabularySnapshot（semantic.read，固定manifest+RustFS+Jena核验）。IG3IdentityTimeService三方法；runtime复用IG3VocabularyRuntime。旧vocabulary端点仍可读取完整事实，但新增结构谓词和所有源码保存/assessment/发布均不能绕过范围和历史检查。

任何源/Jena读取之前先授权完整草稿scope。身份organizationId必须等于草稿组织，siteId必须属于草稿完整厂区集合；跨scope写拒403 identity_scope_forbidden，不按actor全局权限扩大草稿。此前已形成有效声明（本claim局部字段/类型/命名时间引用及已知端点词法/顺序均有效）的身份历史不可删除、改组织/厂区/ns/编号/target/来源/开始时间；允许为旧未知to补明确终点或收窄原to（不能移动from或扩张），旧claim与起点事实保留，建立新claim IRI承接新身份。初次保存便缺失或错误时间的未有效声明允许修正，原修订保留；不得因整个bundle有无关错误、新增重叠claim或未评估而解锁此前局部有效claim。旧有效claim改成错误时间或删类型仍拒。四源普通源码保存也检查该历史约束；原不可变DraftRevision仍完整保存。并发以真正DB CAS锁重新检查，不只预检。

结构编辑先整批完成再治理：非法claim/time/error→422 identity_time_invalid；需要关系但无法确定→422 identity_time_indeterminate。普通源码保存允许语义错误/unknown以便专家修正（跨scope/历史破坏仍拒），assessment与发布失败关闭。命令幂等沿原Replay/SaveCore；重试相同payload不二次修订，异payload同key409。原审计和发布Outbox事务不重建。

## 有限RDF表达

P=`urn:ontology-platform:semantics:`，T=`http://www.w3.org/2006/time#`。所有新身份/时间主体为显式命名IRI；bnode新模板保源码但结构/发布阻断。P:IdentityClaim必须恰一P:organizationId/siteId/sourceNamespace/externalIdentifier（非空xsd:string或plain literal）、P:targetIri（命名IRI）、P:declarationSource（来源IRI）、P:validityInterval（显式T:Interval）。target必须在同bundle有显式命名类型声明，来源IRI不联网。相同编号不同组织/厂区/ns不合并，任何标签不产生sameAs。

T:Instant仅允许rdf:type T:Instant、T:inXSDDateTimeStamp（0或1、xsd:dateTimeStamp、显式Z或±hh:mm、最多7位小数、年0001..9999，不支持闰秒/24:00）；0项为未知时间，不伪造值，多项error。T:Interval仅T:hasBeginning/T:hasEnd（各0或1命名Instant）；未知端点缺谓词，不填无限大。不允许Instant/Interval双类型、额外OWL-Time模板/关系、bnode、循环/悬空引用。受控类型可有既有label/comment annotation，不开放任意时间表达。

P:Event必须恰一T:hasTime指受控Instant或Interval；P:observedAtUtc是独立观察时间，可空或一个同上显式时间戳literal。事件时间、业务有效期、DraftRevision/manifest的创建时间互不替代；不从文件/机器时间推断。半开区间[from,to)，已知from>=to报time_interval_reversed；相接to=from无重叠。相同完整身份键的两个声明若已知重叠（含同target重复记录）identity_ambiguous/AMBIGUOUS；能证明不相交允许历史；未知端点不足以判断时identity_relation_indeterminate/INDETERMINATE，不能当无冲突。单个未知to允许保存/发布，只有所需比较不确定才阻断。

TemporalContractRules为纯公共时间词法/半开关系合同；不依赖EF/HTTP/Jena。返回OVERLAP/DISJOINT/INDETERMINATE/INVALID，不猜时区。

诊断固定code：identity_claim_invalid、identity_scope_conflict、identity_ambiguous、identity_relation_indeterminate、identity_history_immutable、time_timezone_required、time_lexical_invalid、time_interval_reversed、time_reference_missing、time_template_unsupported、event_time_invalid。AssessmentDiagnostic复用真实sourceId/hash/focus/path；跨源无法唯一定位bundle/hash，line/column无证据null。GOVERNANCE error=FAIL，unknown=INDETERMINATE，均不具发布资格；保留原SHACL阶段，不改成通用OWL一致性。

## Profile及兼容

原Current v3完整保留为LegacyM3，v1/v2 hash不变；Current v4只将20受控时间改BASIC/SUPPORTED/ASSERTED，并追加23显式身份治理，保留原21/22。所有发布/回验/正式读取精确version/hash派发：v1/v2原政策，v3仅M3，v4 M3+M4。旧profile不反套M4诊断；新assessment只v4，旧assessment不能新发布，历史Release/Run/回滚保留。不实现sameAs/hasKey推理。

## 生成、测试与路径

唯一模型源docs/contracts/g2-models.json→generate-g2-contracts.py→G2Models.g.cs/g2-schemas.openapi.json；宿主真实OpenAPI导出→g2-platform.openapi.json→generate-types.mjs→g2-generated.ts。生成后逐字节检查，空paths不作API证据。Master单写这些文件和Contracts/Host/g2-client/迁移/公共scripts/锁/CI/Tokens及合同/Security测试。SEM/WEB owned_paths见任务卡。

廉价合同测试先检缺失/null/extra/source枚举/时间zone/非法词法/倒序/相邻/未知关系/VersionRef判别。真实层必须补跨厂组织/重叠同号/历史不可变/陈旧CAS/权限/幂等/审计/真实PG-Jena-RustFS发布查询回滚及浏览器。跨版本/impact伪造/过期属于合同B，不用不存在的A测试宣称完成。独立Reviewer通过后才FROZEN并派SEM-A/WEB-A。

## 最小Synthetic示例

```turtle
@prefix p: <urn:ontology-platform:semantics:> .
@prefix time: <http://www.w3.org/2006/time#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
<urn:synthetic:m4:asset:A> a owl:NamedIndividual .
<urn:synthetic:m4:claim:A> a p:IdentityClaim ;
  p:organizationId "org-a" ; p:siteId "site-a" ;
  p:sourceNamespace "erp.synthetic" ; p:externalIdentifier "EQ-01" ;
  p:targetIri <urn:synthetic:m4:asset:A> ;
  p:declarationSource <urn:synthetic:m4:declaration:v1> ;
  p:validityInterval <urn:synthetic:m4:validity:A> .
<urn:synthetic:m4:validity:A> a time:Interval ;
  time:hasBeginning <urn:synthetic:m4:instant:A> .
<urn:synthetic:m4:instant:A> a time:Instant ;
  time:inXSDDateTimeStamp "2026-01-01T00:00:00Z"^^xsd:dateTimeStamp .
<urn:synthetic:m4:event:A> a p:Event ; time:hasTime <urn:synthetic:m4:instant:A> ;
  p:observedAtUtc "2026-01-01T01:00:00Z"^^xsd:dateTimeStamp .
```

以上未知终点由缺hasEnd表达，不是无穷或确定永久有效。组织/厂区须取实际草稿scope，Synthetic示例不授予权限。

## 结构编辑安全错误优先级补充

此前有效历史破坏优先409 identity_history_immutable（锁内CAS复核）；跨草稿scope拒403 identity_scope_forbidden。其余422按固定类别优先级identity_ambiguous→time_interval_reversed→time_timezone_required→time_lexical_invalid→time_reference_missing→time_template_unsupported→identity_claim_invalid→event_time_invalid；其它error回退identity_time_invalid，未知关系identity_relation_indeterminate。优先级只选择错误类别，不从冲突身份值中选首项。原始源读取/assessment仍返回完整真实来源诊断，结构请求失败不伪造行列或未生成的assessment引用。UI仅显示本地固定安全中文说明，不显示远端detail。
