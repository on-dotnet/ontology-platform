# M0 执行合同归档

2026-10-25，人类在本会话正式批准 M0-MAC-PORTABILITY-001，明确要求以下第二节至文末作为本轮执行要求。原文件名 OntologyPlatform-Mac-CodexMaster-Handoff-and-Portability-V1.md，完整文件 SHA256：094922b82c58bc799188482442c952f5e64728c26f24b32c36e73e93dd3ae29b。本归档不把文档前半部准备指令扩张成系统安装授权。范围以人类最新消息为准：仅M0，不进入SEC/FE/OBS/G2；允许必要项目依赖恢复、开发容器、测试、多Agent Worktree及审查后Git集成，一个ZIP。

---

# 二、交给新 Mac Codex Master 的完整指令（从这里复制到新会话）

## 0. 角色与最新授权

你是私有 GitHub 仓库 `on-dotnet/ontology-platform` 的 **Codex Master / Integrator**，负责计划、委派子 Agent、管理独立 Worktree、冻结公共契约、审查、集成、CI、验证及一个标准 Review ZIP 的交付。

这是**从 Windows 开发主机转移到 macOS 的全新 Codex 会话**。你不能依赖 Windows 会话的私有聊天历史，也不能假称已继承 Windows 本地的 agent 子会话或容器卷。Git 已提交文件和本次用户指令是权威依据。

用户的最新明确要求：

1. 当前 Mac 为主要开发环境，但项目仍须能在 Windows 开发；Linux 容器/CI 继续支持。
2. 保留 **Master + 多 Agent + Git Worktree 并行写入**，不是单 checkout 串行开发。
3. 各 Agent 按可验证里程碑及时 commit/push 任务分支，Master 独立审查及集成验证后及时合并/push `main`。禁止强推、重置覆盖和未验收合并。
4. 当前已完成 `G1-INFRA-001`；原 `G1-WAVE2`（SEC/FE/OBS）尚未启动。**本轮仅授权 `M0-MAC-PORTABILITY-001`：恢复 Master、补齐 Mac 兼容与验证；不实施 G1-WAVE2 业务任务。**
5. 不移动、复制或打印用户 Windows/Codex/GitHub 的登录凭证。任何新系统级安装、权限提升、第三方付费、真实企业凭证、外网服务暴露需要用户明确批准。
6. 执行代码后仍交付唯一一个排除秘密和 `.git` 的标准 ZIP，供 ChatGPT 审查；未通过不伪装 PASS。

## 1. 接管检查（先只读，必须完成）

1. `git fetch --prune origin`，确认远端、`main` HEAD、干净工作树、当前机器芯片架构、macOS 版本及可用工具；如有偏离前序 `25eab6f5...` 的新提交，先解释来源与风险，不覆盖。
2. 按序读取 `AGENTS.md`、`PLANS.md`、`.codex/config.toml`、`.codex/agents/*.toml`、`docs/tasks/current-authorization.md`、`docs/planning/00-10` 相关文档、`docs/bootstrap/ontology-platform-codex-master-plan-bootstrap-v1.0.md`、`docs/development/local-infrastructure.md`、`docs/development/review-package-spec.md`、`docs/evidence/G1-INFRA-001/delivery-report.md`。
3. 输出你识别的 Master 职责、子 Agent 角色、当前 G1 状态、Worktree/Single Writer/Review ZIP 协议、明确禁用项。区别产品运行时 MAF Agent 和 Codex 研发 Agent。
4. 通过当前客户端实际验证自定义子 Agent 是否可发现、是否可以委派只读任务；若当前产品版本或权限不支持，不虚报能力，先记录阻断并提供兼容退路。Master 不应把角色 TOML 当作真实沙箱隔离。
5. 先审查已有当前授权索引，把新的 Mac 迁移授权写成增量记录，不覆盖或伪造 G1-INFRA 的历史验收证据。

## 2. 本轮 M0 允许的 Mac 兼容改造

**先生成清晰的 M0 任务卡、独立分支和验收矩阵，再根据需要派发两个互不冲突的 Worktree 专项。公共根配置、锁文件、CI、AppHost 始终 Single Writer。**

允许审查并修复的范围：

- `backend/src/AppHost/OntologyPlatform.AppHost.csproj` 当前 `NuGetLockFilePath=packages.$(NETCoreSdkRuntimeIdentifier).lock.json`，仓库已有 `packages.win-x64.lock.json` 和 `packages.linux-x64.lock.json`；需要对本机 `osx-arm64`（Intel 则 `osx-x64`）生成官方 NuGet 解析得到的**真实 AppHost 锁文件**并执行受锁 restore、build、test。不能手写仿造锁依赖，更不能破坏现有 Windows/Linux 锁图。
- `scripts/doctor.ps1`、`scripts/verify.ps1`、`scripts/create-review-package.ps1` 及其测试，审查所有 Windows/Linux 假设、平台路径、PowerShell 行为、受限文件权限、正反例兼容。注意现有 doctor 非 Windows 路径是 `node-v...-linux-x64`，必须正确识别 macOS CPU/RID；不能因找不到 Windows/Linux 本地工具就误报 Mac 全局有效工具不可用。
- `scripts/verification-requirements.txt` 目前仅列 Windows x64 CPython3.13、Linux x64 CPython3.12 的 PyYAML wheel hash；在 macOS 下必须真实验证可重复恢复并为**批准的平台/版本**加入实际发布包的合法 hash，或选择经审批的等价锁定方案。不得放弃哈希/许可/完整性验证。
- Docker/容器：检查 PostgreSQL、Keycloak、RustFS、Temurin/Fuseki 锁定镜像摘要是否真实提供运行机器所需的 `linux/arm64` 或 `linux/amd64` 平台；用 `docker manifest inspect`、实际容器运行与探针验证。若没有原生架构，明确报告 BLOCKED/需要兼容镜像审批；不能仅靠 `--platform linux/amd64` 模拟启动就宣称原生兼容和性能可接受。
- Aspire：在 macOS 上实测 DCP/Dashboard、ServiceDefaults、健康检查、容器间网络、回环监听和启动次序；官方 CLI 有无不是本次必需条件，AppHost 是可用入口，避免用实验 API 绕过实际问题。
- PowerShell 原生脚本、绝对路径、UTF-8/LF、大小写敏感、时间/端口、文件权限和 `git worktree` 路径；建立 Windows/macOS/Linux 的真实支持矩阵（OBSERVED/PASS/FAIL/NOT_RUN），不把历史 Windows PASS 改写为 Mac PASS。
- 设计 Mac/Windows/CI 可重复执行的 `doctor`、`verify`、本地 infra runbook 和故障排查文档；更改 CI 时评估私有库 macOS Runner 的费用/使用限制，没有用户授权不启用收费 Runner。至少在本机完成 Mac 真实验证，原 Linux CI 保持不退化。
- 允许完善 Master 迁移交接记录，例如 `docs/development/macos-setup.md`、`docs/handoffs/2026-10-24-mac-master.md`、`docs/tasks/M0-MAC-PORTABILITY-001.md`、相关 ADR/证据和任务合同；请勿重写旧的历史交付报告。

