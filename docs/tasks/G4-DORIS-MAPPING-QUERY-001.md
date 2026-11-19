# G4-DORIS-MAPPING-QUERY-001｜Doris Mapping/Query 规格

## 当前执行与授权
唯一执行状态：WAITING_CHATGPT_REVIEW。S0–S3 已通过本地切片验收。用户于2026-11-18批准同一会话/托管树/分支从7810f79227ea2e203fab8bdce60e4c29a1842110实施。分支codex/g4-doris-mapping-query-001，主线基线606ca2d2c61964e6498dd72d5e9ad960d3593bf7。实施EvidenceRunId=implementation-01；既有资源Owner保持原身份。

Master单写。2026-11-19 追加同请求核验的 PublishingCatalog、ReleaseVerifier、JenaSemanticRuntime 及对应内部合同与回归。原 owned_paths 为[唯一合同C2/F2与集中裁决](../evidence/G4-DORIS-MAPPING-QUERY-001/contract-admission-request.md)列明的源、测试、最小任务注册和当前文档。历史PG规范字节、旧ZIP与私有设施为只读依赖。R0允许14个准确ID在保全、排空、恢复清单与非作者检查后优雅停止。用户随后手动调VM。当前其他旧KEEP受保护，本分支不合main。

## Specify：可观察要求

| AC-ID | 行为与正反Given/When/Then（完整场景见规格E） | 实现/测试位置 | 最早验证层/结果 |
|---|---|---|---|
| AC01 | 已发布且完整授权则查询成功；错用途/未发布拒绝 | MappingValidationService/QueryBindingReader，DorisMappingQueryTests | 正式四角色单表及双表发布均已运行，正例通过 |
| AC02 | decimal同值异scale连边；不等/NULL不连 | DorisQueryReader/G4QueryTests | 独立 SQL 与整数系数参考、正式关系查询同得 T1/T2 |
| AC03 | 全集唯一身份可发布；身份碰撞/未知表模型拒绝 | DorisMappingSourceValidator | S0 模型拒绝，S1 不支持的身份拒绝，S2 多父和危险身份方案被拒 |
| AC04 | 当前授权有效可提交；撤权/轮换先提交无成功副作用 | G4QueryAuthorizationTests/G4QueryRaceTests | 源 SELECT 撤销、读后撤 execute、会话失效及在途轮换 1→2 均拒绝；新发布及历史字节已复核 |
| AC05 | 元数据兼容可用；列/模型变化旧批准拒绝 | QueryBindingReader/新Doris测试 | 审批后形状变化拒绝激活；同查询读行后到目录后验前真实改名返回 422，原 tablet、DDL 与行摘要恢复 |
| AC06 | 完成读取正常返回；取消/断开不得EMPTY或迟到成功 | G4QueryHttpTests/新Doris测试 | b676 独立逐任务证明通过，FE ≤34.371 ms、BE ≤64.521 ms，零成功副作用；124f 原裁决 NO-GO |
| AC07 | 当前activation可提交；同query ABA拒绝 | G4QueryRaceTests | 两个真实同查询 ABA 时序均在原期限内以 409 拒绝，零成功副作用；拒绝当刻 RUNNING |
| AC08 | 新会话恢复原字节；撤权/到期拒绝且不业务重查 | G4QueryPersistenceTests | 新会话恢复原字节；撤权 403；一次性查询到期后结果/证据均 410，FE 审计业务查询集合未增加 |
| AC09 | 六态/可信前缀正确；超预算无COMPLETED | G4QueryTests/G4QueryWireTests | 空集、歧义、扇出、真实断开、超宽列及最终提交截止已测；实体 101 行查询只返回前 100 个可信候选，准确复原已复核 |
| AC10 | HTTP/UI/MCP相同结果；PG旧字节不变 | G4QueryMcpTests/既有Web测试 | PG 两组历史 manifest/result 与 standard assessment 通过。三项 UI 能力和四个 MCP 与 HTTP 原字节相同，撤权 403 清屏与身份切换通过 |
| AC11 | 分别读取记录真实窗口；不盖虚假snapshot | 新Doris测试 | S0 受控写入与 S1 UNKNOWN/null 已核验 |

## Plan：最早真实风险路径

最高风险为PG事务/证据标签误移植、Doris取消尾部超5秒和精确decimal关系。先冻结B/C合同，首个单表正式发布→查询→持久→新会话恢复前先证明原预算内源取消。正式DI/工厂/provider/权限/审计复用，不用测试替代构造证明真实链。证据按F2复用现有schema2/资格/小样预检；资源不足与当前任务消费者缺失是实施BLOCKED条件，不阻止本轮规格交付。

