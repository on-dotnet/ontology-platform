# G3-M1 公共合同

状态：FROZEN。独立m1_contract_review（Astra/high）Spec/Quality PASS，原5项均已关闭。仅G3-M1-001授权；Base d6aab6b47e63c9d5deadfa480f6659c62c5ed138。Master单写，禁止新增直接依赖。

## 公共接口与权威源

复用SourceBundle、SourceHashes、ActorContext、CommandContext、RdfTerm、SemanticDiagnostic、SemanticValidationReport及全部G2协议；不改变历史Run/SSE/Capability的wire shape和schema hash。

新增IG3OntologyService：GetProfile()返回SemanticSupportProfile；AssessAsync(actor,draftId,ValidateDraftRequest,token)返回SemanticAssessment；ReadAssessmentAsync(actor,assessmentId,token)返回持久记录；CompareAsync(actor,CompareVersionsRequest,token)返回SourceComparison[]。GET /api/v1/semantic/support-profile；POST /ontology-drafts/{id}/assessments；GET /semantic-assessments/{id}；POST /ontology-comparisons。宿主全部RequireAuthorization，写评估ontology.edit+CSRF+If-Match，比较semantic.read+CSRF且无业务写入。actor不入请求。服务再次校验role/scope，先授权再解析源。

新增IG3SemanticRuntime.CompareSourcesAsync(left,right,token)返回四源SourceComparison[]；每个源单独解析，blank scope不跨源。比较结果EQUIVALENT/DIFFERENT/INDETERMINATE；SourceChanged为原始字节是否不同，缺席vocabulary不同于空字符串。SourceComparison含SourceId、LeftHash/RightHash（可空）、SourceChanged、GraphComparisonResult。VersionRef(kind=DRAFT|RELEASE,id,revision?)，DRAFT必须revision>=1，RELEASE revision必须null；比较仅同asset+相同完整scope，不接受客户端hash或对象地址。

## Profile与assessment

SemanticSupportProfile：ProfileId、Version、Hash、ReasoningMode、Capabilities[]、ComparisonBudget。稳定ID ontology-platform/g3-m1，Version=1，ReasoningMode=ASSERTED_ONLY。20项capability含Id、Name、Edit/Preserve/Publish/Validation四个明确状态和Reason。Hash为固定顺序JSON（Hash置空）UTF8 SHA256；Hash不进入自身计算。

GraphComparisonBudget：MaxBlankNodes=128、MaxSearchNodes=100000、TimeoutMilliseconds=5000，沿用5000 triples/源码字节上限。精确比较是集合去重、分区细化剪枝、有界双射搜索，最终核验全部triple集合；只有穷尽可判DIFFERENT，预算/取消为INDETERMINATE。相同字节可直接返回EQUIVALENT，无新图语义假设。

SemanticAssessment：AssessmentId、ValidationReportId、DraftId、Revision、Hashes、ProfileVersion、ProfileHash、AssessmentHash、AssessedAtUtc、ExpiresAtUtc、ExecutorVersion、Stages[]、PublishEligible、Diagnostics[]、BudgetStatus。每个stage含Name、Status（PASS/FAIL/NOT_RUN/NOT_SUPPORTED/INDETERMINATE）、Code。stage分别PARSE、SUPPORT、SHACL_CORE、GOVERNANCE、OWL_REASONING（永远NOT_RUN）。明确OWL_REASONING未执行不阻断已登记asserted-only子集，但其他必需阶段必须PASS，预算必须COMPLETE。服务器真实RIOT/SHACL产生，不接受客户端assessment正文。有效期24h；assessment散列为其自身Hash置空后的固定JSON字节；包含准确四hash、profile、执行版本及时间。

AssessAsync由Ontology持久到独立AssessmentRecord，AssessmentId与ValidationReportId有唯一约束；与原报告、幂等回执、审计同一PG事务。保留原ValidateAsync响应，新的验证也生成关联assessment，使原G2客户端调用流程可升级但不能用旧持久报告直接新发布。同一命令重放返回原事实，不换时间或重新评估。ReadAssessment再次授权草稿scope；不存在404，已知越界403。

## 发布及严格兼容

新增PublicationSemantics(ProfileVersion,ProfileHash,AssessmentId,AssessmentHash)。只在DraftPublicationSnapshot、ReleaseProposal、ReleaseManifest增加可缺席且null不序列化的Semantics字段；其余G2字段required规则不变，未知字段仍拒绝。请求CreateProposalRequest不接受此字段；服务端按ValidationReportId定位，不能伪造。

IDraftPublicationReader原方法保持签名：锁定草稿后核验报告及对应assessment的全部绑定、服务端重新计算hash、时间、当前profile、eligible，返回Snapshot.Semantics。Publishing在创建、审核和激活时重新锁读，对比proposal.Semantics；审核Binding加入Semantics；当前revision、profile或assessment变化不沿用旧批准。新PUBLISH必须有Semantics，否则assessment_required；过期assessment_expired；不匹配assessment_binding_conflict（409）；不符合assessment_not_eligible（422）。旧legacy proposal不能新激活PUBLISH。

