# Oracle S2/S3 续行交付 · 2026-11-21

**S2 PARTIAL，S3 NOT_RUN，G4 PARTIAL。** 本轮完成三项真实入口修复、定向回归和非作者调用链复核。首次七角色资源核算通过探针检查，余额不足以容纳完整 prepare 或首份新快照。收尾复测在磁盘上限检查处返回 BLOCKED。没有开启登录或产品窗口。本轮停在 ChatGPT 复审。[机器回执](final-machine-receipt.json) · [非作者复核](non-author-review.json)

本批沿用 `product-resume-01 / s2-s3-01`。fetch 后本地与远端任务分支均为续行 Head `7b8fb59093e6f773ce4aea3c06357111c088f19b`。最终工程输入为 `f809d391f82cdd0470e009a4860209ba1743e446`。上轮 ChatGPT 接受 PARTIAL 交接，最近一次 Oracle 产品实测仍为 `b9c55441d8d53b341e0424a746f5bef32950cf37`。main 为 `5168f2c93ca226caa521a6dc4ac85439335274c4`。

## 三项修复与实测边界

| 复审问题 | 当前代码及工程证据 | 本轮产品原件 |
|---|---|---|
| runtime 消费哪条查询 | ABA 用当前 reader 发起健康双表关系查询，单列 `aba-runtime-seed` 两次预备读。两槽共用同一父执行的 `runtimeQuery`。C# 从持久行核主体、服务器会话、包含 selectionQueryId 的规范请求散列和结果散列。connection 在返回前重开同父 ABA 报告并核 SHA。历史 `latestQuery` 保留，新 reader 恢复使用重建后的结果。 | 未生成新 queryId。当前报告不能提供实机 seed 或同 Q 证据。 |
| 新回滚由谁审核 | Oracle 从本轮正式 Cookie 解保护、SessionStore 当前票据取得 auditor。新提案经正式 DI 的 `MappingApplicationService.DecideAsync` 审核，保留四主体与会话断言。新决定须匹配提案、绑定、审核主体与会话摘要。 | 未生成回滚提案或决定。DI 是本次接线，回滚 HTTP 实测未运行。 |
| 同 Q 的源读、激活、409 与零成功 | 已有正式提交防护继续核验同 Q。消费者核对源完成、B 激活、A 回滚激活、原 5 秒内的 409，以及结果、已提交来源回执、成功审计全零。 | 上一实机止于会话前置。本轮未执行新 Q、两次激活、409 或三项零成功核验。 |
| 审计与期限 | 按同一 runtime 内的目标查询、B 激活新鲜校验、A 回滚验证、A 激活新鲜校验冻结 2＋2＋2＋2。四段各核两张目标表上的成功 SELECT、事件时间及完整父子并集。查询准备、selection、B 草稿评估各有独立窗口。当前与旧 selection 均绑定原请求上下文。 | 8 为独立预期。本轮没有实机事件数、1 秒源读、250 ms 清理或 5 秒完成时长。 |

源标识在已有任务审计视图内按未指定 clientId 的整窗读取。保留逐事件重开、时钟歧义与间隙拒绝。两个旧源夹具继续按自身历史输入核验。访问槽按输入复用后，实际父计划固定为十槽 2,340 秒，四角色认证 600 秒、新 reader 180 秒、提交 40 秒；旧十一槽计划及历史字节仍可重开。[十槽计划](../../../../../scripts/maintenance/workflow-oracle-s2-runtime-plan.json) · [十一槽原计划](../../../../../scripts/maintenance/workflow-oracle-s2-access-plan.json)

## FRESH / REUSED / NOT_RUN

| 状态 | 覆盖范围 |
|---|---|
| FRESH 工程 | 最终工程 Head 上 Node 7/7、Python 38/38、提交区间 diff-check 0。Node 通过 mock 捕获两个实际场景函数的分发参数。Python 拒绝旧 seed、错误请求或会话、缺 selection 上下文、错误审核来源、同数错表和跨动作事件。首个工程候选通过仓库静态格式与 runtime 结构预检。 |
| FRESH 编译 | 最终候选的 16 份 AgentTests 源码（含生成文件）用 388 个现有引用完成 Roslyn 内存编译，emit 成功。引用版本统一产生 CS1701/CS1702 警告。正式 MSBuild 构建、封存及容器执行未运行。 |
| FRESH 原件核验 | 复核 access 的 1,236 件、12,710,185 B，及既有五槽 684 件成员。把历史 access 所依赖的四份可变构建文件封存到内容寻址路径，共 63,430 B；非作者逐件核 SHA 与长度。 |
| REUSED 产品 | 原输入上的 78 项 access、AC03-A/C、S1、EC01、前五槽、旧源 PG/Oracle M2 与已合格的 Doris 兼容子项。EC01 历史资格为 170 件原件，本轮没有再跑产品。Doris 的三份查询结果、两份 manifest 和四份 HTTP 按原离线执行资格保留。 |
| NOT_RUN 产品 | 新十槽均未执行，包括认证、完整 ABA、连接及版本、六态剩余项、100/101、新 reader 恢复和 S3 UI/MCP。重建后的宿主代次、授权 TTL、A 及新 B 提案前态仍需在正式准入后重新核。 |
| BLOCKED / NOT_QUALIFIED | AC03-B、Oracle S0 为 BLOCKED。取消 cleanup250ms、两个 Doris assessment 的独立存储 expected、trust/secret 可逆版本仍未资格。G4 PARTIAL，CI 和全量 SelfTest 未运行。 |

