# 当前授权｜G4-ORACLE-MAPPING-QUERY-001

本批按影响复验、登记临时资源并交三份完整公开脱敏复审文件。执行依据见[研发效率规则](../development/ai-development-efficiency.md)、[审查交付规格](../development/review-package-spec.md)及[资源生命周期](../development/resource-lifecycle.md)。

2026-11-19，用户传达 ChatGPT 对 Doris review-fix-02 的 ACCEPT / GO，RF-02 关闭。Master 已将 main 从 `606ca2d2c61964e6498dd72d5e9ad960d3593bf7` 精确快进至 `5168f2c93ca226caa521a6dc4ac85439335274c4`，普通推送并回读。历史验收与原件由[Doris 卡](G4-DORIS-MAPPING-QUERY-001.md)恢复。

用户已接受阶段 A 和 Oracle P0。自 `8ddaabb90878d5ab72a92908a030b7397c6f2d4d` 起由 Master 在原工作树实施[唯一 A–F](../evidence/G4-ORACLE-MAPPING-QUERY-001/contract-admission-request.md)及[任务卡](G4-ORACLE-MAPPING-QUERY-001.md)。批准本任务独立栈、当前资源准入、零下载准备、替代式恢复与 S0 高风险验证；S0 放行后自动 S1–S3。原 17 个停止资源及三项持卷运行服务保持原状态，旧 Oracle 卷/密钥只保留。main 冻结，G4 PARTIAL，AI OFF。

2026-11-20，Oracle 在 S0 正式取消处 BLOCKED。原交接时占位未确认，两个任务 API 已封闭，证据已保留。S1–S3 延后，集中裁决与保全状态见[阻断交接](../evidence/G4-ORACLE-MAPPING-QUERY-001/implementation-01/s0-blocked/report.md)。

2026-11-20，`s0-recovery-01` 起点为 `9de3b93a0dfddb948b4d68c61ad1b54ce84e0812`。用户批准准确占位晚恢复、当前一致检查点及替代恢复；业务入口持续封闭。三项交付与 RC01–RC06 记录在本批报告。 Oracle S0 BLOCKED，AC03 未通过，S1–S3 未准入，G4 PARTIAL。

2026-11-20 上一恢复批次停止点为 ChatGPT 复审。准确占位已清、原与替代五服务均已退出；RC05 阻断及恢复条件见[当前恢复报告](../evidence/G4-ORACLE-MAPPING-QUERY-001/s0-recovery-01/report.md)。

2026-11-20 的集中授权绑定 s0-recovery-02 和 Base 454d1a2f17581673cbbf44900a5fe241d603f5ef。接受上批 RC01–RC04 限定结论、RC06 停止事实与冻结 Fuseki 的恢复可用性。仅准入正常四账号认证、固定桶版本读取、Compose 安全解析与恢复聚合。Oracle S0 BLOCKED，原清理 NOT_QUALIFIED，G4 PARTIAL。

本批认证窗口已关闭，0/4 个原主体完成新登录，OIDC 为 WAITING_FOR_USER_AUTH。RustFS 实际及独立封存参考各遍历三页，5 个版本、0 个删除标记一致。资源停止后态已核对，RC05 仍 BLOCKED。[本批交接](../evidence/G4-ORACLE-MAPPING-QUERY-001/s0-recovery-02/report.md)

**现行批次 product-resume-01。** 用户批准在当前未合并任务分支上从 `4924f44ec1628b156d7e722513405bc13d376d8e` 推进。4/4 补充按既存原件离线核对。正式取消拆分 AC03-A/B/C；A/C 通过并具备一致副本、资源与权限后进入 S1，再按 S1 结果推进 S2/S3 功能验证。B 继续 BLOCKED / NOT_QUALIFIED。原最终资格、历史失败、原卷与九份归档保留。main 固定，停在 ChatGPT 复审。

本批已核实重置后的 4/4 登录；原会话摘要缺逐行主体关联。分支已修正物理清理与 PG 锁后截止，两台替代正式 API 已登记。新增 PG 三态行锁实测通过，正式源端自然完成竞态仍需真实证据。实机结果与资源范围见[产品恢复报告](../evidence/G4-ORACLE-MAPPING-QUERY-001/product-resume-01/report.md)。


