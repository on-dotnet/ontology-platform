# G4-M3-MAPPING-001｜一次性 A–F 合同与实施准入申请

2026-11-14；阶段 P0_DEPENDENCY_AND_CONTRACT_REVIEW。本文所有新接口、合同、路径和预算均 **PROPOSED / 待人类批准**，不是产品实施授权。唯一当前状态见[任务卡](../../tasks/G4-M3-MAPPING-001.md)。

事实基线 B0 = **e07eab20feb3fdef9e24a20dec12d11b15bd7d46**；正常 fetch 后 main、origin/main 与预期一致。分支 codex/g4-m3-mapping-001，托管树 /Users/chasen/.codex/worktrees/g4-m3-mapping-001/ontology-platform。原 main 的6个未跟踪 .DS_Store 保留。本轮只写本申请、任务卡、追加授权索引；产品、CI、跨平台均 NOT_RUN。

## 一次裁决摘要

推荐批准 A–F 设计及后续限定实施：Connections 内实现 PG 合成受控源映射纵向闭环；AI OFF；G3 固定发布只读；七类真实评估；异人审核；不可变 PG MappingRelease；CAS/审计/Outbox 同物理事务；U07/U09/U10/U11恢复。新增第三方依赖0。批准前仅文档，批准后同会话/分支/树继续。

请求明确裁决：① M2总体PARTIAL、TDengine等待时限定M3入场；② RM-02双分支wire合同；③ 受控PG业务行验证（当前接口没有）；④ 映射授权/持久化/迁移/Host/OpenAPI/TS；⑤ 本Task最小工程消费者与隔离合成运行资源。不批准M4多源查询、Ontop、其他连接器执行、生产或模型调用。不把目录发现当成业务身份、关系基数或可执行性证明。

## A｜依赖、事实与首切片

**原合同**：G4按M1→M2→M3→M4顺序；Mapping只绑定已存在G3 OntologyRelease。**当前事实**见附录S1–S12；Oracle已合main，旧任务卡“停任务分支”仅代表原时点。用户已允许本轮设计审查，并未提前批准实施。

| 所需能力 | B0当前接口/数据/来源 | 缺口 | 首切片建议 |
|---|---|---|---|
| 固定本体发布 | IReleaseCatalog.ReadAsync/ResolveAsync，PublishingCatalog验证正式发布/scope/对象/图（S3） | 无Mapping专用投影，依赖G3真实可用 | 固定releaseId+manifestHash；从G3已发布读服务获取IRI/单位/身份，不取当前Draft |
| 连接/配置版本 | ConnectionView.ConfigRevision/SecretVersion，ConnectionRecord.ConfigHash（S2） | 管理权限不等业务读权限 | Connections内部固定输入与提交锁复核 |
| 目录快照 | CatalogSnapshotView.Scope/ConfigRevision/SecretVersion/SchemaFingerprint/Objects；GET /catalogs/{id}（S1/2） | 没有objectRef/fieldRef和业务键/关系证明；读取会重新访问源ACL | 引用编码snapshotId+精确schema/name/kind/ordinal/name；不补造主键 |
| 类型及支持状态 | OracleMetadata保留原生类型/精度/时区/SupportStatus（S2） | 旧快照缺扩展不能当SUPPORTED；PG无业务值域 | 仅PG限定集合；保留厂商扩展；未知→INDETERMINATE |
| 会话/权限 | OIDC、PostgresTicketStore、G4SessionAuthority；读operator/auditor，写operator（S4） | 没有mapping权限/字段ACL/事务授权epoch | D节新增精确grant与事务复核；默认零授予 |
| 凭据版本 | BoundSecretAsync、密文Secret、SecretVersion及连接守卫（S2） | Mapping不能取明文或旧私有runtime | Connections内部用当前凭据；轮换使审批失效 |
| 源验证 | IPgSourceAdapter只有ProbeAsync/DiscoverAsync且明确不读业务行（S5） | Executability/Identity/Reconciliation运行接口不存在 | 新有界验证端口，仅服务端登记计划，禁止任意SQL |
| 发布与审计 | G3 Publishing、Governance共享物理事务writer（S3/6） | Mapping实体/API/Outbox/action不存在 | Connections拥有映射表/Outbox，Governance独占审计 |
| 工程准入 | workflow产品Task白名单、execution_preflight无本Task（S10） | BLOCKED_FOR_PRODUCT_EXECUTION | F节最小适配后再运行，不借G3的M3参数 |

连接器判断：PG可消费目录，完整映射须新增验证端口；Web现有GET/API_KEY_REF目录可读，但属于API语义，不是SQL源，Mapping执行未验证；Doris/Oracle元数据可消费，映射验证/方言执行未验证，不能认定“最小适配即等价”；TDengine首切片请求422 mapping_source_unsupported，不恢复其调查/资源。

**推荐支持集合**：单连接、完整固定org/sites、最多2个显式登记PG TABLE，每表≤12个选定字段、≤100条能完整读取的合成行；Entity/Property及同源一对多/多对多Relation（显式连接键，输出≤100行，fanout≤10）。类型仅int2/int4/int8、有限numeric(p,s)且p≤28、text/varchar、boolean、date、timestamptz（≤微秒）、jsonb注册顶层标量提取。无时区timestamp仅明确登记时区且无DST歧义才接受。VIEW/函数/数组/UDT/自由表达式/跨源关系拒绝，不将未支持项标PASS。

拟新增 Connections 内部 IMappingSourceValidator.ValidateAsync(actor, sessionRef, immutablePlan, expectedVersions, cancellation)。服务端从固定引用编译SCHEMA/IDENTITY/TIME_UNIT/EXECUTABILITY/RECONCILIATION计划；READ ONLY、REPEATABLE READ源事务，参数化值、受控精确对象及标识符引用，不接受SQL文本。每次≤5s、完整结果≤100行/1MiB、最多2对象；总评估≤30s；每主体1、每连接2个在途任务。实际count及LIMIT 101探测均受预算，超限/取消/零样本不足以证明时INDETERMINATE，不把截断样本当全局唯一证明。源原始行只在内存，持久化计划hash、结果hash、计数、观察时间/源事务快照标识与诊断。独立C#参考变换与执行输出对账；这不是M4业务Query/SourceReadReceipt API。

**待决 A**：批准PG限定集合、有界业务行验证、M2 PARTIAL限定入场。**实施验证**：真实完整小数据集、101行/超时/取消/字段越权/自由SQL/不支持源负例；其他源执行与五源整体仍NOT_RUN。

## B｜RM-02：严格PUBLISH / ROLLBACK及恢复合同

### B1 精确差异

旧MappingProposalView（S7）strict Schema仅有draftId/draftRevision/scope/sourceConnectionId/connectionRevision/sourceCatalogSnapshotId/sourceCatalogFingerprint/ontologyReleaseId/mappingHash/validationHash/impactHash/submittedBy/submittedAtUtc/expiresAtUtc/status/decision，没有kind/回滚目标/secretVersion/adapterVersion。本轮提出独立g4.mapping.v1替代，历史Schema只读。

| 原字段/路由 | 精确新定义及理由 |
|---|---|
| draftId/draftRevision | 仅PUBLISH保留原名；新增mappingId永久身份（1 mapping对应1 draft）；ROLLBACK禁止两draft字段 |
| sourceConnectionId/connectionRevision/sourceCatalogSnapshotId/sourceCatalogFingerprint | 原名保留，移入binding；显式映射当前ConnectionId/ConfigRevision/SnapshotId/SchemaFingerprint |
| ontologyReleaseId/mappingHash/validationHash/impactHash | 移入binding；新增ontologyManifestHash/assessmentId，不重算G3旧manifest |
| 无kind/目标 | kind必填PUBLISH或ROLLBACK；后者必须targetReleaseId+manifestHash，固定历史制品 |
| status=PENDING | 保留wire PENDING（工作流REVIEWING）；APPROVED/REJECTED/EXPIRED/CANCELLED保留，新增STALE |
| decision | 保留decidedBy/decidedAtUtc/decision/reason，新增bindingHash |
| /mapping-proposals/{id}/rollback-proposal | 替换为统一POST /mappings/{id}/proposals的ROLLBACK分支；旧路由未实现，不留含糊父提案别名 |
| Release.active/activationRevision | 移至独立projection，不写入不可变manifest |
| 无active EMPTY/404 | 沿RM裁决统一404 mapping_active_not_found |

封闭模型：下述所有对象拒绝额外字段和重复JSON键，enum大小写严格；分支禁止字段必须省略，不能以null代替。ID为非空安全标识≤128字符；hash为64位小写hex，无sha256前缀，正式运行拒绝synthetic占位。Scope={organizationId,siteIds}，非空唯一完整sites。时间UTC固定7位小数Z；整数≤2^53−1。CommandContext={commandId,idempotencyKey,expectedRevision,reason}全部必填，reason非空≤512字符。错误先401/403，再400形状、422语义、409版本/期限/CAS；在已授权范围确认不存在才404。ProblemDetails沿既有code/traceId/correlationId，不泄SQL/Secret。

### B2 封闭请求/响应模型

