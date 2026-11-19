# Oracle Mapping/Query 实施准入合同

2026-11-19 集中裁决 CONDITIONAL GO。P0 原件位于 `8ddaabb90878d5ab72a92908a030b7397c6f2d4d`，main 为 `5168f2c93ca226caa521a6dc4ac85439335274c4`。以下为本次获准实施的合同。AC01–AC11 须按当期原件裁决。参见[事实索引](facts.md)与[任务卡](../../tasks/G4-ORACLE-MAPPING-QUERY-001.md)。

## A　范围、合成目标与固定读取

Master 单写。沿正式 G3 发布、Mapping 人工作者/异人审核、发布者激活、当前授权查询者的链路。只选一个 `ORACLE_READONLY` 连接，固定 TCPS `oracle-source:2484/FREEPDB1`、`FIXTURE_READER`、`org-demo/site-a`，有序 owners 为 `PRODUCTION, CaseOwner`。新任务独占合成 PDB 及平台。选定两张物理 TABLE 为 `"PRODUCTION"."OMQ_ENTITY"` 与 `"CaseOwner"."OmqTarget"`。首次正式目录发现之前完成两表 DDL、只读授权与种子，保留初始列描述及行散列。S1 只发布第一表，S2 加入第二表。每表最多 12 个显式字段、100 行，2 个实体绑定、1 条同连接等值关系。

两表各 11 列。ROW_ID 为 NUMBER(18,0) PK，JOIN_KEY 分别为 NUMBER(12,1)/(13,2)，VAL 为 NUMBER(28,6)，ORG_ID、SITE_ID、EXT_ID、LABEL 为显式 VARCHAR2，FROM_TS、TO_TS、EVENT_TS、OBSERVED_TS 均为 TIMESTAMP(6)。FROM_TS/TO_TS 同时绑定身份与 temporal 有效期，事件和源观察时间分别来自 EVENT_TS、OBSERVED_TS，明确 Etc/UTC 和六位精度，不读 now 或空引用。发现前冻结两表 DDL、字段归属、单位合同、PK、两表直接 READ、业务身份、小而完整的非 NULL 种子和独立预期。每表 100 行只是读取上限，Mapping 仍受总输出项限制。

三项能力为 `g4_resolve_entity`、`g4_read_observations`、`g4_traverse_relationships`。服务端从同版 binding 的字段和对象白名单生成固定投影与确定次序，精确引用 owner/table/column，固定 `ORDER BY` 唯一非空行键，取 `FETCH FIRST 101 ROWS ONLY` 哨兵。所有值按类型绑定，禁止拼入值或让客户端传 SQL。Mapping 扫描两表全集才可证明唯一性/基数。Query 在同一授权有界集上做确定性分类、时间窗口和精确键匹配，超量只能按 AC07 返回可信前缀或不确定态。扇出≤10、候选边≤1000、返回≤100项/1 MiB、工作集≤4 MiB、单标量≤4096 UTF-8 字节，先核声明上限再物化。专用 reader 不授源写权限。DDL/DML 仅属获准后的单独合成夹具写者。

VIEW、同义词、DB link、跨容器/跨源、自由表达式、游标/分页、任意 schema 或 URL 不入场。保留 Ontop 对比、Web Mapping/Query、TDengine、五源全流程、Windows/AMD64 与生产的缺口。AI OFF。

## B　类型、身份、关系与读一致性

固定 Oracle 26ai Free 23.26.3.0.0 Linux ARM64，ODP.NET Core 23.26.400。M2 能列出某 native type 只说明目录可描述。下表为业务读取的封闭规则，未列组合拒绝；官方版本依据与待测驱动差异见[事实索引](facts.md)。

