# G4-M4-QUERY-001｜唯一 A–F 查询规格与一次性实施申请

2026-11-14；修订 P0.1。唯一状态见[SDD任务卡](../../tasks/G4-M4-QUERY-001.md)。本文新增合同、接口、资源及实施文件均 **PROPOSED，待一次性裁决**；用户已批准的是本轮P0文档工作，不是产品实施。附件为已采用的任务依据，附件中的建议模型、运行与实施方案不自动成为已批准事实。

基线 `f0afb730ce92ecbd3a5947d9c6f58faedc8b2138` 已于本轮 fetch 核实。M3产品TestedCommit=`cfbdddc905e6e15546d7ec8f8c3aee144fe90e6c`；原包Head=`b9dd7eedb7980f8876d1c50c6b826ab096bacff9`，不改原件。M2 PARTIAL、TDengine WAIT_FOR_EXTERNAL_INPUT保留。

## A｜首切片、依赖和唯一执行链

### A1 源码见证与历史依据

下列源码引用均固定于上述完整Base；行号表示该提交，不能当未来实现位置。本文F1中的新增文件只是提案。

| 见证 | 固定路径与行号 | 当前事实与影响 |
|---|---|---|
| W1 | `backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/SemanticGateway.cs:39` | ExecuteAsync返回G2类型，走ReleaseCatalog/VerifiedReleaseSources/Jena；没有PG业务读取 |
| W2 | 同目录 `QueryRules.cs:24`、`CapabilityRegistry.cs:27` | 现有角色/scope守卫、预算及三项能力；新增G4必须沿此入口扩展，不另建Gateway |
| W3 | 同目录 `EvidenceService.cs:27` | 真实G3图证据服务；不能替代G4源行回执，也不能误称当前实现只是synthetic |
| W4 | `backend/src/Modules/Agents/OntologyPlatform.Modules.Agents/SemanticMcpTools.cs:28`、`:83`；`backend/src/Hosts/OntologyPlatform.Api/G2/McpEndpoints.cs:30` | 三工具白名单与semantic.read；G4类型、工具和业务权限未接入 |
| W5 | `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Application/MappingApplicationService.cs:543`、`:581`、`:620` | 历史Manifest/Active投影与Activation.BindingJson分离，当前可用性要重验连接/secret/catalog/epoch；没有业务Query跨模块端口 |
| W6 | 同目录 `MappingActivationService.cs:175`、`:210`、`:228` | activationRevision单调递增，BindingJson与Active、审计同事务；ABA不能仅比较releaseId |
| W7 | `backend/src/Contracts/OntologyPlatform.Contracts/G4MappingServices.cs:37`、`:48` | 已有服务器会话核验、授权Capture与同事务Demand；它们是mapping权限合同，不能默认授权query |
| W8 | `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/Adapters/PgMappingSourceValidator.cs:32`（ReadAsync）、`:278`（Scalar） | 评估器限定fixture、读全限定小集/COUNT和LIMIT101，原始行内存化；不是查询API；精度与类型支持需查询独立测试 |
| W9 | `backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/MappingCanonical.cs:18`；`MappingApplicationService.cs:1250` | mapping-c14n-v1与PG微秒归一规则存在；查询不能重算历史hash或默认字节等价 |
| W10 | `backend/src/Hosts/OntologyPlatform.Api/G4/G4ContractExport.cs:10` | 正式DTO/路由导出后生成TS；P0不运行该临时监听器 |
| W11 | `scripts/maintenance/workflow.py:317`、`workflow_web_cache.py:159`、`execution_preflight.py:248` | M3专属准入存在，M4缺失；当前M4产品gate BLOCKED，不能借M3 TaskId运行 |

历史约束：[RQ-01/02/03](../../contracts/g4-00-query.md)、[ADR-06](../../planning/g4-implementation-plan.md)、[05 §8](../G4-00-CONTRACT-001/input-v1.1/docs/05-DATA-API-CONTRACT.md)、[06](../G4-00-CONTRACT-001/input-v1.1/docs/06-SECURITY-AND-QUERY.md)、[08 S-47..59](../G4-00-CONTRACT-001/input-v1.1/docs/08-STAGES-ACCEPTANCE.md)与[原审查Schema](../G4-00-CONTRACT-001/g4-reviewed-design.schema.json)。历史NOT_IMPLEMENTED不覆盖已完成M1/M3事实。

### A2 申请范围

选择一条PG连接、一个已激活MappingRelease及一个正式OntologyRelease，AI OFF，贯通实体定位与精确属性读取。S1只开放 `g4_resolve_entity`，S3增加 `g4_read_observations`、`g4_traverse_relationships`，均登记在同一CapabilityRegistry；版本hash覆盖输入/输出/执行器/固定必需分支。entity、relationship、observation载荷均先完整冻结；ontology载荷冻结但本轮G4不开放，调用返回422 capability_not_supported，G2 describe_ontology照旧。不存在空壳ontology成功响应。

采用一个源内有界RelationBinding遍历，不申请跨源Join、任意SQL、Ontop、GraphRAG、外部模型或其他源。PARTIAL首先用同一PG真实101行/字节截断且已有可信前缀证明，另用已发布关系的两个独立表分支分别施加SELECT拒绝/超时证明局部失败；两个表不是两个独立源。每个查询分支用独立连接和READ ONLY REPEATABLE READ事务，串行共享同一绝对deadline，不重置5秒；每分支源IO期限=min(1000ms,剩余预算−500ms)，预留500ms用于平台提交/审计与回传前复核；剩余≤500ms不发起新分支，标INDETERMINATE并聚合已有可信前缀。预留不是额外期限，总deadline实际耗尽则503 query_timeout且不保存COMPLETED，不承诺总超时仍能返回PARTIAL；一事务的权限错误/statement timeout只终止该分支，不能将其abort事务继续用作成功分支。身份定位分支为必需且必须完整成功后才执行关系/观测分支；已有实体结果可构成后续分支失败时的可信前缀。QueryBindingReader只校验不可变manifest、当前平台绑定及当前query许可，不调用M3对全映射执行VerifyReadAccess/Usability作为整查询前置；逐分支当前源SELECT权限和catalog核验在PgQueryReader真实事务完成，故一个关系表拒绝可形成PARTIAL而非冒充全映射可用。**不申请第二PG连接**；独立源失败组合S-50仍NOT_RUN，不宣称五源联邦或完整M4全验收。若本次裁决要求跨源PARTIAL，则需重新明确第二源范围与预算，不能复制连接名冒充。