ProposalCreate通用必填集合：schemaVersion、kind、scope、binding、expectedActive、expiresAtUtc、command，另加对应分支字段；全部非null，除明确说明者。schemaVersion=g4.mapping.v1；path mappingId必须与固定资源同属。

- PUBLISH：draftId、draftRevision≥1必填，锁定当前Draft修订与完整Assessment；targetReleaseId/manifestHash禁止。
- ROLLBACK：targetReleaseId、manifestHash必填，目标必须同mapping/完全相同scope、正式发布；draftId/draftRevision禁止。从旧Release原文加载映射，不要求最新Draft等于历史Draft。
- binding全部必填：sourceConnectionId、connectionRevision、configHash、sourceType、sourceCatalogSnapshotId、sourceCatalogFingerprint、ontologyReleaseId、ontologyManifestHash、mappingHash、validationHash、impactHash、assessmentId、adapterVersion、executorVersion、canonicalVersion、secretVersion、authorizationEpoch。版本整数≥1，首切片sourceType=POSTGRESQL；canonicalVersion=mapping-c14n-v1；adapter/executor只取服务器注册值。ROLLBACK的mappingHash/本体身份来自目标manifest，连接/目录/凭据/评估/impact来自当前兼容评估；不覆盖目标manifest内历史输入。
- expectedActive={releaseId,activationRevision}两项必填；首次仅(null,0)，已有active必须(非空ID,正数)，ID+单调revision同时比较防ABA。ROLLBACK必须已有active，target不得等当前active。
- expiresAtUtc>服务器当前时间且≤24h，并不得超过提交者授权租约；不能静默延长，超限422。创建command.expectedRevision=0，无If-Match（创建Proposal而非改Draft）；服务端加锁验证draftRevision。201、Location、ETag="proposal:1"，返回ProposalView。
- ProposalView必填：schemaVersion、proposalId、mappingId、proposalRevision、kind、scope、binding、expectedActive、submittedBy、submittedAtUtc、expiresAtUtc、status、decision、bindingHash、activation，加对应分支。只有decision/activation可null。revision初始1，决定/取消/激活递增。bindingHash覆盖提案不可变字段，排除status/decision/activation/proposalRevision/自身。过期/STALE可为GET投影，不写库；写命令实时核验。
- DecisionRequest={decision,bindingHash,command}；decision=APPROVE|REJECT；If-Match="proposal:n"须等command.expectedRevision，200更新ProposalView。提交者不可自批。decision读对象={decidedBy,decidedAtUtc,decision,reason,bindingHash}，reason来自command；PENDING必为null，APPROVED配APPROVE，REJECTED配REJECT，过期/STALE保留原决定或null。
- ActivationRequest={bindingHash,expectedActive,command}；If-Match同Proposal修订，expectedActive须等提案原值，不准临时改CAS基线。200 ActivationReceipt={activationId,mappingId,proposalId,kind,mappingReleaseId,manifestHash,previousReleaseId,activationRevision,auditId,outboxEventId,activatedAtUtc}，previousReleaseId仅首次可null。ROLLBACK返回旧releaseId。Proposal.status仍APPROVED、activation非null，禁止第二次激活。
- POST /mapping-proposals/{id}/cancel：{command}+If-Match，提交者可取消未激活PENDING/APPROVED，200 View；其他终态409。没有直接回滚/自动审批激活捷径。

幂等键唯一域=org+完整sites+mappingId+action+idempotencyKey；保存commandId/主体/canonical请求hash/原成功回执。当前授权通过后，同主体同payload重放原回执，不重访源、不重复审计；异主体/异payload/同key换commandId→409，相同commandId换key也409。不同命令重复决定/激活409。失败不存成功回执；并发同key由唯一约束和锁收敛一份成功，提交后断网同key可恢复。

### B3 GET、分页与历史恢复

全部GET无写副作用、Cache-Control:no-store；当前会话/scope/源与字段ACL先核验，ETag不授予权限。历史内容不能裁剪后仍声称原hash：完整视图无法授权就403；源不可用只允许有权的非敏感状态摘要、usable=false/UNKNOWN，不能返回无法核实可见性的历史字段。列表仅合法对象。

| 拟新增/api/v1读取端点 | 固定恢复内容 |
|---|---|
| /mappings?connectionId=&status=&cursor=&limit= | {items,nextCursor}；item={mappingId,scope,revision,status,activeReleaseId}，activeReleaseId可null |
| /mappings/{id}；/revisions/{revision} | 最新Draft+ETag，或固定不可变Revision；不能拿最新内容代旧修订 |
| /mappings/{id}/diff?fromRevision=&toRevision= | 两个固定修订hash/变化；新增/release-diff?fromReleaseId=&toReleaseId=供回滚比较当前active与目标 |
| /mappings/{id}/assessments?revision=；/mapping-assessments/{id} | 固定报告；ROLLBACK用targetReleaseId筛选，与revision互斥 |
| /mapping-proposals?status=PENDING；/mapping-proposals/{id} | 双分支固定ProposalView；mapping.read可读可见详情，跨用户审核队列需mapping.review |
| /mapping-releases?mappingId=；/mapping-releases/{id} | ReleaseView={manifest,manifestHash,readOnly:true,projection}；projection={active,activationRevision,usable,reasonCodes,observedAtUtc} |
| /mappings/{id}/active | {mappingId,mappingReleaseId,manifestHash,activationRevision,usable,reasonCodes}；无active404，不可用不等于无active |
| /mapping-jobs/{id} | {jobId,mappingId,revision,target,status,assessmentId,issueCodes,createdAtUtc,completedAtUtc}；assessmentId/完成时间可null；状态QUEUED/RUNNING/SUCCEEDED/FAILED/CANCELLED |

列表统一limit默认20/max50，终页nextCursor=null；签名游标绑定主体、scope、authorizationEpoch、端点、筛选、排序(createdAtUtc,id)、首屏截至水位和5分钟期限。keyset排除首屏后新增项；不保证状态跨页不变。过期/筛选冲突409 mapping_cursor_stale，撤权403；刷新从第一页。固定ID深链刷新只GET，不重复POST。

**RM-01保留**：Draft唯一DRAFT/NEEDS_REVIEW/VALIDATING/READY_FOR_PROPOSAL/BLOCKED。REVIEWING/APPROVED/REJECTED是Proposal工作流；ACTIVE_RELEASE是指针，不新增Draft枚举。

**待决 B**：批准新版本判别模型与路由差异。**实施验证**：oneOf/字段混用/重复键/null与省略、同mapping/scope/hash、过期/幂等/ABA/历史分页；设计正反例在附录，本轮不宣称产品Schema通过。

## C｜映射语义、七评估与不可变MappingRelease

**原合同**：G3身份/半开时序、StableMappingIdentity和七项真实PASS不变。**源码事实**：B0无Mapping实现，G3发布制品不能充当MappingRelease（S3/7）。

| 对象 | 唯一职责与关联 |
|---|---|
| Mapping/Draft | mappingId为scope内永久身份；最新编辑头保存CAS产生Revision；Draft状态为当前修订评估投影 |
| Revision | 不可变scope、本体/连接/快照身份、typed mapping内容与mappingHash |
| Assessment | 固定PUBLISH revision或ROLLBACK release，七阶段报告/证据/版本/预算/期限；运行过程为Job |
| Proposal | 固定目标、完整binding、assessment/impactHash、active基线、主体/权限epoch/期限；独立决定 |
| MappingRelease | 仅PUBLISH成功时插不可变canonical制品；不随轮换/回滚更改 |
| Active/Activation | 唯一(scope,mappingId)指针及单调revision；历史Activation保存本次审批和当前兼容binding |

### C1 Manifest、typed mapping与canonical

StableMappingIdentity保留完整org/sites、ontologyReleaseId、sourceConnectionId/connectionRevision、snapshotId/fingerprint、mappingHash/validationHash/adapterVersion，新增configHash/sourceType/ontologyManifestHash/executorVersion/canonicalVersion。审批另绑定secretVersion/impactHash/assessmentId/authority epoch/主体/期限。

Manifest封闭必填集合：schemaVersion、mappingReleaseId、mappingId、scope、originDraftId、originDraftRevision、binding、mapping、reviewReceipt、createdAtUtc。binding为B2原发布完整固定输入；reviewReceipt={proposalId,bindingHash,submittedBy,decidedBy,decidedAtUtc}，主体不同；无null。manifestHash存独立列，不自包含；无active/当前健康、凭据明文/session。回滚审批写Activation，不覆盖历史reviewReceipt。制品≤1MiB，超限422。

MappingDefinition={entities,properties,relations,identitySpecs,temporalSpecs,conversions,unitSpecs}，集合可空但entities必须非空，各集合id唯一，引用必须解析。封闭元素定义：