| 源定义及用途 | 精确值和拒绝边界 | 最早 S0 独立对照 |
|---|---|---|
| VARCHAR2(n BYTE/CHAR)，显式长度，数据库 AL32UTF8、二进制非补空格比较 | 依目录核 BYTE/CHAR、字符集、排序规则及最大字节≤4096；保留原串、大小写、前后空格和 Unicode 序列。文本外部身份只用白名单 ASCII 非空标识；物理行键用下一行整数 PK，SQL 顺序/内存键一致。内容等值用明确的逐字节 UTF-8 规则。拒 CHAR/NCHAR/NVARCHAR2、语言排序、隐式转换、截断 | 'A'/'A '、大小写、组合字符与分解字符、空串/NULL、字符与字节边界；同前缀不同键返回稳定顺序 |
| NUMBER(p,0)，1≤p≤18 | 可证明整列落入有符号 Int64，限制为 ±(10^p−1)，核实际系数后再转换。有意排除 NUMBER(19,0)、无声明 NUMBER、负 scale 及 FLOAT | 正负边界、零与空值、超出声明或未知精度拒绝。原生有理数与参考整数一致 |
| NUMBER(p,s)，1≤p≤28、1≤s≤p | 精确系数与十进制 scale，拒精度缺失、s>p、隐式舍入与二进制浮点；类型或运算不能无损表示即拒。展示可保留合法小数位。等值比较以整数系数按十进制对齐，零统一、NULL 不连边；不比较字符串或显示 scale | 两列 1.0 与 1.00 连边，近邻、负数、NULL/NULL、28 位边界及超过上限；用独立任意精度系数算期望 |
| TIMESTAMP(6) WITHOUT TIME ZONE（Oracle 拼写 TIMESTAMP(6)），仅已发布 REGISTERED_ZONE=Etc/UTC | 值域为公元 0001-01-01 至 9999-12-31，保留六位小数；这是映射明确解释的本地时间。拒 DATE（含时分秒）、其他小数精度、WITH TIME ZONE、WITH LOCAL TIME ZONE、缺时区策略及未知类型。禁止由会话或宿主时区推断。拒 RAW、LOB、JSON、INTERVAL、二进制浮点及隐式文本化 | 公元上下界、BC、越界或不能无损转换须拒绝；末微秒、跨日、同一值切换会话时区、零长度/反向窗口、时区或精度错配；原端投影与独立 UTC 基准一致 |
| 对象与复合身份 | 目录顺序按 Ordinal，保留 quoted 名大小写。未识别对象/字段、大小写冒用及视图拒绝。行键为受控唯一 PK，映射业务身份按 org/site/实体类型/外部键核完整全集与 NULL、重复和目标基数。任何歧义不补猜。空串按本版 Oracle 读作 NULL，缺身份拒绝，缺属性依现行空值策略，关系任一键 NULL 即无边 | `"OmqTarget"` 与 `"OMQTARGET"`、有尾空格、空外部键、相同业务键不同 PK、多父与重复目标 |
| 半开时间关系 | 两个有效区间必须满足各自 start<end，重叠当且仅当 a.start<b.end 且 b.start<a.end。接壤不重叠。必需时间为 NULL 或无法解释时拒绝发布/标来源不确定，不返回假 EMPTY。 | 公共过滤时间保留 0–9 位小数，独立整数纳秒对照 t−1ns、t、t+1ns、前后一微秒。禁止将请求端点截断/舍入为微秒。独立枚举交叠、接壤、间隙、同起点和 NULL，核实际关系结果 |

**事务边界。** Mapping 全集评估在同一物理非池化连接的一次显式只读事务内读两表。单个 Query 源分支亦使用独占连接，前置会话设置和当前权限核验结束其事务后，在同一非池化物理连接建立驱动显式本地事务，关闭 auto-commit，以该业务事务的第一条 SQL 执行 `SET TRANSACTION READ ONLY`，直到完成所有游标、提交或回滚。核验与业务事务的顺序要由原生会话证据支持。回读当前 ACL/目录使用新鲜视图，不能依赖冻结的旧权限视图。关系遍历目前分支依次读表，不承诺分支间或整次业务查询共享同一快照。每个 receipt 只记真实起止、行数、精度，`watermarkKind=UNKNOWN`、`watermark=null`。当前无可绑定到本次读事务的 SCN 证明，不采集虚构水位。

