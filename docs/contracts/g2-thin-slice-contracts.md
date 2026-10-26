# G2 Thin Slice 公共执行合同 V1

状态：DRAFT_FOR_INDEPENDENT_REVIEW。2026-10-26，Master单写；通过独立契约审查的具体提交才成为产品并行实现基线。本合同具体化G1规划中的唯一CommandContext/EvidenceRef/AssetVersionSnapshot/ExecutionRun，不创建第二套Result或万能共享实体。授权以G2 V1及本会话2026-10-26精确依赖批准为准；历史G1仍PARTIAL。

## 1. 模块、组合与唯一合同

- `backend/src/Contracts/OntologyPlatform.Contracts`：无外部包的跨模块只读DTO/明确用例接口，namespace `OntologyPlatform.Contracts`。只有本切片真实跨模块消费者需要的传输模型，不包含EF实体、DbContext、业务聚合、Repository/UoW。全部公共DTO由Master单写；不放ServiceDefaults/万能BuildingBlocks。
- `Modules/Ontology/OntologyPlatform.Modules.Ontology.Domain` 与 `.Ontology`：独立纯Domain、草稿/修订、验证、RDF适配及专属`ontology` schema。Domain不引用EF/HTTP/Jena/SDK。
- `Modules/Publishing/OntologyPlatform.Modules.Publishing.Domain` 与 `.Publishing`：提案/审批/不可变发布/active/Outbox，专属`publishing` schema。Domain同样纯净。
- `Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery`：唯一受控Gateway/Capability Registry/Evidence服务，不跨模块写表；正式snapshot由Publishing公开读取用例取得。
- `Modules/Agents/OntologyPlatform.Modules.Agents`：Provider/MAF/真实MCP工具适配、持久Run/事件/worker租约，专属`agents` schema。
- 原Governance拥有所有PG安全审计；新的同PG事务审计用例由Governance自己执行。宿主`Api/G2`只做安全边界、HTTP绑定和显式映射；业务不复制到REST/MCP。
- Master唯一修改项目注册/CPM/锁、共享合同、所有迁移、Host composition/AppHost/Design Tokens/OpenAPI/生成器。模块Owner提供模型/设计时工厂，Master生成迁移，不用EnsureCreated冒充迁移。

## 2. 身份、安全、错误和预算

`ActorContext(subjectId, organizationId, siteIds[], roles[], traceId, correlationId)`只由宿主从经过OIDC验证的Claims生成；客户端/模型/tool schema不能提交actor/组织授权范围。`ResourceScope(organizationId, siteIds[])`非空、Ordinal去重排序，siteIds1..16。访问草稿/发布/Run要求同组织且完整scope为可信sites子集，实体查询还按实体实际厂区过滤。未找到404、已知越界403，不返回跨scope实体候选。

共用具名AuthorizationPolicy：`semantic.read`允许现有viewer/operator/auditor；`ontology.edit`要求operator；`release.approve`要求auditor；`release.activate`要求operator。审查主体sub必须不同于提案提交者sub，即使双角色也不能自批。不新增角色体系/外部MCP bearer方案，不信任身份头；同源BFF Cookie复用服务器会话，写入REST/MCP POST均显式Antiforgery，校验Origin/Host不允许任意外部源。MCP本轮仅受控同源/本地已登录客户端，不公开匿名远程服务。

公共错误继续原生ProblemDetails，固定code/traceId/correlationId，准确401/403/404/409/413/422/429/500/503，不把源不可用变EMPTY。`CommandContext(commandId, idempotencyKey, expectedRevision, reason)`：ID为非空受限字符串1..64，reason1..500但不进普通日志；同scope/操作/幂等键唯一且绑定规范化完整payload hash，异payload重复409。GET无副作用；成功写入必须已提交审计。If-Match采用`"<revision>"`，与body expectedRevision同时存在且相同；缺失428，旧值409，不静默覆盖。

