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
./dev.ps1 up          # 构建并启动 postgres、api、web（开发栈只有一套，同一时间只让一个工作区运行）；平台地址 http://10.16.0.13:28080
./dev.ps1 status      # 状态与地址
./dev.ps1 logs api    # 最近日志
./dev.ps1 test-api tests/test_x.py   # 开发中：只跑受影响的后端测试文件
./dev.ps1 test-api    # 后端全量：ruff、mypy、pytest（8 进程并行）
./dev.ps1 test-web    # 前端：eslint、tsc、vitest
./dev.ps1 e2e         # 端到端冒烟：临时环境里用 Playwright 走登录、本体、审核、探索，跑完即删（不在 ci 里）
./dev.ps1 lock api    # 重新生成 backend/uv.lock（web 同理）
./dev.ps1 gen-api     # 由后端 OpenAPI 生成 web/src/api/schema.d.ts
./dev.ps1 ci -Report  # 校验 Compose 配置，运行后端与前端测试、构建镜像并核对接口类型，结果写入提交状态 local-ci
./dev.ps1 images      # 列出本项目镜像及所属工作区
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

- **语言**：与用户沟通一律用简体中文，包括最终答复、进度、等待、计划、任务条目和转述。保留标识符、命令、路径、日志原文，压缩上下文后尤其要检查首批输出。
- **需求与分工**：用户通过 [need](.claude/skills/need/SKILL.md) 的 `/need <一句话需求>` 提需求、确认理解卡并参与最终验收。Claude 分析需求、拆任务、定规格、把关架构、审查、集成和验收。理解卡逐项写明 Claude、Codex 或子代理的分工、理由及 Codex 强度，确认后开工。
- **分支与工作区**：长期分支只有 `main`。每个需求从最新 main 开 `feat/`、`fix/` 或 `chore/` 短分支，经 PR 合并后删除。每个会话一次一个分支，默认在自己的 worktree 开发和测试，不在主检出目录改代码。镜像按工作区隔离（见开发手册"并行开发"）。
- **粒度**：一个 PR 控制在约 1500 行或半天以内，按"一条用户能用的功能从后端到界面"纵切，不按文件路径横切成大批次。
- **先读后改**：动手前读相关代码、测试和本文件指向的文档；先写会失败的测试，再写实现。
- **并行开发**：Claude 先搭共享骨架，定好跨模块的调用方、入口函数和签名，建好类型、接口、路由、i18n 键和一条会失败的测试。文件范围互不重叠且无依赖的任务交给子代理并行，同一批文件只有一个写入者；拆不干净就不拆。
- **子代理**：任务单写清可改的路径、允许的命令、禁止 git 写操作、验收标准及报告内容（改动文件、测试汇总行原文、未完成项和待定取舍）。主会话核对仓库后再转述结论，读过 diff、跑过受影响的测试后才提交。
- **Codex**：工作量大、规则清楚、能按文件切开的活派给 Codex；几行的小改、涉及多处的设计权衡和 L2 设计由 Claude 负责。用 `desktop-dispatch:send` 派发，`desktop-dispatch:wait` 在后台等待并在结束时唤醒会话。Codex 可以自己跑容器测试：经 `desktop-dispatch` 派发的任务遇到沙箱限制时按命令逐条申请权限，由 Codex 的自动审批决定，不需要用户点击；任务正文要写明允许的 Docker 上下文、具体命令和申请提权的那两段话。申请被拒绝或超时时由 Claude 跑。Codex 的产出要读过 diff、核对过测试结果后由 Claude 提交，提交信息注明哪些部分由 Codex 完成。
- **复审与验证**：按 [verify](.claude/skills/verify/SKILL.md) 同时派 `reviewer` 复审并跑受影响的测试，后端全量只在门禁中跑。第二轮复审只看修改的部分。没有必须修的项后，对最终 HEAD 跑一次 `./dev.ps1 ci -Report`，HEAD 变更后重跑。GitHub Actions 没有额度，不查看、不排查；门禁以提交状态 `local-ci` 为准。
- **提交与 PR**：进度、验证命令和结果写进 PR 描述。无关问题用 `gh issue create --label backlog` 记录后继续，不扩大范围。`git add`、`git commit`、`git push`、`gh pr create` 各自单独执行，不用 `;` 串成一条。长提交信息或 PR 正文先写入 `.verification/`，再用 `git commit -F` 或 `gh pr create --body-file`。
- **合并**：确认 PR 分支包含最新 main，使门禁覆盖即将合并的代码。最终 HEAD 的 `local-ci` 为 success 且复审没有必须修的项后，L0、L1 由开发会话自己合并，L2 的开发会话做到 ready 后停下，由主会话或用户审过再合并。合并用 `gh pr merge <n> --squash --match-head-commit <sha>`。
- 派 Codex 见 [dispatch-codex](.claude/skills/dispatch-codex/SKILL.md)。审查合并 PR 统一按 [review-pr](.claude/skills/review-pr/SKILL.md) 执行，包括 `/need` 的合并步骤。

## 6 级别定义

按 PR 实际改动的路径取最高级别，里程碑不整体定级。拿不准按高一级。涉及 L2 范围先停下来问，再动手。

- **L0**：文案、样式、纯文档。
- **L1**：纯界面功能、新页面、新接口（含只读接口）、新查询、连接器的只读能力；表结构保持原样。
- **L2**：仅限数据库迁移；认证、权限、会话、CSRF；AI 写入路径与审核流程；发布与回滚；外部数据源连接与凭据；`compose.yaml`、`dev.ps1`；规则本身，即 `AGENTS.md`、`docs/ui-guidelines.md` 与 `.claude/` 下的文件（技能、子代理、授权规则 `.claude/settings.json`）。

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