S0 用独立夹具写者在两次固定读取间提交成对变更。核同事务前后都见旧版、新事务见新版；做普通独立语句可见新值、跨分支允许不同版本的对照。还原行与授权，复核摘要。驱动若不能确认事务边界、会话发生切换，或历史 ACL 无法以新鲜窗口复验，停止该切片，保持 NOT_VERIFIED。降级成逐语句一致性须裁决。

## C　真实分发、版本与兼容

| 服务端 config / 用途 | 历史目录算法 | Mapping 适配器 / executor | 查询 receipt / 水位 |
|---|---|---|---|
| PgConnectionConfig / POSTGRESQL_READONLY | pg-m1-v1 | pg-mapping-v1 / mapping-validator-v1 | pg-query-v1 / TRANSACTION_SNAPSHOT 与已记录值 |
| DorisConnectionConfig / DORIS_READONLY | pg-m1-v1（当前目录编码的历史事实） | doris-mapping-v1 / doris-mapping-validator-v1 | doris-query-v1 / UNKNOWN、null |
| OracleConnectionConfig / ORACLE_READONLY | oracle-m2-v1 | oracle-mapping-v1 / oracle-mapping-validator-v1 | oracle-query-v1 / UNKNOWN、null |

映射公共 canonical 版本沿用 `mapping-c14n-v1`。只支持上述完整元组且 sourceType 分别为 POSTGRESQL、DORIS、ORACLE。目录身份与新发布/查询版本独立。未知、交叉组合、不同 connectionId、旧激活 revision 或原件内容不符均拒绝。公共 wire、六态、证据字段、PG/Doris/Oracle M2 历史字节、ORM 迁移及依赖锁按原合同。若无法仅用既有字段表达则返回集中裁决。

**未来代码改动图。** 下列 N、Q、C、H 分别指 [Connections](../../../backend/src/Modules/Connections/OntologyPlatform.Modules.Connections)、[SemanticQuery](../../../backend/src/Modules/SemanticQuery/OntologyPlatform.Modules.SemanticQuery)、[Contracts](../../../backend/src/Contracts/OntologyPlatform.Contracts)、[API Host](../../../backend/src/Hosts/OntologyPlatform.Api)。本表差异已获条件授权，Master 按各阶段的当期准入实施。