- Entity={id,entityClassIri,datasetRef,identitySpecId,temporalSpecId,scopeFields}；scopeFields={organization:fieldRef,site:fieldRef}。
- Property={id,entityBindingId,propertyIri,fieldRef,conversionId,unitSpecId,nullPolicy}；nullPolicy=KEEP_NULL|REJECT_NULL，conversionId可null；unitSpecId只有G3目标明确非物理量属性才可null，物理量必须绑定UnitSpec。
- Relation={id,fromBindingId,toBindingId,predicateIri,joinFieldPairs,cardinality,temporalJoinPolicy}；cardinality=ONE_TO_MANY|MANY_TO_MANY；temporalJoinPolicy=HALF_OPEN_OVERLAP；joinFieldPairs为有序{from:fieldRef,to:fieldRef}数组。
- Identity={id,organizationFieldRef,siteFieldRef,sourceNamespace,externalIdFieldRefs,validFromFieldRef,validToFieldRef}；复合外部键有序非空；后两字段可null，未知不等于无限。
- Temporal={id,eventTimeFieldRef,observedAtFieldRef,timezonePolicy,precision,validFromFieldRef,validToFieldRef}；四个时间fieldRef可null；timezonePolicy={kind:UTC|REGISTERED_ZONE,zoneId}，UTC时zoneId=null，否则登记IANA标识；precision=DAY|SECOND|MILLISECOND|MICROSECOND。
- Conversion={id,registeredId,version,parameters}，首期只登记identity、decimal-scale-exact、celsius-to-kelvin、json-top-level-scalar；parameters分别为{}、{scale}、{}、{key,valueType}，valueType=STRING|DECIMAL|BOOLEAN；无动态表达式。
- UnitSpec={id,sourceUnitIri,targetUnitIri,sourceUnitFieldRef,sourceUnitCode,unitRegistryVersion,evidenceKind}；全部必填非null，evidenceKind首切片仅SOURCE_FIELD。两个IRI必须来自绑定G3发布的已支持单位定义；sourceUnitCode经固定unitRegistryVersion精确映射源IRI，不猜大小写/别名。sourceUnitFieldRef是同dataset明确存在的单位代码列，必须在每条受控源行实际等于sourceUnitCode；未知/null/混合单位阻断。源单位证据列和注册版本纳入mappingHash/评估报告，UI需明确选单位证据列；只选转换函数不能证明单位。无源单位列的物理量首切片不支持，不接受自由文字或模型推断补证据。celsius-to-kelvin仅源Cel目标K且G3定义相符；identity仅源目标单位一致。
- datasetRef={snapshotId,schema,name,kind}（首切片kind=TABLE）；fieldRef={datasetRef,ordinal,name}。除明示可null外全部必填非null；IRI必须来自固定G3发布；未知语义不得编造。

mappingHash覆盖MappingDefinition；validationHash覆盖固定七阶段报告内容（schemaVersion/target/输入identity/评估器版本/证据hash/预算/实际开始结束时间/状态/issues，不含自身）；impactHash覆盖active基线、依赖集合版本、diff/结论。报告不引用将来的proposal/manifestHash，避免循环。源catalog沿原字节算法，不因新canonical重算旧fingerprint。

mapping-c14n-v1：UTF-8无BOM、无尾换行、无额外空白；对象键按UTF-8字节序；重复键/额外字段拒绝。Unicode保留精确标量，不做NFC/NFKC，拒绝孤立代理项；只转义双引号、反斜线和控制字符（控制字符小写四位Unicode escape），非ASCII和斜线不转义。IRI用现有登记ASCII URI表示，不静默改大小写/百分号。必填可空字段必须写null，分支禁止字段省略。整数不加号/前导零/负零；decimal用精确十进制字符串，无指数/加号/多余前导及尾随零，-0归0，另有单位/精度证据，不能转double。UTC时间固定7小数Z，日期YYYY-MM-DD，业务时间与observedAt分列。sites和各binding集合按唯一id排序，重复拒绝；externalIdFieldRefs/joinFieldPairs保留顺序。版本不随系统文化设置变化。

字节正反：对象键重排同hash；a=null与省略a不同且必填缺失拒绝；é与组合字符é不同hash；sites集合重排相同，复合外部键顺序交换不同。附录hash只用于设计样例，不是生产制品验收。

### C2 七类必要评估

| 类别 | 真实固定输入/判定 | 可实现性与缺口处理 |
|---|---|---|
| Schema | 原快照字节+当前真实目录/ACL、精确对象/字段/原生类型/能力版本、G3 IRI | 现目录可复用，Mapping核验新增；PARTIAL/未知阻断 |
| Identity | org/site/sourceNamespace/复合键/有效区间，完整小数据集重复和关系端点，G3规则 | 目录不能证明唯一；需新源执行；跨厂同号独立、不自动sameAs；重叠/未知端点INDETERMINATE |
| TimeUnit | 单位来源/G3发布单位、纯转换版本、时区/精度、业务与观察时间 | 未知不猜；不可逆/精度丢失FAIL；G5指标不支持 |
| Security | 当前session/grants/scope/字段/源ACL、只读/TLS/目标、secretVersion | 现连接守卫仅基础；新增细粒度授权；信息缺失不能PASS |
| Executability | 注册typed计划、adapter/executor版本、真实PG只读执行/预算/取消 | 新接口尚未实现；编译成功不代真实执行；NOT_RUN阻断 |
| Reconciliation | 同源事务完整小集、独立参考变换和实际计划输出的值/实体/关系计数 | 超限/零样本不足以证明时INDETERMINATE；不推断生产全量 |
| Impact | 固定active/目标，本体/连接/映射依赖索引版本与变化 | 新完整Mapping依赖索引；M4未开放可证明无本产品M4消费，未知消费者不可称无影响 |

评估wire状态PASS/FAIL/INDETERMINATE/NOT_RUN；UNKNOWN是输入知识状态，归INDETERMINATE。七项全PASS且版本一致才READY_FOR_PROPOSAL；高风险待决NEEDS_REVIEW、安全/版本不可恢复BLOCKED。不能靠人工勾选替代实证。

保存新修订、配置/凭据/权限变更使旧PUBLISH审批STALE；ROLLBACK对旧mapping作当前七项兼容评估，不要求当前Draft相等。可兼容轮换产生新的回滚提案，旧manifest历史版本不改；Active使用目标manifest与本次Activation.currentBinding联合核验，禁止拿历史secretVersion执行。源变化/停用后指针保留但usable=false/REVALIDATION_REQUIRED，历史只供当前有权审计。

远端源与平台PG不能跨库原子锁：不可变受审Assessment有效期不短于提案期限（必须由其输入与授权期限支持，否则创建拒绝）；另生成独立ActivationCheck证明，完成至提交≤30秒，激活前再次真实目录/源授权检查，平台提交锁版本；只证明最后观测窗口，不保证源未来不变。后续任何业务读取还须重新核验源/ACL，不能凭Active绕过漂移。

**待决 C**：批准typed内容/canonical/支持集合/七项拒绝。**实施验证**：字节golden、Unicode/null/decimal/顺序反例，真实身份/关系/转换/漂移、PG制品不可变、G3字节不变。

## D｜权限、异人审核与原子激活

**事实**：Governance writer使用SetDbConnection+UseTransaction，失败显式回滚；无mapping action。G3有短事务CAS/Outbox范式但实体属于G3。G4SessionAuthority读取服务器票据，不代表实时IdP权限同步（S4/6）。**原合同**要求CAS+Governance审计+Outbox同物理事务。

### D1 权限与事务参与

新permission：mapping.read/edit/validate/submit/review/approve/activate、mapping.source.validate。新审计action：mapping.create/update/validate.start/validate.finish/validate.cancel/proposal.create/proposal.cancel/decision/activate/rollback/grant.change。拒绝使用既有authorization.denied；固定资源ID与脱敏元数据，无源行/Secret/SQL日志。

默认角色存在不授予新权限。本机合成初始化显式grant：A编辑提交，B审核（A≠B），C激活；operator可获edit/validate/submit/activate，auditor可获read/review/approve，source.validate额外精确绑定连接/对象/字段/scope，connection.manage不等于业务读。服务端同时验证角色资格和grant；自批按subjectId拒绝，换session仍403。可由提交者激活，但审核必须异人，不强制三个人。

拟新增Governance拥有MappingAuthorizationGrants和MappingAuthorizationEpochs。Grant字段={subjectId,organizationId,siteIds,permission,connectionId,objectRefs,fieldRefs,expiresAtUtc,revokedAtUtc}；非源permission的connectionId=null、对象字段空数组；源许可精确非空；revokedAtUtc可null。组织级epoch单调递增，任何grant变更及组织/厂区/角色变更先增epoch。只申请本机受审CLI初始化/撤销，不新增通用IAM页面/API。

新增公共 IMappingAuthorizationAuthority.CaptureAsync 与 DemandInTransactionAsync(proof, DbConnection, DbTransaction)。前者固定服务器session/主体/权限epoch/租约；后者通过Governance自己的DbContext加入同物理事务，先按organizationId锁唯一组织epoch行，再按subject/sessionRef排序锁Session及所需grant，重读票据/grant/期限/完整scope/roles。Host解密票据解释principal；Governance独占授权表写。内部保存提交者/审核者会话与epoch证据，公开DTO不含session。激活时提交者、审核者、激活者均当前有效；注销/撤权/过期不能用旧Actor绕过，需新提案或重新审批。不存在epoch行以organizationId唯一锁创建，不能跳过。

