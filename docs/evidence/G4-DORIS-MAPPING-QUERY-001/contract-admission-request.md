# Doris Mapping/Query 一次性合同与实施规格

固定源码 Base：`606ca2d2c61964e6498dd72d5e9ad960d3593bf7`。本文件为唯一 A–F，版本 1；所有 PROPOSED 是待 ChatGPT/用户集中裁决的实施建议，并非本轮产品授权。唯一执行状态在[任务卡](../../tasks/G4-DORIS-MAPPING-QUERY-001.md)。本轮只读和文档；没有业务实测 PASS。

## A｜范围、实际能力和封闭切片

已批准的本轮操作为工程精确合并和规格提交。main 已由 b5e3b65d1a3359e8fd778700f525321333df61d2 快进到 Base；包外机器回执位于主树 `artifacts/reviews/G4-DORIS-MAPPING-QUERY-001/main-update-receipt.json`，不重打 M5。原整集 -9/TIMEOUT、122+11+1=134 个唯一用例并集覆盖均保持，不称整集一次 PASS。G4 总体 PARTIAL；M3/M4 是单 PG 切片。

下文路径缩写只用于精确展开：N=`backend/src/Modules/Connections/OntologyPlatform.Modules.Connections/`，Q=`backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery/`，C=`backend/src/Contracts/OntologyPlatform.Contracts/`，H=`backend/src/Hosts/OntologyPlatform.Api/`。行号均指 Base，不是旧任务当时版本。

| 项目 | 当前事实 | 本批次提案／拒绝或未知 |
|---|---|---|
| Doris 连接、目录、秘密生命周期 | M2 已交付；N/Abstractions/IDorisSourceAdapter.cs:5 只有 Probe/Discover | 不重做连接器；不是业务行读取证据 |
| Mapping | N/Application/MappingValidationService.cs:190,199,314,319 只允许 PG 配置/用途/版本 | 新 Doris 验证与分发；未知源失败关闭 |
| Query/恢复 | N/Application/QueryBindingReader.cs:71,135,184,267,326 限 PG；Q/G4QueryExecution.cs:674 固定 PG receipt | 新 Doris reader，沿唯一 Gateway 和既有持久恢复 |
| 关系 | 当前 Q/G4QueryExecution.cs:351 分别读取目标表 | 仅同一 Doris 连接已发布等值关系；各分支独立观察，无跨表原子快照 |
| 目录中 VIEW | DorisSourceAdapter 可发现 VIEW | 本切片只 TABLE；VIEW、外部 catalog、跨源均拒绝 |
| 类型/表达式 | PG 类型和 SQL 是专用实现 | Doris 封闭子集见 B；不自动复制 PG 函数、时区、JSON、分页 |

PROPOSED 全批次上限：单连接，目标沿 M2 的 localhost:19030、internal catalog、fixture database、fixture_reader、org-demo/site-a；仅两个显式 TABLE `dmq_entity`、`dmq_target`。新建任务独有合成实例，绝不借用 M2 KEEP 数据/密钥。每表≤12字段、≤100合成行；源读取 LIMIT101 哨兵，超额映射拒绝；查询按既有可信前缀规则处理。2个实体绑定、1个同源等值关系；fanout≤10、候选边≤1000、输出≤100项/1MiB、中间内存≤4MiB、标量≤4096 UTF-8字节。无自由 SQL/表达式/任意 URL、无跨源、无 cursor/offset、无生产、AI OFF。

S1 只用第一张表做实体定位与 decimal 属性，先走正式 G3 发布→目录→Mapping 评估/异人审核/发布/激活→HTTP 查询→真实持久→新会话原字节恢复。S2 才启用第二表关系和边界反例；S3 UI/MCP 与不变 PG 兼容。三种既有 G4 能力只接入获批类型；时间只开放下述DATETIMEV2(6)+明确Etc/UTC解释，保持现有HALF_OPEN_OVERLAP，未知时间仍阻断，不伪造源时区。

## B｜Doris 源语义与一致性

### B1 一致性选择及版本证据边界

现有 PG 证据来自真实 RepeatableRead/READ ONLY 和 pg_current_snapshot：N/Adapters/PgMappingSourceValidator.cs:89,239；PgQueryReader.cs:149,307。Doris 不执行这些语句，不调用 BeginTransaction(RepeatableRead)，不拼 txid、不将 query ID/目录 hash/随机 UUID 冒充事务快照。