默认限额：每个源码UTF8≤256KiB、合计≤1MiB；RDF解析≤5000 triples，结构投影≤1000节点/2000边；SHACL只支持登记Core约束，单次5秒，最大并发2，禁止用户SHACL-SPARQL/custom target/JS/远程imports/任意查询。Gateway depth1..5、maxRows1..100、timeoutMs100..5000、最多3工具调用/Run；执行上下文总超时30秒，SSE一次连接最长25秒后可续订。超限明确422/429/PARTIAL或UNAVAILABLE，不悄悄截断为FOUND。取消传播到HTTP/PG/Jena；不重试非幂等业务写入。

## 3. 唯一DTO及源码/草稿

所有JSON camelCase、UTC RFC3339，ID字符串；稳定DTO位于唯一Contracts，未知资产版本用null/空数组，不用假v1。

- `SourceBundle(ontologyTurtle, shapesTurtle, vocabularyTurtle?, dataTurtle)`：明确UTF8源，PG保存原始字符串，SHA256按Encoding.UTF8完整字节；无修改导出完全一致。data只Synthetic，本轮不访问真实五源。
- `SourceHashes(ontologyHash, shapesHash, vocabularyHash?, dataHash, bundleHash)`：四项字节hash；bundleHash为各hash按字段顺序以LF拼接再SHA256，vocabulary absent用固定`absent`。不从TDB2回读重建权威源。
- `OntologyDraft(draftId, assetId, scope, baseReleaseId?, revision, etag, name, sources, hashes, ownerSubjectId, updatedAtUtc, projection)`。Create选择自身合法scope；从旧release创建新draft时继承assetId/scope。revision从1单调增，每次语义源保存CAS+审计；布局位置不算语义修改。
- `RdfTerm(kind, value, datatype?, language?)`：kind为iri/blank/literal；`RdfTriple(subject,predicate,object)`和`SemanticProjection(revision,hashes,triples[],nodes[],edges[],structuralEditAllowed,diagnostics[])`是标准RDF的读模型，绝不取代Turtle权威。
- `SemanticEdit(subjectIri, predicateIri, oldObject?, newObject?)`：仅服务器白名单RDF/OWL基本编辑。Class/subClassOf/object/datatype property/domain/range/label/comment/individual type与简单断言；全图未知/复杂公理或空白节点存在时先阻断结构编辑，源码仍完整保留可导出，源码修改须真实RIOT再保存。不得把投影重建为完整本体。
- 支持子集/未知公理/import必须明确显示。无解析/锁定的owl:imports仅保留声明但阻断发布；不联网抓取。复杂OWL源码可保留、查看、Diff，本轮不宣称完整推理/一致性证明；发布只支持已声明可验证子集，不能默默忽略未支持公理。
- `SemanticValidationReport(reportId,draftId,revision,hashes,kind,conforms,issues[],rawReportHash,validatedAtUtc,traceId)`。kind区分RDF_PARSE、SHACL_CORE、OWL_SUPPORT；issue含severity/focusNode/path/value/sourceShape/constraintComponent/message/sourceId。SHACL violations/error与unsupported公理/import阻断发布；OWL逻辑推理明确NOT_RUN，不混淆开放世界与SHACL约束。
- `DraftDiff(baseRevision,targetRevision,baseHashes,targetHashes,addedTriples[],removedTriples[],sourceDiff,unsupportedDiagnostics[])`：服务器固定两修订，原始源与图语义差异分别呈现；bnode不能用随机ID做虚假更改声明。

## 4. Jena工程方案与真实PoC

优先复用已批准Fuseki6.2.0同进程：`/validation`内存dataset、`/ontology`TDB2正式dataset；官方Assembler显式query/GSP/update/shacl endpoint。所有地址和graph IRI来自启动配置/服务器生成的ID，不接收客户端管理地址；管理端仅内部回环，REST/MCP不代理SPARQL/Update/管理API。

