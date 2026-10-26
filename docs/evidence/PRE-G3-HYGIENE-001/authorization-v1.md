# OntologyPlatform · PRE-G3-HYGIENE-001
## G2 结束后的资源治理、轻量审查包及 G3 交接执行授权 V1.0

> **用途：**在启动 G3 Master 规划前，对已经验收的 G2 阶段做一次有证据、可复检、可恢复的工程收尾。本文件是**明确的执行授权**，不是只读研究或 G3 功能开发授权。
>
> **推荐 Codex：**GPT-6.1 Sol，**High**，普通执行模式。独立安全/构包审查优先 GPT-6 Astra / High；资源清单和文档研究 Agent 可使用 Sol / Medium。若客户端不能按角色分别设置模型，Master 使用 Sol / High 即可。
>
> **执行位置：**Mac 的 `/Users/chasen/Developer/repos/ontology-platform`，从新的、短生命周期的 **Local** Codex Master 会话执行，推荐会话名 `ontology-platform-pre-g3-hygiene`。原 G2 会话及其可能仍有关联的 Worktree 均作为待保护资源，不直接删除。
>
> **完成标记：**`PRE_G3_HYGIENE_READY_FOR_REVIEW`。此标记仅表示提交审查，**不代表 G3 已获得授权，也不代表 ChatGPT 已验收通过**。

## 0. 任务来源与事实边界

项目：`on-dotnet/ontology-platform`。

上一个已交付并经 ChatGPT 范围内技术复审认可的 G2 Head 预期为：

`46c7a6de70b1b97c032b12a19bc27c1c54e70f4c`

已核实的 G2 Linux CI：`https://github.com/on-dotnet/ontology-platform/actions/runs/40283523824`，`engineering` 和 `governance-integration` 均为 `success`。

此前只读侧聊报告：本地分支约 23 个、远程跟踪分支约 25 个、Worktree 约 23 个、目录名义占用约 9.4 GiB；Docker socket 当时无法访问，**其资源归属和可回收容量尚未证实**。最新独立 GitHub 查询显示远端共有 25 个分支（含 `main`）。所有数量须以**本轮实际读取**为准。

G2 已实现并获范围内认可的本体草稿、SHACL、发布、CAS/Outbox、Jena 查询、MCP/MAF、SSE 和证据链**不得修改或回退**。保留 Monaco `BLOCKED`、真实 LLM `NOT_RUN/BLOCKED`、Windows/Intel/生产 HA 等原有状态。

本轮目标是：

1. 分阶段回收**确认为本项目所有、已完成、无活跃引用、可恢复**的 Git/Worktree/Docker/临时资源；
2. 改造当前会重复复制历史证据和二进制补丁的 Review ZIP 构包规范，提供**安全、紧凑、可复检、可溯源的唯一审查包**；
3. 将“阶段关闭、资源归属、持续集成和轻量交付”固化为下一阶段可复用的工程制度；
4. 提供独立的 G3 新 Master 交接记录，**但不实施 G3 本体编辑器/业务功能**。

## 1. 开工前必须执行的检查

先读取仓库根 `AGENTS.md`、`PLANS.md`、`.codex/config.toml`、相关子目录 `AGENTS.md`、`docs/tasks/current-authorization.md`、`docs/development/review-package-spec.md`、`docs/handoffs/2026-10-26-g2-master.md`、G2 `delivery-report.md`、`monaco-embedded-security-review.md`、`docs/planning/04-roadmap-and-dependency-dag.md`、所有当前使用的任务卡及相关 ADR。

在仓库根执行只读检查：

- `git status --porcelain=v1 --untracked-files=all`；
- `git fetch --prune origin`（仅更新远程跟踪信息，不删除远程分支）；
- `git rev-parse HEAD`、`git rev-parse origin/main`、`git merge-base`；
- `git worktree list --porcelain`、`git branch -avv`、`git for-each-ref`；
- 对已完成任务读取其提交 SHA、审查报告、阶段状态和 CI；
- 读取现有 Review ZIP 目录、生成工具与测试；
- `docker ps -a`、`docker volume ls`、`docker network ls`、`docker system df -v`，以不泄露环境/密钥的方式检查有限容器元数据与项目标签。

