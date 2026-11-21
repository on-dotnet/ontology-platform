# Oracle 双表 Mapping 与 Query 验收交付

**S2 为 PARTIAL，S3 为 NOT_RUN。** 最后一份 Oracle ABA 实机回执在切换前以退出码 2 结束。没有取得同一查询在原期限内返回 409 及成功副作用为零的实机原件。当前驱动需要在真实会话的授权提交前主动制造竞态，本轮只核验可离线重开的证据。四角色正常登录及双表 access 沿用已合格原件。

## 本轮 AC10 历史字节核验

离线实测 Head 为 `18b8f73c74cce00ca7a0b1c8479be18f4375e40a`。历史证据来自 `413d7363fa544ee9dbf780a9a2707b880af96ec8`。最近 Oracle 实机 Head 仍为 `b9c55441d8d53b341e0424a746f5bef32950cf37`。执行沿用 product-resume-01 / s2-s3-01。

| 核验对象 | 独立预期 | 当前产品结果 |
|---|---|---|
| Doris 查询结果 3 份 | 历史 Git 正文分别为 3,060、8,085、8,085 字节 | 类型解析与规范序列化后全部逐字节相等 |
| Doris 历史发布 2 份 | 两次正式 GET 各自绑定发布时的 manifestHash | 规范序列化结果分别为 4,751、7,529 字节，两个 SHA-256 均与发布值相等 |
| Doris 发布及 assessment 的 HTTP 正文 | 两份历史浏览器报告各有一个对应发布 GET 和一个对应 assessment GET，路径、成功状态和正文摘要均可复核 | 使用现行 HTTP 类型与 JSON 选项，四份正文逐字节相等 |
| Doris assessment 的存储原字节 | 需要独立保存的 CanonicalBytes 或对应存储 ContentHash | 两个 assessment 均未取得该项独立原件，保留 NOT_QUALIFIED |

历史 17 件清单中有三份查询结果。两次历史发布和两次 assessment 的对照另取自当时的 Mapping GET 记录。两条正式离线校验命令均以 0 退出。首轮 Mapping 诊断因路径表达式分组错误在匹配 GET 时退出，修正后逐条匹配唯一原请求。非作者独立复核了结果字节、发布散列和 HTTP 正文。

本轮没有新增登录、产品查询、授权或服务操作。AC03-B 与 Oracle S0 为 BLOCKED，G4 为 PARTIAL。准确命令、散列和既有未资格项见[完整机器回执](final-machine-receipt.json)。独立复核范围见[非作者审查](non-author-review.json)。

## 上一交付的工程与实机记录

下文保留上一交付时的状态与原验收矩阵。关于 Doris 类型序列化的新增证据以上表为准。

**本轮修正了普通审批 HTTP 回执的身份校验和当前 reader 查询原件登记。在途 ABA 驱动仍未修完。S2 为 PARTIAL，S3 为 NOT_RUN。**

| 本次续行 | 准确绑定 |
|---|---|
| 工作分支与批次 | codex/g4-oracle-mapping-query-001，product-resume-01 / s2-s3-01 |
| 续行起点 | `6221362aa5f823a071383d59ffa26ebca61f93f4` |
| 本轮工程代码 | `c7a6bcbc4e9b7cc1a8ea6d87fc95854fd5a4a548` |
| 最近产品实测 | `b9c55441d8d53b341e0424a746f5bef32950cf37` |
| main | `5168f2c93ca226caa521a6dc4ac85439335274c4` |

### 本轮修正与尚未接入的路径

浏览器记录本轮 reader 正式提交的查询 ID 和响应散列。独立消费者逐项核对该 ID、所选查询、FOUND 响应原字节和唯一一次对应的正式 HTTP POST。旧回执中已经有一项真实选中查询和匹配响应，新字段从本次修正开始登记。Oracle 的会话归属检查保留，失败输出改为固定消息，以免值比较把当前与历史会话引用写入双流。

浏览器对新提案的审核调用使用当前 auditor 的正式客户端、该提案的版本及绑定散列，并核对返回的审核人、提交人、提案 ID 和决定。该路径已接入 B 发布提案。回滚提案的请求与响应合同经离线回归。**旧在途入口仍取历史查询，回滚审批仍从先前提案的决定证明取会话引用。** 本轮未将新 reader 或 auditor 的认证材料接入该实机提交前切换器。本轮没有产品窗口、登录、新回滚决策或 409 观测。原预算与 S3 准入条件继续生效。

### 复用、工程验证与资源

