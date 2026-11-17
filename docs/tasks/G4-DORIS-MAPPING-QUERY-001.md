# G4-DORIS-MAPPING-QUERY-001｜Doris Mapping/Query 规格

## 当前执行与授权
唯一执行状态：SPEC_READY_FOR_CHATGPT_REVIEW。阶段A已完成；阶段B仅文档，非作者静态审查已通过，交ChatGPT裁决；产品实施NOT_RUN。

- 沿用当前会话，Code/Agent、Local Mac ARM64；不因附件建议另建会话或改模型。Master单写、只读Explorer和非作者Reviewer。
- Base：`606ca2d2c61964e6498dd72d5e9ad960d3593bf7`；分支 `codex/g4-doris-mapping-query-001`；托管树 `/Users/chasen/.codex/worktrees/g4-doris-mapping-query-001/ontology-platform`。
- TaskId=G4-DORIS-MAPPING-QUERY-001，RunId=merge-spec-01，创建operationId=`7d52da78-a971-43c1-a3df-de8eb7d0649e`。KEEP本树/分支至裁决和明确收尾；未集成且待后续实施，不能回收。
- 授权：2026-11-17用户明确批准附件工程增量合并＋规格批次；只允许main b5e3b65d1a3359e8fd778700f525321333df61d2→Base；不扩至新文档Head。本轮禁产品/DTO/DB/锁改动、下载/prepare/restore/服务/KEEP处置、TDengine/G5、产品ZIP。
- owned_paths：本卡、`docs/evidence/G4-DORIS-MAPPING-QUERY-001/contract-admission-request.md`、同目录少量事实/检查索引、`docs/tasks/current-authorization.md`、`docs/planning/g4-implementation-plan.md`。阶段A回执在主树ignored artifacts/reviews包外。
- read_only_dependencies：其余全部源/合同/脚本/部署/锁/历史证据/ZIP/私有runtime。公共合同Owner仍Master，当前无源码写入权限。
- 唯一规格：[A–F v1](../evidence/G4-DORIS-MAPPING-QUERY-001/contract-admission-request.md)；[只读事实与检查](../evidence/G4-DORIS-MAPPING-QUERY-001/facts.md)。附件作为获准范围来源，不将其所有背景建议当额外操作许可。

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
| S1 | 单表发布/读取/恢复 | Master，规格C2/F2 | AC01/04/06/08/11 | NOT_RUN，待裁决 |
| S2 | 双表精度/模型/并发 | Master，同上 | AC02/03/05/07/09 | NOT_RUN，待裁决 |
| S3 | UI/MCP/PG兼容/最终V3 | Master，同上 | AC10/受影响门禁 | NOT_RUN，待裁决 |

## Verify与恢复

当前产品TestedCommit=无；不把Base旧PG测试当新Doris资格。FRESH仅文档/只读检查，REUSED仅M5同包原件，CI与全部产品NOT_RUN。整集历史 -9/TIMEOUT 保留；134是唯一用例并集覆盖。新文档完整Head和远端回读在包外交付回执，不递归写进自身提交。

恢复从本卡/A–F/事实索引；源语义新决定、资源方案和实施授权待集中裁决。禁止自动开始S1、更新main或进入G5。旧KEEP全部不动，原主树六个.DS_Store已保护。实际Agent活跃耗时UNKNOWN；下载/产品运行/构包/服务处置次数均0，不宣称效率提升。
