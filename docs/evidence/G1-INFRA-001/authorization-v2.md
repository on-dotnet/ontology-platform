# Codex Master 专用授权 V2：G1-INFRA-001 + 并行 Worktree + 持续远程 Git + 标准审查包

> **唯一需要发送给 Codex 的最新实施文件。本文件完整替代之前的 `...ReviewPack-V1.md`。** 另一份 `OntologyPlatform-G1-ENG-001-Review-V1.md` 是供项目负责人阅读、留存的复审报告，不需要发送给 Codex。
>
> **任务编号：** `G1-INFRA-001`。**授权范围：** 项目环境准备、Git 协作规则纠偏、标准审查 ZIP 自动化，以及 G1-INFRA-001 范围内的基础设施实施与验证。**不授权** G1-SEC-001、G1-FE-001、G1-OBS-001、G2 或正式业务功能。继续使用当前 Codex Master 会话，在普通执行模式下启动；首先展示独立工作项与 Worktree 分配，再组织范围内并行执行。

## 0. 必须先读的资料与准入状态

1. 读取根 `AGENTS.md`、`PLANS.md`、`README.md`、`docs/planning/00–10`、`docs/tasks/G1-ENG-001.md`、`docs/evidence/G1-ENG-001/**`、ADR-001/003/005，以及本阶段拟适用的目录规范。
2. 基线提交必须是 `c4679e956d505acd33185e5a289329de67452c84` 或它的合法后继；检查 `git status` 和 `origin/main`，不得强推或覆盖用户未提交改动。
3. 前一阶段独立复审结论为：**静态基线有条件通过，G1-ENG-001 保留 PARTIAL**。`verify -SelfTest` 的历史 PASS 与 `doctor exit 2` 的环境 BLOCKED 均不得篡改。G1 全阶段未通过。
4. 历史 G0 和 G1-ENG-001 文档保持历史事实；以后当前授权信息必须在新的任务卡/审批记录中维护，不要永久写死某个任务编号。
5. 已确认的多行业、冶金首期验证、RDF/OWL/SHACL、Jena/Fuseki、.NET10、Next.js、OpenTelemetry/Grafana 等技术决定继续有效；TMDL、Microsoft GraphRAG、AutoMapper、通用 Repository、生产写回等明确禁止项不恢复。

## 1. 对用户 Git 偏好的正式纠正：Worktree 并行 + 持续提交/推送

### 1.1 必须立即纠正过去错误记录

用户**没有禁用 Worktree，也没有要求全部 Agent 直接在 main 写代码**。用户的真实要求是：

1. **主动利用 Codex 多 Agent 并行开发**，能够拆开的独立任务尽可能并行；
2. 并行的**写入型**任务使用**独立 Git Worktree + 独立任务分支**隔离文件；
3. **及时、定期完成 Git commit 并推送到远程 GitHub**，不要把所有改动积压到一个阶段末尾；
4. Master 负责汇总、独立审查、CI/集成测试，并将**已验收**成果分批集成到 `main`，及时 push 远程；
5. Git 凭证可优先静默使用操作系统已配置的 credential helper / 现有登录状态，**不读取、展示、保存、打包任何认证材料**；认证系统要求人工操作时照常遵守，不得绕过。

旧的“单 checkout、无需 Worktree、Master 唯一代码写者、直接 main 作为默认开发方式”属于**对用户意图的误解**，即刻停止作为未来约束。**只保留公共共享文件 Single Writer 与最终集成 Master 唯一负责**，不限制独立模块的并行开发。

将本项作为新的明确用户决策，更新仓库：

- 根 `AGENTS.md`：删改误写的禁用 Worktree / 直接 main 单人开发表述；强调并行隔离与持续 push；
- `PLANS.md`：新增 Worktree、任务分支、同步、审查、合并、push、冲突处理、恢复规则；
- 相关 `.codex/agents/*.toml`：允许已授权写入型 Agent 在明确任务文件所有权内独立工作，不把 Reviewer 变成写者；
- 新增 `docs/development/git-parallel-workflow.md` 和适当 ADR/任务审查记录；
- 如旧 `README.md` 带有误导性文字，同步改正；**不重写 G0/G1-ENG 已完成历史事实**。在当前新记录中说明这是用户最新明确纠偏，覆盖旧偏好，时间与来源明确。

