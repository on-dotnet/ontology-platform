# Oracle 双表 Mapping 与 Query 验收交付

**S2 部分通过，在源表 READ 撤权反例处阻断。S3 未运行。** 四角色已自动完成正常登录。当前停止点为 ChatGPT 复审。最后实机父命令为 `685e33e9abd749168f6152789677859a`，原始退出码 1。

| 输入 | 准确绑定 |
|---|---|
| 任务、产品 Run、资源 Run | G4-ORACLE-MAPPING-QUERY-001 / product-resume-01 / implementation-01 |
| 分支、批次、后缀计划 | codex/g4-oracle-mapping-query-001 / s2-s3-01 / s2-s3-01-access-01 |
| 原始 Base、此次续行起点 | `da0046433c87aec3b56a89f15953bfbd4114d9ca`、`a40753d33e19c70dbf6e3c43c15e895d2d71bce8` |
| 最后浏览器实测 Head | `ee802b487f386417e312d40e84978ab49e78c182` |
| 源证明修正和本地定向验证 Head | `124dc68ed668b1178d1070cf728894fb489c6097` |
| 实机后端构建输入，旧前五槽构建输入 | `e8b537ed53b24faac246757d9de6592ae6a03ddeb96c81767f1b4373892d0877`、`53bddbec15779aa28ad25dc3082986027dbc6586f289add3326be2342d3d15ea` |
| 受保护 main | `5168f2c93ca226caa521a6dc4ac85439335274c4` |

## EC-01 与既有产品原件

原父 `47f4f5d4e2454a759bd3189a5b37f590` 在 `8f857969ad4fe08e43e5644d951bbf7532e3544d` 实测。收紧后的消费者离线重开 170 件、623,536 字节。六段按顺序为 0、1、0、1、0、0 次业务 SELECT。无过滤父全窗恰有 2 个真实事件，与各段并集逐事件一致，间隙为 0。非作者核准原件索引 `f5fca1f634c23cb1b8f43d681fe402bab60b8f27a432ef7ac2aaf263c3c9b950`。认证、新 reader 和恢复各自有独立零读窗口。

原父 `edd1379b83c246329579075d16ccda58` 的认证、词汇、Mapping、查询和关系五槽，按原输入在 `2a2ea74ff72c22860e4927318913eaece9d14f9f` 单独取得资格。五槽业务读分别为 0、0、0、10、40，间隙为 0。原父失败保留。更早的 e4cf6ad7 父窗曾在 Mapping 审计失败时暂报 PASS，该槽保留原报告状态并明确登记为 NOT_QUALIFIED。四角色、AC03-A 成功先赢、S1、同主体新 reader 原字节恢复和 AC03-C 的 PG 8/8 沿既有实测复用。

## 最后产品窗口

四账号在共享 600 秒窗内完成正常登录、回调及主体核对，34/34 项检查通过。正式连接 Probe 五阶段通过，末阶段累计 738 ms。reader 在正式 GET 上用 1280.8 ms 恢复本人历史关系查询的 5,056 个原字节，SHA-256 为 `fcb551ca11b24fb0a1cec8e38f07fb038d95ba774916c0cafdf2b3ad064c3e66`，该段业务读为 0。首次新关系查询的两个业务读取均在其准确窗口内。父全窗业务读总数为 2，间隙为 0。全部产品请求仍受 5 秒总期限、1 秒源分支与 250 ms 清理期限约束。

| access 内的实际请求 | 结果 | 源业务读取 |
|---|---|---:|
| viewer-a 新双表关系查询 `query-61cd21d6128d453f8b8472c8b38d636d` | HTTP 200、FOUND、两份来源回执 | 2 |
| 无 grant 的主体、撤销 execute、少一字段、自然到期 | 各自 HTTP 200、UNAUTHORIZED | 0 |
| 短 TTL | 准入拒绝并回读原 grant | 0 |
| 目标表 READ 撤回后的查询 `query-3e6bb50bdffe43feaa09736718b1dcb0` | HTTP 503，query_source_cleanup_unconfirmed，883.0 ms | 0 |

源表 ACL 在 finally 中经命令 `1724a6c651f34990865fd58c37a6ffa5` 恢复。其后 PostgreSQL 查询行仍为 FAILED、fence 2，原 Oracle 租约保留。执行审计只有一条 failure，没有成功结果。API 先记录 RESOURCE_FAILURE，再记录 PHYSICAL_DISPOSED。独立观察时任务源会话为零。源清理未在原查询获得确认，后续正常 Query 将被同连接门禁拒绝。

已定位到正式证明视图按三条直接授权计数。撤回其中一条，单行 BLOCKED_COUNT 为正。修正前适配器在完整证明返回后抛出通用异常，明确拒绝未进入独占连接的确认路径。修正后，现行版本的单行有效阻断证明返回拒绝，空、多行、负数、小数、错版本和 I/O 异常保留失败路径。修正编译通过，35 项 adapter/资源所有权定向测试通过。新代码在本次保留租约下没有新产品实测。

## 平台与源权限

每项使用一条实际 grant，自身包含同一 connectionId、org-demo、site-a 和 22 个精确 FieldRef。两个 ObjectRef 是 PRODUCTION/OMQ_ENTITY 和 CaseOwner/OmqTarget。每表依 ordinal 1 至 11 为 ROW_ID、JOIN_KEY、VAL、ORG_ID、SITE_ID、EXT_ID、LABEL、FROM_TS、TO_TS、EVENT_TS、OBSERVED_TS。