| 真实入口 → 消费者 | 最小改动与定向资格 |
|---|---|
| H/G4/G4Composition.cs → N/Application/ConnectionSourceDispatcher.cs、N/Abstractions/IOracleSourceAdapter.cs、OracleAdapterOptions.cs、N/Adapters/OracleSourceAdapter.cs 与 OracleSourceAdapter.Sql.cs | 保留 M2 Probe/Discover 和固定 TCPS/owner。增加业务专用有界会话、Mapping validator、Query reader（建议 N/Adapters/OracleMappingSourceValidator.cs、OracleQueryReader.cs、OracleReadSession.cs），走正式 DI 与单一 Gateway。提取可接受原期限的安全核验，阻止旧连接/Dispose 独立超时进入新路径。 |
| N/Application/ConnectionApplicationService.Catalog.cs → QueryBindingReader.cs 的 DemandCatalog、加载原/最新快照、执行/提交/恢复 | 原件按绑定的 sourceType、config/secret 版本和准确连接分别选择已冻结 CanonicalCatalog 的算法与编码。原发布不可套当前配置；通过服务端持久身份验证类型，取规范顺序与 Encode/Hash。Doris 目录仍按实际旧算法。核造假的 config 类型、登记散列与对象列表不符。 |
| N/Application/MappingValidationService.cs、MappingApplicationService.cs → C/G4MappingRules.cs、G4MappingModels.cs 与 N/Abstractions/IMappingSourceValidator.cs | 同一分发覆盖提案、评估、批准、发布、激活、回滚、历史。以封闭源身份显式判别原观察与证据编码，移除依赖 SourceSemanticsHash 是否非空、UNKNOWN 或二元 config 推断第三源的路径。PG 保留 transactionSnapshot 原属性与顺序；Doris 保留其 evidence/semantic hash 输入。Oracle 新算法绑定本源目录、列声明、权限证明、原表身份和本版 executor，新增 Oracle 类型转换/关系规则。PK、collation、物理对象等源证明只进内部 Oracle 读取模型。 |
| C/G4QueryServices.cs → N/Application/QueryBindingReader.cs → Q/G4QueryExecution.cs、G4SourceEvidenceService.cs | 绑定用途、原/当前目录、授权和固定 reader，复用内部读取模型；按 sourceType 与完整版本校验 receipt、行数/精度/计划/真实读取。执行器显式选择 Oracle 分支的提交余量和跨实例取消观察，PG、Doris 原行为各自锁定。持久结果只读原 canonical，现有查询生命周期与源错误语义保留。 |
| Q/VerifiedReleaseSources.cs、SemanticGateway.cs；Publishing/Jena；Agents 的 SemanticMcpTools.cs；apps/web/src/features/mappings/editor.tsx 与 semantic/g4-query-workspace.tsx | 编辑器现仅请求 PG/Doris，加入明确 Oracle 选项及错误用例。沿正式网关执行查询、恢复及四个工具，核 OpenAPI/生成 TS 的既有形状。正式对象逐槽按原字节/长度/hash、graph IRI、SHACL 和当前权限验证，按原绝对期限清理；历史发布图、请求间缓存与公共字段无扩展需求。 |
| scripts/maintenance/workflow.py、execution_preflight.py、workflow_environment.py、workflow_m2_oracle.py、workflow_oracle_fixture.py、workflow_oracle_platform.py、workflow_evidence.py、scripts/create-review-package.ps1 | 旧 M2 工具硬绑 TaskId/RunId/私有根及元数据流程。未来新增本 TaskId 的最小业务适配与准入登记，复用现有执行、构建身份、浏览器、验证和发布/恢复消费者；分别走真实正/反分发证明旧 M2 仍可用。prepare 先核当前资源与完整本地内容键，零下载；execution_preflight 按阶段核真实 DI、审计与入口，拒未知/错借 TaskId；verify 走新任务独立资格。旧 M2、PG、Doris 仍按自己的准确分发。 |
| H/G4/QueryEndpoints.cs → Q/SemanticGateway.cs、G4QueryExecution.cs → G4QueryResultStore.cs、G4QueryWorker.cs；Agents/SemanticMcpTools.cs、ExecutionRunService.cs、内部 deadline 载体 | HTTP Guard/body、MCP ReserveRun、发布根、查询/取消/恢复、提交到 Run 绑定均继承同一原期限。Store 的 Admit、终结、清理确认、过期与 Sweep 消费 Oracle 保留 owner，worker 重启仍按持久占位计量；跨 API 实库验证。 |

## D　权限、原绝对期限与取消因果

每次核真实 PDB/协议/reader、服务端信任指纹、连接启用与秘密用途/版本、actor/scope/当前授予的操作及所有读字段，包括行键、关系和时间列。目标闭包为两张精确 TABLE 的直接 READ、CREATE SESSION 及固定只读证明视图。M2 允许两个 owner 内的其他 READ；新任务应同时比对完整允许对象集合、禁止额外角色/列授权/ANY/写权限、PUBLIC seed 差异和独立管理视图。S0 单独见证只读主体可看本任务本次执行的最小 ID/时间/错误码投影，无 SQL 文本/绑定值、无系统级取消或广域字典权限；观察者和夹具写者与产品完全分离。Grant 签发、撤销、续期均有范围及审计。取消和恢复同样先核当前权限及正式发布根。查询末次提交在同一平台事务复锁原 release、activation revision、queryId、lease/fence、会话、授权和 deadline。失败零成功结果/receipt/成功审计。