PostgresTicketStore撤销/续更参与相同锁顺序，行更新与激活有可解释先后。外部IdP变更若未同步服务器票据/epoch不能声称即时撤权：首切片合成变更必须先撤销服务器session与grant并在同组织epoch事务中提交，再改角色；生产IdP实时传播不在准入。激活先提交随后撤权，历史成功保留但下一次读/执行拒绝；撤权先提交必须阻断激活。

组织锁精确定义：MappingAuthorizationEpochs主键仅organizationId，每组织一行，任何site集合的映射激活/审批/grant创建修改撤销都锁同一行，宁可多失效、不出现{A}与{A,B}锁域分裂。grant匹配要求subject/organization/permission一致，完整mapping.siteIds为grant.siteIds子集；source.validate另要求所有对象/字段均为grant白名单子集，多条grant不拼凑跨厂范围。scope变更要重新评估，不缩小审批scope绕过撤权。组织epoch任一增加使该组织旧binding失效，包括无关site变更，这是首切片明确接受的保守代价。服务器会话撤销/续更先由可信票据解析组织、取得该组织锁再重读Session并操作；无法解析时失败关闭，不能退回旧无锁路径。测试必须覆盖grant{A,B}、mapping{A}，撤权与激活两种提交先后。

### D1.1 受审评估与激活新鲜证明分离

Assessment是不可变受审结论，validationHash包含其运行时间/证据，不能在人工审核后重跑覆盖。新增Connections拥有ActivationCheck，封闭字段={checkId,proposalId,bindingHash,assessmentId,checkedBinding,checkedAtUtc,expiresAtUtc,stages,semanticResultHash,evidenceHash}，全部必填非null；stages为七个{stage,status,issueCodes,evidenceHash}固定阶段，checkedBinding沿B2；expiresAtUtc≤checkedAtUtc+30秒且≤proposal.expiresAtUtc。semanticResultHash只覆盖所需映射语义不变量：完整限定集合身份唯一/有效区间/单位时区/转换/关系计数及预算/安全策略/影响基线判定，不包含观察时间、原始业务值和本次统计hash。其规则/版本冻结于executor；七项均须真实重验，不允许默认PASS。

激活复核允许“观察时间/源事务快照/具体业务数值变化，但语义不变量仍全部满足”；checkedBinding必须与受审binding逐字段相等（validationHash/assessmentId仍指原报告），本次运行证据只进入evidenceHash，不改审批hash。目录/config/secret/权限/本体/adapter/executor/impact基线任一变动、出现新问题、受审关系基数或语义不变量变化则409 STALE，必须新评估/新提案/异人审核。需改变允许变化集合也须改executor版本并重提案。原Assessment必须保存对应semanticResultHash，以供精确比较。

Activation保存checkId/evidenceHash，Release仍引用原受审validationHash；回滚同规则。最短反例：A提交后等待2分钟、B审核、C启动新ActivationCheck在30秒内提交应成功；重验产生新观察时间不会自行作废审批。反例为轮换secret或重验关系计数改变，必须拒绝旧批准。此补充避免把“30秒源新鲜度”错误变成人工审核的30秒期限。

ActivationCheck必须在网络检查结束后通过短事务持久化到Connections，checkId唯一，绑定proposalId/bindingHash且原字节不可变；过期/失败证明保留，不冒充PASS。新增GET /mapping-proposals/{id}/activation-checks（统一分页）及GET /mapping-activation-checks/{checkId}，按mapping.read与当前源字段权限读取，响应上述封闭对象；U11展示最后复核与失败原因，刷新不触发重跑。首次POST activate内部生成Check，失败返回ProblemDetails附已授权可见的checkId；未授权错误不附ID。重试只有原成功CommandReceipt才能免回源，否则重新生成Check；同提案并发Check可存在，最终CAS只允许一成功。F1的MappingRecords/MappingActivationService/MappingEndpoints及U11 releases组件负责本对象，不新增未列模块。

### D2 唯一推荐提交路径

1. 事务外：当前授权→固定Revision或旧Release→真实G3只读回验→针对受审Assessment的独立ActivationCheck七项复核PASS→PUBLISH构造并校验canonical bytes/hash；ROLLBACK只验旧字节，另建当前兼容证明。昂贵运算/源网络不持平台PG锁。
2. 短事务：ConnectionsDbContext拥有连接/事务；先Governance按固定organizationId/subject顺序授权参与锁，再Connection、永久mapping行、Proposal、命令键/目标Release。所有Mapping命令同序；锁等待≤2s，事务≤5s，超时退出，不长锁回源。
3. 复核：期限/三方session/epoch、连接revision/configHash/secretVersion、snapshot、adapter/executor、原assessmentHash不变及独立ActivationCheck的≤30秒证明。PUBLISH校验当前Draft仍绑定修订；ROLLBACK校验同mapping/scope的正式target/hash，不看最新Draft。过旧ActivationCheck退出重验该证明；不改原Assessment/Proposal。
4. CAS：同时比较active ID+revision，首次锁永久mapping后建Active，防无行竞争。PUBLISH插不可变Release(bytea+hash)，唯一releaseId且数据库约束拒绝UPDATE/DELETE；ROLLBACK不改Release。更新Active/插Activation.currentBinding；调用Governance writer；Connections插MappingOutbox和成功CommandReceipt，所有SaveChanges共享连接事务，任一失败全回滚。
5. Commit成功才返回；提交结果未知以同key恢复。Job复用持久lease/fencing模式扩展Connections，不复制Agents Run框架；旧fence不得写完成。
6. Outbox至少一次，eventId唯一、消费者Receipt去重；仅含mappingId/releaseId/activationRevision/manifestHash。乱序投影仅接受更大revision；查询一次从PG权威Active固定版本，不能以通知先后决定事实；后台投递故障不逆转已提交Active。

MappingRelease全部字节存PG，不引入Mapping对象存储/跨PG原子承诺/孤儿清理。G3原RustFS/Fuseki仅只读验证；本任务创建G3合成前置发布仅属于获批后测试前置，不由Mapping自动创建概念、SourceBundle/dataTurtle/正式图/Manifest/Run。将来改存对象存储须另批预构建、回读、失败孤儿与恢复合同。

必须验证：自批/换session自批、B撤权/过期、A注销、组织厂区/字段撤权、凭据轮换、同键异体、ABA、双激活竞争、审计/Outbox失败、Commit丢响应、旧fence及Outbox重复乱序、源失联。不能用UI禁用或mock替代后端/真实PG故障。

**待决 D**：批准模块所有权、专用权限/grant/epoch、事务参与接口/迁移。**实施验证**：双主体OIDC、同PG多DbContext故障、撤权与提交两种线性先后，成功审计恰一份。

## E｜页面闭环、AI OFF与M4界线

**事实**：B0已有连接/目录及G3页面，Mapping页面/端点不存在（S1/8）。**原合同**：U07/U09/U10/U11恢复、AI OFF及Next/shadcn/Base UI体系，不引入框架。

| 页面动作 | /api/v1 API（注明EXISTING，其余PROPOSED） | 对象/权限/恢复 |
|---|---|---|
| U07选连接/快照/本体 | EXISTING /connections、/connections/{id}/catalogs、/catalogs/{snapshotId}；G3 GET /releases/{id} | connection.read/schema.read；固定ID/hash，STALE不可提交，403无泄露 |
| 创建/编辑/刷新 | POST /mappings；PATCH /mappings/{id}；GET最新/固定revision/diff | mapping.edit；409保留未保存内容，读新版本比较 |
| 人工/规则候选 | POST /mappings/{id}/suggestions | {mode:OFF,command}，返回{revision,candidates,issueCodes}；接受后显式PATCH，不等于批准 |
| U09验证/取消/恢复 | POST /mappings/{id}/validate；GET /mapping-jobs/{id}；POST /mapping-jobs/{id}/cancel；GET assessment | validate+source.validate，202 Job；七项缺证据NOT_RUN，问题绑定bindingId/fieldRef |
| U10提交/异人审核 | POST proposals；GET队列/详情/固定目标/assessment/diff；POST decisions/cancel | submit/review/approve；不取最新Draft代旧审核内容；过期/409新提案 |
| U11激活 | POST activate；GET proposal/active | activate；失败旧active不变，丢响应同key，刷新只GET |
| U11历史/回滚 | GET releases/release-diff；validate ROLLBACK→新Proposal→异人审批→activate | 旧target/hash固定；显示历史与当前兼容binding差异，无active404 |

DraftCreate={scope,ontologyReleaseId,ontologyManifestHash,sourceConnectionId,sourceCatalogSnapshotId,mapping,command}；expectedRevision=0。DraftPatch={mapping,command}+If-Match="mapping:n"。修改源/本体需新mapping，禁止暗换长期身份。DraftView={schemaVersion,mappingId,draftId,scope,ontologyReleaseId,ontologyManifestHash,sourceConnectionId,sourceCatalogSnapshotId,revision,mappingHash,mapping,status,updatedAtUtc}全必填非null。RevisionView同保存内容，status固定保存时DRAFT，当前评估另读，不回填最新hash。

