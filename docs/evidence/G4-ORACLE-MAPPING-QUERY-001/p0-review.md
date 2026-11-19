# Oracle P0 非作者 Review

审查人 `/root/pg_coupling_facts`，Master 单写。2026-11-19，审查对象是以 `5168f2c93ca226caa521a6dc4ac85439335274c4` 为基线的[唯一 A–F](contract-admission-request.md)，含[事实索引](facts.md)与[任务卡](../../tasks/G4-ORACLE-MAPPING-QUERY-001.md)。

| 首审意见 | 作者修订及复核位置 |
|---|---|
| Oracle 能存 BC 等超出现有公共 instant 可无损承载的值，仅限制 TIMESTAMP(6) 声明不足 | B 增加公元 0001–9999、UTC 微秒与不可无损转换的拒绝，纳入 S0 正反例。 |
| 启用流水线时驱动异步取消不受支持 | D 收紧为实例 Pipelining=false、非池化、单在途命令和反例；事实索引记录当前源码与 26ai 官方出处。 |
| M2 源端 ModuleName 写死旧任务，可能把元数据执行归到新业务 | D 规定新任务的 ModuleName、唯一 ClientId 与源端实际回读、RunId/commandId/queryId 关联，保留原 M2 身份并拒绝旧标记。 |

首审核对了目录版本、SourceSemanticsHash/UNKNOWN 分发、单分支事务范围、原期限以及自然结束/观察滞留对照。产品、设施和恢复在本次 Review 中均 NOT_RUN。最终候选的准确 Head 和非作者增量核对结果由包外交付回执绑定。

**非作者增量结论为 P0 GO。** 三项首审意见均关闭，文档可提交集中准入裁决。独立解封三份 M2 原件（8020 / 1071 / 34613 字节），散列与索引一致；只读库存 SHA-256 为 `2fda67495da82c7270e16f034efcb246a2fbd226f3dfb647076acea7f987e4c9`，涉及 20 个相关容器，3 个运行、17 个退出。非作者核对了 VM 与宿主总量、限制、端口采样、原 Oracle 镜像与卷，以及七文档所有权和 Doris 卡追加范围。

此 GO 的对象为 P0 实施合同。源端取消因果、当期余量、隔离恢复均 NOT_VERIFIED；产品、prepare/restore 和主机服务操作均 NOT_RUN。新任务适配器仍 BLOCKED。
