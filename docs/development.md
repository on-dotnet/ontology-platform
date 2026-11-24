# 开发手册

## 环境

| 环境 | 角色 |
|---|---|
| 本机（Windows） | 存放代码，运行 Claude Code、Codex、git、PowerShell 7。不需要安装 Python、Node 包管理器或 .NET |
| Docker 主机 10.16.0.13 | rootless Docker，运行开发栈和所有构建、测试容器；docker 上下文 `linux013-rootless` |

- rootless Docker 无法绑定挂载本机目录，所以构建和测试都把当前工作区打进镜像再运行；锁文件在容器里生成后用 `docker cp` 取回。
- 发布的端口必须大于 1024。开发栈只发布 web：`http://10.16.0.13:28080`。
- 依赖源默认走国内镜像（[dev/mirrors.cn.env](../dev/mirrors.cn.env)），设置 `OP_MIRROR=off` 关闭。Python 锁文件始终指向官方 PyPI。
- 可覆盖的设置写在仓库根目录的 `.env.local`（已被 Git 忽略），例如 `OP_WEB_PORT=28081`。`./dev.ps1 init-env` 会从 [.env.example](../.env.example) 复制一份模板（文件已存在时不覆盖）。

## 开发账号

开发环境首次启动时自动创建管理员：用户名 `admin`，密码 `admin12345`（只在开发环境使用；生产环境必须通过 `OP_ADMIN_PASSWORD` 显式设置，否则拒绝启动）。

## 常用流程

```powershell
./dev.ps1 up           # 构建并启动，等待健康
./dev.ps1 test-api tests/test_ai_pipeline.py '-x'   # 开发中只跑受影响的测试；PowerShell 里以 - 开头的参数要加引号
./dev.ps1 test-api tests/test_auth.py tests/test_workbench.py '-n' '4'   # 文件多时可以加 -n 并行
./dev.ps1 test-api     # 后端全量（ruff、mypy、pytest），一般交给门禁
./dev.ps1 fmt <文件…>  # 在容器里用 ruff 修正并格式化指定的后端文件
./dev.ps1 test-web     # 前端检查（eslint、tsc、vitest 同时跑）
./dev.ps1 lock api     # 改了 backend/pyproject.toml 之后
./dev.ps1 lock web     # 改了 web/package.json 之后
./dev.ps1 gen-api      # 改了后端接口之后，同步前端类型
./dev.ps1 owl-check    # 改了 OWL 导入导出之后，做一次 Protégé 往返检查
./dev.ps1 ci -Report   # 复审通过、提交并推送之后，对最终 HEAD 跑一次完整门禁
```

## 测试的组织

- 后端全量用 pytest-xdist 跑 8 个进程（在 16 核的 Docker 主机上实测，12、16 个不再变快）。每个进程由 `backend/tests/conftest.py` 的会话级夹具 `database_url` 新建一个临时库并迁移到最新版，跑完删除；进程之间只共用 PostgreSQL 服务本身。临时设置进程数：本机配置里写 `OP_TEST_WORKERS=4`，`0` 表示单进程。
- 带参数的 `test-api`（指定文件）默认单进程，需要时自己加 `'-n' '4'`。
- 测试期间密码哈希换成低成本的 Argon2id 参数（`support.TEST_HASHER`），生产参数不变，由 `test_production_hashes_keep_the_rfc_9106_low_memory_profile` 守住。新测试不要依赖哈希的耗时。
- 测试之间不得共享可变状态：文件写到 `tmp_path`，不用固定的端口、目录或数据库名。

## 并行开发

几个会话可以同时开发，各自在一个 git worktree 里工作：

1. 每个会话一个 worktree、一条分支，例如 `git worktree add ../op-feat-x -b feat/x origin/main`。Claude Code 的会话默认就建在 `.claude/worktrees/` 下的独立 worktree 里。
2. 构建和测试的镜像带工作区标签：主检出目录是 `local`，其他 worktree 是"目录名-路径哈希"（例如 `ontology/test-api:faster-gate-354080-21e96cdc`），由 `dev.ps1` 按所在目录算出，也可以用 `OP_IMAGE_TAG` 指定。两个工作区同时跑 `test-api`、`test-web`、`ci`，各用各的镜像和临时数据库，结果只取决于各自的代码。
3. 开发栈（`up`、`status`、`psql`）只有一套，postgres 和数据卷共用：同一时间只让一个工作区运行 `./dev.ps1 up`，最后一次 `up` 的工作区决定开发栈跑的是哪份代码。测试的临时库也建在这个 postgres 里，所以：
   - 别在有人跑测试时运行 `./dev.ps1 down`：它会停掉共用的 postgres，并删掉同一 compose 项目下的一次性容器，其他工作区正在跑的测试会中断。
   - 每次 `test-api` 都会 `up -d postgres`。哪个工作区的 postgres 配置（`compose.yaml` 里的 postgres 服务，或 `OP_POSTGRES_PASSWORD` 等设置）和正在运行的不同，就会重建共用的 postgres 容器（数据卷保留），同样会打断别人。改 postgres 服务定义的分支，测试时先确认没有别的会话在跑。