ValidateRequest={target,command}；target判别PUBLISH:{kind,draftRevision}或ROLLBACK:{kind,targetReleaseId,manifestHash}。If-Match核最新mapping revision，ROLLBACK该值只作调度CAS，不要求Draft内容等目标。Job独立revision初始1、状态转移递增，取消{command}+If-Match="job:n"，仅原提交者且仍具mapping.validate。建议/验证command.expectedRevision与If-Match一致；建议不自动写Draft。候选只允许固定字段/IRI、证据等级METADATA/TERM/USER_ASSERTION/NO_EVIDENCE；无实样仅CANDIDATE_ONLY，高风险不能批量忽略。

UI路由：/data/mappings、/data/mappings/new、/data/mappings/[id]、/data/mappings/[id]/assessments/[assessmentId]、/data/mapping-proposals、/data/mapping-proposals/[id]、/data/mapping-releases/[id]。URL只含ID/修订，不含Secret/session。撤权清内存，未保存草稿仅当前session内存，不跨用户本地存储。Loading/Empty/Error/PermissionDenied/Conflict/Stale/Partial、键盘焦点/窄屏/明暗均真实覆盖。

AI OFF必须从手动/确定性候选到验证/发布/回滚全程可用；注释/来源文本是数据不是指令。无token不失败；不自动创建G3概念，不启LOCAL/外部模型/收费/Provider fallback/G6。M4多源查询/六态/MCP/Ontop/业务ReadReceipt均不申请；有界验证端口不得升级成任意业务查询。

**待决 E**：批准具体页面/API与读取恢复。**实施验证**：双主体浏览器完整纵向、深链刷新、冲突/撤权/取消、AI OFF无外联及G3/G2冻结消费者定向回归。

## F｜实施路径、资源、验收与停止

### F1 未来准确文件/Owner

Master唯一作者及Contracts/迁移/Host/生成链/工程配置Single Writer；一位非作者只读Reviewer。下列待批路径不是本轮修改许可；新增文件显式标注。第三方新依赖0，沿现有项目，不新建Mapping项目。

| Owner / 仓库真实根 | 拟修改或新增 |
|---|---|
| Contracts：backend/src/Contracts/OntologyPlatform.Contracts/ | 新增G4MappingModels.cs、G4MappingRules.cs、G4MappingServices.cs；旧G2/G3 wire不改 |
| Connections：backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/ | 修改Persistence/ConnectionsDbContext.cs；新增Persistence/MappingRecords.cs、Application/MappingApplicationService.cs、Application/MappingValidationService.cs、Application/MappingActivationService.cs、Application/MappingJobWorker.cs、Application/MappingOutboxDispatcher.cs、Abstractions/IMappingSourceValidator.cs、Adapters/PgMappingSourceValidator.cs、MappingCanonical.cs；新增Migrations/{EF生成时间戳}_MappingGovernance.cs及.Designer.cs，修改Migrations/ConnectionsDbContextModelSnapshot.cs |
| Governance：backend/src/Modules/Governance/OntologyPlatform.Modules.Governance/ | 修改TransactionalAuditWriter.cs/GovernanceDbContext.cs；新增MappingAuthorizationGrant.cs、MappingAuthorizationEpoch.cs、MappingAuthorizationParticipant.cs；新增Migrations/{EF生成时间戳}_MappingAuthorization.cs及.Designer.cs，修改Migrations/GovernanceDbContextModelSnapshot.cs |
| Host：backend/src/Hosts/OntologyPlatform.Api/ | 修改G4/G4Composition.cs、G4/G4Endpoints.cs、G4/G4OpenApi.cs、G4/G4ContractExport.cs、Security/PostgresTicketStore.cs；新增G4/MappingEndpoints.cs、G4/MappingSessionAuthority.cs；不改AppHost/全局CI |
| Publishing / Ontology | IReleaseCatalog及已发布读服务只读依赖；无Mapping直接写G3表，不改Manifest/SourceBundle/Run |
| 生成链 | 修改docs/contracts/g4-connections.openapi.json（沿现有g4文件名扩Mapping）、apps/web/scripts/openapi-types.mjs（如判别生成需要）、apps/web/scripts/generate-types.mjs；生成apps/web/src/lib/api/g4-generated.ts；C#→真实Host g4 OpenAPI→既有TS生成器，不手写第二套权威 |
| Web：apps/web/src/ | 新增features/mappings/api.ts、model.ts、editor.tsx、assessment.tsx、proposal.tsx、releases.tsx、mappings.css、mappings.test.ts（均同目录）；E节七个路由各page.tsx；修改features/connections/catalog.tsx增加固定快照入口；复用Shell/Tokens，不新框架/packages/ui |
| 测试 | 新增backend/tests/OntologyPlatform.G2ContractTests/G4MappingWireTests.cs、backend/tests/OntologyPlatform.ConnectionsTests/G4MappingTests.cs、backend/tests/OntologyPlatform.ConnectionsTests/G4MappingSourceTests.cs、backend/tests/OntologyPlatform.SecurityTests/G4MappingAuthorizationTests.cs |
| 工程消费者 | 修改scripts/maintenance/workflow.py、scripts/maintenance/workflow_environment.py、scripts/maintenance/execution_preflight.py、docs/development/verification-gates.json；新增scripts/maintenance/workflow_m3_mapping.py、scripts/maintenance/workflow-m3-mapping.mjs、scripts/tests/WorkflowMapping.Tests.py；复用workflow_execution/evidence及m2_build能力，不重构历史执行器；新增experiments/g4-m3-mapping-001/compose.yaml、fixture.sql、grant-fixture.py（均同目录） |
| 文档 | 本任务三份；后续获批才更新docs/contracts/g4-00-mapping.md记录裁决；历史input-v1.1保持只读 |

迁移时间戳只在实施EF生成时确定，不伪造已存在路径；所有新增表在对应模块schema。DAG：冻结B/C/D+非作者Review→持久化/权限/PG验证→Host/OpenAPI/TS→页面→任务消费者→最短真实与故障→按影响验收。C#中文XML/局部变量用途/成员空行专项审查不能被CS1591替代。

### F2 未来资源申请与当前资源登记

本轮未启动/prepare/restore/检查镜像缓存，不声称本机已有制品。未来最低组合：平台PG、源PG、Keycloak、API、Fuseki、RustFS共6容器，宿主Web/浏览器；接管故障临时第7 API。总容器内存≤8GiB，总CPU配额≤8，每容器PIDs≤256；宿主Web/浏览器≤4GiB。本任务数据≤3GiB、过程证据≤1GiB、工作目录/编译缓存≤6GiB，总增量磁盘≤10GiB。缺容量/制品立即停，不下载补齐，不复制旧KEEP私有runtime/PFX/卷。

来源（源码声明，不是当前可用性实测）：
- experiments/g4-m1-main-integration/compose.m1.yaml：linux/arm64 PG sha256:9a74990a5c776ff210361b67616b347750c66c36ea0dfbb4f575d19fcc3d8437；aspnet sha256:3a05e37c371f358d2b5cb9687d9992171b34b8c9146c283bef865bdbd2c53c55；Keycloak sha256:e1c1331f4a3e826016bdee2193335ed21685f0fd075c70bcb4d8fa7eeba9e1b4。
- experiments/g4-m1-main-integration/compose.g3.yaml：RustFS固定image，精确digest见后面的资源补充；Fuseki只用scripts/maintenance/canonical_fuseki.py及已校验共享镜像，platform+contextSha256+source/config/version内容键，不能随机重构。
- .NET/Web复用当前global.json/Directory.Packages.props/各lock/.node-version/pnpm-lock.yaml，不新增直接依赖；原任务的许可/风险接受不自动扩大至本Task。后续先核来源/许可/已知风险及本Task授权符合，无法确认即停对应制品。

缓存键绑定OS/arch/工具来源/SDK/lock，Web加生成OpenAPI，Fuseki沿canonical；HEAD/RunId只作归属，新Head不自动清缓存。新树路径敏感输出重新绑定；共享只读内容逐成员验证；私有Secret/唯一数据不跨任务复制。批准后才建立本任务新合成凭据、证书、G3前置发布与隔离端口/网络/卷，不借旧KEEP直接运行。

当前新建资源：TaskId=G4-M3-MAPPING-001，RunId=p0-contract-20261114；分支codex/g4-m3-mapping-001；托管树/Users/chasen/.codex/worktrees/g4-m3-mapping-001/ontology-platform，operationId=762e7b11-226a-45ca-9e7e-c686d57facc8。均KEEP：未集成且用户要求同树继续；解除条件为任务获准收尾且成果安全集成/归档。本轮无服务资源，无安全清理候选，不清旧KEEP。

### F3 原验收编号覆盖/延期（本轮产品全部NOT_RUN）