### 1.2 Worktree 与分支执行规约

- **集成主线**：原有仓库 `main` 由 Master/Integrator 负责，不接受多个子 Agent 并发写入。
- **工作树**：在支持的 Codex Worktree 环境中使用托管 Worktree；否则使用 Git 原生 `git worktree` 在不相互嵌套的独立目录建立工作树，Windows 路径须规范化并记录。仅切换分支而继续共用一个工作目录**不算隔离**。
- **任务分支**：例如 `codex/g1-infra-001-review-pack`、`codex/g1-infra-001-aspire`、`codex/g1-infra-001-toolchain-research`。命名需与任务卡相符，创建前确认没有同名冲突。只读研究 Agent 不必创建 Worktree。
- **文件所有权**：每个任务卡必须声明 `owned_paths`、`read_only_dependencies`、合同 Owner、审查者、依赖和验收。**根构建配置、锁文件、CI、AGENTS/PLANS、公共 DTO、Design Tokens、AppHost 共享配置等同一时段只由一个指定写者修改**。遇到共享修改请求，作为变更提案提交 Master/合同 Owner，不越界直接修改。
- **任务通信**：Master 与子 Agent 使用 Codex 可用的委派、消息、进度和完成反馈能力；同时将可恢复事实写入任务卡、提交和证据，不能把短期 Agent 消息当作唯一依据。
- **并行数量**：根据本机资源、工具实际支持和任务 DAG 控制并发；本轮推荐最多同时 2–3 个独立写入工作项，并保留独立只读审查能力。不能把“逻辑岗位数”误当可并发数量。
- **环境不支持 Worktree 时**：明确记录原因，允许先并行只读研究、随后顺序写入；**不得悄悄解释为用户禁止 Worktree**，也不得让多写者在同一目录抢写。

### 1.3 持续提交、推送与集成规则

1. Master 开工前先 `git fetch` 并核对远端 `origin/main`、本地工作树、已存在分支及 G1-ENG 交付 SHA；发现未预期改动或远端分歧先保护用户变更，不 `reset --hard`、不强推、不覆盖。
2. 各写入 Agent 按**可验证的小里程碑**进行原子 commit：例如规则纠偏、审查包脚本/测试、Aspire 基本工程、容器资源编排。每次提交前执行与改动相符的检查，记录失败/未运行状态。
3. **及时 push 各任务分支到 `origin/codex/...`**；可将尚未满足全部集成条件的成果推送到任务分支以便远程备份和协作，但必须明确 `DRAFT/PARTIAL`，不得误当已可合并。禁止推送密钥、凭证、未授权生产资料。
4. Master 对完成的子任务执行独立 Review、检查分支头和合同、运行必要测试；合格后通过审核可追踪的 PR / merge / cherry-pick 方式**逐批集成进 main**，并**及时 push**。**不需等待整个 G1 结束才同步远程 main**；但 main 绝不接受未审核或关键门禁失败的结果。
5. 每次集成前更新 `origin/main` 事实，复核分支差异和冲突。共享合同、迁移、CI 及锁文件由唯一 Owner 处理；禁止无说明覆盖、静默强推或替换他人改动。
6. 以 GitHub 的实际 workflow run/检查结果作为远程 CI 证据；远程暂不可用时保留 `NOT_VERIFIED`，不要宣称 CI 成功。失败时先处理当前授权范围内的问题；重大阻断上报。
7. **发布审查 ZIP 的阶段快照**必须指向一个具体且已提交的 `HeadSha`（可为任务分支或已集成的 main SHA），写出 `BaseSha`、任务分支及提交关系；不能依赖当前 `origin/main..HEAD` 这种可能为空的表达来恢复审查差异。
8. 清理 Worktree、删除临时分支只在确认其变更已被审查、归档并安全集成后进行；不能删除含未整合成果的工作树。阶段末提交当前工作树清单与剩余分支。