新发布Manifest SchemaVersion=2且Semantics完整；SchemaVersion=1必须无Semantics。使用显式ReleaseManifestCompatibility.Validate分版本校验（1=LEGACY_G2、2=G3_M1），未知schema拒绝，不伪造缺字段。原V1所有必需字段保持；V2精确完整hash和profile格式必需。旧V1序列化不新增null字段。回读直接验证存储的原始manifest对象hash，不把反序列化再序列化当作原始字节。

V1在原G2语义清单下验证；V2按其固定profile验证，不将当前profile悄悄用于旧记录。旧报告无assessment不能新PUBLISH，但旧正式Release可按原profile重新回验制品/同批图，再经当前权限、异人审批、24h、CAS及审计Outbox回滚；回滚不锁当前草稿。Run/SSE/MCP snapshot原字节/版本不迁移。V2写入前验收单独编译的兼容读取二进制，之后应用回退仅使用此兼容版本，禁止退G2旧binary。

## 支持边界、字节与输出

M1保留G2结构编辑子集；命名equivalent/disjoint/inverse可源码保存并由profile明确支持有限发布，复杂/bnode/属性特征/restriction/链/imports/身份公理阻结构编辑与发布，原文仍保存导出。不推理、不联网、不从UI投影重建。未修改/no-op原UTF8（含BOM/CRLF/注释）不变；实际精确编辑保留旧修订且仅改明示RDF语义。保留语法失败不创建修订和原预算。

未来Impact仅文档占位，不生成M4业务/表。M1四源比较实际实现；复杂图比较INDETERMINATE不展示0差异，发布验证需要确定比较时必须失败关闭。

## 所有权与验收

## 独立初审修订后的精确边界

1. IDraftPublicationReader为审核只读核验允许platform.operator或platform.auditor（均再检查完整scope），但不改变写操作角色。Decide读取proposal授权后，事务先锁draft再锁proposal并重验，禁止proposal→draft反向顺序。回滚不锁draft。
2. assessment诊断使用新AssessmentDiagnostic(SourceId,SourceHash,Diagnostic,Line?,Column?)包装原SemanticDiagnostic，SourceId只能ontology/shapes/vocabulary/data/bundle。bundle hash用于跨源支持诊断，能准确定位时使用对应源hash；没有可靠定位行列为null，不能猜。旧SemanticDiagnostic不改。
3. Profile四维有限状态：Edit=BASIC|SOURCE；Preserve=EXACT；Publish=SUPPORTED|BLOCKED；Validation=ASSERTED|NOT_SUPPORTED。20行ID按计划01..20，1为SOURCE/EXACT/SUPPORTED/ASSERTED，2..8为BASIC/EXACT/SUPPORTED/ASSERTED，9..11为SOURCE/EXACT/SUPPORTED/ASSERTED（仅命名IRI对），12..19为SOURCE/EXACT/BLOCKED/NOT_SUPPORTED，20为SOURCE/EXACT/BLOCKED/NOT_SUPPORTED（M1不实现OWL-Time模板）。BASIC仅现有白名单结构变更，不表示新M2图形功能。Ontology/vocabulary/data的未知owl公理、blank节点、复杂/未白名单RDFS产生阻断；仅已声明object/datatype property的简单断言和明确普通annotation允许，不把普通自定义词汇宣称推理能力。Shapes采用独立ShapePolicy：既有合法SHACL property/list blank节点不受ontology blank策略误伤，SHACL不支持仍阻断。
4. PublishingRules.Binding按Semantics缺席明确使用原G2匿名对象字段和顺序；有值采用加Semantics的新算法。legacy ROLLBACK保持原批准hash可核验；legacy PUBLISH一律必须重新取得assessment和批准。新增Semantics不得以null字段改变旧绑定/manifest字节。
5. CompareSourcesAsync的5秒和100000搜索节点为一次四源比较共享预算，覆盖RIOT解析、分区细化、搜索和最终核验；左右各SourceBundle四源合计最多5000 triples、每文档256KiB及bundle1MiB。每循环和外部HTTP共享CancellationToken，128 blank节点按单源两图各自检查，超限不是DIFFERENT。任一总体预算/取消触发，返回四个结果全部INDETERMINATE，Code固定comparison_timeout/comparison_cancelled/blank_node_budget/search_node_budget，保留各源字节变化与hash；不把已有部分比较冒充完整完成。比较Runtime捕获自身取消/预算而非沿用G2 Execute的503映射。应用层授权/读取尚未完成即请求取消可按标准取消结束，不能生成成功或落库。比较错误的非法Turtle保持422，不伪装图不同。

Master：本合同、g2-models.json/生成器/Contracts、全部迁移、Host、OpenAPI/生成TS、CI/scripts。SEM：Ontology/Publishing/SemanticQuery实现和对应测试/samples；FE：ontology feature及测试。并行任务均不越界，公共变更先提Master。

验收：DTO缺/额外/错判别负例，V1旧字节与V2严格读取；旧Run/SSE；profile/hash/过期/伪造assessment及CAS/角色负例；20语料；四源往返、同构/非同构/对称/环/共享/超预算取消；真实PG/Jena/RustFS发布查询回滚、active故障不变；真实HTTP/OpenAPI/TS、UI；独立Reviewer及同Head CI。全部目前NOT_RUN。