[官方 4.x 事务说明](https://doris.apache.org/docs/4.x/data-operate/transaction/)描述单语句 READ COMMITTED，且不支持含查询的显式多语句事务。这是 4.x 滚动说明，**不构成已锁定 4.0.8 二进制实证**。4.0.8 SessionVariable 页面未提供本轮可用语义证据，SelectCommand 页面读取失败；不能据此证明多表/多语句一致性。版本与实测缺口保留 NOT_VERIFIED，公开读取无制品下载。

集中申请的最小语义差异：Doris 只声明每次已完成读取的窗口；`watermarkKind=UNKNOWN`、`watermark=null`。输出可有可信、已授权的实际值，但不承诺同一事务快照、跨分支共同时间点或源端持续不变。Mapping 在受控静止合成数据上完成有界全集校验；目录/ACL读取与业务读取前后各核一次，变化即失败关闭，相等不证明窗口内不存在 ABA。合成初始化写者在正式评估/激活/查询窗口内禁止写入，操作者在运行原件记录窗口；该夹具约束不冒充生产锁或数据库隔离。

最短待批探针：精确4.0.8两张合成表（同时核UNIQUE/MOW同key更新只见新逻辑值、DATETIMEV2(6)微秒保真），独立连接在两个顺序 SELECT 间提交受控变更，保留各自输入/返回时间、源端查询标识和独立预期；预期只能陈述各次读的事实，禁止将混合观察盖成事务快照。单语句的一致性也标 NOT_VERIFIED，直到对应版本依据及实测齐全。若业务要求跨表原子快照，本提案不满足，必须拒绝实施该需求，不通过扩大事务标签“解决”。

### B2 表、类型、关系和指纹

| 边界 | PROPOSED 合同 | 待批最短验证／拒绝 |
|---|---|---|
| 表模型 | 仅显式 UNIQUE KEY、enable_unique_key_merge_on_write=true 的合成 TABLE；逻辑当前行而非原始追加事件 | 目录外另读规范化 SHOW CREATE TABLE/受控元数据核模型；完整限定行检查身份唯一并核真实key列。重复写同key是upsert候选语义，须4.0.8首测；不称保留全部原始事件，不悄悄distinct |
| DUPLICATE KEY / AGGREGATE KEY / UNIQUE非MOW | 首批不支持；不假定存储排序key就是唯一主键 | 表模型变化或未知模型拒绝；M2 目录未登记模型，不能只看字段相同就放行 |
| string | VARCHAR，仅原始字符串保真、Ordinal 等值；不 trim、不 lower、不 Unicode 规范化 | SQL collation 未证明时只允许扩大候选再内存精确过滤，禁止会漏项的下推；标识符来自固定目录，值参数化 |
| integer | BIGINT 有符号→int64 十进制字符串；不经 JS number/double | 边界值/越界/NULL 分别实测；INT(11)不当宽度11位数值 |
| decimal | DECIMAL(p,s)，1≤p≤28、0≤s≤p；驱动原精确字符串解析，输出保留 catalog precision/scale | 同值不同p/s依数学精确相等连边；不能比较词法/元数据相等，也不走浮点；更高精度/特殊值拒绝 |
| NULL | 真 NULL 与空串/0不同；属性 nullable 精确核目录 | NULL 身份/必需scope拒绝；Query阶段NULL关系键不成边；Mapping评估/激活遇NULL关系键仍拒绝；missing字段拒绝，不能补null |
| 时间 | 仅DATETIMEV2(6)，源为无时区本地词法；Mapping显式REGISTERED_ZONE/Etc/UTC，MICROSECOND；纯转换后才输出timestampUtc，固定6位小数 | 4.0.8/驱动微秒保真及会话time_zone=+00:00待首测；未知时区/非6精度/零日期/溢出/不合法时间拒绝。DATE/DATEV2/旧DATETIME及其它时区、DST均不开放 |
| 其他类型/转换 | FLOAT/DOUBLE、JSON/VARIANT/ARRAY/MAP/STRUCT、BOOLEAN及所有未列类型拒绝 | 只开放本切片 string/int64/decimal 原值及显式Etc/UTC时间转换；不得沿用PG jsonb/cast函数 |
| 同源关系 | `(scope, 精确decimal值)`等值；两端实体身份各自唯一，目标可有两个不同实体同键；还须满足现有HALF_OPEN_OVERLAP有效期规则 | fanout展开前检查；NULL/不等值不成边；不声称FK约束或跨分支原子性 |

M2 N/Adapters/DorisSourceAdapter.cs:258–304 目录仅字段/对象，N/Application/QueryBindingReader.cs:326 的 pg-m1-v1 必须按源分发。保留 M2 原目录算法及既有快照原字节（ConnectionApplicationService.Catalog.cs:164 当前Doris也使用pg-m1-v1算法标签，这是历史目录哈希，不是PG事务承诺；不重命名旧算法），不将旧快照“升级”为含表模型指纹。Doris mapping-v1 额外有内部 `SourceSemanticsHash`：规范 JSON 固定字段 `sourceType,adapterVersion,catalogFingerprint,tables`，tables 按database/name排序，每项 `database,name,tableModel,mergeOnWrite,keyColumns`，keyColumns保留序位；不包括行值/观测时间。只接受显式模型元数据，未知拒绝。该 hash 进入本次 assessment evidenceHash 与语义不变量 hash；激活时重新核验。同名同列换模型必须 stale。运行 Query 每分支也核允许模型，不把目录指纹当数据水位。

## C｜公共合同和准确实现差异

### C1 冻结版本组合

| 层 | PG保持 | Doris提案 |
|---|---|---|
| MappingVersionBinding | POSTGRESQL / pg-mapping-v1 / mapping-validator-v1 / mapping-c14n-v1 | DORIS / doris-mapping-v1 / doris-mapping-validator-v1 / mapping-c14n-v1 |
| Query读取/receipt | pg-query-v1 / TRANSACTION_SNAPSHOT / 实测PG快照 | doris-query-v1 / UNKNOWN / null |
| 公共wire形状 | g4.mapping.v1、g4.query相关现有schema与字段不变 | 只扩SourceType/adapter/executor允许配对，不加宽任意字符串接受范围 |
| 持久化 | PG历史manifest、result规范字节、hash及恢复语义不改 | 使用现有JSON/receipt字段；不增加迁移、不改G3权威格式 |

内部模型精确提案：`MappingSourceObservation` 保留现有 `Tables,CatalogFingerprint,StartedAtUtc,FinishedAtUtc,SecurityVerified`，将必填 string `TransactionSnapshot` 替换为必填 string `WatermarkKind`、必填 nullable string `Watermark`，增加必填 nullable string `SourceSemanticsHash`（PG null，Doris 64hex）。`G4SourceQueryRead` 同样替换 TransactionSnapshot，新增必填 `AdapterVersion`；已有 CompletedAtUtc 明确为读取结束，不保证事务提交。它们是服务间模型，不是直接 HTTP DTO；共享 Contracts 仍由 Master 唯一改。

PG evidenceHash 计算显式保留旧属性名 transactionSnapshot 及原结构，不能因内部重命名改变旧字节；Doris 用版本分支纳入 watermarkKind/watermark/sourceSemanticsHash，不能让 PG 按 Doris 路径重新序列化。公共 result DTO/receipt 既有 WatermarkKind/Watermark 足够，Q/G4QueryRecord.cs:82,97 已有 adapter/watermark 列；无预防性迁移。

### C2 从正式入口到消费者

| 精确路径（前缀见A） | 未来变更，不是本轮执行 |
|---|---|
| N/Abstractions/IMappingSourceValidator.cs；N/Application/MappingValidationService.cs:190,199,313,743,1157 | 配置改为封闭 Pg/Doris 服务端判别；Doris独立实现。输入、版本、观察hash按源分发；平台PG容量advisory锁保留 |
| N/Application/MappingValidationService.cs:872–881 | MatchesDatatype原仅识PG native名，改按source封闭识别Doris VARCHAR/BIGINT/DECIMAL/DATETIMEV2(6)；NativeType保留真实varchar/decimal(p,s)，不伪装character varying/numeric；同源类型解析复用明确helper，新 N/Application/DorisMappingTypeRules.cs；ConvertValue(:1025,1042)同样识别Doris decimal(p,s)，关系key规范化沿精确数值算法、不比较表示元数据；Instant(:816)显式处理Doris本地微秒+REGISTERED_ZONE/Etc/UTC，保持未知时间拒绝和半开重叠，不伪装PG native名 |
| N/Application/MappingApplicationService.cs:844；C/G4MappingRules.cs:101；C/G4MappingModels.cs:280 | 提案、发布、激活、回滚/历史读都使用相同封闭版本对，不能只开放初次评估 |
| N/Application/QueryBindingReader.cs:71,135,184,267,326 | 执行/历史/提交复核三路同时分发配置、用途、目录算法、reader；当前secret必须是本连接已绑定 DORIS_READONLY，不复用PG秘密 |
| 新 N/Adapters/DorisMappingSourceValidator.cs、DorisQueryReader.cs；新 N/Abstractions/IG4DorisQueryReader.cs | 无客户端SQL，固定字段计划，参数化值、精确类型、大值物化前拒绝、LIMIT哨兵、当前ACL/模型核验 |
| 新 N/Adapters/DorisReadSession.cs；N/Adapters/DorisSourceAdapter.cs、DorisCertificatePolicy.cs | 仅将既有TLS/同账号取消机制提取为受控复用，元数据默认10秒行为不变；业务读传入绝对deadline，禁止机械继承4秒尾部清理 |
| C/G4QueryServices.cs:119；Q/G4QueryExecution.cs:674；Q/G4SourceEvidenceService.cs:28,39 | 源中立内部模型、receipt组合验证；PG与Doris版本严格绑定。UNKNOWN必须null，无读成功不得发成功证据 |
| H/G4/G4Composition.cs:52,72,83 | 正式DI分发，无第二Gateway、无测试专用工厂证明生产链 |
| H/G4/G4OpenApi.cs、G4ContractExport.cs；docs/contracts/g4-connections.openapi.json；apps/web/scripts/generate-types.mjs；apps/web/src/lib/api/g4-generated.ts | DTO→OpenAPI→TS链核验；仅实际规则/注释差异生成，不手改制造伪变化 |
| apps/web/src/features/mappings/editor.tsx:54,57、mappings.test.ts；apps/web/src/features/semantic/g4-query.test.ts | 编辑器当前PG硬筛增加Doris限定选择和负例，既有Query页复用，不扩页面体系 |
| Q/SemanticGateway.cs；Modules/Agents/OntologyPlatform.Modules.Agents/SemanticMcpTools.cs | 行为复用、预计不改；仍四个G4工具，输出同规范字节，不加Doris自由SQL工具 |

不改：公共请求/结果字段集合、六态枚举、Query/Run预算、权限名、平台数据库/迁移、G3发布物、PG catalog/canonical版本、依赖锁/SDK/AppHost/CI/Design Tokens。若实际必须改这些形状或持久语义，停止该差异并集中裁决。源端fixture DDL/数据初始化仅未来实施获批后对任务独有合成库执行，不是产品写源能力。

## D｜安全、取消、授权与运行风险

沿 M2 严格实际握手回调：N/Adapters/DorisCertificatePolicy.cs:16–41 固定私有根、名称、用途、有效期、禁下载；DorisSourceAdapter.cs:117 的 Required 只用于触发回调，不等于完整校验。在线吊销仍 NOT_VERIFIED。继承 M2 仅合成环境风险接受的事实，不能自动将它扩展为生产许可。

源账号每次 SHOW GRANTS 白名单检查（DorisSourceAdapter.cs:212）；平台 grant 还必须覆盖 org/site/connection/dataset/所有读取字段。Doris首期要求整张表 SELECT 的严格既有权限配置，不把PG逐列ACL函数移植，也不把目录可见视为字段有权。撤权/新写权限/继承角色/未知权限格式均失败关闭。源读前与读后、平台提交和响应前再复核；外部源ACL无法与平台PG事务原子提交，最终核验之后的源端变化不承诺追溯召回，明确观察窗口。

Mapping 仍总30秒、statement≤5秒；Query 100..5000ms，分支≤min(1000ms,剩余−500ms)，最后500ms留平台提交/授权，不是额外时间；Run≤30秒/最多3工具。每连接2/每主体1/全任务4、租约10秒心跳2秒/fence规则不改。Doris原元数据10秒+清理4秒**不能直接复用为查询耗时合同**。

取消提案：每分支预算内部预留最多250ms同账号源端取消/关闭，保留实际 ServerThread 身份，只有本次连接ID可作为 KILL CONNECTION 目标；不接受客户端线程ID，不授予管理员。绝对deadline到期无论清理结果均不得返回/持久成功；清理失败记录固定错误，查询终结FAILED/CANCELLED，禁止重试并停止后续产品扩展，保留源残留NOT_VERIFIED。250ms内真实源取消可行性未证，不能以关闭socket或令牌取消证明完成。最早真实切片先测源执行中取消与源端消失，预算不够即BLOCKED，不加时到4秒。驱动原生取消1105旧失败保留；早期KILL QUERY 24ms不冒充现产品KILL CONNECTION路径。

Doris首批自动重试=0（比PG允许的首次未读行连接重试1次更窄）；任何权限/schema/取消/读后故障均不重执行业务查询。固定码按现有失败/六态合同映射，不返回SQL/秘密/未授权源对象。FOUND、EMPTY、PARTIAL、AMBIGUOUS、UNAUTHORIZED、UNAVAILABLE仍沿M4；子源SUCCESS/FORBIDDEN不混同顶层状态；执行RUNNING/FAILED/CANCELLED不是第七业务态。空集只有真实完整读取成功可称EMPTY；故障空数组不得冒充EMPTY。没有可信前缀为UNAVAILABLE，有可信前缀才PARTIAL；总deadline耗尽不能保存COMPLETED。

成功提交沿既有平台短事务：epoch→session→Connections版本→Query lease/fence，结果+receipt+COMPLETED+审计原子；平台PG事务不随外源换Doris。activationId+单调revision阻止A→B→A；当前连接禁用、secret/catalog变化、撤权先提交即拒绝成功；已提交后撤权则回传前拒绝披露，保留真实历史提交。审计失败不披露。外部IdP直接禁用即时传播未支持的旧限制保持，仅平台会话/数据库grant机制可作保证。

历史恢复重新核当前本人、scope、execute/result/evidence权限与源当前ACL/字段兼容，仅系统目录/权限读取，不重放业务SELECT、不生成新readReceipt、不改保存canonical。active改变可显示历史版本，权限失效必须清屏并废弃迟到响应；结果TTL24h、receipt/必要元数据7天、容量各64MiB沿现合同。MCP每次调用同Gateway、当前授权及工具预算。

## E｜最早真实切片、独立预期与反例

以下全部设计，NOT_RUN。正式参与者为合成OIDC中的编辑者A、审核者B、激活者C和查询者Q，A/B按既有异人约束；独立参考操作者R只在任务合成设施准备数据/读取独立SQL预期，不通过产品写源。正式DI、DbContext工厂、provider、源TLS、G3/Jena/RustFS、权限/审计/持久模块均使用当前实现。

两表字段固定：dmq_entity `(org_id VARCHAR(32) NOT NULL, site_id VARCHAR(16) NOT NULL, entity_id VARCHAR(32) NOT NULL, join_key DECIMAL(10,2) NULL, amount DECIMAL(20,2) NULL, unit_code VARCHAR(8) NOT NULL, valid_from DATETIMEV2(6) NOT NULL, valid_to DATETIMEV2(6) NOT NULL, event_at DATETIMEV2(6) NOT NULL, observed_at DATETIMEV2(6) NOT NULL)`；dmq_target `(org_id VARCHAR(32) NOT NULL, site_id VARCHAR(16) NOT NULL, target_id VARCHAR(32) NOT NULL, join_key DECIMAL(12,3) NULL, valid_from DATETIMEV2(6) NOT NULL, valid_to DATETIMEV2(6) NOT NULL, event_at DATETIMEV2(6) NOT NULL, observed_at DATETIMEV2(6) NOT NULL)`。UNIQUE KEY(org_id,site_id,entity_id/target_id)，显式MOW=true；key列在定义首部且非null。只有4.0.8真实目录/SHOW CREATE核定唯一key并经受控重复写见证后，reader才填RecordKeyFields为这三个实际列；否则不得声明ROW_KEY或FOUND，首切片BLOCKED。身份/排序仍核全限定集合，URI不冒充主键。

参考数据：entity=(org-demo,site-a,E1,1.00,9007199254740993.20,K)；target各行org-demo/site-a，依次T1=1.000、T2=1.000、T3=1.010、T4=NULL。独立预期在产品查询前冻结：E1精确amount字符串9007199254740993.20/p20/s2；目标集合恰T1,T2，fanout=2；T3/T4不连边。两表统一valid_from=2026-11-01 00:00:00.000000、valid_to=2026-12-01 00:00:00.000000、event_at=2026-11-17 12:00:00.123456、observed_at=2026-11-17 12:00:01.123456，Etc/UTC解释。身份/TemporalSpec引用相同有效期列。amount仅为精度测试的合成温度量（不作物理合理性声明），unit_code=K；UnitSpec注册版本1，source/targetUnitIri均urn:synthetic:m3:K-v1、identity转换。正式G3词汇沿已批准单位定义提供nominalUnit/quantityKind/dimension一致证据，独立预期包含K单位及unit_code源证据，不新增单位注册项。T4只在正式激活后插入，发布/激活夹具仅T1/T2/T3；另一个明确Mapping反例先放NULL应阻断，不在成功夹具中混入。参考SQL由R固定执行 `SELECT t.target_id FROM fixture.dmq_entity e JOIN fixture.dmq_target t ON e.org_id=t.org_id AND e.site_id=t.site_id AND e.join_key=t.join_key AND e.valid_from<t.valid_to AND t.valid_from<e.valid_to WHERE e.org_id='org-demo' AND e.site_id='site-a' AND e.entity_id='E1' ORDER BY t.target_id`。SQL是测试原件，不进入UI/MCP或用户载荷；另用整数系数/十进制scale算法独立得到1.00=1.000、1.00≠1.010、NULL不等值，不从被测结果生成expected。SQL自身语法/返回也是NOT_RUN，失败不篡改expected迎合产品。

| AC / 场景与时机 | 正例／关键反例与可观察断言 |
|---|---|
| AC01 S1发布 | A正式G3/目录/Mapping评估→B审核→C激活→Q定位E1；给固定类型与授权应正式成功；未发布/错source-purpose/混配adapter拒绝且无成功发布/activation |
| AC02 类型 | 真实读取大decimal不失精度；p/s不同等值保留两条边。1.010、NULL不连；高精度/未知类型/缺字段/未知时区阻止映射发布；微秒123456保真，半开端点恰相接不成边，已有canonical不变 |
| AC03 身份/模型 | 同完整key重复写只允许验证后的upsert逻辑当前行；改变身份映射使两个不同key投到同一实体身份则全量校验拒绝，不能distinct；改DUPLICATE/AGGREGATE模型或同列换模型后旧assessment不可激活；无新成功Release/Activation |
| AC04 当前授权 | 源读前撤grant无行读取；读返回后、提交前同query撤grant/session失效/secret轮换，成功CAS不得成立；历史result/evidence拒绝且UI清屏 |
| AC05 目录 | 评估后到激活前删除/换类型/换ordinal/换模型；查询源读中受控DDL；前后指纹/模型变动拒绝，不能用旧目录继续成功 |
| AC06 取消/源断开 | Q开始实际业务SELECT后另一正式取消入口取消；同一query因果链含源开始→取消提交→源消失→终态，取消先提交无result/成功receipt/COMPLETED；迟到值不能上屏。源断开不得EMPTY |
| AC07 版本/ABA | 同query源返回后正式C激活B再A；revision递增后旧query提交409，无成功副作用；不同query的独立切换不能当因果证据 |
| AC08 恢复 | S1成功后新OIDC会话/新DbContext读取同query，SHA与字节相同；业务SELECT计数不增加，当前ACL查询可增加；TTL/授权失效分别410/403，无重执行 |
| AC09 预算/六态 | 真空、101哨兵、超大字段、fanout11、分支断开/超时，按可信前缀与六态；总deadline含审计，不保存超时COMPLETED，不增加第七态 |
| AC10 消费者/PG | UI和四工具与HTTP相同canonical；无权限工具isError且固定文案；旧PG发布物及历史result原字节/hash不变 |
| AC11 一致性边界 | 受控写者在两SELECT间提交；Dorisreceipt仍UNKNOWN/null，记录各窗口，不声称同快照；静止fixture窗口违反即该验收失效 |

无成功副作用是指目标操作没有新成功业务结果/Release/Activation，允许既有失败/拒绝审计；若成功先于撤权提交，按D保留已发生事实，不能要求抹去历史。首个证据即绑定实际源版本、fixture、会话/授权epoch摘要、构建输入/预期、命令退出码与时间，沿现有公开证据扫描和schema2记录；不保存密码/票据/私有CA材料。

## F｜实施准入、资源、验证和交付

### F1 准确版本与资源条件

复用已准入 Doris4.0.8 ARM64：FE `sha256:c7b4288a34affac9fe809a2895565b4d558ea3b85fbf5d29bb1ec27d398e4f02`，BE `sha256:1d4ccee8d7cc5e33f1c16e0b3ce764f5f764c396ea5e938a8793f88682c982f7`（infra/doris/compose.yaml:6,48）；MySqlConnector2.6.2（N/packages.lock.json:31）。不升级、不新增依赖/锁变化/下载。M2 [delivery-status](../G4-M2-DORIS-01/delivery-status.md)及[product-proof-index](../G4-M2-DORIS-01/product-proof-index.json)仅作连接/目录来源，不称Doris业务读已验收。证书、源角色、二进制与运行输入变化后必须新定向TLS/取消验证。

当前只读观察：VM 16,787,419,136 bytes（约15.63GiB）/12CPU；M4与M5各7容器仍运行，不能假定历史资源已释放。M2四卷 `g4-m2-doris-01-probe_{be-data,be-log,fe-data,fe-log}` 与原私有runtime全部KEEP。主机可用磁盘约224.7GiB是本轮df观测，非后续启动保证。详细安全投影见[事实索引](facts.md)。不读取Env/secret，不启动诊断容器。

PROPOSED 独立任务栈预算：FE4GiB/2CPU、BE6GiB/2CPU、平台PG0.75GiB/1CPU、Keycloak1GiB/1CPU、Fuseki2GiB/2CPU、RustFS0.5GiB/1CPU=14.25GiB/9CPU（6容器）。API和临时第二API均为宿主进程各预留0.75GiB/1CPU，使用只读运行快照；宿主Web/浏览器另4GiB，宿主增量峰值共5.5GiB/2CPU加浏览器CPU。固定localhost:19030在宿主API内指向FE发布端口，绝不在普通API容器里误用localhost。每容器PIDs≤256。M4+M5实测受限配额合计12GiB/9CPU，故同时运行候选容器峰值26.25GiB/18CPU，当前VM不满足。暂停旧栈后14.25GiB虽小于15.63GiB，但只余约1.38GiB系统空间，仍不满足提案的至少2GiB VM保留量，不能称“只需暂停即可”。本轮未暂停任何KEEP。

集中资源选项：建议用户另行明确提供≥32GiB/24CPU开发VM（另核宿主余量，不能由Agent改全局设置），维持旧KEEP运行；或明确授权指定旧栈暂停并提供≥20GiB/14CPU VM。两方案都需后续即时全资源盘点/创建前预算核验；默认全部旧KEEP不动。当前未申请直接处置任何ID；若选暂停方案，必须先提交准确完整容器ID、实测释放量、保留卷/密钥/备份与逐ID恢复命令的集中授权，不可用本提案代替暂停许可。

新project候选 `ontology-g4-doris-mapping-query-001`，源FE固定loopback19030（与M2选项一致，冲突即BLOCKED，不偷改目标）；宿主API15641/Web15642/OIDC15643/平台PG15644/Fuseki15645/RustFS15646/第二宿主API15647，只loopback，未测可用。FE沿批准bridge入口、平台PG/OIDC/Fuseki/RustFS按这些端口仅loopback发布供宿主API访问，内部数据网络internal；FE沿M2 bridge入口，bridge有出站不称断网。新独立CA/凭据/卷/realm；旧M2私有runtime不复制。磁盘增量≤12GiB（数据4、证据1、构建/缓存7），共享镜像不再下载/保存副本。BE所需max_map_count≥2000000、无swap、nofile≥60000只在获准启动前核，不自行改全局。

### F2 未来实施文件所有权与门禁

Master唯一写者，C2列出的精确源/合同/生成文件为候选所有权；新增受控测试 N对应 `backend/tests/OntologyPlatform.ConnectionsTests/DorisMappingQueryTests.cs`，以及现有 `backend/tests/OntologyPlatform.QueryTests/G4QueryTests.cs`、`G4QueryPersistenceTests.cs`、`G4QueryHttpTests.cs`、`G4QueryRaceTests.cs`，`backend/tests/OntologyPlatform.G2ContractTests/G4QueryWireTests.cs`、`backend/tests/OntologyPlatform.SecurityTests/G4QueryAuthorizationTests.cs`、`backend/tests/OntologyPlatform.AgentTests/G4QueryMcpTests.cs`。UI精确owned_paths为C2所列editor.tsx、mappings.test.ts、g4-query.test.ts；不新建第二查询页面体系。

必须新增任务准入适配器（候选 `scripts/maintenance/workflow_doris_mapping_query.py` 和浏览器 `workflow-doris-mapping-query.mjs`），仅最小注册到 `workflow.py`、`execution_preflight.py`、`docs/development/verification-gates.json`，复用现有证据/执行/环境模块。测试 `scripts/tests/WorkflowDorisMappingQuery.Tests.py`；任务独有compose候选 `infra/doris/compose.mapping-query.yaml`。这是未来业务消费者必要范围，**不是另建工程优化任务**；本轮全部只读。未登记消费者时 prepare/verify 产品准入为BLOCKED，不能借M2/M4 TaskId偷跑。

恢复前读取本任务卡/唯一规格；长任务先host_continuity preflight并确认能源策略，再当前milestone执行前置、prepare零下载、当前实际DI/audit/消费者核验。稳定输入按影响验收，不从M1重跑。复用刚合并的创建前资源预算、同消费者即时前提、只读运行快照、独立测试库Owner/nonce守卫、生产量构包测量；不复制另一套执行体系。测试库不接运行库，产品运行产物只读绑定完整输入。

长工程外层期限采用同环境实际观测加有限余量：旧133项构包294.32秒只作参考，候选600秒硬上限，启动前按当前输入规模确认；不能机械240秒重造超时，也不能扩大产品5秒。失败按PRODUCT/HARNESS/EVIDENCE/ENVIRONMENT/EXTERNAL留原件，短定位有新假设才重验。

### F3 当前验证边界与集中决定

FRESH：main祖先/归档SHA/精确patch、普通push握手与回读、受保护文件哈希；本轮源码/公开资料/资源只读事实；文档UTF-8/链接/白名单/diff-check/有限敏感扫描及非作者Review。REUSED：同一M5工程ZIP机器回执与非作者重开；134唯一用例口径原件。M2/M3/M4为准确历史参考，未在本轮重新取得新产品资格。NOT_RUN：所有产品测试、prepare/restore、服务操作、Doris探针、构包、CI/双架构/生产；NOT_VERIFIED见B/D/F未知项。

一次裁决需决定：①A/B的窄类型、UNIQUE KEY/MOW逻辑行及应用身份校验、独立观察/UNKNOWN水位及静止合成窗口是否接受；②C的封闭版本组合、内部模型及PG字节兼容策略；③D取消须在原预算内证明，否则BLOCKED，以及已知IdP/撤销限制；④E先单表真实发布/查询/持久恢复再关系与反例；⑤F具体资源方案、任务自有合成DDL/数据/凭据、精准消费者和测试路径。批准不能自动授权main、生产、G5、TDengine、新依赖或处置旧KEEP。

规格阶段不ZIP。未来实施获准且完成后，沿[PLANS](../../../PLANS.md)唯一规则：源码/格式→适用测试→非作者Review→提交→当前输入绑定→唯一V3→非作者同包重开→包外回执；>10MiB解释、>15MiB阻断；不继承本轮禁包例外。本轮普通push文档分支后停ChatGPT裁决，新Head不合main。

### F4 独立审查与轻量检查

非作者 /root/spec_review 经初审与两轮增量复核，最终确认“可交集中裁决，未发现剩余规格阻断”。实际检查见同目录事实索引；该结论仅为静态规格可审，不代表产品通过。

表模型变更记录：作者静态自审发现DUPLICATE排序键不能证明ROW_KEY，故候选缩为UNIQUE/MOW且以4.0.8最短探针为实施首门禁；未证不得按数据库唯一约束宣称成功。SourceSemanticsHash中keyColumns必须精确等于上述冻结三列，MOW必须true；Query每次核相同固定形状，不能仅比较allowed模型名。
