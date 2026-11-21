# Oracle S2 受限交接 · 旧查询取证与正式归位

**S2 PARTIAL，S3 NOT_RUN。** 原 A release 已恢复到 revision 3。旧查询 d368 的零成功副作用已证实，原租约占位仍在。本次准确晚 CAS、诊断 ABA、修正后正式十槽各 **0 次**。历史十槽仍为 1 PASS、1 FAIL、8 NOT_RUN。停在 ChatGPT 复审。[机器回执](final-machine-receipt.json) · [非作者复核](non-author-review.json)

## 旧失败与后态

原父 `c02e89f8d8f2481f90058606ccf71b29` 退出 1，子 `5b90bb8f66fb4ddd9bfeddbe5015133a` 退出 2。5349 B stdout 的 SHA-256 为 `d1fba9b095bec4a31831c598e4bbf7bd043579d923e57efd3403a0dab74efc15`。机器回执内含完整结构化原文、两条原始流和命令回执的定位及散列。

| 有证事件 | 同一 Q 的时间（UTC） | 结论 |
|---|---|---|
| 源读完成、B_ACTIVATED 事件 | 13:52:18.3722077、13:52:19.5006019 | 在途审计分四段为 2、2、2、0，共 6 次。 |
| 回滚评估、job 读回 | 13:52:20.858066、13:52:21.3386383 | assessment 已落库，job SUCCEEDED。最后有证客户端调用为 ReadJobAsync，离原截止还有 296.4737 ms。 |
| 原截止、Gateway 捕获异常 | 13:52:21.635112、13:52:21.6423091 | 捕获 503 query_timeout，晚 7.1971 ms。原事件 COMMIT_REJECTED 仅定位到异常捕获。 |

回滚 job 为 `job-cb148f92ceeb4628a071c1a9a87c4af0`，assessment 为 `ma-3867fb5152d5444fb4953f7c47af62b9`，validate 命令为 `30336355-cba2-467b-a1de-0554287d28cc`。B 的正式激活时间为 13:52:19.4744354 UTC，表中列的是随后记下的 B_ACTIVATED 事件。原 stdout 无 rollbackDecision、activatedA。准确区间内只见 B 的激活检查和命令，未见回滚提案、决定、检查或激活提交。最后 Activate 是否被调用仍未知。

独立 PG 后读取到 `query-d368ac610c7745889890e1589653af8f` 为 FAILED、fence 2、原 owner 尚在，leaseUntil 与原 deadline 相同，结果 hash 为空、密文长度和大小为 0，读收据为 0。唯一失败审计为 `83330a307d7a4583aa44e7c2a6db4fa4`，成功审计为 0。原 Oracle 实例已停机，新代两次观察均为零会话。两条 Oracle clientId 只能按时间关联，缺少它们与该 Q 的准确执行归属原件。独立复核据此保留原行、原期限与审计，同连接后续产品任务未准入。

## 正常回滚与时序

归位前，PG 及正式 Active 都指向原 B revision 2。操作者重新验证原 A release 并提出回滚，独立审核者批准，激活者正式提交，随后从提案、Active 和 PG 读取旧 A → B → 新 A 的完整链。北京时间 2026-11-22 00:16:52.8198980 的新回执 `activation-d2dcec9ef54c4f3bb96d60cab449580b`，原 release `release-6d6469e33f744b7c93b8e4d516fca0c4`，新提案 `proposal-c7e58b62fe234d7282689ae7b23000d5`。前缀消费命令 `34de8c4335f94f97b6eac73f32fbf3e3` 连接历史回执与 revision 3，历史查询字节保留。

本次正常 HTTP 路径的 validate 返回耗时 41.6 ms，七轮 job 读回各 447.6–497.2 ms，assessment 读取 441.6 ms，提案 25.2 ms、决定 19.7 ms、激活 1646.8 ms。机器回执逐项列出开始/结束、身份、响应和计时。与旧在途 Q 的进程、传输和计时边界不同，这些数值不足以给旧 timeout 指定主因。归位产生的源读未单独计数。原 Q 的 12 次审计仅归于旧父窗。

