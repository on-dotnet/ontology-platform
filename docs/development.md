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
./dev.ps1 e2e          # 端到端冒烟（Playwright + Chromium）：自起一套 op-tmp-e2e-* 临时 postgres/api/web，用 web/e2e/e2e.env 的测试账号，跑完全部删除；不在门禁里
./dev.ps1 lock api     # 改了 backend/pyproject.toml 之后
./dev.ps1 lock web     # 改了 web/package.json 之后
./dev.ps1 gen-api      # 改了后端接口之后，同步前端类型
./dev.ps1 schema-check # 检查前端类型是否与后端接口一致（门禁里也会跑）
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
5. worktree 删掉以后，它的镜像标签会留下。`./dev.ps1 images` 列出本项目的镜像（`ontology/*`）及所属工作区，`./dev.ps1 clean-images` 删除已不存在的工作区的标签。它只删符合"目录名-8 位哈希"格式、且不属于任何现存工作区的 `ontology/*` 标签；不符合这个格式的标签（如 `local`、用 `OP_IMAGE_TAG` 指定的 `my-custom`、`<none>`）一律不动；`git worktree list` 失败时什么也不删；不 prune、不强制删除，仍有容器在用的镜像会保留。
6. 仓库的 Claude Code 钩子 `.claude/hooks/guard-dev-commands.mjs` 会在 Bash 和 PowerShell 命令执行前检查命令文本：含 `dev.ps1 reset` 的命令在任何目录都会被拦下，只能由用户本人运行；含 `dev.ps1 down` 的命令在 worktree 里会被拦下，需要停开发栈时请主会话或用户在主检出目录运行。`up` 和其他子命令不受影响。钩子只按文本匹配，宁可多拦：命令里只是提到这几个词也会被拦。钩子自身出错时一律放行，已有的 deny 规则仍是底线。测试：`node --test .claude/hooks/`。
7. `ci`、`test` 被 Ctrl+C 中断时，在控制台里子进程会收到同一个中断并清理自己的临时容器；在别的环境里子进程可能还在跑，重跑前用 `docker ps --filter name=op-tmp-` 确认。

## Protégé 往返检查 `./dev.ps1 owl-check`

用 Protégé 底层的库 OWL API（4.5.29）检查平台的导出能否被 Protégé 原样读写。步骤：

1. 在临时 api 容器里，把 `samples/owl-features` 的每个样例、钢铁样例（三个文件合在一起）、开发栈每个本体的当前版本（开发栈在运行时）导入平台再导出；
2. 在断网的 OWL API 容器（镜像 `ontology/owlapi:<工作区标签>`，由 [dev/owlapi](../dev/owlapi) 构建）里读入并另存为 Turtle；
3. 把另存的文件当作对同一本体的导入读回，比较差异。

通过的条件：OWL API 没有解析错误，也没有未解析的三元组；读回后没有差异，只允许导入时标为"Protégé 会改写"的公理被改写。判定规则见[规格 002](specs/002-m2-ontology-workbench.md) 第 4.3 节。

报告、导出文件和 OWL API 的输出都存放在 `.verification/owl-check/`。构建工具镜像时，Maven 依赖经 `dev/mirrors.cn.env` 里的 `OP_MAVEN_MIRROR` 下载。这个命令不纳入门禁。

## 门禁 `./dev.ps1 ci`

先校验 compose 配置，再同时运行 `test-api`（全量）、`test-web`、构建 api 与 web 运行镜像（`build`）、接口类型检查（`schema-check`），四项各写一个日志到 `.verification/ci/`。全部结束后按这个顺序打印：通过的一项打出汇总行，失败的一项打出失败用例和日志末尾。任一步失败即整体失败，退出码为 1。汇总行和提交状态里，接口类型检查记作 `schema`，例如 `compose=ok test-api=ok test-web=ok build=ok schema=ok`。带 `-Report` 时要求工作区干净、提交已推送，并把结果写成 GitHub 提交状态 `local-ci`。`./dev.ps1 test` 同样同时运行 `test-api`、`test-web`，日志在 `.verification/test/`。