4. 本机私有配置 `.env.local` 不在 Git 里，新 worktree 里没有。主检出目录的这份没有改 `OP_POSTGRES_PASSWORD`、`OP_DOCKER_CONTEXT`、`OP_MIRROR` 时，跑测试和门禁不需要它；改了的话，由用户本人把它复制到 worktree，否则 worktree 会用默认值，触发上一条的重建或连错主机。要在 worktree 里 `up`、`ai-check`、`eval` 也需要复制，否则开发栈会以"AI 未配置"启动。
5. worktree 删掉以后，它的镜像标签会留下。`./dev.ps1 images` 列出本项目的镜像（`ontology/*`）及所属工作区，`./dev.ps1 clean-images` 删除已不存在的工作区的标签。它只删符合"目录名-8 位哈希"格式、且不属于任何现存工作区的 `ontology/*` 标签；`local`、用 `OP_IMAGE_TAG` 指定的标签和 `<none>` 一律不动；`git worktree list` 失败时什么也不删；不 prune、不强制删除，仍有容器在用的镜像会保留。
6. `ci`、`test` 被 Ctrl+C 中断时，在控制台里子进程会收到同一个中断并清理自己的临时容器；在别的环境里子进程可能还在跑，重跑前用 `docker ps --filter name=op-tmp-` 确认。

## Protégé 往返检查 `./dev.ps1 owl-check`

用 Protégé 底层的库 OWL API（4.5.29）检查平台的导出能否被 Protégé 原样读写。步骤：

1. 在临时 api 容器里，把 `samples/owl-features` 的每个样例、钢铁样例（三个文件合在一起）、开发栈每个本体的当前版本（开发栈在运行时）导入平台再导出；
2. 在断网的 OWL API 容器（镜像 `ontology/owlapi:<工作区标签>`，由 [dev/owlapi](../dev/owlapi) 构建）里读入并另存为 Turtle；
3. 把另存的文件当作对同一本体的导入读回，比较差异。

通过的条件：OWL API 没有解析错误，也没有未解析的三元组；读回后没有差异，只允许导入时标为"Protégé 会改写"的公理被改写。判定规则见[规格 002](specs/002-m2-ontology-workbench.md) 第 4.3 节。

报告、导出文件和 OWL API 的输出都存放在 `.verification/owl-check/`。构建工具镜像时，Maven 依赖经 `dev/mirrors.cn.env` 里的 `OP_MAVEN_MIRROR` 下载。这个命令不纳入门禁。

## 门禁 `./dev.ps1 ci`

先校验 compose 配置，再同时运行 `test-api`（全量）、`test-web`、构建 api 与 web 运行镜像，三项各写一个日志到 `.verification/ci/`。全部结束后按这个顺序打印：通过的一项打出汇总行，失败的一项打出失败用例和日志末尾。任一步失败即整体失败，退出码为 1。带 `-Report` 时要求工作区干净、提交已推送，并把结果写成 GitHub 提交状态 `local-ci`。`./dev.ps1 test` 同样同时运行 `test-api`、`test-web`，日志在 `.verification/test/`。

开发中不要先手动跑一遍全量再跑门禁：只跑受影响的测试，复审通过后对最终 HEAD 跑一次门禁（见 [AGENTS.md](../AGENTS.md) 第 5 节）。

## Docker 主机的限制

- CPU 目前只有 x86-64-v1 指令集：Doris 无法运行；NumPy 2.4 及以上会崩溃。依赖选型时避开需要 SSE4.2/AVX 的包。
- 无法直接访问 api.openai.com 与 github.com，模型调用经本机代理出去（见下节）。

## 审核模式

`OP_REVIEW_MODE` 决定谁能审核变更集（规格 002 第 8 节）：

- `single`（默认）：reviewer 和 admin 可以审核、合并自己提交的变更集；他们手工编辑时"保存"直接生效。
- `separate`：任何人都不能审核自己提交的变更集（返回 403 `changeset.self_review`），手工编辑一律提交审核，由另一位审核人处理。

在本机配置文件里写 `OP_REVIEW_MODE=separate`，再运行 `./dev.ps1 up` 生效。设置页会显示当前模式。

## 大模型

模型配置只经环境变量提供。Key 不进仓库、不写日志、不在任何接口返回。

1. 运行 `./dev.ps1 init-env`，在生成的本机配置文件里填 `OP_OPENAI_API_KEY`。
2. Docker 主机访问不了 OpenAI 时，填 `OP_AI_PROXY=http://用户:口令@本机IP:端口`，指向本机已有的代理（例如 Clash Verge 的 mixed-port，需开启"允许局域网连接"并设置认证）。代理只作用于模型调用，不影响数据库、依赖下载等其他流量。
3. `./dev.ps1 ai-check`：发一次最小的结构化调用，只输出"可用 / 不可用"和错误类型，不打印 Key 和代理。
4. `./dev.ps1 eval [案例]`：用 `samples/<案例>/docs` 的资料跑一遍真实识别，按 `samples/<案例>/eval/expected.toml` 打分（对象类型与关系的准确率和召回率、证据定位率），结果存到 `.verification/eval/`。会消耗模型额度，不在门禁里运行。

未配置 Key 时平台照常运行，资料可以上传，但识别会以 `ai.not_configured` 失败；配置好后在资料页重试即可。
