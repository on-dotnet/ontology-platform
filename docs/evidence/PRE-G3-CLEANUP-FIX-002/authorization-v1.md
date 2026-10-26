# OntologyPlatform · PRE-G3-CLEANUP-FIX-002
## G3 前资源清理纠偏：必须实际清理，不得以只读盘点替代交付

**授权类型：明确的实施授权（Mac Codex Local，普通执行模式），不是 Plan Only。**

- 项目：`/Users/chasen/Developer/repos/ontology-platform`，GitHub：`on-dotnet/ontology-platform`。
- 已交付基线：`de2c020c486df5557b1b17f6b62c1befd96312f2`；开工时务必 `git fetch` 并核对真实 `origin/main`，不允许强制回退。
- **推荐模型：GPT-6.1 Sol，High。** 资源归属调查子 Agent 可用 Medium；独立 Reviewer 推荐 GPT-6 Astra，High。若 Codex 不允许逐个设置则 Master 使用 Sol/High。
- 本轮任务仅修复资源治理缺口，不实施 G3 业务功能；允许在确认的安全白名单内清理**已结束的本项目开发/测试资源**，无须每项重复审批。绝不触碰生产、其他仓库、全局 Codex、未知来源或无法恢复的业务数据。
- 必须遵守根 `AGENTS.md`、`PLANS.md`、当前授权索引、资源生命周期规范、Git Worktree 及审查包 V2 规则。本文件作为用户新的明确授权，覆盖旧文档中将全部 Git/Docker 一概 `KEEP/DEFERRED` 的限制，但不覆盖安全防护。
- **完成标记：`PRE_G3_CLEANUP_FIX_READY_FOR_REVIEW`。** 没有实际清理所选安全候选时不得输出 PASS；如确实全部受阻，输出 `PRE_G3_CLEANUP_FIX_BLOCKED` 并列出不可越过的具体事实与单项所需决策。

## 一、复审发现的问题（必须先读）

前次 PRE-G3-HYGIENE-001：审查包由 47.95 MB 降至约 2 MB，已删除 4 个旧 ZIP 和 3 个收据文件，逻辑回收 66,400,665 bytes。但**Git 分支删除 0、Worktree 删除 0、Docker 资源删除 0**。原 `scripts/maintenance/inspect-resources.ps1` 明确是只读程序，没有 `Apply`，对所有 Git 分支/Worktree/Docker 直接归为 KEEP/DEFERRED；54 项回归主要是构包验证，不代表资源回收成功。

上次 Docker 真实盘点约为 2 个 exited 容器、48 个命名卷、23 个镜像、13 个 Build Cache 记录，Docker 报告卷可回收约 3.691 GB。远程 GitHub 当前约 26 个分支（含 main），没有开放 PR。上述为历史观察，**必须重新读取、逐项核实**，不应直接以旧数值执行操作。

已完成的 G0、G1、M0、G2 与 PRE-G3 任务按**阶段已关闭**处理；不要再把“无法查看某个历史聊天是否仍在使用”作为无限期保留一切资源的理由。正在被当前 Codex 任务持有、带重要 ignored 私有资料或仍有未集成提交的资源例外保留，并说明具体对象。G2 Master 特有本地证书、私有运行配置和调试资料优先保护。

## 二、交付目标与优先级

本次必须同时产生：

1. **有真实效果的资源清理**：对已确认安全的 Git 本地分支、远程分支、历史 Worktree、已结束测试 Docker 容器/卷、重复镜像和旧构建历史采取实际行动，并列出每项成功/保留理由；
2. **可持续的清理机制**：默认 DryRun，单次提供精确资源白名单/版本校验后才 Apply，自动化测试能证明既能安全删除，又能拒绝误删；
3. **前后数字与独立检查**：本轮回收的准确目标和结果，GitHub 远程分支数量、Worktree 数、Docker 各资源数量、Docker 的实际占用变化。不能以 54 项 ReviewPackage 回归替代清理验收。

若至少存在一个确认为安全的候选，却没有执行删除且未给出具体故障证据，**本轮为 FAIL，不允许包装成“PARTIAL 但安全通过”**。若资源部分保留，允许总体 PARTIAL，但所有实际删除和仍需处理的候选必须有可审计区分。

## 三、C1：Git / Worktree 真正回收

先记录 `git branch -avv`、`git worktree list --porcelain`、`git for-each-ref`、`git status`、`git ls-remote`、当前远端 PR、提交接受记录。