链路：HTTP/MCP → 同一SemanticGateway新增ExecuteG4Async → 同一Guard/Registry → Connections提供只读固定映射与typed PG执行端口 → Gateway六态/证据 → 当前授权事务复核 → Query结果存储 → UI/HTTP/MCP恢复。新增 `IG4QueryBindingReader.CaptureAsync/VerifyInTransactionAsync` 与 `IG4SourceQueryReader.ReadAsync`（名称PROPOSED）；Connections仅自己读表、实现源连接生命周期，SemanticQuery不直读写Connections表。Governance通过 `IG4QueryAuthorizationAuthority`提供capture/current/session/事务参与；不复用mapping.source.validate许可。共享物理PG事务由模块参与者显式加入，不增泛型Repository/UoW。

## B｜RQ-02 封闭wire合同

### B1 兼容、词法和精确差异

G2 REST `POST /api/v1/semantic/queries`、旧Run和旧三MCP工具字节保持。G4 REST为 `POST /api/v1/data/semantic-queries`。原Schema中SemanticQuery及G4QueryResultV1分支作为基底；只按本文列出的差异替换，不修改原输入。保留schemaVersion=`g4.query-result.v1`，这是尚未产品化的提案完善，不声称兼容原来源链子集解码器；能力版本必须变化。顶层仍精确12字段：schemaVersion/status/data/candidates/evidence/snapshot/subSources/validTime/observedAtUtc/traceId/limited/diagnostics。snapshot、candidate、evidence、subSource及diagnostic字段沿原Schema逐字段保留（准确字段名为sourceDatasetRef/sourceRecordRef/sourceReadReceiptId，不用05摘要别名）。新增绑定详情只放ReadReceipt及内部Query记录，不临时扩顶层。G4→G2转换本轮禁止。

全层封闭对象，除显式列出的可选请求filter外，表列字段全部必填；未知字段、重复键（包括嵌套与转义后重名）、非法UTF-8/孤立代理项、NaN/Infinity拒绝400 query_payload_invalid；不得先反序列化字典吞重复键。请求≤64KiB、JSON深度≤16；响应完整≤1MiB。枚举大小写敏感；标识1..128 ASCII登记字符，IRI≤2048且沿RQ-01 ASCII URI验证，不请求该URL。字符串值≤4096 UTF-8字节，label≤256；不trim或Unicode规范化业务值。缺字段与null不同，null只在明确位置合法。一般整数预算用JSON整数；Int64/decimal业务值与long版本计数用十进制字符串，不走JS number。未知enum/schemaVersion拒绝，禁止静默fallback。

请求仍为原SemanticQuery十字段；filters只允许siteId/entityExternalId/validFrom/validTo/entityIri。省略或null的前四filter表示未提供，不代表源null；entityIri若存在不可null且siteId必填。maxRows最低2（为保证AMBIGUOUS可返回至少两个候选，原最小1在G4中收紧），最大100。首期不接受cursor/offset/orderBy；返回按下文稳定序截断，limited=true不承诺下一页，客户端新增cursor字段400。时间窗两端要么都无要么均是UTC时刻且from<to，半开，上限31天；未知时区数据不能匹配该窗口并返回UNAVAILABLE/INDETERMINATE，不转UTC。

### B2 完整判别载荷（PROPOSED）

`data[]`严格oneOf以下四种字段集合，无互相可空的大DTO；公共kind/entityIri/evidenceIds保留，ontology.entityIri固定null。evidenceIds有序去重且至少1，必须解析到本响应获授权证据；无证据的业务值不输出。数组上限：data总100、每实体properties32、types16、evidence256、候选100；总字节上限更早生效。

| 类型 | 精确字段及类型 |
|---|---|
| entity | kind="entity", entityIri:IRI, evidenceIds:ID[], identity:Identity, typeIris:IRI[1..16], label:string或null, properties:Property[], validTime:Interval或null |
| relationship | kind="relationship", entityIri:IRI（source.entityIri）, evidenceIds:ID[], relationshipIri:IRI（发布对象属性）, source:Endpoint, target:Endpoint, cardinality:ONE_TO_ONE|ONE_TO_MANY|MANY_TO_ONE|MANY_TO_MANY, validTime:Interval或null |
| observation | kind="observation", entityIri:IRI, evidenceIds:ID[], identity:Identity, propertyIri:IRI, value:Value, unit:Unit或null, eventTime:Time或null, observedAtUtc:UTC, validTime:Interval或null |
| ontology（未开放） | kind="ontology", entityIri:null, evidenceIds:ID[], ontologyReleaseId:ID, classes:Class[], properties:OntologyProperty[]；本轮不返回，仅冻结形状 |
| Identity | organizationId:ID, siteId:ID, sourceNamespace:string, externalId:string（非空≤256）, effectiveTime:Interval或null；五者联合定位，不以externalId全局去重 |
| Endpoint | entityIri:IRI, identity:Identity, typeIris:IRI[1..16]；两端均当前有权、满足发布domain/range，否则不输出边 |
| Property | propertyIri:IRI, value:Value, unit:Unit或null, eventTime:Time或null, evidenceIds:ID[1..256] |
| Unit | unitSpecId:ID, unitIri:IRI, source:MAPPING_RELEASE|SOURCE_FIELD, sourceFieldRef:ID或null, evidenceIds:ID[1..256]；MAPPING_RELEASE时fieldRef=null，SOURCE_FIELD必须有登记fieldRef及证据；无单位时null，不能猜单位 |
| Interval | from:Time, to:Time或null；同时间种类/精度，半开from<to；to=null为未知结束；不能用观察时间填业务时间 |
| Time | kind:UTC|LOCAL|DATE, lexical:string, fractionalDigits:整数0..9；UTC为YYYY-MM-DDTHH:mm:ss[.固定digits]Z，LOCAL同式无Z/offset，DATE为YYYY-MM-DD且digits=0；实际公历/秒0..59校验，不接受闰秒，不猜本地时区 |
| Class | iri:IRI, label:string或null, evidenceIds:ID[1..256] |
| OntologyProperty | iri:IRI, kind:OBJECT|DATATYPE, domainIris:IRI[], rangeIris:IRI[], evidenceIds:ID[1..256]；未来开放须另定真实本体证据适配，不造PG行来源 |