## Tasks：按行为纵向拆分

| 切片 | AC与成果 | Owner/路径 | 正反验证 | 当前结果 |
|---|---|---|---|---|
| A | 精确工程main更新 | Master，既有主树 | 原件/祖先/握手/回读 | COMPLETE，包外机器回执 |
| B | 唯一规格和独立审查 | Master，owned_paths | 文档轻量核对 | COMPLETE，静态可交裁决 |
| S1 | 单表发布/读取/恢复 | Master，规格C2/F2 | AC01/04/06/08/11 | GO_TO_S2，单表切片已复核，正式在途取消见 AC06 |
| S2 | 双表精度/模型/并发 | Master，同上 | AC02/03/05/07/09 | 双表、边界、当前权限和 AC06 均已复核通过 |
| S3 | UI/MCP/PG兼容/最终V3 | Master，同上 | AC10/受影响门禁 | UI/MCP、PG 历史字节与 16 项受影响门禁通过。最终 V3 的散列、同包重开和远端回读见包外回执 |

## Verify与恢复

自本卡、唯一规格和implementation-01原件恢复。本 Run 已完成 R0、S0–S3 及受影响工程门禁。CI 为 NOT_RUN，G4 整体为 PARTIAL。原整集-9/TIMEOUT和134唯一覆盖保留。未跟踪用户文件保持原状。

R0原件及非作者结论见[14个准确ID与保全缺口](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/r0-review.json)。第一次中止时，14个原ID中，M4主/次API已请求TERM、自然退出0，其余12个仍运行。8个易失卷热备及隔离同ID恢复通过，两份隔离H2读取原夹具realm通过。用户批准的改序由非作者现场放行后，M4 keyring已取得冷副本并独立核验。准备处置M5前排空检查触发DRAIN_ACTIVITY_DETECTED，剩余处置中止，八卷继续由准确只读容器持有。非作者现场复核结论为NO-GO继续停机或调VM。20轮事后采样及单独补核MappingJobs/MappingOutbox均为零，触发时具体活动UNKNOWN。见[停机与独立复核回执](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/cold-save-review.json)及[恢复保护反例](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/cold-save-validation.json)。现VM仍15.63GiB/12CPU，暂缓用户手调。离线准备与定向检查见[当前验证](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/validation.json)。SDK短诊断通过，正式prepare受原失败保护拦截，C#未编译。S0及后续产品链均NOT_RUN。

## 本次剩余12个ID重新准入（2026-11-18）

准入回执 SHA-256 为 `67415b09491a84605a77a7cedfeaf27835b1bfd308182e75859e4a66926cab95`。两个平台库各48张表处于准确栅栏事务内，三轮连续观察四库分项均为零，包含MappingJobs和MappingOutbox；非作者放行同一栅栏内的余12个原ID。

第二次中止时，累计6个原容器退出、8个仍运行。4个API退出0，M4 Keycloak退出143并有关闭记录。M4 Fuseki退出143、无OOM，其镜像配置关闭了根日志，未取得本次应用关闭完成的证据，处置中止。两套keyring及M4 Keycloak三份冷备已经过独立校验。M4 Fuseki原卷的两次完整摘要与已审热副本完全一致，其关闭钩子完成状态仍为UNKNOWN。原只读持卷容器持续保护八卷；未调整VM。当时的独立结论为NO-GO继续停机或调VM，分项结果、退出原件及复核见[再准入回执](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/readmission-01.json)，定向反例见[验证回执](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/readmission-validation.json)。

## 余8个ID接续与M5源库异常退出（2026-11-18）

两套 Fuseki 都通过用户批准的替代验收。原镜像隔离读取最终冷 TDB2，M4 的默认图为 0 行、命名图共 4291 行，6 个已发布图逐图匹配；M5 分别为 0 行、1461 行，2 个已发布图逐图匹配。两套应用关闭钩子均保留 UNKNOWN。非作者先复核替代验收前提，再核对同一批排空事务中两个平台库合计 96 张表的栅栏及四库连续三轮零在途，才放行后续处置。

八个易失卷的最终冷归档共 795217920 字节，已逐份复核长度、全字节 SHA-256、权限及隔离同 ID 恢复。两份 Keycloak 副本均读取到预期 realm。14 个原 ID 中已有 11 个退出，10 个达到本轮停止验收。M5 源 PostgreSQL 使用镜像配置的 SIGINT，Docker 停止命令返回 0，容器退出 1，未触发 OOM。Tini 报告信号转发权限不足。退出后只读解析原卷 pg_control 状态头得到 6（DB_IN_PRODUCTION），未检验全文件 CRC，WAL 恢复能力仍待验证。该退出单独记为失败。