真实PoC已完成：既有镜像实测Apache Jena6.2.0；RIOT接收UTF8、内存图保留01 typed lexical、未知blank-node断言、SHACL正负例和focus/path/message、非法Turtle400。见本轮master/jena-shacl-poc-green.json（九项）。首轮客户端GET误发Content-Type导致415，红例完整保留。符合/不符合均HTTP200，真正判据`sh:conforms`；report用官方支持application/rdf+json映射标准RDF terms。PoC不是完整生产语义/性能/安全PASS。

暂存graph以随机ID独占、输入hash/revision关联，finally删除；每个操作受预算，不跨请求共享未授权图。内存丢失可从PG原始源码重建。Shapes先经RIOT解析并检查允许Core谓词/组件，再执行；拒绝SPARQL/JS/自定义target/递归不支持组件。标准Core清单在SEM代码/契约测试统一，首次只需NodeShape/PropertyShape、targetClass、path（单IRI）、minCount/maxCount/datatype/class/nodeKind/minInclusive/maxInclusive/in及标准message/severity/name/description，未支持不静默执行。

TDB2可能规范化typed literals，发布仅接受符合已声明规范词法子集的数据；部署前后按RDF term/计数/受控查询验证。字面量词法或图语义不能对账即失败，active不切换；复杂/blank公理未验真不可宣称可发布。原始源始终PG/RustFS保留；结构编辑新修订格式/注释可改变，但旧修订源码完整保留并显示Diff。禁止依靠unsupported TDB开关改变字面量策略。

Fuseki默认请求/解析日志可能含用户源码/查询，G2配置必须关闭这些原文出口，由.NET安全固定事件与Trace记录阶段/hash/状态，不记录Turtle/Shapes/Prompt/SQL/SPARQL正文。Alloy现有低基数规则不扩大。

## 5. 不可变发布、审批、激活与恢复

`ReleaseProposal(proposalId,draftId,draftRevision,hashes,scope,submittedBy,submittedAt,expiresAt,status,approval?)`绑定完整sourceBundleHash和验证报告。有效期24小时；提交必须当前精确revision验证成功。审核PENDING→APPROVED/REJECTED，任何修改使旧批准不能用于当前draft；发布前短事务复核当前draft revision/hash/合法范围/未过期/独立sub。审核决定是独立REST命令，SSE不审批。

`ReleaseManifest(schemaVersion=1,releaseId,assetId,scope,draftId,revision,hashes,ontologyGraphIri,dataGraphIri,importLocks[],snapshot,artifactObjects[],createdAtUtc)`；artifactObjects含固定objectKey/hash/size/contentType。SourceBundle四类源分别不可变对象，manifest也回读hash；key包含releaseId/contenthash，不覆盖不同字节。RustFS先验证已有对象完全相等再视为幂等。批准的基础ontology/Shacl/SKOS；mapping/metric/rule未实现的数组为空且明确absent。

`AssetVersionSnapshot(releaseId,ontologyHash,shapesHash,vocabularyHash?,dataHash,ontologyGraphIri,dataGraphIri,mappingVersions[],metricVersions[],ruleVersions[],capabilityVersions[])`；三能力本次真实schema hash版本登记，非假关联。新查询读取当前active快照；Run固定snapshot，回滚不改旧Run。

发布状态：PREPARING→ARTIFACTS_VERIFIED→GRAPH_DEPLOYED→GRAPH_VERIFIED→ACTIVE；失败FAILED_RETRYABLE或FAILED_FINAL，保留已准备制品/图供幂等恢复，不误报已激活。准备时持久proposal/release/idempotency key，外部逐点上传/GET hash/隔离命名图加载/SHACL与受控查询回验后才进入短PG激活事务。图IRI服务器按releaseId确定，与其他release完全隔离。active键为organization+assetId+完整scope，不用首厂替代。