若主线已超过预期 G2 Head：**先核对新增提交与当前授权，绝不 reset 或覆盖。** 若发现他人未提交改动，先记录并保护，不修改其工作目录。

在 `docs/evidence/PRE-G3-HYGIENE-001/` 生成**清理前只读清单**，按 Git、Worktree、Docker、ZIP、缓存分别列出资源 ID、归属依据、状态、体积估算、风险和建议动作。任何删除前先保存可复检清单。需要原始清单但含敏感环境字段时，仅保存脱敏摘录。

本次代码和记录的唯一实施分支命名为 `codex/PRE-G3-HYGIENE-001`；Master 负责经独立审查集成到 `main`。所有改变公共文件的步骤实行 Single Writer。可并行委派只读分支调查、Docker 调查、构包专项 Reviewer，但**Git 清理和构包器修改不可并发破坏同一工作树或共享索引**。

## 2. Git 分支与 Worktree：安全条件优先

**目标：**移除经证明不再需要的旧任务工作目录及本地/远程任务分支；不删除未集成成果、当前活跃会话依赖和其他机器还在使用的分支。

### 2.1 必须先分类

为每个 Worktree/分支标记以下一种状态：

- `ACTIVE`：仍有活跃 Codex 会话、任务、锁定 Worktree 或正在审核的 PR；
- `KEEP`：长期 main、G3 准备使用、未完成/未集成、或来源用途不明；
- `SAFE_CANDIDATE`：历史阶段已审、成果已经并入 `origin/main`、没有未提交/未跟踪/被忽略的重要私有数据、无活跃会话及远端任务依赖；
- `AMBIGUOUS`：分支通过 cherry-pick 等方式集成，祖先检查不能证明等价，或者有未核实的跨机器使用；
- `ORPHANED_METADATA`：目录实际丢失、可确认只剩过时 worktree 管理记录。

必须执行并记录：

- `git merge-base --is-ancestor <branch-tip> origin/main`；
- 非祖先场景的 `git cherry`/稳定 patch-id、文件差异与最终 tree 对比，以及相应提交/PR 证据；
- `git status --porcelain=v1 -uall`，并检查**ignored 文件**是否包含证书、私有 Run 配置、数据库、工具状态、未归档审查材料；
- `git worktree list --porcelain` 是否 locked、prunable，是否存在进行中的 Codex 会话；
- 对准备删除的**远程**分支查询确切远程 tip、开放 PR、当前其他机器是否仍在使用。不得将 `git branch -r --merged` 作为唯一判断依据。

**禁止用年龄、`codex/` 前缀或“看起来已经合并”作为删除的唯一证据。**

### 2.2 允许自动执行的安全回收

完成上述检查后，允许对**确切为本项目、已审核完成、无活跃引用、无唯一内容**的候选执行以下受限操作：

1. 使用 `git worktree remove <exact-path>` 正常删除已经确认干净的附属 Worktree；不使用 `--force`，不用手工 `rm -rf` 替代 Git 命令。保留主 checkout 和正在使用的 G2/G3 会话工作树。
2. Worktree 成功移除后，对完全并入主线的本地任务分支使用 `git branch -d <exact-name>`；不得使用 `-D`。有歧义的 cherry-pick 分支先保留。
3. 远程任务分支仅在**实际 tip 未变化、祖先包含已确认、无开放 PR/跨机器活跃引用、任务已验收**的情况下允许 `git push origin --delete <exact-name>`；其他情况 `DEFERRED`，附明确原因和后续处理建议。
4. `git worktree prune` 仅在确认**管理记录对应目录确实不存在**时执行；不把它当作删除真实目录的手段。
5. 所有操作均记录目标、原始 tip、依据、命令、退出码与执行后状态；失败不得自动扩大权限、强推、强删或 `reset --hard`。

自动保护至少包括：`main`、`origin/main`、全部当前活跃/锁定 Worktree、未关闭任务分支、未提交的用户数据、未知来源路径，以及**尚可能被 G3 交接引用的 G2 Master Worktree**。即使某项看似可以删除，只要无法确认其是否被旧聊天或 Windows 电脑使用，就保留并列明。

## 3. Docker 资源与磁盘治理