第三次中止时的非作者结论为 NO-GO。当时两套平台 PostgreSQL 和 M4 源 PostgreSQL 仍在运行，原持卷容器继续只读挂载八卷。VM 实读 16787419136 字节、12 CPU，暂缓调整。当时待裁决事项为 M5 源库持久卷的隔离恢复与余三库的原生有界关库。正式 prepare 仍为 BLOCKED / SHORT_REPRO_REQUIRED，S0–S3 及产品验收未运行。完整 ID、逐轮计数、冷备与停机结果见[第三次中止回执](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/readmission-02.json)和[定向测试回执](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/readmission-02-validation.json)。

## R0 完成，等待用户调整 Docker VM（2026-11-18）

按新增单卷授权，从 M5 源库的只读持久卷制作 68311040 字节私有归档。准确原镜像在隔离副本完成 WAL redo。冻结原件中的标准表 2/3 行和激活后数值表 2/4 行，全部行与 34 个列定义比对通过；同站点数值关联与单个 NULL 匹配符合原预期。副本以 postgres 用户执行 fast 关库，退出 0，原生 pg_controldata 读回 shut down。原 M5 源库的退出码仍为 1，验收依据为副本恢复。非作者复核后，两个平台库各 48 张表持续封闭投递，三库连续三轮零在途并取得同栅栏独立放行。M4 源库、M5 平台库、M4 平台库依次由 UID 999 请求有界 fast 关库，三个当次日志均有关闭完成标志，容器均退出 0，逐卷原生控制文件均为 shut down。

14 个原容器已退出并保留。13 个按停止验收通过，包含 8 个常规停止、3 个 PostgreSQL 原生 fast 关库及 2 个 Fuseki 替代验收；另 1 个按已批准的单卷恢复例外通过。非作者复核九份私有归档，共 863528960 字节。最后完整回读八卷通过后释放了准确的临时只读持卷容器。Docker 回读运行容器为 0，调前 VM 内存为 16787419136 字节，CPU 为 12。下次恢复旧栈须按[原 ID 与恢复顺序](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/r0-review.json)先恢复并核验八个易失卷。见[本轮机器回执与非作者结论](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/readmission-03.json)和[14 项定向测试](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/readmission-03-validation.json)。

用户手动将 VM 调至 20 GiB / 12 CPU 后，按已审公式重新读回 Docker 额度、宿主余量和阶段峰值，满足条件才启动 S0。正式 prepare 仍由现有 SHORT_REPRO_REQUIRED 保护。S0–S3、产品验收与最终 V3 待后续实施。

## S0 真实源观测与取消阻断（2026-11-18）

Docker 引擎实读 20964958208 字节（19.525 GiB）、12 CPU。旧 14 个原容器仍退出。宿主为 32 GiB / 12 核。S0 两节点配额 10 GiB / 4 CPU，保留 2 GiB 后剩余 7.525 GiB。后续六服务的 14.25 GiB / 9 CPU 纸面额度扣除同一预留后剩余 3.275 GiB；后续宿主进程、临时负载及真实延迟仍须按阶段核验。首次内核探针发现 max_map_count 为 262144。按用户追加授权调整后，两次非特权回读均为 2000000，VM 无 swap 设备，nofile 软硬值均为 65536。

任务独立的 FE/BE 均报告 doris-4.0.8-rc02-bc8ea1bac6d。原生 MySQL 客户端严格核验 CA 和 localhost 身份后，证实两表 UNIQUE/MOW 三列键、整行 upsert、精确大额小数、微秒第六位、BIGINT 边界与同站点的 T1/T2 关系。两次 SELECT 之间受控写入可见，已复位并保留 UNKNOWN/null 水位。第一次在 BE 注册前运行 SELECT 的 1105 失败保留。正式目录发现、产品类型拒绝和激活后 NULL 场景尚未运行。

取消见证绑定 reader 自己的连接 60 和源 QueryId ebdb6844fe824e68-8774daafa439a615。同账号 KILL CONNECTION 在请求后 37.133ms 获确认，FE 随后计数为 0。请求后 304.005ms 的独立观测仍有 1 个 BE 活动任务。较晚的单独读回为 FE 0 / BE 0，确切终止时刻未知。250ms 清理门禁未通过，1000ms 分支和 5000ms 总预算保留原值。非作者裁决 S0 BLOCKED。MySqlConnector 正式路径、五秒端到端取消及 S1–S3 均未获验收。正式 prepare 原入口返回 SHORT_REPRO_REQUIRED（exit 2），180 秒失败身份和 15 秒诊断成功身份分列。