**同数据库跨模块显式事务：** Publishing协调同一物理Npgsql连接及DbTransaction。Publishing上下文只写本模块active CAS/activation/idempotency/Outbox；Governance提供其自己拥有的enlisted审计写入器；Ontology提供其自己拥有的当前revision锁定读取用例。上下文显式UseTransaction，共享连接而不是只共享连接串。锁顺序draft→proposal→active，激活CAS包含activationRevision（每次激活/回滚递增，避免ABA）、expectedActiveReleaseId和scope；首次active也有唯一约束。任一步/审计/Outbox失败全回滚。commit后才返回X-Audit-Id/成功；不在事务后另WriteAsync假称原子。

`OutboxMessage(eventId,releaseId,activationRevision,eventType,payloadHash,createdAtUtc,attempts,nextAttemptAt,dispatchedAt?,lease/fencing)`与active/审计同事务；BackgroundService至少一次调和，消费者按eventId唯一去重。事件通知不承担版本正确性，查询直接固定PG active/manifest；缓存若有只按releaseId，不靠通知失效。POST-ACTIVATION实测对象/图仍可读；丢失时新查询UNAVAILABLE，告警/调和，不悄悄切别版。无生产GC策略，不删历史/被Run引用制品。

响应丢失以(scope,operation,idempotencyKey,payloadHash)读回真实activation；相同命令已提交返回相同release/activation，不重复审计/Outbox。并发不同内容仅一个CAS成功，另一409，旧active不指向半制品。回滚需针对目标完整旧manifest另行异人审核；重新验证旧制品/图，递增activationRevision，以相同CAS+审计+Outbox路径激活，不删除历史图/对象。

## 6. 正式查询、能力、合成来源与证据

`SemanticQueryPlan(capabilityId,capabilityVersion,assetId,releaseId?,entityType?,entityIri?,externalId?,siteId?,relationshipIris[],depth,maxRows,timeoutMs)`：能力只能describe_ontology、resolve_entity、traverse_relationships/trace_material；不接受SQL/SPARQL/任意URL。releaseId省略时一次读取active；显式历史版也重新授权，模型不得自己增加范围。非法schema/路径/预算422；同一应用Gateway供REST/MCP/MAF调用。

`SemanticQueryResult(status,data[],candidates[],evidence[],snapshot,subSources[],validTime?,observedAtUtc,traceId,limited,diagnostics[])`：FOUND有效非空；EMPTY所有必需源成功且无匹配；PARTIAL有可用子结果但预算截断/必需来源不全；UNAVAILABLE无可信结果且依赖失败；UNAUTHORIZED能力/范围拒绝；AMBIGUOUS多个实际可访问不同IRI候选，不按同号Join。HTTP鉴权依旧401/403，业务六态不替代传输安全。

`SemanticCapability(id,version,inputSchema,outputSchema,meaning,policy,executorId,budgets)`：稳定schema/hash版本；Schema Catalog返回真实OWL概念/属性/关系，不硬编码冶金类到通用执行器。受控读取正式graph，校验release manifest/source hash/actual named graph；缺失错版UNAVAILABLE。指定路径必须是正式ontology中声明objectProperty，过滤跨site关系和未授权节点。深度广度/时间/行数边界实测，不允许一对一假设。

`EvidenceRef(evidenceId,releaseId,scope,graphIri,subjectIri,predicateIri,objectTerm,sourceId,sourceRecordId,sourceObjectKey,contentHash,validFromUtc,validToUtc?,observedAtUtc,modelVersion,mappingVersion?,synthetic=true)`；hash验证引用源对象，scope由真实断言来源计算，证据endpoint再次授权+核验完整release/source。不将客户端给出的EvidenceRef直接视为可信，不让答案内引用绕过scope。模型版本与业务有效时间/采集时间分开。

