# G4-M1-RECOVERY-001 · Codex 单包入口（授权草案）

**当前状态：PROPOSED / AWAITING_USER_APPROVAL。** 此包是 ChatGPT 对 G4-M1 受阻交付的独立复审及一次性恢复任务**建议**，不是用户已批准新的镜像拉取权限。只有用户明确批准此包的受控新下载/运行门禁，Codex 才可按下述阶段执行任何新的拉取或容器操作。

任务名：`本体智能平台｜G4-M1 精确镜像合规准入及 PostgreSQL 真实验收恢复`

TaskId：`G4-M1-RECOVERY-001`。

Master：`GPT-6 Astra / High`；非作者 Reviewer：`GPT-6.1 Sol / High`；必要时同目录不冲突的 Worker：`GPT-6.1 Sol / Medium`。以 Codex 实际提供模型为准，记录真实模型与 effort。不并行争夺同一 Docker daemon/共享合同。

## 阅读顺序

1. `docs/01-EXECUTION-CONTRACT.md`（**当前授权后唯一执行合同**；覆盖以前合同的镜像准入顺序，不改变 G3 等原约束）。
2. `docs/02-ADMISSION-DECISION.md`（原门禁问题、准入先后顺序、镜像许可、预算/清理）。
3. `docs/03-ACCEPTANCE-AND-MAINLINE.md`（真实P3–P5及49项验收/停止）。
4. `docs/04-LESSONS-LEDGER.md`（已踩坑防重复机制）。
5. `evidence/` 三份上一任务保留事实，`review/ChatGPT-independent-review.md`。
6. `references/` 原批准合同的**冻结引用**，以及仓库 Head 实际规则 `AGENTS.md`、`PLANS.md`、`docs/tasks/current-authorization.md`、`docs/development/*`、G4-00、G2/G3。若冲突：G3冻结合同和用户最新明确授权优先，当前新合同只修改准确授权边界。
7. `START-CODEX.md` 供新会话复制；`python3 tools/verify_package.py <ZIP路径>` 可检验本输入 ZIP（不请求第三方依赖）。

## 源码基线

- G3 protected main：`d1a61daffe844475b07705797e3ad325cc3f2945`。
- G4-00 合同 Head：`8afc5d4dfd32e7adb48262cce6587057c0e68715`。
- G4-M1 部分完成并推送 Head：`59edb405dfb4acf4d4a259cffdc3551bafa90d2c`。
- G4-M1 TestedCommit：`958dc6c4eb121958ae889213d1a523a7e7914ce8`。
- 新任务从 G4-M1 Head 创建新独立 Worktree/分支 `codex/g4-m1-recovery-001`。旧 Master/PG/UI Worktree 保留不可清理，必要时按已有工具恢复既有冻结证据。

**本任务不允许自动推进 G4-M2、G4-M3、G4-M4、G5 或 G6，也不允许自动合并 main。**