Value严格判别：所有分支只具有`type`、`lexical`，decimal另有`precision`、`scale`，null另有`declaredType`（没有precision/scale）。type=string/boolean/int64/decimal/date/timestampUtc/timestampLocal/null。string lexical字符串保真可空串；boolean lexical只字符串"true"或"false"；int64 lexical匹配`0|-?[1-9][0-9]*`并在[-9223372036854775808,9223372036854775807]；decimal lexical非指数，precision=1..28、scale=0..precision，固定scale位小数、整数部分至少一位、去多余前导零、禁止负零，有效数位不超precision；date及时刻沿Time词法，PG时刻固定6位微秒；null lexical=null且declaredType是上述非null类型。单位只对已发布物理量属性合法，null值仍保留已知单位；未知nullable不得自动解释为允许null，缺映射字段拒绝，不用null补missing。不支持原始任意JSON值；M3注册JSON键提取只准产出上述标量。

**精度差异**：M3 decimal Scalar可去尾零、时间7位且末位0；M4按批准catalog scale重建精确decimal词法，PG timestamp输出6位并核ticks%10=0，不是截断非零第7位。PG numeric大于28位/特殊值/数组/domain未明确支持即拒绝，不经double。DATE不补午夜，LOCAL不补Z。完整模型允许9位时间为未来合同，PG本轮只接≤6位源精度且准确输出6位。未知时间eventTime=null，未知单位unit=null，但物理量单位缺失使该值不可作为可信结果，给INDETERMINATE诊断。

结果规范字节 `g4-query-c14n-v1`：UTF-8无BOM无换行，对象键按UTF-8字节序；JSON字符串使用最小转义（控制符\u00xx小写、引号/反斜线转义，不转义非ASCII或斜线），数字只允许上述安全结构整数。集合IRI/ID按UTF-8序去重；properties按propertyIri；候选按entityIri；data按kind、entityIri、propertyIri、eventTime.lexical、relationshipIri、target.entityIri升序（不适用项空串），同键多值按完整规范字节排序并仅去除字节相同项。时序业务排序先比较实际同类型时刻，不能混LOCAL/UTC。该规则不调用MappingCanonical猜测数组含义，不修改历史catalog/manifest hash。持久bytea保存原规范字节与SHA256，DB回读重新散列并以正式解码器读取；不使用jsonb回写作字节原件。

### B3 可解析正例与反例

下列是**载荷分支正例**，不是已运行结果；外壳使用原Schema的12字段及C节状态约束。`e-1`必须由测试构造真实同scope的证据/回执，示例自身不证明来源。P1实体、P2关系、P3观测均为后续开放分支；P4ontology仅形状正例，运行仍422。

```json
{"kind":"entity","entityIri":"urn:fixture:heat:1","evidenceIds":["e-1"],"identity":{"organizationId":"org-1","siteId":"site-1","sourceNamespace":"pg-fixture","externalId":"H1","effectiveTime":null},"typeIris":["urn:fixture:Heat"],"label":null,"properties":[{"propertyIri":"urn:fixture:mass","value":{"type":"decimal","lexical":"9007199254740993.20","precision":20,"scale":2},"unit":{"unitSpecId":"unit-1","unitIri":"urn:fixture:kg","source":"MAPPING_RELEASE","sourceFieldRef":null,"evidenceIds":["e-1"]},"eventTime":null,"evidenceIds":["e-1"]}],"validTime":null}
```

```json
{"kind":"relationship","entityIri":"urn:fixture:heat:1","evidenceIds":["e-1"],"relationshipIri":"urn:fixture:casts","source":{"entityIri":"urn:fixture:heat:1","identity":{"organizationId":"org-1","siteId":"site-1","sourceNamespace":"pg-fixture","externalId":"H1","effectiveTime":null},"typeIris":["urn:fixture:Heat"]},"target":{"entityIri":"urn:fixture:slab:1","identity":{"organizationId":"org-1","siteId":"site-1","sourceNamespace":"pg-fixture","externalId":"S1","effectiveTime":null},"typeIris":["urn:fixture:Slab"]},"cardinality":"ONE_TO_MANY","validTime":null}
```

```json
{"kind":"observation","entityIri":"urn:fixture:heat:1","evidenceIds":["e-1"],"identity":{"organizationId":"org-1","siteId":"site-1","sourceNamespace":"pg-fixture","externalId":"H1","effectiveTime":null},"propertyIri":"urn:fixture:sequence","value":{"type":"int64","lexical":"9223372036854775807"},"unit":null,"eventTime":{"kind":"UTC","lexical":"2026-11-14T01:02:03.123456Z","fractionalDigits":6},"observedAtUtc":"2026-11-14T01:02:04.000000Z","validTime":null}
```

```json
{"kind":"ontology","entityIri":null,"evidenceIds":["e-1"],"ontologyReleaseId":"ontology-1","classes":[{"iri":"urn:fixture:Heat","label":null,"evidenceIds":["e-1"]}],"properties":[]}
```

N1–N12是对以上正例的精确负例变换，expected outcome：

| ID | 变换 | 预期 |
|---|---|---|
| N1 | P1添加target或遗漏properties | 封闭判别失败；请求400，服务端输出校验失败503且不提交 |
| N2 | P1 decimal.lexical改JSON number 9007199254740993.20 | 拒绝浮点载荷，不尝试恢复 |
| N3 | P1 scale=3而lexical仍两位；或lexical="-0.00" | 词法/scale失败 |
| N4 | P3 lexical="9223372036854775808" | Int64越界失败 |
| N5 | P3 LOCAL时间强加Z，或第7位非零当作PG微秒 | 拒绝类型/精度失配，不舍入 |
| N6 | P1 missing属性以null Value替代 | 不等价；源缺字段REVALIDATION_REQUIRED，不保存FOUND |
| N7 | P2 target厂区无权 | 无边/端点泄露；按C授权优先级拒绝或有权部分PARTIAL |
| N8 | P2 entityIri与source不等 | 交叉不变量失败503，不提交 |
| N9 | P3 evidenceIds=["absent"] | 交叉引用失败503，不提交 |
| N10 | P1在kind后再加转义键"k\u0069nd" | 重复键400；Schema之前拒绝 |
| N11 | P4运行g4_describe_ontology | 422 capability_not_supported，无伪数据 |
| N12 | Unit.source=SOURCE_FIELD且sourceFieldRef=null | 判别失败；不得猜测单位 |