样例至少五类Heat/CastingSequence/Slab/RollingEvent/Coil，实体IRI含org/site/source命名空间；同外部号两个site保留两个IRI。至少Slab→多个RollingEvent→多个Coil及反向谱系、缺关系/非法值负例。实体标Synthetic；属性/关系用标准RDF reification/PROV-O来源节点携带sourceId/sourceRecordId/valid/observed和适用模型版本，mapping absent明确，不虚构G4映射。所有返回关系/值能找到适用assertion provenance，缺证据不编造。

## 7. Run、MAF、MCP、SSE

`ExecutionRun(runId,ownerSubjectId,scope,snapshot,status,providerMode,createdAtUtc,updatedAtUtc,lastSeq,cancelRequested,leaseOwner?,leaseUntil?,fencingToken)`；status QUEUED/RUNNING/COMPLETED/FAILED/CANCELLED，终态唯一。Agent只选/解释正式schema受控工具；不开放发布/审批写工具。Provider默认disabled，允许明确标识deterministic harness真实驱动MAF工具路径，绝不称真实LLM。无已批模型/凭证则真实模型BLOCKED/NOT_VERIFIED，UI明确模型未配置；不能由环境里存在凭证推断授权。用户文字不进普通日志/标签，不能绕过工具预算/审批或scope。

`ExecutionEvent(runId,seq,eventId,eventType,schemaVersion=1,occurredAtUtc,snapshot,payload)`；eventId=`runId:seq`。payload为唯一有文档schema的对象，消息正文只持久Run事件，不作为普通遥测。事件类型run.started/tool.started/tool.completed/evidence.added/message.delta/run.completed/run.failed/run.cancelled；approval.required只在真实必要人工动作存在时发，不造审批步骤。

worker先以CAS租约/fencing取得Run，按row lock分配seq；run状态/唯一(runId,seq)/事件同Agents事务+Governance审计提交后才发送。恢复不重复副作用（本轮工具只读），失效fence不能提交；取消持久化、worker传播并唯一终态。限3次工具/30秒，无真实模型时按输入中的显式capability调用harness，不用预写答案；返回文本由实际Gateway结果/证据生成。

SSE用.NET10原生`ServerSentEvents`/`SseItem`，GET `/execution-runs/{id}/events`以PG分页为真相，通知仅唤醒；没有history/subscription间丢失窗口。Last-Event-ID必须匹配runId、非负seq且不超过已持久lastSeq，非法400/409；每轮读PG，seq去重，终态后关闭。断网仅断订阅，取消独立POST；慢客户端有界批次/连接超时后重放，不占用业务事务。每轮重新验证会话仍有效/范围未撤销，注销/30分钟到期不能无限订阅。事件保留本轮不GC，过期游标未来明确410和snapshot，不假称已实现自动保留。

MCP2.3.0直接包仅AspNetCore，显式注册三能力工具，禁止程序集任意发现；工具ClaimsPrincipal从服务器注入且不入schema，使用相同AuthorizationPolicy/Gateway/预算/Evidence。真实MCP initialize/tools/list/tools/call及越权/注入/超额测试；MCP transport SSE不冒充Run SSE。MAF1.26.0+Extensions.AI10.11.0真实恢复/编译/工具调用测试，其他MAF直接包未经登记不加。

## 8. API与Web冻结清单

统一`/api/v1`，公开路由以真实OpenAPI3.1为准，语义如下：