本轮仅清理已证明由**本项目测试**创建的资源。Docker Desktop 中的其他项目容器、卷、镜像、构建器一律不可触碰。

- 保存 `before/after` Docker 资源清单及逻辑磁盘容量；优先使用标签、命名约定、关联 AppHost、明确的任务创建记录、测试证据进行多重归属认定。
- 保留一套日常开发所需且用户明确希望复用的 PostgreSQL、Jena、RustFS、Keycloak 持久数据卷、固定镜像与必要的开发网络；记录用途、版本、卷名与后续启动方式。
- 临时测试资源只在已完成测试、无当前挂载引用、无敏感/独有数据、拥有证据足以恢复的情况下删除。
- 删除测试卷前，检查是否有仍需的工厂样例、本体发布版本、审计、私有运行凭证或恢复实验数据。必要时先做**经授权且脱敏的备份/摘要**；无法证明安全就保持。
- 运行中的资源先判断所有权及必要性；绝不停止本项目以外的容器。
- 镜像是可共享资源；没有正面证据证明独占且无引用，不删除固定版本镜像。
- 构建缓存可能是 Docker Desktop 全局共享；无法按项目确认归属则只报告容量，不执行全局清理。

**明确禁止：**

- `docker system prune -a --volumes`；
- 无条件 `docker volume prune --all`、全局 `docker builder prune -a`；
- 删除 Docker Desktop 数据目录、重置 Docker Engine、删除整个持久卷集合；
- 打印、写入 Git 或打包容器环境中的密码、密钥、令牌。

Docker socket 若无法连接，标记 `BLOCKED / NOT_VERIFIED`，仍可完成其他任务，**绝不凭旧记录假装已清理**。

## 4. 旧审查 ZIP 和项目临时文件

- 完整盘点 `artifacts/reviews/` 下的 ZIP，记录 `TaskId`、Base/Head、大小、SHA-256、已有验收记录、是否存在只有本地 ZIP 才包含的独有证据。
- **当前 G2 最后一个有效 ZIP 在新轻量包构建和独立校验完成前必须保留**；历史 ZIP 不原地改写，不冒充原 SHA。
- 已有可追溯 Git Commit、文档和 CI、且本地包没有唯一价值的旧阶段 ZIP，可以在成功产生本任务 Review ZIP 后清理。若有无法恢复的重要证据，则保留并标记原因。
- 最终 `artifacts/reviews/` 以**当前一份有效 Review ZIP**为目标；如果保留其他文件必须显示 `DEFERRED` 及理由。
- 不删除历史 Git 记录、已归档测试失败分析、ADR、任务、交接、提交/校验和清单。
- 仅清理明确由项目生成、可重新生成、归属无歧义的临时构建产物；忽略的 `.tools/`、PFX、`.env`、私有 Runtime、证书、Docker 卷备份等一律不按普通垃圾自动删除。
- 不访问或清理用户全局 `~/.codex/`、其他仓库、系统缓存或用户目录中的无关文件。

## 5. Review ZIP V2：从全量重复包升级为轻量可审查包

### 5.1 已发现的真实冗余

上一版 G2 ZIP 包含 `source/` 下所有历史 `docs/evidence`，同时顶层 `evidence/` 再复制一遍，另有约 12.8 MiB 压缩后大小的完整 binary patch。

新规范要求**只对一份文件保存字节内容**；审查仍能从指定 Head、路径和 hash 验证来源。不能为了缩包就丢掉必要的现行源码、合同、真实测试结果或失败证据。

### 5.2 目标 ZIP 结构

建议新建 `schemaVersion=2` 的 **compact reviewer package**，示例：

```text
REVIEW_SUMMARY.md
manifest.json
SHA256SUMS.txt
git/
  commits.txt
  changed-files.json
  diff-text.patch
  diff-check.txt
  ci.json
source/
  ...当前需要审查的非证据源码/配置/测试/契约（保留原仓库相对结构）...
review-evidence/
  validation.json
  delivery-report.md
  selected-tests/
  selected-screenshots/
evidence-index.json
```

最低要求：

