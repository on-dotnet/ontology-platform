# G4-ORACLE-MAPPING-QUERY-001：EC-01、S2/S3 与 ABA 澄清交接

本批产品尚未完成。唯一任务状态 **S2_S3_WAITING_FOR_NORMAL_AUTH**：EC-01 已关闭，S2/S3 入口、独立预期与消费者已实施并获得限定准入；当前正常认证窗口到期且首角色未提交，0/4 认证，全部 S2/S3 场景与六条新组合 grant 签发均为 **NOT_RUN**。本报告不是 Oracle S0、G4 或完整工程 PASS。

Base `da0046433c87aec3b56a89f15953bfbd4114d9ca`；产品代码 Head `6d77931685a3d5c8a5a9ac68e9b1cf63df872d4b`；分支 `codex/g4-oracle-mapping-query-001`；产品 Run `product-resume-01`，批次 `s2-s3-01`，持久资源 Run `implementation-01`。交付 Head 为三文件所在的准确 Git 提交，普通 push/远端回读记录另存 ignored 回执。main/origin/main 保持 `5168f2c93ca226caa521a6dc4ac85439335274c4`。

## EC-01 与既有资格

原父命令 `47f4f5d4e2454a759bd3189a5b37f590`、原 TestedCommit `8f857969ad4fe08e43e5644d951bbf7532e3544d` 及六阶段原件保持原字节。消费者提交 `1a9361ec6de5fe40bc195a1406f8695b8a616c93` 强制所有阶段及父全窗审计不按 clientId 过滤，并比较完整稳定事件键、内容、半开窗口和时钟区间；父集合必须为阶段无重复并集，间隙读不得被过滤。

离线重新资格命令 `7795d4266f3945c3ba338644aa7d7d81` exit 0。非作者独立重开 170 件原件、623536 字节；索引 SHA `f5fca1f634c23cb1b8f43d681fe402bab60b8f27a432ef7ac2aaf263c3c9b950`。六阶段读数 `0/1/0/1/0/0`，父全窗 2，间隙 0。七类真实篡改反例拒绝。当前候选关键闭包未削弱，非作者追加 6/6 离线回归及 S2 前缀/间隙验证。此过程未重开旧登录或业务链。

已接受的四角色、AC03-A 成功先赢、S1、新 reader 原字节恢复及 AC03-C PG8 事实保留其原输入身份。AC03-B **BLOCKED**、B cleanup250ms **NOT_QUALIFIED**、Oracle S0 **BLOCKED**、G4 **PARTIAL** 不变。

## ABA 澄清及实际实现

唯一 A–F AC05 和任务矩阵已同步：撤销未定义的“两类全覆盖”，不设置第二类阻断。唯一必验 Mapping 时序为同 Q 捕获 A → 真实源读完成且未成功提交 → 正式激活 B → 正式回滚激活原 A（新 activationId、递增 revision）→ 同 Q 在原五秒内 `409 query_binding_stale`，独立确认零成功结果、零已提交来源回执、零成功执行审计。连接 ConfigRevision 反例及历史结果/旧 selection 分别验收，不计为第二类。Doris 两份历史原件是同一顺序两次实测，历史文件未回写。本批真实 ABA **NOT_RUN**。

已贯通 Oracle fixture → m4 实际分发 → platform → 正式 evidence 消费者及 preflight/gate 输入。新 planId `s2-s3-01` 固定十五槽，总 3240 秒；初始四角色认证 600 秒、提交后 40 秒，新 reader 180 秒，各产品槽 180 秒，当前会话/grant 余量至少 210 秒。旧 auth-handoff-01 计划 SHA `826aa393316000c6bc3fe7ce9017eab8f71db21ceb895893e39d5a22cafeecc5` 未变。产品 5 秒/源分支 1 秒/清理 250 ms 不变。

组合授权入口仅允许批准的一个连接、org-demo/site-a、两张 TABLE 各11列。每条新 grant 自身覆盖完整22字段；不能拼接两个单表授权。保留旧15行；另9项空对象/字段工作流权限只在自然到期时同范围追加。本次认证先失败，尚未调用该签发入口。

Oracle 双表投影和完整父/目标集检查已实施：交叠身份、多父、10→11扇出及预算边界；内部完整行载体 JsonIgnore，未扩公开 wire。Web 仅补 Oracle ACTIVE 来源准入。实际驱动包含正式双表发布、数值/时间/NULL/关系、授权/目录/ABA/连接版本、六态/100与一次101、新 reader、MCP四工具和 UI 恢复/撤权/迟到响应。独立消费者核固定字面量、真实源记录、完整证据引用和命令审计；未从产品输出生成预期。

## 当前实测与覆盖

| 范围 | 当前事实 |
|---|---|
| EC-01 | PASS，既存业务执行复用、消费者新资格 |
| S2/S3 实现和准入 | 已实施；非作者限定 GO，仅允许有界实测 |
| 初始四角色认证 | FAIL/EXTERNAL，0/4；首角色未提交 |
| 六条组合 grant 实际签发 | NOT_ISSUED |
| 双表健康链、各反例、唯一在途 Mapping ABA、独立连接版本、新 reader | NOT_RUN |
| UI、HTTP/MCP 同源字节与消费者真实验收 | NOT_RUN |
| trust/secret 实际轮换 | NOT_QUALIFIED；本任务仅 version1，无准确可恢复替代版本 |
| PG 黄金字节、Oracle M2 目录 | 定向2项及1项通过，保持原源算法边界 |
| Doris 历史兼容 | 17件历史原件按映射恢复并与原 Git 字节一致；不替代当前 typed manifest/assessment 序列化证明 |