本次合成源已按准确进程发送镜像优雅停止信号。BE 退出 0、FE 退出 143，均无 OOM；FE 应用关闭钩子完成情况未知。4 个源数据及日志卷保留，当前运行容器为 0。详见[实测回执与非作者结论](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s0-source-review.json)和[离线反例回执](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s0-validation.json)。

## S0 正式驱动复测（2026-11-18）

正式 prepare 的原 SDK 命令退出 71，原错误为外层沙箱拒绝 sandbox_apply。非作者核对了原错误输出和候选状态副本。现有公共短复现入口按同一 180 秒身份持锁运行原隔离命令，14 秒看门狗内实测 0.220 秒、退出 0。正式 prepare 随后返回 DEPENDENCIES_READY，零下载，验证 21 个项目的资产。早期 15 秒诊断的不同身份保留在原件中。

源码 cf02313240b00cd74704859700128c5f7d1fd390 上的正式 MySqlConnector 2.6.2 测试读到 E1 的唯一逻辑行、精确金额 9007199254740993.20 与 123456 微秒，两表三列有序键和 UNIQUE/MOW 均匹配。取消测试使用同账号、同固定 FE 和本次真实连接 52。独立观察者匹配 QueryId e5f15ab3fbd44503-bafbb4493f6c778c。取消后约 18 毫秒驱动结束，20.683 毫秒后分支返回 query_source_unavailable。250 毫秒截止后仍观测到 BE 任务，耗时随后继续增长。BE 收到取消后约 2.924 秒进入 fragment 析构，统计行的耗时冻结后仍存在；取消后约 4.316 秒首次观测 FE/BE 双零。

非作者复核类型测试一项通过，取消测试一项失败，五秒内的事后观察与源清理分列。S0 继续阻断 S1–S3。待裁决仅涉及取消资格的 SQL 计划范围及代表性证据。单行 SLEEP 在该版本内不能及时中断，若裁定以允许的固定业务计划验证，仍需运行中取消及独立 BE 终结原件，沿用 250ms、1s、5s。此次实测未给普通业务投影作出可取消性结论。两源节点与旧十四个准确容器均已退出，四个本任务卷保留。本轮未构包。[正式回执与非作者裁决](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s0-driver-review.json)。

## 固定 SQL 取消见证（2026-11-18）

用户已将放行范围限定为产品生成的固定 SQL。SLEEP 的历史失败作为版本能力边界保留。本次源码为 f642666c2353fe3c8e7c504be4b6287ff4e65ffe，采用两张原表、每表恰好100个合成逻辑行、独占同账号辅助 TLS 连接；就绪的独立旁路按准确 QueryId 观察 BE。固定 SELECT 的结果缓存仅对本语句关闭。正常测试读回 100 个实体及两条符合精确等值和半开关系的目标 T1、T2。

最终两个计划在 BE 注册到上下文析构之间分别经历 2.200ms、2.339ms。应用在取消后 6.5965ms、3.9266ms 返回不可用。实体缺少同 QueryId 的用户取消到达事件；关系的取消到达比上下文析构晚 0.105ms。两项 MTP 都因缺少运行中源任务被取消的证据而 exit 2。四组构建、各自见证、源事件及四次数据复原见[固定计划机器回执与非作者裁决](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s0-fixed-plan-review.json)。非作者裁决 S0 BLOCKED，S1–S3 尚未放行。收尾时四个源卷保留，准确 2+14 个容器均退出。此前成功构建的滚动绑定文件已由正常构建更新，原 SLEEP 失败与本次全部失败原件分别保留。

## S0 非作者放行与 S1 准入（2026-11-19）

固定计划的独立取消压力验证在两表各 65,536 行时进行，随后恢复原行及散列。最终构建七项定向 MTP 各 1/1，正常成功门禁仍为每表最多 100 行。实体、关系从请求到最晚清理分别为 4.7634、3.7644 ms。实际同名表模型及类型反例被拒绝，两个负例都恢复原 tablet。AC11 在两次正式读之间有独立已提交写入，微秒时区解释明确，水位仍为 UNKNOWN/null。非作者批准进入 S1。源证据不能代替正式产品发布与恢复。[原件索引与独立结论](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s0-qualified-review.json)及[定向验收](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s0-qualified-validation.json)。

## S1 单表放行与 S2 正式取消复核（2026-11-19）