以请求接收时单调时基换算的原绝对截止为界，全程≤5 s。源分支预算取 min(1 s，原期限剩余−500 ms 提交余量)，在该分支内预留最多 250 ms 用于 cancel/游标关闭/事务结束/Dispose/确认。读取、握手、权限、对象和源证明、平台观察与提交都消耗原剩余；若剩余≤250 ms 不发新读。每个进行中的 Oracle 分支复用平台同 queryId/lease/fence 的串行取消观察，建议间隔 10 ms、最多四执行合计理论≤400 次/秒，先测真实负载与延迟。原心跳继续。核连接池关闭、Pipelining=false、禁重试、单连接单命令；启动时验证实际实例属性，pipelining=true 的负对照拒绝进入取消场景，令牌与定向 OracleCommand.Cancel 作用于本次实例。不得另起清理期限、遗弃底层工作或在未确认状态归还槽位。预算内无法确认清理则无成功、记录未知、隔离该执行与槽位、封闭后续投递并报告；不可借后台补清理宣称在期限内成功。

HTTP 在 Guard/读 body 前、MCP 在每次 G4 工具调用 ReserveRun 前建立单调起点与最多五秒 token。Gateway 仅取 min(入口原期限、入口起点＋Query.TimeoutMs、外层剩余)，末端 Run 绑定也服从同一预算。UTC 用于持久关联，本地耗时按单调时钟；跨时钟使用保守误差界。5 s/1 s/250 ms 适用于正式 Query、取消与恢复。Mapping 评估继续使用既有 30 s。共享 G4 慢前置处理的行为发生改变，PG/Doris 正常、拒绝、恢复与预算边界定向验收，G2 路由沿旧合同。

Oracle 取消/超时/失败时先阻止成功并推进 fence。源清理未确认保留原 LeaseOwner；Admit 在同一数据库锁下计入 RUNNING 与终态仍有 owner 的占位，拒同连接新工作；过期未 Sweep、进程失联及重启仍保护。LeaseUntilUtc 到期不能视为物理空闲。准确 queryId、原 owner、原 fence 和当前终态 fence 在同一数据库事务 CAS 清除一次；须确认同次源执行、游标、事务、连接已释放且无残余。错身份、重复、迟到成功、Sweep/取消竞态不可清除他人占位。结果到期访问仍拒绝，Sweep/过期清理不得删除未知占位。正常成功释放、PG/Doris 终态及公共状态/迁移保持原合同。无法用现有字段实现须提供具体反例并集中裁决。

正式取消提交时间由同一事务 CommitAsync 调用开始至成功返回夹定，核实持久状态及取消审计。有效清理截止取原总截止、原分支截止与取消提交＋250 ms 三者最早。以提交区间下界到源终止和全部清理确认区间上界加时钟误差作验收，包含观察、传播、Cancel、游标、事务与 Dispose。CompletedAtUtc 预赋值、HTTP 返回和 worker 检测时刻都不能重置窗口。超时、掉线或后台迟到恢复分开记录。两 API 与真实平台库验证取消后占位、逾期/重启/Sweep、CAS 只释放一次及迟到成功被拒。

**最早的源端因果实验。** 保留 M2 的 ModuleName=G4-M2-ORACLE-01。新业务必须用 ModuleName=G4-ORACLE-MAPPING-QUERY-001 和每次执行独占的非敏感 ClientId，将该标记与 TaskId/RunId/commandId/queryId 对应，核对源端实际可见值与长度；拒用旧模块名或复制上一执行的标记。先测固定 SELECT 自然结束、正式取消的授权/发布核验至事务提交延迟、观察采样周期、源证据落盘滞后与跨时钟不确定区间。每次关联平台 queryId/lease/fence → 唯一物理会话（实例、PDB、SID、SERIAL#、审计会话及本轮标记）→ 本次 SQL_ID/SQL_EXEC_START/SQL_EXEC_ID 或能区分重复执行的源事件。默认串行计划，若存在并行执行者须完整证明所有从属任务终止，否则退回。正式取消先提交时源命令仍在执行，源观察者取到同次执行因用户中断的终态（候选原生错误 ORA-01013，与准确调用对应）以及退出执行/无残余的独立观测；最坏时钟误差计入，自取消提交至终止≤250 ms，清理不越分支与总截止。记录处理/采样/证据到达三个时间，迟到审计须有可界定的原始事件时间。源端抽样消失、会话断开、客户端异常、超时或单纯双零均不足。自然结束、取消在完成之后、身份复用、慢观察者给出负对照；核平台零成功副作用。该证据链在本版 Free 的可用性 **NOT_VERIFIED**。同一执行须有定向 Cancel 的实际发出证据和原超时期限，排除 CommandTimeout、请求断开、先发超时与自然完成；ORA-01013 单独不足。UNIFIED_AUDIT_TRAIL.EXECUTION_ID 与 V$SESSION.SQL_EXEC_ID 分别取证，须证明实际桥接；审计创建或到达时刻不能代替终止边界。按预期自然结束是负对照。先在正常上限内测窗口；若命中不了真正运行中的固定 SQL 或需扩大权限/数据/预算，保留原件并停 S0，不进入正式后续切片。