当前父命令 `eebde047943f4a7e8e405510131308ea`，真实 exit 1。父报告 `browser-s2-s3-oracle-1795192895705.json`，唯一执行阶段为 s0-oracle-auth，时间 2026-11-20 16:31:35.705–16:41:35.441 UTC（本地次日00:31–00:41）。`operator-ab submitted=false`，分类 `ORACLE_LOGIN_WAITING_FOR_INPUT`，人工等待约598.783秒、提交后网络时间0。未读取或导出密码、Cookie或认证表单正文；后续十四槽没有执行。

父全窗和认证阶段均有无 clientId 过滤的实际源审计，固定业务 SELECT 记录均为0。报告 `inputsUnchanged=false`、`QUERY_BROWSER_INPUT_DRIFT` 保留：finally 中绑定调用仍受已耗尽阶段截止约束，未取得 outputBinding；这既不能签发输入稳定，也不能推断实际发生构建或宿主漂移。父命令在3240秒预算内，认证阶段耗尽600秒；timingStatus从实际耗时/登记期限推导并与真实exitCode分列；包装编排脚本正常收尾 exit0 不会覆盖产品父 exit1。

## 按影响检查与独立审查

本批67项Python定向及新增2项Node通过；原23项Node在嵌套执行中已覆盖，不再累计。另有 Connections8、组合授权4、PG黄金2、Oracle M2目录1、Web12、共享查询分发16、工程计划29；Web类型/lint及源码格式通过。完整SelfTest和CI **NOT_RUN**。具体命令、实际退出码、输入键及原件散列见机器文件，不汇总成整体产品 PASS。

候选13f69589后只有 OracleQueryReader 中文注释更正，运行代码行为未变；API/query/agent已按当前代码 Head 零下载重建绑定，旧行为测试明确保留原源码观察，不冒充在最终 Head 重跑。Web当前输入键 `88687364c5d81386b75a005aeabd19b0d78e464bceb875472e097a56b895b17d`。运行后端输入键 `53bddbec15779aa28ad25dc3082986027dbc6586f289add3326be2342d3d15ea`。

非作者关闭三项消费者缺陷：PG等价时间词法被错误拒绝、根/目标证据错绑、根属性误引目标证据；4项消费者测试及权限SQL正反例通过。独立产品差异审查未发现阻断，唯一注释问题已修。真实失败窗口与收尾复核另见 non-author-review.json；所有结论都不授予S2/S3验收。

## 资源和保留失败

第一次启动前磁盘核算为43,035,360,190字节，超过40GiB，服务未启动。仅回收当前树被忽略且可重建的 `.next/cache`：真实释放187,748,352分配字节、命令 `754ffcb4e2984a0fb2d3c211f9ab1d20` exit0、路径缺席、Web产物绑定未变。独立只读检查确认无跟踪/链接/多硬链接；旧树、runtime、密钥和原件未删。重查准入后复用五个副本及必要两台API，无下载、无新依赖。

收尾operation `9112c22911f54b27bfacfbd70414c9f4`：双轮七项排空全0；本次两台API准确ID已移除；Oracle、PG、IdP、RustFS、Fuseki五副本进程停止保留；Fuseki仅PROCESS_EXITED、cleanShutdown=UNKNOWN、allTdbLocksRemoved=false，干净关闭/可恢复性未资格；本次Web进程退出且15744端口释放。旧17个停止资源、原3个运行持卷服务及原卷/密钥/九份归档保持保护。main不变。归档device资格 `afb2486dae1e4727bd11298ebf8bd629` 直接复用，未复制717MB旧夹具。当前45秒宿主监测10个心跳均锁屏/熄屏、能源策略持续就绪，sessionContinuity仍NOT_VERIFIED。

保留EC首次Python环境失败、历史测试包装器/JS前检失败、消费者早期NOT_GO、磁盘准入失败和本次认证失败。Vitest首命令实际12通过，但包装器误按stdout解析并在当前Oracle树使用旧默认任务名报告路径；偏差保留，后以现有隔离配置12通过，未操作旧Doris服务。

首轮13f早期测量得到结果但回收临时树时未保留原始双流，明确 **NOT_QUALIFIED**，不伪造补原件。仅重做当前6d短链：MemberPlan、MeasureOnly、受控plan命令原件均有效，精测7,353,028字节；状态是MEASURED_NOT_READY_FOR_ACCEPTANCE。受控plan PLANNED、未知输入0，其自动earlyMeasurements因无新匹配代表仍NOT_READY。临时207MB稀疏验证树包含所有gate输入，核原件留存后准确移除，用户四个Finder文件保留。

## 当前交付边界

三文件为完整公开脱敏交接，私有双流、认证材料与归档内容不上传。产品仍未完成，按授权不生成例行中间PARTIAL ZIP；最终完整V3及非作者同包重开仍待真实S2/S3完成。下一步必需的是当前正常OIDC人工输入，不能通过旧会话、账号重置或恢复工程替代。保留所有未资格项，本次普通push与远端回读后停ChatGPT复审，不合并main。

公开草稿第一次schema检查因补充索引/期限/计数字段放在封闭schema的权威层而拒绝（2300a4036d084855b5653c81a74633f7，exit1）；原字段移入metadata，未放宽消费者。更正检查 fd1f085c8cfe46b0870fb7c1b96031c0 exit0，仅说明证据格式有效。
