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


## 2026-11-04 阶段 B 消费者续执行

最新用户指令为执行 2026-11-03 PHASE-B-CONTINUE，原文和SHA归档在 [本轮证据](../evidence/G4-M1-MAIN-INTEGRATION-001/b-continue-20261104-01/index.json)。恢复Head为720c9cb72a22b9d905a1adade65c042de79a5ad0；恢复时工作树干净，远端main/任务分支与批准值一致。已审三文件和旧ZIP保持原字节。本轮RunId=b-continue-20261104-01，Master唯一作者，Reviewer只读。

19项精确白名单任务消费者/配置已补齐为可执行草案：统一身份及输入绑定、离线工具副本、真实工程/生成链/Host/模块/迁移/HTTP/浏览器门禁、源数据库读回、故障恢复、精确回收和离线main竞态fixture。所有产品文件、共享脚本、锁和CI继续只读。边界16项测试通过；这不代表真实产品验收通过。

B0独立审查及新T尚待冻结，I01–I08本轮均NOT_RUN。执行顺序保持B0→T→I01→I05→I03拒绝→I02→I04/I03正例→I06→I07→I08；依赖缓存缺失、真实产品失败、输入漂移或超预算时停止依赖步骤并保留见证。此前阻断和PARTIAL交付段落保留历史时点，不作为本轮通过依据。当前仍不授权main/M2/G6，不生成重复中间ZIP。

B0补充独立审查通过，最终19项驱动清单SHA21c6b08b1246a16c501f1148269d5a18e822af93d66d7807ac702a378d7e1a73，17项边界测试exit0，无开放P0/P1/P2。获准沿用既有B授权冻结新T并开始PREFLIGHT/I01；真实产品门禁仍NOT_RUN，不将本审查当作B完成。


## 2026-11-04 真实 I01 与离线边界事件

新T e09a8c8fc7f21ac1f3d447e8f67493c5f85059f0上原SelfTest27套和任务17项通过；全solution restore失败，后续原生/Web/产品门禁未运行。本任务入口漏读Mac专用锁，SDK解析还绕过项目离线源产生NuGet HTTP缓存；原始事实保留，零下载门禁未满足。此前B0/PREFLIGHT的边界充分性结论被真实运行推翻，不能据此继续标PASS。

四个任务工具完成修复，168锁包本地只读核验、SDK/OS/首次运行隔离probe及22任务测试通过，非作者修复Review通过；尚无修复后完整新T验收，保持BLOCKED_WITH_WITNESS。详见[阻断与恢复交接](../evidence/G4-M1-MAIN-INTEGRATION-001/b-continue-20261104-02/blocked-handoff.md)。仅收尾证据与已审安全副本回收，真实门禁停止，无新V3/main/M2。