1. 收集 Head 下相关**真实源码、配置、测试、接口定义、ADR 与当前任务证据**；不得只提交文档或少量摘要而把关键实现隐藏在外部仓库。
2. 不重复复制 `source/docs/evidence/` 与顶层 evidence/docs。当前 ZIP 任一物理内容最多保留一份；其他引用使用索引及相对路径。
3. `diff-text.patch` 应覆盖本阶段全部必要的**文本代码差异**，二进制文件改用 `changed-files.json` 列出 Base/Head Git blob OID、SHA-256、字节数、路径、变更类型；审查所需代表截图等文件仅保留必要样本。对于被删除/替换的二进制资产，保证可由受控 Git Base/Head 恢复，若无法恢复则保留所需证据，不虚称脱离 Git 也可自给自足。
4. 对不随 ZIP 原文提供的历史大型证据，`evidence-index.json` 至少记录仓库相对路径、所属 Commit/Git blob、SHA-256、大小、测试范围、可访问或重建方式及保留策略。不得用不稳定临时私有路径作为唯一凭据。
5. 保持 Base、Head 为显式 40 位 SHA，Base 是 Head 祖先；从**已提交 Head**读取内容，不能混入未提交文件。主线 CI 必须对应同一个 Head。
6. 保留路径穿越、符号链接、大小写碰撞、重复成员、凭证泄漏、压缩包篡改、差异失真、旧格式兼容等安全门禁。
7. **不要改写旧 schemaVersion=1 ZIP**。新构包器 `VerifyOnly` 要么兼容旧包验证，要么提供明确的只读旧版验证入口和回归测试。
8. 构包中发生中断或校验不通过，不替换最后一个有效 ZIP，不清空原始证据。
9. 允许生成完整审计包的设计作为后续备选，但本阶段最终只向 ChatGPT 交付**一个 compact ZIP**。
10. ZIP 体积采用软门槛：建议不超过 10 MiB；大于 15 MiB 时必须逐项说明必要大型内容。**不能为了数字好看而省略关键证据**。

需修改并测试：

- `docs/development/review-package-spec.md`；
- `scripts/create-review-package.ps1`；
- `scripts/tests/ReviewPackage.Tests.ps1`；
- 必要的任务收尾脚本/CI 门禁与交接规范；
- `PLANS.md`、`AGENTS.md` 的永久阶段收尾条款。

新增/修改第三方直接依赖仍需事先申请；优先使用现有 PowerShell、Git、.NET ZIP/散列 API。

### 5.3 必须实测的回归

用真实临时 Git fixture 和本项目本轮 Head，至少验证：

- 原版 ZIP 正确处理或明确兼容策略；
- Compact 模式完整创建、重开独立验证和固定 Head/source blobs；
- 文本修改、增删重命名、二进制增删修改与大量截图变更；
- `source` 与 evidence 无重复 payload，已省略证据存在完整索引；
- 非祖先 Base、脏树、未跟踪文件、敏感 token、符号链接、路径穿越、大小写冲突和伪造校验和全部拒绝；
- 与真实 Git 提交差异一致，旧阶段 CI 不被虚假复用；
- Review ZIP 实际缩小，附具体压缩前后字节数和保留/省略清单，不仅凭 zip 文件存在就判 PASS；
- Mac 本地和 Linux CI 验证，不破坏已有 Windows 专用脚本的语法和路径兼容性。

## 6. 永久工程改进：把阶段资源回收纳入 DoD

建立可复用的项目级《阶段收尾与资源生命周期规范》，建议路径 `docs/development/resource-lifecycle.md`。

建议新建**默认只读**的 `scripts/maintenance/inspect-resources.ps1`；若实现执行器，默认 `-DryRun`，只有使用白名单、准确资源 ID、前后确认和日志时才接受 `-Apply`。所有脚本支持 macOS/Windows 的 PowerShell 7，不能硬编码 `/Users/...` 或 `C:\...`。

在 `PLANS.md` / `AGENTS.md` 中新增：每个里程碑完成且获审后，Master 应：

- 记录任务分支/Worktree、Docker、Review ZIP 与 ignored 目录的资源归属；
- 审核已集成状态和跨机器活跃引用；
- 先提交/Push、独立 Review、验证同 Head CI，再做有边界的资源回收；
- 只保留当前任务必要的工作树和开发数据；异常保留明确原因与到期复查条件；
- 出具清理前后数量/磁盘占用、待处理清单、成功及未清理理由；
- 将提交、测试、恢复入口和新的 Head 写入下一阶段交接；
- 不把清理变成需要每个小步骤都由用户批准的频繁人工操作，但有歧义/不可逆/生产/跨项目操作必须停下确认。

