# G4-M1-MAIN-INTEGRATION-001

状态：B / BLOCKED_WITH_WITNESS；P0限定准入通过；稳定产品验收未启动。

最新用户授权：按2026-11-02 Plan审查执行授权执行。原始审批见本任务证据p0/original-documents.json 中的 approval-original.md；完整计划见G4-M1-MAIN-INTEGRATION-001/PLAN.md。

ApprovedMain=d1a61daffe844475b07705797e3ad325cc3f2945；CandidateSourceHead=99753df6f03b184e40b431a5b5aba89d8fa67087；TaskBranch=codex/g4-m1-main-integration-001。Master唯一作者与共享输入责任人，非作者Reviewer只读。

owned_paths：计划第2节精确任务文档、证据、experiments/g4-m1-main-integration所列文件及PgFixtureSecurityTests.cs两处精确身份白名单。read_only_dependencies：其余产品Host、Contracts、Modules、UI、migrations、生成器/产物、共享scripts、CI、锁、历史证据及旧工作树。公共合同无变化。

只复用核验本地工具/镜像，零下载、零费用，最多6容器/6GiB，卷3GiB观测停机阈值。原49产品检查保持INHERITED_NOT_RERUN；CI/Windows/Intel NOT_RUN；AMBER-A1和完整供应链限制保留。

严格停止：任一产品缺陷需越界修复、工具/镜像身份不符、输入漂移或资源边界失败时保存见证并停止对应入口。最终B交唯一LOCAL V3与包外回执，只有全I01-I08和独立Review通过才READY_FOR_CHATGPT_MAIN_MERGE_APPROVAL；不得执行C/main更新或M2/G6。

具体阻断、未完成适配和精确修复申请见 [阻断交接](../evidence/G4-M1-MAIN-INTEGRATION-001/blocked-handoff.md)。本次任何提交/ZIP只交付阻断见证及DRAFT，不代表B完成；不授权C。

## 2026-11-03 精确格式补丁续执行

最新明确授权为精确15文件格式/BOM追加审批；独立源码提交80af5bb3a5c6cbe3906bb6aee8a78c2bc7536f7e，15/15校验并普通推送。原owned_paths仅追加该审批表的精确字节例外。whitespace通过、完整format仍exit2，新T SelfTest初始扫描exit1，状态保持BLOCKED_WITH_WITNESS。当前结果和未应用三文件最小申请见[本轮阻断交接](../evidence/G4-M1-MAIN-INTEGRATION-001/resume-20261103-01/blocked-handoff.md)。旧证据/ZIP原样保留，三文件提案未授权未应用。

## 2026-11-03 三文件精确修复结果

精确三文件补丁已完成，源码提交2b5af7b81fbd78143ea2a76c787bfc2fa402e30d；新T8c7e43ab4f8f27d231d9d83b42c96ef17a1918fe额外无损归档旧空日志。完整format、build、27套SelfTest、双扫描器正反与编译迁移ID检查通过；直接受影响两项目79通过/260真实夹具跳过/0失败。详见[本轮交付](../evidence/G4-M1-MAIN-INTEGRATION-001/three-file-apply-20261103-01/handoff.md)。仅三文件修复及必要证据/收尾；B整体验收未完成，适配器DRAFT和I02–I07未运行，不进入main审批或M2。此前段落保留当时状态，旧空日志按新归档映射恢复原字节。