接口类型检查 `./dev.ps1 schema-check` 用 `gen-api` 同一个生成函数从当前代码生成 `web/src/api/schema.d.ts` 的内容，与仓库里的文件比较（两边的换行都按 LF 比较）。不一致就失败，显示差异的开头，并提示运行 `./dev.ps1 gen-api` 后提交；完整的两份文件留在 `.verification/gen-api/`。它要用 api 运行镜像，所以在门禁里等 `build` 完成后才开始；test-web 镜像由它自己再构建一次（与 `test-web` 一步共用缓存），不等 `test-web` 跑完。实测门禁总耗时与加这一项之前持平（约 42 秒）。

开发中不要先手动跑一遍全量再跑门禁：只跑受影响的测试，复审通过后对最终 HEAD 跑一次门禁（见 [AGENTS.md](../AGENTS.md) 第 5 节）。

## Docker 主机的限制

- CPU 目前只有 x86-64-v1 指令集：Doris 无法运行；NumPy 2.4 及以上会崩溃。依赖选型时避开需要 SSE4.2/AVX 的包。
- 无法直接访问 api.openai.com 与 github.com，模型调用经本机代理出去（见下节）。

## 审核模式

`OP_REVIEW_MODE` 决定谁能审核变更集（规格 002 第 8 节）：

- `single`（默认）：reviewer 和 admin 可以审核、合并自己提交的变更集；他们手工编辑时"保存"直接生效。
- `separate`：任何人都不能审核自己提交的变更集（返回 403 `changeset.self_review`），手工编辑一律提交审核，由另一位审核人处理。

在本机配置文件里写 `OP_REVIEW_MODE=separate`，再运行 `./dev.ps1 up` 生效。设置页会显示当前模式。

## 冶金样例库 `./dev.ps1 seed-steel`

M3 的数据绑定与查询用一套人工合成的冶金 MES 数据作外部数据源（`samples/steel/relational/`，规格 003 第 11 节）。

1. 开发栈运行时执行 `./dev.ps1 seed-steel`。它在开发用的 postgres 实例里建库 `steel_mes` 和只读账号 `steel_reader`（口令 `steel-reader-dev-only`，只在开发环境使用，性质同开发管理员口令），执行两个 SQL 文件，授予该账号对 `mes` 模式的查询权限，并把账号的默认事务设为只读。每次运行都重建 `mes` 模式，可以重复运行；它只动 `steel_mes` 这个库，不碰平台自己的库；`OP_ENV=production` 时拒绝运行。
2. 在"数据"页新建数据源：主机 `postgres`，端口 5432，库 `steel_mes`，用户 `steel_reader`，口令同上。
3. 测试镜像里只有 `backend/`，所以 `backend/tests/fixtures/connectors/steel/` 放同样的两个 SQL 文件；改样例时两处一起改，`seed-steel` 装载前会比对，不一致就停下。测试不依赖 `seed-steel`：每个测试进程自己建临时库装入样例（`backend/tests/external_source.py`）。

## 数据源凭据的密钥轮换

数据源的口令用 `OP_SECRET_KEY` 派生的密钥加密存库（规格 003 第 5.4 节），数据库备份里只有密文，密钥要另外保管。更换密钥的步骤：

1. 在本机配置文件里把旧值放进 `OP_SECRET_KEY_PREVIOUS`（可以有多个，逗号分隔），新值放进 `OP_SECRET_KEY`，重启 api 和 worker。这时旧密文仍能解开，新写入一律用新密钥。
2. 在 api 容器里运行 `python -m ontology_platform.modules.connectors.rekey`，把全部凭据用新密钥重新加密。输出只有条数（重新加密的、解不开的）。
3. 去掉 `OP_SECRET_KEY_PREVIOUS`，重启。

密钥丢失或填错时，数据源显示"保存的口令无法读取"（`datasource.credential_unreadable`），由管理员重新填写口令即可，其余功能不受影响。

