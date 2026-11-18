# G4-DORIS-MAPPING-QUERY-001｜Doris Mapping/Query 规格

## 当前执行与授权
唯一执行状态：R0_HALTED_PIN_HELD。用户于2026-11-18批准同一会话/托管树/分支从7810f79227ea2e203fab8bdce60e4c29a1842110实施。分支codex/g4-doris-mapping-query-001，主线基线606ca2d2c61964e6498dd72d5e9ad960d3593bf7。实施EvidenceRunId=implementation-01；既有资源Owner保持原身份。

Master单写。owned_paths 为[唯一合同C2/F2与集中裁决](../evidence/G4-DORIS-MAPPING-QUERY-001/contract-admission-request.md)列明的源、测试、最小任务注册和当前文档。历史PG规范字节、旧ZIP与私有设施为只读依赖。R0允许14个准确ID在保全、排空、恢复清单与非作者检查后优雅停止。用户随后手动调VM。当前其他旧KEEP受保护，本分支不合main。

## Specify：可观察要求

| AC-ID | 行为与正反Given/When/Then（完整场景见规格E） | 实现/测试位置 | 最早验证层/结果 |
|---|---|---|---|
| AC01 | 已发布且完整授权则查询成功；错用途/未发布拒绝 | MappingValidationService/QueryBindingReader，DorisMappingQueryTests（拟新增） | 正式发布+真实Doris，NOT_RUN |
| AC02 | decimal同值异scale连边；不等/NULL不连 | DorisQueryReader（拟新增）/G4QueryTests | SQL独立预期，NOT_RUN |
| AC03 | 全集唯一身份可发布；身份碰撞/未知表模型拒绝 | DorisMappingSourceValidator（拟新增） | 源真实行，NOT_RUN |
| AC04 | 当前授权有效可提交；撤权/轮换先提交无成功副作用 | G4QueryAuthorizationTests/G4QueryRaceTests | 独立连接因果链，NOT_RUN |
| AC05 | 元数据兼容可用；列/模型变化旧批准拒绝 | QueryBindingReader/新Doris测试 | 源目录，NOT_RUN |
| AC06 | 完成读取正常返回；取消/断开不得EMPTY或迟到成功 | G4QueryHttpTests/新Doris测试 | 源端取消，NOT_RUN |
| AC07 | 当前activation可提交；同query ABA拒绝 | G4QueryRaceTests | 两正式参与者，NOT_RUN |
| AC08 | 新会话恢复原字节；撤权/到期拒绝且不业务重查 | G4QueryPersistenceTests | 真实平台PG，NOT_RUN |
| AC09 | 六态/可信前缀正确；超预算无COMPLETED | G4QueryTests/G4QueryWireTests | 实际deadline，NOT_RUN |
| AC10 | HTTP/UI/MCP相同结果；PG旧字节不变 | G4QueryMcpTests/既有Web测试 | 正式消费者，NOT_RUN |
| AC11 | 分别读取记录真实窗口；不盖虚假snapshot | 新Doris测试 | 最短版本探针，NOT_RUN |

## Plan：最早真实风险路径

最高风险为PG事务/证据标签误移植、Doris取消尾部超5秒和精确decimal关系。先冻结B/C合同，首个单表正式发布→查询→持久→新会话恢复前先证明原预算内源取消。正式DI/工厂/provider/权限/审计复用，不用测试替代构造证明真实链。证据按F2复用现有schema2/资格/小样预检；资源不足与当前任务消费者缺失是实施BLOCKED条件，不阻止本轮规格交付。

## Tasks：按行为纵向拆分

| 切片 | AC与成果 | Owner/路径 | 正反验证 | 当前结果 |
|---|---|---|---|---|
| A | 精确工程main更新 | Master，既有主树 | 原件/祖先/握手/回读 | COMPLETE，包外机器回执 |
| B | 唯一规格和独立审查 | Master，owned_paths | 文档轻量核对 | COMPLETE，静态可交裁决 |
| S1 | 单表发布/读取/恢复 | Master，规格C2/F2 | AC01/04/06/08/11 | NOT_RUN，待R0/S0放行 |
| S2 | 双表精度/模型/并发 | Master，同上 | AC02/03/05/07/09 | NOT_RUN，待R0/S0放行 |
| S3 | UI/MCP/PG兼容/最终V3 | Master，同上 | AC10/受影响门禁 | NOT_RUN，待R0/S0放行 |