PG 首次只读检查为 90 行、epoch 121、最短 6743.490 秒。归位时 6＋9 项最短还有 5705.121 秒，准入需 1710 秒，实际续发 0 项。离线覆盖第二笔自然到期提交中断后重开、错误身份、范围、epoch、短 TTL 和撤销。

## 工程、资源与资格

- FRESH。按同一 backend 输入 `fb4819a6cfc6f68500ac11d7b1d46aa6775b1095935e004637524ce8c9345243` 零下载 prepare，重建 API、Agent、Query，重开 99／222／222 个快照成员，并验证 compose、挂载与新宿主。构建命令分别为 `baf431eb7fb04e3ca790dbbd6b27c22b`、`dc4969af41e544e2aaf81ef6e2007c23`、`28b4ef736f3a4b3da47969857b6e3171`。
- FRESH。隔离 PostgreSQL 四组共 18/18，零跳过。覆盖及时物理释放后的普通最终拒绝、取消、未知或晚释放、错 owner/fence、PG 锁跨 root 以及审计失败回滚。仅普通拒绝且所有原条件成立时原子失败、解占并写审计。隔离库和两个临时容器已回收。
- FRESH。原资源窗 `072d21b9dd5149abb97a0ed9ac92c6a5` 内 finally 两次排空各七项均零，两 API 按 ID 移除，五副本退出，末次准入 `c373ef49bf644a59a988ca7dba07145a` 的运行角色为空，保护清单一致。Fuseki 的 cleanShutdown 仍为 UNKNOWN。冷态 43,004,441,022 B，7 次计费采样最高 43,019,882,942 B，沿用 48/44/4 GiB。原卷、九份封存、四个 Finder 文件均保留。
- FRESH。9b81 的正式关闭、9386 的两副本维护以及 05ea 的七角色归位均按准确代次登记。05ea 收口索引含 119 个原件；以后重开须绑定其真实宿主与关闭证明。
- REUSED。原前五槽 684 个成员及其 546 个冻结成员、access 78 checks 和原 S1 按既有受控输入复用。C 的新增分段诊断、失败 finally 后态及被动消费者只完成构建和离线验证。原四事件资格合同保留。
- NOT_RUN。新诊断、修正后正式十槽、S3 和 CI。AC03-B、Oracle S0、cleanup250ms 沿用原未资格状态。旧正式十槽还有一个独立的后置读取缺陷，ActiveView 仅提供 revision 等字段，完整 activationId 位于提案的 activation 回执。这次独立正常归位已从该回执取全身份。

工程候选的正式 verify 退出 2。首个 backend 门禁尝试重开 implementation-01 的 Oracle S0 资格原件，返回 `OMQ_ORIGINALS_NOT_RUN_s0` 并退出 1，后继 interaction 门禁未执行。独立工程套件 29/29、Oracle 准入套件 145/145。政策检查初次缺少项目 YAML 解析器；从本地按字节核对后，复验退出 0。适用完整验收尚未通过。

## 提交与原件

| 身份 | 值 |
|---|---|
| 接受的 Base，亦为维护期间原工作树所见 HEAD | `7047f9cfb33bd46677433a368f19e5614a0f0179` |
| 历史正式产品实测提交 | `851906f140c0defc0201b392e838e191b20afa27` |
| 工程候选及本次维护构建输入的提交绑定 | `55107958b2e26547dd1f040800c9188d7443601d` |
| 固定 main | `5168f2c93ca226caa521a6dc4ac85439335274c4` |
| 交付 Head | 远端普通推送后从任务分支回读，完整对象、三个 blob 与散列见包外回执 `artifacts/workflow/G4-ORACLE-MAPPING-QUERY-001/product-resume-01/s2-s3-01/aba-delivery-readback-7047f9cf.json`。 |

维护期间源码尚在原工作树，实际构建以三份精确输入及快照绑定，工程候选另以同一输入重核。门禁、旧失败、资源与每条原件路径和散列列在机器回执中。未生成中间 PARTIAL ZIP。