从 M5 平台 PG 的只读原卷制作私有隔离副本，原镜像只核对指定历史行 `ma-ace12515d7804af2870f2a434c167951`。其 2,509 个规范字节与历史 ContentHash 和 golden 逐字节一致，SHA-256 为 `b97c13b97057f7fb5c0c9119aaa0b0a0f3db9525e87dc53e5bbdb263c03e7665`。standard 与 numeric 两组 manifest/result 的定向 MTP 为 2/2，零跳过。强后验核实两个临时容器与临时卷均已回收，原库保持原停止时间，当前六服务均在运行。[隔离核验与源身份](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/pg-standard-assessment-origin.json)及[资源后验](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s1/pg-golden-postcheck-f23591fea356468097da52c352bcfe89.json)。

正式发布后 Q 读到 E1、9007199254740993.20 K 与六位微秒。重新启动 API、建立新 OIDC 会话，恢复结果 SHA-256 为 `29dbbfbb1fc4a232477fa47806d53f6a8c1eaa23a2e7516d255a52627ce0e3a0`。FE 独立阳性对照增加一次业务读，四个恢复观测均为 22 次并具有相同 QueryId 集合。[S1 非作者放行](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s1-qualified-review.json)。

S2 已通过双表正式发布与激活。SQL 与整数系数参考及 Q 的实读均得到 T1、T2，T3 不等、T4 为 NULL、T5/T6 恰好相接均被排除。另起评估包含 T4 的两表，收到 `mapping_relation_endpoint_unknown`。三项现行授权逐项撤销并准确恢复；拒绝执行前后 FE 业务读数均为 32，历史结果恢复字节相同。[S2 原件索引](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s2/index.json)。

正式取消试验的 BE 执行窗口为 7.527 ms，取消接口返回 409 `query_already_finished`，原查询成功提交并留有一次成功审计。两表压力数据随后按准确键及原行散列复原。非作者裁决 AC06 NO-GO。现有两秒心跳晚于一秒源分支期限，持久化 fence 保护和源端及时终止须分别核准。250 ms 清理、1 秒分支、5 秒总预算继续生效。V3 小样测量因两个用户未跟踪文件触发 DIRTY_TREE，待选择测量检出方式。S3 长链与最终打包尚未开始。

第 10→11 个关系目标的真实反例暴露两处缺陷。查询展开增加了逐父检查后，第 10 条仍完整返回，第 11 条使结果变为 PARTIAL，只保留可信的根实体。Mapping 原先用词法比较 1.00 与 1.000，两侧计数都为零，错误返回 READY_FOR_PROPOSAL。旧评估和短定位命令均已保留。限定 Doris 精确十进制比较、独立从目标侧对账后，四个正式主体重新执行双表发布与激活，得到 release-1511432536e64f64b652b5f250661ff1。重验得到 T1/T2、NULL 拒绝、授权拒绝前后业务读数 46→46，以及 11 条时 mapping_fanout_exceeded 和 active 404。两次扇出场景均按九个准确键复原，原行散列相同。[修正前后及复原原件](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s2/index.json)。

## S2 版本竞争与获批的独立取消观察（2026-11-19）

四个 OIDC 主体使用正式服务参与者。真实源读取后，激活修订 1→2→3 回到同一 release，同一 query 在 1,386.3842 ms 得到 409 query_binding_stale。拒绝当刻为 RUNNING，结果、已提交读取回执、成功审计均为零。先前浏览器取错 ActiveView 字段与 MTP 工作目录错误原件保留。非作者核准此次受控时序的限定结论。

每 10 ms 的独立只读观察已在正常根与关系分支实测 8 和 3 次，单次最长 2.4733 和 3.1354 ms。两个真实时钟迟滞反例均在分支预算内失败关闭。数据库永久失联时迟到任务的资源释放时刻仍未知。等待 FE 实际检测业务查询后投递正式取消，返回 409，BE 自然窗口为 8.152 ms。另一次在平台准入后立即投递，取消 HTTP 200、原查询 HTTP 409、数据库 CANCELLED，结果、读取回执及成功审计均为零，取消审计一条；BE 在取消提交前已经自然结束。两项各自保留。八批普通装载后固定查询自然窗口仍仅 7.743 ms，按预设停止条件结束，两个表的准确键及原行散列均已复原。非作者保持 AC06 NO-GO。