**禁止范围**：不得提前实施 `G1-SEC-001`、`G1-FE-001`、`G1-OBS-001`、G2、真实企业数据源、MCP/MAF 产品功能；不得顺手安装大量新框架、更换 .NET 主版本、重写本体架构或降低原安全/验收要求。

## 3. 并行与 Git 守则

- 本次既要验证 Master 能调度子 Agent，也要保持目录写入隔离。所有写入 Agent 在独立 Worktree + `codex/M0-...` 分支中工作。子 Agent 任务卡列明 `owned_paths`、依赖、Owner、Reviewer、验收与停止条件。只读 Agent 可共享目录。
- 从当前已获批准的 `main` 基线建立任务分支；适用时分成工程脚本兼容与容器架构验证两个工作流。公共构建配置、锁文件、CI、任务授权由 Master 唯一写入。
- 各分支可及时推送标 DRAFT/PARTIAL 的进度；只有独立 Reviewer 通过、针对 Mac 的命令真实执行、原 Linux CI 不退化后，Master 才能将被批准的成果合并到 `main` 并及时 push。
- 不拷贝旧 Windows Worktree 目录；历史远端分支若需要，使用 `git fetch` + 新本机 worktree 建立。禁止 `reset --hard`、`push --force`、覆盖未预期工作树或删除未集成工作树。

## 4. 本次最低验收标准

按真实环境记录完整命令、退出码、macOS/CPU/RID、工具版本、容器平台、依赖图版本、SHA、启动健康、失败与修复。最低应检查：

1. `git`、`gh`、Codex、.NET SDK 10.0.402、Node 24.22.1、pnpm 11.28.8、PowerShell 7、Python3、Docker daemon 的实际可用性。
2. 项目静态规则、结构化语法检查和 Review Package 的正反例，在 Mac 执行，不能跳过坏例。
3. `.NET` 在 `osx-arm64`/`osx-x64` 上受锁 restore、build、MSTest、format 真实通过；保留原 Windows/Linux 锁和 CI 结果。
4. Docker 资源在 Mac 上实际拉起：PostgreSQL、Fuseki/Jena、RustFS、Keycloak，核实 readiness、最小隔离操作、重启持久化；密钥由 Mac 本机安全存储新建，不提交。
5. Aspire AppHost/Dashboard 在 Mac 实际可运行，健康/Trace 关联能查询；完整 LGTM 仍属于 Wave 2，不提前冒充实现。
6. Mac README、诊断命令、适用 RID/架构矩阵、尚未验证的运行条件，以及 Windows 回退手册均完善。
7. 任务分支/Worktree 状态与实际 CI 记录准确，独立 Reviewer 无未解决阻断；本次 M0 工程的验收 ZIP 能在 Mac 创建并独立复核。

如果一项无法执行，请写 `BLOCKED` 或 `NOT_RUN`，不绕过安全校验或篡改配置以取得虚假 PASS。不具备管理员授权时不自行安装系统 Docker/.NET/Homebrew，只列出用户应该安装什么。

## 5. 统一交付与严格停止

- 总状态 PASS/PARTIAL/BLOCKED；明细列出每项实际命令、退出码、机器环境、容器架构、兼容性结论、单项 Reviewer 意见、Git Commit/Branch/Worktree、`main` CI HeadSha。
- 严格使用当前仓库 `scripts/create-review-package.ps1` 和 `docs/development/review-package-spec.md`，生成一个排除 `.git`、真实秘密、令牌、`.env`、Docker 卷、编译缓存的审查 ZIP。记录准确 ZIP 路径、大小、SHA256、重开验证结果；如果工具在 Mac 失败，先在本任务范围内修复并重测。
- 任务通过时，可按上述门禁合并并推送 main；验证不通过则保留任务分支和证据，状态 PARTIAL/BLOCKED，不能假称完成。
- **不自动启动 G1 Wave 2**。最终输出：`M0_MAC_MASTER_READY_FOR_REVIEW`。
- 用户随后会将 Review ZIP 交给 ChatGPT 审查，批准后再向当前 Mac Master 发送原先未执行的 `OntologyPlatform-CodexMaster-G1-Wave2-SEC-FE-OBS-V1.md`（其前提以新的已验证 Mac 基线为准）。

**最终必须停止在 M0 关口。**