实现时以上与zero/空串/null/LOCAL日期/同微秒PG持久往返作为正式字节回归。当前只有文档轻量检查，DTO/OpenAPI/TS执行均NOT_RUN。

## C｜六态、证据与恢复

### C1 状态优先级和HTTP

顺序：认证→根scope/snapshot可见性→请求词法/能力→固定版本/选择资格→各分支授权/执行→当前授权与版本复核→审计和结果原子提交→响应前当前会话复核。未登录401，已登录完全无scope或snapshot权限403 ProblemDetails；不查询不可见snapshot、不返回连接/映射/目录ID。不存在/不属于主体的queryId统一404。合法主体的未知选择422，固定版本漂移409，越权优先403且不返候选。内部错误/审计失败503 ProblemDetails；错误只code/traceId/correlationId，无源异常。

| 条件（均已证明snapshot可见） | 业务态/HTTP | data / candidates / evidence |
|---|---|---|
| 当前可见候选≥2，候选定位完整可信 | AMBIGUOUS / 200 | data空；至少2候选及其证据；不自动首选 |
| 全部所需数据分支被拒且无可信行 | UNAUTHORIZED / 200 | data/candidates/evidence空；仅获准非敏感snapshot；子源ID不可见则整个请求403 |
| 无可信行且任一必需分支故障、未知、截断或定位不完整 | UNAVAILABLE / 200 | 无数据/候选；仅可见脱敏诊断/实际回执；不能凭零行EMPTY |
| 至少一可信行但有必需分支失败/拒绝/截断/证据降级 | PARTIAL / 200 | 只当前获准的可信行和可解引用证据；candidates空 |
| 全部必需分支成功完整且有可信行 | FOUND / 200 | data非空、candidates空、limited=false |
| 全部必需分支成功完整且明确零行 | EMPTY / 200 | data/candidates空、limited=false；保留真实零行readReceipt引用 |

同一connection可有多个subSources项，逐分支以sourceReadReceiptId区分并按该ID排序；失败未形成receipt时仅保留一个该connection的失败摘要，不把两个表说成两个独立源。子源必要性固定于capability版本，本轮所有注册分支必需；不运行后改为optional。权限+故障混合且无行为UNAVAILABLE，不假称全拒绝；有行则PARTIAL。可见候选已≥2但定位分支不完整时优先UNAVAILABLE（不能声称完整消歧）；截断候选可显示AMBIGUOUS且limited=true仅当已证明至少2且返回2..100个获准候选、未读取分支不会改变所示候选有效性。maxRows≥2避免违反原Schema。取消/RUNNING不是业务态；执行状态见C4。

RQ-01选择请求在HTTP必需附加 `X-Selection-Query-Id`（原AMBIGUOUS查询ID，≤128 ASCII；不新增请求body字段），无entityIri时禁止该header；存在entityIri却无该header为422 selection_context_required。服务端读取同主体/组织未到期原查询并核原status=AMBIGUOUS、候选集合和原完整Binding；选择请求除entityIri与必需siteId外的全部参数必须与原查询一致，siteId必须等于所选原候选厂区。原查询到期410，ID不存在/异主体404，不允许直接自带IRI绕过选择记录。选择后核当前主体、site/externalId、固定Ontology/Mapping/Activation版本与候选资格；仅原获准候选中的精确IRI可选，不把IRI作为URL访问。候选撤权403、已可见但版本过期409、不匹配422；响应均无候选列表。UI清除旧候选，不自动重试选择。

### C2 固定身份与证据链

Query固定内部Binding每连接精确字段：mappingId/mappingReleaseId/manifestHash/originalCatalogSnapshotId/originalCatalogFingerprint/activationId/activationRevision/currentCatalogSnapshotId/currentCatalogFingerprint/connectionId/connectionRevision/configHash/secretVersion/ontologyReleaseId/authorizationEpoch/capabilityVersion。long计数十进制字符串。历史manifest不可变；当前Activation绑定不能覆盖原catalog，旧secretVersion只作身份，不回读旧秘密执行。snapshot.sourceCatalogSnapshotIds列本次校验目录，evidence.sourceCatalogSnapshotId列原发布目录，ReadReceipt把二者连起来。

SourceReadReceipt为内部持久对象，业务HTTP/MCP不能直接获取其完整Binding。SourceReadReceipt封闭字段：schemaVersion（g4.read-receipt.v1）、receiptId、queryId、binding（上述Binding）、sourceDatasetRef、queryPlanHash、adapterVersion、scope、status（沿subSource六值）、rowCount（0..100）、limited、watermarkKind（沿原五值）、watermark（string或null，≤256）、sourceRecordRef（string或null）、precision（沿五值）、validTime（原UTC区间或null）、readStartedAtUtc、readCompletedAtUtc、resultHash（64小写hex或null）、traceId。每分支独立回执；成功/EMPTY必须真实读取结束、resultHash非null，未执行/失败可null且不能引用它证明业务值。resultHash只覆盖该分支已授权投影数据的规范字节（不含receipt、总结果或resultHash自身），避免循环散列；总结果hash另存Query记录。一个receipt可能覆盖多行，顶层sourceRecordRef仅确实单行可定位时有值；每行精度在evidence。receiptId随机不可猜，hash不自含，receiptHash存储外列。readReceipt→mappingRelease→原目录→当前目录→精确connection版本均可按当前权限解析；API从不返回configHash/secretVersion以外的凭证材料，内部Binding的这些身份字段也不进入普通业务响应。

未知SourceRecordRef必须null：有真实数据集证据可降DATASET，有可靠窗口可TIME_WINDOW；都不可核则UNKNOWN。UNKNOWN只允许脱敏诊断，不输出业务断言/候选，不让Agent当确定事实。DATASET/TIME_WINDOW数据可返回但整体PARTIAL并明确不能记录定位；所有输出evidenceIds及属性/单位/端点来源都必须闭合。不造graphIri、dataHash或sourceObjectKey。source-evidence读取只返回当前有权的证据与脱敏receipt投影，不自动重查源；显式重查是新Query、新权限和预算。