**现行执行批 auth-handoff-01（2026-11-20 最新明确授权）。** Base `33e66879a6b48e25580f1623316b88fe5a5e85cc`，继续原分支／工作树和 `product-resume-01`，持久资源归 `implementation-01`。接受 R1/R2/R3 与受影响结算修复，按输入资格复用，不重做历史恢复。四原账号正常 OIDC：operator-ab 用 `operator-reset-01-20261120` 单独条目，其余三人用 `040700Z` 组各自条目；不重置或抽取秘密。表单可交互后交接，单次四角色人工窗口最多600秒，提交后40秒覆盖回调、CSRF、/me；成功在同一浏览器推进 A/C→S1，新 reader 最多180秒独立认证。固定阶段及预算见[唯一A–F](../evidence/G4-ORACLE-MAPPING-QUERY-001/contract-admission-request.md)本批追加说明。原15项授权仅自然到期可同范围追加最长四小时，保留历史行。先定向回归，再一次实际窗口；无新事实不重复。三份公开脱敏完整文件在 `product-resume-01/auth-handoff-01/`，普通push回读，无中间ZIP；main仍为 `5168f2c93ca226caa521a6dc4ac85439335274c4`，最终停ChatGPT复审。

2026-11-20 auth-handoff-01 收尾：最终代码 `fdadc58f8be175090961c9fcee8af192cf6b790c`，62项定向及非作者21项通过。两次实际窗口各1/4，auditor原件提交后timeout，后续非秘密服务端记录invalid_user_credentials，过期未核实。用户明确授权再次有界登录及仅恢复原3持卷实例；原3已恢复且保护20项匹配，第三窗最终被归档device身份漂移阻断，未启动浏览器。任务5副本停止、2API已移除。唯一状态AUTH_HANDOFF_REVIEW_BLOCKED，历史失败及未资格不变。三份完整公开脱敏文件见 `docs/evidence/G4-ORACLE-MAPPING-QUERY-001/product-resume-01/auth-handoff-01/`；普通push回读后停ChatGPT复审。

用户最新明确要求先修复设备号漂移导致的前检，尽量自动验证，整个已授权任务完成后才最终交付；正常四角色认证及条件A/S1授权继续，秘密与密码重置边界保持。

当前认证已在第三实际窗口取得4/4正常主体及票据；任务仍AUTH_HANDOFF_IMPLEMENTING。A因脚本漏实现合同允许的成功先赢分支而停，先修直接驱动/消费者并验证，再在新代码事实下进行固定顺序窗口，自动继续条件S1；历史失败不改判。用户要求全部完成后交付继续有效。

**当前执行结果（auth-handoff-01）：本批A/S1目标已完成，状态AUTH_HANDOFF_S1_REVIEW_READY。** 实测8f857969ad4fe08e43e5644d951bbf7532e3544d；第四父命令47f4f5d4e2454a759bd3189a5b37f590 exit0，原六阶段连续PASS，真实消费者和非作者独立重开通过，reader恢复为真正新正常会话且零业务重读。当前任务2API已移除、5副本退出，保护原3运行/17停止及归档保持。历史失败与B/cleanup250ms未资格、Oracle S0 BLOCKED/G4 PARTIAL不改；S2/S3未执行。普通push并回读三份完整文件，最终停ChatGPT复审，main保持5168f2c93ca226caa521a6dc4ac85439335274c4。


**现行执行批 s2-s3-01（2026-11-20 最新明确授权）。** 用户执行附件《Codex-G4-ORACLE-MAPPING-QUERY-001-Evidence-Closure-and-S2-S3-20261120.md》，Base `da0046433c87aec3b56a89f15953bfbd4114d9ca`，原分支/工作树、产品 Run `product-resume-01` 与资源 Run `implementation-01` 保持。接受四角色、AC03-A、S1 与新 reader 原事实；先修 EC-01 全窗源审计消费，并离线重开父命令 `47f4f5d4e2454a759bd3189a5b37f590`。非作者确认后自动实施 S2/S3，先补真实入口、独立预期与消费者并冻结新 planId，再启动有界产品窗口。批准六条各自覆盖双表22精确字段的组合 grant，旧15项及历史行保留；不拼接单表授权。正常认证/资源复用及5秒/1秒/250ms合同保持。AC03-B及Oracle S0 BLOCKED，B cleanup250ms NOT_QUALIFIED，G4 PARTIAL；main固定5168f2c93ca226caa521a6dc4ac85439335274c4。完成后普通push回读及本批三份完整公开脱敏文件，停ChatGPT复审，不生成中间PARTIAL ZIP。规格与状态沿唯一任务卡/A–F。

2026-11-20 最新 ABA 澄清：继续当前 s2-s3-01，唯一A–F AC05已更正为一种明确 Mapping 在途顺序（同 Q 源返回后正式 B→原 A，再原截止内409、零成功副作用），撤销未定义“两类全覆盖”数量及等待项。连接版本反例、历史结果与旧 selection 分别保留验收；已有准确有效原件直接复用。无需为措辞更正重跑产品、重开登录或恢复链；其他授权、预算、资源与最终复审关口保持。

2026-11-21当前执行事实：G4-ORACLE-MAPPING-QUERY-001 / product-resume-01 / s2-s3-01 正常认证窗无提交到期，0/4，S2/S3与组合授权签发NOT_RUN；原范围与ABA澄清不变。完成准确服务收尾，保留阻断，当前三文件交接后停ChatGPT复审；不将此状态解释为产品完成或main准入。

