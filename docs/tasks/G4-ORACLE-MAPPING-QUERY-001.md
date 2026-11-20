# G4-ORACLE-MAPPING-QUERY-001｜Oracle Mapping/Query

唯一任务状态 **AUTH_HANDOFF_REVIEW_BLOCKED**。源读取及正式结算已修改。替代 API 的当前资源窗口已按身份登记，真实 PG 三态锁内截止通过。按用户最终限定，本批另已核实一个重置账号的正式 /me 和登录审计。详见[本批报告](../evidence/G4-ORACLE-MAPPING-QUERY-001/product-resume-01/report.md)。本批按 [唯一 A–F](../evidence/G4-ORACLE-MAPPING-QUERY-001/contract-admission-request.md) 的 AC03-A/C 决定 S1 准入，S1 通过后才进入 S2/S3 功能验证。AC03-B 及 Oracle S0 仍 BLOCKED，G4 PARTIAL，AI OFF。

## 执行身份与所有权

当前项目会话、本机 Code/Agent，Master 集成，P0 非作者为 `/root/pg_coupling_facts`，S0 独立只读审查者为 `/root/spec_review`。P0 Base 为 `5168f2c93ca226caa521a6dc4ac85439335274c4`，分支 `codex/g4-oracle-mapping-query-001`，托管工作树 `/Users/chasen/.codex/worktrees/g4-oracle-mapping-query-001/ontology-platform`，operationId `bf751e90-6c75-4102-a34a-7184c735a5c3`。本机 macOS ARM64，Docker VM Linux ARM64。本次使用现行会话配置。实施起点 `8ddaabb90878d5ab72a92908a030b7397c6f2d4d`。本轮为 implementation-01。

P0 的文档归属为本任务卡、[唯一 A–F](../evidence/G4-ORACLE-MAPPING-QUERY-001/contract-admission-request.md)、[事实索引](../evidence/G4-ORACLE-MAPPING-QUERY-001/facts.md)、[非作者 Review](../evidence/G4-ORACLE-MAPPING-QUERY-001/p0-review.md)、[当前授权](current-authorization.md)、[G4 规划](../planning/g4-implementation-plan.md)与 [Doris 卡末尾的集成追加记录](G4-DORIS-MAPPING-QUERY-001.md)。回执为 ignored。read_only_dependencies 为本轮 owned_paths 以外的产品、合同与门禁，以及锁、迁移、旧证据、既有资源和冻结架构。本轮实施 owned_paths 由唯一合同 C 的精确改动图、现有 preflight/prepare/verify/证据消费者、任务专用夹具与受影响测试确定。Master 单写共享路径；历史证据、旧资源/密钥、锁、迁移只读。

本轮最小正式根采用附件批准的独立托管写者。Connections 源绑定及其专用测试归 `codex/omq-source-bindings`，SemanticQuery、G4 HTTP/MCP 原期限与占位及其专用测试归 `codex/omq-deadline-store`。Master 独占共享 Contracts、组合根、工程入口、设施与当前任务分支集成。非作者审查者只读。两写者均不操作 Docker。

## 行为、最早验证与切片

| SDD 切片 | 关联 AC 与正式入口 | 当期资格 |
|---|---|---|
| S0 源能力及取消 | AC01–03、11。先验证 Oracle 类型、事务、受控固定 SQL、正式取消与独立源终态；不可观察即停。 | BLOCKED。固定 SQL 在正式取消提交前已读完；两表事务、直取消和 PG 占位子项已测。 |
| S1 单表 | AC04、05、08、10。沿正式发布、当前 grant、HTTP、真实平台持久化及新会话恢复 | NOT_RUN |
| S2 双表 | AC03、05–08。等值与半开关系、ABA、撤权、超量、原期限内清理和零成功副作用 | NOT_RUN |
| S3 消费者及兼容 | AC09–11。UI/HTTP/MCP 同源字节，PG/Doris 与 Oracle M2 的原身份对照 | NOT_RUN |

每个 AC 的正反 Given/When/Then、真实 DI、独立预期、原件、输入变化及最小重验在唯一规格 E。实施先补当前 TaskId 实际分发，旧 M2 的通过记录仅归原输入。源实例已有原生事务并发对照、固定游标自然完成及 ODP 定向取消原件。首次源冷备已在替代容器通过驱动重开。资源余量按当次准入记录，完整平台恢复仍待验证。

## 核验与恢复

本轮按 A/F 冻结 host-entry 与两内部网、API 内定向 relay、替代式恢复；按 A/B/E 验 11 列、激活后 NULL 注入、纳秒端点与显式驱动事务；按 C/D 验 HTTP/MCP 原期限、跨实例 Oracle 未确认占位与真实证据资格。S0 准入失败执行止损，真实通过再继续。原 Doris ZIP/回执及 Main 更新可由本树 `artifacts/reviews/G4-ORACLE-MAPPING-QUERY-001/main-update-receipt.json` 恢复；准确文档 Head、检查/推送/回读见相邻 `delivery-receipt.json`。历史数据和私有材料由原 Owner 保管。本轮实施完成后交付唯一最终 V3、同包重开和包外机器回执。

