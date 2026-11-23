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
./dev.ps1 test-api     # 后端检查
./dev.ps1 test-api tests/test_ai_pipeline.py '-x'   # 只跑指定测试；PowerShell 里以 - 开头的参数要加引号
./dev.ps1 fmt <文件…>  # 在容器里用 ruff 修正并格式化指定的后端文件
./dev.ps1 test-web     # 前端检查
./dev.ps1 lock api     # 改了 backend/pyproject.toml 之后
./dev.ps1 lock web     # 改了 web/package.json 之后
./dev.ps1 gen-api      # 改了后端接口之后，同步前端类型
./dev.ps1 ci -Report   # 提交并推送之后，对 HEAD 跑完整门禁
```

## 门禁 `./dev.ps1 ci`

依次运行：compose 配置校验、`test-api`、`test-web`、构建 api 与 web 运行镜像。任一步失败即整体失败。带 `-Report` 时要求工作区干净、提交已推送，并把结果写成 GitHub 提交状态 `local-ci`。

## Docker 主机的限制

- CPU 目前只有 x86-64-v1 指令集：Doris 无法运行；NumPy 2.4 及以上会崩溃。依赖选型时避开需要 SSE4.2/AVX 的包。
- 无法直接访问 api.openai.com 与 github.com，模型调用经本机代理出去（见下节）。

## 大模型

模型配置只经环境变量提供。Key 不进仓库、不写日志、不在任何接口返回。

1. 运行 `./dev.ps1 init-env`，在生成的本机配置文件里填 `OP_OPENAI_API_KEY`。
2. Docker 主机访问不了 OpenAI 时，填 `OP_AI_PROXY=http://用户:口令@本机IP:端口`，指向本机已有的代理（例如 Clash Verge 的 mixed-port，需开启"允许局域网连接"并设置认证）。代理只作用于模型调用，不影响数据库、依赖下载等其他流量。
3. `./dev.ps1 ai-check`：发一次最小的结构化调用，只输出"可用 / 不可用"和错误类型，不打印 Key 和代理。
4. `./dev.ps1 eval [案例]`：用 `samples/<案例>/docs` 的资料跑一遍真实识别，按 `samples/<案例>/eval/expected.toml` 打分（对象类型与关系的准确率和召回率、证据定位率），结果存到 `.verification/eval/`。会消耗模型额度，不在门禁里运行。

未配置 Key 时平台照常运行，资料可以上传，但识别会以 `ai.not_configured` 失败；配置好后在资料页重试即可。