生产 MemberPlan 首次在原树因未跟踪文件返回 DIRTY_TREE；同 Head 的干净检出命中凭据扫描器对测试源码中运行时文件读取表达式的规则。非作者定位是源码假阳性。改为在连接握手时提供凭据后，干净的提交 3f1cac15ffaaa73393b61b3536168e2993801a48 上 MemberPlan 通过；MeasureOnly 实测候选 5,922,914 字节，三个逻辑原件均核到实际载荷和逐字节 SHA-256，未生成产品 ZIP。全部原件索引见[并发及取消非作者复核](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s2-concurrency/index.json)。

已核准同一查询的第二组 ABA 时序。修订从 3→4→5，同一 release 的 activation 发生变化，在 1,372.9755 ms 返回 409。独立撤权场景在真实源读后撤销两条准确 execute grant，8.551 ms 后提交被拒（403 query_forbidden）。两种拒绝当时均为 RUNNING，零结果、回执与成功审计。恢复两条原授权后，Q 再次取得相同结果字节。宿主观察日志记录的是浏览器前件，其 queryId 与受控竞争不同。独立正常行数场景验证 EMPTY、两个真实候选 AMBIGUOUS、源 SELECT 撤销时当前与历史访问拒绝，以及不同实体键共享关系值时的多父 Mapping 拒绝。源测试行和 SELECT 均已恢复。

另一条单独查询在真实读完后只将同一合成 Q 会话改为已过期。在 13 ms 内确认到期更新完成，约 7 ms 后事务拒绝提交，403 query_forbidden，零结果、回执及成功审计。准确会话按原绝对时间比较恢复，正式浏览器重读前件字节一致。[并发证据索引](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s2-concurrency/index.json)。

### AC06 单表分级压力终判

用户批准只扩大实体表。目标始终为 T1/T2/T3，实体总数 262,144、1,048,576、4,194,304 时，独立 BE 注册至析构分别为 13.574、24.080、31.925 ms。平台取消此前约需 146 ms，三档均低于预设的 160 ms 可测窗口，故本批没有追加正式取消。每档恢复原始 1 个实体和 3 个目标，原行散列一致。非作者核过 4、16、64 个连续准确键区间，三级均维持 AC06 NO-GO。最大档结束前 BE 容器历史内存高水位为 3,339,681,792 字节，恢复后 BE 存储为 267,325,440 字节；逻辑数据已复原，物理 rowset 有变化。文件与目录同步的补强晚于试验，崩溃恢复没有实测。[三级机器台账](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s2-concurrency/s2-entity-tiers-75f1a625719d.json)。

正式审批在原始两表上通过。类型与模型分别变化后，C 两次激活均返回 409 mapping_activation_check_failed，之前的 release、activationId 及修订 5 保持一致。变更期间，当前权限不足以查看失败检查的源细节，读取返回 403。原 tablet 与行散列复原后，按同一 checkId 回读到原先记录的 NOT_RUN 与 mapping_source_shape_invalid。两个场景中目录均可见临时交换表，不能从正式激活拒绝单独归因于模型。源端单独模型拒绝见 S0。首次试验误期望检查在源变化期间可读，其失败原件保留。

收口时原 14 个容器均已按 ID、镜像及退出状态回读。新任务 FE、BE 已用 TERM 优雅停止，保留四个卷。平台 PG 的三项在途计数均为零，执行 pg_ctl fast 后，docker exec 客户端退出码 137，数据库容器退出码 0、无 OOM，且日志含数据库已关闭。其持久卷仍在。Keycloak、Fuseki、RustFS 继续持有本任务的三个易失卷，待复审确定后续保全或处置。没有运行中的本任务 API、编译器或压力夹具。S3、CI、完整产品验收及最终 V3 尚未运行。


### 同请求发布核验与 S2 接续

用户批准在同一取消请求中复用已核过的发布对象及同批实际图。正式目录按当前主体核权限，RustFS 字节与 PG 原件逐槽对账，严格 UTF-8、快照绑定、RIOT 和真实图 SHACL 均执行。请求结束时不保存图或验证结果供下一次请求复用。三次完成态正式取消耗时 75.329、66.352、65.939 ms。最近一次发布核验本身仍需约 54 ms。独立复核维持 AC06 NO-GO；现有数据不足以在已审 31.925 ms 窗口重开正式竞态。此前运行中请求先后胜负、三个压力档和 SLEEP 能力边界均保留。