Active执行中切换（含A→B→A）在提交前比较activationId+revision，409 query_binding_stale，丢弃暂存业务值，不静默换版本。连接禁用、secret轮换、schema漂移同样阻止成功提交；真实catalog指纹要在源事务中核验，平台当前绑定随后短事务再核。既有已提交历史结果的Active改变不重写其绑定；历史读取当前主体/字段/源授权允许时读原结果，UI显示“历史版本”，不要求重新激活，不重新执行源SQL。授权撤销或当前源权限无法核实则403/503并清屏，不用历史grant兜底。不同分支/源水位独立，不承诺跨源原子快照；外源改变在事务可观察范围外无法彻底消除，只陈述read窗口，不声称读取未来状态。

### C3 持久化与删除

申请SemanticQuery独占schema `semantic_query`，新DbContext和迁移。Query记录输入hash、主体/组织/会话引用hash、完整固定Binding、幂等键、deadline、租约/fence、执行状态、取消标志、时间、结果hash/大小/到期时间；Run只保存本次G4 queryId和工具计数，不把G4塞旧G2结果列。旧Agents Run读路径继续当前鉴权，不能仅信创建时actor。

结果仅保存**本任务合成fixture**经授权投影的≤100条、≤1MiB规范字节；包括业务值/候选及必要证据，明确不同于M3“源行只在内存”。申请保存24小时，receipt和必要安全元数据7天；结果到期GET返回410 result_expired且不自动再执行，receipt不可恢复过期值。Query/Run历史安全元数据7天后删除，治理审计保留沿既有政策，审计无业务行/查询正文/秘密。总Query结果≤64MiB、receipt/元数据≤64MiB，满额拒绝429，不删旧任务或未到期结果抢空间。

bytea存AEAD加密规范结果（既有ASP.NET DataProtection，无新包；task专用purpose/key ring，key权限仅服务身份；多API受控共用本任务key ring，不拷旧runtime），外列SHA256为加密前规范字节，仅内部可见。读取核解密/hash/schema/交叉引用及当前权限。原行/SQL不进日志或ZIP，测试证据只用批准合成输出且公开前扫描。业务响应Cache-Control:no-store，浏览器不写localStorage/IndexedDB，不按旧用户恢复缓存。删除仅本任务到期记录，由模块后台worker按准确ID/到期条件删除密文与receipt，留下无值删除审计；审查KEEP解除前不得顺带清任务资源。真实业务数据持久化/导出不在本次申请内。

### C4 恢复API（PROPOSED）

POST严格SemanticQuery，必需Idempotency-Key（1..128 ASCII，组织+主体域）；幂等输入hash覆盖规范SemanticQuery及selectionQueryId（无选择为null），不忽略header差异；同键同请求返回同Query引用/原结果且重验当前权限，同键异payload409，保留24小时；不自动重执行失败/取消或超时query。响应完成时200 G4QueryResultV1及Location、X-Query-Id；尚在执行202 QueryView，不构造六态。GET `/api/v1/data/semantic-queries/{queryId}` 返回QueryView；GET `/{queryId}/result` 返回200原结果、202执行中、409取消/失败、410到期。POST `/{queryId}/cancel` 幂等，owner及当前query权限核验；取消成功或已取消均200 QueryView且executionStatus=CANCELLED；仅在取消事务提交后回应。已完成409，不销毁历史结果。GET `/api/v1/data/source-evidence/{id}` 按当前权限返回G4SourceEvidenceView（下文精确字段），不返回内部Binding全字段。

G4SourceEvidenceView封闭必填字段为 `schemaVersion`（g4.source-evidence.v1）、`evidence`（B1原Schema的G4SourceEvidenceRef完整对象）、`receipt`（ReceiptView）。ReceiptView封闭必填字段为receiptId、queryId、mappingReleaseId、manifestHash、originalCatalogSnapshotId、currentCatalogSnapshotId、connectionId、connectionRevision（十进制字符串）、activationId、activationRevision（十进制字符串）、queryPlanHash、adapterVersion、status、rowCount、limited、watermarkKind、watermark（string或null）、readStartedAtUtc、readCompletedAtUtc、resultHash（hex或null）、traceId。其余类型/枚举同C2；字段均受同Query/snapshot/source-evidence权限交集保护，不能证明这些身份可见就403，不做隐式字段删除或假ID。无configHash/secretVersion/session/授权grant、SQL、源定位秘密；sourceRecordRef仍只在evidence中按精度规则返回。

QueryView精确字段：queryId、executionStatus（RUNNING/COMPLETED/CANCELLED/FAILED）、createdAtUtc、completedAtUtc（或null）、expiresAtUtc、resultHash（或null，获准结果读取者才可见）、errorCode（或null固定码）。它不是第七业务态。结果URL由客户端从queryId构造，不接收任意URL。浏览器保存URL中的queryId，刷新只GET持久结果；重新执行需显式新幂等键。注销/主体变化/403立即清屏并使在途响应generation失效。MCP新增工具为 `g4_resolve_entity`、`g4_read_observations`、`g4_traverse_relationships`、`g4_query_result`；前三输入严格封闭 `{query:SemanticQuery,idempotencyKey:string,selectionQueryId:string|null}`，全部必填，能力名必须与query.capabilityId对应，capabilityVersion与Registry当前版本严格相等，key映射HTTP Idempotency-Key，selectionQueryId映射上述选择header。恢复工具输入严格 `{queryId:string}`，调用同一GET result服务且每次计入工具预算；本轮不新增MCP取消/证据工具，UI通过受控HTTP入口查看证据。MCP返回成功工具content精确为QueryView或G4QueryResultV1，二者由executionStatus/schemaVersion互斥判别，StructuredContent与text来自同一规范JSON。`g4_query_result`同一服务恢复；G4调用工具返回结构化QueryView或结果，工具错误严格isError=true，StructuredContent省略，Content恰一个TextContentBlock且Text固定为semantic_tool_rejected（不泄露权限/源细节）；不是成功六态，工具预算同Run≤3。

## D｜安全、执行和事务预算

保持depth≤5、maxRows≤100、timeoutMs≤5000（100起），Run≤30s/最多3工具调用。总deadline涵盖定位、catalog、源IO、持久与审计；超时后不得重新给审计5秒。每连接最多2在途、每主体1、全任务4，跨实例PG租约表原子计数，10秒租约/2秒心跳，最多到deadline；递增fence每次接管更新。过期worker不能提交；失联后取消源且不自动重试，接管只终结FAILED，不重执行外源。第一次源连接失败仅可在未读取任何行、同版本同plan且剩余预算内重试1次；认证/授权/schema/取消不重试。

