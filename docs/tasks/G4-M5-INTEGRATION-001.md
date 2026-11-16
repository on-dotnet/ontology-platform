# G4-M5-INTEGRATION-001｜工程入口收敛与PG整合

## 当前执行与授权
唯一状态：IN_PROGRESS；batchAcceptance=NOT_RUN；G4Overall=PARTIAL。2026-11-16人类明确批准[批次附件](../evidence/G4-M5-INTEGRATION-001/authorization.md)全部A/B/C；不再等待P0审批。

- Master唯一作者，Explorer只读覆盖盘点，Reviewer非作者独立预期/增量/最终审查；并发3。
- Base：`a6716b11c3795e5670c07f1ca37057e5649bed89`，已正常fetch核对；分支`codex/g4-m5-integration-001`。
- 托管树：`/Users/chasen/.codex/worktrees/g4-m5-integration-001/ontology-platform`，一次创建；原main与6个未跟踪DS_Store保持。
- owned_paths：本任务卡/证据；`docs/tasks/current-authorization.md`、`docs/planning/g4-implementation-plan.md`、`apps/web/AGENTS.md`；`scripts/maintenance/workflow.py`及最小context/helper/M5适配；`scripts/verify.ps1`、`scripts/validate-structured-files.py`、`docs/development/verification-gates.json`及直接回归；必要environment/web-cache/preflight/package消费者；既有PG整合模块必要修复由Master登记具体路径。
- read_only_dependencies：历史docs/evidence、旧ZIP/回执、M3/M4冻结合同/实现、其它KEEP。公共DTO/Schema/数据库/canonical/权限/5秒预算不变。
- 不更新main、不部署、不下载、不进入G5/G6/G7、不恢复TDengine；仅PG双对象受控路径，非PG mapping/query、双架构与生产不声明通过。

## Specify：可观察要求
| AC-ID | 行为/关键反例 | 最早验证/结果 |
|---|---|---|
| BI-01/02 | 当前授权/规划/Web事实准确，旧原文按固定blob恢复 | 入口检查/NOT_RUN |
| BI-03 | 默认代码路径与证据分离，历史执行依赖显式纳入；漏依赖拒绝 | context回归/NOT_RUN |
| BI-04 | 机器重算diff含删除/重命名两侧；文档产品0执行，fixture/合同使相关资格失效，未知拒绝 | 增量检查回归/NOT_RUN |
| BI-05 | numeric/ABA/授权/canonical/状态独立预期及失效反例 | [独立预期](../evidence/G4-M5-INTEGRATION-001/independent-expectations.json)，产品NOT_RUN |
| BI-06/07 | scenario-ready先于长链；错库/Owner在SQL前拒绝，运行快照不可变 | 定向正反/NOT_RUN |
| BI-08/09 | 正式G3→连接目录→Mapping→Gateway→UI/MCP→新会话恢复及撤权/回滚 | 新M5组合FRESH/NOT_RUN |
| BI-10 | 非作者规格→反例→代码→原件，发现闭环 | 进行中 |
| BI-11/12 | 唯一V3/非作者重开/包外JSON与准确效能/限制 | NOT_RUN |

## Plan与Tasks
- A1：收敛当前入口，历史精确Git索引；修正文档真实状态。
- A2：workflow只读context输出路径/来源/遗漏，显式evidence模式；登记历史执行依赖。
- A3：先回归失败→机器diff选择→原校验器增量入口→定向通过；保留Full/SelfTest，稳定工程输入一次完整工程验收。
- B：并行只读盘点原M5/S01–70与当前缩小范围；非作者独立预期先于作者PASS。
- C：A/B自动通过后最小M5准入、场景就绪、首条PG真纵向、风险组合；复用M4不可变构建/隔离库/分层资格。
- 最终：按影响验证→非作者审查→提交/push→输入绑定→唯一V3→非作者VerifyOnly→包外回执，停ChatGPT复审。

## Verify与恢复
先只读资源观测：M3/M4运行配额11.75GiB/11.5CPU，VM12CPU、共同上限14GiB；用户追加明确批准精确暂停6个M3容器，保留容器/卷/数据。M5≤7容器/6.5GiB/8CPU、宿主≤4GiB、总新增≤10GiB。能源策略实测AC sleep=0/displaysleep=10；长验收仍需有界monitor。

首次CLI先已有prepare幂等离线准备；没有M5消费者先做最小注册，不伪装M4。失败按PRODUCT/HARNESS/EVIDENCE/ENVIRONMENT/EXTERNAL记录原exit；FRESH/REUSED分列；CI及其它平台NOT_RUN。

恢复从本卡、[当前授权](current-authorization.md)、本任务证据与当前分支diff开始；不重复读历史会话。所有创建资源KEEP至本轮复审/准确回收，其他任务KEEP不删除。

B线盘点与本轮唯一矩阵：[acceptance.json](../evidence/G4-M5-INTEGRATION-001/acceptance.json)。B静态确认限定PG路径无需新合同；原S-50/56/62/64等缺口保留。A早审R1调度、R2反向链接已关闭；R3已改为实际命令来源资格，等待非作者核验。M5首次prepare下载0、依赖就绪；M3实际暂停释放5.75GiB/7CPU，M4保持运行。

本轮具体新增/调整邻接路径：workflow_context.py、workflow_pg_profile.py、workflow_m5_integration.py、WorkflowContext.Tests.py、WorkflowIntegration.Tests.py；M4执行/输入/证据/快照最小第二消费者参数；G4QueryPersistenceTests/G4QueryMcpTests/G4QueryAbaRuntimeTests只增加精确M5测试身份。无产品DTO或生产代码修改。