## 大模型

模型配置只经环境变量提供。Key 不进仓库、不写日志、不在任何接口返回。

1. 运行 `./dev.ps1 init-env`，在生成的本机配置文件里填 `OP_OPENAI_API_KEY`。
2. Docker 主机访问不了 OpenAI 时，填 `OP_AI_PROXY=http://用户:口令@本机IP:端口`，指向本机已有的代理（例如 Clash Verge 的 mixed-port，需开启"允许局域网连接"并设置认证）。代理只作用于模型调用，不影响数据库、依赖下载等其他流量。
3. `./dev.ps1 ai-check`：对 `OP_AI_MODEL`、`OP_AI_REASONING_MODEL` 各发一次最小的结构化调用，带上识别时用的推理强度（`OP_AI_EFFORT`、`OP_AI_REASONING_EFFORT`），只输出"可用 / 不可用"、模型、强度和错误类型，不打印 Key 和代理。兼容服务不认 `reasoning.effort` 时，这里会报 HTTP 400，把两个强度设为 `default` 即可。
4. `./dev.ps1 eval [案例]`：识别评测，见下一节。

未配置 Key 时平台照常运行，资料可以上传，但识别会以 `ai.not_configured` 失败；配置好后在资料页重试即可。

## 识别评测

`./dev.ps1 eval [案例]` 用 `samples/<案例>/docs` 的资料按顺序跑识别，按 `samples/<案例>/eval/expected.toml` 打分，结果存到 `.verification/eval/<案例>-<时间>.json`。不在门禁里运行。识别结果按合并计划（规格 004 第 5.2 节）合并，模拟审核人全部接受：与工作版本里的元素是同一个的并入它，局部名被占用的改名，跳过的项按合并的错误码计。跑两个场景（规格 004 第 10 节）：

- **顺序场景**（结果的顶层）：每份资料的变更集合并后再识别下一份，后面的资料与前面的结果对齐。分数与以前的基线可比。
- **同基线场景**（结果的 `sameBaseline`）：全部资料都对着起始本体识别，识别完再按顺序合并，相当于一次上传多份、之后才审核。`-Sequential` 不跑这个场景。

两个场景都在 `merge` 里报告被跳过的项（`skipped`、`skippedByCode`）、重复的关系（端点和名称与前面某条相同，`duplicateRelations`），有答案时还报告重复的类型（同一期望组里有几个类型，`duplicateTypeGroups`：主名称相同的、有 `possible_duplicate` 标记的、没有标记的各多少组）。

**录制与回放**。每次模型调用按"用途、模型、提示词、输入文字、输出结构的 JSON Schema、附件"的哈希录制，存在 `.verification/eval/recordings/<案例>/<哈希>.json`，另有 `models.json` 记下最近一次有新录制的运行用的模型。录制文件里是哈希、用途、模型名、资料名、模型的结构化输出和调用次数、token 数，没有 Key 和代理地址。哈希不含服务地址：同一个模型名换了服务商，回放的仍是原来的输出。

- 默认：有录制的调用直接回放，没有的才调用模型并录下来。只为输入变了的调用付费：改了某个阶段的提示词，付这个阶段和输入受它影响的后续调用；改了确定性的后处理（如 `build_proposals`），第一份资料和各资料的 terms 阶段不受影响，顺序场景从第二份资料起 types、relations 阶段的提示词里有前面资料合并进来的对象类型，结果变了就要重新调用（关系和属性不进提示词）。同基线场景的 types、relations 阶段只看起始本体，输入与顺序场景不同（第一份资料除外），要单独录制一次；之后同样免费回放。资料、分块和合并后元素的 id 由名称派生，同样的输入每次得到同样的提示词。
- `-Replay`：只回放。任何一次调用没有录制就失败（同基线场景还没录过时，加 `-Sequential` 只回放顺序场景），并说明是哪份资料、哪个阶段。容器拿不到 Key 和代理，模型用 `models.json` 里记的，所以在没有本机私有配置的 worktree 里也能跑。
- `-Recordings <目录>`：换一个录制目录。在别的 worktree 里用主检出目录的录制：`./dev.ps1 eval steel -Replay -Recordings <主检出目录>/.verification/eval/recordings/steel`。
- 想全部重新调用模型，换一个空目录或删掉录制目录。录制不会自动清理，过时的只是不再命中。

