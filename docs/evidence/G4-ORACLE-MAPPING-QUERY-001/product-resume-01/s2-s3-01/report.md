# 普通 HTTP 关系查询诊断

**NORMAL_PATH_BLOCKED · S2 PARTIAL · S3 NOT_RUN · G4 PARTIAL。** Q1 首个取消来源为 workCutoff，首个失败阶段为 readOnly.cancelled。只读校验包含会话身份、权限汇总、只读证明、直接对象授权和游标释放。现有事件无法区分内部耗时，离线注入取消仅复现外部症状。单一可修原因未锁定，停止 Q2。 本批清除了 f159 的 owner 与租约截止。Q1 没有结果字节可供 GET，原字节恢复尚未取得资格。

## 两个失败的证据边界

历史正式父 `4032c1d770b240989966ba3275d86999` 退出 1，业务 POST 返回 503，客户端耗时 1671.913 ms。根据时间窗、连接及审计唯一关联 `query-f1599097a7274c20b82cbf0dfcea4e2b`。旧 API 已移除，原收据未保全逐阶段 trace。有效配置为默认 Warning，SemanticQuery 及 Connections.OracleSourceAdapter 为 Information。PRIMARY_CAUSE_NOT_RECOVERABLE_FROM_OLD_ARTIFACTS。776.090 ms 是 API 创建字段到 PG 完成字段的 UTC 差。零次业务 SELECT 只说明该审计窗没有业务读。

三次普通关系请求的归一化请求散列均为 `4530c34dbe04e8e6b5f3608d49d5189364bd94eeff5e3c4e45c82bf078036f44`。历史健康 Q a3b2eaa370fe4f8193d3d2ac817f6f7b 在 A1/epoch121 用时 2762.698 ms，返回 5056 B，SHA-256 为 `1546bdc00a5565fd9a1ad80f37c9dbec9fba11a8c6b0932082c2cad129cf8897`。f159 与本批 Q1 使用 A3/epoch136。健康样本、f159、Q1 的最短授权余量约为 14400、13713、5594 秒。Q1 的 PG 台账共 105 行，本次选用的 15 项授权最短余量为 5593.633 秒，满足 1710 秒要求，续授 0。历史宿主及授权代次有差异，三个请求的对比不足以诊断冷启动。

| 样本 | 源码 | API 快照 | Oracle 容器 | 授权 epoch | 最短余量 s |
|---|---|---|---|---:|---:|
| 健康普通关系 | `851906f140c0` | `56622dd78172` | `65bdf442f567` | 121 | 14399.945 |
| f159 | `9e84841423ba` | `d642579639d1` | `65bdf442f567` | 136 | 13713.168 |
| Q1 | `5318f9b1807f` | `5ed4767eb175` | `65bdf442f567` | 136 | 5593.633 |

完整代码、API 代次、配置和激活身份已写入机器回执。各样本为对应阶段首次关系 POST，源连接池在此前的状态未知。Q1 使用真实 reader，未发送业务预热查询。

## Q1 的 HTTP、时钟和收口

正式父 `e1c70fc2faf344f39c98ac6731a061aa` 退出 1。四角色认证阶段耗时 4874.068 ms。Q1 POST 返回 503 `query_source_cleanup_unconfirmed`，客户端 1718.061 ms。响应没有 Q 头。PG 唯一命中 `query-5d891e89221e4a3f8f6893873b1d7a9d`，与投影和审计的 trace `b7493f3191111571d3a690378ee48ecd`、correlation `89d5324d20fe42ae9cccfe59ea9f4752` 相符。PG 行 FAILED、fence 2，owner 散列 `f155210a2019304736db8f52cc879be44f88045bd28ddcbae06878159f09e08b`，原失败审计 `3e1ca8e4e1af42efa3ac8d0007c8debf`，持久错误 query_source_unavailable。源业务读、结果字节、结果读收据均为 0。未知 owner 留在现场。

下表按实际 API 的 1 GHz 单调时钟，以源分支建立期限为零点。剩余总期限来自事件处的 TimeSpan。5 秒 HTTP、1 秒源分支和 250 ms 清理均沿用原期限。Dispose 和观察器退出计入源调用。租约观察 100 ms 超时、观察器异常、正式取消和请求取消本次均未触发。没有进入目录、事务及业务命令阶段。