**保护多 Agent 并行能力**：Worktree 必须仍可正常创建、提交/Push、Review、集成；不能为减少分支数量恢复“共用 main 串行开发”。

## 7. 新 G3 Master 交接

在 `docs/handoffs/` 新增一个简短的 G3 前交接文档，包含：

- 本任务前后的 main/CI，最近已审 G2 状态；
- G3 开始时应该使用的**动态最新 Head**，不能继续机械使用旧 `46c7a6…`；
- 已清理和仍保留的工作树、分支、Docker 资源、旧审查包及恢复方式；
- Monaco `BLOCKED`、真实 LLM `NOT_RUN`、Windows/Intel/生产等未完成项；
- 可直接运行的检查/构包命令与 CI；
- G3 既定**下一步先 Plan**，不得因本任务自动开始 G3 功能开发。

可更新 `docs/tasks/current-authorization.md` 作为本任务授权及实际状态的索引，但不得抹除任何历史审批事实。

## 8. 并行方式、阶段门禁和提交顺序

推荐按照以下 **四个可验证关口**实施，不要重新制造一个直到最后才集成的大任务：

**H1：只读资源盘点与风险分类**
- Git/Worktree/Docker/ZIP 各项证据和受保护/候选清单；
- `current authorization`、真实 main/CI 事实；
- 未确认项保持 `DEFERRED/NOT_VERIFIED`。

**H2：Review ZIP V2 与工具回归**
- 允许单独工具 Agent 在独立 Worktree 开发；
- Master/独立 Reviewer 验证格式/安全/紧凑性/旧包回归；
- 通过后及时 Commit/Push/集成，再继续下一步。

**H3：项目限定清理**
- 仅处理 H1 里证明安全的候选；
- 对需要保护的资料保留；
- 在执行日志中记录每项清理的实际命令、状态及 before/after；
- 完成后抽测已保留开发环境/工程验证可用性。

**H4：收尾与交接**
- 当前阶段任务、ADR、规范、证据摘要、G3 handoff 固化；
- 代码/文档集成到 main，并执行同 Head 的 CI 和独立审查；
- 按 Review ZIP V2 构包，从已提交 Head 生成、独立重开；
- **确认新 ZIP 可用后**清理可证明不再需要的历史本地 Review ZIP；不删除具有唯一证据价值的包；
- 主线和相关任务工作树干净，不破坏活跃或待复审会话；
- 阶段结束后停止，**不直接执行 G3 Plan**。

所有安全清理结果必须真实执行并记录；Docker 不可达、Windows 不可用、旧枝含未知内容等均分别如实保留，不可用静态脚本通过替代。

## 9. 交付物和验收条件

最终只给用户**一个 Review ZIP 的本地完整路径**、文件大小、SHA-256、阶段 Base/Head、GitHub CI URL、任务状态和本次 `PASS/PARTIAL/DEFERRED/NOT_VERIFIED` 摘要。

ZIP 内必须有：

1. `REVIEW_SUMMARY.md`；
2. 版本化的 `manifest.json`、SHA256SUMS 和基线/当前提交及 CI；
3. G3 前可审查的资源盘点、具体清理记录、清理后的剩余项、实际回收量；
4. 当前构包器和回归测试源码、完整或必要的 text diff/二进制索引；
5. 核心测试输出、Review ZIP V2 的实际复检以及独立审查；
6. 面向新 Master 的 G3 交接文档和未完成风险矩阵。

严格区分 `PASS`、`PARTIAL`、`BLOCKED`、`NOT_RUN`、`NOT_VERIFIED`。部分资源因保护条件被保留，并不自动导致其他已执行安全清理失败；但所有未完成范围必须明确记录。若没有可安全删除的资源，应报告零回收并说明原因，**不得为了达到预设容量而删除未知数据**。

完成并独立复检后输出：

`PRE_G3_HYGIENE_READY_FOR_REVIEW`

**到此立即停止。禁止自动启动 G3 或修改 G3 业务源码。**