非作者在续行 Base 上完整重开最后已合格的 access。78 项检查、1,236 个成员共 12,710,185 字节。工程修正后再次逐件校验成员字节。唯一变化是已关闭窗口的资源清单改从按内容寻址的归档读取；其原字节 1,384 B、SHA-256 `a94e305ff2e5ad8cec38c370cd06fece9dc9d918995db7a4730373ba0816b531`。原成员索引 `945280d40ddf750bea9fc4ecc6a3660b23b07871a4c1af2a203ec50fbac470ca` 与本机当前路径索引 `478b7484274c63d2cfde842a256cb1a1d86f65f39cb51e9dff692b7ff2399adb` 分列保留。access 本次产品执行次数为零。

| 本轮定向验证 | 结果 |
|---|---|
| Node 浏览器合同与分发 | 5/5 通过，零跳过；含回滚提案的普通 HTTP 替身测试 |
| Python 原件消费者、固定前缀及权限边界 | 35/35 通过；此前 34 项中的一次前缀字节差异失败保留 |
| AgentTests 编译 | 既有 SDK、禁网、无 restore，0 错误、4 个既存包裁剪警告 |
| 源码格式 | 通过，CI 与完整 SelfTest 未运行 |

资源预检最初为 42,950,898,110 B，超出 40 GiB 上限。按既有流程回收 17 个本工作树公共 feed 冗余副本，共 7,413,760 B；各有同散列保留原档，回收前核对打开句柄与挂载，回收后逐件核缺席及保留原件。本次增加的基线抵扣为零，完整 prepare 仍为 NOT_CURRENT。编译后重新准入为 42,945,450,430 B，任务运行角色为空，受保护清单摘要与前次一致。没有新 grant、租约维护、实机审批、源 ACL 变更或产品服务启停。

[机器回执](final-machine-receipt.json) 包含本次真实命令和上次交付的完整机读记录。[非作者审查](non-author-review.json) 明确区分本轮离线证据和既有实机证据。AC03-B 和 Oracle S0 保持 BLOCKED，定向清理为 NOT_QUALIFIED，G4 为 PARTIAL，停止在 ChatGPT 复审。

## 上一交付的实机结果与完整覆盖

下面的“本次”“最新”“当前”均指续行起点 `6221362a` 的已封存窗口。

**S2 部分通过，S3 未运行。** 指定旧查询的残留租约已清除，原始失败记录完整保留。两次正常认证均为 4/4。最新一次实机验证通过了源 READ 撤权、清理、历史结果拒绝及其余 access 场景。在途 Mapping ABA 在查询会话前置检查处失败。当前停点为 ChatGPT 复审。

| 绑定 | 值 |
|---|---|
| 分支、产品 Run、资源 Run | codex/g4-oracle-mapping-query-001、product-resume-01、implementation-01 |
| 批次与后缀计划 | s2-s3-01、s2-s3-01-access-01 |
| 始发 Base、此次续行 Base | `da0046433c87aec3b56a89f15953bfbd4114d9ca`、`095d2dd8ff957afa64f01fd938f18ffd357d8d5c` |
| 首个新实机 Head | `319e7cfe7dc6c9351ced63fbdd7c799640b31411` |
| 最后实机 Head | `b9c55441d8d53b341e0424a746f5bef32950cf37` |
| 最后工程候选 Head | `bd46e04eec2551fcc486df1e3959b1890b3dd29f`，新增门禁输入登记并修正测试替身绑定 |
| 实机后端构建输入，依两次窗口顺序 | `7cea75160944c1a12b91335cb3897ca9c30a6b299f300348ce6ed4382a45af3f`、`8fed359384cb38c7bebef568109778e76974027d894da821abd59362663582f9` |
| main | `5168f2c93ca226caa521a6dc4ac85439335274c4` |

## 既有资格与预算

EC-01 已关闭。原父命令 `47f4f5d4e2454a759bd3189a5b37f590` 在 `8f857969ad4fe08e43e5644d951bbf7532e3544d` 实测。非作者重开 170 件原件、623,536 字节，六段业务读依次为 0、1、0、1、0、0。父全窗无 clientId 过滤，恰有 2 个事件，与六段并集逐事件匹配，间隙为 0。原件索引 SHA-256 为 `f5fca1f634c23cb1b8f43d681fe402bab60b8f27a432ef7ac2aaf263c3c9b950`。沿用已获准的四角色、AC03-A 成功先赢、S1、同主体新 reader 原字节恢复，以及 AC03-C 的 PG 8/8 原件。

原父 `edd1379b83c246329579075d16ccda58` 的认证、词汇、Mapping、查询、关系五槽在其实测 Head `2a2ea74ff72c22860e4927318913eaece9d14f9f` 分别取得资格。五槽业务读为 0、0、0、10、40，间隙为 0。其原父整体失败及更早错误暂报 PASS 的 Mapping 原件均按当时状态保留。

后缀计划父时限 2,520 秒，原四角色共享认证窗 600 秒，新 reader 和各产品槽分别 180 秒，提交后回调上限 40 秒，紧前会话和授权余量要求 210 秒。产品请求 5 秒，源分支 1 秒，清理 250 ms。既有 auth-handoff-01 计划按原散列封存。