| 方法/路径 | 输入→输出/边界 |
|---|---|
| GET/POST /ontology-drafts | 列表/create name+scope+SourceBundle+CommandContext→OntologyDraft |
| GET/PUT /ontology-drafts/{id} | 源码及投影读取/CAS保存；PUT要求If-Match+CommandContext |
| POST /ontology-drafts/{id}/edits | SemanticEdit+CommandContext/If-Match→新修订与真实投影 |
| GET /ontology-drafts/{id}/diff?fromRevision= | 同scope两修订真实差异 |
| POST /ontology-drafts/{id}/validations | 固定revision/hashes→SemanticValidationReport，失败422或报告conforms=false，依赖503 |
| GET/POST /release-proposals | 可访问提案列表/精确草稿revision创建；回滚提案另带targetReleaseId |
| POST /approvals/{id}/decisions | approvalId=proposalId；decision approve/reject+CommandContext→真实决定 |
| GET /releases、GET /releases/{id} | 可访问正式manifest与active/历史状态 |
| POST /release-activations | proposalId+expectedActivationRevision+expectedActiveReleaseId+CommandContext→activation及manifest；回滚复用已批准目标提案 |
| GET /semantic/discover、GET /capabilities | 正式Schema Catalog/唯一能力registry |
| POST /semantic/queries | SemanticQueryPlan→同一SemanticQueryResult，CSRF |
| GET /evidence/{id} | 服务端查找/重新授权/真实源hash与断言→EvidenceRef及来源 |
| POST/GET /execution-runs、GET /execution-runs/{id} | create prompt+plan+CommandContext/list/snapshot（owner及scope） |
| GET /execution-runs/{id}/events | 原生text/event-stream持久事件和Last-Event-ID |
| POST /execution-runs/{id}/cancel | CSRF独立持久Command，不通过断流取消 |
| /mcp | 受保护SDK Streamable HTTP endpoint；同身份/CSRF/Origin/能力策略 |

OpenAPI文档加入所有新增API的session/CSRF/status/Schema，生成TS支持enum/union/null/inline对象/字典，不能退unknown掩盖实际合同。不存在的phase资产明确absent。严格schema拒绝不认识的命令字段或客户端actor/scope注入。G1原接口/状态保持实际回归。

Web真实SSR身份沿用G1；G2切片置于`src/features/{ontology,publishing,semantic,agent}`，路由/挂载在App Router与现有Shell。Master持有tokens/生成types/client基础协议；FE可改Shell导航和本切片样式，不能复制第二套认证或设计体系。Monaco0.57.0/Cytoscape3.34.4通过Client Component懒加载，本地worker不CDN，卸载dispose/destroy；移动Monaco官方不支持，390用同一真实revision/接口的textarea和表单fallback，明确限制。

Turtle/Shapes编辑dirty时标记旧投影，不能假称同步；保存/解析后图/表单与新revision/hash一致。409保留本地文本并允许重新加载/对比；图布局不推进revision。中文三栏/移动tabs，deep/light、1440/1280/390、键盘/ARIA、错误空态404/409/源503/延迟取消/模型未配置都基于真实API。SSE fetch流跨chunk/多行data解析、run/seq去重、快照和重连；React文本渲染不执行答案HTML。

## 9. 执行与审查门禁

S1语义/草稿+FE→S2审批/发布/故障/回滚→S3正式查询/MCP/MAF/SSE/FE。每一门均独立固定Commit+完整Diff+真实证据审查，Master集成main并push后继续，不等最后才首次合并。十类验收入口按授权§6，缺模型明确BLOCKED但继续工具路径；G1受锁安全/身份/审计/LGTM/CI回归不删减。

新增业务诊断使用固定phase/route/status/outcome/hash/version/Trace，Telemetry不记录用户源/Prompt/异常原文/连接串。低基数指标仅固定能力ID/结果类别，不加主体/厂区/实体/trace标签；PG审计独立持久。API/SHACL/SPARQL/发布/SSE性能真实样本记录，不编生产SLO。

最终仅唯一标准Review ZIP，Base精确6154ebb3703031a49cf0c555c9f0c3596e3b7726到最终已提交Head，全源码/diff/真实十类证据/同Head CI/独立审查/逐成员复验。总体状态按真实事实，保留G1跨平台/生产未运行，交付G2_THIN_SLICE_READY_FOR_REVIEW后停止，不进G3–G8。