### 1.4 本阶段可并行的工作项（不扩大授权范围）

- **A：Git 规则纠偏及审查包工具**：由指定 Owner 更新仓库研发规范，实现可重复构包、正反例与安全检查。
- **B：基础设施与 Aspire**：由另一独立 Owner 在自己的 Worktree 研究和实施 AppHost/ServiceDefaults、PG/Jena/RustFS/Keycloak 开发资源；若依赖尚未满足，可先完成设计/静态代码，真实启动保持 BLOCKED/NOT_RUN。
- **C：工具链/容器与官方依赖核验**：原则上并行只读研究，报告安装路径、哈希、兼容性和权限边界；如需修改全局配置或共享锁文件由 Master 排队给唯一 Owner。
- **独立 Reviewer**：只读审查各分支，关注架构、机密、静态门禁、真实构建和代码/文档注释。

Master 必须先冻结各任务 owned_paths。若 A 与 B 会同时修改同一工程目录，则调整拆分或顺序，**不能为了追求并行而破坏一致性**。

## 2. 工作项 C：解除 G1 环境阻断（与独立审查包工作可并行）

**先执行 `scripts/doctor.ps1`、只读系统探查及安全来源核查。** 将版本、路径、退出码保存为证据。

目标版本以本仓库 `global.json`、`.node-version`、`package.json`、`.config/dotnet-tools.json` 为准：.NET SDK 10.0.402、Node 24.22.1、pnpm 11.28.8、局部 dotnet-ef 10.0.13 候选。重新核验相应官方发行物/哈希/签名和兼容性，禁止从非官方镜像或未知脚本安装。

本条提示词授权**为本项目准备所需的官方稳定工具链**，优先使用用户目录或隔离目录中的并存安装，不改变机器范围的 SDK、PATH、Node 默认版本或既有全局 EF 工具。若必须进行管理员级安装、系统全局修改或需要不明确的凭证/付费操作，停止并报告所需的具体用户动作。

- 不要为了通过 doctor 而降低精确锁定版本。
- 校验 Node/npm/pnpm 引入版本的安全公告；现有用户安装不应被不必要覆盖。
- 在实际新增应用包后，执行真实的依赖恢复、包锁、许可和安全检查；不得创建伪造锁文件。
- 如果 Docker Desktop/daemon 不可用，先只读探测并列出阻断原因；**未经明确授权不要自行安装系统级 Docker 或修改 WSL/虚拟化配置**。

## 3. 工作项 A：标准审查 ZIP 自动交付机制（以后每阶段必需）

建立可重复、正式可维护的以下项目能力（可与只读工具链核验、独立 Aspire 工作树中的不冲突工作并行）：

- `scripts/create-review-package.ps1`：从明确的 `BaseSha`、`HeadSha`、`TaskId` 创建审查 ZIP。
- `docs/development/review-package-spec.md`：归档内容、安全规则、示例命令及状态语义。
- 对应的正反测试，纳入 `scripts/verify.ps1` / 适当 CI 门禁。

**审查包内容：**

```text
OntologyPlatform-Review-G1-INFRA-001-<shortSHA>.zip
├─ REVIEW_SUMMARY.md             # 中文总结、范围、验证状态、阻断项、下阶段建议
├─ manifest.json                 # taskId、baseSha、headSha、branch、date、status、命令/结果
├─ git/
│  ├─ changed-files.txt
│  ├─ diff.patch                  # BaseSha -> HeadSha 的完整本阶段差异
│  ├─ commits.txt
│  ├─ status.txt
│  └─ diff-check.txt
├─ source/                       # HEAD 中相关的已提交源码、配置、脚本和资源
├─ docs/                         # 本阶段任务卡、ADR、合同、实际审查与测试证据
├─ evidence/                     # 测试输出、构建日志摘要、环境、CI URL、故障记录
└─ SHA256SUMS.txt                 # 各归档成员校验和
```

**强制要求：**