- 对早期完成、已审、tip 确认为 `origin/main` 祖先、无开放 PR、远端 tip 未变化的 `codex/*`，列为默认可清理候选。重点核实以前盘点指出的约 **13 个远程祖先任务分支**。当前任务分支、main、活跃工作树关联分支排除在当次删除外。
- 对 Worktree，检查真实位置、当前任务/会话持有情况、tracked/untracked、ignored 内容、符号链接及唯一数据。已结束且没有未保存内容的旧任务树用 `git worktree remove <精确路径>`，不可 `--force`。只在指定旧 Worktree 中清理由工具产生且可再生的 `bin/obj/node_modules/.next/.turbo` 等，禁止粗暴清理整个 ignored 集合；有 `.env`、私有运行配置、PFX、证书、未归档测试证据的树保留，写明阻断原因。
- Worktree 解除后，对真正已合并的本地分支使用 `git branch -d <准确分支>`，不能使用 `-D`。远端祖先分支在保存原 tip / SHA 与无开放 PR 证据后，使用逐个 `git push origin --delete <准确分支>`；每个删除前重新检查 `ls-remote` 的 tip，发生变化停止该项。
- 对非祖先 / cherry-pick 分支，检查 `git cherry`、patch-id、源文件最终实现、独立审核结果，存在唯一未整合提交时保留，并提供差异及修复路线；不得因想把数量降至零而丢掉唯一成果。
- 不删除 `main`、不执行 `git reset --hard`、强推或批量未审核 ref 删除。跨 Mac/Windows 的远端分支引用必须核对，但已完结阶段且无开放任务不要求无法获得的“历史聊天不存在证明”。
- `git worktree prune` 仅用于已确认为失效记录的 metadata，不代替 `git worktree remove`。

交付前后远端分支真实数量、被删 ref 的完整 SHA、Worktree 精确路径与大小、实际删除量、仍保留的非祖先分支及处理建议。

## 四、C2：Docker 真正回收，保护一套可复用开发环境

本次授权的清理对象仅限**本项目已结束测试生成的临时资源**。此前盘点发现 48 个卷主要是 `g2-*`、`m0-mac-*`、`wave2-*` 测试组，每组包含 PostgreSQL、Jena/Fuseki、RustFS、Keycloak 或 LGTM 数据；这些不是生产卷。对于能够通过任务创建记录、测试夹具和隔离命名确认是**可再运行的合成测试数据**，验收归档且无活跃挂载后允许删除；不要求逐条证明测试样例“没有唯一价值”。真实账号、证书、业务事实、审计唯一副本仍需保护。

### 首先明确 KEEP 清单

- 指定一套真正可复用的日常开发数据环境（PG、Jena、RustFS、Keycloak 及需要的 LGTM），记录**准确卷 ID、镜像版本、用途、恢复入口**。若现有卷都是隔离测试卷，不要擅自把它们都称为稳定开发卷；选定一套可安全复用的，或先报告固定开发环境初始化方案。
- 暂保留与 G2 Master 私有 runtime、PFX 或关键恢复操作绑定的卷，除非已有独立完整备份及明确替代方案。
- 不修改 Docker Desktop 的全局配置，不重建/删除默认 `bridge`、`host`、`none` 网络。

### 对安全候选执行真实清理

1. `docker ps -a --no-trunc`、`docker inspect` 和 `docker volume inspect` 建立容器→卷→镜像依赖图；对**停止、属于本项目、无未归档唯一写入层**的精确容器使用 `docker rm <ID>`，保留仍需开发的卷。
2. 对已结束、无容器引用、命名与任务证据一致、内容仅为可再生测试数据的精确卷使用 `docker volume rm <name>`。优先检查历史重复的 `g2-*`、`m0-mac-*`、`wave2-*` 组，**不要运行全局 volume prune**。删除失败不得扩大范围。
3. 对已无容器依赖、非保留清单且由本项目重复构建的精确 Fuseki 镜像，使用 `docker image rm <image-ID>`；镜像层共享时以 Docker 实测空间为准，不把标称大小相加。保留所需固定 tag/digest。
4. 对截图中的项目 `infra/development/fuseki` 历史构建，先用 `docker buildx history ls` 列出实际 ID，再用 `docker buildx history rm <具体ID>` 清除已不需要的历史记录。明确说明“Build history 删除”与“Build cache 实际占用减少”并非同一件事。
5. `docker buildx du` 与 `docker system df -v` 量化剩余缓存；如果无法证明 BuildKit 缓存可按项目隔离，不运行全局 `buildx prune` / `builder prune`，改为输出精确缓存限制与后续治理策略。
6. 区分 Docker 本身的 Build 日志、停止容器日志与 Loki 日志；没有持久化的关键调试事实不能因清理日志而消失。对已验收且有 Git/CI 证据的临时日志允许删除。

禁止 `docker system prune -a --volumes`、`docker volume prune -a`、`docker image prune -a` 或其它全局通配清理；不能触碰非本项目容器、卷、镜像、缓存。

