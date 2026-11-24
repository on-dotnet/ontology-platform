# 本体智能平台 协作规则

本文件是 Claude 与 Codex 共用的唯一规则文件。产品与架构见 [docs/architecture.md](docs/architecture.md)，界面规则见 [docs/ui-guidelines.md](docs/ui-guidelines.md)，阶段计划见 [docs/roadmap.md](docs/roadmap.md)，开发环境见 [docs/development.md](docs/development.md)。

## 1 项目是什么

AI Native 的本体智能平台：用户把资料和数据交给平台，AI 识别出业务概念、关系和约束并生成带证据的变更集，人审核后发布为标准的本体（RDF、OWL 2、SHACL、SKOS），再供查询、问答和外部智能体使用。基调是 AI First。钢铁冶金是第一个案例。开源，Apache-2.0。

## 2 目录地图

| 路径 | 内容 |
|---|---|
| `backend/` | Python 3.13 + FastAPI 模块化单体；`src/ontology_platform/modules/<模块>/` |
| `web/` | React 19 + Vite 前端 |
| `samples/` | 案例与测试样例：`steel/` 钢铁冶金，`owl-features/` OWL 特性 |
| `docs/` | 架构、界面规范、路线图、开发手册、ADR |
| `dev/` | 开发用配置（国内依赖源等） |
| `compose.yaml`、`dev.ps1` | 容器编排与统一入口 |
| `.claude/` | 技能、子代理与命令白名单 |

## 3 常用命令

代码在本机 Windows，容器跑在 Docker 主机 10.16.0.13（上下文 `linux013-rootless`）。在 PowerShell 7 中从仓库根目录运行：

```powershell
./dev.ps1 up          # 构建并启动 postgres、api、web；平台地址 http://10.16.0.13:28080
./dev.ps1 status      # 状态与地址
./dev.ps1 logs api    # 最近日志
./dev.ps1 test-api tests/test_x.py   # 开发中：只跑受影响的后端测试文件
./dev.ps1 test-api    # 后端全量：ruff、mypy、pytest（8 进程并行）
./dev.ps1 test-web    # 前端：eslint、tsc、vitest
./dev.ps1 lock api    # 重新生成 backend/uv.lock（web 同理）
./dev.ps1 gen-api     # 由后端 OpenAPI 生成 web/src/api/schema.d.ts
./dev.ps1 ci -Report  # 完整门禁（三项同时跑），结果写成提交状态 local-ci
./dev.ps1 clean-images  # 删除已不存在的工作区留下的 ontology/* 镜像标签
```

## 4 红线

- **AI 不直接改本体**：AI 的一切写操作只能生成变更集，经人审核后才生效。不得增加绕过审核的写入路径。
- **外部数据源只读**：连接器只执行只读查询，不得写入用户的业务系统。
- **密钥**：不读取、不打印、不提交 `.env.local`、API Key、证书和私钥。模型 Key 只经环境变量或不入库的文件提供。
- **数据库迁移**：已合并到 main 的 Alembic 迁移不可修改、重命名、删除，只能新增；新迁移要保证上一版程序仍能运行（先加后删）。
- **资源**：Docker 主机上还有其他项目。只操作名字以 `ontology` 或 `op-tmp-` 开头的容器、镜像、卷；临时容器以 `op-tmp-` 开头、用完即删。不执行 `docker compose down -v`、全局 `prune`，不删除数据卷。唯一允许删卷的入口是用户本人运行的 `./dev.ps1 reset`。
- **授权规则**：不得为了让命令通过而修改、删除或放宽任何授权规则（`.claude/settings.json`、`.claude/settings.local.json`、用户级 `~/.claude/settings.json`），也不得用 `git update-index --skip-worktree` 之类的办法隐藏改动。规则拦住时停下来，告诉用户是哪条规则、要执行什么命令，由用户决定。授权规则只能经 PR 正式修改 `.claude/settings.json`。
- **界面**：遵守 [界面规范](docs/ui-guidelines.md)。页面上不输出过程信息；所有文字走 i18n；只用设计令牌。
- **依赖**：只引入许可证宽松的知名开源库，PR 里写明来源、版本、许可证。Docker 主机 CPU 升级前，不引入需要 SSE4.2/AVX 的包（NumPy ≥ 2.4、torch、polars 等）。
- **验证的诚实**：没有实际运行过的不写"已验证"；失败不跳过，不靠重试碰运气。
- **文件**：不新建总结、报告、进度类文件。临时产物放 `.verification/`（已被 Git 忽略）。不创建 CLAUDE.md。

## 5 工作方式