1. 默认使用 Git 已提交文件生成源码快照（如 `git archive HEAD`），不以人工复制整个工程目录作为输入；明确基线 `BaseSha`，即使已将成果合并并推送到 main，也不能用 `origin/main..HEAD` 这种可能为空的差异来代替任务差异。
2. `BaseSha` 必须可验证为 `HeadSha` 的祖先，否则标注冲突、停止构包。检查未提交或未跟踪的需交付资料，要求先依法提交或明确报告排除，不能静默漏掉。
3. **禁止包含** `.git/`、`.env`、`.env.*`（允许无密钥的 `.env.example`）、`.ssh/`、`.codex/auth*`、凭证/密钥、`.pfx/.pem/.key`、缓存、`node_modules/`、`.next/`、`bin/`、`obj/`、镜像、数据库文件、机器级系统日志、私有模型和未授权的企业生产数据。
4. 严格审查源码与 diff 中是否包含疑似密钥或敏感内容；如发现，先修复/撤销敏感提交并报告处理，绝不将原值放入审查包。仅做简单正则扫描不得宣称全面防泄露。用户无需上传 `.git` 或个人环境。
5. 归档内保留中文 Markdown、必要 JSON/YAML/TOML、脚本和当前真实源码，不要求打包无关依赖与编译产物；可以通过文档导航直接找到关键实现、验收命令、失败原因和日志。
6. 在包内提供 `manifest.json` 的 PASS/PARTIAL/BLOCKED/NOT_RUN 逐项证据，而非仅输出口头“通过”。没有真实测试不允许打 PASS。
7. 生成 ZIP 后**重新打开并验证**完整性、文件清单、散列、路径安全、禁止项和 diff 对应 HEAD。故意添加模拟 `.git` / `.env` / token 的隔离负例验证包生成器拒绝或清理；不得用真实凭证测试。
8. 审查 ZIP 输出在被 Git 忽略的 `artifacts/reviews/` 中，不提交 ZIP 到 Git，不上传第三方网盘；最终答复只需给出确切文件路径及归档 SHA256，供用户自行上传 ChatGPT。
9. 将本规范加入根 `AGENTS.md` 和 `PLANS.md` 的所有完成任务 DoD，并确保新任务可沿用；**不要继续把根规则锁死在 G1-ENG-001**。历史证据不重写。
10. CI 成功证据需有明确 GitHub Actions run ID、URL、commit、结论；无法读取则标 `NOT_VERIFIED`，不能仅凭 commit status 为空推断成功或失败。

## 4. 第三子阶段：实施 G1-INFRA-001（仅在必要环境就绪后）

以 `docs/planning/05-agent-team-and-task-contracts.md` 的 G1-INFRA-001 为业务范围，交付以下基础设施纵向能力：

- 建立 `OntologyPlatform.AppHost` 和 `OntologyPlatform.ServiceDefaults`（.NET10），区分启动编排与公共服务默认值。`ServiceDefaults` 仅承担 OpenTelemetry、健康检查、服务发现、HTTP Resilience 等；不放业务模型。
- 在开发环境定义 PostgreSQL、Jena/Fuseki/TDB2、RustFS、Keycloak 的资源、配置模板及健康检查；使用安全凭证引用、不写入固定密码，保留容器端口、数据持久化、启动顺序及重启验证。
- 必要时建立**最小非业务 API 宿主**以实测健康检查和 ServiceDefaults，不实现业务接口、登录流程、前端 Shell、本体发布、MCP/Agent、SSE。超过该边界须先提出变更而不能自行扩权。
- 依赖采用 .NET 官方优先、许可/安全核查、可重复锁定；Aspire 与 Next 优先采用 ADR-003 的稳定通用 JavaScript 资源，不引入未核准实验 Helper。
- 将真实项目接入恢复、编译、测试与 CI；分别记录已通过、未运行和受阻项，禁止以空 solution 或静态检查代替真实构建。
- 接通基本 OTel/健康检查可留钩，但完整 Grafana LGTM/中文运维属于 G1-OBS-001，BFF/Keycloak 的业务认证属于 G1-SEC-001，均不得提前冒充完成。
- 编写 `docs/tasks/G1-INFRA-001.md`、操作手册、风险/依赖登记与独立审核报告，明确后续 SEC/FE/OBS 的契约和阻断。