完成后必须用 Docker CLI 重新获取真实前后清单及占用，不以 `Docker Desktop` 手工截图作为唯一证据。若无法执行某类删除（如 Docker socket 权限），保留准确命令与错误、其他类继续推进，最终该项 BLOCKED。若 Docker 仍有大量安全候选未被执行，应判定本任务未完成，不得笼统记录全部 DEFERRED。

## 五、C3：可执行治理工具与质量门禁

- 允许改造 `scripts/maintenance/inspect-resources.ps1`，使其能按**实际状态**给出 `SAFE_CANDIDATE`、`KEEP`、`AMBIGUOUS`，而不是统一 KEEP。
- 新建 `scripts/maintenance/cleanup-resources.ps1` 或等价脚本：默认 `DryRun`；独立且明确的 `Apply` 模式；仅执行审核后生成的资源 ID 白名单，包含资源期望 SHA/tip、Worktree 绝对目录边界、卷/镜像/容器准确 ID 与用途、过期拒绝与变动重验。Git 远端删除逐个比较实际 tip，不能批量无条件删除。
- 本项目既有 `Review ZIP V2` 已验收，没有必要再次重写构包器；仅在本次真实审查证据缺失时做局部最小修复。
- 建立真实临时 Git 仓库/模拟 Docker CLI 回归：祖先安全删除、非祖先保护、脏树拒绝、活跃 Worktree 保护、无权限/资源变更 fail closed、项目边界/其他项目不能被触碰、同名资源不误删、DryRun 零副作用、Apply 结果与白名单一致。
- 开发中按可验证里程碑提前 Review 和 CI，不要把集成留到最后。业务源码 `backend/src/Modules/**`、`apps/web/src/features/**`、`semantic/**`、现有本体/Agent API/发布逻辑全部非本次写入范围。

## 六、C4：公开 GitHub 仓库安全与交接

当前 `on-dotnet/ontology-platform` 已公开。补充一个**只读、覆盖 Git history/任务分支及已提交证据的安全检查**，重点核对是否意外公开真实凭证、生产地址、PFX、私有业务数据或不可公开的模型配置。检测仅记录路径/类别，绝不打印原始秘密。发现真实风险先报告并提出轮换和历史处理计划，不擅自重写远端 Git 历史。

完成后更新 `docs/development/resource-lifecycle.md`、`AGENTS.md`、`PLANS.md`、当前授权和 `docs/handoffs/`：明确安全候选应当按期真实清理，不能通过统一 DEFERRED 掩盖遗漏。阶段 DoD 新增**项目资源回收真实验收**和“如果存在可安全清理的资源但 0 删除则 FAIL”。

## 七、验收报告与停止条件

使用最终 `main` Head 运行可执行验证，并记录**与真实 Head 一致的 GitHub CI**；只有 CI 确有成功结论时才写 PASS。确保当前可靠开发环境仍可复用（至少健康探针或明确限制），并复核没有无意删除其他资源。独立 Reviewer 检查每条删除证据，不能只复查脚本语法。

报告必须有一张按**真实变化**填写的表：

| 类别 | Before | 安全可删候选 | 实际删除 | After | 体积变化 | 未删除的具体原因 |
|---|---:|---:|---:|---:|---:|---|
| Git 本地分支 | | | | | | |
| Git 远程分支 | | | | | | |
| Git Worktree | | | | | | |
| Docker 容器 | | | | | | |
| Docker 卷 | | | | | | |
| Docker 镜像 | | | | | | |
| Docker Build history | | | | | | |
| Docker Build cache | | | | | | |
| Review ZIP | | | | | | |

**工程验收条件：**已知存在安全候选的 Git 分支、Worktree、Docker 测试资源不能全部 0 删除；除非有逐项真实阻断原因且状态 BLOCKED。对未能清理的历史候选给出具体名称和一次性必要决策，而不是笼统“旧会话或数据可能存在”。区分释放逻辑字节、Docker 引擎报告使用量和 macOS 真实物理磁盘空间；不虚报释放值。

按既有 `Review ZIP V2` 输出**唯一审查 ZIP**，包含清理代码、测试、项目真实 before/after、执行台账、独立审查、Git/CI 与完整风险索引；不包含凭证、私有 runtime、原始数据库、历史大型截图及无关数据。保持当前最新有效 ZIP 直到新包成功重开验收，再回收可确定无唯一价值的旧包。

完成输出：`PRE_G3_CLEANUP_FIX_READY_FOR_REVIEW`。如果所有真正可删资源都被实际阻断，输出：`PRE_G3_CLEANUP_FIX_BLOCKED`，附真实阻断对象/失败命令及最小待确认决策。**不得自动进入 G3。**
