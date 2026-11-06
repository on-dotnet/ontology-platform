# G4-ENG-WORKFLOW-001 当前状态与实施卡

状态：IMPLEMENTING。此文件为唯一当前状态；最终 Head 从任务分支/包外回执读取，不预填未来SHA。

Base：`709d22ac11880539669d032550a056d7d761dda8`（2026-11-07 fetch已确认）。阶段C回执在原M1树 `artifacts/g4-m1-main-integration-001/phase-c-20261107-01/phase-c-receipt.json`，状态 G4_M1_MAIN_INTEGRATED_WITH_DISCLOSED_LIMITATIONS，原ZIP SHA `b82c8db92d0da05d95214f5fe5286f4c6dbdf9ce7e71b936787478bd3d13bf9a`。只读核对，无改写。

用户批准附件见[原文](../evidence/G4-ENG-WORKFLOW-001/authorization.md)，固定场景见[EG-01～12](../evidence/G4-ENG-WORKFLOW-001/acceptance-scenarios.json)。目标是可运行的按影响验收/幂等准备/短烟测/失败止损/精简证据。非目标：M1冻结交付、业务代码、M2/G6、依赖变更、收费服务、main/CI/全局配置更新。

## 所有权与依赖

Master树 `/Users/chasen/.codex/worktrees/g4-eng-workflow-001/ontology-platform`，分支 `codex/g4-eng-workflow-001`。Master唯一写根AGENTS/PLANS/当前授权、允许的工程政策、verification-gates.json、workflow.py、Workflow.Tests.py、verify接线及本任务文档。环境与烟测为两个真正独立模块，各独立托管树及任务分支，依次集成任务分支；根/共享文件仍Single Writer。非作者Reviewer只读。并发最多Master+两独立写项；批量审查在写项结束后运行。

环境Writer owned：`scripts/maintenance/workflow_environment.py`、`scripts/tests/WorkflowEnvironment.Tests.py`。
烟测Writer owned：`scripts/maintenance/workflow_smoke.py`、`workflow-smoke.mjs`、`scripts/tests/WorkflowSmoke.Tests.py`。
read_only_dependencies：业务源码/锁/SDK版本、M1全部19驱动及历史证据、已批准工具与缓存。只复用已验证内容，不复用旧runtime/凭证。公共合同由Master维护，模块接口 `prepare(root, task)`、`smoke(root, task)`。

依赖顺序：现行政策+gate登记 → 环境准入/定向测试 → 短真实烟测 → 稳定完整工程SelfTest → 独立Review → 提交/输入绑定 → 唯一V3+独立重开。原Full命令保持完整，日常只运行受影响项。

## 已执行与下一动作

- FRESH：基线fetch、阶段C回执核验、Mac宿主preflight；AC sleep=0，锁屏/整会话连续性 NOT_VERIFIED。
- FRESH：11个Workflow定向测试通过；保留初次缺入口与分类负例失败事实。非作者发现的证据JSON误伤产品门禁、零测试判定、超时止损等已进入修复。
- 环境Writer已完成第一次本树离线restore（168包/21项目），仍在核验与幂等回归；此处不把其过程结果认定最终验收。
- REUSED：暂未声明产品结果复用。历史M1成功保留原来源，不宣称本任务新跑。
- NOT_RUN：稳定完整SelfTest、主树真实烟测、新树切换最终证据、CI、Windows、Intel、最终ZIP及独立重开。
- 下一动作：集成两个模块并在Master树真实调用；冻结源码后一次完整工程SelfTest和独立Review。

失败指纹：工程早期行为缺陷的短回归，不启动产品昂贵链；相同未变失败禁止盲重试。资源：当前Master/Writer树与任务私有材料KEEP（未集成/审查中，完成审查及精确引用核验后解除）；未创建付费或生产资源。旧M1树/私有材料均只读。

## 恢复与验收入口

`python3 -B scripts/maintenance/workflow.py --help`；`python3 -B scripts/tests/Workflow.Tests.py`。已提交候选：`workflow.py plan --base <Base> --head <Head> --output <ignored计划>`，再 `verify --task G4-ENG-WORKFLOW-001 --plan <计划>`。复用索引需精确Git提交/回执路径，原回执与日志必须可从同一不可变提交恢复。声明FRESH/REUSED不改旧schema状态枚举。

新树prepare与smoke通过真实调用才可称可用。`.codex` setup/actions 格式未核实，未创建配置、未声称自动启用；交付CLI供人工或已验证环境动作调用。