2026-11-19 非作者核对集中修订。已关闭所有权表述、C 表排版与旧准入时态意见。结论为 GO 进入条件执行，运行资格仍按每阶段当前原件判定。

本次 S0 最小正式根已通过真实 OIDC 登录、G3 发布、正式目录发现、Mapping 异人核准及激活。源业务读者与四个 OIDC 主体相互独立。首批 76、57、46 个检查分别属于 provision、mapping 和当期 ready，均按各自实测提交登记。正式取消与资源恢复条件见[阻断交接](../evidence/G4-ORACLE-MAPPING-QUERY-001/implementation-01/s0-blocked/report.md)。

2026-11-20，`s0-recovery-01` 起点为 `9de3b93a0dfddb948b4d68c61ad1b54ce84e0812`。实施占位入口封闭、内部维护 CAS 及 Run 较早截止。Master 独占正式资源操作、恢复审计白名单、预算器、备份和最终交接。原任务及操作身份保留，新增维护尝试分别登记。 Oracle S0 BLOCKED，AC03 未通过，S1–S3 未准入，G4 PARTIAL。

本批真实占位已完成 TASK_LEVEL_RECOVERY，替代栈已停止保留。RC05 的 OIDC 签名/角色和对象历史版本缺证，收尾 BLOCKED，S0 BLOCKED，G4 PARTIAL。[恢复报告](../evidence/G4-ORACLE-MAPPING-QUERY-001/s0-recovery-01/report.md)

s0-recovery-02 以 454d1a2f17581673cbbf44900a5fe241d603f5ef 为 Base。OIDC 与 RustFS 写者分别拥有各自维护 Python/C# 文本，复用已计量的 omq-deadline-store 与 omq-source-bindings 托管工作树。Master 单写实际维护分发、阶段预算、资源、测试汇总和交付。正常认证使用替代 PG 与 IdP，允许会话、审计及由正式票据生命周期引发的 epoch 变化。对象读取在实际及封存参考间串行。原五服务和原业务入口保持封闭。

本批认证窗口已关闭，0/4 个原主体完成新登录，OIDC 为 WAITING_FOR_USER_AUTH。RustFS 实际及独立封存参考各遍历三页，5 个版本、0 个删除标记一致。资源停止后态已核对，RC05 仍 BLOCKED。[本批交接](../evidence/G4-ORACLE-MAPPING-QUERY-001/s0-recovery-02/report.md)

product-resume-01 从 `4924f44ec1628b156d7e722513405bc13d376d8e` 开始。Master 负责证据消费、产品阶段准入、共享文件集成和真实资源。独立写者分别负责 Oracle 生命周期及 Connections/Query 回归、SelfTest 夹具及其执行预算。非作者先复核登录原件和竞态切片，再审实际交付。


## auth-handoff-01 执行追踪

Base `33e66879a6b48e25580f1623316b88fe5a5e85cc`；Master 单写 `workflow-m4-query.mjs`、Oracle fixture/plan/platform/evidence、受影响 tests、gate登记、本卡/当前授权/唯一A–F及本批三文件。其它产品、构建、依赖锁、私有材料、旧原件只读。非作者 `/root/auth_review` 只读审查真实调用链和原件。

固定执行顺序：auth → AC03-A natural-cancel → Mapping当前正式链核验／必要补齐 → S1 → reader-auth → s1-reopen。前后处理各60秒，auth600秒，四产品槽各180秒，新reader认证180秒，父截止1620秒。没有可选尾阶段。前置失败或取消不进入后续；产品5秒／源分支1秒／清理250ms不变。每阶段前重核必要会话与授权210秒；新reader会话只替换reader。auth不读源、不续授、不发布；恢复只读平台存储。

正反例由现有Node/Python框架定向回归：超过40秒人工等待后成功、提交后40秒与未提交区分、CSRF/me共用剩余期限、快速提交、取消/失败止步、实际驱动连续A/S1与新reader、真实外层/资格固定计划、替换阶段/父命令及越期拒绝。真实服务只在回归和非作者阻断闭合后开一次窗口。历史三次失败、旧1/1、S0/B阻断与cleanup NOT_QUALIFIED保持。

2026-11-20 auth-handoff-01 收尾：最终代码 `fdadc58f8be175090961c9fcee8af192cf6b790c`，62项定向及非作者21项通过。两次实际窗口各1/4，auditor原件提交后timeout，后续非秘密服务端记录invalid_user_credentials，过期未核实。用户明确授权再次有界登录及仅恢复原3持卷实例；原3已恢复且保护20项匹配，第三窗最终被归档device身份漂移阻断，未启动浏览器。任务5副本停止、2API已移除。唯一状态AUTH_HANDOFF_REVIEW_BLOCKED，历史失败及未资格不变。三份完整公开脱敏文件见 `docs/evidence/G4-ORACLE-MAPPING-QUERY-001/product-resume-01/auth-handoff-01/`；普通push回读后停ChatGPT复审。