| 原ID | 后续首切片真实验收/延期依据 |
|---|---|
| S-23 | 删列/类型/权限漂移定位binding，未知阻断active可用性 |
| S-24/S-25 | G3固定ID/hash、SKOS无越权；AI OFF真实全链 |
| S-26 | AI ON延期，入口拒绝/不外传负例保留，不标AI产品PASS |
| S-27 | 注释prompt injection不能改Policy/执行代码 |
| S-28/S-29 | 跨厂同号独立、同厂重叠/未知端点/半开边界；M4 AMBIGUOUS响应延期 |
| S-30/S-31 | 未知单位/时区/precision阻断，PG精确时间转换；TD ns执行延期、不得降精度 |
| S-32 | 同PG一对多/多对多真实计数/fanout；跨源/M4结果延期 |
| S-33 | PG jsonb顶层missing/null/0/空串、转换失败；其他源延期 |
| S-34/S-35 | 真实hash，低风险规则批采纳，高风险待决/来源 |
| S-36/S-37 | 不写G3、OFF无token可用；ON费用/Provider运行延期，不fallback外传 |
| S-38/S-39 | impact/validation/schema/secret/权限变化旧approval失效 |
| S-40 | 服务端同主体403，换session也拒绝 |
| S-41 | 审批后失联/漂移激活失败，旧指针不变 |
| S-42 | 同PG audit/outbox/CAS分别故障回滚 |
| S-43 | 先验canonical不可变字节，重复ID异bytes拒绝 |
| S-44 | 竞争一成功一409，ABA，同key重试一份成功审计 |
| S-45 | 固定旧release回滚，当前七评估/异人/期限/权限/CAS；当前Draft不同仍可回滚 |
| S-46 | G3旧manifest/source原字节、旧Run定向兼容 |
| S-60/S-61 | U07/U09/U10/U11及连接入口成功/失败/刷新/无障碍，其他单元延期 |
| S-62/S-63/S-64 | Mac ARM64真实后验；Windows/Linux/x64 NOT_RUN；五源发布查询S-64延期 |

执行：格式/注释→相关单元/strict合同/TS生成→最短真实OIDC→PG→UI发布回滚→必要故障恢复→独立Review。新task adapter须实核audit/DI/消费者；execution_preflight精确阶段G4-M3-MAPPING-001未实现前BLOCKED，不借G3 M3。报告artifacts/workflow/G4-M3-MAPPING-001/{RunId}/；首次证据即test-review-evidence.ps1适用schema预检，schema2真实exitCode/timingStatus分列。产品gates=environment/contract/backend/web/interaction；工程engineering/preflight/新增mapping-task-admission，登记传递输入。

FRESH与REUSED分列，仅重新核验相同输入键的真实成功原件可复用，不能用旧摘要冒充本次exit0。七项新评估无旧运行证据。不重跑历史M1全链/无变化自然TTL，不因文档Head重构缓存。CI按需NOT_RUN。获批后长运行按规则做host_continuity及能源策略确认；本轮仅轻量文档。未来交付包依届时授权，本轮禁止ZIP。

**待决 F**：批准上述文件/迁移/权限/PG验证/预算/0新依赖/最小工程适配。**停止**：批准前不实施；需新依赖/载荷、无法隔离、M4能力/生产目标、七项缺实证或授权原子性无法证明时停对应链。

## 附录一｜固定来源

以下均B0=e07eab20feb3fdef9e24a20dec12d11b15bd7d46；路径相对仓库根，行号或符号用于git show恢复。拟新增路径不是事实证据。

| 来源 | 准确路径:行/符号 | 性质 |
|---|---|---|
| S1 | backend/src/Hosts/OntologyPlatform.Api/G4/G4Endpoints.cs:14–29，MapG4Endpoints | 当前连接/目录API，无Mapping |
| S2 | backend/src/Contracts/OntologyPlatform.Contracts/G4ConnectionModels.cs:373–500；backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/ConnectionApplicationService.Catalog.cs:86，CatalogAsync | 当前DTO/目录重验 |
| S3 | backend/src/Modules/Publishing/OntologyPlatform.Modules.Publishing/PublishingCatalog.cs:24/42；backend/src/Contracts/OntologyPlatform.Contracts/G2Services.cs:143；backend/src/Hosts/OntologyPlatform.Api/G2/PublishingEndpoints.cs:29 | 当前G3固定发布核验 |
| S4 | backend/src/Hosts/OntologyPlatform.Api/G4/G4Composition.cs:28/93；backend/src/Hosts/OntologyPlatform.Api/Security/PostgresTicketStore.cs:91/118 | 当前票据/注销，无新mapping权限 |
| S5 | backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Abstractions/IPgSourceAdapter.cs:6 | 仅探测/metadata，不读业务行 |
| S6 | backend/src/Modules/Governance/OntologyPlatform.Modules.Governance/TransactionalAuditWriter.cs:14/38；backend/src/Modules/Publishing/OntologyPlatform.Modules.Publishing/PublishingActivation.cs:142，CommitActivationAsync | 共享物理事务范式，无Mapping action |
| S7 | docs/evidence/G4-00-CONTRACT-001/input-v1.1/contracts/g4-proposed-wire-contract.schema.json:470/1267/1467/1618；docs/contracts/g4-00-mapping.md，RM-01/RM-02 | 历史PROPOSED严格Schema及缺口 |
| S8 | apps/web/src/features/connections/catalog.tsx；apps/web/src/features/publishing/review.tsx；apps/web/scripts/generate-types.mjs:5 | 当前页面/生成链，无Mapping页面 |
| S9 | docs/evidence/G4-00-CONTRACT-001/input-v1.1/docs/05-DATA-API-CONTRACT.md §1–7；同目录07-AI-NATIVE-ALIGNMENT.md §2–6与08-STAGES-ACCEPTANCE.md:83–114 | 历史语义/AI/验收，NOT_RUN不改 |
| S10 | scripts/maintenance/workflow.py:317–318；scripts/maintenance/execution_preflight.py:248；docs/development/verification-gates.json | 当前Task准入缺失 |
| S11 | docs/tasks/G4-M2-ORACLE-01.md；B0历史b202ec98/f6955e27/e07eab20 | Oracle已合入、TDengine等待 |
| S12 | docs/bootstrap/ontology-platform-codex-master-plan-bootstrap-v1.0.md:92–101；docs/planning/g4-implementation-plan.md；docs/contracts/g4-00-connections.md、g4-00-query.md、g4-00-ui.md（后三者同目录） | 架构及相邻边界 |


## 附录二｜PROPOSED JSON正反例（设计数据）

以下4个样例分别为两类POST请求及其201/GET读取，URL均为/api/v1/mappings/mapping-demo/proposals（GET按返回proposalId）。它们是B节字段集合的最小合法形状，不是产品运行结果。设计场景假定服务器时间08:00Z、A授权至08:20Z、全部引用存在且同scope、七评估PASS且新鲜。ROLLBACK场景假定当前Draft=9、旧Release来自Revision=1，当前兼容评估通过；不能因为9≠1拒绝回滚。

hash值是SHA256("design-…")的设计夹具摘要，不是完整实际制品散列/验收证据；真实产品必须由所引用原字节计算并核对，不能直接复制样例。bindingHash则按本节完整不可变提案示例JSON计算（UTF-8排序无空白），排除B2明确列出的可变字段。所有日期用于设计时间窗，不是本轮执行时间。

### PUBLISH请求
```json
{
  "schemaVersion": "g4.mapping.v1",
  "kind": "PUBLISH",
  "scope": {
    "organizationId": "ORG_DEMO",
    "siteIds": [
      "SITE_A"
    ]
  },
  "binding": {
    "sourceConnectionId": "conn-demo",
    "connectionRevision": 3,
    "configHash": "0020ade81e94863575012b822973b87664a541f6c5adf9d48b62cabf54a3bbdd",
    "sourceType": "POSTGRESQL",
    "sourceCatalogSnapshotId": "catalog-demo-3",
    "sourceCatalogFingerprint": "6213ef7a313963646b6509fa8cbe463a0af3797aceb57272c230929a549cb6de",
    "ontologyReleaseId": "ontology-demo-1",
    "ontologyManifestHash": "1746ac8a2bbeca5f14f7e63428cf77dd15d07bbb1a5add770ee982061424fa72",
    "mappingHash": "07294da37d1cf910ecf4098b03c88ada1509d63e6c24375e5e9a356327f02892",
    "validationHash": "6109100c1cae2fa7a8d7b24da5e9b85de9b497f188c4085d00ed0e32e0e49b78",
    "impactHash": "59eaa5343d4dc16d3c40dc4cc743b74668c126ad9a7804a7cf70489e06aed597",
    "assessmentId": "assessment-demo-publish",
    "adapterVersion": "pg-mapping-v1",
    "executorVersion": "mapping-validator-v1",
    "canonicalVersion": "mapping-c14n-v1",
    "secretVersion": 2,
    "authorizationEpoch": 7
  },
  "expectedActive": {
    "releaseId": null,
    "activationRevision": 0
  },
  "expiresAtUtc": "2026-11-14T08:15:00.0000000Z",
  "command": {
    "commandId": "cmd-p-1",
    "idempotencyKey": "idem-p-1",
    "expectedRevision": 0,
    "reason": "提交合成映射"
  },
  "draftId": "draft-demo",
  "draftRevision": 2
}
```