## E　AC、原件资格与切片顺序

全部 AC 为 NOT_RUN。表中左项为 Given/When/Then 正例，右项为相同入口的反例。每项先把独立预期与原件登记，再对候选按相关输入重核资格。

| AC / 最早切片 | 正例与反例、判定 | 正式入口、独立预期与原件 / 最小重验 |
|---|---|---|
| 01 S0 类型与身份 | 给定两表，正式 reader 与 B 的边界值、字段元数据匹配；空键、错大小写、尾空格误合并、未知数字或时间类型拒绝 | ODP.NET/正式 DI；独立整数系数、UTF-8、微秒基准及原生类型字典。改类型只补矩阵与受影响序列化 |
| 02 S0 一致性与水位 | 给定同事务两读之间的已提交更新，同一事务旧、新事务新；跨分支无共同水位，混入 SCN/SID/快照标签拒绝 | 正式业务会话＋独立写者和读者，准确物理会话/事务顺序与前后行摘要。重测事务范围 |
| 03 S0/D、S2 正式取消 | 自然结束对照成功；有界正式取消时同一命令在途并因取消终止、零成功。自然完成竞态、采样滞留、错误执行 ID、残余任务、平台观察失败不可放行 | S0 最小真实驱动与平台路径，S2 在活跃发布上正式 HTTP Cancel 复验；源终态/传播/预算和独立库行计数。改驱动、预算或计划重测准确因果 |
| 04 S1 单表纵切 | 给定已发布 G3、当前授权与单表映射，异人审核→发布→激活→HTTP 实体查询→持久→新会话恢复原字节；作者自批、错用途、未发布或图/SHACL 不符拒绝 | 正式四角色、PG/对象存储/真实图的发布根，源值独立夹具期望，manifest/assessment/result/receipt 原字节。改绑定重测 S1 |
| 05 S1/S2 权限/目录/ABA | 当前授予与版本匹配才提交；旧目录/激活、TTL 不足或自然到期、撤字段、trust/secret 轮换拒绝，原连接同 query 两种 A→B→A 时序拒绝 | 正式预检查/提交/恢复，准确 revision、源证明、事务与成功副作用计数。单独核权限先提交及 source ACL 漂移 |
| 06 S2 等值与关系 | 给定两张已发布表，相等异 scale 且半开重叠才连；先以非 NULL 数据评估、异审、发布、激活，再由独立写者按准确键注入 NULL，正式 Query 证明任一端 NULL 均不连边，复原后核两表散列。Mapping 遇 NULL/缺端点继续阻断；邻近值、接壤、反区间、重复目标、多父或过扇出不产额外边 | 关系网关及正式 reader；独立枚举边集/窗口与源 SQL 对照；验证仅依赖受控全集。改关系规则重测 |
| 07 S2 六态与超量 | 空而完整才 EMPTY，明确命中 FOUND，多候选 AMBIGUOUS，可信受限前缀 PARTIAL，失授权 UNAUTHORIZED，失败或无可信结果 UNAVAILABLE；超量评估拒绝，有限 Query 不能误报完整 | 正式查询与六态 wire；确认 100 边界和 101 哨兵。本轮仅一次独立 101 行反例，准确键还原两表摘要。ROW_ID 未进入业务身份时允许依法 UNAVAILABLE，不强造 PARTIAL |
| 08 S1/S2 恢复 | 新会话本人有权则回读完全相同原字节；过期、撤权、错主体和权限范围拒绝，恢复不重放业务 SELECT | 实际 PG 存储＋源审计窗口、sha/字节、行数，状态与正文；持久/ACL 改动补 |
| 09 S3 消费者 | 正式 UI/HTTP/MCP 同版返回三能力和同一原字节；撤权清屏、身份切换、旧请求晚到不泄露旧结果，四个受控 MCP 工具无旁路 | 实际浏览器/API/工具分发，独立 UI 可见性、原始响应及源审计。改 UI 仅补涉及路径 |
| 10 S1/S3 历史兼容 | PG/Doris 原发布/assessment/result 与原执行相同，Oracle M2 原目录 hash 可重算；互换源标签/水位、旧证据改字节拒绝 | 精确 Git/original golden、真实 canonical 与消费分发；当前无 Oracle 历史业务发布。改哪个编码器只补其黄金集及相邻源拒绝对照 |
| 11 首份证据／每个长场景前 | 正确新 TaskId、充分 TTL、当前版本与夹具允许，过期/短 TTL/目录/激活反例保持原前态不被自动修好；无业务 DML/SELECT 的窗口才可判该前检无副作用 | 真实准入/生产资格消费者、负例原件及同解析器有活动正对照；重算输入漂移则拒绝或重测 |