先前失败保留在原测量窗口。父 `1afa8fd9ad624134a814126527f7a916` 退出 1；实机 ABA 子命令 `36606f5b1aa74ac09863d99930578f85` 退出 2。父失败与已获资格的 access 分列。本轮初次 Node 回归和历史兼容登记前的 Python 回归也曾失败。默认工程 plan 在已提交候选遇到原树四份未跟踪 Finder 文件，以 `PLAN_DIRTY` 退出 2；这些文件均保留。定向回归与 plan/verify 分别记账。[上轮完整三文件与失败记录](https://github.com/on-dotnet/ontology-platform/tree/7b8fb59093e6f773ce4aea3c06357111c088f19b/docs/evidence/G4-ORACLE-MAPPING-QUERY-001/product-resume-01/s2-s3-01)

## 资源、原件与最小裁决

| 七角色准入及 prepare 项目 | 本轮观测 |
|---|---|
| 原准入入口 | `source-admission-1a5e08c40f73499db1743a7ee19bedde.json`。预估含 helper 为 13.75 GiB、10.5 CPU，任务运行角色为空。探针已删除并核缺席，末次命令 `cf20111e407f4384802f73e46daffac0`。 |
| 磁盘额度 | 上限 42,949,672,960 B。该次计入 42,949,370,302 B，余额 302,658 B。此为准入采样时刻的任务账本。 |
| 收尾复测 | 同一七角色入口在 17:51（北京时间）计入 42,949,988,798 B，超上限 315,838 B，入口在启动探针前返回 BLOCKED。保护清单摘要与首次一致。原件 `source-admission-d2b76b2e75914bbc935540287d0619e2.json`，末次命令 `63f1f7eafa4c4dfa98cd3739f42234da`。 |
| 当前完整 prepare | 环境内容键 `d6d909b8cad6e0c13389a3323def278aa77870bbca92689ade15af303daafb43`。179 个批准包的来源摘要已核，21 个项目资产文件存在。feed 缺 80 件、261,791,963 B；私有 NuGet 缓存缺 168 件、263,059,792 B。合计 524,851,755 B 逻辑文件，按该次余额至少短 524,549,097 B；目录、其他临时量与复现基线抵扣的影响须在真实峰值中另核。 |
| 新快照 | 当前后端构建键在既存六种快照键中缺席。第一份 API 快照按现有 99 个输出的分配与元数据公式，未计回执已需至少 32,112,640 B，按同一余额至少短 31,809,982 B。完整七角色峰值未获资格。 |
| 回收与保护 | 只读核对 13 份回收台账，250 个已回收的准确文件路径均缺席。重新出现的 399 个构建文件合计 37,715,968 B，是候选上界，当前挂载与业务引用未取得删除资格。即使全部合格也不足以覆盖完整 prepare。本轮新增抵扣 0。17 个 STOPPED_KEEP、3 个持卷服务、旧卷及九份封存归档保持保护。 |
| 两份 Doris assessment | 检查三份现存审查包的公开证据与 16 份本地非秘密候选。精确 ID `ma-a77741308dd94252a393281745421189`、`ma-99d5dbdfae694e7c83bcc9f865a9932e` 均未定位独立存储 CanonicalBytes 或 ContentHash。可定位两份 HTTP 与第二个 assessment 的快照。已知 PG 存储凭据属于不同 ID。本轮未恢复旧栈。 |

**集中裁决项只有资源处置。** 请确定原 40 GiB 内可永久释放且允许逐件核验的额外任务冗余，或另行授权调整离线准备流程，使相同内容键的完整验证能在额度内完成。按收尾复测，完整 prepare 的最低缺口为 525,167,593 B。首份快照单项的最低缺口为 32,428,478 B。两项分别对同一次余额测算，完整阶段峰值仍需实测。本轮未删除候选、增发权限或尝试慢 SQL。Doris expected、AC03-B 和 Oracle S0 的现有状态继续保留。

机器回执的 `metadata.evidenceIndex` 逐条提供命令 ID、实际退出码、计时、stdout/stderr/receipt 的任务树相对路径、字节数与 SHA-256。`metadata.resource`、`checkSources`、`rawCheckIndexes`、`accessBackups` 分别定位准入、离线检查源、原索引与四份封存原件。普通推送后的交付 Head、远端任务分支与 main 回读记在原批次 `runtime-closure-remote-readback.json`。当前交付为三文件 PARTIAL 复审，未生成中间 ZIP。