## 5. 测试与退出门禁

必须执行实际可运行的检查，并记录完整命令、退出码、日志要点、环境和版本：

- `doctor` 在已准备的机器上符合锁定工具链要求；若未达到，状态 `BLOCKED`，不要继续伪装真实集成通过。
- YAML/TOML/JSON/XML、仓库政策、禁止包、注释格式及敏感信息静态检查。
- Review Pack 正例/负例与归档复检，禁止 `.git` 和秘密泄漏。
- 存在真实 .NET 项目后执行 `dotnet restore`、`dotnet build` 和适当测试；存在实际 Web 项目后才执行 pnpm 对应目标。不可运行明确 `NOT_RUN`。
- 可用容器环境中执行 AppHost/ServiceDefaults 与资源启动、健康/日志关联、持久化重启验证；若 Docker 未授权或不可用，则保留 `PARTIAL/BLOCKED`，不称 G1-INFRA 全部完成。
- 记录 GitHub CI 对最终 commit 的 run URL / 结果，若不可获得则 `NOT_VERIFIED`。
- Master 整理实施与验证结果；独立只读 Reviewer 检查任务范围、代码、凭证、配置、日志和阻断项，并报告 Critical/Important/Minor。Important 修复后复验。

## 6. 最终交付、Git 与自动停止

- **允许已授权范围内 2–3 个独立写任务通过 Worktree/任务分支并行**，Master 是 `main` 的唯一集成责任人，不是全部源码的唯一写者。
- **及时 Git commit 与 push**：独立任务的可验证里程碑即提交，并 push 到远程任务分支；经过独立审查/集成检查的成果按批次进入 `main` 并及时推送。提交和远程同步的频率由真实里程碑决定，不盲目每几分钟制造无意义提交；不因为阶段未结束就积压完成代码。
- 禁止 `force push`、覆盖未预期改动、推送明文秘密、静默合并未验收成果到 main；认证可复用但不得读取、泄露或打包凭证。
- 每个工作项完成提交独立审查意见。当前阶段所有代码、Markdown 与证据必须在 Git 中可追溯。若发生不能解决的分支冲突或关键 CI 失败，保留分支与现场并说明阻断。
- **无论 PASS、PARTIAL 还是 BLOCKED，都尽可能生成符合规格的审查 ZIP。** 若未实现真实运行，说明原因，不虚报。
- 最终审查包只要**一个 ZIP 文件**提供给用户上传；实施完成报告不需要另行生成第二个用户操作提示词。必要的详细审计报告包含在 ZIP 内。
- 最终报告必须列明：
  1. 任务状态（PASS / PARTIAL / BLOCKED）、阶段判断与剩余事项；
  2. `BaseSha`、`HeadSha`、`main` 集成 SHA、任务分支及各 Worktree；
  3. 已完成的 commits、对应推送分支、远程 push 结果、PR/合并记录、GitHub CI URL/结论（或 NOT_VERIFIED）；
  4. 并行任务分工、文件所有权及 Reviewer 审查摘要；
  5. 文件、组件清单，真实运行测试结果，阻断/未执行项；
  6. Review ZIP **确切绝对路径、大小、SHA256**，并证明已经复检，ZIP 不包含 `.git`、秘钥或凭证；
  7. 下一任务依赖和停止条件。
- 完成后输出 `G1_INFRA_001_READY_FOR_REVIEW` 并**立即停止**；不得自行执行 G1-SEC-001、G1-FE-001、G1-OBS-001、G2 或其他未授权任务。

### 关于用户新决策的权威优先级

本提示词中的“允许 Worktree 并行、及时提交/推送远程 Git”是**用户最新明确要求**，优先于仓库中先前因误解记录的“单 checkout、不使用 Worktree、只在阶段末 push”等旧文本。执行过程中先将相冲突的永久规则更正并提交，之后让所有任务按新规则运行。