**证据消费者。** 每阶段走现有 execution_preflight/workflow 的真实分发；原件含 TaskId/RunId、阶段/模式/预期故障、argv 与摘要、commandId/父宿主、双流/退出码、单调耗时、API/测试构建、驱动及阶段参数指纹、inputsUnchanged、真实审计区间与解析器版本。对健康及预期拒绝执行同样核验。资格反例覆盖同步更新文件登记后仍错的指纹、argv、驱动、构建与宿主、错阶段、inputsUnchanged=false、窗口对不上和零检查。首份原件经 workflow_evidence.publish/restore 核原长/哈希，首份代表原件在最早可验证里程碑提交后经 workflow plan 的代表原件登记触发生产 MeasureOnly，同一成员选择核 MemberPlan，避免最后才发现格式或体积问题。机制可复用；归档/精测及最终同包重开绑定当期输入。

S0 先测类型、会话/事务及取消窗口，再决定能否继续；最小正式取消可需先建立一份正式授权发布与最小 API，不等待完整 UI。S1 单表发布到新会话；S2 双表、负例和正式取消；S3 浏览器/MCP 与相邻源兼容。每个长命令紧前检查资源、构建、TTL≥测得最坏场景时长加恢复余量、源与平台前态。旧 M2 生命周期、Doris 定向取消或历史 134 项不能替当期响应、版本或观察。每个失败先封存原件，按 PRODUCT/HARNESS/EVIDENCE/ENVIRONMENT/EXTERNAL 分类，以新输入或新假设只重试受影响短链。本轮实施完成并通过后生成唯一最终 V3、包外机器回执与非作者同包重开。

## F　资源选项、保全与停止

批准**独立新栈**。原有三项易失持卷保留，旧任务镜像可按准确内容键只读复用。新 Oracle 卷、平台 PG、独立 Keycloak/Fuseki/RustFS、API 主副、测试容器、网络与密钥全绑定本 TaskId/RunId。不得在旧源/PDB或现有三服务运行新数据。下表是已批准上限，GiB/CPU 为 Docker hard limit；S0–S3 逐阶段启用所需子集。