## 指定租约的维护结果

`query-3e6bb50bdffe43feaa09736718b1dcb0` 原执行为 HTTP 503、query_source_cleanup_unconfirmed。维护前封闭两个 API，核验零在途工作、两次零源会话及五分钟有效的原始证明。隔离 PostgreSQL 用例 1/1 通过。实机命令 `67e2eb4d7e4a41cb953f5a0c00a8e31f` 以比较并交换更新同一行的 LeaseOwner 和 LeaseUntilUtc，同一事务记录维护审计。维护助手已移除。

停机前重新读取该行，状态 FAILED，fence 为 2，两列均空，结果长度 0。其余列摘要为 `94cced454818eaa4d88c6cf498bc159332a334352a92954c7da8d5fba7192a14`。原 failure 审计 `4b8e81b0b1f1482ba5bf55aa167a6575` 保留，另有一条 data.query.cleanup.recover。该行的原期限内取消清理资格仍为 NOT_QUALIFIED。

## 源 READ、平台权限及恢复

第一窗父 `c9a0458559de4934a530dcbcc9ca74a4` 退出码 1。撤回目标表 READ 后，新查询 `query-5aa70328195f4a99bb162f114f2c62ae` 返回 HTTP 200、UNAVAILABLE，零业务读。物理释放得到确认，两列租约为空。失败原因到分支释放观测为 1.946 ms。随后历史结果 GET 为 HTTP 500 / internal_error，865.377667 ms。旧报告缺第四个请求级审计窗口及 sourceCleanup。非作者核准前述子项，整槽保留 FAIL。

历史结果 GET 在 Oracle 只读证明拒绝时，曾把连接层错误报告成内部错误。代码对相应错误增加了正式的语义错误映射。第二窗父 `1afa8fd9ad624134a814126527f7a916` 在该修正上实测。认证 34 项、access 78 项，非作者分别重开 966 和 1,236 个成员，均为 CASE_QUALIFIED。access 的 11 个无过滤审计窗口共 2 次业务读。全父窗 6 次业务读归属认证 0、access 2、ABA 前置 4，间隙为 0。

| 最新 access 场景 | 实机结果 | 业务读 |
|---|---|---:|
| 撤回目标表 READ 后执行双表查询 | HTTP 200 / UNAVAILABLE，空数据和来源，查询 `query-dd5638dcdcc84e04a429322d8f8dd153` | 0 |
| 同次撤权下恢复历史结果 | HTTP 503 / query_source_unavailable，808.869791 ms | 0 |
| 恢复直接 READ 后执行健康双表关系查询 | FOUND，两份来源回执 | 2 |
| 无 grant、撤销 execute、少一个字段、自然到期 | 各为 UNAUTHORIZED，短 TTL 前置亦按预期拒绝 | 0 |
| 分别撤销结果读取、来源读取 | 两个 GET 均为 HTTP 403 / query_forbidden，临时权限变更均有回读 | 0 |

对最新撤权查询，源事件、终态行及源会话由三个独立命令读取。自 RESOURCE_FAILURE 至已确认的 BranchRelease 为 **1.5729 ms**。PG 终态 COMPLETED，两列租约为空，结果 SHA-256 为 `d3b5852967dc63ac0f55cbac17eb959ab47c7d210111cf9c6c2ad097942946d5`。同时观测到 0 个任务源会话。AC03-B 的定向取消仍为 BLOCKED。

每条组合授权均有相同 connectionId、org-demo、site-a、两个 ObjectRef 及完整 22 个 FieldRef。对象为 PRODUCTION/OMQ_ENTITY 和 CaseOwner/OmqTarget，每表 11 字段，按序为 ROW_ID、JOIN_KEY、VAL、ORG_ID、SITE_ID、EXT_ID、LABEL、FROM_TS、TO_TS、EVENT_TS、OBSERVED_TS。

| 角色与操作 | 单条组合 grant |
|---|---|
| operator / mapping.source.validate | `omq-s23-97079e300a66540eb7b53a5f6f3ebf2a` |
| auditor / mapping.source.validate | `omq-s23-4ded2c11b4226faae7048d8ac391bb56` |
| activator / mapping.source.validate | `omq-s23-a42ab8e97dc92c8027e702c4a69c1b4b` |
| reader / data.query.execute | `omq-s23-a3aedb231d0f77c6711156fc8ce4dac2` |
| reader / data.query.result.read | `omq-s23-ce8f478983910496be13d7b822675356` |
| reader / data.query.evidence.read | `omq-s23-a39a4cfd7be6689a3dba1ede4be26892` |