**期望答案的格式**（TOML，规范化规则：去空白、全角转半角、小写）：

- `entity_types = [{ names = [...], core = true|false }]`：模型给出的中文名、英文名、本地名或任一同义词与 `names` 中任一项相同即命中。
- `relations = [{ domain, range, core }]`：两端用对象类型 `names` 的第一个名字，不计较方向和名称。
- `properties = [{ domain, names, core }]`（可选）：`domain` 用对象类型 `names` 的第一个名字；属性所属类型是这一项、且名称与 `names` 任一项相同才命中。
- `hierarchy = [{ child, parent, core }]`（可选）：子类与父类都用对象类型的第一个名字，方向要对。
- 准确率 = 命中任一期望项（含 `core = false`）的预测数 / 预测总数；召回率 = 找到的 `core = true` 项 / `core = true` 项总数。属性与层级没有分母时（没有预测，或没有 `core` 项）记 `null`，屏幕上显示 `-`；类型与关系沿用以前的口径（没有预测记 0）。没有 `properties`、`hierarchy` 段的案例只报预测数量，类型与关系的分数与以前的算法相同。
- 答案在调用模型之前先检查：缺字段、两端不是某个类型的第一个名字，都会直接失败并指出是哪一条。

结果还包括证据定位率（`groundedShare`：没有 `evidence_not_found` 标记的项的比例）、证据字面核验率（`literalShare`：模型所引的那一句里出现该项名称的比例，关系要两端都出现；按类型、关系、属性分列，规格 004 第 7.2 节），以及每份资料、每个阶段的模型调用次数（含重试；回放命中记 0 次，另计 `replayed`）、耗时和输入、输出、推理 token，汇总在 `usage`；`usage.elapsed` 是每份资料从开始识别到结束的秒数（同一份资料的各批同时调用，所以它小于各次调用的耗时之和；`total` 是各份资料依次识别的秒数之和）；`recorded…` 各项是每次调用录制时的耗时与 token，回放的调用也计入，用来比较两次运行的用量（PR 4 之前的录制没有耗时和推理 token）。录制的键包含推理强度（`OP_AI_EFFORT`、`OP_AI_REASONING_EFFORT`），`models.json` 记下录制时的强度供回放使用。改了 `expected.toml` 想重新打分而不重跑，可把结果里的 `elements`、`parents` 和新的期望答案经 `--rescore` 重新计分（见 `ai/eval.py` 开头的说明）；结果顶层是顺序场景，同基线场景用 `sameBaseline.elements` 和 `sameBaseline.parents`。

**不入库的资料**。脱敏后的真实资料不提交进仓库，放在 `.verification/private-docs/<名称>/`（`.verification/` 已被 Git 忽略），结构同案例包：`docs/` 放资料，`eval/expected.toml` 可以没有。把目录路径当作案例参数：

```powershell
./dev.ps1 eval .verification/private-docs/<名称>
```

参数里带 `/` 或 `\` 就按目录处理，结果存为 `.verification/eval/dir-<名称>-<时间>.json`，录制存在 `.verification/eval/recordings/dir-<名称>/`，都不出 `.verification/`。没有 `eval/expected.toml` 时只做识别：输出识别出的元素、各阶段耗时与 token，并提示"没有答案，未打分"；答案后补上以后，加 `-Replay` 再跑一次即可打分，不再调用模型。注意：评测时资料内容会发给配置的模型服务（经 `OP_AI_BASE_URL`、`OP_AI_PROXY` 配置的地址），资料要先脱敏，且只能交给允许接收它的服务。

案例包的规则（答案先写、留出集只用来测量）见 [samples/README.md](../samples/README.md)。