AC04 在途读取后正式轮换凭据版本 1→2、连接修订 2→3，同一查询 409，随后同一连接重新发现、异人审核并激活双表，新结果与历史原字节均已恢复。AC05 同一查询数据行返回后、目录后验前改列名，422，拒绝当下无结果、来源回执或成功审计。AC08 仅使一次性查询到期，结果和证据均 410。AC09 中断准确源连接后结果为 UNAVAILABLE，业务行、证据和来源回执均为零，执行记录为 COMPLETED 并有一条 allowed 审计。准确列宽 512 的负例在源投影前拒绝并恢复原表。早先总截止实际返回 5029.368 ms；最终事务从五秒内部预留 100 ms 后，真实短锁和近截止竞争分别用时 2537.7962 和 4927.9878 ms，两者均返回 503 且无成功副作用。六条定向拒绝记录最终均为 FAILED。独立真实第 101 行仍待取证。

正式受影响计划在干净代码提交上覆盖 243 个路径，未知为零。产品门禁与 S3 准入另行核定。收尾回读确认旧 14 个实例继续 STOPPED_KEEP；本任务 FE、BE、持久平台 PG 已停止，三项易失服务持续持卷。完整验收、最终 V3 与同包重开仍待 AC06 和后续阶段放行。[本轮原件索引及非作者结论](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s2-followup/index.json)

### 2026-11-19 独立第 101 行反例与新的取消时序

正式查询 query-48fd26ca6f92465899394df114ff3aa1 使用当前双表绑定、站点过滤和 maxRows 100。实体装载为 101 行，目标保留 3 行。HTTP 200 返回 UNAUTHORIZED，来源 FORBIDDEN，无来源回执。查询时 Q 的三项连接授权均已自然到期。已按 100 个准确复合键恢复，实体 1 行、目标 3 行，两表原行散列均与装载前一致。非作者确认恢复通过，哨兵未获验证。正式取消的新时序仍待具备当前授权的同一主体实测。[哨兵请求、恢复和权限原件](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s2-timing/index.json)

补入正常单行 E1 的正式执行、历史结果与证据回读，作为后续装载前件。新取消试验在准确行锁处同步，保留真实核验、事务与驱动。非作者静态同意在有效授权下作有界实测。当前尚无新时序的运行结果。已按零在途收口，旧 14 个与本任务 FE、BE、平台 PG 继续 STOPPED_KEEP，三个本任务易失卷仍由原服务持有。

### 2026-11-19 限定重授及实测

同一 Q、连接及原十八个字段的三项权限重授四小时，旧行与审计保留。单行执行、结果和证据回读全部通过。独立 101 行查询返回 AMBIGUOUS、limited、100 个准确候选和 100 项证据，业务数据为零。准确恢复实体 1 行、目标 3 行，两表原行散列一致。非作者确认本查询哨兵通过。[当次原件及复核](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s2-timing/renewed-sentinel-review.json)

首个新时序中，正式取消 HTTP 200，查询终态 CANCELLED。结果、来源回执与成功审计为零，有一条取消审计。测试调度早于源读取的再次治理授权，与已获治理锁的取消事务相遇，业务 SQL 未在 BE 执行。原失败保留。同步已移至正式 MySqlConnector 物理业务命令发出前，源端再次授权、握手和目录前验先完成。[首试原件](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s2-timing/overlap-first-review.json)

第二次试验中查询 query-66dfd106112b424b80dc90c5a214eda8 通过真实权限、发布和事务核验。PG 先读见 CANCELLED，随后同一 BE 收到 KILL。分片 0 此前已自然析构，分片 1 收到用户取消、向协调器报告取消错误并析构。全查询上下文于解锁前保守锚点后 43.033 ms 析构，分支上界 304.9061 ms、总耗时 769.7025 ms。无结果、读回执或成功审计，取消审计一条。原门禁缺调度器任务取消事件及 250 ms 内 FE/BE 双零。最后采样为 0/1，后置读回 0/0。独立正常完成对照的统计行在 1529.729 ms 仍存在，2035.838 ms 采样才消失，期间任务时间、CPU 与扫描行数保持不变。非作者维持 AC06 NO-GO。两批压力夹具均按准确键复原。S3、CI、最终 V3 与同包重开仍未运行。[精确查询原件与复核](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s2-timing/overlap-command-review.json)

### AC06 独立源端取证与正式连接 Profile

平台查询 `query-89e22e5c058a4c3ca6c12977f73e8c93` 对应源 QueryId `5d120076dc124651-99c14320eb5fd255`。平台读见已提交取消后，BE 收到用户取消。独立 BE 任务视图覆盖两个实例、三个任务，28.962 ms 内清零。FE 以用户取消结束并返回零行，终态上界 28.745 ms，独立活动视图消失上界 44.661 ms。分支 272.0526 ms，总耗时 723.5581 ms。结果字节、来源回执、成功执行审计均为零，取消审计一条。旧统计视图在 250.226 ms 仍为 0/1。

