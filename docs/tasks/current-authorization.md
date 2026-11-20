# 当前授权｜G4-ORACLE-MAPPING-QUERY-001

本批按影响复验、登记临时资源并交三份阻断复审文件。执行依据见[研发效率规则](../development/ai-development-efficiency.md)、[审查交付规格](../development/review-package-spec.md)及[资源生命周期](../development/resource-lifecycle.md)。

2026-11-19，用户传达 ChatGPT 对 Doris review-fix-02 的 ACCEPT / GO，RF-02 关闭。Master 已将 main 从 `606ca2d2c61964e6498dd72d5e9ad960d3593bf7` 精确快进至 `5168f2c93ca226caa521a6dc4ac85439335274c4`，普通推送并回读。历史验收与原件由[Doris 卡](G4-DORIS-MAPPING-QUERY-001.md)恢复。

用户已接受阶段 A 和 Oracle P0。自 `8ddaabb90878d5ab72a92908a030b7397c6f2d4d` 起由 Master 在原工作树实施[唯一 A–F](../evidence/G4-ORACLE-MAPPING-QUERY-001/contract-admission-request.md)及[任务卡](G4-ORACLE-MAPPING-QUERY-001.md)。批准本任务独立栈、当前资源准入、零下载准备、替代式恢复与 S0 高风险验证；S0 放行后自动 S1–S3。原 17 个停止资源及三项持卷运行服务保持原状态，旧 Oracle 卷/密钥只保留。main 冻结，G4 PARTIAL，AI OFF。

2026-11-20，Oracle 在 S0 正式取消处 BLOCKED。原交接时占位未确认，两个任务 API 已封闭，证据已保留。S1–S3 延后，集中裁决与保全状态见[阻断交接](../evidence/G4-ORACLE-MAPPING-QUERY-001/implementation-01/s0-blocked/report.md)。

2026-11-20，`s0-recovery-01` 起点为 `9de3b93a0dfddb948b4d68c61ad1b54ce84e0812`。用户批准准确占位晚恢复、当前一致检查点及替代恢复；业务入口持续封闭。三项交付与 RC01–RC06 记录在本批报告。 Oracle S0 BLOCKED，AC03 未通过，S1–S3 未准入，G4 PARTIAL。

2026-11-20 上一恢复批次停止点为 ChatGPT 复审。准确占位已清、原与替代五服务均已退出；RC05 阻断及恢复条件见[当前恢复报告](../evidence/G4-ORACLE-MAPPING-QUERY-001/s0-recovery-01/report.md)。

2026-11-20 的集中授权绑定 s0-recovery-02 和 Base 454d1a2f17581673cbbf44900a5fe241d603f5ef。接受上批 RC01–RC04 限定结论、RC06 停止事实与冻结 Fuseki 的恢复可用性。仅准入正常四账号认证、固定桶版本读取、Compose 安全解析与恢复聚合。Oracle S0 BLOCKED，原清理 NOT_QUALIFIED，G4 PARTIAL。

本批认证窗口已关闭，0/4 个原主体完成新登录，OIDC 为 WAITING_FOR_USER_AUTH。RustFS 实际及独立封存参考各遍历三页，5 个版本、0 个删除标记一致。资源停止后态已核对，RC05 仍 BLOCKED。[本批交接](../evidence/G4-ORACLE-MAPPING-QUERY-001/s0-recovery-02/report.md)

**现行批次 product-resume-01。** 用户批准在当前未合并任务分支上从 `4924f44ec1628b156d7e722513405bc13d376d8e` 推进。4/4 补充按既存原件离线核对。正式取消拆分 AC03-A/B/C；A/C 通过并具备一致副本、资源与权限后进入 S1，再按 S1 结果推进 S2/S3 功能验证。B 继续 BLOCKED / NOT_QUALIFIED。原最终资格、历史失败、原卷与九份归档保留。main 固定，停在 ChatGPT 复审。