### PUBLISH创建响应/GET读取
```json
{
  "schemaVersion": "g4.mapping.v1",
  "kind": "PUBLISH",
  "scope": {
    "organizationId": "ORG_DEMO",
    "siteIds": [
      "SITE_A"
    ]
  },
  "binding": {
    "sourceConnectionId": "conn-demo",
    "connectionRevision": 3,
    "configHash": "0020ade81e94863575012b822973b87664a541f6c5adf9d48b62cabf54a3bbdd",
    "sourceType": "POSTGRESQL",
    "sourceCatalogSnapshotId": "catalog-demo-3",
    "sourceCatalogFingerprint": "6213ef7a313963646b6509fa8cbe463a0af3797aceb57272c230929a549cb6de",
    "ontologyReleaseId": "ontology-demo-1",
    "ontologyManifestHash": "1746ac8a2bbeca5f14f7e63428cf77dd15d07bbb1a5add770ee982061424fa72",
    "mappingHash": "07294da37d1cf910ecf4098b03c88ada1509d63e6c24375e5e9a356327f02892",
    "validationHash": "6109100c1cae2fa7a8d7b24da5e9b85de9b497f188c4085d00ed0e32e0e49b78",
    "impactHash": "59eaa5343d4dc16d3c40dc4cc743b74668c126ad9a7804a7cf70489e06aed597",
    "assessmentId": "assessment-demo-publish",
    "adapterVersion": "pg-mapping-v1",
    "executorVersion": "mapping-validator-v1",
    "canonicalVersion": "mapping-c14n-v1",
    "secretVersion": 2,
    "authorizationEpoch": 7
  },
  "expectedActive": {
    "releaseId": null,
    "activationRevision": 0
  },
  "expiresAtUtc": "2026-11-14T08:15:00.0000000Z",
  "draftId": "draft-demo",
  "draftRevision": 2,
  "proposalId": "proposal-demo-p",
  "mappingId": "mapping-demo",
  "submittedBy": "subject-A",
  "submittedAtUtc": "2026-11-14T08:00:00.0000000Z",
  "bindingHash": "aa86df96ef9bd4d7e18c988957390916bad6fa40cf049b31549a4e3ec2e31749",
  "proposalRevision": 1,
  "status": "PENDING",
  "decision": null,
  "activation": null
}
```

### ROLLBACK请求
```json
{
  "schemaVersion": "g4.mapping.v1",
  "kind": "ROLLBACK",
  "scope": {
    "organizationId": "ORG_DEMO",
    "siteIds": [
      "SITE_A"
    ]
  },
  "binding": {
    "sourceConnectionId": "conn-demo",
    "connectionRevision": 3,
    "configHash": "0020ade81e94863575012b822973b87664a541f6c5adf9d48b62cabf54a3bbdd",
    "sourceType": "POSTGRESQL",
    "sourceCatalogSnapshotId": "catalog-demo-3",
    "sourceCatalogFingerprint": "6213ef7a313963646b6509fa8cbe463a0af3797aceb57272c230929a549cb6de",
    "ontologyReleaseId": "ontology-demo-1",
    "ontologyManifestHash": "1746ac8a2bbeca5f14f7e63428cf77dd15d07bbb1a5add770ee982061424fa72",
    "mappingHash": "07294da37d1cf910ecf4098b03c88ada1509d63e6c24375e5e9a356327f02892",
    "validationHash": "93683f0a3e2cff6671f5416e32d13a44af0c1b18bef6003cb9fa162ce6e44b63",
    "impactHash": "6b5607f5fcddf89db2079540bbbf13116bc3762907bb7a8300fcf72f4d539d5a",
    "assessmentId": "assessment-demo-rollback",
    "adapterVersion": "pg-mapping-v1",
    "executorVersion": "mapping-validator-v1",
    "canonicalVersion": "mapping-c14n-v1",
    "secretVersion": 2,
    "authorizationEpoch": 7
  },
  "expectedActive": {
    "releaseId": "release-demo-current",
    "activationRevision": 4
  },
  "expiresAtUtc": "2026-11-14T08:15:00.0000000Z",
  "command": {
    "commandId": "cmd-r-1",
    "idempotencyKey": "idem-r-1",
    "expectedRevision": 0,
    "reason": "恢复固定历史映射"
  },
  "targetReleaseId": "release-demo-old",
  "manifestHash": "d82120eebccad8745dfc7cce5a3a09e82b429305a85739da26a1f2cf8c3fdfaf"
}
```

### ROLLBACK创建响应/GET读取
```json
{
  "schemaVersion": "g4.mapping.v1",
  "kind": "ROLLBACK",
  "scope": {
    "organizationId": "ORG_DEMO",
    "siteIds": [
      "SITE_A"
    ]
  },
  "binding": {
    "sourceConnectionId": "conn-demo",
    "connectionRevision": 3,
    "configHash": "0020ade81e94863575012b822973b87664a541f6c5adf9d48b62cabf54a3bbdd",
    "sourceType": "POSTGRESQL",
    "sourceCatalogSnapshotId": "catalog-demo-3",
    "sourceCatalogFingerprint": "6213ef7a313963646b6509fa8cbe463a0af3797aceb57272c230929a549cb6de",
    "ontologyReleaseId": "ontology-demo-1",
    "ontologyManifestHash": "1746ac8a2bbeca5f14f7e63428cf77dd15d07bbb1a5add770ee982061424fa72",
    "mappingHash": "07294da37d1cf910ecf4098b03c88ada1509d63e6c24375e5e9a356327f02892",
    "validationHash": "93683f0a3e2cff6671f5416e32d13a44af0c1b18bef6003cb9fa162ce6e44b63",
    "impactHash": "6b5607f5fcddf89db2079540bbbf13116bc3762907bb7a8300fcf72f4d539d5a",
    "assessmentId": "assessment-demo-rollback",
    "adapterVersion": "pg-mapping-v1",
    "executorVersion": "mapping-validator-v1",
    "canonicalVersion": "mapping-c14n-v1",
    "secretVersion": 2,
    "authorizationEpoch": 7
  },
  "expectedActive": {
    "releaseId": "release-demo-current",
    "activationRevision": 4
  },
  "expiresAtUtc": "2026-11-14T08:15:00.0000000Z",
  "targetReleaseId": "release-demo-old",
  "manifestHash": "d82120eebccad8745dfc7cce5a3a09e82b429305a85739da26a1f2cf8c3fdfaf",
  "proposalId": "proposal-demo-r",
  "mappingId": "mapping-demo",
  "submittedBy": "subject-A",
  "submittedAtUtc": "2026-11-14T08:00:00.0000000Z",
  "bindingHash": "0ff7ac6d077ee643a96da16b07f158dde134acc2941c30e0768b064718ef2c2e",
  "proposalRevision": 1,
  "status": "PENDING",
  "decision": null,
  "activation": null
}
```


### 决定与激活最小命令

下例作用于PUBLISH提案：主体B用If-Match="proposal:1"决定；随后当前有权C用If-Match="proposal:2"激活。ROLLBACK同合同，不需要draft字段。这里只展示命令形状，未执行。
```json
{
  "decision": "APPROVE",
  "bindingHash": "aa86df96ef9bd4d7e18c988957390916bad6fa40cf049b31549a4e3ec2e31749",
  "command": {
    "commandId": "cmd-decide",
    "idempotencyKey": "idem-decide",
    "expectedRevision": 1,
    "reason": "异人确认固定输入"
  }
}
```
```json
{
  "bindingHash": "aa86df96ef9bd4d7e18c988957390916bad6fa40cf049b31549a4e3ec2e31749",
  "expectedActive": {
    "releaseId": null,
    "activationRevision": 0
  },
  "command": {
    "commandId": "cmd-activate",
    "idempotencyKey": "idem-activate",
    "expectedRevision": 2,
    "reason": "激活已批准固定提案"
  }
}
```


### 代表性负例（对上述样例单点变异）

每条是JSON可解析设计变异说明，不是产品已观察的HTTP结果。授权失败优先；以下HTTP假设调用者已通过基础身份/scope鉴权。
```json
[
  {
    "case": "missing-target",
    "base": "ROLLBACK",
    "operation": "remove",
    "path": "/targetReleaseId",
    "expectedHttp": 400,
    "code": "mapping_payload_invalid"
  },
  {
    "case": "wrong-hash",
    "base": "ROLLBACK",
    "operation": "replace",
    "path": "/manifestHash",
    "value": "b62afae84bd660439acfbe2809e8ff76c5205f489b7689437ceb7260d272b0ad",
    "expectedHttp": 409,
    "code": "mapping_target_mismatch"
  },
  {
    "case": "cross-scope",
    "base": "ROLLBACK",
    "operation": "replace",
    "path": "/scope/siteIds",
    "value": [
      "SITE_B"
    ],
    "expectedHttp": 403,
    "code": "mapping_scope_forbidden"
  },
  {
    "case": "mixed-branch",
    "base": "ROLLBACK",
    "operation": "add",
    "path": "/draftRevision",
    "value": 9,
    "expectedHttp": 400,
    "code": "mapping_payload_invalid"
  },
  {
    "case": "publish-with-target",
    "base": "PUBLISH",
    "operation": "add",
    "path": "/targetReleaseId",
    "value": "release-demo-old",
    "expectedHttp": 400,
    "code": "mapping_payload_invalid"
  },
  {
    "case": "expired",
    "base": "PUBLISH",
    "operation": "replace",
    "path": "/expiresAtUtc",
    "value": "2026-11-14T07:59:00.0000000Z",
    "expectedHttp": 409,
    "code": "mapping_approval_stale"
  },
  {
    "case": "active-conflict",
    "base": "ROLLBACK",
    "operation": "server-active-revision",
    "path": "/expectedActive/activationRevision",
    "value": 5,
    "expectedHttp": 409,
    "code": "mapping_active_conflict"
  },
  {
    "case": "nullable-target",
    "base": "ROLLBACK",
    "operation": "replace",
    "path": "/targetReleaseId",
    "value": null,
    "expectedHttp": 400,
    "code": "mapping_payload_invalid"
  },
  {
    "case": "unknown-field",
    "base": "PUBLISH",
    "operation": "add",
    "path": "/autoApprove",
    "value": true,
    "expectedHttp": 400,
    "code": "mapping_payload_invalid"
  },
  {
    "case": "same-subject",
    "base": "DECISION",
    "operation": "actor",
    "value": "subject-A",
    "expectedHttp": 403,
    "code": "mapping_self_approval_forbidden"
  },
  {
    "case": "schema-drift",
    "base": "ACTIVATE",
    "operation": "server-current-fingerprint",
    "value": "47ce1dcca57e39bc97f81c10db6ed414f33f721f68f8a6ae22188df97884684a",
    "expectedHttp": 409,
    "code": "mapping_approval_stale"
  },
  {
    "case": "stale-secret",
    "base": "ACTIVATE",
    "operation": "server-secretVersion",
    "value": 3,
    "expectedHttp": 409,
    "code": "mapping_approval_stale"
  },
  {
    "case": "key-different-payload",
    "base": "PUBLISH",
    "operation": "reuse-key-change-reason",
    "value": "另一意图",
    "expectedHttp": 409,
    "code": "mapping_command_conflict"
  }
]
```