typed plan只允许发布对象/列、等值身份、scope交集、批准时间窗、稳定排序、已发布RelationBinding；值参数化、标识符从固定catalog取。禁止SQL/SPARQL/URL/函数/CTE/DDL/DML/管理工具/模型直连数据库。源只读账号及READ ONLY REPEATABLE READ，本轮只合成fixture；不把字符串以SELECT开头当安全证明。

在源大值物化前用octet_length/源端CASE拒绝超长字段（4096B）及JSON原文（64KiB），SQL LIMIT101哨兵、全查询最多100数据项/1MiB响应/4MiB中间内存/1000条候选边；fanout估计与预算在展开前检查。无可信前缀超限UNAVAILABLE，有可信完整项前缀PARTIAL；不将截断空数组EMPTY。分页未开放，禁止透明循环翻页；观察排序eventTime+实体IRI+已登记唯一源键，源无唯一稳定键不声称游标完整性。Join只同源已发布关系，不把关系N×M展开计为无限预算。

新增默认零grant权限：`data.query.execute`（连接/数据集/字段/scope）、`data.query.result.read`（本人Query+同投影授权）、`data.query.evidence.read`；根snapshot还需semantic.read及正式本体scope。连接管理、mapping.read、mapping.source.validate均不能替代这些权限。合成realm中显式给指定测试主体grant，生产无默认角色升级；三项permission均只允许platform.viewer/platform.operator/platform.auditor任一完整角色作为前置；简写和其他角色均拒绝。每个请求分支需单条未过期grant完整覆盖该组织、全部请求site、精确connection/dataset/field集，不合并多条grant拼权限。不同分支可分别命中自己的完整grant；顶层snapshot不可见是403，某个可见分支缺grant只能在其ID可披露前提下记FORBIDDEN并按C1聚合。result.read还须本人query且当前execute grant覆盖原保存投影；evidence.read还须覆盖关联query结果和全部引用字段；不因只获result.read就绕过源字段许可。role只是前置，数据库grant与当前会话必需。四处检查：源读取前、结果提交/回传前、历史结果读取、MCP每次调用；字段/行scope交集在源SQL和输出双重核验。禁止客户端actor/session。

新增审计action封闭白名单：data.query.execute/read/cancel/evidence.read/expire；allowed/denied/failure沿现有审计枚举。审计仅queryId、scope、版本身份摘要、计数、固定码。成功提交原子边界：短平台PG事务按组织授权epoch→会话→Connections版本→Query租约/fence顺序锁定，模块参与者复核当前grant、active/connection/secret/catalog，写结果+receipt+COMPLETED+事务审计；任何失败全部回滚。外源IO期间不持平台长锁。取消事务与成功事务争同Query行，取消先提交则成功CAS失败；成功先提交则取消409。撤权先提交不得保存成功；成功先提交后撤权，回传前再鉴权，禁止披露并保留历史已提交事实（不能谎称从未保存）。网络写出后发生撤权无法召回已授权字节；定义线性化点和实际可保证边界，不承诺不可能的追溯抹除。本轮保证本平台服务器会话注销/禁用、数据库grant撤销、连接禁用与secret轮换；票据解密或当前会话状态无法核实即失败关闭。**外部Keycloak直接禁用账号但平台会话未失效的即时传播不支持**：现有MappingSessionAuthority仅解密本地票据（`backend/src/Hosts/OntologyPlatform.Api/G4/MappingSessionAuthority.cs:27`），没有IdP实时核验。该场景明确NOT_SUPPORTED/NOT_RUN，禁止声称已验证；本次申请只限合成环境，需用户在D集中接受此边界才可实施，不把它当安全PASS或生产承诺。要求外部禁用即时生效时，先在本申请补齐受控IdP协议/权限/缓存期限/文件并再裁决相关范围，不在编码中临时补认证合同。审计失败503；拒绝审计失败也不返回数据。

## E｜SDD最早真实切片与消费者

任务卡按已合并[SDD模板](../../tasks/templates/sdd-task.md)关联AC，不另建spec/plan。S1为正式DI → TLS PG合成映射 → HTTP查询 → 同事务结果/receipt → 新DI/DbContext解密/hash/精确值 → 浏览器刷新无源二次查询。S2优先当前撤权/迟到响应/ABA/取消/EMPTY与失败/消歧，非作者早审；S3才补关系/观测、同Gateway MCP和旧G2兼容。三切片是自动自检节点，不加逐项人工审批。

正式composition、factory生命周期、Npgsql/provider、迁移、路由序列化、OIDC票据/数据库grant全部复用；仅替换批准的合成端点/新合成凭据。禁止用测试专用factory或内存数据库证明真实PG持久/并发；跨实例使用两个API进程和独立连接。测试注入故障仅作用本任务合成源/租约，不停旧KEEP服务。

后续首份真实输出立即经既有workflow_evidence公开扫描/无损封装→`pwsh -NoProfile -File scripts/test-review-evidence.ps1`（参数以脚本实际help为准）→已提交候选`python3 -B scripts/maintenance/workflow.py plan --base <Base> --head <Head> --output <ignored-plan>`→`workflow.py package-check --task G4-M4-QUERY-001 --base <Base> --head <Head> --evidence <evidence-json>`。验证实际后缀、UTF8/LF、空白、ANSI、空流、ignored/禁入路径，日志原字节hash可恢复；schema2 exitCode/timingStatus分开。不新增报告体系，小样仅ignored诊断、不生成中间ZIP。本轮这些产品证据命令全部NOT_RUN。

## F｜准确范围、资源、影响与集中裁决

### F1 后续owned_paths（PROPOSED）

Master是唯一写者，所有公共合同、迁移、Host、工程消费者Single Writer；一个非作者只读Reviewer。无需产品Worker。下列目录别名仅为精确路径展开，不是目录全权授权：C=`backend/src/Contracts/OntologyPlatform.Contracts/`；Q=`backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/`；N=`backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/`；G=`backend/src/Modules/Governance/OntologyPlatform.Modules.Governance/`；H=`backend/src/Hosts/OntologyPlatform.Api/`；A=`backend/src/Modules/Agents/OntologyPlatform.Modules.Agents/`。N表示新增，M表示修改。