- **语言**：与用户的一切沟通都用简体中文，包括最终答复、过程中的进度说明、等待说明、计划与任务列表条目、子代理和 Codex 的汇报转述。代码标识符、命令、路径、日志原文保持原样。上下文被压缩后的第一批输出尤其要检查。
- 提需求用 `/need <一句话需求>`（[.claude/skills/need](.claude/skills/need/SKILL.md)）：先出理解卡，确认后再动手。验证按 [verify](.claude/skills/verify/SKILL.md)。
- **分支**：长期分支只有 `main`。每个需求从最新 main 开一条短分支（`feat/`、`fix/`、`chore/`），经 PR 合并，合并后删除分支。每个会话一次一个分支。
- **工作区**：会话默认在自己的 git worktree 里工作，不在主检出目录里改代码。几个会话可以同时开发、同时跑测试，镜像按工作区区分，互不覆盖（做法见[开发手册](docs/development.md)"并行开发"一节）。
- 先读后改：动手前读相关代码、测试和本文件指向的文档。
- 先写会失败的测试，再写实现。开发中只跑受影响的测试：`./dev.ps1 test-api tests/<文件>.py`、改了前端时 `./dev.ps1 test-web`。不手动跑后端全量，全量只在门禁里跑一次。在 PR 描述里贴出命令和结果。
- **复审与门禁的顺序**：复审和受影响的测试同时进行；复审没有必须修的项之后，再对最终 HEAD 运行一次 `./dev.ps1 ci -Report`，要求成功（提交状态 `local-ci` 为 success）。按复审意见修改后，第二轮复审只看修改的部分。门禁之后 HEAD 又变了，就重新运行。
- 涉及 L2 范围先停下来问。
- 进度写在 PR 描述里。发现与当前任务无关的问题，用 `gh issue create --label backlog` 记录后继续，不扩大范围。
- 提交与发 PR：`git add`、`git commit`、`git push`、`gh pr create` 各自单独执行，不用 `;` 串成一条；较长的提交信息或 PR 正文先写到 `.verification/` 下的文件，再用 `git commit -F`、`gh pr create --body-file`。
- GitHub Actions 没有额度，不查看、不排查 Actions；门禁以 `./dev.ps1 ci -Report` 写的提交状态 `local-ci` 为准。

### 并行与子代理

- 一个任务里文件范围互不重叠、彼此不等对方结果的部分，交给子代理同时做。同一批文件只有一个写入者；拆不干净就不拆。
- 任务说明写全：只许改哪些路径；不许做 git 写操作；能运行哪些命令；验收标准；最后报告什么（改了哪些文件、测试汇总行原文、没做到的、拿不准的取舍）。
- 子代理不提交：主会话读过 diff、跑过受影响的测试后才提交。子代理的结论要核对，不能直接当作"已验证"。
- 复审交给 `reviewer` 子代理，与受影响的测试同时进行；门禁在复审通过之后跑（见上）。

### Codex 分工

用户提需求并参与理解卡与最终验收；Claude 负责需求分析、拆任务、规格、架构把关、审查、集成与验收；Codex（`openai/codex-plugin-cc` 插件调用本机 codex CLI）作为开发工程师写代码。

- **开工前定执行者**：理解卡里逐项写明由谁做（Codex、Claude、子代理）及理由、Codex 的强度。用户确认理解卡即确认分工。
- **适合派给 Codex**：工作量大、规则清楚、能按文件切开的活，例如按规格实现接口与测试、按界面规范实现页面、实现某个数据源连接器。几行的小改、需要在多处之间权衡的设计，由 Claude 直接做。L2 的设计决策不交给 Codex。
- **先搭共享骨架**：共享文件（类型、接口、路由、i18n 键、一条会失败的测试）由 Claude 先建好；并行的批次按文件范围拆开，互不重叠。
- **任务单**放在 `.verification/codex/<名称>.md`，写明负责的路径、不许碰的路径、禁止任何 git 写操作、禁止运行的命令、验收标准、报告内容。
- **派发**：`node <插件目录>/scripts/codex-companion.mjs task --background --write --fresh --effort <low|medium|high> --cwd <仓库> --prompt-file <任务单>`。机械改写用 medium，按复审意见小修用 low，需要设计的用 high。进度看 `status --all` 和 `jobs/<任务>.log`。
- **测试由 Claude 跑**：Codex 的沙箱里启动 docker 会失败，凡经 `./dev.ps1` 的测试由 Claude 运行，失败的输出再交给 Codex 修。
- **审查不省**：读 diff，运行受影响的测试，派 `reviewer` 复审；界面改动按界面规范第 12 节走查并截图。已知问题：放宽测试断言、为改一处去改生成逻辑、用隐晦写法实现关键条件。
- **提交由 Claude 做**，提交信息里注明哪些部分由 Codex 完成。

## 6 级别定义

- **L0**：文案、样式、纯文档。
- **L1**：新页面、新接口、新查询、新连接器的只读能力；表结构保持原样。
- **L2**：数据库迁移；认证、权限、会话、CSRF；AI 写入路径与审核流程；发布与回滚；外部数据源连接与凭据；`compose.yaml`、`dev.ps1`、`.claude/settings.json`。

拿不准按高一级。

## 7 代码约定

- 标识符与代码注释用英文，简洁，只解释"为什么"；用户文档用中文（README 另有英文版）。
- 后端：ruff（lint + format）与 mypy strict 必须通过；模块按 `models.py / schemas.py / service.py / api.py` 组织，模块之间只调用服务，不跨模块读写表；接口字段 camelCase，错误用 problem+json 并带稳定的 `code`。
- 前端：TypeScript strict，eslint 通过；组件只用设计令牌；所有文字走 i18n 键；接口类型来自 `./dev.ps1 gen-api` 生成的 `schema.d.ts`，不手写重复类型。
- 测试：新功能必须有测试；测试要能在实现缺失时失败，不得为通过而放宽断言。

## 8 文档索引

- [架构说明](docs/architecture.md)
- [界面规范](docs/ui-guidelines.md)
- [路线图](docs/roadmap.md)
- [开发手册](docs/development.md)
- [ADR](docs/adr/)：[0001 推倒重建](docs/adr/0001-rebuild.md)、[0002 技术栈](docs/adr/0002-tech-stack.md)