非作者将原生日志的三个工作线程对到两个实例。单任务实例的关闭原因已确认。双任务实例的两条关闭事件各自缺任务编号；该 QueryId 的 FE 归档目录亦无 Profile，目录内已知控制归档可读。独立复核给出七项通过、一项缺证，正式浏览器失败，定向 MTP 1/1。此前的失败、同主键复原台账及运行输入均保留。[124f 原件与复核](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s2-equivalent/index.json)

用户随后允许在独占 FE 的正式主连接握手窗口临时启用 true/3，结束即恢复，并用新连接回读。第一次限窗 50.240 ms，只有主连接 254 继承设置，新连接 255 读回全局和会话均为 false/1。准确源 QueryId 的 Profile、FE 审计与流水线算子一致，实际返回 101 行；KILL 晚于 BE 上下文自然结束。第二次限窗 41.039 ms，源 Profile 同样记录 101 行。观察器读到 BE 日志文件尾部尚未换行的部分时退出，此次未取得完整平台时序。两次压力夹具均已复原；这些试验各自保留 NO-GO。

当前授权内的并列时间压力变体仅统一新增合成实体的 event_at，目标仍为原三行。产品固定 SQL 继续使用实体键打破并列。试验先测注册到最早分片自然结束的时间；在现行前置权限核验与取消事务已进入准确锁的时序下，使用 50 ms 作为是否值得发起正式竞争的试验下限。早期 160 ms 下限及其当时约 146 ms 的完整平台路径保留在原规格。验收始终以同一查询的正式提交、逐任务因果、零成功副作用及 250 ms／1 s／5 s 计量。

AC06 经非作者重开通过，正式取消提交先于同一查询的源端终止。FE 和 BE 上界分别为 34.370667 ms 和 64.52009 ms，分支 366.3627 ms，总计 807.1056 ms，成功副作用为零。握手后的全局和新会话均已恢复 false/1。早期浏览器失败原件继续保留。[独立复核](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s2-equivalent/ac06-non-author-review.json)

### S3 正式消费者

MCP 三项执行及一项恢复共 125 条检查。查询页和映射编辑器 44 条，恢复及身份失效 46 条。客户端先保留正式响应原字节，再在刷新后比对。刷新前后的 FE 审计 QueryId 集合完全相同。真实撤销同一主体的 result.read 后返回 403 并清屏，恢复原授权后读回同一规范结果。两个标签切换身份时，迟到的原授权响应被丢弃。[最终产品原件](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s3/product-inputs.json)

受影响回归包括 PG/Doris 适配和分发 42 项、实际 Doris 认证及 TLS 与固定源读 4 项、Query 23 项、wire 6 项、发布批次 4 项，另行重开 PG 两组黄金字节。Web 的类型、lint、22 项单元和生产构建均通过。第一个 MCP 拒绝、刷新失败、Web 宿主退出超时和误选 100 行夹具的回归继续保留。旧十四个容器为 STOPPED_KEEP，本任务的三个持久服务已停，Keycloak、Fuseki、RustFS 继续持有易失卷。[收口回执](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s3/continued-platform-keep-8a6e2624592041c194d3cf372dadca26.json)

工程静态检查首次在 17 份历史 JSON 的末尾换行和夹具的一处凭据读取表达式处失败。17 份历史原件已按仓库标准恢复并与原 Git 对象逐字节核对。PG 黄金用例读取无损封装，保留数据库原始 2509 字节与独立 ContentHash。夹具改动前后 Python 语法树完全相同。生产代码和 Web 输入均未改变，更新后的 QueryTests 独立重验。[原件恢复映射](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/historical-byte-mapping.json) · [定向重验](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/s3-requalification/product-inputs.json)

### 本地交付绑定与复审关口

实测提交为 `3790ead2dd8ce33db432c5b7cb345786a2e697cc`。干净检出上 556 个变更路径全部归入受影响计划。11 项工程门禁重新执行，5 项产品门禁重新核验实测原件，16 项均通过。另对本批 33 份 C# 文件核验 Roslyn 空白格式。AC06 和 S3 的独立复核以及随后 17 份历史原件的字节复核均已签收。最终 V3、分支实际交付 Head、同包独立重开与普通推送后回读由包外回执绑定。当前决定仅涉及本任务的 Doris 切片。[本地验收](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/final/validation.json) · [工程执行回执](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/final/workflow-receipt.json) · [最后一次非作者变更复核](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/final/non-author-review.json)