| 项目 | 新增上限 GiB / CPU | 加入当前持卷 3.5 GiB / 4 CPU 后 |
|---|---|---|
| S0 源 Oracle 4/2、串行探针 0.5/0.5 | 4.5 / 2.5 | 8 / 6.5；正式取消需下行正式根栈 |
| 正式持续栈，Oracle 4/2、PG 0.75/0.5、OIDC 1/1、Fuseki 2/1、RustFS 0.5/0.5、主 API 0.75/0.5 | 9 / 5.5 | 12.5 / 9.5 |
| 跨实例副 API 0.75/0.5 与临时探针 0.5/0.5 同时存在的最高阶段 | 10.25 / 6.5 | **13.75 / 10.5**；约余 5.78 GiB / 1.5 CPU。不得并发额外 build、恢复或压力任务 |

替代式恢复仅在新原栈排空、原生干净停止、原卷保留后启动隔离整栈。含原三服务＋单探针为 13 GiB/10 CPU，再加副 API 为 13.75 GiB/10.5 CPU。源卷、备份、恢复副本、临时文件和日志同时计入磁盘，不在运行原栈旁叠加恢复。首次有效小种子即做保全与隔离恢复，最终再核准确最终数据。

以实施当刻为准。预留 VM 至少 3 GiB / 1.5 CPU，正式运行前核 VM 内可用 RAM、磁盘可用空间和预热期观测；当前仅知 VM 总量。宿主另留至少 4 GiB 可用，Web/浏览器/证据程序建议合计≤2 GiB，监测压力及 swap 持续增长。旧镜像展开上限 13 GiB；新任务独占磁盘峰值≤40 GiB（含归属镜像、源与平台卷、私有备份和临时副本、日志及候选包），另留 VM/宿主各≥10 GiB 空间；源镜像已实占部分按实际共享层扣除，逐项登记剩余增量和备份上界。核共享层避免重复计费，库存不可回收空间不作可用预算。若临时隔离恢复会超峰值，时间错开而且重算，无可证明空间则停。宿主和 Docker VM 文件系统分开计量。

两个 internal 网络与一个任务专用普通 bridge host-entry（具有出站能力）。Oracle 仅 source-internal、不发布端口。平台 PG/Fuseki/RustFS 仅 platform-internal，无宿主端口。主副 API 均接三网，OIDC 接 platform-internal 和 host-entry，宿主 Web 与发布端口限 127.0.0.1；临时探针/观察者只接必要内部网，无公开端口。主/副 API、OIDC、Web 首选 15741/15742/15743/15744。先实测占用，冲突在 15741–15747 一次冻结不冲突的 PortMap，早于 issuer/callback、构建与浏览器。PG 审计经内部探针或准确 ID exec。每个 API 的 network namespace 内复用 M4 固定 loopback relay 至新 OIDC/Fuseki/RustFS/宿主 Web，计入该 API 配额；不直改 Jena/RustFS loopback 守卫、不增加常驻容器或自由转发。启动后逐向用正式客户端核宿主 Web→API/OIDC、SSR→API、主副 API→平台/源、OIDC discovery/token/callback、图/对象和构建身份，未通则不进入长链。

保全首选新任务的普通持久卷及独立权限目录，密钥与数据分开管理。持续记录准确容器/卷/镜像/网络 ID、内容键、读写者、引用和 TaskId。封闭投递/有界排空、原生一致备份、旧挂载保留、隔离恢复同身份并验证 PG 原行/授权、OIDC 主体签名、TDB2 发布图/SHACL、对象版本原字节、Oracle 两表/权限/信任及密钥解密。非作者核 before-command-exit-after 后再裁决释放，任何 UNKNOWN 原态留存。源端全库灾备、私有密钥可恢复性与新任务隔离恢复均 NOT_VERIFIED。

**当前授权与停止。** 仅本任务新资源可有界启停、备份和替代恢复，旧 17 个 STOPPED_KEEP 和三个运行中持卷者继续按原 ID 保护，旧 Oracle 卷/密钥不得借用。当前资源与入口检查失败即停；新栈必须保留完整的原卷与可恢复私有键。100 行正常范围无法证明正式固定 SQL 在取消提交时仍在途，或同源终态不可归因，集中报告 BLOCKED。无新假设不扩大数据、权限或时限。S0 通过自动 S1–S3；完成才打唯一最终 V3，无成功时交阻断回执与原件。
