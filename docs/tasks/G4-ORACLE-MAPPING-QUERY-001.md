# G4-ORACLE-MAPPING-QUERY-001｜Oracle Mapping/Query

唯一任务状态 **P0_READY_FOR_ADMISSION_REVIEW**。截至 2026-11-19，Doris 已精确集成；本任务交付 Oracle 文档准入合同，产品实施待集中裁决。G4 PARTIAL，AI OFF。

## 执行身份与所有权

当前项目会话、本机 Code/Agent，Master 单写，非作者 `/root/pg_coupling_facts` 只读。Base 为 `5168f2c93ca226caa521a6dc4ac85439335274c4`，分支 `codex/g4-oracle-mapping-query-001`，托管工作树 `/Users/chasen/.codex/worktrees/g4-oracle-mapping-query-001/ontology-platform`，operationId `bf751e90-6c75-4102-a34a-7184c735a5c3`。本机 macOS ARM64，Docker VM Linux ARM64。本次使用现行会话配置。Stage=P0 / DOCS_ONLY。

owned_paths 为本任务卡、[唯一 A–F](../evidence/G4-ORACLE-MAPPING-QUERY-001/contract-admission-request.md)、[事实索引](../evidence/G4-ORACLE-MAPPING-QUERY-001/facts.md)、[非作者 Review](../evidence/G4-ORACLE-MAPPING-QUERY-001/p0-review.md)、[当前授权](current-authorization.md)、[G4 规划](../planning/g4-implementation-plan.md)与 [Doris 卡末尾的集成追加记录](G4-DORIS-MAPPING-QUERY-001.md)。回执为 ignored。read_only_dependencies 为全部产品/合同、锁、门禁、旧证据、资源元数据及冻结架构。公共合同 Owner 为 Master，当前授权只读。

## 行为、最早验证与切片

| SDD 切片 | 关联 AC 与正式入口 | 当期资格 |
|---|---|---|
| S0 源能力及取消 | AC01–03、11。先验证 Oracle 类型、事务、受控固定 SQL、正式取消与独立源终态；不可观察即停。 | NOT_RUN |
| S1 单表 | AC04、05、08、10。沿正式发布、当前 grant、HTTP、真实平台持久化及新会话恢复 | NOT_RUN |
| S2 双表 | AC03、05–08。等值与半开关系、ABA、撤权、超量、原期限内清理和零成功副作用 | NOT_RUN |
| S3 消费者及兼容 | AC09–11。UI/HTTP/MCP 同源字节，PG/Doris 与 Oracle M2 的原身份对照 | NOT_RUN |

每个 AC 的正反 Given/When/Then、真实 DI、独立预期、原件、输入变化及最小重验在唯一规格 E。当前产品准入适配器缺失，状态 BLOCKED；不借旧 G4-M2-ORACLE-01 身份。最早源端窗口、VM 实际余量、隔离恢复均待实测。

## 核验与恢复

只执行文档静态检查、非作者 Review 与 Git 交付。CI、产品、prepare/restore 均 NOT_RUN。原 Doris ZIP/回执及 Main 更新可由本树 `artifacts/reviews/G4-ORACLE-MAPPING-QUERY-001/main-update-receipt.json` 恢复；准确文档 Head、检查/推送/回读见相邻 `delivery-receipt.json`。历史数据和私有材料由原 Owner 保管。未来获准实施的交付沿用唯一最终 V3、同包重开和包外机器回执。