| 所有者/用途 | 精确文件 |
|---|---|
| Master 合同/生成 | N C/G4QueryModels.cs、G4QueryRules.cs、G4QueryServices.cs；M C/G2Services.cs（只新增独立G4接口/方法，不改旧签名）；M H/G4/G4OpenApi.cs、G4ContractExport.cs；M `docs/contracts/g4-connections.openapi.json`、`apps/web/src/lib/api/g4-generated.ts`、`apps/web/scripts/generate-types.mjs`；N `docs/contracts/g4-m4-query.md`（获批后仅索引本文与生成物，不复制规格） |
| Master 唯一Gateway | M Q/SemanticGateway.cs、QueryRules.cs、CapabilityRegistry.cs、SemanticQueryModule.cs、OntologyPlatform.Modules.SemanticQuery.csproj；N Q/G4QueryExecution.cs、G4QueryCanonical.cs、G4QueryDbContext.cs、G4QueryRecord.cs、G4QueryResultStore.cs、G4QueryWorker.cs、G4SourceEvidenceService.cs |
| Master 迁移 | N Q/Migrations/20261114000000_G4QueryPersistence.cs、20261114000000_G4QueryPersistence.Designer.cs、G4QueryDbContextModelSnapshot.cs；只建semantic_query自己表，精确名暂定，生成工具若要求不同时间戳只在本表更新并记录同一迁移身份 |
| Master Connections跨模块读取 | N N/Application/QueryBindingReader.cs、Adapters/PgQueryReader.cs、Abstractions/IG4PgQueryReader.cs；M N/Application/MappingActivationService.cs、Application/ConnectionApplicationService.cs、Application/ConnectionApplicationService.Commands.cs、Application/ConnectionApplicationService.Enable.cs（仅统一版本复核锁顺序） |
| Master 已准入依赖的锁闭包 | M Q/packages.lock.json、H/OntologyPlatform.Api.csproj（仅必要既有项目引用）、H/packages.lock.json、`backend/tests/OntologyPlatform.QueryTests/packages.lock.json`、`backend/tests/OntologyPlatform.SecurityTests/packages.lock.json`、`backend/tests/OntologyPlatform.AgentTests/packages.lock.json`；精确闭包只许既有中央版本，不改Directory.Packages.props |
| Master 当前授权/事务 | N G/QueryAuthorizationParticipant.cs；M G/MappingAuthorizationParticipant.cs、TransactionalAuditWriter.cs；DI注册归H/G4/G4Composition.cs，复用既有grant/epoch表形状，新增query许可策略，不默认授予，不另迁移Governance |
| Master Host/会话 | N H/G4/QueryEndpoints.cs；M H/G4/G4Composition.cs、H/G2/G2Authorization.cs、H/G2/McpEndpoints.cs、H/Program.cs；当前服务器会话复用MappingSessionAuthority，不读取客户端票据材料 |
| Master Run/MCP | M A/SemanticMcpTools.cs、ExecutionRunService.cs、AgentRunExecutor.cs；N A/G4QueryRunReference.cs；新G4工具执行引用单独在semantic_query表绑定runId，不改旧Run载荷/迁移 |
| Master UI | N `apps/web/src/features/semantic/g4-query-workspace.tsx`、`g4-query-api.ts`、`g4-query-model.ts`、`g4-query.test.ts`；M `apps/web/src/features/semantic/query-workspace.tsx`（并列G4入口，不替换G2）；M `apps/web/src/lib/api/openapi-types.test.ts`；复用现有Design System，不改Tokens |
| Master 测试 | N `backend/tests/OntologyPlatform.QueryTests/G4QueryTests.cs`、`G4QueryPersistenceTests.cs`、`G4QueryHttpTests.cs`、`G4QueryRaceTests.cs`；N `backend/tests/OntologyPlatform.ConnectionsTests/G4QuerySourceTests.cs`；N `backend/tests/OntologyPlatform.G2ContractTests/G4QueryWireTests.cs`；N `backend/tests/OntologyPlatform.SecurityTests/G4QueryAuthorizationTests.cs`；N `backend/tests/OntologyPlatform.AgentTests/G4QueryMcpTests.cs`；M上述既有测试项目csproj仅引用必要既有项目/复制批准fixture，不新增包 |
| Master 本任务最小工程消费者 | N `scripts/maintenance/workflow_m4_query.py`、`workflow-m4-query.mjs`、`scripts/tests/WorkflowQuery.Tests.py`；M `scripts/maintenance/workflow.py`、`workflow_environment.py`、`workflow_web_cache.py`、`execution_preflight.py`、`docs/development/verification-gates.json`；本任务注册/结构核验/报告资格/环境键/真实驱动，复用公共执行与证据模块，不新增工程优化任务 |
| Master 文档/证据 | 本轮三文档；获批后 `docs/evidence/G4-M4-QUERY-001/` 内当前Run公开原件/索引；ignored `artifacts/workflow/G4-M4-QUERY-001/` 与 `artifacts/reviews/` |

只读依赖：G2/G3冻结DTO及原始Schema、现有M3 manifest/canonical/fixture来源、模块Domain边界、中央版本配置及未受影响锁文件、SDK、AppHost、CI、Design Tokens、全部历史ZIP/证据、旧任务资源。无新的第三方包种类/版本/镜像需求；Q新增直接引用仓库已准入的Microsoft.EntityFrameworkCore.Relational/Design 10.0.13及Npgsql.EntityFrameworkCore.PostgreSQL 10.0.3（准确版本见根Directory.Packages.props:18–19、32），DataProtection来自既有FrameworkReference。本次集中申请Q及依赖Q的Host/测试项目锁闭包重生成；仅本地已核缓存，零下载，不重做既有供应链调查。缺包或闭包出现新版本即停止，不偷偷扩依赖。所有正式DTO→Host OpenAPI→`docs/contracts/g4-connections.openapi.json`→generate-types→`g4-generated.ts`→UI/MCP消费者由Master同一提交更新；本轮不生成。

### F2 资源提案与停止条件

P0创建记录：TaskId=G4-M4-QUERY-001，RunId=p0-contract-20261114；托管树 `/Users/chasen/.codex/worktrees/g4-m4-query-001/ontology-platform`，branch=`codex/g4-m4-query-001`，operationId=`ddb793db-9e28-4040-977d-73af96443916`。KEEP原因：待裁决且要求同树继续；解除条件：明确收尾授权且成果安全集成/归档。本轮无服务创建、移交、清理，不接触原树六个未跟踪.DS_Store。