## Verify与恢复

自本卡、唯一规格和implementation-01原件恢复。按R0→S0→S1→S2→S3验证；产品资格、最终V3与CI尚无本Run结果。原整集-9/TIMEOUT和134唯一覆盖保留。未跟踪用户文件保持原状。

R0原件及非作者结论见[14个准确ID与保全缺口](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/r0-review.json)。第一次中止时，14个原ID中，M4主/次API已请求TERM、自然退出0，其余12个仍运行。8个易失卷热备及隔离同ID恢复通过，两份隔离H2读取原夹具realm通过。用户批准的改序由非作者现场放行后，M4 keyring已取得冷副本并独立核验。准备处置M5前排空检查触发DRAIN_ACTIVITY_DETECTED，剩余处置中止，八卷继续由准确只读容器持有。非作者现场复核结论为NO-GO继续停机或调VM。20轮事后采样及单独补核MappingJobs/MappingOutbox均为零，触发时具体活动UNKNOWN。见[停机与独立复核回执](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/cold-save-review.json)及[恢复保护反例](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/cold-save-validation.json)。现VM仍15.63GiB/12CPU，暂缓用户手调。离线准备与定向检查见[当前验证](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/validation.json)。SDK短诊断通过，正式prepare受原失败保护拦截，C#未编译。S0及后续产品链均NOT_RUN。

## 本次剩余12个ID重新准入（2026-11-18）

准入回执 SHA-256 为 `67415b09491a84605a77a7cedfeaf27835b1bfd308182e75859e4a66926cab95`。两个平台库各48张表处于准确栅栏事务内，三轮连续观察四库分项均为零，包含MappingJobs和MappingOutbox；非作者放行同一栅栏内的余12个原ID。

第二次中止时，累计6个原容器退出、8个仍运行。4个API退出0，M4 Keycloak退出143并有关闭记录。M4 Fuseki退出143、无OOM，其镜像配置关闭了根日志，未取得本次应用关闭完成的证据，处置中止。两套keyring及M4 Keycloak三份冷备已经过独立校验。M4 Fuseki原卷的两次完整摘要与已审热副本完全一致，其关闭钩子完成状态仍为UNKNOWN。原只读持卷容器持续保护八卷；未调整VM。当时的独立结论为NO-GO继续停机或调VM，分项结果、退出原件及复核见[再准入回执](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/readmission-01.json)，定向反例见[验证回执](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/readmission-validation.json)。

## 余8个ID接续与M5源库异常退出（2026-11-18）

两套 Fuseki 都通过用户批准的替代验收。原镜像隔离读取最终冷 TDB2，M4 的默认图为 0 行、命名图共 4291 行，6 个已发布图逐图匹配；M5 分别为 0 行、1461 行，2 个已发布图逐图匹配。两套应用关闭钩子均保留 UNKNOWN。非作者先复核替代验收前提，再核对同一批排空事务中两个平台库合计 96 张表的栅栏及四库连续三轮零在途，才放行后续处置。

八个易失卷的最终冷归档共 795217920 字节，已逐份复核长度、全字节 SHA-256、权限及隔离同 ID 恢复。两份 Keycloak 副本均读取到预期 realm。14 个原 ID 中已有 11 个退出，10 个达到本轮停止验收。M5 源 PostgreSQL 使用镜像配置的 SIGINT，Docker 停止命令返回 0，容器退出 1，未触发 OOM。Tini 报告信号转发权限不足。退出后只读解析原卷 pg_control 状态头得到 6（DB_IN_PRODUCTION），未检验全文件 CRC，WAL 恢复能力仍待验证。该退出单独记为失败。

非作者结论为 NO-GO。两套平台 PostgreSQL 和 M4 源 PostgreSQL 仍在运行，原持卷容器继续只读挂载八卷。VM 实读 16787419136 字节、12 CPU，暂缓调整。继续处置需单独裁决 M5 源库持久卷的隔离恢复与余三库的原生有界关库。正式 prepare 仍为 BLOCKED / SHORT_REPRO_REQUIRED，S0–S3 及产品验收未运行。完整 ID、逐轮计数、冷备与停机结果见[第三次中止回执](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/readmission-02.json)和[定向测试回执](../evidence/G4-DORIS-MAPPING-QUERY-001/implementation-01/readmission-02-validation.json)。
