# G4-M2-ORACLE-01｜Oracle P0 一次性准入核对

唯一任务状态：**P0_BLOCKED_WITH_WITNESS**；原P0文档独立审查通过；本次精确元数据诊断证实跨域307，未取到config，待ChatGPT准入裁决；产品未准入。2026-11-13。

- 目标：集中裁决 [A–F 准入申请](../evidence/G4-M2-ORACLE-01/admission-request.md)。本轮只读调查、文档、公开有界元数据；产品仅拟议连接与目录发现。
- 当前阻断：本次获批一次有界诊断确认HTTP307、完整正文0字节，Location指向Oracle Cloud Object Storage跨域源站；未跟随，未保存签名参数，config未取得。后续需裁决该精确对象的跨域读取边界；此前失败具体状态/长度缺失保持UNKNOWN，不用本次结果回填。
- Base：`5113d0b9b233e307664c964ae9bf3c1d6b10adfb`，本轮fetch成功后origin/main同值。Head由最终交付回执给出完整SHA（本页由该提交恢复，避免自引用）；分支`codex/g4-m2-oracle-01`。
- 唯一托管树：`/Users/chasen/.codex/worktrees/g4-m2-oracle-01/ontology-platform`；operationId=`be289194-eb2d-493d-95f7-e7aaee6e5cd7`。TaskId=`G4-M2-ORACLE-01`；RunId=`P0-20261113-01`；历史增量=`P0-CONFIG-20261113-02`；本次诊断=`P0-CONFIG-DIAG-20261113-03`。KEEP：供同会话后续获批实施；审查且任务关闭后再考虑归档。
- Owner：本会话Master，文档唯一写者；Reviewer：非作者只读Agent，回执见申请末尾。DAG：基线/授权→源码与官方资料→A–F→轻量检查→独立审查→提交/push→停止。
- owned_paths：本卡、`docs/evidence/G4-M2-ORACLE-01/admission-request.md`、同目录`metadata/`、`docs/tasks/current-authorization.md`（仅追加）。其余均read_only_dependencies；共享合同/锁/脚本/迁移Single Writer留待另批。
- 已核对：驱动/依赖、数据库ARM64发行/许可、TLS/Wallet/取消、权限/类型、ORACLE_READONLY全生命周期、单机预算及后续源码范围。恢复从[原件索引](../evidence/G4-M2-ORACLE-01/metadata/index.json)按URL/散列读取，不重搜历史。
- 执行：源码读取、官方元数据、宿主/Docker公开元信息、文档范围/链接/原件散列/格式与证据schema，结果见申请。prepare/restore/build/产品测试/历史全量/CI/生产/跨平台均**NOT_RUN**，无产品PASS。
- 边界：不下载nupkg/RPM/镜像层，不安装/启动/生成证书/改全局信任，不更新main，不交ZIP，不另开工程优化或恢复任务。主checkout六项未跟踪`.DS_Store`保留；未操作旧资源。
- TDengine继续**WAIT_FOR_EXTERNAL_INPUT**，未恢复调查/开发、未改其树/分支/原件，未合入其分支。M2未全部完成，不进入M3/M4。

停止位置：ChatGPT准入审查；后续获批后在本Oracle会话、本树继续。