采用**全新任务隔离栈**，不移交M3 KEEP、不复用其realm/卷/证书/凭据。可复用已校验只读镜像和内容缓存；私有runtime不复制。新平台PG768MiB/1CPU、源PG768MiB/1CPU、Keycloak1GiB/1CPU、API768MiB/1CPU、Fuseki2GiB/2CPU、RustFS512MiB/1CPU，共5.75GiB/7CPU；短命第二API额外768MiB/1CPU，M4峰值6.5GiB/8CPU、7容器，每容器PIDs≤256。M3登记6容器5.75GiB/7CPU是历史账，不是当前实测；若仍全部KEEP，共同峰值至少12.25GiB/15CPU、13容器，另加宿主Web/浏览器4GiB。申请共同容器上限14GiB/16CPU、宿主Web/浏览器4GiB；其他任务实际占用也必须加入，未知或超限不启动第二栈，不删除旧资源补预算。

新task compose project `ontology-g4-m4-query-impl-01`，独立network/volumes；仅127.0.0.1端口申请API15441、Web15442、Keycloak15443、平台PG15444、源PG15445、Fuseki15446、RustFS15447、第二API15448。获批后运行前确认未占用；冲突只重新选择未占用loopback端口并在同任务记录，不停止占用者。新合成证书/凭据只在本任务私有runtime；测试角色仅本任务realm显式subject/grant。数据≤3GiB、证据≤1GiB、缓存/构建≤6GiB，总增量≤10GiB；与M3历史磁盘预算合并最多20GiB且实际可用空间先核实。准备零下载，缺镜像/SDK/缓存立即BLOCKED；不恢复TDengine。

后续长任务先host_continuity preflight与用户能源策略确认，本轮没有把M3能源确认继承成新任务实际观测；再当前TaskId的execution_preflight和workflow prepare。准入适配未实现前BLOCKED。按准确TaskId/RunId记录创建/ID/配额；最终只收本任务安全候选，before-command-exit-after强后验，旧KEEP始终保护。

### F3 验收影响与一次性裁决

| 范围 | 后续必须FRESH | 可在新资格核验后REUSED | 本轮 |
|---|---|---|---|
| RQ-02/生成链 | 新判别字节、OpenAPI/TS一致、PG新上下文往返 | 不变G2历史输入部分 | NOT_RUN |
| PG执行/证据/六态 | TLS只读真实查询、空/故障/截断/候选/关系/精度 | M3发布原件身份仅为前提 | NOT_RUN；M3评估不代业务执行 |
| 当前授权/并发/恢复 | OIDC+DB grant、独立API租约、ABA、取消、迟到响应、刷新 | 无相应M4旧证据 | NOT_RUN |
| UI/MCP/G2兼容 | 当前生成物消费者、受控真实工具，无LLM | G2无影响部分资格核验 | NOT_RUN |
| 工程/证据 | 新TaskId入口、失败止损、公开资格与小样预检，稳定工程输入一次适用完整SelfTest | 公共未变输入的原Run/hash/有效测试数及证据核验 | NOT_RUN |
| 云CI/其他架构/其他数据库 | 只有另行要求才运行 | 不冒充本地结果 | NOT_RUN |

不能为新Head重跑M3全链。精确命令与门禁沿verification-gates登记，不把接口存在当准入。记录首真实路径形成时间、失败PRODUCT/HARNESS/EVIDENCE/ENVIRONMENT/EXTERNAL及发现切片、restore/产品重跑/封包次数；当前均未发生，时间UNKNOWN，restore=0、产品运行=0、封包=0，不宣称提速。

请在同一裁决中批准或修正：**A** PG单源三能力与不覆盖S-50/其他源；**B** 完整判别/精确数值/时间/字节合同及G2隔离；**C** 六态、证据、版本与24h合成结果恢复；**D** 默认零grant、明确角色/单条grant规则、事务/fence/取消和预算，以及仅合成环境下外部IdP直接禁用未即时传播的明确限制；**E** S1→S2早审→S3真实纵向验证；**F** 上述精确文件、迁移/生成物、Task消费者、独立资源及共同峰值、零新依赖。普通范围内修复不逐patch审批；新增业务语义/路径越权/费用/依赖/生产/main仍需明确决定。上述任一未裁决不是默许，由用户一次答复形成后续授权。

本轮不实施、不运行产品或服务、不prepare/restore、不下载/安装、不重跑M3、不清或移交KEEP、不更新main、不进入M5。停一次性规格与实施裁决关口。获批后沿同会话/树/分支；产品完成默认唯一最终V3 ZIP+SHA+包外回执+非作者独立重开，无需再次申请打包。本轮P0不生成ZIP。

### F4 P0检查与独立Review

2026-11-14 P0轻量检查FRESH：Python标准库只读检查exit0，三路径白名单=3、UTF-8无BOM/LF/尾换行通过、新增相对链接12条存在、4个JSON正例可解析且无重复键、四个判别顶层与嵌套字段集合一致、decimal/Int64精确字符串/微秒词法/关系端点/evidenceIds检查通过、未知字段负例拒绝、AC01–12齐全、六态表齐全、授权索引只追加。相同检查随最后文档修订复核；`git diff --check` exit0，提交时另核完整Base差异。没有安装Schema运行环境，完整JSON Schema/DTO/生成链/所有产品场景NOT_RUN；四例中ontology只验证封闭形状，不代表开放能力或真实证据成立。

非作者 `/root/m4_p0_review` 在本托管树执行一轮集中只读审查，后仅复核实际增量。发现并修正：原候选选择缺固定查询标识、分支事务/总预算、证据安全投影/MCP幂等输入/取消返回合同、IdP即时禁用能力误述、角色与单条grant前置规则。作者核对另修正不存在的Module路径、PG读取方法定位及既有EF锁闭包范围。最终Reviewer原话：“本轮发现项已关闭，可提交一次性A–F裁决；未发现剩余设计文档阻断。”审查仅静态文档/源码，未运行产品；外部IdP直接禁用即时传播仍必须在D由人类接受，未支持不是安全PASS。

所有产品FRESH/REUSED均无；CI/多平台NOT_RUN。当前文档可交裁决，不表示A–F建议已获批准。收尾保持三路径、无ZIP、无服务/准备/安装/产品运行；完整Head由任务分支提交给出，后续沿同树恢复。
