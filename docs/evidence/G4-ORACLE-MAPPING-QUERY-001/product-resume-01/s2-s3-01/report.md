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