| API 阶段 | 事件 | 相对源分支 ms | 剩余 HTTP ms |
|---|---|---:|---:|
| http | enter | -918.184 | 4999.163 |
| branch | enter | 0.155 | 4080.835 |
| initialLease | enter | 0.451 | 4080.538 |
| initialLease | returned | 3.410 | 4077.579 |
| observer | enter | 4.027 | 4076.962 |
| source | enter | 4.459 | 4076.530 |
| permit | enter | 4.865 | 4076.124 |
| permit | returned | 5.557 | 4075.433 |
| acquisition | returned | 14.976 | 4066.014 |
| permitCheck | enter | 64.307 | 4016.682 |
| permitCheck | returned | 64.810 | 4016.179 |
| tls | enter | 64.822 | 4016.168 |
| tls | returned | 67.805 | 4013.184 |
| openCheck | enter | 88.857 | 3992.132 |
| openCheck | returned | 89.209 | 3991.780 |
| open | enter | 89.211 | 3991.779 |
| open | returned | 237.112 | 3843.876 |
| permitReturn | enter | 237.140 | 3843.849 |
| permitReturn | returned | 237.684 | 3843.305 |
| sessionTag | enter | 237.686 | 3843.304 |
| sessionTag | returned | 237.851 | 3843.138 |
| readOnly | enter | 238.110 | 3842.879 |
| workCutoff | signal | 752.838 | 3328.151 |
| cleanupStart | enter | 753.579 | 3327.410 |
| readerCutoff | signal | 765.797 | 3315.191 |
| readOnly | cancelled | 783.839 | 3297.149 |
| cleanupStart | enter | 783.890 | 3297.099 |
| disposeConnection | enter | 783.977 | 3297.012 |
| disposeConnection | returned | 787.785 | 3293.204 |
| PHYSICAL_RELEASE | returned | 787.916 | 3293.074 |
| source | cancelled | 788.049 | 3292.940 |
| observer | returned | 788.067 | 3292.922 |
| cleanup | unconfirmed | 788.115 | 3292.874 |
| http | returned | 795.308 | 3285.682 |

准确宿主 `2c0549a8e4b8d4f9dd8157204c8c24685f702f7c127c2041bd360612004d4041`，进程命名空间 PID 9，模块 `c6d6a558-bfe6-4f65-bb4a-489586a79bbd`。先导出再移除 API，命令 `56bca1e4a9d84523b85a993124b8a48e` 成功。消费者重开 8385 B、SHA-256 `6af20f5eb2369c71d3f95133e2f9d51ccb7bf633e137d7990cffb92cad358bc2`，34 条事件，丢失 0。认证、响应后审计／PG 取证、导出和资源关闭计在外层。API／源 UTC 对宿主的前后误差区间及逐阶段外层时间见机器回执。

本批实际 POST 1/2、产品窗 1/2、活跃 198.185/2340 秒。Q1 用 1 次，Q2 用 0 次。剩余名额随本批停止。两台 API 已移除，前后七项排空均为零，五个持久角色已退出，Fuseki cleanShutdown 为 UNKNOWN。末代原件 SHA-256 `64bdc66845958810935eb00e9b633108b6c5dc7ebf56ea19d030c396a5db5040`。原卷和密钥、九归档、旧 17 加原 3、原 V3、四个 Finder 文件保持。峰值计费 43,236,250,046 B，止损线 44 GiB，总额 48 GiB，收尾预留 4 GiB。

## f159 准确维护

先重开 c35242b898c04ae3ad5529ba346d320f 关闭原件（7735 B、SHA-256 `a3839fe8ebb6e418e42e2280d1d6044acd7a1a4f3f65babdc8f13b8c7d055348`）、源代次与生产者封闭证明，再以新连接校验冻结行与审计。仅启动任务 PG。隔离事务 1/1 通过后，`908a039cfe604cadbbf839706c9ec369` 退出 0。一次提交将 owner 与租约截止清空，保留原失败审计 `38ebcc6e08504994b36a322edc4ffd86` 并追加维护审计 `fca8425bb6fc49c28361038ec1d6e90b`。新连接逐项回读稳定行、审计、收据、错误码。该任务级恢复保留原清理失败。Q1 晚维护、d368 重做、A3 回滚均为 0。

## 工程验收与下一关口

Doris 工程入口 11/11，覆盖历史 Git 正例、14 个篡改变体及真实输入改变触发 RF_PRODUCT_REVISION。旧 assessment 仍未资格。Python 定向 4/4，含准确 dotnet 与 AgentTests 构建绑定的两项源关联测试，以及仅替换 HTTP transport 的真实 request 记录到 Python 的 410/seed 后半段。扩展集 5/5，含本次实际 API 投影负例。C# 9/9，完整 Oracle 入口 156/156。发现数与实际执行相符，skip 0。选择收据及实际命令列于下表。