| 角色与 operation | 最新签发 ID |
|---|---|
| operator / mapping.source.validate | `omq-s23-97079e300a66540eb7b53a5f6f3ebf2a` |
| auditor / mapping.source.validate | `omq-s23-4ded2c11b4226faae7048d8ac391bb56` |
| activator / mapping.source.validate | `omq-s23-a42ab8e97dc92c8027e702c4a69c1b4b` |
| reader / data.query.execute | `omq-s23-a3aedb231d0f77c6711156fc8ce4dac2` |
| reader / data.query.result.read | `omq-s23-ce8f478983910496be13d7b822675356` |
| reader / data.query.evidence.read | `omq-s23-a39a4cfd7be6689a3dba1ede4be26892` |

03:18:50 UTC 同范围续授后平台从 60 行增为 75 行，原 15 条及其两轮共 30 条续发历史逐字段保留。最新 6 条组合 grant 和 9 条无字段工作流 grant 单列登记。04:39:12 UTC 平台回读 75 行、epoch 94，六条当时有效，记录的到期时间是 07:18:50.397521 UTC。九组 execute 权限变更均有准确恢复后态，两次源表直接 READ 撤回及恢复均已回读。result/evidence 专项撤权场景未运行。

## AC 覆盖与保留项

| 条款 | 实际覆盖 | 当前资格 |
|---|---|---|
| AC01–02 | 既有 Oracle 固定投影、事务/水位和单表原件，当前双表关系实读 | 保留分项原资格 |
| AC03 | A 成功先赢，C 既有 PG 8/8，B 没有合格的原期限内取消命中 | B BLOCKED，cleanup250ms NOT_QUALIFIED，Oracle S0 BLOCKED |
| AC04、AC06 | 既有正式提案、异人审核、激活、双表精确值/时间与关系。已测 NULL、接壤、重复目标、多父、扇出等原前缀范围 | 已执行部分按原输入复用 |
| AC05 | 当前执行权限四项拒绝已核。唯一在途 ABA 要求同一 Q 完成真实源读后，正式激活 B、回滚激活原 A，在原期限内 409 query_binding_stale，零成功副作用 | 本窗 ABA 及单列的连接/版本反例 NOT_RUN。历史结果恢复单列 |
| AC07–08 | 新双表 FOUND、四项 UNAUTHORIZED、本人历史关系结果原字节 | 完整六态及 100/101、当期新 reader 恢复和撤回结果/来源读取权限均未资格 |
| AC09 | HTTP 健康关系及来源回执已实测 | 独立 S3、UI 三能力、MCP 四工具、刷新、撤权清屏及迟到响应 NOT_RUN |
| AC10 | 既有 PG 黄金字节、Oracle M2 目录合同，17 份 Doris 历史原件散列相符 | 当前 Doris 类型序列化未资格 |
| AC11 | 原计划、资源和剩余 TTL 核验，父全窗审计、续授与权限恢复 | 新后端与既有产品构建输入不同，完整工程资格未签发 |

trust/secret 没有同任务可逆替代版本。CI、完整 SelfTest 和跨平台验证为 NOT_RUN。G4 为 PARTIAL。

## 保留的失败与资源收尾

此前无提交的 600 秒窗口及其他早期失败逐窗保存在机器回执。父 04f23ea8 首次在源 ACL 反例失败，7e3085f4 与 60a80687 在健康查询的源前置检查处失败。三次历史维护仅命中各自固定的行，准确 CAS 命令分别为 56a20ab08e69402e8469f7c8c8362f4c、7e9289f17c0740a68a18058360f6a1c4、de30f36b29a44481993c2babfa3969c8。最后窗口查询 `query-3e6bb50bdffe43feaa09736718b1dcb0` 需要单独处置才能释放同连接容量。现有维护入口的目标均与此行不同。

关闭先后两次核对七项队列/工作计数，均为零。两个准确 API 已分别移除并回读缺席。首次原生停止走旧基线计量被拒绝，记录值为 43,051,581,886 字节。同批停止入口接回原产品计量，仍使用 40 GiB 上限。Oracle、RustFS、IdP、PG 原生停止，PG 控制状态为 shut down。Fuseki 进程退出，cleanShutdown 为 UNKNOWN，锁仍可见。关闭账本为 `a2bfcbd13fbb42c8856081845ac002a4`。四个主机端口的服务随本批收口，Web 进程退出并回读端口释放。17 个保留停止项、3 个受保护原运行项及 9 个归档继续保留。最后一次额度实测 42,895,778,238 / 42,949,672,960 字节。

最新窗口有 14 条主机心跳。该窗锁屏/熄屏连续性为 NOT_VERIFIED。后端工程定向检查为 35 项，S2 Python 为 34 项，JS 为 4 项，各自按原命令计数。

## 原件定位

机器回执列出 7,075 条实跑命令的 Run、commandId、原回执长度与 SHA。每份本机原回执给出实际双流身份、长度、散列和时限。另有 200 个关联原件的相对路径、长度与 SHA。8 个 Web 进程的 START、READY、END 原始事件及双流也已按准确身份登记。审查范围和索引时间截止点在机器回执中。浏览器会话、密码和私有双流留在本机。上一版三份文件精确绑定到提交 `70c94502a2bfbb0a306ccf599403a75fceeb61b1`。本次交付提交由三份文件的同一固定 Git 链接标识。当前没有中间 PARTIAL ZIP。