停机前回读了 6 条组合授权、9 条工作流授权、共 75 行和 epoch 106。沿用了原授权 ID，本次收尾新增 0 条。原 15 项及历史续发保留。源端两条直接 READ 都已恢复，均不可转授，两表夹具各 1 行，内容与基线摘要一致，任务源会话为 0。

## 唯一 Mapping 在途 ABA 与剩余验收

准入要求为同一 Q 捕获 A、完成真实源读且成功提交前，正式激活 B、正式回滚并重新激活原 release A，activationId 更新、revision 递增。随后同一 Q 必须在原期限内返回 409 / query_binding_stale，成功结果、已提交来源回执和成功执行审计均为零。Doris 两份历史原件是相同顺序的两次观测。连接版本、历史结果、旧 selection 各自验收。

最新实机前置完成了歧义查询、选中目标、B 草稿验证及异人审核。MTP 命令 `36606f5b1aa74ac09863d99930578f85` 退出码 2，1 个失败、零通过、零跳过。保存查询归属原登录会话，当前 reader 已正常重新登录，身份前置断言失败。在途 Q 未启动，B 和原 A 均未发生本次切换，409 与零成功副作用未取得资格。静态复核另发现，后续回滚审批路径会复用上一项决策中的审核会话引用；本次实机退出时尚未进入该路径。继续验收需要新的回滚提案由当前审核者在正式认证边界内独立审批。

05:44:35 UTC 实机只读回查，当前 release A 为 `release-6d6469e33f744b7c93b8e4d516fca0c4`，原 activation revision 为 1。B 提案 `proposal-b05bc6871ec0484c8f473adb98dc691e` 为 APPROVED、revision 2，尚未激活，记录的到期时间为 05:49:40 UTC。保留该提案及其审批原件用于复审；到期后的服务端状态未实测。

| 条款 | 当前覆盖和缺项 |
|---|---|
| AC01–02 | 固定投影、事务/水位及单表原件按原输入复用，当前健康双表新增两次业务读。 |
| AC03 | A 成功先赢，C 的 PG 8/8 保留。B、B 的 250 ms 和 Oracle S0 分别保持 BLOCKED / NOT_QUALIFIED / BLOCKED。 |
| AC04、AC06 | 正式提案、审核、既有激活、双表精确值、NULL/接壤/重复目标/多父/扇出按原前缀验收。 |
| AC05 | execute、result、evidence 权限拒绝已核。唯一在途 Mapping ABA 失败于前置。连接版本反例、其余版本和旧 selection 未取得本窗资格。 |
| AC07–08 | FOUND、UNAVAILABLE、UNAUTHORIZED 及历史结果授权检查已实测。完整六态、100/101 和本后缀新 reader 恢复尚未验收。 |
| AC09 | S2 整体未通过，S3、UI 三能力、MCP 四工具、刷新、撤权清屏及迟到响应 NOT_RUN。 |
| AC10 | 既有 PG 黄金字节、Oracle M2 目录合同与 17 份 Doris 历史散列沿原输入保留。当前 Doris 类型序列化未资格。 |
| AC11 | 两个新父窗及资源、授权和无过滤审计均有可重开原件。完整工程资格、CI、完整 SelfTest 和跨平台验证未签发。 |

trust/secret 没有已登记、同任务可逆替代版本。G4 为 PARTIAL。历史冷启动超时、未完成认证窗、原 503、首窗 500 和最新 ABA 前置失败均保留。

## 工程验证、资源与交付

在最后实机输入上，S2 Python 34 项、Node 4 项、运行时入口、资源复用与源码格式短链通过。另将三个新消费模块登记到已有门禁。该门禁首次运行 129 项中 4 项测试替身仍绑定旧资源入口；更正测试替身后 129/129 通过。此前的 35 项 Oracle 适配器与资源所有权测试按原输入保留。

两轮排空各 7 个计数均为 0。两个任务 API 已移除并按原 ID 验证缺席。五个副本均已退出。Oracle 的原生关闭输出和 PostgreSQL 的 shut down 控制状态已独立重开。RustFS、Keycloak 的 TERM 与退出已核实；Keycloak 退出码 143，停机日志仅留摘要，其干净关闭标记没有独立日志原件。Fuseki 的 cleanShutdown 为 UNKNOWN，TDB 锁保留。任务运行角色余数为零。两窗 Web 均已退出、端口释放，原 17 停止资源、3 运行资源和 9 份归档受保护。后验磁盘准入总量 42,949,190,078 字节，上限 42,949,672,960 字节。

上一次交付的三份完整文件绑定在续行 Base；机器回执列出各自的长度与 SHA-256。本次新增普通命令及双流的核验截止时间、每个原件的长度与摘要、Web 生命周期和未执行槽位均见[机器回执](final-machine-receipt.json)。两个只读评审角色的重开范围、结论和限制见[非作者审查](non-author-review.json)。本批按授权交付三个公开文件，停止在 ChatGPT 复审。