Web 与 interaction 缺少成功的正式父，消费者返回 OMQ_FORMAL_S2_S3_NOT_RUN。当前普通路径及同 Q GET 均未取得资格。先定位只读校验内部的单一原因并验证普通关系与原字节 GET，再另行审查真实 ABA 和剩余 S2。250 ms、AC03-B、Oracle S0 保留原资格。历史诊断／正式父各 1，本批新增 ABA、十槽、S3、main 合并均为 0。CI 与完整 SelfTest 均未运行。

| 检查或取证 | 实际命令 ID | 退出码 |
|---|---|---:|
| 历史正式父 | `4032c1d770b240989966ba3275d86999` | 1 |
| 环境准备 | `4b5bdcb7347345bab911476ed5ca1d8f` | 0 |
| PG隔离维护断言 | `69d3e200d84d4244b8e390f871924ce9` | 0 |
| f159维护 | `908a039cfe604cadbbf839706c9ec369` | 0 |
| Q1普通正式父 | `e1c70fc2faf344f39c98ac6731a061aa` | 1 |
| API导出 | `56bca1e4a9d84523b85a993124b8a48e` | 0 |
| CSharp定向 | `160154146cfd439f9e29d8db39ab2ba3` | 0 |
| Python定向 | `ac1cb3013e14491d81291503a8216a1e` | 0 |
| Python交叉与投影 | `6cfbff661378460f93b0990127c569bb` | 0 |
| 初次完整Oracle | `1fa2c8b17a96474aa04d530532543e9c` | 1 |
| 清环境历史夹具失败 | `cb715030cf9b497fb19bb10d9f92f5d1` | 1 |
| 完整Oracle | `979d8bcf71d249f19b819077438d5cc9` | 0 |
| 已绑定门禁 | `bf696c8eafd644bf833b6b9fc82848d6` | 2 |
| 交互消费者 | `30adb7539cb84c37b86c7764a4e496fa` | 1 |
| 构建-api | `7807f8af509a484ea11b0007ba590437` | 0 |
| 构建-agent | `0d608cea9bf84e73b58359cd127df45e` | 0 |
| 构建-query | `853dd873701749f4a8156a824f2adbdd` | 0 |
| f159前置-row | `36e084afe8ab4763a492f20410544f6d` | 0 |
| f159前置-audit | `70e58d248ea0461091d2c4d51b563884` | 0 |
| f159前置-receipts | `9d39bc60a07b4a49897f6fa80fc0dab9` | 0 |
| f159前置-errorCode | `a65341f6f9154382aec20da3355358c1` | 0 |
| f159提交前-row | `15dd6f279f5f4d2d8d1b555e93597342` | 0 |
| f159提交前-audit | `34f6b0235cfa472ca151d9cac264785d` | 0 |
| f159提交前-receipts | `92fe71a1aa1e4d36bbebd0b5cbef49d2` | 0 |
| f159提交前-errorCode | `365cd37c494f4408875053d731c72bde` | 0 |
| f159新连接回读-row | `303a65a4743947519fa34480a4a2a1fd` | 0 |
| f159新连接回读-audit | `6e00a818c2ea4befb56620c2e80522c4` | 0 |
| f159新连接回读-receipts | `e97f65d4fbf04416bae3b51219d82e1b` | 0 |
| f159新连接回读-errorCode | `794e08f6d9cc4c5989d01b4502db6255` | 0 |
| Q1关联-ident | `94718d9f17394ca0adfdcaab5834bef5` | 0 |
| Q1关联-row | `6795cc23c706473ba61daf2830a1670c` | 0 |
| Q1关联-audit | `3da1a808c24741cdab667343a55e3eb6` | 0 |
| Q1关联-data | `f3b7944ad1a343308ce3d436df749b38` | 0 |
| Q1排空-before | `819c297cc68b4ed6bcfc8525edd88a52` | 0 |
| Q1排空-after | `cd7ec043dea74061beeb752f7f9b23df` | 0 |
| 独立干净候选政策 | `79e8227a350c4e1991188932ca7ed222` | 0 |
| normal-engineering-plan-a0d4d94 | `a0d4d94fa6754375af3ce22d6912dc93` | 0 |
| normal-engineering-verify-ebcb9da | `ebcb9da775134b168e105941587dbf8c` | 2 |
| normal-stable-oracle-task-admission-bb99da5 | `bb99da5ed17a4a328e9fbd14a95aac21` | 0 |

