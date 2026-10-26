# PRE-G3-CLEANUP-FIX-002 任务合同与实施计划

> Master按writing-plans/executing-plans实施，独立只读Review；人类已批准附件全部执行，不重复设计审批。

- 授权：[原文](../evidence/PRE-G3-CLEANUP-FIX-002/authorization-v1.md)；BaseSha=`de2c020c486df5557b1b17f6b62c1befd96312f2`，fetch后origin/main同值。
- Master唯一main集成/公共文件写者，分支`codex/PRE-G3-CLEANUP-FIX-002`，复用当前pre-g3-hygiene托管树；不启动G3、不改G2业务/合同/锁/运行配置、不调用付费模型。
- Master owned_paths：根AGENTS/PLANS、docs/development/resource-lifecycle.md、docs/tasks/PRE-G3-CLEANUP-FIX-002.md、docs/tasks/current-authorization.md、docs/evidence/PRE-G3-CLEANUP-FIX-002/**、docs/handoffs/2026-10-26-pre-g3-cleanup-fix.md、scripts/maintenance/inspect-resources.ps1、scripts/maintenance/audit-public-history.py、scripts/tests/PublicHistory.Tests.py、scripts/tests/InspectorResources.Tests.py、scripts/verify.ps1（仅新真实清理测试接入）。
- 工具Owner cleanup_implementer：独立复用已闭合g2-observability托管树，切新任务枝`codex/PRE-G3-CLEANUP-FIX-002-tools`；仅 owned_paths=`scripts/maintenance/cleanup-resources.ps1`、`scripts/maintenance/cleanup_resources.py`、`scripts/tests/CleanupResources.Tests.py`。原OBS枝/提交保留，ignored只读复用、不碰其他路径；该树在Owner释放且集成Review/CI前从清理候选暂时排除。新建树不是必要，避免无依据影响历史树。
- read_only_dependencies：业务backend/apps/semantic、合同、原Review V2构包器、历史证据/ADR、所有私有runtime/凭证。Git/Docker调查Agent只读，不共享索引写入；所有实际Apply由Master串行执行。

## 设计与工具合同

沿用已验收Review ZIP V2。新增PowerShell7入口+Python标准库清理器（仓库已有Python运行前提，无第三方依赖）；默认DryRun、显式Apply、准确JSON白名单，执行前全量校验且每步再次校验。白名单需taskId/project/repositoryRoot/gitCommonDir/originUrl/expectedMainSha/createdAt/expiresAt/protectedWorktrees/keep/operations。操作种类限精确branch/worktree/已证明可再生cache和project容器/卷/镜像/build history；不提供全局prune/force/网络删除。日志before→command→exit→after，失效/改tip/引用/dirty/私有路径/项目越界/权限错误fail closed。源码只从已提交Head构包。

## 关口与验证

- [x] C0：完整读取整改授权、当前规则/既有工具，fetch核基线；重新Git/PR/Docker调查，阶段关闭由新人类授权确认，保留项必须具体。
- [x] C3：先真实Git+模拟Docker RED，工具实现GREEN（safe ancestor删除、非祖先/dirty/active/项目越界/同名资源ID/权限/过期/变更拒绝、DryRun零副作用、Apply精确白名单）；独立Review，SelfTest接入；commit/push/同HeadCI/早期main集成后才真实Apply。
- [x] C1/C2：保存精确Git/Docker before和审核白名单；逐项正常删除，保留main/当前树/私有G2及具体独特提交；重验并记录实际after和Engine容量，健康探针或明确限制。
- [x] C4：只读公开仓库全部reachable history/refs/blob/证据秘密及潜在私有地址检查，只报路径/类别，不输出值；不改Git历史。更新永久DoD、风险矩阵和交接。
- 交付后置关口：独立逐条实际删除审查已通过，最终main Head的Mac SelfTest/同HeadLinuxCI、唯一轻量包重开、旧包精确回收只按提交后真实manifest与delivery-receipt收口，不在生成它们的Git提交中预填结果；全部完成后输出PRE_G3_CLEANUP_FIX_READY_FOR_REVIEW并停止。

必须有实际候选删除。已知安全候选但0删除=FAIL；只有逐项不可越过失败才能BLOCKED，不再用无法证明历史聊天不存在统一保留。任务研究已确认12远端/10本地/11历史树候选；工具树占用期间排除1树。Docker实际候选2停止容器/24M0-Wave2卷/13重复Fuseki镜像/18项目history；24G2卷具体绑定3套G2 Master runtime/PFX，保护理由逐组列明。Build cache共享归属受限，不全局prune。数量以执行前后真实清单更新。

## 已实施结果

266项CLI操作全部exit0，10树/11本地枝/13远端枝/2容器/24卷/13镜像及175cache实效保持；其中18history只有即时缺席，后验回现，持久完成结论已撤回。175cache逻辑2,530,247,461 bytes。6保护树、24G2卷、12非祖先refs保留，4/4清理后健康探针通过。最终同HeadCI/唯一ZIP/旧包后置回收取实际manifest与外部delivery-receipt，不在Git预填未来结果；阶段交付报告见本任务evidence/delivery-report。

## 后验BuildKit持久删除纠偏（同一FIX002范围）

最终复核发现BuildKit v0.34.0单Ref查询零计数键导致history rm仅内存tombstone、VM自然生命周期后原18记录回现。原工具Owner已释放且工作树已实际移除；Master从此串行接手cleanup-resources.ps1/cleanup_resources.py/CleanupResources.Tests.py三个owned_paths，无并行写者，不扩大业务权限。保留原日志/时点快照，撤回18history持久完成结论；补RED/GREEN、独立Review和同HeadCI后仅原18精确子计划重验。禁止RPC竞态、全局restart/update/prune/配置变更；自然idle不能当成功，须实际观察generation并验证强absence。

## 持久history整改已实测闭环

e40b1be同HeadCI40365150329双job success→Master mainFF/push→新自然代际48a→仅原18fresh DryRun/Apply18/18→18精确DB无记录→闲置后自然VM0→1/newbridge212a仍1history，原18无回现。266唯一资源、284资源变更命令尝试、568日志，不重复计回收；原532即时快照与后验回现证据原样保留。最终CI/ZIP收口仍以最终已提交Head的真实交付回执为准，不进G3。