额外语义负例：同scope内换另一个mapping的target即409 mapping_target_mismatch；源ACL撤销403且不返回目标内容；无active的回滚404；审批后到期409；注册版本未知/七项含NOT_RUN为422 mapping_assessment_incomplete；当前Draft修改只使PUBLISH失效、不使ROLLBACK自动失效。过期创建统一409 mapping_approval_stale；超过24h或提交者租约则422 mapping_expiry_invalid。

### 资源精确补充

B0 experiments/g4-m1-main-integration/compose.g3.yaml:200 固定RustFS为 rustfs/rustfs@sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b。该文件:171是历史Fuseki本地imageId，不直接作为本Task的可用性证明；必须由canonical内容键验证共享镜像。未启动/拉取/下载、未声明旧风险接受自动适用。

## 附录三｜独立Review与文档验证

非作者Reviewer=/root/mapping_p0_review，未写文件。首次审查提出P1评估新鲜度冲突、P1重叠scope撤权锁、P2源单位证据缺失；作者已修正为独立ActivationCheck、组织级epoch和SOURCE_FIELD UnitSpec。一次定向复核结论：可提交用户一次性准入裁决，三项全部关闭，无未解决实质问题；不授予实施权限。复核正文SHA256=4eb4944f3dcad64369ad4941a0b479573ae5295e855565752c0e9c82523083df（加入本收尾记录前的完整文件）。Reviewer独立核过7个JSON可解析、两份bindingHash、git diff-check exit0；其未独立查看作者静态检查失败原件，未冒充通过。产品/完整Schema/CI/跨平台均NOT_RUN。首次合并写入被自动审批审查拒绝，原因是其认为授权索引追加可能越权；重新只读核验用户已批准附件第3节明确列入该路径后，分离操作重新审查获准。没有绕过拒绝、扩大产品授权或重写历史授权。


### 本轮检查回执与适用边界

| 命令/检查 | 真实结果 |
|---|---|
| git fetch origin；git rev-parse HEAD origin/main（开工） | fetch exit0；均为B0；初次默认沙箱fetch因FETCH_HEAD写权限失败，获准后正常fetch成功；未更新main |
| python3 -B /tmp/g4-m3-doc-check.py | exit0；3个授权路径、UTF-8/LF/围栏/相对链接、7个JSON、2对判别请求/读取、2个bindingHash、13个负例定义、A–F及授权只追加检查通过 |
| pwsh -NoProfile -File scripts/verify.ps1 | **exit1保留**：structured-syntax FAIL，YAML/TOML解析失败或项目解析器不可用；未运行SelfTest/Native/Tests |
| python3 -B -c（标准库模块可用性短诊断） | exit0；Python 3.13.17，tomllib_available=True、yaml_available=False；未安装/restore；无YAML/TOML变更，不以该失败否定本次已通过的专项Markdown/JSON检查，也不声称仓库静态总门禁PASS |
| git diff --check及最终已暂存diff-check | exit0（最终提交前再执行）；产品测试/真实服务/生成链/完整JSON Schema检查/CI/跨平台均NOT_RUN |

test-review-evidence.ps1已只读核对：它接收review evidence JSON，不接收Markdown设计文档。本轮唯一产物是Markdown，不伪造schema2产品报告供其通过，因此该证据JSON门禁不适用；未来真实证据仍必须早预检。JSON片段检查为本文件字段一致性检查，不等于正式OpenAPI/JSON Schema执行。独立Review结论是设计可供裁决，非产品PASS。

本轮所有失败保留：上述静态FAIL及初次沙箱fetch拒绝；一次命令编排语法错误发生于执行前、无文件写入；授权索引写入自动审查拒绝与依据附件重新核验获准见本附录前段。无下载、安装、服务、产品/DTO/数据库/工程脚本变更、ZIP或main更新。普通提交/push身份以本会话Git回执及本任务分支HEAD为准，不在文档中制造自引用提交SHA。

### 可复检的本轮专项检查源码

以下只读标准库检查源随本文保留；在仓库根提取此python围栏到临时目录运行，不安装工具，不属于产品实现或工程脚本修改。
```python
from pathlib import Path
import re,json,hashlib,subprocess
root=Path.cwd()
files=['docs/tasks/G4-M3-MAPPING-001.md','docs/evidence/G4-M3-MAPPING-001/contract-admission-request.md','docs/tasks/current-authorization.md']
for f in files:
 raw=(root/f).read_bytes()
 assert not raw.startswith(b'\xef\xbb\xbf') and b'\r' not in raw and raw.endswith(b'\n'),f
 s=raw.decode('utf-8')
 assert s.count(chr(96)*3)%2==0,f
 for target in re.findall(r'\[[^\]\n]+\]\(([^)\n]+)\)',s):
  if '://' not in target and not target.startswith('#'):
   assert (root/f).parent.joinpath(target.split('#')[0]).resolve().exists(),(f,target)
s=(root/files[1]).read_text()
blocks=re.findall(chr(96)*3+r'json\n(.*?)\n'+chr(96)*3,s,re.S)
def strict(pairs):
 d={}
 for k,v in pairs:
  assert k not in d,k
  d[k]=v
 return d
data=[json.loads(b,object_pairs_hook=strict) for b in blocks]
assert len(data)==7,len(data)
common={'schemaVersion','kind','scope','binding','expectedActive','expiresAtUtc','command'}
bind={'sourceConnectionId','connectionRevision','configHash','sourceType','sourceCatalogSnapshotId','sourceCatalogFingerprint','ontologyReleaseId','ontologyManifestHash','mappingHash','validationHash','impactHash','assessmentId','adapterVersion','executorVersion','canonicalVersion','secretVersion','authorizationEpoch'}
for request,view in [(data[0],data[1]),(data[2],data[3])]:
 branch={'draftId','draftRevision'} if request['kind']=='PUBLISH' else {'targetReleaseId','manifestHash'}
 assert set(request)==common|branch
 assert set(request['binding'])==bind
 for k,v in request['binding'].items():
  if k.endswith('Hash') or k=='sourceCatalogFingerprint':assert re.fullmatch('[a-f0-9]{64}',v),k
 expected={k:v for k,v in request.items() if k!='command'}
 expected.update(proposalId=view['proposalId'],mappingId=view['mappingId'],submittedBy=view['submittedBy'],submittedAtUtc=view['submittedAtUtc'])
 raw=json.dumps(expected,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
 assert hashlib.sha256(raw).hexdigest()==view['bindingHash']
 assert view['decision'] is None and view['activation'] is None and view['status']=='PENDING'
 assert set(view)==set(expected)|{'bindingHash','proposalRevision','status','decision','activation'}
assert data[4]['bindingHash']==data[5]['bindingHash']==data[1]['bindingHash']
assert len(data[6])==13
assert all('## '+x+'｜' in s for x in 'ABCDEF')
old=subprocess.check_output(['git','show','e07eab20feb3fdef9e24a20dec12d11b15bd7d46:docs/tasks/current-authorization.md'])
assert (root/files[2]).read_bytes().startswith(old)
changed=subprocess.check_output(['git','diff','--name-only','e07eab20feb3fdef9e24a20dec12d11b15bd7d46'],text=True).splitlines()
untracked=subprocess.check_output(['git','ls-files','--others','--exclude-standard'],text=True).splitlines()
assert set(changed+untracked)==set(files),(changed,untracked)
print('PASS: 3 authorized paths; UTF8/LF/fences/links; 7 JSON blocks; 2 discriminated request/view pairs; 2 binding hashes; 13 negative design cases; A-F; append-only authorization')
```