## 独立复核

工程复核逐字重开 37 组三联命令收据，产品复核逐格核对 34 条事件和 17 份索引原件，维护复核重开 357 条登记路径。Q1 的 API 宿主与模块、PG 失败行、两个时钟区间、f159 两列新连接回读均相符。当前完整稳定候选门禁 `ebcb9da775134b168e105941587dbf8c` 真实退出 2。环境、合同、后端分别复用 21、27、10 项执行并重新核准。查询准入 16 项、Doris 11 项、工程 29 项均重新执行。独立 Oracle 入口实际发现 156 个不同用例并全数执行，干净候选政策检查退出 0。

本批实际执行的跨边界用例如下。

- `WorkflowOracleSourceAssociation.SourceAssociationTests.test_ordinary_rejection_requires_fresh_same_connection_after_release`
- `WorkflowOracleSourceAssociation.SourceAssociationTests.test_reopen_two_branches_emitted_by_agent_test_process`
- `OracleRuntimeSourceEventsTests.ExportTwoCompleteSourceBranchesForOfflineReopen`
- `WorkflowOracleS2.S2ReadinessTests.test_expired_catalog_and_current_reader_seed_are_independently_bound`
- `WorkflowOracleSourceAssociation.SourceAssociationTests.test_reopen_normal_http_failure_and_overflow`

## c44c6294 历史交付原文

下列原文记录维护前截面。原文中的“行内执行 776.090 毫秒”应读作两个 UTC 字段之差。历史 f159 的 owner 已由本批准确维护清空。

# Oracle S2/S3 限定交接

**S2 PARTIAL，S3 NOT_RUN。** d368 的准确晚 CAS 已完成。一次诊断与一次修正后的正式十槽均已执行。正式父通过四角色认证，随后在 ABA 槽的首个关系查询收到 `503 query_source_cleanup_unconfirmed`。该查询的两列租约仍在。两个父命令均未派发在途 ABA 的 25 秒 DI 子进程。交付停在 ChatGPT 复审。

| 本轮实际操作 | 命令 | 结果 |
|---|---|---|
| d368 准确维护 | `8c6dac18ce3940398c85dba1660cdcdc` | exit 0。新连接已核两列清空、原失败审计保留、恰有一条维护审计 |
| 诊断父 | `a576965c8f4d47999676d82ecfde9106` | exit 1，24.169 秒。认证 6.217 秒，ABA 槽 13.453 秒，历史结果 GET 返回 410 |
| 修正后的正式父 | `4032c1d770b240989966ba3275d86999` | exit 1，31.101／2340 秒。认证 6.729／600 秒，ABA 槽 22.005／180 秒。十槽 1 PASS、1 FAIL、8 NOT_RUN |

## 准确晚恢复

非作者重开 d368 的请求与绑定、宿主和网络、专用 Oracle 实例、原父与实际 docker-exec 子进程、两台 API 及生产者关闭原件，再核 9b81 → 9386 → 05ea 的原生关闭与后态。维护只启任务 PG，冻结行位于 `mapping`、系统标识 `7709907053089669168`。事务校验身份、owner 散列、FAILED/fence 2、稳定行与唯一失败审计后，清空两列租约并写入维护审计。独立复核覆盖 493 件原件。

查询 `query-d368ac610c7745889890e1589653af8f` 的 request、binding 和其余行字节稳定。原失败审计 `83330a307d7a4583aa44e7c2a6db4fa4` 保留，新维护审计为 `514479db82f74b4a921a4b2ca2674bb6`。新连接的行、审计及读收据三个命令分别为 `393e621987fd4b5cbdc4baea4030f82c`、`43a3dcf0771b488a9c2d835ff4dfcdeb`、`2abc9b489e224d49b06e7fba2e5ce477`。成功审计、结果和读收据均为零。历史两条 clientId 与 Q 的逐源归属仍为 NOT_PROVEN，cleanup250ms、AC03-B、Oracle S0 保留原资格。

## 两次产品执行

诊断中，当前连接五阶段探测通过。随后 reader 读取历史 `query-d293780099754592b3e2a00957e13c8b`，10.684 毫秒后返回 `410 result_expired`。实际驱动要求 200，因而停止。修正保留历史 queryId、5056 字节的原散列和真实 410。在准确过期分支中，驱动使用该槽原有的新关系查询，要求同一父、reader、会话和 Q 从正式 GET 取回相同字节并核零源读。该新分支的后半段取得离线正反例覆盖。

