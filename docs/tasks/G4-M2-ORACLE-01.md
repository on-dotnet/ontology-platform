# G4-M2-ORACLE-01｜Oracle 开发切片

唯一任务状态：**READY_FOR_REVIEW**（2026-11-13）。本机开发实现与验证完成，停在任务分支审查关口；不代表生产或M2整体完成。

- 范围：用户已明确批准A–F及13GiB镜像/40GiB总磁盘预算，并接受当前冻结镜像的本机开发风险。完整裁决、历史失败和本次结果见[A–F申请](../evidence/G4-M2-ORACLE-01/admission-request.md)。不更新main、不生成ZIP。
- 基线：`5113d0b9b233e307664c964ae9bf3c1d6b10adfb`；分支`codex/g4-m2-oracle-01`。最终Head随交付回执给出。唯一托管树`/Users/chasen/.codex/worktrees/g4-m2-oracle-01/ontology-platform`，operationId=`be289194-eb2d-493d-95f7-e7aaee6e5cd7`；实施RunId=`oracle-impl-02`。Master单写，Reviewer=`/root/oracle_p0_review`。
- 已实现：Oracle 26ai Free **23.26.3.0.0 / Linux ARM64**，驱动23.26.400；ORACLE_READONLY、TCPS、原生READ ONLY与直接READ、固定目标/owner/scope、严格元数据DTO、信任变更栅栏、真实API/UI及工程消费者。10个实际新增包锁定，既有依赖未升级。
- 当前验证：API/Web构建、46共享单元、19合同、122页面组件、5真实Adapter全部通过；11组真实OIDC/UI覆盖创建/探测/启用/发现、撤权、轮换、取消/禁用/注销、在途权限变化、fence接管及审计故障回滚。8作业/5探测与绑定本次输入的脱敏SQL审计原件一致。五类本机产品资格通过；原失败保留，零跳过。
- 源端负例：坏密码/CA/wallet/真实Oracle错SAN拒绝；过期证书由同源隔离TLS夹具验证拒绝（Oracle工具拒绝导入过期证书）。4组权限变化拒绝；取消、禁用、注销均有准确SID/SERIAL提前结束证明。PUBLIC基线与冻结镜像seed一致，仅新增4用户默认授权差异。
- 收尾：已准确删除4容器、2网络、2个已备份tmpfs卷，后验通过；宿主Web已停止。Oracle普通数据卷、用户镜像、私有runtime/PFX/KeyRing/wallet及持久备份KEEP供同任务恢复。PG备份隔离恢复11表一致，Keycloak备份启动后准确realm返回200；未跟踪两项`.DS_Store`保留。
- 证据恢复：[metadata/index.json](../evidence/G4-M2-ORACLE-01/metadata/index.json)保留全部历史并追加本次原件/执行链接；详细本地原件位于`artifacts/workflow/G4-M2-ORACLE-01/implementation-02`。owned_paths为申请E及明确列出的最小工程适配，公共合同/锁由Master单写。
- 限制：CI/Windows/x64/生产一体机NOT_RUN；Oracle整库灾备、其它RU/edition及生产容量未验收。锁屏/睡眠与宿主RSS全程峰值NOT_VERIFIED；当前容器资源上限及实际磁盘占用已核。备份恢复逐查询完整正文未单独留存，实际断言源码/退出回执和摘要已绑定并经独立复核。
- TDengine保持 **WAIT_FOR_EXTERNAL_INPUT**，未恢复调查/开发，未改其工作树、分支或原件。后续继续仍用本Oracle会话和工作树；生产授权不由Git权限推定。