2026-11-21最新用户明确可完成正常登录，授权从a40753d33e19c70dbf6e3c43c15e895d2d71bce8连续完成同product-resume-01/s2-s3-01窗口，S2通过自动S3、完成统一交付。认证4/4后发现的本批驱动/证据缺口按影响修复和重验；复用当前五副本/两API及未变构建，不另起恢复工程。原权限、5秒/1秒/250ms及全部阶段预算、AC03-B与G4状态、main保护不变。

2026-11-21当前执行结果：同批后缀s2-s3-01-access-01在Head2f7b4f5476280c3f8e93d69fc94dbc5d6c55f9f0的600秒正常认证窗未提交，0/4；其后十槽NOT_RUN。原前五槽正式资格及六条双表组合grant保留。两API移除、五副本进程停止、保护资源/main不变；原未资格项不提升。本次统一公开脱敏交付后停ChatGPT复审，不声称S2/S3完成，不构中间PARTIAL ZIP。

2026-11-21最新用户说明刚才未在电脑旁，明确再次尝试最终600秒认证窗口。继续原Oracle分支、product-resume-01/s2-s3-01与既有后缀计划；正常登录后自动余下S2/S3。复用已资格原件；原预算、权限、受保护资源、main及G4/B边界不变。

2026-11-21 10:02 用户再次要求弹出正常认证窗，继续原Oracle树/同批，仍600秒上限与原预算。先保留刚结束0/4失败及原资源关闭事实，再按准确两段代次原件恢复入口；S2通过自动S3，统一交付后ChatGPT复审。

2026-11-21最新明确授权：用户要求Codex自行填写现有密码完成正常登录，不再要求本人操作。仅后缀s2-s3-01-access-01使用系统钥匙串四个准确账号条目，operator-ab为独立operator-reset-01-20261120，其余为isolated-login-20261120T040700Z；口令只在本机进程内直填已核验本机OIDC表单，不显示、写日志、落盘、导出会话或重置密码。原600秒/新reader180秒/提交40秒与产品预算不变。最新父04f23ea8cfe34868a8500b80164d86fb认证4/4及34checks通过；access因源清理未确认503失败，后9槽NOT_RUN，权限/源ACL准确恢复。继续短链修复和自动S2→S3，当前状态S2_S3_IMPLEMENTING。

2026-11-21 本批收尾状态为 **S2_BLOCKED_SOURCE_ACL_CLEANUP**。四角色已经正常认证，产品父命令 685e33e9abd749168f6152789677859a 在源 READ 撤权清理处失败。恢复权限并保留准确失败查询和租约，原资源已收口，S3 为 NOT_RUN。源证明修正通过本地定向测试，实机资格仍待核。当前停点为原分支统一交付及 ChatGPT 复审。详见[任务卡](G4-ORACLE-MAPPING-QUERY-001.md)和[本批报告](../evidence/G4-ORACLE-MAPPING-QUERY-001/product-resume-01/s2-s3-01/report.md)。

2026-11-21 用户从 `095d2dd8ff957afa64f01fd938f18ffd357d8d5c` 明确继续同分支、同批。唯一新维护对象为 `query-3e6bb50bdffe43feaa09736718b1dcb0` 的原租约。保留原 FAILED 和失败审计，先实测源 READ 撤权及清理，再按 S2 资格自动推进 S3。沿既有正常静默认证、单条双表 grant、原预算及受保护资源边界。

2026-11-21 本轮已按续行授权清理唯一指定行的残留租约。最新四角色正常认证和 source READ / access 均获资格，原失败完整保留。S2 的唯一 Mapping ABA 在当前与既存查询的会话一致性检查处失败，B 提案已获批但未激活，S3 未运行。2 个 API 与 5 个任务副本已收口。当前状态为 S2_PARTIAL_ABA_SESSION_BLOCKED_CHATGPT_REVIEW，统一交付后停 ChatGPT 复审。见[本批报告](../evidence/G4-ORACLE-MAPPING-QUERY-001/product-resume-01/s2-s3-01/report.md)。

2026-11-21 用户明确从 6221362a 继续原分支、原批次，以本轮 reader 和当前 auditor 独立审批修正 Oracle ABA，复用 access；S2 通过后自动 S3。本轮收尾的工程候选 c7a6bcbc 已核浏览器正常审核端点合同与当前 reader 查询原件，实机在途入口仍未完成。原 5 秒／1 秒／250 ms、六条双表 grant、AC03-B、Oracle S0、G4 和 main 边界继续有效。三份公开文件汇总至[本批报告](../evidence/G4-ORACLE-MAPPING-QUERY-001/product-resume-01/s2-s3-01/report.md)，停 ChatGPT 复审。