正式执行复现历史 410 并进入原有 seed POST。HTTP 用时 1671.913 毫秒，距五秒上限 3328.087 毫秒，响应 503、错误码 `query_source_cleanup_unconfirmed`。此次 HTTP 没有返回 queryId。关闭 PG 前，按准确连接和请求起止查询，唯一命中 `query-f1599097a7274c20b82cbf0dfcea4e2b`。

| 正式失败 Q 的现场事实 | 实测 |
|---|---|
| 未过滤 Oracle 审计 | seed 窗预期 2 次业务 SELECT，实际 0 次；正式父全窗也是 0 次 |
| PG 时间（UTC） | 创建 12:50:37.198569，完成 12:50:37.974659，截止 12:50:41.308879。行内执行 776.090 毫秒，完成时余 3334.220 毫秒 |
| 状态与占位 | FAILED，fence 2，owner 散列 `08d6b6d8633b72b6ad4a980128d3e6a1b68c83b5c388cecd3a3296d84accf4cb`，租约截止等于原 Q 截止。LEASE_HELD_NOT_QUALIFIED |
| 副作用 | 唯一失败审计 `38ebcc6e08504994b36a322edc4ffd86`；成功审计 0，resultHash 为 null，结果大小、密文长度和读收据均为 0 |

正式失败行保留现场。源分支一秒和清理 250 毫秒各自的实测时长与差额均未知。seed GET、实体选择、B4/A5、同 Q 在原期限内拒绝、普通最终 403/409 的占位释放与下一同连接新查询准入均未取得本轮实机资格。当前完整 A 仍为 `activation-d2dcec9ef54c4f3bb96d60cab449580b`、revision 3。历史父 `c02e89f8d8f2481f90058606ccf71b29` 和子 `5b90bb8f66fb4ddd9bfeddbe5015133a` 的失败原件保留；旧超时最后有证调用为 ReadJobAsync，剩 296.4737 毫秒。

## 工程、授权与收口

四处原入口修正覆盖完整激活回执与下一槽消费、真实子进程的有界允许字段收集和 logger、当前 run 的工程适配器、准确三笔或登记五笔激活链。普通最终 403/409 的已审实现保留。后端变更后按同一输入键重建 API、Agent、Query，实际宿主重开各 99／222／222 件快照。首次产品开窗因查错构建原件目录在诊断派发前关闭，诊断与正式计数均为零。实测候选通过 55 项 Python 和 9 项 JS 定向检查，历史五槽 684 件与 access 78 项按输入重开。

诊断时 PG 确认原 15 项 grant 自然到期，按原范围签发 6＋9 项。检查点由 90 行／epoch 121 推进到 105 行／epoch 136。正式窗复用同一组，剩余 13713.168 秒，新增 0 项。工程 verify 退出 2。environment 21、contract 27、backend 10、query-task-admission 16 全部通过。旧 Doris 门执行 11 项，1 项因 RF_PRODUCT_REVISION 失败；后续门、CI 未运行。两份旧 Doris assessment 仍未资格。

PG-only 维护后继为 `134da209…`，派发前关闭后继为 `344cb4dd…`，诊断关闭后继为 `d5598f01…`。最终正式操作 `c35242b898c04ae3ad5529ba346d320f` 的收口记录单独绑定实测末次关闭。两台 API 均已移除，五个任务持久角色均已退出，前后排空各七项均为零。Fuseki 的 cleanShutdown 为 UNKNOWN。原卷、九归档、旧 17 个停止实例与原 3 个运行实例受保护，四个 Finder 文件散列已核。正式窗 6 个样本的最高计费量为 43,155,800,510 字节（40.19 GiB）。非作者重开末窗 1,343 件原件，末次关闭摘要为 `a3839fe8ebb6e418e42e2280d1d6044acd7a1a4f3f65babdc8f13b8c7d055348`。各窗合计 1,453 组不重复的路径、字节散列及长度见机器回执。

Base 为 `11f438423179d1cc64d043eb2483793b7e03f962`，正式及最终工程实测代码为 `9e84841423bac82911fc989b7b0a4ec999ac1ac7`。main 固定为 `5168f2c93ca226caa521a6dc4ac85439335274c4`。普通推送后的完整分支 Head 与三文件逐字节回读登记在同批本机包外回执 `delivery-readback-11f438.json`。本批无中间 PARTIAL ZIP。[机器回执](final-machine-receipt.json) · [非作者复核](non-author-review.json)
